"""Differential test for src/sound.c — the sound module's SFX trigger, the stub that calls it, and
the STOP CHAIN that drives the chip.

THE FIRST BATTERY INSIDE THE SOUND MODULE. Everything at $17adc..$1abc8 is one PC-relative replayer
the game reaches only through the stub table at its head, and $1a48a is the one routine in it that
touches nothing but RAM: no PSG port, no supervisor mode, no call out. So a trigger case here is the
same whole-image differential as everywhere else, and what it proves is narrow and worth stating —
that the right bytes landed in the right module fields. WHAT IS HEARD is the per-VBL tick at $17c74,
which reads this state and writes $ff8800, and nothing here says anything about it.

...AND THE FIRST BATTERY ANYWHERE THAT DRIVES THE YM2149. `snd_stop` -> `snd_stop_all_sfx` ->
`snd_psg_silence` end in four chip accesses, and the first of them is a READ: `ori.b #$3f,d1` sets
the six tone/noise enables and LEAVES BITS 6-7, the port A/B I/O direction lines. Those bits are an
INPUT of the run — nothing in the routine computes them — so every case here declares them with
`psg_seed={7: …}`, both cores are served the same byte, and the ordered access ledger plus the
register file the run leaves are compared alongside the image (tools/recreate_kit/TRAP_MODEL.md,
"Phase 6"; none of it is IN the image, so nothing else could see a divergence). One case declares
NOTHING and requires the oracle to refuse the run, which is the guard those cases rest on.

WHY THAT MATTERS MORE THAN IT LOOKS. Before the seeded model the read had no correct answer and was
served 0 — and `0 | $3f` and `read | $3f` agree, so a reconstruction that ignored the read-back
would have been GREEN while writing $3f, flipping port A to input and floating the floppy
drive-select lines. That mutant is one of the sweep's, and it is caught by the ledger alone.

WHAT THE CASES HOLD

  * BOTH SOURCES OF TABLE DATA. The pointer table at $1a830 and the 26 descriptors behind it are in
    the image, so a case can run the SHIPPED data — every id the game passes and every id the table
    has — and can also POKE a table entry to redirect an id at a descriptor of its own. Both,
    because the shipped data does not reach every arm: no shipped descriptor carries a volume index
    outside 0..9, and only a seeded one puts the id's own bytes where a case chose them.
  * THE ARITHMETIC PAST THE TABLE'S END. `ext.w d0 / add.w d0,d0` makes the id a SIGNED byte and
    there is no bounds check, so ids $1a..$7f read past the table and $80..$ff read BACKWARDS off
    it. Every one of the 256 lands inside the image — a word entry added to the module base spans
    32 KiB either side of it — so the model computes the same address the instructions do rather
    than the cases stopping where the data stops.
  * THE COPY'S DIRECTION. The descriptor reaches the channel state through `move.b (a0)+,(a1)+`,
    which walks UP, and three of the table's entries put a descriptor just BELOW channel C's state
    and overlapping it — so the copy re-reads bytes it has already written. Nothing but such an id
    tells that apart from a block move, and the state block is seeded so the propagated bytes are
    not the zeros the shipped image leaves there.
  * THE THREE CHANNELS. $1a494, $1a504 and $1a56e are the same fifteen instructions with the
    channel's own offsets. $6b46 (actor_damage_template_hitpoints, `move.w #$1,d1`) is the one call
    site in the image that does not ask for A, so the B arm is LIVE code reached from the shipped
    game and only C is dead — pinned anyway, because the entry pin CLAIMS the three arms are one
    base-plus-stride and only a case shows they behave that way.
  * THE STUB'S REGISTER PRESERVATION. $17b14 is `movem.l d0-a6,-(a7) / bsr / movem.l (a7)+ / rts`.
    Memory cannot show that, so the case enters the oracle with a distinct value in every register
    the oracle reports and requires all fifteen back, WITH the effect's writes landing.

  * THE STOP CHAIN'S THREE ENTRY POINTS. `snd_stop` and `snd_stop_all_sfx` are stub-table entries
    (+28 and +70) and `snd_psg_silence` is the tail both `bra.w` into, so each is run on its own and
    each case states the module state that entrant is entitled to write — which is what says the
    engine flag belongs to the outer one and the shadow bytes to the middle one.

...AND NOW THE TICK ITSELF. $18106 walks one channel's pattern stream through 24 opcode handlers
that live BELOW it and branch back INTO it, and $17ca0 is snd_music_tick under its tempo head: the
gate, the fractional tick DROPPER, the SFX engine, the fade, the row step, the period/volume pass,
the SFX mixdown and the chip write. Two things about it are worth stating before the cases:

  * THE OPCODE GRID'S REACHABILITY COLUMN IS DERIVED. `_shipped_pattern_census` decodes every pattern
    the 17 songs reach and counts what it finds, so "the shipped data reaches this handler" is the
    DATA's claim per row. Eleven of the 24 are reached; thirteen are pinned from a seeded stream and
    say so. The walk self-proves: every one of the 106 patterns ends in $87 or $8e, so those two
    counts have to add up to the pattern count exactly.
  * THE NON-LOCAL EXIT IS PINNED FROM THE TICK AND NEVER STANDALONE. Opcode $8e's `addq.l #4,sp`
    unwinds snd_channel_step's frame, so entered at $18106 it would pop the runner's own sentinel.
    The C reports it as a status, the tick acts on it, and the case runs the whole tail from $17ca0
    — with the PSG ledger as the proof that the rest of the tick never ran.

KNOWINGLY NOT PINNED
  * WHAT IS HEARD. The tick and everything it calls ARE ported now, and the chip surface is a real
    one — an ordered ledger of up to fifteen accesses per tick and a register file — but it is
    register values, not sound. A green suite says the right bytes reached the right PSG registers
    in the right order and says nothing about the audio.
  * THE MODULE'S OTHER MUTABLE STATE — the music channel states, the PRNG and the globals besides
    the engine flag, the SFX-active flags and the four PSG shadow bytes the stop chain clears.
    Nothing here models the rest: the write set each case allows is exactly its routine's, so a port
    that reached one of them reddens as a stray write rather than being covered by a model that does
    not exist.
  * THE SUPERVISOR WINDOW. `snd_psg_silence` masks interrupts around its chip writes
    (`move sr,d2 / move #$2700,sr … move d2,sr`) so the per-VBL tick cannot write the chip mid
    sequence. The reconstruction makes no attempt at it — there is no C analogue and no interrupt to
    keep out — and the oracle enters every run at SR = $2700 anyway, so the mask is a no-op there.
    What IS observable is the saved SR arriving in d2, and one case asserts it.
  * WHAT AN SFX SOUNDS LIKE, or what a descriptor field means beyond the role
    ../notes/sound_module_recon.md read off the tick.
  * THAT A REAL ST ANSWERS $fffa01 AND $ff820a THE WAY A CASE DECLARES. The 44-byte tempo head at
    $17c74 branches on both, and the cases declare them with `hw_seed=` (TRAP_MODEL.md, "Phase 7")
    — so what is pinned is "given these bytes, both cores agree", never "the machine holds them".
    `hw_seed={$fffa01: $b0, $ff820a: $02}` is a claim about a 50 Hz colour ST, documented rather
    than measured, and it is the kit's own honest limit rather than this battery's.
  * $98..$b7, the one branch of the ported code that is not reproduced: the dispatch reads a word of
    the handlers' own instruction stream as a jump target. No shipped pattern byte is one.
"""
import ctypes
import pathlib
import re

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, RTS, add_w_dn_dn, addi_w_dn, assert_psg_surfaces,
                  branch_w_to, bsr_w, btst_imm_dn, assert_bands_are_seeded, clr_b_d16, clr_w_d16, clr_w_dn, longword, lsl_w_imm_dn,
                  move_b_abs_l_dn, move_b_d16_dn, move_b_imm_abs_l, move_b_imm_d16,
                  move_b_postinc_dn, move_w_ind_dn, moveq, opcode, overlay, subi_w_dn, tst_b_d16,
                  word)
from layout import wb

import emu      # noqa: E402  (harness puts the kit's oracle on sys.path)
import loader   # noqa: E402

# --- the module's layout, from the header both languages read ------------------------------------
MODULE_BASE = wb("SND_MODULE_BASE")
PTR_TABLE = wb("SND_SFX_PTR_TABLE")
SFX_IDS = wb("SND_SFX_IDS")
DESCRIPTORS = wb("SND_SFX_DESCRIPTORS")
DESCRIPTOR_LEN = wb("SND_SFX_DESCRIPTOR_LEN")
VOLUME_PTRS = wb("SND_SFX_VOLUME_PTRS")
VOLUME_STREAMS = wb("SND_SFX_VOLUME_STREAMS")
TABLE_ENTRY_LEN = wb("SND_TABLE_ENTRY_LEN")   # both tables hold a3-relative WORDS

CHANNELS = wb("SND_CHANNELS")
CHANNEL_A = wb("SND_CHANNEL_A")
ACTIVE_FLAGS = wb("SND_SFX_ACTIVE_FLAGS")
ACTIVE = wb("SND_SFX_ACTIVE")
STATE = wb("SND_SFX_STATE")
STATE_LEN = wb("SND_SFX_STATE_LEN")
MIX_PERIOD = wb("SND_SFX_MIX_PERIOD")
MIX_PERIOD_LEN = wb("SND_SFX_MIX_PERIOD_LEN")
MIX_NOISE = wb("SND_SFX_MIX_NOISE")
MIX_VOLUME = wb("SND_SFX_MIX_VOLUME")

DESC_PERIOD_STEP = wb("SND_DESC_PERIOD_STEP")
DESC_TONE_PERIOD = wb("SND_DESC_TONE_PERIOD")
DESC_NOISE_PERIOD = wb("SND_DESC_NOISE_PERIOD")
DESC_MIXER_BITS = wb("SND_DESC_MIXER_BITS")
DESC_VOLUME_INDEX = wb("SND_DESC_VOLUME_INDEX")
DESC_VOLUME_STEP = wb("SND_DESC_VOLUME_STEP")
DESC_SECOND_RELOAD = wb("SND_DESC_SECOND_RELOAD")
MIXER_NOISE_OFF = wb("SND_MIXER_NOISE_OFF")

STATE_PERIOD_COUNT = wb("SND_STATE_PERIOD_COUNT")
STATE_VOLUME_COUNT = wb("SND_STATE_VOLUME_COUNT")
STATE_SECOND_COUNT = wb("SND_STATE_SECOND_COUNT")
STATE_STREAM_BASE = wb("SND_STATE_STREAM_BASE")
STATE_STREAM_CURSOR = wb("SND_STATE_STREAM_CURSOR")

# ...and the stop chain's own: the module state it clears, and the chip registers it drives.
ENGINE_ENABLED = wb("SND_ENGINE_ENABLED")
ENGINE_DISABLED = wb("SND_ENGINE_DISABLED")
ACTIVE_FLAGS_LEN = wb("SND_SFX_ACTIVE_FLAGS_LEN")
PSG_SHADOW = wb("SND_PSG_SHADOW")
PSG_REG_MIXER = wb("PSG_REG_MIXER")
PSG_REG_VOLUME_A = wb("PSG_REG_VOLUME_A")
PSG_REG_VOLUME_B = wb("PSG_REG_VOLUME_B")
PSG_REG_VOLUME_C = wb("PSG_REG_VOLUME_C")
PSG_MIXER_ALL_OFF = wb("PSG_MIXER_ALL_OFF")
PSG_VOLUME_SILENT = wb("PSG_VOLUME_SILENT")
SILENCED_VOLUMES = (PSG_REG_VOLUME_A, PSG_REG_VOLUME_B, PSG_REG_VOLUME_C)

# ...and the TICK TIER's: the module PRNG, the six descriptor/state fields the SFX tick reads that
# the trigger does not, and the whole music channel record $18208 walks.
PRNG_STATE = wb("SND_PRNG_STATE")
PRNG_STATE_LEN = wb("SND_PRNG_STATE_LEN")
PRNG_LOW_WORD = wb("SND_PRNG_LOW_WORD")
PRNG_TAP_MASK = wb("SND_PRNG_TAP_MASK")
PRNG_TAP_BIAS = wb("SND_PRNG_TAP_BIAS")
PRNG_FEEDBACK_BIT = wb("SND_PRNG_FEEDBACK_BIT")

DESC_DURATION = wb("SND_DESC_DURATION")
DESC_SLIDE_AMOUNT = wb("SND_DESC_SLIDE_AMOUNT")
DESC_USE_PRNG = wb("SND_DESC_USE_PRNG")
DESC_SLIDE_DIRECTION = wb("SND_DESC_SLIDE_DIRECTION")
DESC_SLIDE_COUNT = wb("SND_DESC_SLIDE_COUNT")
DESC_SUSTAIN = wb("SND_DESC_SUSTAIN")
SFX_INACTIVE = wb("SND_SFX_INACTIVE")
MIX_PERIOD_LOW = wb("SND_MIX_PERIOD_LOW")
VOLUME_STREAM_LOOP = wb("SND_VOLUME_STREAM_LOOP")

MUSIC_CHANNEL_STATE = wb("SND_MUSIC_CHANNEL_STATE")
MUSIC_CHANNEL_LEN = wb("SND_MUSIC_CHANNEL_LEN")
CH_FLAGS = wb("SND_CH_FLAGS")
CH_VIBRATO_ACC = wb("SND_CH_VIBRATO_ACC")
CH_ARPEGGIO_BASE = wb("SND_CH_ARPEGGIO_BASE")
CH_ARPEGGIO_CURSOR = wb("SND_CH_ARPEGGIO_CURSOR")
CH_VIBRATO_DEPTH = wb("SND_CH_VIBRATO_DEPTH")
CH_VIBRATO_SPEED = wb("SND_CH_VIBRATO_SPEED")
CH_ENVELOPE_SPEED = wb("SND_CH_ENVELOPE_SPEED")
CH_NOTE = wb("SND_CH_NOTE")
CH_VOLUME = wb("SND_CH_VOLUME")
CH_ENVELOPE_COUNT = wb("SND_CH_ENVELOPE_COUNT")
CH_ENVELOPE_CURSOR = wb("SND_CH_ENVELOPE_CURSOR")
CH_ENVELOPE_LAST = wb("SND_CH_ENVELOPE_LAST")
CH_PORTA_LIMIT = wb("SND_CH_PORTA_LIMIT")
CH_PORTA_STEP = wb("SND_CH_PORTA_STEP")
CH_PORTA_CURRENT = wb("SND_CH_PORTA_CURRENT")
CH_PORTA_CONTROL = wb("SND_CH_PORTA_CONTROL")
CH_YIELD = wb("SND_CH_YIELD")
CH_DETUNE = wb("SND_CH_DETUNE")
CH_MIXER_MASK = wb("SND_CH_MIXER_MASK")
CH_FLAG_TOGGLE = wb("SND_CH_FLAG_TOGGLE")
CH_FLAG_VIBRATO = wb("SND_CH_FLAG_VIBRATO")
CH_FLAG_ENVELOPE = wb("SND_CH_FLAG_ENVELOPE")
CH_NOISE_ROUTE_FLAGS = wb("SND_CH_NOISE_ROUTE_FLAGS")
CH_PORTA_ENABLED = wb("SND_CH_PORTA_ENABLED")
CH_PORTA_HELD = wb("SND_CH_PORTA_HELD")
CH_PORTA_AT_LIMIT = wb("SND_CH_PORTA_AT_LIMIT")
CH_YIELD_TAKEN = wb("SND_CH_YIELD_TAKEN")
CH_YIELD_MASK = wb("SND_CH_YIELD_MASK")
ARPEGGIO_END = wb("SND_ARPEGGIO_END")
NOTE_PERIOD_TABLE = wb("SND_NOTE_PERIOD_TABLE")
NOTE_PERIOD_ENTRIES = wb("SND_NOTE_PERIOD_ENTRIES")
GLOBAL_TRANSPOSE = wb("SND_GLOBAL_TRANSPOSE")
NOISE_PERIOD_BASE = wb("SND_NOISE_PERIOD_BASE")
NOISE_PERIOD_OUT = wb("SND_NOISE_PERIOD_OUT")
NOISE_ROUTE_MASK = wb("SND_NOISE_ROUTE_MASK")
NOISE_PERIOD_XOR = wb("SND_NOISE_PERIOD_XOR")
NOISE_TONE_BITS = wb("SND_NOISE_TONE_BITS")
NOISE_ROUTE_YIELDED = wb("SND_NOISE_ROUTE_YIELDED")
MIXER_NOISE_BITS = wb("SND_MIXER_NOISE_BITS")
PORTA_OCTAVE_BIAS = wb("SND_PORTA_OCTAVE_BIAS")
PORTA_OCTAVE_STEP = wb("SND_PORTA_OCTAVE_STEP")

# ...and the PATTERN STEPPER's ($18106 plus its 24 handlers) and the TICK BODY's ($17ca0): the rest
# of the music channel record, the opcode table and its range decoder, and the module globals no
# routine below the tick names.
CH_NOISE_TRACKS_NOTE = wb("SND_CH_NOISE_TRACKS_NOTE")
CH_TRACKS_NOTE_SET = wb("SND_CH_TRACKS_NOTE_SET")
CH_PATTERN_CURSOR = wb("SND_CH_PATTERN_CURSOR")
CH_SEQUENCE_OFFSET = wb("SND_CH_SEQUENCE_OFFSET")
CH_SEQUENCE_INDEX = wb("SND_CH_SEQUENCE_INDEX")
CH_DURATION = wb("SND_CH_DURATION")
CH_DURATION_RELOAD = wb("SND_CH_DURATION_RELOAD")
CH_ENVELOPE_BASE = wb("SND_CH_ENVELOPE_BASE")
CH_FLAG_MARK = wb("SND_CH_FLAG_MARK")
CH_FLAG_SLIDE = wb("SND_CH_FLAG_SLIDE")
CH_FLAG_SLIDE_UP = wb("SND_CH_FLAG_SLIDE_UP")
CH_YIELD_ASKED = wb("SND_CH_YIELD_ASKED")

PATTERN_JUMP_TABLE = wb("SND_PATTERN_JUMP_TABLE")
PATTERN_OPCODES = wb("SND_PATTERN_OPCODES")
PATTERN_NOTE_LIMIT = wb("SND_PATTERN_NOTE_LIMIT")
PATTERN_CMD_LIMIT = wb("SND_PATTERN_CMD_LIMIT")
PATTERN_CMD_INDEX_MASK = wb("SND_PATTERN_CMD_INDEX_MASK")
PATTERN_DURATION_BIAS = wb("SND_PATTERN_DURATION_BIAS")
PATTERN_INSTRUMENT_BIAS = wb("SND_PATTERN_INSTRUMENT_BIAS")
PATTERN_ARPEGGIO_BIAS = wb("SND_PATTERN_ARPEGGIO_BIAS")
PATTERN_DURATION_MIN = wb("SND_PATTERN_DURATION_MIN")
ARPEGGIO_PTR_TABLE = wb("SND_ARPEGGIO_PTR_TABLE")
INSTRUMENT_PTR_TABLE = wb("SND_INSTRUMENT_PTR_TABLE")

MASTER_VOLUME = wb("SND_MASTER_VOLUME")
SONG_SPEED = wb("SND_SONG_SPEED")
SONG_SPEED_COPY = wb("SND_SONG_SPEED_COPY")
CHANNEL_LOCKS = wb("SND_CHANNEL_LOCKS")
CHANNEL_LOCKS_LEN = wb("SND_CHANNEL_LOCKS_LEN")
SONG_LOADED = wb("SND_SONG_LOADED")
SONG_UNLOADED = wb("SND_SONG_UNLOADED")
FADE_RATE = wb("SND_FADE_RATE")
FADE_COUNTDOWN = wb("SND_FADE_COUNTDOWN")
PERIOD_SCRATCH = wb("SND_PERIOD_SCRATCH")
SPEED_ACC = wb("SND_SPEED_ACC")
TICK_DROP_VALUE = wb("SND_TICK_DROP_VALUE")
TICK_DROP_ACC = wb("SND_TICK_DROP_ACC")
TICK_DROP_50HZ = wb("SND_TICK_DROP_50HZ")
TICK_DROP_60HZ = wb("SND_TICK_DROP_60HZ")
TICK_DROP_MONO = wb("SND_TICK_DROP_MONO")
GPIP_COLOUR_MONITOR = wb("MFP_GPIP_COLOUR_MONITOR")   # $fffa01 bit 7, the tempo head's first test
SYNC_50HZ = wb("SHIFTER_SYNC_50HZ")                   # $ff820a bit 1, its second
MASTER_VOLUME_MASK = wb("SND_MASTER_VOLUME_MASK")
MASTER_VOLUME_FULL = wb("SND_MASTER_VOLUME_FULL")
MIXER_CHANNEL_A_BITS = wb("SND_MIXER_CHANNEL_A_BITS")
PSG_REG_TONE_A = wb("PSG_REG_TONE_A")
PSG_REG_TONE_LEN = wb("PSG_REG_TONE_LEN")
PSG_REG_NOISE_PERIOD = wb("PSG_REG_NOISE_PERIOD")

LONGWORD_MASK = leaf.LONGWORD_MASK
LONGWORD_LEN = leaf.LONGWORD_BYTES
WORD_LEN = leaf.WORD_BYTES
BYTE_LIMIT = 0x100      # what a byte operation's carry out means, and what its wrap is modulo

# The 334 bytes ../names.txt gives $1a48a, stated so the entry pin cannot pass on a body of any
# other length, and so that the three arms' own lengths have to add up to it.
TRIGGER_BODY_BYTES = 334

# The caps, from the bodies rather than guessed. One arm is 8 instructions of setup, DESCRIPTOR_LEN
# iterations of `move.b`+`dbf` and 20 more (the noise store included); the dispatch above it is at
# most 5, and the stub adds its `movem` pair, its `bsr` and its `rts`.
TRIGGER_INSN_CAP = 5 + 8 + 2 * DESCRIPTOR_LEN + 20
STUB_INSN_CAP = TRIGGER_INSN_CAP + 4


# --- the arithmetic the trigger's two table reads spell ------------------------------------------
# `leaf.s8` is the `ext.w Dn` that sends an id of $80 or more backwards off the table it indexes;
# machine.h's `sign_ext8` is the reconstruction's own spelling of the same thing.

def _module_address(offset):
    """`adda.l a3,An` over a SIGNED word — the module naming a place inside itself. The window is the
    base plus or minus 32 KiB, all of which is inside the loaded image, which is why the reads that
    go through one need no bus guard where the reads through a stored CURSOR do."""
    return (MODULE_BASE + leaf.s16(offset)) & LONGWORD_MASK


def _module_pointer(image, table, byte_index):
    """One entry of an a3-relative WORD table, resolved as `movea.w 0(An,Dn.w),An / adda.l a3,An`
    does: a signed byte doubled into the index, and the ENTRY itself sign-extended before the module
    base is added to it."""
    entry = (table + TABLE_ENTRY_LEN * leaf.s8(byte_index)) & LONGWORD_MASK
    return _module_address(leaf.u16(image, entry))


def _descriptor_of(image, effect_id):
    return _module_pointer(image, PTR_TABLE, effect_id)


def _channel_state(channel):
    return STATE + channel * STATE_LEN


def _music_channel(index):
    """One music channel record's ADDRESS — the a0 the tick hands $18106 and $18208 alike."""
    return MUSIC_CHANNEL_STATE + index * MUSIC_CHANNEL_LEN


def _mix_period(channel):
    """...and the other block with a stride of its own, which five call sites spelt inline."""
    return MIX_PERIOD + channel * MIX_PERIOD_LEN


# --- what one arm must write, and where ----------------------------------------------------------

def _copied_record(image, source, state):
    """The fourteen bytes `move.b (a0)+,(a1)+ / dbf` leaves at ``state``, ONE BYTE AT A TIME.

    A source that overlaps its destination FROM BELOW propagates: the loop reaches offsets whose
    source address it has already written, and re-reads what it put there — so the record is not the
    slice a block move would leave. The module's own pointer table puts a descriptor exactly there
    (PROPAGATING_IDS below), which is what makes the copy's DIRECTION observable. For every other id
    no source address is ever a destination address and this is the pre-run slice.
    """
    copied = {}
    for offset in range(DESCRIPTOR_LEN):
        at = source + offset
        copied[state + offset] = copied.get(at, image[at])
    return bytes(copied[state + offset] for offset in range(DESCRIPTOR_LEN))


def expected_writes(image, effect_id, channel):
    """``{address: bytes}`` for every byte the trigger must leave, stated from the DESCRIPTOR the
    tables select — the field roles ../notes/sound_module_recon.md read off the tick — rather than
    from src/sound.c's own copy, so the two are different statements of the same thing.

    Its KEYS are the write set as well: the noise byte appears only on the arm that writes it, so a
    port that wrote it unconditionally fails as a stray write and not only as a diff.

    IT READS THE PRE-RUN IMAGE everywhere except the copy. That is sound for the mix block because
    the 14-byte copy is the second thing the arm does, before any store into it — the cases that put
    a descriptor there rely on exactly that, and say so. The copy is the one place the arm can read
    what it has already written, and `_copied_record` models it. The only OTHER read past a store is
    `move.b (a2),volume`, and the assert below is what keeps every case clear of it.
    """
    state = _channel_state(channel)
    source = _descriptor_of(image, effect_id)
    record = _copied_record(image, source, state)
    stream = _module_pointer(image, VOLUME_PTRS, record[DESC_VOLUME_INDEX])

    written = {
        ACTIVE_FLAGS + channel: bytes([ACTIVE]),
        state: record,
        state + STATE_PERIOD_COUNT: record[DESC_PERIOD_STEP:DESC_PERIOD_STEP + 1],
        state + STATE_VOLUME_COUNT: record[DESC_VOLUME_STEP:DESC_VOLUME_STEP + 1],
        state + STATE_SECOND_COUNT: record[DESC_SECOND_RELOAD:DESC_SECOND_RELOAD + 1],
        state + STATE_STREAM_BASE: stream.to_bytes(LONGWORD_LEN, "big"),
        state + STATE_STREAM_CURSOR: stream.to_bytes(LONGWORD_LEN, "big"),
        _mix_period(channel):
            record[DESC_TONE_PERIOD:DESC_TONE_PERIOD + MIX_PERIOD_LEN],
        MIX_VOLUME + channel: bytes(image[stream:stream + 1]),
    }
    # `btst #3,state+6 / bne` — set means this channel's noise is off, and then the descriptor's
    # third byte is NOT copied into the noise period all three arms share.
    if not record[DESC_MIXER_BITS] & MIXER_NOISE_OFF:
        written[MIX_NOISE] = record[DESC_NOISE_PERIOD:DESC_NOISE_PERIOD + 1]
    assert not any(addr <= stream < addr + len(value) for addr, value in written.items()), (
        f"the volume stream at {stream:#x} is inside a band this arm writes, so the byte read out "
        f"of it is not the pre-run one this model states")
    return written


def write_bands(written):
    return leaf.merge_bands({addr + index for addr, value in written.items()
                             for index in range(len(value))})


def assert_written(info, written, what):
    for addr, expected in sorted(written.items()):
        actual = leaf.read_bytes(info, addr, len(expected), what)
        assert actual == expected, (
            f"{what}: {addr:#x} is {actual.hex()}, not the {expected.hex()} the descriptor gives")


# --- the encodings the two entries are pinned against --------------------------------------------
# Each base opcode below carries every field EXCEPT the register numbers, which the builders OR in
# from the constants above — so an arm wired to another channel's offset, or reading through the
# wrong address register, fails on the bytes at its own address.
#
# THE LEDGER, which is leaf.py's rule for where an encoding lives. `add.w Dn,Dn`, `moveq` and
# `move.b #imm,d16(An)` are leaf's and are imported above — the last of them because this battery
# was its THIRD user (test_actor.py and test_map.py had spelt the other two). Five of the constants
# below stand at TWO users and say so beside themselves; the rest stand at one. `BNE_S` is the
# apparent exception that is not one: its two bytes are also `bne.w`'s opcode word, which five
# batteries spell, but a `bcc.s` carries its displacement IN the low byte and a `bcc.w` in a word
# after it, so they are different instructions that agree on two bytes.
SF_D16_AN = 0x51e8              # sf d16(An) — Scc with the always-false condition
EXT_W_DN = 0x4880               # ext.w Dn.  ALSO IN test_blit.py (`ext_w_dn`)
LEA_D16_PC_AN = 0x41fa          # lea d16(pc),An.  ALSO IN test_hud.py (`LEA_D16_PC_A0`)
MOVEA_W_D8_AN_DN_AM = 0x3070    # movea.w d8(An,Dn.w),Am, with the base register in the low three
ADDA_L_AN_AM = 0xd1c8
MOVE_B_POSTINC_POSTINC = 0x10d8
MOVE_B_D16_PC_D16_AN = 0x117a
MOVE_W_D16_PC_D16_AN = 0x317a
MOVE_B_D16_PC_DN = 0x103a
MOVE_L_AN_D16_AM = 0x2148
MOVE_B_IND_AN_D16_AM = 0x1150
BTST_IMM_D16_AN = 0x0828
BTST_IMM_ABS_L = 0x0839         # btst #imm,<abs>.l — the tempo head's two machine tests
CMP_B_IMM_DN = 0xb03c           # cmp.b #imm,Dn.  ALSO IN test_text.py (`cmp_b_imm_dn`)
BNE_S = 0x6600
MOVEM_L_TO_PREDEC_A7 = 0x48e7   # ALSO IN test_hud.py, inside `MOVEM_L_SAVE_A0_A1`'s literal
MOVEM_L_FROM_POSTINC_A7 = 0x4cdf  # ...and `MOVEM_L_RESTORE_A0_A1`'s
MOVE_L_AN_PREDEC_A7 = 0x2f08
MOVEA_L_POSTINC_A7_AN = 0x205f  # ALSO IN test_copylock.py's `MOVEA_L_POSTINC_A7_A0_RTS`

# The registers the arms use, named once so a builder cannot pin one and the reconstruction read
# another: a3 is the module base, a0 the descriptor cursor, a1 the state cursor, a2 the stream.
D0, D1 = 0, 1
A0, A1, A2, A3, A7 = 0, 1, 2, 3, 7

# `move.b d16(pc),d16(a3)`: an opcode word and two displacement words. The `bne.s` over the noise
# store needs this before the store can be built at its own address, and a test below requires the
# assembled store to be exactly this long.
NOISE_STORE_BYTES = 6


def _pc_relative(at, target):
    """A `d16(pc)` displacement, which counts from the extension word exactly as a `bcc.w`'s does —
    hence leaf.py's own constant. A `bcc.s` does NOT: its displacement is the bytes it spans and
    nothing more, which is why `BNE_S` below is built from a stated length instead."""
    return word(target - (at + BRANCH_EXTENSION))


def _module_displacement(address):
    """An a3-relative displacement, which is how the module names every one of its own fields."""
    offset = address - MODULE_BASE
    assert -0x8000 <= offset < 0x8000, f"{address:#x} is not within a d16 of the module base"
    return offset


def _module_offset(address):
    """...as the displacement WORD an operand carries."""
    return word(_module_displacement(address))


def _lea_pc(register, target):
    return lambda at: opcode(LEA_D16_PC_AN | (register << 9)) + _pc_relative(at, target)


def _move_b_pc(source, destination):
    """`move.b d16(pc),d16(a3)` — how all five of the arm's field copies are spelt."""
    return lambda at: (opcode(MOVE_B_D16_PC_D16_AN | (A3 << 9)) + _pc_relative(at, source)
                       + _module_offset(destination))


def _index_by_signed_byte():
    """`ext.w d0 / add.w d0,d0` — the id, and later the volume index, turned into a word offset."""
    return opcode(EXT_W_DN | D0) + add_w_dn_dn(D0, D0)


def _table_lookup(register, table):
    """`lea table(pc),An / movea.w 0(An,d0.w),An / adda.l a3,An` — one a3-relative word table read.
    The arm does this twice, for the descriptor and for the volume stream."""
    return [_lea_pc(register, table),
            opcode(MOVEA_W_D8_AN_DN_AM | (register << 9) | register) + word(D0 << 12),
            opcode(ADDA_L_AN_AM | (register << 9) | A3)]


def _arm(base, channel):
    """One channel's arm, built from the same base-plus-stride the reconstruction uses — which is
    what makes this a pin on the STRIDE and not only on the code."""
    state = _channel_state(channel)
    active = ACTIVE_FLAGS + channel
    copy = opcode(MOVE_B_POSTINC_POSTINC | (A1 << 9) | A0)

    return leaf.assemble(base, [
        opcode(SF_D16_AN | A3) + _module_offset(active),
        _index_by_signed_byte(),
    ] + _table_lookup(A0, PTR_TABLE) + [
        moveq(DESCRIPTOR_LEN - 1, D0),
        _lea_pc(A1, state),
        copy, leaf.dbf(D0, copy),
        _move_b_pc(state + DESC_PERIOD_STEP, state + STATE_PERIOD_COUNT),
        lambda at: (opcode(MOVE_W_D16_PC_D16_AN | (A3 << 9))
                    + _pc_relative(at, state + DESC_TONE_PERIOD)
                    + _module_offset(_mix_period(channel))),
        (opcode(BTST_IMM_D16_AN | A3) + word(MIXER_NOISE_OFF.bit_length() - 1)
         + _module_offset(state + DESC_MIXER_BITS)),
        opcode(BNE_S | NOISE_STORE_BYTES),
        _move_b_pc(state + DESC_NOISE_PERIOD, MIX_NOISE),
        _move_b_pc(state + DESC_VOLUME_STEP, state + STATE_VOLUME_COUNT),
        _move_b_pc(state + DESC_SECOND_RELOAD, state + STATE_SECOND_COUNT),
        lambda at: (opcode(MOVE_B_D16_PC_DN | (D0 << 9))
                    + _pc_relative(at, state + DESC_VOLUME_INDEX)),
        _index_by_signed_byte(),
    ] + _table_lookup(A2, VOLUME_PTRS) + [
        opcode(MOVE_L_AN_D16_AM | (A3 << 9) | A2) + _module_offset(state + STATE_STREAM_BASE),
        opcode(MOVE_L_AN_D16_AM | (A3 << 9) | A2) + _module_offset(state + STATE_STREAM_CURSOR),
        opcode(MOVE_B_IND_AN_D16_AM | (A3 << 9) | A2) + _module_offset(MIX_VOLUME + channel),
        leaf.move_b_imm_d16(A3, ACTIVE, _module_displacement(active)),
        RTS,
    ])


def _trigger_entry():
    """$1a48a: the module base into a3, then two `cmp.b #n,d1` that each branch OVER one arm. The
    last arm has no test of its own — anything that is not 0 or 1 is channel C."""
    base = leaf.entry_of("snd_trigger_effect")
    body = _lea_pc(A3, MODULE_BASE)(base)
    for channel in range(CHANNELS - 1):
        dispatch = opcode(CMP_B_IMM_DN | (D1 << 9)) + word(channel)
        branch = len(dispatch) + len(opcode(BNE_S))
        arm = _arm(base + len(body) + branch, channel)
        body += dispatch + opcode(BNE_S | len(arm)) + arm
    return body + _arm(base + len(body), CHANNELS - 1)


# The stub table at $17adc: seven entries at a 14-byte pitch, each a register save, a `bsr` into the
# module and the matching restore. NOT seven of a kind — the register sets differ and the last is a
# plain `move.l` of a3 rather than a `movem`, and is 10 bytes — which is why the shape is pinned.
# Its BASE is exported because it is the module's whole interface: test_hud.py's $bbca pin builds a
# `jsr d16(a1)` into it and takes the address from here rather than looking the name up again.
STUB_TABLE_BASE = leaf.entry_of("snd_stub_00")
SAVE_ALL = 0xfffe        # `movem.l d0-a6,-(a7)`: every bit but a7's, in PRE-DECREMENT bit order
RESTORE_ALL = 0x7fff     # ...and the same fifteen registers in POST-INCREMENT order
STUB_TABLE = (
    (0, "snd_play_song", SAVE_ALL, RESTORE_ALL),
    (14, "snd_music_tick", SAVE_ALL, RESTORE_ALL),
    (28, "snd_stop", SAVE_ALL, RESTORE_ALL),
    (42, "snd_resume", 0x0010, 0x0800),               # a3 alone
    (56, "snd_trigger_effect", SAVE_ALL, RESTORE_ALL),
    (70, "snd_stop_all_sfx", 0x6000, 0x0006),         # d1 and d2
    (84, "snd_start_fadeout", None, None),            # `move.l a3,-(a7)` / `movea.l (a7)+,a3`
)
STUB_TRIGGER_OFFSET = 56
_TRIGGER_STUB = next(stub for stub in STUB_TABLE if stub[0] == STUB_TRIGGER_OFFSET)


def _stub(offset, called, save, restore):
    """One stub, built where the table puts it, so its `bsr` displacement comes out of the two
    addresses ../names.txt gives rather than being transcribed."""
    at = STUB_TABLE_BASE + offset
    if save is None:
        return (opcode(MOVE_L_AN_PREDEC_A7 | A3) + bsr_w(at + 2, leaf.entry_of(called))
                + opcode(MOVEA_L_POSTINC_A7_AN | (A3 << 9)) + RTS)
    return (opcode(MOVEM_L_TO_PREDEC_A7) + word(save) + bsr_w(at + 4, leaf.entry_of(called))
            + opcode(MOVEM_L_FROM_POSTINC_A7) + word(restore) + RTS)


# --- the stop chain's own encodings --------------------------------------------------------------
# `clr.w`/`clr.b d16(An)` are leaf's (three batteries spell the byte form); the LONG form has one
# user and stays here, beside the instruction it belongs to. The three SR moves have one user each
# and are this file's alone — nothing else in the reconstruction touches the status register.
CLR_L_D16_AN = 0x42a8           # clr.l d16(An)
MOVE_SR_DN = 0x40c0             # move sr,Dn — NOT privileged on a 68000 (it is from the 68010 on)
MOVE_DN_SR = 0x46c0             # move Dn,sr
MOVE_IMM_SR = 0x46fc            # move #imm,sr
ORI_B_IMM_DN = 0x0000           # ori.b #imm,Dn — the immediate travels in a WORD
MOVE_B_DN_ABS_L = 0x13c0        # move.b Dn,<abs>.l — the SOURCE register is the low three bits (a
                                # `move`'s source EA), where the destination's sit at bits 6-11
BRA_W = 0x6000

D2 = 2                          # d1 takes the mixer read-back; d2 holds the saved SR
# The two ports are leaf.py's: test_audio_capture.py spells the select one too, so leaf's rule (an
# encoding or address more than one battery names lives there) applies.
PSG_SELECT = leaf.PSG_SELECT    # the port a register number is latched into, and read back from
PSG_DATA = leaf.PSG_DATA        # ...and the write-only data port

SUPERVISOR_SR = 0x2700          # `move.w #$2700,sr`: supervisor, IPL 7, condition codes clear —
                                # numerically the SR the oracle enters every run at, which is why
                                # the mask is a no-op there (TRAP_MODEL.md, "The entry state")
BYTE_MASK = 0xff


def _clr_l_d16(base, displacement):
    return opcode(CLR_L_D16_AN | base) + word(displacement)


def _psg_select(register):
    """`move.b #<reg>,$ff8800.l` — the latch write every access begins with."""
    return move_b_imm_abs_l(register, PSG_SELECT)


def _psg_write_imm(register, value):
    """...and select-then-data for a constant, which is how the three volumes are zeroed."""
    return _psg_select(register) + move_b_imm_abs_l(value, PSG_DATA)


def _silence_entry():
    """$17f30: save the SR and mask interrupts, read-modify-write the mixer, zero the three volume
    registers, restore the SR. The `ori` is the whole claim — a mask of anything but
    WB_PSG_MIXER_ALL_OFF, or a `move.b` where the `ori` is, fails on these bytes."""
    return (opcode(MOVE_SR_DN | D2) + opcode(MOVE_IMM_SR) + word(SUPERVISOR_SR)
            + _psg_select(PSG_REG_MIXER)
            + move_b_abs_l_dn(D1, PSG_SELECT)
            + opcode(ORI_B_IMM_DN | D1) + word(PSG_MIXER_ALL_OFF)
            + opcode(MOVE_B_DN_ABS_L | D1) + longword(PSG_DATA)
            + b"".join(_psg_write_imm(reg, PSG_VOLUME_SILENT) for reg in SILENCED_VOLUMES)
            + opcode(MOVE_DN_SR | D2) + RTS)


def _stop_all_entry():
    """$1aaea: the four shadow stores mirror the four chip accesses above — same registers, same
    values, `clr.w` covering two adjacent volume shadows — which is the claim that the shadow is
    indexed by REGISTER NUMBER. Ends in a `bra.w`, not a `bsr`."""
    base = leaf.entry_of("snd_stop_all_sfx")
    return leaf.assemble(base, [
        _lea_pc(A3, MODULE_BASE),
        _clr_l_d16(A3, _module_displacement(ACTIVE_FLAGS)),
        clr_w_d16(A3, _module_displacement(PSG_SHADOW + PSG_REG_VOLUME_A)),
        clr_b_d16(A3, _module_displacement(PSG_SHADOW + PSG_REG_VOLUME_C)),
        move_b_imm_d16(A3, PSG_MIXER_ALL_OFF, _module_displacement(PSG_SHADOW + PSG_REG_MIXER)),
        lambda at: branch_w_to(BRA_W, at, leaf.entry_of("snd_psg_silence")),
    ])


def _stop_entry():
    """$17f24: `sf` the engine flag and `bra.w` on. Twelve bytes."""
    base = leaf.entry_of("snd_stop")
    return leaf.assemble(base, [
        _lea_pc(A3, MODULE_BASE),
        opcode(SF_D16_AN | A3) + _module_offset(ENGINE_ENABLED),
        lambda at: branch_w_to(BRA_W, at, leaf.entry_of("snd_stop_all_sfx")),
    ])


# --- the tick tier's own encodings ----------------------------------------------------------------
# The three routines below are pinned WHOLE — 28, 600 and 330 bytes — because that is the only form
# in which the SFX tick's base-plus-stride claim is a claim about the bytes: three arms built from
# one function of `channel` either assemble to the image's own 558 bytes or they do not.
#
# Every encoding here has ONE user (this file). The shared ones — `moveq`, `add_w_dn_dn`,
# `btst_imm_dn`, `clr_w_dn`, `clr_b_d16`, `subi_w_dn`, `addi_w_dn`, `move_b_d16_dn`,
# `move_w_ind_dn`, `move_b_imm_d16`, `bsr_w` — come from leaf.py above.
ANDI_B_IMM_DN = 0x0200          # andi.b #imm,Dn — the immediate travels in a WORD
ADDI_B_IMM_DN = 0x0600
EORI_B_IMM_DN = 0x0a00
ANDI_B_IMM_D16_AN = 0x0228
LSHIFT_IMM_DN = 0xe000          # ALSO IN test_hud.py (`SHIFT_OPCODE`), the second speller.
                                # The base of every immediate shift: count at 11-9, direction at 8,
LSHIFT_LEFT = 0x100             # size at 7-6, and the TYPE (00 AS, 01 LS, 10 ROX, 11 RO) at 4-3
LSHIFT_LOGICAL = 0x08
ROXL_W_D16_AN = 0xe5e8          # roxl.w d16(An) — a memory shift, so the count is one and the
                                # register field carries the TYPE instead
SUBQ_B_D16_AN = 0x5128          # subq.b #n,d16(An) — the count in bits 11-9, 0 meaning 8. ALSO IN
                                # test_actor.py (`subq_b_d16`), the second speller
SUBQ_B_DN = 0x5100
ADDQ_L_D16_AN = 0x50a8
MOVE_B_D16_AN_D16_AM = 0x1168
MOVE_B_DN_D16_AN = 0x1140
MOVE_B_DN_DN = 0x1000
MOVE_B_IMM_DN = 0x103c
MOVEA_L_D16_PC_AN = 0x207a
MOVEA_L_D16_AN_AM = 0x2068
MOVE_W_D16_PC_DN = 0x303a
MOVE_W_DN_D16_AN = 0x3140
ADD_B_EA_DN = 0xd000            # add.b <ea>,Dn — the destination register at bits 11-9, the SOURCE
ADD_W_EA_DN = 0xd040            # effective address in the low six
ADD_W_DN_D16_AN = 0xd168
SUB_B_EA_DN = 0x9000
SUB_W_DN_D16_AN = 0x9168
ADDX_B_DN_DN = 0xd100
ADDA_W_DN_AN = 0xd0c0
AND_B_EA_DN = 0xc000
EOR_B_DN_EA = 0xb100
CMP_B_DN_DN = 0xb000
NOT_B_DN = 0x4600
BCLR_IMM_DN = 0x0880
BCLR_IMM_D16_AN = 0x08a8
BSET_IMM_D16_AN = 0x08e8
LEA_D16_PC_A1 = 0x43fa

# The two effective addresses the instructions above name as a source: `d16(A0)` — the music channel
# record — and `d16(pc)`, which is how this module reaches every one of its own globals.
EA_D16_A0 = 0x28
EA_D16_PC = 0x3a

BEQ_S, BMI_S, BPL_S, BCC_S, BCS_S, BRA_S, BSR_S = (
    0x6700, 0x6b00, 0x6a00, 0x6400, 0x6500, 0x6000, 0x6100)

D3, D4, D5, D6, D7 = 3, 4, 5, 6, 7

# The shift counts the module spells, DECODED rather than transcribed: the immediate field holds
# three bits with 0 meaning 8, so a count of 1 or 2 is itself.
SHIFT_BY_ONE = 1
PRNG_FEEDBACK_SHIFT = 2         # `lsl.b #2,d0`, whose last bit out is PRNG_FEEDBACK_BIT


def _bytes_of(pieces):
    """The LENGTH of a run of pin pieces.

    A piece's BYTES can depend on where it sits — a `d16(pc)` operand does — but its length cannot,
    so a run is measured by assembling it at a placeholder address. That is what lets every branch
    below take its displacement from the run it jumps over instead of from a transcribed number: the
    run is named once, measured here and splatted into the body, so the two cannot disagree.
    """
    return len(leaf.assemble(0, pieces))


# The two instruction WIDTHS a span is stated by rather than measured from — for the three calls in
# snd_sfx_tick's dispatch, whose targets are absolute addresses and so cannot be assembled at the
# placeholder address `_bytes_of` measures at. Each is a property of the instruction and not a
# stand-in for a particular one: a `bsr.w` is four bytes whatever it calls.
SHORT_BRANCH_BYTES = 2          # `bcc.s`/`bsr.s`: one opcode word, the displacement in its low byte
BSR_W_BYTES = 4                 # `bsr.w`: an opcode word and a displacement word


def _branch_s(condition, spanned):
    """A SHORT branch forward over the run ``spanned`` — a list of pin pieces, or the byte count of
    one of the two widths above.

    Its displacement is the bytes it spans and NOTHING more — a `bcc.s` counts from the byte after
    its own opcode word, where a `bcc.w` counts from its extension word (leaf.BRANCH_EXTENSION).
    The two are different rules and this file spells both.
    """
    distance = spanned if isinstance(spanned, int) else _bytes_of(spanned)
    assert 0 < distance < 0x80, f"{distance} is not a forward short displacement"
    return opcode(condition | distance)


def _branch_s_to(condition, at, target):
    """...and the same aimed at an ABSOLUTE address, for the tick's two BACKWARD branches, its call
    into channel A's arm and the portamento's octave loop."""
    displacement = target - (at + WORD_LEN)
    # A displacement byte of 0 selects the `.w` form and one of $ff the `.l` form, so neither is a
    # short branch: emitting one would assemble a two-word instruction that swallows the next.
    assert -0x80 <= displacement < 0x80 and displacement not in (0, -1), (
        f"{displacement} is not a short displacement")
    return opcode(condition | (displacement & BYTE_MASK))


def _shift_imm(count, reg, left):
    """`lsl.b`/`lsr.b Dn` — one base opcode with the direction and the LOGICAL type ORed in, so the
    two the module uses cannot be got the wrong way round. The WORD form is leaf's
    (`lsl_w_imm_dn`), which three batteries already spell."""
    return opcode(LSHIFT_IMM_DN | ((count & 7) << 9) | (LSHIFT_LEFT if left else 0)
                  | LSHIFT_LOGICAL | reg)


def _immediate_b(base_opcode, reg, value):
    """`andi.b`/`addi.b`/`eori.b #imm,Dn` — the byte immediate occupies a whole word."""
    return opcode(base_opcode | reg) + word(value & BYTE_MASK)


def _btst_imm_abs_l(bit, address):
    """`btst #n,<abs>.l` — the tempo head's two machine tests, and this battery's alone.

    Eight bytes: the opcode word with the absolute-long effective address already in it, the BIT
    NUMBER in an extension word of its own, and the 24-bit bus address as a longword. `btst_imm_dn`
    next door is the register form and shares neither field layout nor length.
    """
    return opcode(BTST_IMM_ABS_L) + word(bit) + longword(address)


def _tst_b(address):
    return tst_b_d16(A3, _module_displacement(address))


def _subq_b_module(address):
    return opcode(SUBQ_B_D16_AN | (1 << 9) | A3) + _module_offset(address)


def _subq_b_record(offset):
    return opcode(SUBQ_B_D16_AN | (1 << 9) | A0) + word(offset)


def _move_b_record(source, destination):
    """`move.b d16(a0),d16(a0)` — one field of the music channel record copied onto another.

    The SOURCE displacement comes first in the instruction stream even though the destination
    register sits higher in the opcode word, which is the 68000's rule for a MOVE whose two
    effective addresses both carry an extension."""
    return opcode(MOVE_B_D16_AN_D16_AM | (A0 << 9) | A0) + word(source) + word(destination)


def _move_b_dn_record(reg, offset):
    return opcode(MOVE_B_DN_D16_AN | (A0 << 9) | reg) + word(offset)


def _move_b_dn_module(reg, address):
    return opcode(MOVE_B_DN_D16_AN | (A3 << 9) | reg) + _module_offset(address)


def _move_b_pc_dn(reg, target):
    return lambda at: opcode(MOVE_B_D16_PC_DN | (reg << 9)) + _pc_relative(at, target)


def _move_w_pc_dn(reg, target):
    return lambda at: opcode(MOVE_W_D16_PC_DN | (reg << 9)) + _pc_relative(at, target)


def _movea_l_pc(reg, target):
    return lambda at: opcode(MOVEA_L_D16_PC_AN | (reg << 9)) + _pc_relative(at, target)


def _prng_entry():
    """$1aaca. The tap mask, the bias, the shift count and — the point — the ORDER of the two
    `roxl.w`s: the LOW word turns first, so its top bit is the X the high word's takes."""
    return leaf.assemble(leaf.entry_of("snd_prng_step"), [
        _move_b_pc_dn(D0, PRNG_STATE),
        _immediate_b(ANDI_B_IMM_DN, D0, PRNG_TAP_MASK),
        _immediate_b(ADDI_B_IMM_DN, D0, PRNG_TAP_BIAS),
        _shift_imm(PRNG_FEEDBACK_SHIFT, D0, left=True),
        opcode(ROXL_W_D16_AN | A3) + _module_offset(PRNG_STATE + PRNG_LOW_WORD),
        opcode(ROXL_W_D16_AN | A3) + _module_offset(PRNG_STATE),
        _move_b_pc_dn(D0, PRNG_STATE),
        RTS,
    ])


def _sfx_arm(base, channel):
    """One SFX-tick arm, built from the SIX base-plus-stride blocks the three share — the 26-byte
    state, the active flag, the mix period word, the mix volume byte, the PSG VOLUME SHADOW the
    end-of-effect arm clears, and the PRNG byte, which steps by one so the three channels read three
    different bytes of the one 32-bit state.

    Assembled from `channel` alone, so an arm wired to a neighbour's offset — or a stride written as
    anything but the constants in ../include/wonderboy.h — fails on the bytes at its own address.
    """
    state = _channel_state(channel)
    mix_period = _mix_period(channel)

    # $1a60e — the effect is over: disarm the channel and silence the module's own PSG volume
    # shadow. NOT the SFX mix volume: the store is a3+4046, WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A.
    end_of_effect = [
        opcode(SF_D16_AN | A3) + _module_offset(ACTIVE_FLAGS + channel),
        clr_b_d16(A3, _module_displacement(PSG_SHADOW + PSG_REG_VOLUME_A + channel)),
        RTS,
    ]

    # $1a62e — rewrite the mix period from the descriptor's own tone period plus a delta byte, which
    # is the channel's PRNG byte when descriptor +7 asks for it. `add.b` then `addx.b` puts the SAME
    # delta into both halves of the word.
    prng_delta = [_move_b_pc_dn(D0, PRNG_STATE + channel)]
    pitch = [
        _subq_b_module(state + DESC_SLIDE_COUNT),
        _move_b_pc(state + DESC_PERIOD_STEP, state + STATE_PERIOD_COUNT),
        _move_b_pc_dn(D0, state + DESC_USE_PRNG),
        _branch_s(BEQ_S, prng_delta),
        *prng_delta,
        _move_b_pc_dn(D1, state + DESC_TONE_PERIOD + MIX_PERIOD_LOW),
        opcode(ADD_B_EA_DN | (D1 << 9) | D0),
        _move_b_dn_module(D1, mix_period + MIX_PERIOD_LOW),
        _move_b_pc_dn(D1, state + DESC_TONE_PERIOD),
        opcode(ADDX_B_DN_DN | (D1 << 9) | D0),
        _move_b_dn_module(D1, mix_period),
    ]

    # $1a66a — the constant pitch slide. `tst.b / beq / bpl`: zero does nothing, POSITIVE subtracts
    # and negative adds, so a descriptor byte of $ff slides the period UP.
    slide_up = [
        _move_w_pc_dn(D0, state + DESC_SLIDE_AMOUNT),
        opcode(ADD_W_DN_D16_AN | (D0 << 9) | A3) + _module_offset(mix_period),
    ]
    slide_down = [
        _move_w_pc_dn(D0, state + DESC_SLIDE_AMOUNT),
        opcode(SUB_W_DN_D16_AN | (D0 << 9) | A3) + _module_offset(mix_period),
    ]
    # The `beq` skips the WHOLE slide, the `bpl` that picks its direction included, so both spans are
    # stated from the same runs.
    leave_slide_up = [_branch_s(BRA_S, slide_down)]
    pick_direction = [_branch_s(BPL_S, slide_up + leave_slide_up)]
    slide = [
        _tst_b(state + DESC_SLIDE_DIRECTION),
        _branch_s(BEQ_S, pick_direction + slide_up + leave_slide_up + slide_down),
        *pick_direction,
        *slide_up,
        *leave_slide_up,
        *slide_down,
    ]

    # $1a684 — the shared noise byte takes this channel's period low byte, unless `btst #3` of the
    # descriptor's mixer byte says this channel's noise is off.
    noise_store = [_move_b_pc(mix_period + MIX_PERIOD_LOW, MIX_NOISE)]
    noise = [
        (opcode(BTST_IMM_D16_AN | A3) + word(MIXER_NOISE_OFF.bit_length() - 1)
         + _module_offset(state + DESC_MIXER_BITS)),
        _branch_s(BNE_S, noise_store),
        *noise_store,
    ]

    # $1a692 — one step of the volume stream. $80 loops back to the base and takes the byte there;
    # any other negative byte HOLDS, storing nothing at all, which is why both `bne`s below aim at
    # the arm's own `rts`.
    stream_store = [
        opcode(MOVE_L_AN_D16_AM | (A3 << 9) | A2) + _module_offset(state + STATE_STREAM_CURSOR),
        _move_b_dn_module(D0, MIX_VOLUME + channel),
    ]
    stream_reload = [
        _movea_l_pc(A2, state + STATE_STREAM_BASE),
        move_b_postinc_dn(D0, A2),
    ]
    stream_loop = [
        opcode(CMP_B_IMM_DN | (D0 << 9)) + word(VOLUME_STREAM_LOOP),
        _branch_s(BNE_S, stream_reload + stream_store),
        *stream_reload,
    ]
    stream_step = [
        _move_b_pc(state + DESC_VOLUME_STEP, state + STATE_VOLUME_COUNT),
        _movea_l_pc(A2, state + STATE_STREAM_CURSOR),
        move_b_postinc_dn(D0, A2),
        _branch_s(BPL_S, stream_loop),
        *stream_loop,
        *stream_store,
    ]
    volume = [
        _subq_b_module(state + STATE_VOLUME_COUNT),
        _branch_s(BNE_S, stream_step),
        *stream_step,
        RTS,
    ]

    # $1a656 — the period countdown, then the secondary counter that gates the slide. A reload of 0
    # disables the counter and the slide then runs every tick.
    second_reload = [_move_b_dn_module(D0, state + STATE_SECOND_COUNT)]
    second_step = [
        _subq_b_module(state + STATE_SECOND_COUNT),
        _branch_s(BNE_S, second_reload + slide),
        *second_reload,
    ]
    second = [
        _subq_b_module(state + STATE_PERIOD_COUNT),
        _move_b_pc_dn(D0, state + DESC_SECOND_RELOAD),
        _branch_s(BEQ_S, second_step),
        *second_step,
    ]

    slide_gate = [
        _tst_b(state + DESC_SLIDE_COUNT),
        _branch_s(BEQ_S, pitch + second + slide + noise),
    ]
    pitch_gate = [
        _tst_b(state + DESC_SUSTAIN),
        _branch_s(BNE_S, slide_gate),
        *slide_gate,
    ]
    sustain_gate = [
        _tst_b(state + DESC_SUSTAIN),
        _branch_s(BNE_S, end_of_effect),
    ]
    return leaf.assemble(base, [
        _tst_b(state + DESC_DURATION),
        _branch_s(BNE_S, sustain_gate + end_of_effect),
        *sustain_gate,
        *end_of_effect,
        _subq_b_module(state + DESC_DURATION),
        _tst_b(state + STATE_PERIOD_COUNT),
        _branch_s(BNE_S, pitch_gate + pitch),
        *pitch_gate,
        *pitch,
        *second,
        *slide,
        *noise,
        *volume,
    ])


SFX_ARM_NAMES = ("snd_sfx_tick_channel_a", "snd_sfx_tick_channel_b", "snd_sfx_tick_channel_c")
SFX_SHARED_RTS = 0x1a5d8        # the two bytes BEFORE snd_sfx_tick's entry, and its only `rts`


def _sfx_tick_entry():
    """$1a5da, and then the three arms it calls, laid out end to end.

    The `bsr` targets come from ../names.txt, so an arm that moved would fail here rather than in a
    case; the two backward branches are aimed at SFX_SHARED_RTS, which is what says the `rts` two
    bytes below the entry belongs to THIS routine and is no orphan.
    """
    base = leaf.entry_of("snd_sfx_tick")
    arms = [leaf.entry_of(name) for name in SFX_ARM_NAMES]
    call_arm_a = [lambda at: _branch_s_to(BSR_S, at, arms[0])]
    call_arm_b = [lambda at: bsr_w(at, arms[1])]
    call_arm_c = [lambda at: bsr_w(at, arms[2])]
    entry = leaf.assemble(base, [
        _lea_pc(A3, MODULE_BASE),
        lambda at: bsr_w(at, leaf.entry_of("snd_prng_step")),
        _tst_b(ACTIVE_FLAGS + CHANNEL_A),
        lambda at: _branch_s_to(BMI_S, at, SFX_SHARED_RTS),
        _branch_s(BEQ_S, SHORT_BRANCH_BYTES),
        *call_arm_a,
        _tst_b(ACTIVE_FLAGS + 1),
        _branch_s(BEQ_S, BSR_W_BYTES),
        *call_arm_b,
        _tst_b(ACTIVE_FLAGS + 2),
        _branch_s(BEQ_S, BSR_W_BYTES),
        *call_arm_c,
        lambda at: _branch_s_to(BRA_S, at, SFX_SHARED_RTS),
    ])
    return entry + b"".join(_sfx_arm(arms[channel], channel) for channel in range(CHANNELS))


def _period_volume_entry():
    """$18208, whole. Six arms over one music channel record, and every field offset, immediate and
    branch distance ../include/wonderboy.h states, checked at once."""
    base = leaf.entry_of("snd_channel_period_and_volume")

    # $18214 — one step of the volume envelope. The NEXT byte is peeked before the cursor moves, so a
    # negative one leaves both the cursor and the last value alone.
    advance = [
        opcode(ADDQ_L_D16_AN | (1 << 9) | A0) + word(CH_ENVELOPE_CURSOR),
        _move_b_dn_record(D0, CH_ENVELOPE_LAST),
    ]
    envelope_step = [
        _move_b_record(CH_ENVELOPE_SPEED, CH_ENVELOPE_COUNT),
        opcode(MOVEA_L_D16_AN_AM | (A2 << 9) | A0) + word(CH_ENVELOPE_CURSOR),
        move_b_d16_dn(D0, A2, 1),
        _branch_s(BMI_S, advance),
        *advance,
    ]
    envelope = [
        _subq_b_record(CH_ENVELOPE_COUNT),
        _branch_s(BCC_S, envelope_step),
        *envelope_step,
        _move_b_record(CH_ENVELOPE_LAST, CH_VOLUME),
    ]

    # $18272 — the portamento's own offset, in the note table's units.
    # `bclr`/`bset #5,44(a0)` — which end of its range the slide is running towards, and the two
    # clamps that flip it. Both `bcc`/`bcs` skip to the ONE store of the stepped value, so each of
    # them jumps over the other arm as well as over its own clamp.
    at_limit_bit = CH_PORTA_AT_LIMIT.bit_length() - 1
    clamped = [
        opcode(BCLR_IMM_D16_AN | A0) + word(at_limit_bit) + word(CH_PORTA_CONTROL),
        opcode(MOVE_B_DN_DN | (D1 << 9) | D4),
    ]
    step_up = [
        opcode(ADD_B_EA_DN | (D1 << 9) | EA_D16_A0) + word(CH_PORTA_STEP),
        opcode(CMP_B_DN_DN | (D1 << 9) | D4),
        _branch_s(BCS_S, clamped),
        *clamped,
    ]
    underflowed = [
        opcode(BSET_IMM_D16_AN | A0) + word(at_limit_bit) + word(CH_PORTA_CONTROL),
        moveq(0, D1),
    ]
    leave_step_up = [_branch_s(BRA_S, step_up)]
    step_down = [
        opcode(SUB_B_EA_DN | (D1 << 9) | EA_D16_A0) + word(CH_PORTA_STEP),
        _branch_s(BCC_S, underflowed + leave_step_up + step_up),
        *underflowed,
    ]
    porta_step = [
        btst_imm_dn(at_limit_bit, D6),
        _branch_s(BNE_S, step_down + leave_step_up),
        *step_down,
        *leave_step_up,
        *step_up,
        _move_b_dn_record(D1, CH_PORTA_CURRENT),
    ]
    octave_body = [
        lsl_w_imm_dn(SHIFT_BY_ONE, D1),
        _immediate_b(ADDI_B_IMM_DN, D5, PORTA_OCTAVE_STEP),
    ]
    octave_loop = octave_body + [
        lambda at: _branch_s_to(BCC_S, at, at - _bytes_of(octave_body)),
    ]
    hold_test = [
        btst_imm_dn(CH_FLAG_TOGGLE.bit_length() - 1, D7),
        _branch_s(BNE_S, porta_step),
    ]
    sign_extend = [subi_w_dn(D1, BYTE_LIMIT)]
    portamento = [
        opcode(MOVE_B_DN_DN | (D5 << 9) | D1),
        move_b_d16_dn(D4, A0, CH_PORTA_LIMIT),
        _shift_imm(SHIFT_BY_ONE, D4, left=True),
        move_b_d16_dn(D1, A0, CH_PORTA_CURRENT),
        btst_imm_dn(CH_PORTA_HELD.bit_length() - 1, D6),
        _branch_s(BEQ_S, hold_test),
        *hold_test,
        *porta_step,
        _shift_imm(SHIFT_BY_ONE, D4, left=False),
        opcode(SUB_B_EA_DN | (D1 << 9) | D4),
        _branch_s(BCC_S, sign_extend),
        *sign_extend,
        _immediate_b(ADDI_B_IMM_DN, D5, PORTA_OCTAVE_BIAS),
        _branch_s(BCS_S, octave_loop),
        *octave_loop,
        add_w_dn_dn(D0, D1),
    ]

    # $182dc — the vibrato, whose speed byte is a DELAY and not a divider: the tick that decrements
    # it to zero does not store the zero back.
    extend_depth = [addi_w_dn(D6, -BYTE_LIMIT)]
    vibrato_step = [
        clr_w_dn(D6),
        move_b_d16_dn(D6, A0, CH_VIBRATO_DEPTH),
        _branch_s(BPL_S, extend_depth),
        *extend_depth,
        opcode(ADD_W_EA_DN | (D6 << 9) | EA_D16_A0) + word(CH_VIBRATO_ACC),
        opcode(MOVE_W_DN_D16_AN | (A0 << 9) | D6) + word(CH_VIBRATO_ACC),
        opcode(ADD_W_EA_DN | (D0 << 9) | D6),
    ]
    store_speed = [_move_b_dn_record(D4, CH_VIBRATO_SPEED)]
    leave_vibrato = [_branch_s(BRA_S, store_speed)]
    vibrato = [
        move_b_d16_dn(D4, A0, CH_VIBRATO_SPEED),
        opcode(SUBQ_B_DN | (1 << 9) | D4),
        _branch_s(BNE_S, vibrato_step + leave_vibrato),
        *vibrato_step,
        *leave_vibrato,
        *store_speed,
    ]

    # $18300 — publish the noise period and merge this channel's bits into the shadow mixer.
    own_noise = [
        _move_b_pc_dn(D3, NOISE_PERIOD_BASE),
        _immediate_b(EORI_B_IMM_DN, D3, NOISE_PERIOD_XOR),
        _move_b_dn_module(D3, NOISE_PERIOD_OUT),
        opcode(MOVE_B_IMM_DN | (D3 << 9)) + word(NOISE_TONE_BITS),
    ]
    yielded = [
        opcode(ANDI_B_IMM_D16_AN | A0) + word(CH_YIELD_MASK) + word(CH_YIELD),
        move_b_d16_dn(D1, A0, CH_MIXER_MASK),
        _immediate_b(ANDI_B_IMM_DN, D1, MIXER_NOISE_BITS),
        opcode(NOT_B_DN | D1),
        opcode(AND_B_EA_DN | (D3 << 9) | D1),
        move_b_imm_d16(A3, NOISE_ROUTE_YIELDED, _module_displacement(NOISE_PERIOD_OUT)),
    ]
    mixer = [
        _immediate_b(EORI_B_IMM_DN, D7, BYTE_MASK),
        _move_b_pc_dn(D3, NOISE_ROUTE_MASK),
        _immediate_b(ANDI_B_IMM_DN, D7, CH_NOISE_ROUTE_FLAGS),
        _branch_s(BNE_S, own_noise),
        *own_noise,
        _move_b_pc_dn(D2, PSG_SHADOW + PSG_REG_MIXER),
        opcode(EOR_B_DN_EA | (D2 << 9) | D3),
        opcode(AND_B_EA_DN | (D3 << 9) | EA_D16_A0) + word(CH_MIXER_MASK),
        opcode(EOR_B_DN_EA | (D2 << 9) | D3),
        move_b_d16_dn(D1, A0, CH_YIELD),
        _branch_s(BPL_S, yielded),
        *yielded,
        _move_b_dn_module(D3, PSG_SHADOW + PSG_REG_MIXER),
        move_b_d16_dn(D1, A0, CH_VOLUME),
        RTS,
    ]

    arpeggio_loop = [opcode(MOVEA_L_D16_AN_AM | (A1 << 9) | A0) + word(CH_ARPEGGIO_BASE)]
    return leaf.assemble(base, [
        moveq(0, D7),
        move_b_d16_dn(D7, A0, CH_FLAGS),
        btst_imm_dn(CH_FLAG_ENVELOPE.bit_length() - 1, D7),
        _branch_s(BEQ_S, envelope),
        *envelope,
        move_b_d16_dn(D0, A0, CH_NOTE),
        lambda at: opcode(ADD_B_EA_DN | (D0 << 9) | EA_D16_PC) + _pc_relative(at, GLOBAL_TRANSPOSE),
        opcode(ADD_B_EA_DN | (D0 << 9) | EA_D16_A0) + word(CH_DETUNE),
        opcode(MOVEA_L_D16_AN_AM | (A1 << 9) | A0) + word(CH_ARPEGGIO_CURSOR),
        move_b_postinc_dn(D1, A1),
        opcode(BCLR_IMM_DN | D1) + word(ARPEGGIO_END.bit_length() - 1),
        _branch_s(BEQ_S, arpeggio_loop),
        *arpeggio_loop,
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A1) + word(CH_ARPEGGIO_CURSOR),
        opcode(ADD_B_EA_DN | (D0 << 9) | D1),
        lambda at: opcode(LEA_D16_PC_A1) + _pc_relative(at, NOTE_PERIOD_TABLE),
        opcode(ADD_B_EA_DN | (D0 << 9) | D0),
        moveq(0, D1),
        opcode(MOVE_B_DN_DN | (D1 << 9) | D0),
        opcode(ADDA_W_DN_AN | (A1 << 9) | D1),
        move_w_ind_dn(D0, A1),
        move_b_d16_dn(D6, A0, CH_PORTA_CONTROL),
        btst_imm_dn(CH_PORTA_ENABLED.bit_length() - 1, D6),
        _branch_s(BEQ_S, portamento),
        *portamento,
        _immediate_b(EORI_B_IMM_DN, D7, CH_FLAG_TOGGLE),
        _move_b_dn_record(D7, CH_FLAGS),
        btst_imm_dn(CH_FLAG_VIBRATO.bit_length() - 1, D7),
        _branch_s(BEQ_S, vibrato),
        *vibrato,
        *mixer,
    ])


# --- the pattern stepper, its opcode handlers and the tick body: their own encodings --------------
# Every one of these has ONE user (this file); the shared ones come from leaf.py as everywhere above.
# A `bcc.w` and a `bcc.s` SHARE their opcode word — the short form carries its displacement in the low
# byte, which is zero for the word form — so the constants above serve both and the FORM is which
# builder is used: `_branch_s`/`_branch_s_to` for the byte displacement, `_branch_w`/`branch_w_to`
# for the word one.
ADDQ_B_DN = 0x5000              # addq.b #n,Dn — the count in bits 11-9, 0 meaning 8
ADDQ_L_AN = 0x5088              # addq.l #n,An — `addq.l #4,sp`, opcode $8e's frame unwind
ADDQ_W_DN = 0x5040
CLR_B_DN = 0x4200
TST_L_D16_AN = 0x4aa8           # tst.l d16(An) — the LONG form, which is what makes a pad byte count
ADD_B_DN_D16_AN = 0xd128        # add.b Dn,d16(An): a memory read-modify-write, and the CARRY after it
AND_B_DN_D16_AN = 0xc128
ORI_B_IMM_D16_AN = 0x0028
MOVE_B_POSTINC_D16_AN = 0x1158  # move.b (An)+,d16(Am) — one operand byte out of the pattern stream
MOVE_B_PREDEC_D16_AN = 0x1160   # move.b -(An),d16(Am) — the envelope SPEED, one byte BELOW its stream
MOVE_W_IMM_D16_AN = 0x317c
MOVEA_W_D16_AN_AM = 0x3068
MOVE_B_D16_PC_ABS_L = 0x13fa    # move.b d16(pc),<abs>.l — one shadow byte to the PSG data port
TST_W_D8_AN_XN = 0x4a70
MOVEA_W_D8_AN_XN_AM = 0x3070    # movea.w d8(An,Xn.w),Am, with the BASE register in the low three
JMP_D8_AN_XN = 0x4ef0           # jmp d8(An,Xn.w) — $18106's last instruction, and the dispatch
INDEX_IS_ADDRESS_REG = 0x8000   # bit 15 of an extension word: the index is An and not Dn
SHIFT_TYPE_ROTATE = 0x18        # the type field at bits 4-3, where LSHIFT_LOGICAL is 01 and this 11
ST_D16_AN = 0x50e8              # st d16(An) — Scc with the always-true condition, SF_D16_AN's twin

TEMPO_HEAD_BYTES = 44           # $17c74..$17c9f, the two hardware reads and the byte they choose
CHANNEL_STEP_BODY_BYTES = 258   # $18106..$18207
PATTERN_HANDLER_BYTES = 306     # $17fd4..$18105 — the 24 handlers, BELOW the routine they belong to
TICK_BODY_BYTES = 644           # $17ca0..$17f23
PATTERN_HANDLER_BASE = leaf.entry_of("snd_pattern_op_97_trigger_sfx")

# The `rts` snd_music_tick's four exits share, and $1a5d8's twin: the two bytes BELOW the tick's own
# entry, derived from it rather than transcribed.
TICK_SHARED_RTS = leaf.entry_of("snd_music_tick") - len(RTS)
# ...and the tail both endings of a song enter. Opcode $8e's handler is `addq.l #4,sp` and then this,
# so the address the FADE branches to is the handler's entry plus that one instruction.
ADDQ_L_SP_BYTES = 2
END_SONG_TAIL = leaf.entry_of("snd_pattern_op_8e_end_song") + ADDQ_L_SP_BYTES


def _branch_w(condition, spanned):
    """`_branch_s`'s twin for the distances the tick's body is too long to say in a byte. No size
    assertion: the original spells `bne.w $18188` over 122 bytes, which a `.s` would have fitted."""
    return leaf.branch_over(condition, spanned if isinstance(spanned, int) else _bytes_of(spanned))


def _bra_shortest(target):
    """`bra` to ``target`` in the form the original's assembler picked — `.s` where the displacement
    fits in a byte and `.w` where it does not. Computed from the distance rather than transcribed,
    which is what makes a handler that moved fail on its own bytes rather than on a flag."""
    def build(at):
        displacement = target - (at + WORD_LEN)
        if -0x80 <= displacement < 0x80 and displacement not in (0, -1):
            return _branch_s_to(BRA_S, at, target)
        return branch_w_to(BRA_W, at, target)
    return build


def _rol_b(count, reg):
    """`rol.b #n,Dn` — the same base opcode as the shifts with the ROTATE type ORed in."""
    return opcode(LSHIFT_IMM_DN | ((count & 7) << 9) | LSHIFT_LEFT | SHIFT_TYPE_ROTATE | reg)


def _shadow_tone(channel):
    """The PSG register NUMBER of a channel's fine tone period, which is also its shadow's offset."""
    return PSG_REG_TONE_A + channel * PSG_REG_TONE_LEN


def _rol_byte(value, count):
    """`rol.b #n,Dn`, and for channel A no instruction at all — which is a rotate by zero."""
    wide = value << count
    return (wide | (wide >> 8)) & BYTE_MASK


def _channel_mixer_bits(channel):
    """$09, $12, $24 — one constant rotated by the channel number, which is the claim the `ori.b`
    immediates and the `rol.b` counts make together."""
    return _rol_byte(MIXER_CHANNEL_A_BITS, channel)


def _move_b_postinc_record(offset):
    return opcode(MOVE_B_POSTINC_D16_AN | (A0 << 9) | A1) + word(offset)


def _move_b_postinc_module(address):
    return opcode(MOVE_B_POSTINC_D16_AN | (A3 << 9) | A1) + _module_offset(address)


def _table_read(register, table):
    """`lea table(pc),An / movea.w 0(An,d0.w),An / adda.l a3,An` — the stepper's three word tables,
    read the same way the trigger's two are but WITHOUT the `ext.w` above them."""
    return [_lea_pc(register, table),
            opcode(MOVEA_W_D8_AN_XN_AM | (register << 9) | register) + word(D0 << 12),
            opcode(ADDA_L_AN_AM | (register << 9) | A3)]


def _channel_step_runs():
    """$18106's own 258 bytes, as the named runs its branches take their displacements from.

    Returned rather than assembled so the two addresses the OPCODE HANDLERS branch back into — the
    `moveq #0,d0` that reads the next pattern byte and the reload that closes the row — can be
    derived from the runs above them instead of transcribed, and the handler block and the stepper
    cannot then disagree about either.
    """
    noise_tracks = [_move_b_dn_module(D0, NOISE_PERIOD_BASE)]
    note = [
        _move_b_dn_record(D0, CH_NOTE),
        tst_b_d16(A0, CH_NOISE_TRACKS_NOTE),
        _branch_s(BEQ_S, noise_tracks),
        *noise_tracks,
        opcode(MOVEA_L_D16_AN_AM | (A2 << 9) | A0) + word(CH_ENVELOPE_BASE),
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A2) + word(CH_ENVELOPE_CURSOR),
        # The two reads of `(a2)` the original really does, one per field. The only store between
        # them is the cursor's, which is why src/sound.c fetches once.
        opcode(MOVE_B_IND_AN_D16_AM | (A0 << 9) | A2) + word(CH_ENVELOPE_LAST),
        opcode(MOVE_B_IND_AN_D16_AM | (A0 << 9) | A2) + word(CH_VOLUME),
        _move_b_record(CH_ENVELOPE_SPEED, CH_ENVELOPE_COUNT),
        opcode(BSET_IMM_D16_AN | A0) + word(CH_FLAG_ENVELOPE.bit_length() - 1) + word(CH_FLAGS),
    ]

    # $18152 — the hand-over ladder. Built from the BOTTOM, because each channel's second `beq` jumps
    # over everything that is left, which is exactly the run assembled so far.
    ladder = [opcode(ST_D16_AN | A0) + word(CH_YIELD)]
    for channel in reversed(range(CHANNELS)):
        probe = [opcode(BTST_IMM_D16_AN | A3) + word(MIXER_NOISE_OFF.bit_length() - 1)
                 + _module_offset(_channel_state(channel) + DESC_MIXER_BITS)]
        ladder = [
            _tst_b(ACTIVE_FLAGS + channel),
            _branch_s(BEQ_S, _bytes_of(probe) + SHORT_BRANCH_BYTES),
            *probe,
            _branch_s(BEQ_S, ladder),
        ] + ladder
    end_row = [
        _move_b_record(CH_DURATION_RELOAD, CH_DURATION),
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A1) + word(CH_PATTERN_CURSOR),
        tst_b_d16(A0, CH_YIELD),
        _branch_s(BEQ_S, ladder),
        *ladder,
        RTS,
    ]

    slide_up = [leaf.addq_b_d16(1, A0, CH_NOTE), RTS]
    slide = [
        opcode(BTST_IMM_D16_AN | A0) + word(CH_FLAG_SLIDE.bit_length() - 1) + word(CH_FLAGS),
        _branch_s(BNE_S, [RTS]),
        RTS,
        opcode(BTST_IMM_D16_AN | A0) + word(CH_FLAG_SLIDE_UP.bit_length() - 1) + word(CH_FLAGS),
        _branch_s(BEQ_S, slide_up),
        *slide_up,
        _subq_b_record(CH_NOTE),
        RTS,
    ]

    head = [_subq_b_record(CH_DURATION)]
    prologue = [clr_b_d16(A0, CH_FLAGS),
                opcode(MOVEA_L_D16_AN_AM | (A1 << 9) | A0) + word(CH_PATTERN_CURSOR)]
    read_next = leaf.entry_of("snd_channel_step") + _bytes_of(head) + BRANCH_EXTENSION * 2 \
        + _bytes_of(prologue)
    end_row_at = read_next + _bytes_of([moveq(0, D0), move_b_postinc_dn(D0, A1)]) \
        + BRANCH_EXTENSION * 2 + _bytes_of(note)

    arpeggio = _table_read(A2, ARPEGGIO_PTR_TABLE) + [
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A2) + word(CH_ARPEGGIO_CURSOR),
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A2) + word(CH_ARPEGGIO_BASE),
        lambda at: branch_w_to(BRA_W, at, read_next),
    ]
    arpeggio = [add_w_dn_dn(D0, D0)] + arpeggio
    duration = [
        opcode(ADDQ_B_DN | (1 << 9) | D0),
        _move_b_dn_record(D0, CH_DURATION_RELOAD),
        lambda at: branch_w_to(BRA_W, at, read_next),
    ]
    instrument = [add_w_dn_dn(D0, D0)] + _table_read(A2, INSTRUMENT_PTR_TABLE) + [
        opcode(MOVE_L_AN_D16_AM | (A0 << 9) | A2) + word(CH_ENVELOPE_BASE),
        opcode(MOVE_B_PREDEC_D16_AN | (A0 << 9) | A2) + word(CH_ENVELOPE_SPEED),
        lambda at: branch_w_to(BRA_W, at, read_next),
    ]
    dispatch = [
        leaf.andi_w_dn(D0, PATTERN_CMD_INDEX_MASK),
        add_w_dn_dn(D0, D0),
        _lea_pc(A2, PATTERN_JUMP_TABLE),
        opcode(MOVEA_W_D8_AN_XN_AM | (A2 << 9) | A2) + word(D0 << 12),
        opcode(JMP_D8_AN_XN | A3) + word(INDEX_IS_ADDRESS_REG | (A2 << 12)),
    ]
    # The range chain, built bottom-up so each `bcs` spans exactly the pieces between it and its arm.
    add_arpeggio = [_immediate_b(ADDI_B_IMM_DN, D0, PATTERN_ARPEGGIO_BIAS)]
    to_instrument = add_arpeggio + arpeggio + duration
    add_instrument = [_immediate_b(ADDI_B_IMM_DN, D0, PATTERN_INSTRUMENT_BIAS),
                      _branch_s(BCS_S, to_instrument)]
    to_duration = add_instrument + add_arpeggio + arpeggio
    add_duration = [_immediate_b(ADDI_B_IMM_DN, D0, PATTERN_DURATION_BIAS),
                    _branch_s(BCS_S, to_duration)]
    to_dispatch = add_duration + add_instrument + add_arpeggio + arpeggio + duration + instrument
    decode = [opcode(CMP_B_IMM_DN | D0) + word(PATTERN_CMD_LIMIT),
              _branch_s(BCS_S, to_dispatch)] + to_dispatch + dispatch

    read = [moveq(0, D0), move_b_postinc_dn(D0, A1), _branch_w(BMI_S, note + end_row + slide)]
    # The opening `bne.w` reaches the SLIDE, so it spans the read loop and the row but not the arms
    # below it — which is also the only reason the pattern walk is unreachable while a row runs.
    to_slide = prologue + read + note + end_row
    body = to_slide + slide + decode
    return {"pieces": [*head, _branch_w(BNE_S, to_slide), *body],
            "read_next": read_next, "end_row": end_row_at}


_CHANNEL_STEP = _channel_step_runs()
# The two addresses inside $18106 that a handler `bra`s back to — $18116 and $18148 — DERIVED.
PATTERN_READ_NEXT = _CHANNEL_STEP["read_next"]
PATTERN_END_ROW = _CHANNEL_STEP["end_row"]


def _channel_step_entry():
    """$18106, whole: the countdown, the pitch slide, the pattern read loop, the range decoder and
    the `jmp` through the opcode table, which is its LAST instruction."""
    return leaf.assemble(leaf.entry_of("snd_channel_step"), _CHANNEL_STEP["pieces"])


def _noise_route_handler(bits, tracks_note):
    """$18044 and $18064 — opcodes $8b and $8a, one body with two masks and two flag values."""
    return [
        move_b_d16_dn(D0, A0, CH_MIXER_MASK),
        opcode(MOVE_B_DN_DN | (D1 << 9) | D0),
        _immediate_b(ANDI_B_IMM_DN, D0, bits),
        _move_b_pc_dn(D2, NOISE_ROUTE_MASK),
        opcode(EOR_B_DN_EA | (D2 << 9) | D0),
        opcode(AND_B_EA_DN | (D0 << 9) | D1),
        opcode(EOR_B_DN_EA | (D2 << 9) | D0),
        _move_b_dn_module(D0, NOISE_ROUTE_MASK),
        opcode((ST_D16_AN if tracks_note else SF_D16_AN) | A0) + word(CH_NOISE_TRACKS_NOTE),
        _bra_shortest(PATTERN_READ_NEXT),
    ]


# The twenty-four handlers in ADDRESS order — which is not the table's order — each named for the
# opcode whose table entry points at it. Two of the entries share $180e4, and two handlers FALL INTO
# the one below them ($86 into $85's `bset`, $88 into $82's control store), so the block is 23 runs.
def _pattern_handler_runs():
    set_flag = lambda bit: opcode(BSET_IMM_D16_AN | A0) + word(bit) + word(CH_FLAGS)  # noqa: E731
    return (
        # $97 — one operand byte into d0, then stub +56, WITHOUT ever setting d1 (../names.txt).
        [move_b_postinc_dn(D0, A1),
         lambda at: bsr_w(at, leaf.entry_of("snd_call_trigger_effect")),
         _bra_shortest(PATTERN_READ_NEXT)],
        [_move_b_postinc_module(MASTER_VOLUME), _bra_shortest(PATTERN_READ_NEXT)],           # $96
        [_move_b_postinc_module(FADE_RATE), _move_b_pc(FADE_RATE, FADE_COUNTDOWN),
         _bra_shortest(PATTERN_READ_NEXT)],                                                  # $95
        [_move_b_postinc_module(SONG_SPEED), _move_b_pc(SONG_SPEED, SONG_SPEED_COPY),
         _bra_shortest(PATTERN_READ_NEXT)],                                                  # $94
        [_move_b_postinc_record(CH_SEQUENCE_OFFSET),
         _move_b_postinc_record(CH_SEQUENCE_OFFSET + 1),
         opcode(MOVE_W_IMM_D16_AN | A0) + word(0) + word(CH_SEQUENCE_INDEX),
         _bra_shortest(PATTERN_READ_NEXT)],                                                  # $93
        # $8e — the frame unwind, and then the tail the FADE enters two bytes later.
        [opcode(ADDQ_L_AN | (4 << 9) | A7),
         opcode(SF_D16_AN | A3) + _module_offset(SONG_LOADED),
         lambda at: branch_w_to(BRA_W, at, STUB_TABLE_BASE + STUB_STOP_OFFSET)],
        [move_w_ind_dn(D0, A0, CH_SEQUENCE_INDEX),                                           # $87
         opcode(MOVEA_W_D16_AN_AM | (A2 << 9) | A0) + word(CH_SEQUENCE_OFFSET),
         opcode(ADDA_W_DN_AN | (A2 << 9) | D0),
         opcode(ADDQ_W_DN | (WORD_LEN << 9) | D0),
         opcode(TST_W_D8_AN_XN | A3) + word(INDEX_IS_ADDRESS_REG | (A2 << 12)),
         _branch_s(BNE_S, [opcode(MOVEA_W_D16_AN_AM | (A2 << 9) | A0) + word(CH_SEQUENCE_OFFSET),
                           moveq(WORD_LEN, D0)]),
         opcode(MOVEA_W_D16_AN_AM | (A2 << 9) | A0) + word(CH_SEQUENCE_OFFSET),
         moveq(WORD_LEN, D0),
         opcode(MOVEA_W_D8_AN_XN_AM | (A1 << 9) | A3) + word(INDEX_IS_ADDRESS_REG | (A2 << 12)),
         opcode(ADDA_L_AN_AM | (A1 << 9) | A3),
         opcode(MOVE_W_DN_D16_AN | (A0 << 9) | D0) + word(CH_SEQUENCE_INDEX),
         _bra_shortest(PATTERN_READ_NEXT)],
        _noise_route_handler(NOISE_TONE_BITS, tracks_note=True),                             # $8b
        _noise_route_handler(MIXER_NOISE_BITS, tracks_note=False),                           # $8a
        [move_b_d16_dn(D0, A0, CH_MIXER_MASK),                                               # $8c
         _immediate_b(EORI_B_IMM_DN, D0, BYTE_MASK),
         _move_b_pc_dn(D2, NOISE_ROUTE_MASK),
         opcode(AND_B_EA_DN | (D0 << 9) | D2),
         opcode(AND_B_DN_D16_AN | (D0 << 9) | A3) + _module_offset(NOISE_ROUTE_MASK),
         opcode(ST_D16_AN | A0) + word(CH_NOISE_TRACKS_NOTE),
         _bra_shortest(PATTERN_READ_NEXT)],
        [clr_w_d16(A0, CH_VIBRATO_ACC), set_flag(CH_FLAG_VIBRATO.bit_length() - 1),          # $84
         _move_b_postinc_record(CH_VIBRATO_DEPTH), _move_b_postinc_record(CH_VIBRATO_SPEED),
         _bra_shortest(PATTERN_READ_NEXT)],
        [_move_b_postinc_module(GLOBAL_TRANSPOSE), _bra_shortest(PATTERN_READ_NEXT)],        # $89
        [_move_b_postinc_record(CH_DETUNE), _bra_shortest(PATTERN_READ_NEXT)],               # $92
        [set_flag(CH_FLAG_SLIDE_UP.bit_length() - 1)],                                       # $86 ->
        [set_flag(CH_FLAG_SLIDE.bit_length() - 1), _bra_shortest(PATTERN_READ_NEXT)],        # $85
        [_move_b_postinc_record(CH_PORTA_STEP),                                              # $88 ->
         opcode(MOVE_B_IND_AN_D16_AM | (A0 << 9) | A1) + word(CH_PORTA_LIMIT),
         _move_b_postinc_record(CH_PORTA_CURRENT)],
        [move_b_imm_d16(A0, CH_PORTA_ENABLED, CH_PORTA_CONTROL),                             # $82
         _bra_shortest(PATTERN_READ_NEXT)],
        [clr_b_d16(A0, CH_PORTA_CONTROL), _bra_shortest(PATTERN_READ_NEXT)],                 # $81
        [set_flag(CH_FLAG_MARK.bit_length() - 1), _bra_shortest(PATTERN_READ_NEXT)],         # $83/$8d
        [clr_b_d16(A0, CH_VOLUME), _bra_shortest(PATTERN_END_ROW)],                          # $80
        [set_flag(CH_FLAG_ENVELOPE.bit_length() - 1), _bra_shortest(PATTERN_END_ROW)],       # $8f
        [opcode(ST_D16_AN | A0) + word(CH_YIELD), _bra_shortest(PATTERN_READ_NEXT)],         # $90
        [opcode(SF_D16_AN | A0) + word(CH_YIELD), _bra_shortest(PATTERN_READ_NEXT)],         # $91
    )


PATTERN_HANDLER_NAMES = (
    "snd_pattern_op_97_trigger_sfx", "snd_pattern_op_96_master_volume",
    "snd_pattern_op_95_fade_rate", "snd_pattern_op_94_song_speed",
    "snd_pattern_op_93_set_sequence", "snd_pattern_op_8e_end_song",
    "snd_pattern_op_87_next_pattern", "snd_pattern_op_8b_route_tone",
    "snd_pattern_op_8a_route_noise", "snd_pattern_op_8c_route_off",
    "snd_pattern_op_84_vibrato_on", "snd_pattern_op_89_transpose", "snd_pattern_op_92_detune",
    "snd_pattern_op_86_slide_up", "snd_pattern_op_85_slide_on",
    "snd_pattern_op_88_portamento_set", "snd_pattern_op_82_portamento_on",
    "snd_pattern_op_81_portamento_off", "snd_pattern_op_83_set_flag_bit1",
    "snd_pattern_op_80_rest", "snd_pattern_op_8f_envelope_on",
    "snd_pattern_op_90_yield_to_sfx", "snd_pattern_op_91_reclaim_channel",
)
# Where in the table each of those handlers is named from — the opcode's own index, and $180e4 twice.
PATTERN_OPCODE_OF_HANDLER = (0x17, 0x16, 0x15, 0x14, 0x13, 0x0e, 0x07, 0x0b, 0x0a, 0x0c, 0x04, 0x09,
                             0x12, 0x06, 0x05, 0x08, 0x02, 0x01, 0x03, 0x00, 0x0f, 0x10, 0x11)
PATTERN_ALIASED_OPCODE = 0x0d       # $8d, whose table entry is $83's handler
STUB_STOP_OFFSET = 28               # stub +28, which opcode $8e's tail `bra.w`s into


def _pattern_handlers():
    """$17fd4..$18105 — the twenty-three handler bodies, laid out end to end at the block's base."""
    return leaf.assemble(PATTERN_HANDLER_BASE,
                         [piece for run in _pattern_handler_runs() for piece in run])


def _psg_write_shadow(register, shadow_reg):
    """`move.b #reg,$ff8800.l / move.b d16(pc),$ff8802.l` — select, then one SHADOW byte."""
    select = _psg_select(register)
    return lambda at: (select + opcode(MOVE_B_D16_PC_ABS_L)
                       + _pc_relative(at + len(select), PSG_SHADOW + shadow_reg) + longword(PSG_DATA))


def _tick_body_entry():
    """$17ca0, whole. The gate, the drop accumulator, the three calls, the SFX mixdown and the chip
    write, with every module address, every stride and both non-local exits at once."""
    base = leaf.entry_of("snd_music_tick_body")

    fade_reload = [_move_b_pc(FADE_RATE, FADE_COUNTDOWN)]
    volume_step = [_subq_b_module(MASTER_VOLUME),
                   lambda at: branch_w_to(BEQ_S, at, END_SONG_TAIL)] + fade_reload
    fade_rest = [_tst_b(MASTER_VOLUME),
                 lambda at: branch_w_to(BEQ_S, at, END_SONG_TAIL),
                 _subq_b_module(FADE_COUNTDOWN),
                 _branch_s(BNE_S, volume_step)] + volume_step
    fade = [_move_b_pc_dn(D0, FADE_RATE), _branch_s(BEQ_S, fade_rest)] + fade_rest

    reseed = [_move_b_pc(NOISE_PERIOD_BASE, NOISE_PERIOD_OUT)]

    row_calls = []
    for channel in range(CHANNELS):
        row_calls += [_lea_pc(A0, _music_channel(channel)),
                      lambda at: bsr_w(at, leaf.entry_of("snd_channel_step"))]
    rows = [_move_b_pc_dn(D0, SONG_SPEED),
            opcode(ADD_B_DN_D16_AN | (D0 << 9) | A3) + _module_offset(SPEED_ACC),
            _branch_s(BCC_S, row_calls)] + row_calls

    publish = [opcode(ANDI_B_IMM_D16_AN | A3) + word(MASTER_VOLUME_MASK)
               + _module_offset(MASTER_VOLUME)]
    for channel in range(CHANNELS):
        clamp = [moveq(0, D1)]
        publish += [
            _lea_pc(A0, _music_channel(channel)),
            lambda at: bsr_w(at, leaf.entry_of("snd_channel_period_and_volume")),
            opcode(MOVE_W_DN_D16_AN | (A3 << 9) | D0) + _module_offset(PERIOD_SCRATCH),
            _move_b_dn_module(D0, PSG_SHADOW + _shadow_tone(channel)),
            _move_b_pc(PERIOD_SCRATCH, PSG_SHADOW + _shadow_tone(channel) + 1),
            _move_b_pc_dn(D0, MASTER_VOLUME),
            _immediate_b(EORI_B_IMM_DN, D0, MASTER_VOLUME_FULL),
            opcode(SUB_B_EA_DN | (D1 << 9) | D0),
            _branch_s(BCC_S, clamp),
            *clamp,
            _move_b_dn_module(D1, PSG_SHADOW + PSG_REG_VOLUME_A + channel),
        ]
    publish += [_move_b_pc(NOISE_PERIOD_OUT, PSG_SHADOW + PSG_REG_NOISE_PERIOD)]

    mixdown = []
    for channel in range(CHANNELS):
        noise_store = [_move_b_pc(MIX_NOISE, PSG_SHADOW + PSG_REG_NOISE_PERIOD)]
        arm = [
            _move_b_pc(_mix_period(channel) + MIX_PERIOD_LOW, PSG_SHADOW + _shadow_tone(channel)),
            _move_b_pc(_mix_period(channel), PSG_SHADOW + _shadow_tone(channel) + 1),
            _move_b_pc_dn(D0, _channel_state(channel) + DESC_MIXER_BITS),
            btst_imm_dn(MIXER_NOISE_OFF.bit_length() - 1, D0),
            _branch_s(BNE_S, noise_store),
            *noise_store,
            opcode(ORI_B_IMM_D16_AN | A3) + word(_channel_mixer_bits(channel))
            + _module_offset(PSG_SHADOW + PSG_REG_MIXER),
            *([] if channel == CHANNEL_A else [_rol_b(channel, D0)]),
            opcode(AND_B_DN_D16_AN | (D0 << 9) | A3)
            + _module_offset(PSG_SHADOW + PSG_REG_MIXER),
            _move_b_pc(MIX_VOLUME + channel, PSG_SHADOW + PSG_REG_VOLUME_A + channel),
        ]
        # Channel A alone can abandon the tick, exactly as it alone can end snd_sfx_tick.
        abandon = ([lambda at: branch_w_to(BMI_S, at, TICK_SHARED_RTS)]
                   if channel == CHANNEL_A else [])
        mixdown += [_tst_b(ACTIVE_FLAGS + channel), _branch_s(BEQ_S, abandon + arm)] + abandon + arm
    mixdown += [opcode(ANDI_B_IMM_D16_AN | A3) + word(PSG_MIXER_ALL_OFF)
                + _module_offset(PSG_SHADOW + PSG_REG_MIXER)]

    noise_write = [_psg_write_shadow(PSG_REG_NOISE_PERIOD, PSG_REG_NOISE_PERIOD)]
    chip = [
        opcode(MOVE_SR_DN | D1),
        opcode(MOVE_IMM_SR) + word(SUPERVISOR_SR),
        opcode(CLR_B_DN | D2),
        opcode(TST_L_D16_AN | A3) + _module_offset(CHANNEL_LOCKS),
        _branch_s(BNE_S, noise_write),
        *noise_write,
    ]
    for channel in range(CHANNELS):
        writes = [
            _psg_write_shadow(_shadow_tone(channel), _shadow_tone(channel)),
            _psg_write_shadow(_shadow_tone(channel) + 1, _shadow_tone(channel) + 1),
            _psg_write_shadow(PSG_REG_VOLUME_A + channel, PSG_REG_VOLUME_A + channel),
            _immediate_b(ORI_B_IMM_DN, D2, _channel_mixer_bits(channel)),
        ]
        chip += [_tst_b(CHANNEL_LOCKS + channel), _branch_s(BNE_S, writes)] + writes
    chip += [
        _psg_select(PSG_REG_MIXER),
        move_b_abs_l_dn(D0, PSG_SELECT),
        _move_b_pc_dn(D3, PSG_SHADOW + PSG_REG_MIXER),
        opcode(EOR_B_DN_EA | (D0 << 9) | D3),
        opcode(AND_B_EA_DN | (D3 << 9) | D2),
        opcode(EOR_B_DN_EA | (D0 << 9) | D3),
        opcode(MOVE_B_DN_ABS_L | D3) + longword(PSG_DATA),
        opcode(MOVE_DN_SR | D1),
        lambda at: branch_w_to(BRA_W, at, TICK_SHARED_RTS),
    ]

    gate_flags = [opcode(TST_L_D16_AN | A3) + _module_offset(ACTIVE_FLAGS)]
    gate_tail = gate_flags + [lambda at: _branch_s_to(BEQ_S, at, TICK_SHARED_RTS)]
    music = fade + reseed + rows + publish
    return leaf.assemble(base, [
        _tst_b(ENGINE_ENABLED),
        _branch_s(BNE_S, _bytes_of(gate_flags) + SHORT_BRANCH_BYTES),
        *gate_tail,
        _move_b_pc_dn(D0, TICK_DROP_VALUE),
        opcode(ADD_B_DN_D16_AN | (D0 << 9) | A3) + _module_offset(TICK_DROP_ACC),
        lambda at: _branch_s_to(BCS_S, at, TICK_SHARED_RTS),
        lambda at: bsr_w(at, leaf.entry_of("snd_sfx_tick")),
        _tst_b(ENGINE_ENABLED),
        _branch_w(BEQ_S, music),
        *music,
        *mixdown,
        *chip,
    ])


def _tempo_head_entry():
    """$17c74: the module base, the DEFAULT drop value, and the two hardware tests that overwrite it.

    Both `btst`s carry their bit number in an extension word and their address as an absolute LONG,
    so this pin is over the bit AND the address at once — a port reading the neighbouring MFP
    register, or testing bit 6, fails here before any case runs. Both branch displacements come from
    the length of the arm they skip, so the three-way shape is the pin's claim and not a transcribed
    number.
    """
    base = leaf.entry_of("snd_music_tick")
    sixty_hz = [leaf.move_b_imm_d16(A3, TICK_DROP_60HZ, _module_displacement(TICK_DROP_VALUE))]
    colour_arm = [_btst_imm_abs_l(SYNC_50HZ.bit_length() - 1, leaf.SHIFTER_SYNC),
                  _branch_s(BNE_S, sixty_hz)] + sixty_hz
    mono_arm = [leaf.move_b_imm_d16(A3, TICK_DROP_MONO, _module_displacement(TICK_DROP_VALUE)),
                _branch_s(BRA_S, colour_arm)]
    return leaf.assemble(base, [
        _lea_pc(A3, MODULE_BASE),
        leaf.move_b_imm_d16(A3, TICK_DROP_50HZ, _module_displacement(TICK_DROP_VALUE)),
        _btst_imm_abs_l(GPIP_COLOUR_MONITOR.bit_length() - 1, leaf.MFP_GPIP),
        _branch_s(BNE_S, mono_arm),
    ] + mono_arm + colour_arm)


ENTRY_BYTES = {
    "snd_music_tick": _tempo_head_entry(),
    "snd_trigger_effect": _trigger_entry(),
    "snd_call_trigger_effect": _stub(*_TRIGGER_STUB),
    "snd_psg_silence": _silence_entry(),
    "snd_stop_all_sfx": _stop_all_entry(),
    "snd_stop": _stop_entry(),
    "snd_prng_step": _prng_entry(),
    "snd_sfx_tick": _sfx_tick_entry(),
    "snd_channel_period_and_volume": _period_volume_entry(),
    "snd_channel_step": _channel_step_entry(),
    "snd_music_tick_body": _tick_body_entry(),
}
SOUND_ROUTINE_COUNT = 11

# The caps, from the bodies, each the body's own instruction count plus the one instruction osh_run
# counts past its `rts` (leaf.RUNNER_SENTINEL_INSN — measured here first, hoisted there once three
# batteries derived caps from instruction counts). Silence is 2 SR moves + 4 for the mixer
# read-modify-write + 2 per volume register + the restore and the `rts`; each entrant above it adds
# its own stores and its `bra.w` (stop_all: `lea`, three clears, the shadow mixer store, the branch;
# stop: `lea`, `sf`, branch).
SILENCE_INSN_CAP = 2 + 4 + 2 * len(SILENCED_VOLUMES) + 2 + leaf.RUNNER_SENTINEL_INSN
STOP_ALL_INSN_CAP = SILENCE_INSN_CAP + 6
STOP_INSN_CAP = STOP_ALL_INSN_CAP + 3

# --- the glue ------------------------------------------------------------------------------------
_trigger = leaf.register_glue("snd_trigger_effect", [ctypes.c_uint32] * 2)
_stub_call = leaf.register_glue("snd_call_trigger_effect", [ctypes.c_uint32] * 2)
_stop = leaf.image_glue("snd_stop")
_stop_all = leaf.image_glue("snd_stop_all_sfx")

# snd_psg_silence takes NO image argument — it writes no image byte, and its whole output is the
# access ledger — so its glue is the one here that cannot come out of leaf's two factories.
_silence_fn = leaf.bind("snd_psg_silence", [])


def _silence(_lib, _image):
    return _silence_fn()


def _run(name, glue, image, effect_id, channel, what, regs, poison=True, insns=None):
    """One trigger differential: run it, bound its write set to the arm's own, and compare every
    byte against the model above. ``image`` is what the model reads — the loaded image, or a poked
    copy of it where the case seeded one."""
    written = expected_writes(image, effect_id, channel)
    info = leaf.run(name, glue, write_bands(written), what, regs=regs, poison=poison,
                    max_insns=insns or TRIGGER_INSN_CAP)
    assert_written(info, written, what)
    return info


def _poked_image(pokes):
    """The loaded image with ``pokes`` applied — what the model reads for a case that seeds one.

    The kit applies the same dict to the run itself (``regs["_pokes"]``); this is the model's copy
    of it, so the expectation is computed over exactly the bytes both sides are given.
    """
    image = bytearray(harness.BASE_IMAGE)
    for addr, value in pokes.items():
        image[addr:addr + len(value)] = value
    return image


def _run_trigger(effect_id, channel, what, entry_d0=0, entry_d1=None, poison=True):
    """``entry_d0``/``entry_d1`` carry the bits ABOVE the byte each register is read at."""
    d0, d1 = entry_d0 | effect_id, channel if entry_d1 is None else entry_d1
    return _run("snd_trigger_effect", _trigger(d0, d1), harness.BASE_IMAGE, effect_id, channel,
                what, regs={"d0": d0, "d1": d1}, poison=poison)


def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, SOUND_ROUTINE_COUNT)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_an_entry_is_the_instruction_this_battery_reconstructs(name):
    """One assert per routine over every address, offset, stride and immediate at once — including
    all three channel arms, which is where the base-plus-stride claim is really tested."""
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


def test_the_three_arms_fill_the_body_and_the_next_routines_rts_follows_it():
    """Without this the entry pin would pass on a body of any length. The two bytes past the end are
    an `rts` no arm of THIS routine reaches — each ends with its own.

    IT IS NOT AN ORPHAN, which is what this case and ../names.txt both used to say. Batch 23 read
    the branches: it is snd_sfx_tick's shared `rts`, the target of that routine's `bmi.s` at $1a5e6
    and its `bra.s` at $1a600, exactly as $17c72 serves snd_music_tick. So it is the first two bytes
    of the NEXT routine and the boundary between them, which is why the tick's own body test below
    asserts it from the other side as well.
    """
    entry = leaf.entry_of("snd_trigger_effect")
    body = len(ENTRY_BYTES["snd_trigger_effect"])
    assert body == TRIGGER_BODY_BYTES, (
        f"the three arms assemble to {body} bytes, not the {TRIGGER_BODY_BYTES} claimed")
    following = bytes(harness.BASE_IMAGE[entry + body:entry + body + len(RTS)])
    assert following == RTS, f"the two bytes past the body are {following.hex()}, not an `rts`"


def test_the_noise_store_is_the_length_its_branch_skips():
    """`bne.s` over the noise store is the one displacement built from a stated length rather than
    from the piece itself, so the length is checked against the piece."""
    assert len(_move_b_pc(0, MODULE_BASE)(0)) == NOISE_STORE_BYTES


# --- the tables, read off the image ---------------------------------------------------------------

def test_the_two_tables_are_self_bounding():
    """Nothing in the image declares either table's length; both are read off the DATA, and both
    prove themselves the same way — entry 0 resolves to the byte immediately past the table, and the
    records behind it end exactly where the next table begins."""
    image = harness.BASE_IMAGE
    assert _descriptor_of(image, 0) == DESCRIPTORS, "the pointer table's entry 0 must abut it"
    assert DESCRIPTORS + SFX_IDS * DESCRIPTOR_LEN == VOLUME_PTRS, (
        "the descriptors must end exactly where the volume-stream pointers begin")
    assert _module_pointer(image, VOLUME_PTRS, 0) == VOLUME_PTRS + VOLUME_STREAMS * TABLE_ENTRY_LEN


def test_every_shipped_descriptor_selects_a_volume_stream_in_range():
    """The +10 field indexes a ten-entry table with no check on it. That every shipped descriptor
    stays inside it is the other half of the counts above — and the reason a SEEDED descriptor is
    needed to reach the out-of-range arm at all."""
    image = harness.BASE_IMAGE
    for effect_id in range(SFX_IDS):
        index = image[DESCRIPTORS + effect_id * DESCRIPTOR_LEN + DESC_VOLUME_INDEX]
        assert index < VOLUME_STREAMS, f"sfx {effect_id}'s volume index is {index:#04x}"


def test_the_shipped_descriptors_reach_both_arms_of_the_noise_test():
    """`btst #3` is a branch the shipped data has to exercise from both sides, or every case below
    would agree about the noise byte for one reason only."""
    image = harness.BASE_IMAGE
    noise_off = [image[DESCRIPTORS + i * DESCRIPTOR_LEN + DESC_MIXER_BITS] & MIXER_NOISE_OFF
                 for i in range(SFX_IDS)]
    assert any(noise_off) and not all(noise_off), f"the mixer bit is one-sided: {noise_off}"


def test_the_three_channels_address_three_disjoint_sets_of_bytes():
    """The four strides the arms step by, checked against each other rather than read off the
    disassembly a second time: three states, three flags, three period words and three volume bytes
    have to be disjoint or an arm would arm a neighbour's channel."""
    blocks = []
    for channel in range(CHANNELS):
        blocks.append(set(range(_channel_state(channel), _channel_state(channel) + STATE_LEN))
                      | {ACTIVE_FLAGS + channel, MIX_VOLUME + channel}
                      | set(range(_mix_period(channel),
                                  MIX_PERIOD + (channel + 1) * MIX_PERIOD_LEN)))
    for channel in range(CHANNELS):
        for other in range(channel + 1, CHANNELS):
            assert not blocks[channel] & blocks[other], f"channels {channel} and {other} overlap"
        assert MIX_NOISE not in blocks[channel], "the noise byte belongs to no single channel"


# --- $1a48a over the game's own data --------------------------------------------------------------

# EVERY `lea $17adc.l,aN` in the program — the stub table is the module's only entry point from
# outside it, so this is the whole of the game's traffic with the driver. The sites that go on to
# the TRIGGER carry the (id, channel) pair they load; the rest play a song, stop, tick, fade or poll
# a flag. ../notes/sound_module_recon.md holds the same table with the stub offset each one calls.
SFX_CALL_SITES = {
    0x000a98: (22, 0), 0x000c42: (5, 0), 0x000ca0: (5, 0), 0x000e82: (0, 0),
    0x00169c: (1, 0), 0x001726: (3, 0), 0x0017bc: (3, 0), 0x001982: (4, 0),
    0x0020ee: (6, 0), 0x00542c: (9, 0), 0x00678c: (9, 0), 0x00679c: (8, 0),
    0x006ae4: (11, 0), 0x006b4e: (19, 1), 0x006be2: (25, 0), 0x00bc9c: (15, 0),
}
NON_TRIGGER_CALL_SITES = (0x00058e, 0x000720, 0x000ae2, 0x000c90, 0x00191e, 0x00192c,
                          0x006bca, 0x006fb0, 0x00e54a, 0x00f9fc)

# ...and the ids the sweeps run, DERIVED from those sites rather than listed beside them: a list of
# its own could omit one the game passes and still look complete, which is exactly what happened to
# id 19 ($6b46's, the one channel-B site) until batch 17.
SHIPPED_CALL_IDS = tuple(sorted({effect_id for effect_id, _channel in SFX_CALL_SITES.values()}))

# `lea $17adc.l,aN` for every one of the 68000's eight address registers — what the scan below looks
# for. Built with leaf's own encoder, so the scan and the entry pins spell the instruction once.
ADDRESS_REGISTERS = 8
LEA_STUB_TABLE = {leaf.lea_abs_l(reg, STUB_TABLE_BASE) for reg in range(ADDRESS_REGISTERS)}
LEA_ABS_L_BYTES = len(next(iter(LEA_STUB_TABLE)))


@pytest.mark.parametrize("effect_id", range(SFX_IDS))
def test_a_shipped_effect_arms_channel_a_from_its_descriptor(effect_id):
    _run_trigger(effect_id, CHANNEL_A, f"sfx {effect_id} on channel A, shipped descriptor")


def test_the_sweep_covers_every_id_the_game_actually_passes():
    """COMPLETENESS rather than containment. The old form of this case asserted only that the ids
    were a SUBSET of 0..25, which an id the game passes but the table omits satisfies while being
    absent — and one was: 19, from $6b46's channel-B site.

    So the table above is required to name EVERY `lea $17adc.l,aN` in the program, which is every
    way anything outside $17adc..$1abc8 reaches the module at all, and SHIPPED_CALL_IDS is derived
    from it. A new call site then either appears in the table or reddens here.
    """
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    scanned = {at for at in range(0, len(program) - LEA_ABS_L_BYTES, WORD_LEN)
               if program[at:at + LEA_ABS_L_BYTES] in LEA_STUB_TABLE}
    stated = set(SFX_CALL_SITES) | set(NON_TRIGGER_CALL_SITES)
    assert scanned == stated, (
        f"the program names the stub table at {sorted(hex(a) for a in scanned - stated)} as well, "
        f"and not at {sorted(hex(a) for a in stated - scanned)}")
    assert set(SHIPPED_CALL_IDS) <= set(range(SFX_IDS)), (
        f"a shipped site passes an id outside the table: {SHIPPED_CALL_IDS}")


@pytest.mark.parametrize("channel", range(CHANNEL_A + 1, CHANNELS))
@pytest.mark.parametrize("effect_id", SHIPPED_CALL_IDS)
def test_every_channel_arm_uses_its_own_offsets(effect_id, channel):
    """The B arm is LIVE — $6b46 passes d1 = 1 (test_actor.py's
    `test_the_enemy_path_asks_for_a_channel_the_rest_of_the_image_never_does` pins that from its
    entry bytes) — and C is the dead one. Both are swept here, because the entry pin CLAIMS the
    three arms are one base plus a stride and only a case shows they behave that way. Channel A is
    left out because the sweep above already runs every one of these ids on it."""
    _run_trigger(effect_id, channel, f"sfx {effect_id} on channel {channel}")


def test_the_channel_is_chosen_by_d1s_low_byte_alone():
    """`cmp.b #0,d1` reads one byte, so a d1 whose upper three bytes are rubbish still selects
    channel A — and a d1 of $ffffffff selects C the way a d1 of 2 does."""
    _run_trigger(SHIPPED_CALL_IDS[0], CHANNEL_A, "channel A behind a poisoned d1",
                 entry_d1=0xdeadbe00)
    _run_trigger(SHIPPED_CALL_IDS[0], CHANNELS - 1, "channel C from a d1 of $ff",
                 entry_d1=0xffffffff)


# Every d1 the third arm has to swallow. 2 is the channel it names and 3 the first value past it,
# which is the pair a clamp written one off would tell apart — and it is not hypothetical: the
# pattern opcode $97 reaches the stub without ever setting d1 (../names.txt), so any byte can arrive.
CHANNEL_C_SELECTORS = (2, 3, 0x10, 0x7f, 0x80, 0xfe, 0xff)


@pytest.mark.parametrize("selector", CHANNEL_C_SELECTORS,
                         ids=[f"d1_{s:02x}" for s in CHANNEL_C_SELECTORS])
def test_every_d1_that_is_not_a_or_b_arms_channel_c(selector):
    """The last arm has no `cmp.b` of its own — it is what the second `bne` falls into — so every
    selector from 2 up arms the SAME channel, and none of them arms a fourth one."""
    _run_trigger(SHIPPED_CALL_IDS[0], CHANNELS - 1, f"a d1 of {selector:#04x}", entry_d1=selector)


def test_the_channel_c_sweep_brackets_the_last_channels_own_number():
    """A sweep that started above the channel count would let a clamp written one too high pass:
    the values that tell `< CHANNELS` from `<= CHANNELS` apart are exactly these two."""
    assert CHANNELS - 1 in CHANNEL_C_SELECTORS and CHANNELS in CHANNEL_C_SELECTORS


def test_the_effect_is_chosen_by_d0s_low_byte_alone():
    """`ext.w d0` throws away everything above the low byte before the index is built."""
    _run_trigger(SHIPPED_CALL_IDS[-1], CHANNEL_A, "a shipped id behind a poisoned d0",
                 entry_d0=0x12345600)


# --- ids past the table, and ids below it ---------------------------------------------------------
# $1a48a bounds-checks NOTHING, and that is not hypothetical: the pattern opcode $97 calls the stub
# without ever setting d1 (../names.txt), so the module can reach these arms with whatever the tick
# left behind. Each id is chosen for what its arithmetic reaches; the model computes the same
# address the instructions do rather than knowing where it lands.
OUT_OF_RANGE_IDS = (
    (SFX_IDS, "the first id past the table — its entry is descriptor 0's first two bytes"),
    (0x40, "well past it, still a positive index"),
    (0x7f, "the largest positive index the sign extension allows"),
    (0x80, "...and the smallest negative one, which reads 256 bytes BELOW the table"),
    (0xc0, "a negative index whose descriptor carries an out-of-range volume index"),
    (0xff, "index -1: the two bytes immediately before the table"),
)


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("effect_id,why", OUT_OF_RANGE_IDS,
                         ids=[f"id_{c[0]:02x}" for c in OUT_OF_RANGE_IDS])
def test_an_id_outside_the_table_indexes_it_anyway(effect_id, why, channel):
    _run_trigger(effect_id, channel, f"id {effect_id:#04x} on channel {channel} ({why})")


def test_the_out_of_range_sweep_reaches_both_sides_of_the_table():
    """A sweep of only positive overruns would leave the sign extension — the whole reason the id is
    `ext.w`ed rather than zero-extended — unpinned."""
    indices = [leaf.s8(effect_id) for effect_id, _why in OUT_OF_RANGE_IDS]
    assert any(index >= SFX_IDS for index in indices) and any(index < 0 for index in indices)


def test_the_out_of_range_sweep_reaches_an_out_of_range_volume_index():
    """The descriptors the shipped table names all carry a volume index in 0..9, so only a
    descriptor reached by an out-of-range id drives the SECOND table read outside its bounds."""
    image = harness.BASE_IMAGE
    reached = [image[_descriptor_of(image, effect_id) + DESC_VOLUME_INDEX]
               for effect_id, _why in OUT_OF_RANGE_IDS]
    assert any(index >= VOLUME_STREAMS for index in reached), reached


# Ids whose descriptor overlaps a block the arm goes on to WRITE. Not contrived — these are shipped
# table entries — and they are what says the copy reads its source before the mix block is rebuilt.
# Poisoning is off: the attribution pass inverts oracle-written bytes, and here those bytes are also
# the descriptor, so the re-run would be measuring a different effect rather than the same one.
SELF_OVERLAPPING_IDS = (0x81, 0x8d, 0xac)


@pytest.mark.parametrize("effect_id", SELF_OVERLAPPING_IDS,
                         ids=[f"id_{i:02x}" for i in SELF_OVERLAPPING_IDS])
def test_a_descriptor_inside_the_mix_block_is_read_before_it_is_rewritten(effect_id):
    _run_trigger(effect_id, CHANNEL_A, f"id {effect_id:#04x}, whose descriptor is the mix block",
                 poison=False)


def test_the_self_overlapping_ids_really_do_overlap():
    """The guard on the cases above: if the table stopped sending these ids into the mix block they
    would quietly become three more ordinary out-of-range cases."""
    image = harness.BASE_IMAGE
    mix = set(range(MIX_PERIOD, MIX_VOLUME + CHANNELS))
    for effect_id in SELF_OVERLAPPING_IDS:
        source = _descriptor_of(image, effect_id)
        assert mix & set(range(source, source + DESCRIPTOR_LEN)), (
            f"id {effect_id:#04x}'s descriptor at {source:#x} is not inside the mix block")


# --- a descriptor the copy overruns into ----------------------------------------------------------
# The ids above pin WHEN the descriptor is read. These pin the copy's DIRECTION, which nothing else
# can: `move.b (a0)+,(a1)+` walks UP, so a source sitting just below its destination and overlapping
# it re-reads bytes the copy has already written, and the record propagates. A block move — the
# `memmove` a port would reach for — leaves the pre-run bytes there instead, and every other case in
# this file agrees with both readings.
#
# Only channel C's state is reachable this way, and only from three of the 256 ids — which name two
# distinct descriptors, one of them twice, so these are those two: $1aaa5 (ids $8f and $93) and
# $1aaac (id $9f). The third id would be a third run of a case already made.
PROPAGATING_IDS = (
    (0x8f, "eleven bytes below it, so its last three bytes are copies of its first three"),
    (0x9f, "four below it, so ten of its fourteen bytes are the copy reading itself"),
)
PROPAGATING_CHANNEL = CHANNELS - 1

# The whole SFX state block, which is what a propagating case seeds: the descriptor is INSIDE it, so
# one keyed band covers both the bytes the copy reads and the bytes it reads back. Seeded because the
# shipped image leaves this block zero — and over zeros a propagated byte and a pre-run one are the
# same byte, so the case would pin nothing.
STATE_BLOCK_LEN = CHANNELS * STATE_LEN


def _propagating_case(effect_id, why):
    return f"id {effect_id:#04x} on channel C, whose descriptor sits {why}"


def _propagating_image(what):
    """The seeded image one of these cases runs on, and the pokes that make it."""
    pokes = {STATE: leaf.keyed_block(STATE, STATE_BLOCK_LEN, leaf.case_salt(what))}
    return _poked_image(pokes), pokes


@pytest.mark.parametrize("effect_id,why", PROPAGATING_IDS,
                         ids=[f"id_{c[0]:02x}" for c in PROPAGATING_IDS])
def test_a_descriptor_below_the_state_is_copied_forward_one_byte_at_a_time(effect_id, why):
    """Poisoning is off for the reason the mix-block cases give: the bytes the attribution pass
    would invert are also this copy's source."""
    what = _propagating_case(effect_id, why)
    image, pokes = _propagating_image(what)
    _run("snd_trigger_effect", _trigger(effect_id, PROPAGATING_CHANNEL), image, effect_id,
         PROPAGATING_CHANNEL, what, poison=False,
         regs={"d0": effect_id, "d1": PROPAGATING_CHANNEL, "_pokes": pokes})


@pytest.mark.parametrize("effect_id,why", PROPAGATING_IDS,
                         ids=[f"id_{c[0]:02x}" for c in PROPAGATING_IDS])
def test_the_propagating_ids_really_do_read_their_own_destination(effect_id, why):
    """The guard on the two cases above, and the reason they exist: with the seed each of them uses,
    the fourteen bytes a forward BYTE copy leaves are not the fourteen a block move would. If the
    table ever stopped sending these ids under the state — or the seed ever stopped separating the
    two readings — they would quietly become two more out-of-range cases."""
    what = _propagating_case(effect_id, why)
    image, _pokes = _propagating_image(what)
    source = _descriptor_of(image, effect_id)
    state = _channel_state(PROPAGATING_CHANNEL)
    assert source < state < source + DESCRIPTOR_LEN, (
        f"id {effect_id:#04x}'s descriptor at {source:#x} does not overlap the state at "
        f"{state:#x} from below")
    assert (_copied_record(image, source, state)
            != bytes(image[source:source + DESCRIPTOR_LEN])), (
        f"id {effect_id:#04x} propagates nothing under this seed, so a block move would pass it")


# --- a descriptor of the case's own ---------------------------------------------------------------
# Where a seeded descriptor goes: past the module's data but well inside the 32 KiB a table entry can
# reach, and clear of every block an arm writes. The table ENTRY that names it is seeded too, which
# is what makes these the pin on the pointer table's read — the shipped cases only ever exercise the
# entries the image already holds.
SEEDED_DESCRIPTOR = MODULE_BASE + 0x4000
SEEDED_ID = 7

# (mixer byte, volume index, why) — the two descriptor fields that STEER the arm, as against the
# eleven it only copies through.
SEEDED_CASES = (
    (0x00, 0, "the noise byte written, and the first volume stream"),
    (MIXER_NOISE_OFF, VOLUME_STREAMS - 1, "noise off, and the last volume stream"),
    (MIXER_NOISE_OFF - 1, 0, "every mixer bit but the one the `btst` reads"),
    (0xff, VOLUME_STREAMS, "noise off, and the first volume index PAST the table"),
    (0x00, 0x80, "a volume index the sign extension sends backwards off its table"),
)


def _seeded_record(mixer, volume_index, salt):
    record = bytearray(leaf.keyed_block(SEEDED_DESCRIPTOR, DESCRIPTOR_LEN, salt))
    record[DESC_MIXER_BITS] = mixer
    record[DESC_VOLUME_INDEX] = volume_index
    return bytes(record)


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("mixer,volume_index,why", SEEDED_CASES,
                         ids=[f"mixer_{c[0]:02x}_stream_{c[1]:02x}" for c in SEEDED_CASES])
def test_a_seeded_descriptor_is_reached_through_the_pointer_table(mixer, volume_index, why,
                                                                  channel):
    """The table entry is a3-relative and SIGN-EXTENDED, so seeding it is also what says an entry is
    a word OFFSET from the module base rather than an address."""
    what = (f"a seeded descriptor at {SEEDED_DESCRIPTOR:#x} on channel {channel} "
            f"(mixer {mixer:#04x}, volume index {volume_index:#04x} — {why})")
    pokes = {
        PTR_TABLE + SEEDED_ID * TABLE_ENTRY_LEN: word(SEEDED_DESCRIPTOR - MODULE_BASE),
        SEEDED_DESCRIPTOR: _seeded_record(mixer, volume_index, leaf.case_salt(what)),
    }
    _run("snd_trigger_effect", _trigger(SEEDED_ID, channel), _poked_image(pokes), SEEDED_ID,
         channel, what, regs={"d0": SEEDED_ID, "d1": channel, "_pokes": pokes})


def test_the_seeded_descriptor_is_clear_of_every_block_an_arm_writes():
    """Otherwise a seeded case would be measuring the overlap the three ids above measure."""
    seeded = set(range(SEEDED_DESCRIPTOR, SEEDED_DESCRIPTOR + DESCRIPTOR_LEN))
    for channel in range(CHANNELS):
        for addr, length in write_bands(expected_writes(harness.BASE_IMAGE, 0, channel)):
            assert not seeded & set(range(addr, addr + length))


def test_the_seeded_cases_reach_both_arms_of_the_noise_test():
    noise_off = [mixer & MIXER_NOISE_OFF for mixer, _index, _why in SEEDED_CASES]
    assert any(noise_off) and not all(noise_off)


# --- $17b14: the stub -----------------------------------------------------------------------------
# The stub table is the module's whole interface, so its SHAPE is pinned as well as the one entry
# reconstructed here.

@pytest.mark.parametrize("offset,called,save,restore", STUB_TABLE,
                         ids=[f"plus_{stub[0]}" for stub in STUB_TABLE])
def test_the_stub_table_has_the_shape_the_module_map_claims(offset, called, save, restore):
    """Each stub's `bsr` displacement is built from the two addresses ../names.txt gives, so a map
    entry aimed at the wrong routine fails on the bytes."""
    at = STUB_TABLE_BASE + offset
    expected = _stub(offset, called, save, restore)
    actual = bytes(harness.BASE_IMAGE[at:at + len(expected)])
    assert actual == expected, (
        f"stub +{offset} at {at:#x} is {actual.hex()}, not the {expected.hex()} the module map "
        f"claims for {called}")


def test_the_reconstructed_stub_is_the_tables_trigger_entry():
    """`lea $17adc.l,a1 / jsr 56(a1)` is how $bbca and the other call sites reach the trigger, so
    the reconstruction has to sit at exactly that offset and nowhere else."""
    assert leaf.entry_of("snd_call_trigger_effect") == STUB_TABLE_BASE + STUB_TRIGGER_OFFSET


# Every register the oracle reports, seeded with a value of its own — so a stub that restored one
# register from another's slot is caught as well as one that restored nothing.
PRESERVED_ENTRY_REGS = {name: 0x5a000000 + index * 0x111
                        for index, name in enumerate(emu.REPORTED_REGS)}
LOW_BYTE_MASK = 0xff


def test_the_stub_restores_every_register_it_saved():
    """The `movem` pair is the whole point of $17b14 and memory cannot show it, so this is the one
    case in the suite that reads the oracle's registers rather than the image. It runs a REAL effect
    at the same time: a stub that preserved everything by never calling the trigger would pass a
    register compare on its own."""
    effect_id, channel = SHIPPED_CALL_IDS[0], CHANNEL_A
    what = f"the stub calling sfx {effect_id} with every register live"
    regs = dict(PRESERVED_ENTRY_REGS)
    regs["d0"] = (regs["d0"] & ~LOW_BYTE_MASK) | effect_id
    regs["d1"] = (regs["d1"] & ~LOW_BYTE_MASK) | channel
    info = _run("snd_call_trigger_effect", _stub_call(regs["d0"], regs["d1"]), harness.BASE_IMAGE,
                effect_id, channel, what, regs=dict(regs), insns=STUB_INSN_CAP)
    for name, entered in regs.items():
        assert info["regs"][name] == entered, (
            f"{what}: the stub left {name}={info['regs'][name]:#010x}, not the {entered:#010x} it "
            f"was entered with")


def test_the_preservation_case_gives_every_register_a_distinct_value():
    """A seed that repeated a value would let a stub restore one register from another's slot and
    still pass the compare above."""
    assert len(set(PRESERVED_ENTRY_REGS.values())) == len(PRESERVED_ENTRY_REGS)


@pytest.mark.parametrize("effect_id", SHIPPED_CALL_IDS)
def test_the_stub_lands_the_effects_writes(effect_id):
    """The other half: the registers come back, and the memory the trigger writes still lands."""
    _run("snd_call_trigger_effect", _stub_call(effect_id, CHANNEL_A), harness.BASE_IMAGE,
         effect_id, CHANNEL_A, f"sfx {effect_id} through the stub",
         regs={"d0": effect_id, "d1": CHANNEL_A}, insns=STUB_INSN_CAP)


# --- the stop chain: $17f24 -> $1aaea -> $17f30 ---------------------------------------------------
# Three routines, two of them stub-table entries and the third the tail both `bra.w` into. Each is
# run on its own, and each case states the module state THAT entrant is entitled to write — which is
# what says the engine flag belongs to the outer one and the four shadow bytes to the middle one.
#
# THE MODELS BELOW ARE EXPORTED. test_actor.py's $6bb8 cases reach this chain through stub +28, so
# they need the same three statements; two copies of them could disagree while both batteries stayed
# green, which is the reason test_stage.py imports test_hud.py.

PSG_WRITE = harness.OS_PSG_EVENT_WRITE
PSG_READ = harness.OS_PSG_EVENT_READ
PSG_NREGS = harness.OS_PSG_NREGS


def silence_events(mixer_on_entry):
    """The ordered access ledger `snd_psg_silence` leaves: read the mixer back, write it merged, then
    three volume writes. The READ entry is what separates this from a reconstruction that read the
    WRONG register — such a run's writes, and the file it leaves, can be a correct one's exactly."""
    silenced = mixer_on_entry | PSG_MIXER_ALL_OFF
    return ([(PSG_READ, PSG_REG_MIXER, mixer_on_entry), (PSG_WRITE, PSG_REG_MIXER, silenced)]
            + [(PSG_WRITE, reg, PSG_VOLUME_SILENT) for reg in SILENCED_VOLUMES])


def silence_file(psg_seed):
    """...and the register file plus its known mask afterwards, as (bytes, mask).

    Built from the SEED rather than from the ledger, so it is a second statement of the same run and
    not a restatement of the first: a register the case declared and the routine never touches has to
    come back holding what it was given.
    """
    values = bytearray(PSG_NREGS)
    known = 0
    for reg, value in psg_seed.items():
        values[reg] = value
        known |= 1 << reg
    values[PSG_REG_MIXER] = psg_seed[PSG_REG_MIXER] | PSG_MIXER_ALL_OFF
    for reg in SILENCED_VOLUMES:
        values[reg] = PSG_VOLUME_SILENT
        known |= 1 << reg
    return bytes(values), known | (1 << PSG_REG_MIXER)


# What each entrant of the chain writes to the IMAGE, cumulatively: the tail writes nothing at all
# (its whole output is the ledger), the middle one clears the SFX flags and rewrites the module's own
# shadow of the four registers it is about to silence, and the outer one adds the engine flag.
SILENCE_WRITES = {}
STOP_ALL_WRITES = {
    **SILENCE_WRITES,
    ACTIVE_FLAGS: bytes(ACTIVE_FLAGS_LEN),
    PSG_SHADOW + PSG_REG_MIXER: bytes([PSG_MIXER_ALL_OFF]),
    PSG_SHADOW + PSG_REG_VOLUME_A: bytes([PSG_VOLUME_SILENT]),
    PSG_SHADOW + PSG_REG_VOLUME_B: bytes([PSG_VOLUME_SILENT]),
    PSG_SHADOW + PSG_REG_VOLUME_C: bytes([PSG_VOLUME_SILENT]),
}
STOP_WRITES = {**STOP_ALL_WRITES, ENGINE_ENABLED: bytes([ENGINE_DISABLED])}

STOP_CHAIN = {
    "snd_psg_silence": (SILENCE_WRITES, SILENCE_INSN_CAP),
    "snd_stop_all_sfx": (STOP_ALL_WRITES, STOP_ALL_INSN_CAP),
    "snd_stop": (STOP_WRITES, STOP_INSN_CAP),
}
_STOP_CHAIN_GLUE = {
    "snd_psg_silence": _silence,
    "snd_stop_all_sfx": _stop_all,
    "snd_stop": _stop,
}

# The bytes ../names.txt gives each routine, stated so the entry pins cannot pass on a body of any
# other length — and so that the three have to tile the addresses the module map claims.
STOP_CHAIN_BODY_BYTES = {"snd_stop": 12, "snd_psg_silence": 82, "snd_stop_all_sfx": 26}


def assert_psg_state(info, psg_seed, what):
    """...and the stop chain's own view of it, whose two surfaces are computed from the SEED."""
    values, known = silence_file(psg_seed)
    assert_psg_surfaces(info, silence_events(psg_seed[PSG_REG_MIXER]), values, known, what)


def run_stop_chain(name, psg_seed, what, regs=None):
    """One stop-chain differential: the image diff and the write set leaf.run makes, this routine's
    own written bytes stated by value, and both PSG surfaces."""
    written, cap = STOP_CHAIN[name]
    info = leaf.run(name, _STOP_CHAIN_GLUE[name], write_bands(written), what,
                    regs=dict(regs or {}), max_insns=cap, psg_seed=psg_seed)
    assert_written(info, written, what)
    assert_psg_state(info, psg_seed, what)
    return info


# Every mixer byte a case declares the chip held. The first is what TOS leaves (both ports OUTPUT),
# and the reason bits 6-7 are the point: `ori.b #$3f` must carry them through untouched.
MIXER_SEEDS = (
    (0xc0, "both port-direction bits set — what TOS leaves, and what the floppy depends on"),
    (0x40, "port A output, port B input"),
    (0x80, "...and the other way round, so the two bits are told apart"),
    (0x00, "no bits at all: exactly the value a FABRICATED read would have invented"),
    (0xff, "every bit, so the `ori` has nothing left to set"),
    (PSG_MIXER_ALL_OFF, "already silent, with both direction bits clear"),
    (0x9c, "port B only, three of the six enables clear — an ordinary mid-tune mixer"),
)
MIXER_DIRECTION_BITS = 0xc0     # bits 6-7: the port A/B I/O direction lines the `ori` preserves


@pytest.mark.parametrize("name", sorted(STOP_CHAIN))
@pytest.mark.parametrize("mixer,why", MIXER_SEEDS, ids=[f"mixer_{s[0]:02x}" for s in MIXER_SEEDS])
def test_the_stop_chain_silences_the_chip_from_the_mixer_the_case_declares(name, mixer, why):
    run_stop_chain(name, {PSG_REG_MIXER: mixer}, f"{name} over a mixer of {mixer:#04x} ({why})")


def test_the_mixer_seeds_reach_all_four_states_of_the_preserved_bits():
    """The guard on the sweep above: bits 6-7 are the two the `ori` must NOT touch, so a sweep that
    never varied them would agree with a port that cleared them in three cases out of four."""
    seen = {mixer & MIXER_DIRECTION_BITS for mixer, _why in MIXER_SEEDS}
    assert seen == {0x00, 0x40, 0x80, 0xc0}, f"the sweep only reaches {sorted(hex(s) for s in seen)}"


@pytest.mark.parametrize("mixer,why", MIXER_SEEDS, ids=[f"mixer_{s[0]:02x}" for s in MIXER_SEEDS])
def test_the_mixer_write_keeps_the_port_direction_bits_it_read_back(mixer, why):
    """Stated as its own claim rather than left inside the ledger comparison, because it is the one
    thing the seeded read model exists for: a port that ignored the read-back writes $3f, port A
    flips to input, and the floppy drive-select lines float."""
    what = f"the preserved bits of a mixer of {mixer:#04x} ({why})"
    info = run_stop_chain("snd_psg_silence", {PSG_REG_MIXER: mixer}, what)
    written = [value for kind, reg, value in info["regs"]["psg_events"]
               if kind == PSG_WRITE and reg == PSG_REG_MIXER]
    assert written == [mixer | PSG_MIXER_ALL_OFF], f"{what}: the mixer was written {written}"
    assert written[0] & MIXER_DIRECTION_BITS == mixer & MIXER_DIRECTION_BITS, (
        f"{what}: the direction bits came out {written[0] & MIXER_DIRECTION_BITS:#04x}")


# A register the routine never touches, declared alongside the mixer. Register 14 is PSG port A —
# the floppy drive/side select — which is exactly what the preserved direction bits are ABOUT.
UNTOUCHED_SEED = {PSG_REG_MIXER: 0xc0, 14: 0x07, 0: 0x5a}


def test_a_register_the_chain_never_names_comes_back_holding_what_the_case_declared():
    """The other half of the ledger comparison: the chain writes four registers and only four, so a
    port that silenced the chip by rewriting the whole file would leave these two changed."""
    info = run_stop_chain("snd_stop", UNTOUCHED_SEED, "a seed declaring two registers besides the "
                                                      "mixer")
    file_after = info["regs"]["psg_file"]
    for reg, value in UNTOUCHED_SEED.items():
        if reg == PSG_REG_MIXER:
            continue
        assert file_after[reg] == value, (
            f"register {reg} ended {file_after[reg]:#04x}, not the {value:#04x} the case declared")


def test_a_case_that_declares_nothing_is_refused_rather_than_served_a_fabricated_mixer():
    """THE GUARD EVERY CASE ABOVE RESTS ON. Without the seed the oracle has no correct byte for the
    read-back and must refuse the run — if it invented one instead, a port that ignored the
    read-back would agree with it and this whole battery would be measuring `shim.c`."""
    with pytest.raises(RuntimeError, match=r"psg_seed=\{7: <byte>\}"):
        leaf.run("snd_psg_silence", _silence, [], "snd_psg_silence with nothing declared",
                 max_insns=SILENCE_INSN_CAP)


# The registers the tail leaves behind. d1 takes the read-back through a BYTE move and a BYTE `ori`,
# so its upper three bytes are the caller's; d2 takes the SR, a WORD move, so its high half is too.
SILENCE_ENTRY_REGS = {"d1": 0x11223344, "d2": 0x55667788}
SILENCE_MIXER = 0xc0


def test_the_tail_leaves_the_read_back_in_d1_as_a_byte_and_the_saved_sr_in_d2_as_a_word():
    """Neither register is reproduced — the C returns nothing and has no status register — so this
    asserts the ORACLE's, the way src/actor.c's passes do with their walked-out cursors. It is what
    says `move.b`/`ori.b` and `move sr` are byte and word operations rather than longword ones."""
    what = "the tail's outgoing registers"
    info = run_stop_chain("snd_psg_silence", {PSG_REG_MIXER: SILENCE_MIXER}, what,
                          regs=dict(SILENCE_ENTRY_REGS))
    merged = SILENCE_MIXER | PSG_MIXER_ALL_OFF
    assert info["regs"]["d1"] == (SILENCE_ENTRY_REGS["d1"] & ~BYTE_MASK) | merged, (
        f"{what}: d1 is {info['regs']['d1']:#010x} — the read-back is a BYTE move")
    assert info["regs"]["d2"] == leaf.set_low_word(SILENCE_ENTRY_REGS["d2"], SUPERVISOR_SR), (
        f"{what}: d2 is {info['regs']['d2']:#010x}, not the entry SR in its low word")


def test_the_stop_chain_bodies_are_the_lengths_the_module_map_claims():
    """Without this the entry pins would pass on a body of any length. The three also have to TILE:
    $17f24's twelve bytes end where the tail begins, and the tail ends where snd_resume does."""
    for name, expected in sorted(STOP_CHAIN_BODY_BYTES.items()):
        assert len(ENTRY_BYTES[name]) == expected, (
            f"{name} assembles to {len(ENTRY_BYTES[name])} bytes, not the {expected} claimed")
    assert leaf.entry_of("snd_stop") + STOP_CHAIN_BODY_BYTES["snd_stop"] \
        == leaf.entry_of("snd_psg_silence"), "$17f24's twelve bytes must abut the tail"
    assert leaf.entry_of("snd_psg_silence") + STOP_CHAIN_BODY_BYTES["snd_psg_silence"] \
        == leaf.entry_of("snd_resume"), "...and the tail must end where snd_resume begins"


# That the two are the stub table's +28 and +70 needs no case of its own: the shape test above builds
# each stub's `bsr` displacement from leaf.entry_of(called), so a reconstruction sitting anywhere
# else fails there, on the bytes at the stub's own address.


# --- the tick tier: $1aaca, $1a5da and $18208 -----------------------------------------------------
#
# THE .PRG SHIPS THESE BANDS DIRTY. $17bc6..$17c71, $18352..$1836a, $1aa7c..$1aac9 and
# $1aae6..$1aae9 hold residue from a run at another load base (../notes/sound_module_recon.md §6),
# so NO case below reads an initial value out of the image: every one of them either seeds the band
# with `leaf.keyed_block` or fills it through `expected_writes`, the trigger's own model, which is
# what a real arming leaves there. The PRNG is seeded even where its value looks irrelevant, because
# it steps on EVERY tick and is never reset — a case comparing two ticks that trusted the image
# would be comparing against a state some earlier case had already advanced.

BUS_ADDR_MASK = wb("BUS_ADDR_MASK")
WORD_MASK = leaf.WORD_MASK
SIGN_BIT_B = 0x80
PSG_SHADOW_LEN = PSG_REG_VOLUME_C + 1           # registers 0..10, indexed BY register number
MIX_BLOCK_LEN = (MIX_VOLUME + CHANNELS) - MIX_PERIOD
SFX_STATE_BLOCK_LEN = CHANNELS * STATE_LEN


class _Memory:
    """A mutable copy of the image that RECORDS every byte a model stores.

    The write set a case allows and the values it compares both come out of `written`, exactly as
    they come out of `expected_writes` for the trigger — one entry per BYTE, so a word store followed
    by a byte store into it leaves the byte's own value and not a stale halfword.

    Reads go through the 68000's 24-bit address bus and then a bounds check, because these routines
    follow POINTERS OUT OF THE DIRTY IMAGE — an envelope cursor, an arpeggio cursor, a volume-stream
    cursor. src/sound.c's `module_byte` is the same two lines; the shim answers a read past the image
    with zeros and both sides reproduce that.
    """

    def __init__(self, image):
        self.mem = bytearray(image)
        self.written = {}

    def byte(self, at, value):
        self.mem[at] = value & BYTE_MASK
        self.written[at] = bytes([value & BYTE_MASK])

    def word(self, at, value):
        self.byte(at, value >> 8)
        self.byte(at + 1, value)

    def long(self, at, value):
        for index in range(LONGWORD_LEN):
            self.byte(at + index, value >> (8 * (LONGWORD_LEN - 1 - index)))

    def set_bits(self, at, mask):
        """`bset #n,<ea>` — the read-modify-write the models say four times over the flags byte.
        Named for _Memory.decrement's reason: spelling the address once per statement is what stops a
        paste reading one field and writing its NEIGHBOUR."""
        self.byte(at, self.read(at) | mask)

    def decrement(self, at):
        """`subq.b #1,<ea>` — the store, and the value the `bne`/`bcc` after it reads. Spelt here
        because the models say it five times and the reconstruction says it as `image[X]--`; naming
        the address once per statement is what stops a paste re-reading its NEIGHBOUR."""
        self.byte(at, self.read(at) - 1)
        return self.read(at)

    def read(self, at):
        return self.mem[at]

    def read_word(self, at):
        return int.from_bytes(self.mem[at:at + WORD_LEN], "big")

    def read_long(self, at):
        return int.from_bytes(self.mem[at:at + LONGWORD_LEN], "big")

    def read_through_pointer(self, at):
        at &= BUS_ADDR_MASK
        return self.mem[at] if at < len(self.mem) else 0


# --- $1aaca: the module's own PRNG ----------------------------------------------------------------

PRNG_INSNS = 8                                  # the body's own instruction count
PRNG_INSN_CAP = PRNG_INSNS + leaf.RUNNER_SENTINEL_INSN
PRNG_BODY_BYTES = 28
_prng = leaf.image_glue("snd_prng_step", ctypes.c_uint8)


def _model_prng(memory):
    """The state $1aaca leaves, and the byte it returns in d0's low byte.

    The two `roxl.w`s are spelt as the loop the module is — LOW word first, so the bit that leaves
    ITS top is the X the high word's takes. Written this way rather than as one 33-bit rotate
    because the order is the whole mechanism, and a model that composed them the other way round
    would still be a 32-bit shift.
    """
    taps = ((memory.read(PRNG_STATE) & PRNG_TAP_MASK) + PRNG_TAP_BIAS) & BYTE_MASK
    extend = (taps >> PRNG_FEEDBACK_BIT) & 1
    for at in (PRNG_STATE + PRNG_LOW_WORD, PRNG_STATE):
        value = memory.read_word(at)
        memory.word(at, ((value << 1) | extend) & WORD_MASK)
        extend = value >> 15
    return memory.read(PRNG_STATE)


# Every state a case declares the PRNG held. The four tap combinations are the point: bit 3 and bit 6
# of the TOP byte, whose XOR is the bit fed back in — so a port that ORed them, or read one bit
# alone, agrees with three of these four and fails the fourth.
PRNG_SEEDS = (
    (0x00000000, "neither tap: the feedback bit is 0 and the state stays 0"),
    (0x08000000, "bit 3 alone — the bias is what carries it up into bit 6"),
    (0x40000000, "bit 6 alone"),
    (0x48000000, "BOTH taps, whose XOR is 0 again: the case that separates the XOR from an OR"),
    (0x00008000, "the LOW word's top bit alone, which only the second `roxl` can move up"),
    (0x80000000, "the top bit, which leaves the machine — the second `roxl`'s carry out is dropped"),
    (0xffffffff, "every bit, so both word-to-word carries have something to carry"),
    (0xb8b94212, "the four bytes the shipped image happens to hold, SEEDED rather than trusted"),
)
PRNG_ENTRY_D0 = 0x5a5a5a5a      # the bits above the byte the `move.b` writes


def _run_prng(state, what):
    """One PRNG differential, against a state the case declares.

    A3 IS AN ENTRY REGISTER HERE. Unlike every routine the module is reached from outside through,
    $1aaca does NOT open with `lea $1738c(pc),a3` — it inherits the base its one caller left there
    (the whole-body pin above is what says the `lea` is absent), so a case that did not seed a3 would
    run the two `roxl.w`s against a base of zero. The differential found exactly that.
    """
    pokes = {PRNG_STATE: state.to_bytes(PRNG_STATE_LEN, "big")}
    memory = _Memory(_poked_image(pokes))
    returned = _model_prng(memory)
    info = leaf.run("snd_prng_step", _prng, write_bands(memory.written), what,
                    regs={"a3": MODULE_BASE, "d0": PRNG_ENTRY_D0, "_pokes": pokes},
                    max_insns=PRNG_INSN_CAP)
    assert_written(info, memory.written, what)
    assert info["ret"] == returned, (
        f"{what}: the reconstruction returned {info['ret']:#04x}, not the {returned:#04x} the "
        f"stepped state's top byte gives")
    assert info["regs"]["d0"] == (PRNG_ENTRY_D0 & ~BYTE_MASK) | returned, (
        f"{what}: the oracle left d0 = {info['regs']['d0']:#010x} — the final `move.b` writes ONE "
        f"byte, so the caller's upper three come back")
    return memory


@pytest.mark.parametrize("state,why", PRNG_SEEDS, ids=[f"state_{s[0]:08x}" for s in PRNG_SEEDS])
def test_the_prng_shifts_its_whole_state_left_through_the_feedback_bit(state, why):
    _run_prng(state, f"a PRNG state of {state:#010x} ({why})")


def test_the_prng_seeds_reach_all_four_states_of_the_two_taps():
    """The guard on the sweep above. Without all four, a feedback bit read as bit 3 alone, as bit 6
    alone or as their OR would each pass — they differ from the XOR on exactly one combination."""
    seen = {(state >> 24) & PRNG_TAP_MASK for state, _why in PRNG_SEEDS}
    assert seen == {0x00, 0x08, 0x40, 0x48}, f"the sweep only reaches {sorted(hex(s) for s in seen)}"


def test_the_prng_seeds_produce_both_feedback_bits():
    """...and the other half of it: the four combinations have to give BOTH values of the bit, or the
    sweep would be pinning the shift and not the feedback."""
    fed = {(((state >> 24) & PRNG_TAP_MASK) + PRNG_TAP_BIAS) >> PRNG_FEEDBACK_BIT & 1
           for state, _why in PRNG_SEEDS}
    assert fed == {0, 1}


PRNG_CHAIN_TICKS = 4


def test_the_prng_is_history_dependent_across_steps():
    """FOUR steps in a row, each seeded from the last one's own result rather than from the image.

    This is the case that says the state is carried: a port that recomputed it from the image every
    time would agree with the first step and diverge from the second. It is also why every other
    case here declares $1aae6 — the step runs on EVERY tick and snd_play_song does not reset it.
    """
    state = PRNG_SEEDS[-1][0]
    seen = []
    for tick in range(PRNG_CHAIN_TICKS):
        memory = _run_prng(state, f"PRNG step {tick} of a chain from {PRNG_SEEDS[-1][0]:#010x}")
        state = memory.read_long(PRNG_STATE)
        seen.append(state)
    assert len(set(seen)) == PRNG_CHAIN_TICKS, f"the chain repeated itself: {[hex(s) for s in seen]}"


def test_the_prng_state_begins_where_its_code_ends():
    """Self-bounding, the way the two SFX tables are: the four mutable bytes sit immediately past the
    last instruction, so the body's length and the state's address prove each other."""
    assert leaf.entry_of("snd_prng_step") + PRNG_BODY_BYTES == PRNG_STATE
    assert len(ENTRY_BYTES["snd_prng_step"]) == PRNG_BODY_BYTES


# --- $1a5da: the SFX tick -------------------------------------------------------------------------

SFX_ARM_BODY_BYTES = 186
SFX_ENTRY_BODY_BYTES = 40       # the dispatch above the arms, without its shared `rts`
SFX_TICK_BODY_BYTES = len(RTS) + SFX_ENTRY_BODY_BYTES + CHANNELS * SFX_ARM_BODY_BYTES
# The cap is each body's own instruction COUNT, which bounds any path through it: the entry is 14
# instructions (its shared `rts` included), the PRNG 8 and each arm 55.
SFX_ENTRY_INSNS = 14
SFX_ARM_INSNS = 55
SFX_TICK_INSN_CAP = (SFX_ENTRY_INSNS + PRNG_INSNS + CHANNELS * SFX_ARM_INSNS
                     + leaf.RUNNER_SENTINEL_INSN)
_sfx_tick = leaf.image_glue("snd_sfx_tick")


def _model_sfx_arm(memory, channel):
    """One arm of $1a5da, transcribed from the original's own order.

    Its six base-plus-stride blocks are computed here from `channel` exactly as src/sound.c computes
    them, which is deliberate: what the two statements are being checked against each other for is
    the SEQUENCE of stores, and the strides are pinned by the entry pin above on the bytes.
    """
    state = _channel_state(channel)
    mix_period = _mix_period(channel)

    # $1a602 — over only when BOTH the duration and the sustain flag have run out.
    if memory.read(state + DESC_DURATION) == 0 and memory.read(state + DESC_SUSTAIN) == 0:
        memory.byte(ACTIVE_FLAGS + channel, SFX_INACTIVE)
        memory.byte(PSG_SHADOW + PSG_REG_VOLUME_A + channel, PSG_VOLUME_SILENT)
        return
    memory.decrement(state + DESC_DURATION)

    if memory.read(state + STATE_PERIOD_COUNT) == 0:
        if memory.read(state + DESC_SUSTAIN) == 0 and memory.read(state + DESC_SLIDE_COUNT) == 0:
            _model_sfx_volume(memory, state, channel)       # $1a62c: straight to the stream
            return
        # $1a62e — the SAME delta byte into both halves, `add.b` then `addx.b`.
        memory.decrement(state + DESC_SLIDE_COUNT)
        memory.byte(state + STATE_PERIOD_COUNT, memory.read(state + DESC_PERIOD_STEP))
        delta = memory.read(state + DESC_USE_PRNG)
        if delta != 0:
            delta = memory.read(PRNG_STATE + channel)
        low = memory.read(state + DESC_TONE_PERIOD + MIX_PERIOD_LOW) + delta
        memory.byte(mix_period + MIX_PERIOD_LOW, low)
        memory.byte(mix_period, memory.read(state + DESC_TONE_PERIOD) + delta + (low >> 8))
    memory.decrement(state + STATE_PERIOD_COUNT)

    # $1a65a — a reload of 0 disables the counter and the slide then runs every tick.
    second_reload = memory.read(state + DESC_SECOND_RELOAD)
    slide_due = True
    if second_reload != 0:
        slide_due = memory.decrement(state + STATE_SECOND_COUNT) == 0
        if slide_due:
            memory.byte(state + STATE_SECOND_COUNT, second_reload)
    if slide_due:
        direction = memory.read(state + DESC_SLIDE_DIRECTION)
        if direction != 0:
            amount = memory.read_word(state + DESC_SLIDE_AMOUNT)
            period = memory.read_word(mix_period)
            memory.word(mix_period, (period + amount if direction & SIGN_BIT_B
                                     else period - amount) & WORD_MASK)

    if not memory.read(state + DESC_MIXER_BITS) & MIXER_NOISE_OFF:
        memory.byte(MIX_NOISE, memory.read(mix_period + MIX_PERIOD_LOW))

    _model_sfx_volume(memory, state, channel)


def _model_sfx_volume(memory, state, channel):
    """$1a692. Reached from TWO places — the arm's tail and the early jump at $1a62c — which is why
    it is a function here as it is a label there."""
    if memory.decrement(state + STATE_VOLUME_COUNT) != 0:
        return
    memory.byte(state + STATE_VOLUME_COUNT, memory.read(state + DESC_VOLUME_STEP))

    cursor = memory.read_long(state + STATE_STREAM_CURSOR)
    value = memory.read_through_pointer(cursor)
    cursor = (cursor + 1) & LONGWORD_MASK
    if value & SIGN_BIT_B:
        if value != VOLUME_STREAM_LOOP:
            return                                          # a HOLD writes nothing at all
        cursor = memory.read_long(state + STATE_STREAM_BASE)
        value = memory.read_through_pointer(cursor)
        cursor = (cursor + 1) & LONGWORD_MASK
    memory.long(state + STATE_STREAM_CURSOR, cursor)
    memory.byte(MIX_VOLUME + channel, value)


def _model_sfx_tick_into(memory):
    """The whole of $1a5da: the PRNG step, then one arm per armed channel."""
    _model_prng(memory)
    if memory.read(ACTIVE_FLAGS + CHANNEL_A) & SIGN_BIT_B:
        return                                              # `bmi` — B and C do not run either
    for channel in range(CHANNELS):
        if memory.read(ACTIVE_FLAGS + channel) != 0:
            _model_sfx_arm(memory, channel)


def _model_sfx_tick(image):
    """...entered on its own, which is how this battery runs it and how the TICK does not: the tick
    body's model steps the same memory it is already holding."""
    memory = _Memory(image)
    _model_sfx_tick_into(memory)
    return memory


def _mutable_seed(salt):
    """Every mutable band the tick reads, filled with ADDRESS-KEYED bytes.

    All four of them ship dirty, so a case that left one alone would be running on a previous run's
    leftovers; keyed on the address so a walk with the wrong stride lands on a byte that is wrong for
    where it was written rather than on a plausible zero.
    """
    return {
        STATE: leaf.keyed_block(STATE, SFX_STATE_BLOCK_LEN, salt),
        MIX_PERIOD: leaf.keyed_block(MIX_PERIOD, MIX_BLOCK_LEN, salt),
        PSG_SHADOW: leaf.keyed_block(PSG_SHADOW, PSG_SHADOW_LEN, salt),
    }


def _armed_pokes(effect_id, channels, prng, salt, flags=None, overrides=None):
    """The module state a case runs the tick on: a seeded mutable band, then exactly what
    `snd_trigger_effect` leaves for ``effect_id`` on each of ``channels`` — the trigger's own model,
    already proven against the original by the cases above — then the active flags and the PRNG.

    ``overrides`` is a poke dict applied last, for the cases that need a field the shipped
    descriptors do not reach (a volume cursor parked on a $80, a duration of zero).
    """
    pokes = _mutable_seed(salt)
    for channel in channels:
        pokes = overlay(pokes, expected_writes(_poked_image(pokes), effect_id, channel))
    armed = bytearray(ACTIVE_FLAGS_LEN)
    for channel in channels:
        armed[channel] = ACTIVE
    return overlay(pokes,
                    {ACTIVE_FLAGS: bytes(flags if flags is not None else armed),
                     PRNG_STATE: prng.to_bytes(PRNG_STATE_LEN, "big")},
                    overrides or {})


def _run_tick_sequence(name, glue, model, cap, what, pokes, ticks, regs=None, psg_seed=None,
                       hw_seed=None, hw_events=()):
    """``ticks`` consecutive differentials of one per-VBL routine, each entered on the state the last
    one left. All three routines this file ticks go through here — $1a5da, $17ca0 and $17c74.

    A single tick reaches almost nothing — a freshly armed effect spends its first ticks counting
    down — so the sequence is what walks the volume stream, empties the duration and reaches the
    end-of-effect arm from the game's own descriptors. Each tick is its own whole-image differential;
    the state is carried forward through the POKES, so nothing is taken on trust from the run before.

    THE CHIP IS NOT CARRIED FORWARD, AND THAT IS THE HARNESS'S RULE RATHER THAN A SHORTCUT. The image
    carries because the pokes do; the YM2149's register file does not, because ``differential()``
    calls ``g_psg_reset(seed, known)`` at the head of EVERY run on both sides. There is no way to
    hand the oracle a chip that tick N left — a model that carried its own file forward would expect
    a read-back the oracle is never served, and the case would redden on the harness rather than on
    the game. So a multi-tick sequence here is N runs from one declared chip state and NOT a
    continuous chip timeline: what carries between ticks is memory, and what the mixer merge sees at
    each tick is the seed. Stated because it bounds what these cases can claim.

    ...AND NEITHER IS THE MACHINE, for the same reason and with the same shape: ``hw_seed`` declares
    what $fffa01 and $ff820a held on ENTRY to each run, re-installed per run on both sides, so a
    sequence is N ticks of ONE declared machine rather than a machine that could change under the
    replayer. Which is what a real frame is, so the limit costs nothing here.

    ``hw_events`` is the ordered ``(address, byte)`` stream that declaration IMPLIES, and a case
    passing ``hw_seed`` states it. ``harness.differential`` compares the two sides' streams to each
    other; nothing there says the oracle read anything at all, so without this a case whose entry
    point never reached a `btst` would compare two empty streams and pass.

    ``model(memory, psg_seed)`` steps the model in place and returns the off-image surfaces to
    compare, or None for a routine that touches no port.
    """
    info = None
    for tick in range(ticks):
        label = f"{what}, tick {tick}" if ticks > 1 else what
        memory = _Memory(_poked_image(pokes))
        surfaces = model(memory, psg_seed)
        info = leaf.run(name, glue, write_bands(memory.written), label,
                        regs={**(regs or {}), "_pokes": pokes}, max_insns=cap, psg_seed=psg_seed,
                        hw_seed=hw_seed)
        assert_written(info, memory.written, label)
        if surfaces is not None:
            assert_psg_surfaces(info, surfaces.events, surfaces.values, surfaces.known, label)
        if hw_seed is not None:
            assert info["regs"]["hw_events"] == list(hw_events), (
                f"{label}: the oracle's modeled hardware reads were "
                f"{info['regs']['hw_events']}, not the {list(hw_events)} this case's declaration "
                f"implies — that stream is the whole of what a hardware branch leaves behind")
        pokes = overlay(pokes, memory.written)
    return pokes, info


def _sfx_tick_model(memory, _psg_seed):
    """$1a5da drives no port, so it has no off-image surfaces to compare."""
    _model_sfx_tick_into(memory)
    return None


def _run_ticks(what, pokes, ticks):
    return _run_tick_sequence("snd_sfx_tick", _sfx_tick, _sfx_tick_model, SFX_TICK_INSN_CAP,
                              what, pokes, ticks)[0]


# Every mutable band an SFX-tick case must cover, as (base, length). Stated so the guard below can
# say WHICH band a seeding bug left on the shipped residue.
SFX_SEEDED_BANDS = ((STATE, SFX_STATE_BLOCK_LEN), (MIX_PERIOD, MIX_BLOCK_LEN),
                    (PSG_SHADOW, PSG_SHADOW_LEN), (ACTIVE_FLAGS, ACTIVE_FLAGS_LEN),
                    (PRNG_STATE, PRNG_STATE_LEN))


def test_a_tick_case_seeds_every_mutable_byte_its_arms_read():
    """THE GUARD ON `_overlay`, and on this section's own opening claim.

    Before the review pass the seeding merged key by key, so the trigger's fourteen-byte state write
    replaced the seventy-eight-byte state seed and its two-byte mix-period write replaced the
    eleven-byte mix seed: most of both bands ran on the shipped residue and every case stayed green,
    because the two cores read the same residue. Nothing but this says otherwise.
    """
    for channels in ((CHANNEL_A,), tuple(range(CHANNELS))):
        pokes = _armed_pokes(SHIPPED_CALL_IDS[0], channels, SFX_TICK_SEED, 0)
        assert_bands_are_seeded(pokes, SFX_SEEDED_BANDS, f"an SFX case arming {channels}")


SFX_TICK_SEED = 0x12345678      # a PRNG state with both taps clear in its top byte
SFX_SWEEP_TICKS = 6
PRNG_EFFECT_IDS = (12, 20, 21)  # the descriptors whose +7 is set — the module's only PRNG consumers


@pytest.mark.parametrize("effect_id", range(SFX_IDS))
def test_a_shipped_effect_ticks_down_over_its_own_descriptor(effect_id):
    """Every descriptor the module ships, armed through the trigger's own model and then ticked."""
    what = f"sfx {effect_id} on channel A, {SFX_SWEEP_TICKS} ticks"
    _run_ticks(what, _armed_pokes(effect_id, (CHANNEL_A,), SFX_TICK_SEED, leaf.case_salt(what)),
               SFX_SWEEP_TICKS)


@pytest.mark.parametrize("channel", range(CHANNEL_A + 1, CHANNELS))
@pytest.mark.parametrize("effect_id", SHIPPED_CALL_IDS)
def test_every_tick_arm_steps_its_own_channels_blocks(effect_id, channel):
    """Channels B and C, whose arms the entry reaches through their own `bsr`s — so each is entered
    at ITS address even though the reconstruction has one body. Channel A is left out because the
    sweep above already runs every id on it."""
    what = f"sfx {effect_id} on channel {channel}, {SFX_SWEEP_TICKS} ticks"
    _run_ticks(what, _armed_pokes(effect_id, (channel,), SFX_TICK_SEED, leaf.case_salt(what)),
               SFX_SWEEP_TICKS)


def test_three_armed_channels_run_three_arms_in_one_tick():
    """All three at once, with a different effect on each: the shared noise byte then belongs to
    whichever arm ran LAST, which is the one thing three separate cases could not show."""
    what = "three channels armed at once"
    salt = leaf.case_salt(what)
    pokes = _armed_pokes(0, (), SFX_TICK_SEED, salt, flags=bytes([ACTIVE] * CHANNELS + [0]))
    for channel, effect_id in enumerate((0, 1, 2)):
        pokes = overlay(pokes, expected_writes(_poked_image(pokes), effect_id, channel))
    pokes = overlay(pokes, {ACTIVE_FLAGS: bytes([ACTIVE] * CHANNELS + [0])})
    _run_ticks(what, pokes, SFX_SWEEP_TICKS)


# The flag bytes the `bmi` and the `beq` ladder are read with. Channel A's is the only one with a
# SIGN test on it, so a negative there ends the whole routine and B and C never run — which nothing
# in the shipped code can produce (the trigger `sf`s the byte to 0 and stores 1) and only a seeded
# state reaches.
FLAG_LADDER = (
    ((0xff, ACTIVE, ACTIVE, 0), "channel A's flag NEGATIVE: the whole tick ends before B and C"),
    ((0x80, ACTIVE, ACTIVE, 0), "the smallest negative flag, which is the `bmi`'s own boundary"),
    ((0x7f, 0, 0, 0), "the largest POSITIVE flag: A alone runs"),
    ((0, ACTIVE, 0, 0), "A idle, B armed"),
    ((0, 0, ACTIVE, 0), "A idle, C armed"),
    ((0, 0xff, 0xff, 0), "B and C NEGATIVE, which for them is just non-zero — both arms run"),
    ((0, 0, 0, 0), "nothing armed: the PRNG steps and nothing else is written"),
)


@pytest.mark.parametrize("flags,why", FLAG_LADDER, ids=[f"flags_{f[0][0]:02x}" for f in FLAG_LADDER])
def test_the_flag_ladder_decides_which_arms_run(flags, why):
    what = f"active flags {tuple(hex(f) for f in flags)} ({why})"
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], tuple(range(CHANNELS)), SFX_TICK_SEED,
                         leaf.case_salt(what), flags=bytes(flags))
    _run_ticks(what, pokes, 2)


def test_the_flag_ladder_brackets_the_sign_bit_on_both_sides():
    """The guard on the case above: $7f and $80 are the pair that tell `bmi` from `bne` apart, and
    without both of them a port that tested the whole byte would pass."""
    channel_a = [flags[CHANNEL_A] for flags, _why in FLAG_LADDER]
    assert SIGN_BIT_B in channel_a and SIGN_BIT_B - 1 in channel_a


def test_only_the_prng_moves_when_no_channel_is_armed():
    """Stated as its own claim rather than left inside the ladder: the step is unconditional, so a
    tick with nothing playing still advances the state every SFX with descriptor +7 draws from."""
    what = "an idle tick"
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], (), SFX_TICK_SEED, leaf.case_salt(what),
                         flags=bytes(ACTIVE_FLAGS_LEN))
    memory = _model_sfx_tick(_poked_image(pokes))
    assert set(memory.written) == set(range(PRNG_STATE, PRNG_STATE + PRNG_STATE_LEN)), (
        f"an idle tick wrote {sorted(hex(a) for a in memory.written)}")
    _run_ticks(what, pokes, 1)


# The two ends of an effect's life, neither of which a freshly armed descriptor reaches inside the
# sweep's ticks: the duration counter emptied with no sustain flag (the arm that disarms the channel
# and silences its PSG volume shadow), and the same with the sustain flag up (which holds).
END_OF_EFFECT_CASES = (
    ((0, 0), "duration and sustain both spent: the channel disarms itself"),
    ((0, 1), "duration spent but SUSTAINING: the counter wraps to $ff and the effect runs on"),
    ((1, 0), "one tick of duration left, so the NEXT tick is the one that ends it"),
)


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("duration,sustain,why", [(d, s, w) for (d, s), w in END_OF_EFFECT_CASES],
                         ids=[f"duration_{c[0][0]}_sustain_{c[0][1]}" for c in END_OF_EFFECT_CASES])
def test_the_end_of_an_effect_disarms_its_channel(duration, sustain, why, channel):
    what = f"sfx on channel {channel} with duration {duration} and sustain {sustain} ({why})"
    state = _channel_state(channel)
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], (channel,), SFX_TICK_SEED, leaf.case_salt(what),
                         overrides={state + DESC_DURATION: bytes([duration]),
                                    state + DESC_SUSTAIN: bytes([sustain])})
    _run_ticks(what, pokes, 3)


# The three state bytes the pitch gate reads, as (period countdown, sustain, slide count). The FIRST
# row is the mutation sweep's finding: a countdown already spent with neither a sustain flag nor a
# slide step left jumps STRAIGHT to the volume stream — skipping the countdown decrement, the
# secondary counter, the slide and the noise byte — and no case built from a freshly armed descriptor
# reached it, so a port that fell through into the countdown instead survived the whole battery.
PITCH_GATE_CASES = (
    ((0, 0, 0), "the countdown spent with neither hold: STRAIGHT to the volume stream"),
    ((0, 1, 0), "...the same countdown, held up by the sustain flag, so the pitch reloads"),
    ((0, 0, 1), "...and held up by a slide step instead"),
    ((1, 0, 0), "a countdown of 1: it only decrements, and next tick is the gate's"),
)
PITCH_GATE_DURATION = 8         # enough that the effect does not end inside the case's ticks


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("counts,why", PITCH_GATE_CASES,
                         ids=[f"count_{c[0][0]}_sustain_{c[0][1]}_slide_{c[0][2]}"
                              for c in PITCH_GATE_CASES])
def test_the_pitch_gate_decides_whether_the_rest_of_the_arm_runs_at_all(counts, why, channel):
    period_count, sustain, slide_count = counts
    what = f"channel {channel}: pitch gate {counts} ({why})"
    state = _channel_state(channel)
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], (channel,), SFX_TICK_SEED, leaf.case_salt(what),
                         overrides={state + DESC_DURATION: bytes([PITCH_GATE_DURATION]),
                                    state + STATE_PERIOD_COUNT: bytes([period_count]),
                                    state + DESC_SUSTAIN: bytes([sustain]),
                                    state + DESC_SLIDE_COUNT: bytes([slide_count])})
    _run_ticks(what, pokes, 2)


def test_the_pitch_gate_sweep_reaches_the_arm_that_writes_nothing_but_the_volume():
    """The guard on the row above: the model has to show that arm writing NEITHER the period
    countdown nor the mix period, or the case would be one more ordinary tick."""
    what = "the pitch gate's own early exit"
    state = _channel_state(CHANNEL_A)
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], (CHANNEL_A,), SFX_TICK_SEED, leaf.case_salt(what),
                         overrides={state + DESC_DURATION: bytes([PITCH_GATE_DURATION]),
                                    state + STATE_PERIOD_COUNT: bytes([0]),
                                    state + DESC_SUSTAIN: bytes([0]),
                                    state + DESC_SLIDE_COUNT: bytes([0])})
    written = _model_sfx_tick(_poked_image(pokes)).written
    assert state + STATE_PERIOD_COUNT not in written, "the countdown must NOT be decremented here"
    assert MIX_PERIOD not in written and MIX_NOISE not in written


# The direction byte the constant pitch slide reads. `tst.b / beq / bpl`: ZERO does nothing, and no
# shipped descriptor carries a zero there (the guard below is what says so), so that arm is reachable
# only from seeded state — a port that always subtracted would otherwise pass every case here.
SLIDE_DIRECTION_CASES = (
    (0x00, "no slide at all, which NO shipped descriptor reaches"),
    (0x01, "positive: the period is pulled DOWN by the word at +4"),
    (0x7f, "the largest positive direction, which is still a subtraction"),
    (0x80, "the smallest NEGATIVE one — the `bpl`'s own boundary — which adds"),
    (0xff, "and the one the shipped descriptors use for that arm"),
)
# The secondary counter gates the slide, so a reload of zero is what lets it run on every tick.
SLIDE_SECOND_RELOAD = 0
SLIDE_PERIOD_COUNT = 5          # non-zero, so the pitch reload is skipped and only the slide moves


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("direction,why", SLIDE_DIRECTION_CASES,
                         ids=[f"direction_{c[0]:02x}" for c in SLIDE_DIRECTION_CASES])
def test_the_pitch_slide_reads_its_direction_byte_three_ways(direction, why, channel):
    what = f"channel {channel}: slide direction {direction:#04x} ({why})"
    state = _channel_state(channel)
    pokes = _armed_pokes(SHIPPED_CALL_IDS[0], (channel,), SFX_TICK_SEED, leaf.case_salt(what),
                         overrides={state + DESC_DURATION: bytes([PITCH_GATE_DURATION]),
                                    state + STATE_PERIOD_COUNT: bytes([SLIDE_PERIOD_COUNT]),
                                    state + DESC_SECOND_RELOAD: bytes([SLIDE_SECOND_RELOAD]),
                                    state + DESC_SLIDE_DIRECTION: bytes([direction])})
    _run_ticks(what, pokes, 2)


def test_no_shipped_descriptor_carries_a_zero_slide_direction():
    """The guard on the row above: all 26 carry $01 or $ff, so the `beq` arm is unreachable from the
    game's own data and only a seeded case can pin it. If the table ever changed, this reddens and
    the seeded case becomes redundant rather than silently uninteresting."""
    image = harness.BASE_IMAGE
    directions = {image[DESCRIPTORS + i * DESCRIPTOR_LEN + DESC_SLIDE_DIRECTION]
                  for i in range(SFX_IDS)}
    assert directions == {0x01, 0xff}, f"the shipped slide directions are {sorted(directions)}"


def test_the_slide_direction_sweep_brackets_the_sign_test():
    """$7f and $80 are the pair that tell `bpl` from a `!= 0` test apart, and 0 is the third arm."""
    directions = [direction for direction, _why in SLIDE_DIRECTION_CASES]
    assert 0 in directions and SIGN_BIT_B - 1 in directions and SIGN_BIT_B in directions


# A volume stream of the case's own, parked past the module's data and well inside the 32 KiB a
# table entry can reach. The three bytes a stream can hold are all here: an ordinary volume, the $80
# that loops, and a negative byte that is not $80 and therefore HOLDS.
SEEDED_STREAM = MODULE_BASE + 0x4400
SEEDED_STREAM_BYTES = bytes([0x0c, 0x0a, VOLUME_STREAM_LOOP])
STREAM_CASES = (
    (0, "the stream's first byte: an ordinary volume"),
    (2, "parked ON the $80, so this tick loops back to the base and takes the byte there"),
)
HOLD_BYTES = (0x81, 0xc0, 0xff)     # every negative byte that is NOT the loop marker

# A stream whose FIRST byte is NEGATIVE. Only the LOOP path can reach it, and the original does NOT
# re-test the byte it takes there — `move.b (a2)+,d0` after the reload falls straight into the store
# — so that byte becomes the channel's mix volume however large it is. No shipped stream begins with
# one (the guard below), so without this case a port that re-applied the `bpl` after the reload
# agrees with every other case here: the mutant was RUN and survived before this landed.
SEEDED_LOOP_STREAM_BYTES = bytes([0xc3, 0x0a, VOLUME_STREAM_LOOP])


def _stream_pokes(channel, cursor_offset, what, stream=SEEDED_STREAM_BYTES):
    """A case's own volume stream, with the channel's cursor parked where the case wants it."""
    state = _channel_state(channel)
    return _armed_pokes(SHIPPED_CALL_IDS[0], (channel,), SFX_TICK_SEED, leaf.case_salt(what),
                        overrides={
                            SEEDED_STREAM: bytes(stream),
                            state + STATE_STREAM_BASE: SEEDED_STREAM.to_bytes(LONGWORD_LEN, "big"),
                            state + STATE_STREAM_CURSOR:
                                (SEEDED_STREAM + cursor_offset).to_bytes(LONGWORD_LEN, "big"),
                            # ...and a volume countdown of 1, which `subq.b #1` takes to zero, so
                            # THIS tick steps the stream; the reload of 1 keeps every tick stepping.
                            state + STATE_VOLUME_COUNT: bytes([1]),
                            state + DESC_VOLUME_STEP: bytes([1]),
                        })


@pytest.mark.parametrize("channel", range(CHANNELS))
@pytest.mark.parametrize("cursor_offset,why", STREAM_CASES,
                         ids=[f"cursor_{c[0]}" for c in STREAM_CASES])
def test_the_volume_stream_steps_and_loops(cursor_offset, why, channel):
    what = f"channel {channel}'s volume stream at offset {cursor_offset} ({why})"
    _run_ticks(what, _stream_pokes(channel, cursor_offset, what), 3)


@pytest.mark.parametrize("terminator", HOLD_BYTES, ids=[f"byte_{b:02x}" for b in HOLD_BYTES])
def test_a_negative_stream_byte_that_is_not_the_loop_marker_writes_nothing(terminator):
    """The HOLD. Neither the cursor nor the mix volume moves, so the arm's last two stores do not
    happen at all — which is a claim about the write SET and not only about the values, and the band
    `_run_ticks` allows is what enforces it."""
    what = f"a volume stream ending in {terminator:#04x}"
    pokes = _stream_pokes(CHANNEL_A, len(SEEDED_STREAM_BYTES) - 1, what,
                          stream=SEEDED_STREAM_BYTES[:-1] + bytes([terminator]))
    memory = _model_sfx_tick(_poked_image(pokes))
    state = _channel_state(CHANNEL_A)
    assert not set(memory.written) & set(range(state + STATE_STREAM_CURSOR,
                                               state + STATE_STREAM_CURSOR + LONGWORD_LEN)), (
        f"{what}: the model moved the cursor, so this case is not the hold it claims to be")
    assert MIX_VOLUME + CHANNEL_A not in memory.written
    _run_ticks(what, pokes, 2)


@pytest.mark.parametrize("channel", range(CHANNELS))
def test_the_loop_reload_takes_its_byte_without_re_testing_the_sign(channel):
    """The one thing the loop path can do that the first read cannot: hand back a NEGATIVE volume."""
    what = f"channel {channel} looping onto a stream that begins {SEEDED_LOOP_STREAM_BYTES[0]:#04x}"
    _run_ticks(what, _stream_pokes(channel, len(SEEDED_LOOP_STREAM_BYTES) - 1, what,
                                   stream=SEEDED_LOOP_STREAM_BYTES), 2)


def test_no_shipped_volume_stream_begins_with_a_negative_byte():
    """The guard on the case above, and the reason it must be seeded: all ten shipped streams open
    on a volume in $00..$7f, so the game's own data cannot reach that arm."""
    image = harness.BASE_IMAGE
    firsts = [image[_module_pointer(image, VOLUME_PTRS, index)] for index in range(VOLUME_STREAMS)]
    assert not any(first & SIGN_BIT_B for first in firsts), (
        f"a shipped stream begins negative: {[hex(f) for f in firsts]}")
    assert SEEDED_LOOP_STREAM_BYTES[0] & SIGN_BIT_B, "...and this case's own must, or it pins nothing"


# Two PRNG states whose per-channel bytes differ everywhere, so a pitch delta taken from the wrong
# channel's byte lands on a different period.
PRNG_PITCH_SEEDS = (0x01234567, 0xfedcba98)


# ONE of the three, not all three. `sfx_reload_period` reads descriptor +7 as a FLAG — nothing in it
# distinguishes one non-zero value from another, so a mutant that told the three ids apart would have
# to be a mutant of the flag test itself, which id 12 catches alone; the set {12, 20, 21} is pinned
# by the completeness guard below rather than by running each of them. (Batch-22's kill-matrix rule:
# the axis came out only after the sweep confirmed no mutant separates the ids.)
PRNG_PITCH_EFFECT = PRNG_EFFECT_IDS[0]


@pytest.mark.parametrize("state", PRNG_PITCH_SEEDS, ids=[f"prng_{s:08x}" for s in PRNG_PITCH_SEEDS])
@pytest.mark.parametrize("channel", range(CHANNELS))
def test_a_prng_driven_effect_takes_its_delta_from_its_own_channels_byte(channel, state):
    """A descriptor with +7 set, on all three channels, over two declared PRNG states.

    Each channel reads a DIFFERENT byte of the one state ($1aae6 + channel), which is the one place
    the three arms differ by a stride of one rather than of the block they address — and the state
    the byte is taken from is the one the tick has ALREADY stepped, not the one it was entered with.
    """
    what = f"sfx {PRNG_PITCH_EFFECT} on channel {channel} over a PRNG state of {state:#010x}"
    _run_ticks(what, _armed_pokes(PRNG_PITCH_EFFECT, (channel,), state, leaf.case_salt(what)),
               SFX_SWEEP_TICKS)


def test_the_prng_effect_ids_are_the_only_shipped_descriptors_that_ask_for_it():
    """The guard on the case above: if the descriptor table stopped setting +7 on exactly these
    three, the sweep would quietly become three more ordinary effect cases."""
    image = harness.BASE_IMAGE
    asking = tuple(effect_id for effect_id in range(SFX_IDS)
                   if image[DESCRIPTORS + effect_id * DESCRIPTOR_LEN + DESC_USE_PRNG])
    assert asking == PRNG_EFFECT_IDS, f"the descriptors asking for the PRNG are {asking}"


def test_the_prng_pitch_seeds_give_every_channel_a_byte_of_its_own():
    """...and the other half: two states whose three channel bytes are all distinct, so a delta read
    through the wrong channel's offset cannot agree by accident."""
    for state in PRNG_PITCH_SEEDS:
        channel_bytes = [(state >> (8 * (LONGWORD_LEN - 1 - channel))) & BYTE_MASK
                         for channel in range(CHANNELS)]
        assert len(set(channel_bytes)) == CHANNELS, f"{state:#010x} repeats a byte: {channel_bytes}"


def test_the_tick_tiles_the_module_between_the_trigger_and_the_pointer_table():
    """The three arms, the entry and the shared `rts` have to add up to the 600 bytes between
    snd_trigger_effect's body and the SFX pointer table — and the `rts` has to sit where the
    trigger's body ends, which is what makes it the tick's and not an orphan."""
    entry = leaf.entry_of("snd_sfx_tick")
    assert SFX_SHARED_RTS + len(RTS) == entry, "the shared `rts` must abut the tick's entry"
    assert leaf.entry_of("snd_trigger_effect") + TRIGGER_BODY_BYTES == SFX_SHARED_RTS
    assert len(ENTRY_BYTES["snd_sfx_tick"]) == SFX_TICK_BODY_BYTES - len(RTS)
    assert entry + len(ENTRY_BYTES["snd_sfx_tick"]) == PTR_TABLE, (
        "the tick's last arm must end exactly where the SFX pointer table begins")


@pytest.mark.parametrize("channel", range(CHANNELS))
def test_each_arm_sits_a_whole_body_after_the_last(channel):
    """The arms' own addresses, from ../names.txt, against the stride the entry pin assembles them
    at — so a name moved without the body moving fails here rather than inside a case."""
    entry = leaf.entry_of("snd_sfx_tick")
    expected = entry + SFX_ENTRY_BODY_BYTES + channel * SFX_ARM_BODY_BYTES
    assert leaf.entry_of(SFX_ARM_NAMES[channel]) == expected, (
        f"{SFX_ARM_NAMES[channel]} is not {expected:#x}")
    assert len(_sfx_arm(expected, channel)) == SFX_ARM_BODY_BYTES


# --- $18208: one music channel's period and volume ------------------------------------------------
#
# A3 IS AN ENTRY REGISTER HERE TOO. Like $1aaca and unlike everything reached through the stub table,
# this routine does not open with `lea $1738c(pc),a3`: it inherits the base snd_music_tick left
# there. The whole-body pin above is what says the `lea` is absent, and every case below seeds a3.

PERIOD_VOLUME_BODY_BYTES = 330
# The cap is the body's own 102 instructions plus the three EXTRA turns its one loop can take — the
# octave doubling runs at most four times, and the body counts its three instructions once.
PERIOD_VOLUME_INSNS = 102
PERIOD_VOLUME_LOOP_INSNS = 3
PERIOD_VOLUME_EXTRA_OCTAVES = 3
PERIOD_VOLUME_INSN_CAP = (PERIOD_VOLUME_INSNS
                          + PERIOD_VOLUME_EXTRA_OCTAVES * PERIOD_VOLUME_LOOP_INSNS
                          + leaf.RUNNER_SENTINEL_INSN)

# Where a case's own envelope and arpeggio streams go: past the module's data, well inside the 32 KiB
# a3-relative window, and clear of every band the routine writes.
SEEDED_ENVELOPE = MODULE_BASE + 0x4600
SEEDED_ARPEGGIO = MODULE_BASE + 0x4700
# The envelope is read one byte AHEAD of its cursor and ends on any negative byte; the arpeggio is
# read at its cursor and ends on bit 7, which is stripped before the byte is used as a note offset.
SEEDED_ENVELOPE_BYTES = bytes([0x05, 0x0a, 0x0f, 0x08, 0xff])
SEEDED_ARPEGGIO_BYTES = bytes([0x00, 0x04, 0x07, 0x8c])

MUSIC_STATE_BLOCK_LEN = CHANNELS * MUSIC_CHANNEL_LEN
GLOBALS_BLOCK = wb("SND_ENGINE_ENABLED")
GLOBALS_BLOCK_LEN = 28          # $17c56..$17c71, the whole a3+2250..2277 band (../names.txt)

# Each named field's WIDTH, so a case can write one by name and the record's layout is stated once.
RECORD_FIELD_WIDTH = {
    CH_FLAGS: 1, CH_NOISE_TRACKS_NOTE: 1, CH_PATTERN_CURSOR: LONGWORD_LEN,
    CH_SEQUENCE_OFFSET: WORD_LEN, CH_SEQUENCE_INDEX: WORD_LEN,
    CH_VIBRATO_ACC: WORD_LEN, CH_ARPEGGIO_BASE: LONGWORD_LEN,
    CH_ARPEGGIO_CURSOR: LONGWORD_LEN, CH_VIBRATO_DEPTH: 1, CH_VIBRATO_SPEED: 1,
    CH_ENVELOPE_SPEED: 1, CH_DURATION: 1, CH_DURATION_RELOAD: 1, CH_NOTE: 1, CH_VOLUME: 1,
    CH_ENVELOPE_COUNT: 1, CH_ENVELOPE_CURSOR: LONGWORD_LEN, CH_ENVELOPE_BASE: LONGWORD_LEN,
    CH_ENVELOPE_LAST: 1, CH_PORTA_LIMIT: 1, CH_PORTA_STEP: 1,
    CH_PORTA_CURRENT: 1, CH_PORTA_CONTROL: 1, CH_YIELD: 1, CH_DETUNE: 1, CH_MIXER_MASK: 1,
}
# What every case starts from before its own overrides. Deliberately unremarkable — a mid-range note,
# a countdown that has not expired, no arm armed — so that a case's overrides are the whole of what
# it is about.
# EVERY MODULE GLOBAL $18208 READS, pinned rather than left to the keyed seed — enumerated from
# src/sound.c, not from the ones a case happened to care about.
#
# The transpose is why this exists: it sits inside GLOBALS_BLOCK and is added to every note, so a
# salt-derived byte there moved each case's effective note off the one its name stated, and the two
# boundary cases INVERTED on one channel. The other three are the same hazard one step out — a case
# named for the noise arm should not be reading a routing mask, a period base or a shadow mixer the
# salt chose. The salt then covers only the bytes no name-level claim can compute over, and the case
# that IS about one of these overrides it.
GLOBAL_DEFAULTS = {
    GLOBAL_TRANSPOSE: 0,
    NOISE_PERIOD_BASE: 0x21,        # an ordinary noise period, and not one the XOR maps to itself
    NOISE_ROUTE_MASK: 0x36,         # some tone bits set and some clear, so the merge has both
    PSG_SHADOW + PSG_REG_MIXER: 0x5a,
}


def test_the_global_defaults_name_every_module_global_the_pass_reads():
    """The guard on the table above: the four are the whole of what `$18208` reads outside the
    record it is handed, so a fifth appearing in src/sound.c has to appear here too or the case
    naming it would be running on a salt-derived byte again."""
    body = pathlib.Path(__file__).resolve().parents[1] / "src" / "sound.c"
    pass_source = body.read_text().split("---- $18208:")[1]
    named = {name for name, address in
             (("SND_GLOBAL_TRANSPOSE", GLOBAL_TRANSPOSE), ("SND_NOISE_PERIOD_BASE",
                                                           NOISE_PERIOD_BASE),
              ("SND_NOISE_ROUTE_MASK", NOISE_ROUTE_MASK),
              ("SND_PSG_SHADOW", PSG_SHADOW + PSG_REG_MIXER))
             if address in GLOBAL_DEFAULTS}
    read = {name for name in ("SND_GLOBAL_TRANSPOSE", "SND_NOISE_PERIOD_BASE",
                              "SND_NOISE_ROUTE_MASK", "SND_PSG_SHADOW")
            if f"image[WB_{name}" in pass_source or f"WB_{name} + WB_PSG_REG_MIXER]" in pass_source}
    assert read <= named, f"{sorted(read - named)} is read by the pass but not pinned by a default"
RECORD_DEFAULTS = {
    CH_FLAGS: 0, CH_VIBRATO_ACC: 0, CH_ARPEGGIO_BASE: SEEDED_ARPEGGIO,
    CH_ARPEGGIO_CURSOR: SEEDED_ARPEGGIO, CH_VIBRATO_DEPTH: 2, CH_VIBRATO_SPEED: 3,
    CH_ENVELOPE_SPEED: 4, CH_NOTE: 0x30, CH_VOLUME: 0x0c, CH_ENVELOPE_COUNT: 2,
    CH_ENVELOPE_CURSOR: SEEDED_ENVELOPE, CH_ENVELOPE_LAST: 0x0a, CH_PORTA_LIMIT: 0x20,
    CH_PORTA_STEP: 4, CH_PORTA_CURRENT: 0x18, CH_PORTA_CONTROL: 0, CH_YIELD: 0, CH_DETUNE: 0,
}
# The one field the module never writes: a per-channel CONSTANT, so the shipped bytes are the link
# time ones and not residue. Read off the image rather than restated, and pinned below.
SHIPPED_MIXER_MASKS = tuple(harness.BASE_IMAGE[_music_channel(index) + CH_MIXER_MASK]
                            for index in range(CHANNELS))


class SndChannelMix(ctypes.Structure):
    """include/sound.h's `snd_channel_mix` — the same two fields in the same order, so a case can
    hand the reconstruction its entry d0 and read its two results back."""
    _fields_ = [("period", ctypes.c_uint32), ("volume", ctypes.c_uint32)]


_period_volume_fn = leaf.bind("snd_channel_period_and_volume",
                              leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.POINTER(SndChannelMix)])


def _period_volume_glue(channel, entry_period, entry_volume, results):
    """The reconstruction's whole result is an in/out struct rather than a returned d0, so the glue
    keeps one struct per invocation and appends its two fields to ``results``.

    A LIST AND NOT ONE STRUCT, because the attribution pass runs the candidate a SECOND time on a
    poisoned image and a single struct would end holding that run's answer — which is the right
    answer to a different question. The case reads results[0], the run its model was built for.
    """
    def call(_lib, image):
        mix = SndChannelMix(period=entry_period, volume=entry_volume)
        _period_volume_fn(image, channel, ctypes.byref(mix))
        results.append({"d0": mix.period, "d1": mix.volume})
    return call


def _model_envelope(memory, channel):
    """$18214. `subq.b #1 / bcc` — the BORROW is the trigger, so the envelope advances on the tick
    after the countdown reaches zero, and the byte it takes is PEEKED one past the cursor."""
    count = memory.read(channel + CH_ENVELOPE_COUNT)
    memory.byte(channel + CH_ENVELOPE_COUNT, count - 1)
    if count == 0:
        memory.byte(channel + CH_ENVELOPE_COUNT, memory.read(channel + CH_ENVELOPE_SPEED))
        cursor = memory.read_long(channel + CH_ENVELOPE_CURSOR)
        peeked = memory.read_through_pointer(cursor + 1)
        if not peeked & SIGN_BIT_B:
            memory.long(channel + CH_ENVELOPE_CURSOR, (cursor + 1) & LONGWORD_MASK)
            memory.byte(channel + CH_ENVELOPE_LAST, peeked)
    memory.byte(channel + CH_VOLUME, memory.read(channel + CH_ENVELOPE_LAST))


def _model_arpeggio(memory, channel):
    """$18244. The cursor has already advanced when the terminator is tested, and a terminator
    replaces it with the BASE rather than with base + 1 — so the ending entry is itself played."""
    cursor = memory.read_long(channel + CH_ARPEGGIO_CURSOR)
    step = memory.read_through_pointer(cursor)
    cursor = (cursor + 1) & LONGWORD_MASK
    if step & ARPEGGIO_END:
        step &= BYTE_MASK ^ ARPEGGIO_END
        cursor = memory.read_long(channel + CH_ARPEGGIO_BASE)
    memory.long(channel + CH_ARPEGGIO_CURSOR, cursor)
    return step


def _model_portamento(memory, channel, note_index, flags, control):
    """$18272, and the whole of d1's low word on the arm that runs it."""
    limit = (memory.read(channel + CH_PORTA_LIMIT) << 1) & BYTE_MASK
    current = memory.read(channel + CH_PORTA_CURRENT)
    step = memory.read(channel + CH_PORTA_STEP)

    if not (control & CH_PORTA_HELD and flags & CH_FLAG_TOGGLE):
        if control & CH_PORTA_AT_LIMIT:
            current = (current + step) & BYTE_MASK
            if current >= limit:                     # `cmp.b / bcs` — an UNSIGNED compare
                memory.byte(channel + CH_PORTA_CONTROL, control & ~CH_PORTA_AT_LIMIT & BYTE_MASK)
                current = limit
        elif current < step:                         # `sub.b / bcc` — the borrow is the underflow
            memory.byte(channel + CH_PORTA_CONTROL, control | CH_PORTA_AT_LIMIT)
            current = 0
        else:
            current = (current - step) & BYTE_MASK
        memory.byte(channel + CH_PORTA_CURRENT, current)

    half_limit = limit >> 1
    offset = (current - half_limit) & BYTE_MASK
    if current < half_limit:                         # `subi.w #256` sign-extends the byte
        offset = (offset - BYTE_LIMIT) & WORD_MASK

    octave = note_index + PORTA_OCTAVE_BIAS          # an ADD, so its CARRY is the condition
    while not octave >> 8:
        offset = (offset << 1) & WORD_MASK
        octave = (octave & BYTE_MASK) + PORTA_OCTAVE_STEP
    return offset


def _model_vibrato(memory, channel):
    """$182dc. The speed byte is a DELAY: the tick that decrements it to zero does not store the
    zero back, so the field holds its last non-zero value and steps every tick from then on."""
    speed = (memory.read(channel + CH_VIBRATO_SPEED) - 1) & BYTE_MASK
    if speed != 0:
        memory.byte(channel + CH_VIBRATO_SPEED, speed)
        return 0
    depth = memory.read(channel + CH_VIBRATO_DEPTH)
    if depth & SIGN_BIT_B:
        depth -= BYTE_LIMIT                          # `clr.w / move.b / bpl / addi.w #-256`
    accumulator = (memory.read_word(channel + CH_VIBRATO_ACC) + depth) & WORD_MASK
    memory.word(channel + CH_VIBRATO_ACC, accumulator)
    return accumulator


def _model_mixer(memory, channel, flags):
    """$18300 — the two MODULE GLOBALS the pass writes, which is what makes it more than a function
    of the record it is handed."""
    routing = memory.read(NOISE_ROUTE_MASK)
    if flags & CH_NOISE_ROUTE_FLAGS == CH_NOISE_ROUTE_FLAGS:
        memory.byte(NOISE_PERIOD_OUT, memory.read(NOISE_PERIOD_BASE) ^ NOISE_PERIOD_XOR)
        routing = NOISE_TONE_BITS
    mask = memory.read(channel + CH_MIXER_MASK)
    shadow = memory.read(PSG_SHADOW + PSG_REG_MIXER)
    merged = ((routing ^ shadow) & mask) ^ shadow
    if memory.read(channel + CH_YIELD) & CH_YIELD_TAKEN:
        memory.byte(channel + CH_YIELD, memory.read(channel + CH_YIELD) & CH_YIELD_MASK)
        merged &= ~(mask & MIXER_NOISE_BITS) & BYTE_MASK
        memory.byte(NOISE_PERIOD_OUT, NOISE_ROUTE_YIELDED)
    memory.byte(PSG_SHADOW + PSG_REG_MIXER, merged)


def _model_period_volume(memory, channel, entry_period):
    """The two registers $18208 leaves, and every byte it stores on the way."""
    flags = memory.read(channel + CH_FLAGS)
    if flags & CH_FLAG_ENVELOPE:
        _model_envelope(memory, channel)

    note = (memory.read(channel + CH_NOTE) + memory.read(GLOBAL_TRANSPOSE)
            + memory.read(channel + CH_DETUNE)) & BYTE_MASK
    note = (note + _model_arpeggio(memory, channel)) & BYTE_MASK

    # `add.b d0,d0` — a BYTE double, so the index never leaves the 256 bytes at the table's base
    # however large the note is, and a note from NOTE_PERIOD_ENTRIES up reads past its end.
    note_index = (note << 1) & BYTE_MASK
    period = memory.read_word(NOTE_PERIOD_TABLE + note_index)
    scratch = note_index

    control = memory.read(channel + CH_PORTA_CONTROL)
    if control & CH_PORTA_ENABLED:
        scratch = _model_portamento(memory, channel, note_index, flags, control)
        period = (period + scratch) & WORD_MASK

    flags ^= CH_FLAG_TOGGLE
    memory.byte(channel + CH_FLAGS, flags)
    if flags & CH_FLAG_VIBRATO:
        period = (period + _model_vibrato(memory, channel)) & WORD_MASK

    _model_mixer(memory, channel, flags)
    return {"d0": leaf.set_low_word(entry_period, period),
            "d1": (scratch & ~BYTE_MASK & WORD_MASK) | memory.read(channel + CH_VOLUME)}


def _record_bytes(index, salt, fields, defaults=RECORD_DEFAULTS):
    """One 48-byte music channel record: ADDRESS-KEYED bytes with the case's own fields over them.

    Keyed rather than zeroed because the band ships dirty and a zero would be indistinguishable from
    a field the routine cleared; keyed on the address so a read at the wrong offset lands on a byte
    that is wrong for where it was written.

    ``defaults`` picks WHICH tier's unremarkable starting record this is: RECORD_DEFAULTS covers the
    fields $18208 reads and STEP_RECORD_DEFAULTS extends it with the stepper's (the countdown, the
    pattern cursor and the sequence pair). Every key must be in RECORD_FIELD_WIDTH — a missing one
    is a KeyError here rather than a silently unwritten field.
    """
    record = bytearray(leaf.keyed_block(_music_channel(index), MUSIC_CHANNEL_LEN, salt))
    fields = {**defaults, CH_MIXER_MASK: SHIPPED_MIXER_MASKS[index], **fields}
    for offset, value in fields.items():
        width = RECORD_FIELD_WIDTH[offset]
        record[offset:offset + width] = value.to_bytes(width, "big")
    return bytes(record)


PERIOD_VOLUME_ENTRY_D0 = 0xdead0000     # the HIGH word, which is the half the routine never writes
PERIOD_VOLUME_ENTRY_D1 = 0x1234abcd     # ...and a d1 that `moveq #0,d1` must destroy entirely


def _run_period_volume(index, what, fields=None, globals_=None):
    """One $18208 differential: the image diff and the write set, the model's own bytes by value,
    and BOTH outgoing registers against the oracle and the reconstruction alike."""
    salt = leaf.case_salt(what)
    record = _music_channel(index)
    pokes = overlay(
        {MUSIC_CHANNEL_STATE: leaf.keyed_block(MUSIC_CHANNEL_STATE, MUSIC_STATE_BLOCK_LEN, salt),
         GLOBALS_BLOCK: leaf.keyed_block(GLOBALS_BLOCK, GLOBALS_BLOCK_LEN, salt),
         PSG_SHADOW: leaf.keyed_block(PSG_SHADOW, PSG_SHADOW_LEN, salt),
         SEEDED_ENVELOPE: SEEDED_ENVELOPE_BYTES,
         SEEDED_ARPEGGIO: SEEDED_ARPEGGIO_BYTES},
        {record: _record_bytes(index, salt, fields or {})},
        {addr: bytes([value]) for addr, value in GLOBAL_DEFAULTS.items()},
        {addr: bytes([value]) for addr, value in (globals_ or {}).items()})

    memory = _Memory(_poked_image(pokes))
    expected = _model_period_volume(memory, record, PERIOD_VOLUME_ENTRY_D0)

    results = []
    info = leaf.run("snd_channel_period_and_volume",
                    _period_volume_glue(record, PERIOD_VOLUME_ENTRY_D0, PERIOD_VOLUME_ENTRY_D1,
                                        results),
                    write_bands(memory.written), what,
                    regs={"a3": MODULE_BASE, "a0": record, "d0": PERIOD_VOLUME_ENTRY_D0,
                          "d1": PERIOD_VOLUME_ENTRY_D1, "_pokes": pokes},
                    max_insns=PERIOD_VOLUME_INSN_CAP)
    assert_written(info, memory.written, what)
    for register in ("d0", "d1"):
        assert info["regs"][register] == expected[register], (
            f"{what}: the oracle left {register} = {info['regs'][register]:#010x}, not the "
            f"{expected[register]:#010x} the model gives")
        assert results[0][register] == expected[register], (
            f"{what}: the reconstruction left {register} = {results[0][register]:#010x}, not "
            f"{expected[register]:#010x}")
    return memory, expected


# (name, record fields, module globals) — one entry per branch of the six arms, and per boundary
# inside them. Every case runs on all three channel records, which is what pins the 48-byte stride
# and the per-channel mixer mask.
PERIOD_VOLUME_CASES = (
    ("a plain note with no arm armed", {}, {}),
    ("the envelope running with its countdown already spent", {CH_FLAGS: CH_FLAG_ENVELOPE,
                                                              CH_ENVELOPE_COUNT: 0}, {}),
    ("the envelope running with its countdown still turning", {CH_FLAGS: CH_FLAG_ENVELOPE,
                                                               CH_ENVELOPE_COUNT: 3}, {}),
    ("an envelope countdown of exactly ONE, the tick before the borrow — the sweep's finding, "
     "since `subq.b #1 / bcc` and a `<= 1` test agree on every other value",
     {CH_FLAGS: CH_FLAG_ENVELOPE, CH_ENVELOPE_COUNT: 1}, {}),
    ("the envelope's cursor one byte before its NEGATIVE terminator, which holds",
     {CH_FLAGS: CH_FLAG_ENVELOPE, CH_ENVELOPE_COUNT: 0,
      CH_ENVELOPE_CURSOR: SEEDED_ENVELOPE + len(SEEDED_ENVELOPE_BYTES) - 2}, {}),
    ("an envelope speed of zero, which reloads the countdown to zero and steps every tick",
     {CH_FLAGS: CH_FLAG_ENVELOPE, CH_ENVELOPE_COUNT: 0, CH_ENVELOPE_SPEED: 0}, {}),
    ("the arpeggio parked ON its terminator, so the cursor goes back to the base",
     {CH_ARPEGGIO_CURSOR: SEEDED_ARPEGGIO + len(SEEDED_ARPEGGIO_BYTES) - 1}, {}),
    ("an arpeggio base that is not its cursor, so a loop is observable",
     {CH_ARPEGGIO_CURSOR: SEEDED_ARPEGGIO + len(SEEDED_ARPEGGIO_BYTES) - 1,
      CH_ARPEGGIO_BASE: SEEDED_ARPEGGIO + 1}, {}),
    ("the last note the period table holds", {CH_NOTE: NOTE_PERIOD_ENTRIES - 1}, {}),
    ("the first note PAST it, which reads the arpeggio pointer table as a period",
     {CH_NOTE: NOTE_PERIOD_ENTRIES}, {}),
    ("the last note before the doubled index wraps the byte", {CH_NOTE: 127}, {}),
    ("a note of 128, whose doubled index wraps to the table's first entry", {CH_NOTE: 128}, {}),
    ("the largest note a byte holds", {CH_NOTE: 0xff}, {}),
    ("a note carried past the table by the GLOBAL TRANSPOSE alone",
     {CH_NOTE: NOTE_PERIOD_ENTRIES - 4}, {GLOBAL_TRANSPOSE: 8}),
    ("...and one pulled back below it by the channel's own detune",
     {CH_NOTE: NOTE_PERIOD_ENTRIES + 4, CH_DETUNE: 0xf0}, {}),
    ("portamento running DOWN towards its limit",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_PORTA_CURRENT: 0x18, CH_PORTA_STEP: 4}, {}),
    ("portamento UNDERFLOWING, which zeroes the current and flips the direction bit",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_PORTA_CURRENT: 2, CH_PORTA_STEP: 4}, {}),
    ("portamento exactly at its step, the boundary the borrow is read on",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_PORTA_CURRENT: 4, CH_PORTA_STEP: 4}, {}),
    ("portamento running UP", {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_AT_LIMIT,
                               CH_PORTA_CURRENT: 0x18, CH_PORTA_STEP: 4}, {}),
    ("portamento REACHING its limit, clamped and the direction bit cleared",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_AT_LIMIT, CH_PORTA_CURRENT: 0x3e,
      CH_PORTA_STEP: 4, CH_PORTA_LIMIT: 0x20}, {}),
    ("portamento landing EXACTLY on its limit, which `bcs` clamps and a `>` test would not — the "
     "sweep's finding",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_AT_LIMIT, CH_PORTA_CURRENT: 0x3c,
      CH_PORTA_STEP: 4, CH_PORTA_LIMIT: 0x20}, {}),
    ("portamento one step BELOW its limit, the other side of that compare",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_AT_LIMIT, CH_PORTA_CURRENT: 0x39,
      CH_PORTA_STEP: 4, CH_PORTA_LIMIT: 0x20}, {}),
    ("a HELD portamento on a tick whose toggle bit is SET, where it does not step",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_HELD, CH_FLAGS: CH_FLAG_TOGGLE}, {}),
    ("...and on the tick whose toggle bit is clear, where it does",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED | CH_PORTA_HELD, CH_FLAGS: 0}, {}),
    ("portamento on the LOWEST note, four octaves of doubling below the reference index",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_NOTE: 0}, {}),
    ("portamento on the note the doubling stops at", {CH_PORTA_CONTROL: CH_PORTA_ENABLED,
                                                      CH_NOTE: 48}, {}),
    ("...and one semitone below it, where exactly one doubling happens",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_NOTE: 47}, {}),
    ("portamento whose limit has the top bit set, which `lsl.b #1` throws away",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_PORTA_LIMIT: 0x90}, {}),
    ("a portamento offset that is NEGATIVE, so the `subi.w` sign extension is what is doubled",
     {CH_PORTA_CONTROL: CH_PORTA_ENABLED, CH_PORTA_CURRENT: 2, CH_PORTA_LIMIT: 0x20,
      CH_PORTA_STEP: 0, CH_NOTE: 0}, {}),
    ("vibrato with its speed still counting down", {CH_FLAGS: CH_FLAG_VIBRATO,
                                                    CH_VIBRATO_SPEED: 3}, {}),
    ("vibrato whose countdown reaches zero and is NOT stored back",
     {CH_FLAGS: CH_FLAG_VIBRATO, CH_VIBRATO_SPEED: 1, CH_VIBRATO_DEPTH: 5}, {}),
    ("vibrato with a NEGATIVE depth, sign-extended into the accumulator",
     {CH_FLAGS: CH_FLAG_VIBRATO, CH_VIBRATO_SPEED: 1, CH_VIBRATO_DEPTH: 0xfb}, {}),
    ("vibrato whose accumulator wraps the word", {CH_FLAGS: CH_FLAG_VIBRATO, CH_VIBRATO_SPEED: 1,
                                                  CH_VIBRATO_DEPTH: 0x7f,
                                                  CH_VIBRATO_ACC: 0xffc0}, {}),
    ("a vibrato speed of zero, which the `subq.b` takes to $ff rather than to a step",
     {CH_FLAGS: CH_FLAG_VIBRATO, CH_VIBRATO_SPEED: 0}, {}),
    # The four states of the flag pair the noise arm reads, seeded as their PRE-toggle values since
    # the arm sees the byte after `eori.b #1`. Only the first runs the arm.
    ("post-toggle flags $03: BOTH noise bits set, so the arm runs",
     {CH_FLAGS: CH_NOISE_ROUTE_FLAGS ^ CH_FLAG_TOGGLE}, {}),
    ("post-toggle flags $02: the same channel one tick later, bit 0 now clear",
     {CH_FLAGS: CH_NOISE_ROUTE_FLAGS}, {}),
    ("post-toggle flags $01: bit 0 alone, which a `!= 0` test would take for the arm",
     {CH_FLAGS: 0}, {}),
    ("post-toggle flags $00: neither bit", {CH_FLAGS: CH_FLAG_TOGGLE}, {}),
    ("a channel YIELDED to the SFX engine", {CH_YIELD: 0xff}, {}),
    ("a yield flag whose sign bit is the only one set", {CH_YIELD: SIGN_BIT_B}, {}),
    ("a yield flag one below the sign bit, which is NOT a yield", {CH_YIELD: SIGN_BIT_B - 1}, {}),
    ("a yielded channel that ALSO owns the noise, so both writes of $17c6c happen in order",
     {CH_YIELD: 0xff, CH_FLAGS: CH_NOISE_ROUTE_FLAGS ^ CH_FLAG_TOGGLE}, {}),
    ("a shadow mixer of $ff, so the merge has nothing left to set", {},
     {PSG_SHADOW + PSG_REG_MIXER: 0xff}),
    ("...and one of $00", {}, {PSG_SHADOW + PSG_REG_MIXER: 0x00}),
    ("a noise routing mask of $ff against a zero shadow", {},
     {NOISE_ROUTE_MASK: 0xff, PSG_SHADOW + PSG_REG_MIXER: 0x00}),
)


# ONE record for the whole grid. $18208 is channel-AGNOSTIC — a0 is its argument and the body has no
# per-channel code at all, unlike the SFX tick's three arms, which are three copies of one body. The
# other two records carry exactly one thing of their own, the constant mixer mask at +47, and the two
# cases below are the whole of what pins it. MEASURED, not argued: a port with the mask hardcoded to
# channel A's $09 passes every one of these rows on record 0 and fails on records 1 and 2.
PERIOD_VOLUME_RECORD = 0
MASK_PINNING_CASES = (
    ("the mixer merge, whose mask is this record's own",
     {CH_FLAGS: CH_NOISE_ROUTE_FLAGS ^ CH_FLAG_TOGGLE}, {}),
    ("...and the yield, the second place the same mask is read", {CH_YIELD: 0xff}, {}),
)


@pytest.mark.parametrize("case,fields,globals_", PERIOD_VOLUME_CASES,
                         ids=[c[0][:48].replace(" ", "_") for c in PERIOD_VOLUME_CASES])
def test_a_music_channels_period_and_volume(case, fields, globals_):
    _run_period_volume(PERIOD_VOLUME_RECORD, f"record {PERIOD_VOLUME_RECORD}: {case}",
                       fields, globals_)


@pytest.mark.parametrize("index", range(PERIOD_VOLUME_RECORD + 1, CHANNELS))
@pytest.mark.parametrize("case,fields,globals_", MASK_PINNING_CASES,
                         ids=[c[0][:40].replace(" ", "_") for c in MASK_PINNING_CASES])
def test_the_other_records_carry_their_own_mixer_mask(case, fields, globals_, index):
    """The two arms that read +47, on the two records the grid above does not run — which is what
    makes the trim a claim about the BODY (it takes its record from a0) rather than a saving."""
    _run_period_volume(index, f"record {index}: {case}", fields, globals_)


def test_the_arpeggio_terminator_bit_cannot_change_the_note_it_selects():
    """The `bclr #7,d1` clears a bit the routine then throws away, and this states it rather than
    leaving a reader to find it.

    The stripped byte's ONLY use is `add.b d1,d0`, and d0 is then doubled as a BYTE — so bit 7 of the
    sum becomes bit 8 of the index and is masked off. A port that left the bit in selects the same
    period entry, the same portamento scratch and the same everything for EVERY note, which is why
    the mutation sweep's "the terminator bit is not stripped" mutant survived and is EQUIVALENT
    rather than uncaught. The `bclr` earns its place through the Z it sets, not through the value.
    """
    for note in range(BYTE_LIMIT):
        stripped = ((note + 0) << 1) & BYTE_MASK
        left_in = ((note + ARPEGGIO_END) << 1) & BYTE_MASK
        assert stripped == left_in, f"note {note:#04x} tells the two apart: {stripped}/{left_in}"


def test_the_three_music_records_carry_the_three_mixer_masks_the_module_map_claims():
    """+47 is the ONE field of the record nothing in the module ever writes, so the shipped bytes are
    the link-time ones rather than residue — which is what lets the cases above seed them from the
    image. Required to be the three distinct masks ../names.txt names, in order."""
    assert SHIPPED_MIXER_MASKS == (0x09, 0x12, 0x24), (
        f"the three constant mixer masks are {tuple(hex(m) for m in SHIPPED_MIXER_MASKS)}")


def _effective_note(fields, globals_):
    """The note byte a case's own fields make $18208 look the period table up by.

    FOUR fields decide it, not one: the record's note, the global transpose, the channel's detune and
    the arpeggio byte the cursor lands on. The two guards below were written against `CH_NOTE` alone
    and passed on arithmetic no run performed — the review pass's finding, and the reason
    GLOBAL_DEFAULTS pins the transpose rather than leaving it to the keyed seed.
    """
    record = {**RECORD_DEFAULTS, **fields}
    transpose = {**GLOBAL_DEFAULTS, **globals_}[GLOBAL_TRANSPOSE]
    step = SEEDED_ARPEGGIO_BYTES[record[CH_ARPEGGIO_CURSOR] - SEEDED_ARPEGGIO]
    return (record[CH_NOTE] + transpose + record[CH_DETUNE]
            + (step & (BYTE_MASK ^ ARPEGGIO_END))) & BYTE_MASK


def test_the_note_sweep_reaches_both_sides_of_the_period_tables_end():
    """The guard on the aliasing cases: without a note below NOTE_PERIOD_ENTRIES, one between it and
    the byte index's wrap, and one past that wrap, a port that bounded the index to the table — or
    one that doubled the note as a WORD — would pass every case here."""
    notes = [_effective_note(fields, globals_) for _case, fields, globals_ in PERIOD_VOLUME_CASES]
    assert any(note < NOTE_PERIOD_ENTRIES for note in notes)
    assert any(NOTE_PERIOD_ENTRIES <= note < 128 for note in notes)
    assert any(note >= 128 for note in notes), "no case reaches the byte index's own wrap"


def test_the_portamento_sweep_reaches_every_octave_count_the_doubling_can_take():
    """The loop runs `ceil((96 - index) / 24)` times and the sweep has to reach both ends of that —
    zero doublings and the four the lowest note takes — or a loop written as an `if` would pass."""
    counts = set()
    for _case, fields, globals_ in PERIOD_VOLUME_CASES:
        if not fields.get(CH_PORTA_CONTROL, 0) & CH_PORTA_ENABLED:
            continue
        octave = (((_effective_note(fields, globals_) << 1) & BYTE_MASK) + PORTA_OCTAVE_BIAS)
        turns = 0
        while not octave >> 8:
            turns += 1
            octave = (octave & BYTE_MASK) + PORTA_OCTAVE_STEP
        counts.add(turns)
    assert {0, 4} <= counts, f"the portamento cases only reach {sorted(counts)} doublings"


def test_the_noise_flag_sweep_reaches_all_four_states_of_the_pair_the_arm_reads():
    """`eori.b #$ff / andi.b #3 / bne` reads the two low flag bits AFTER the toggle, so a sweep that
    missed one of the four would agree with a port testing `!= 0` instead of `== 3`."""
    seen = {(fields[CH_FLAGS] ^ CH_FLAG_TOGGLE) & CH_NOISE_ROUTE_FLAGS
            for _case, fields, _globals in PERIOD_VOLUME_CASES if CH_FLAGS in fields}
    assert seen == {0, 1, 2, 3}, f"the sweep only reaches post-toggle {sorted(seen)}"


def test_a_period_and_volume_case_seeds_every_mutable_byte_it_reads():
    """The same guard the tick battery carries, for this pass's four dirty bands."""
    what = "a period/volume case"
    salt = leaf.case_salt(what)
    pokes = overlay(
        {MUSIC_CHANNEL_STATE: leaf.keyed_block(MUSIC_CHANNEL_STATE, MUSIC_STATE_BLOCK_LEN, salt),
         GLOBALS_BLOCK: leaf.keyed_block(GLOBALS_BLOCK, GLOBALS_BLOCK_LEN, salt),
         PSG_SHADOW: leaf.keyed_block(PSG_SHADOW, PSG_SHADOW_LEN, salt)},
        {_music_channel(0): _record_bytes(0, salt, {})},
        {addr: bytes([value]) for addr, value in GLOBAL_DEFAULTS.items()})
    assert_bands_are_seeded(pokes, ((MUSIC_CHANNEL_STATE, MUSIC_STATE_BLOCK_LEN),
                                     (GLOBALS_BLOCK, GLOBALS_BLOCK_LEN),
                                     (PSG_SHADOW, PSG_SHADOW_LEN)), what)


def test_the_pass_ends_where_the_psg_shadow_begins():
    """Self-bounding: the body's last instruction is followed immediately by the eleven shadow bytes
    it writes one of, so the length and the shadow's address prove each other."""
    assert len(ENTRY_BYTES["snd_channel_period_and_volume"]) == PERIOD_VOLUME_BODY_BYTES
    assert leaf.entry_of("snd_channel_period_and_volume") + PERIOD_VOLUME_BODY_BYTES == PSG_SHADOW


def test_the_pass_is_called_three_times_by_the_tick_and_by_nothing_else():
    """Its three `bsr.w` sites are the tick's, one per music channel record — which is what says the
    `channel` argument is an ADDRESS of the case's choosing rather than an index."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    target = leaf.entry_of("snd_channel_period_and_volume")
    call = leaf.BSR_W
    sites = [at for at in range(0, len(program) - len(call) - WORD_LEN, WORD_LEN)
             if program[at:at + len(call)] == call
             and at + BRANCH_EXTENSION + leaf.s16(leaf.u16(program, at + len(call))) == target]
    assert sites == [0x17d16, 0x17d3e, 0x17d66], f"its callers are {[hex(a) for a in sites]}"


# --- $18106 and its 24 opcode handlers: the pattern stepper ---------------------------------------
#
# THE STEPPER IS RECORD-AGNOSTIC, exactly as $18208 is: a0 is its argument and the body has no
# per-channel code (the tick's three `bsr`s are what supply the three addresses, and the tick's own
# battery below runs them). So the opcode grid runs on ONE record and two named cases run the base
# case on the other two — the mutant that buys is a stepper wired to channel A's address, which
# passes every row of the grid on record 0 and fails on records 1 and 2.

# Where a case's own pattern stream, sequence table and follow-on pattern go: past the module's data,
# inside the 32 KiB an a3-relative word can name, and clear of every band anything here writes.
SEEDED_PATTERN = MODULE_BASE + 0x4800
SEEDED_PATTERN_STRIDE = 0x40        # one stream per music channel, so a tick case can walk all three
SEEDED_SEQUENCE_OFFSET = 0x4900     # the a3-relative word the record's +6 holds
SEEDED_SEQUENCE = MODULE_BASE + SEEDED_SEQUENCE_OFFSET
SEEDED_NEXT_PATTERN_OFFSET = 0x4a00
SEEDED_NEXT_PATTERN = MODULE_BASE + SEEDED_NEXT_PATTERN_OFFSET

# A two-entry sequence table and its 0000 terminator. Entry 0 and entry 1 name DIFFERENT patterns, so
# a walk that took the wrong one lands on a different note.
SEEDED_SEQUENCE_BYTES = (SEEDED_NEXT_PATTERN_OFFSET.to_bytes(WORD_LEN, "big")
                         + (SEEDED_NEXT_PATTERN_OFFSET + 4).to_bytes(WORD_LEN, "big")
                         + bytes(WORD_LEN))
SEEDED_NEXT_PATTERN_BYTES = bytes([0x21, 0x00, 0x00, 0x00, 0x42, 0x00, 0x00, 0x00])
FOLLOWING_NOTE = 0x30               # what every opcode stream ends with, so a handler that closed the
                                    # row where it should read on writes no note and reddens

STEP_RECORD_DEFAULTS = {
    **RECORD_DEFAULTS,
    CH_NOISE_TRACKS_NOTE: 0,
    CH_SEQUENCE_OFFSET: SEEDED_SEQUENCE_OFFSET,
    CH_SEQUENCE_INDEX: WORD_LEN,
    CH_DURATION: 4,
    CH_DURATION_RELOAD: 6,          # different from the countdown, so a reload from the wrong field
                                    # cannot look like a countdown that simply did not move
    CH_ENVELOPE_BASE: SEEDED_ENVELOPE,
    CH_YIELD: 0,
}
# EVERY MODULE GLOBAL the stepper reads, pinned rather than left to the keyed seed — the same hazard
# GLOBAL_DEFAULTS exists for one tier down. The three SFX-active flags are the hand-over ladder's
# whole input and sit INSIDE the globals band, so a salt-derived byte there decides the ladder.
STEP_GLOBAL_DEFAULTS = {
    NOISE_ROUTE_MASK: GLOBAL_DEFAULTS[NOISE_ROUTE_MASK],
    **{ACTIVE_FLAGS + channel: 0 for channel in range(CHANNELS)},
}

# The caps, from the bodies' geometry: one pass through $18106 itself, plus the most a single pattern
# byte can cost (the three-instruction read, the four-instruction range decoder and the longest
# handler, $87's sequence walk), plus the stub-and-trigger call opcode $97 makes.
STEP_ROW_INSNS = 40
PATTERN_BYTE_INSNS = 24
STEP_PATTERN_BYTES = 8              # the longest stream any case here walks before a row closes
CHANNEL_STEP_INSN_CAP = (STEP_ROW_INSNS + STEP_PATTERN_BYTES * PATTERN_BYTE_INSNS + STUB_INSN_CAP
                         + leaf.RUNNER_SENTINEL_INSN)

# include/sound.h's `snd_step_result`, restated here because ctypes hands the value back as an int.
# Both members are pinned against the header below, for TICK_D1's reason: sound.h is not scraped.
STEP_RETURNED = 0
STEP_SONG_ENDED = 1
_channel_step = leaf.register_glue("snd_channel_step", [ctypes.c_uint32] * 2, ctypes.c_uint32)

# ...and src/sound.c's `pattern_exit`, which is the three endings the handlers have.
EXIT_READ_NEXT, EXIT_ROW_DONE, EXIT_SONG_ENDED = range(3)


def _module_table_entry(memory, table, index):
    """`add.w d0,d0 / movea.w 0(An,d0.w),An / adda.l a3,An` — one a3-relative word table entry,
    indexed WITHOUT the `ext.w` the two SFX tables are read through."""
    return _module_address(memory.read_word(table + index * TABLE_ENTRY_LEN))


def _seeded_pattern(channel):
    return SEEDED_PATTERN + channel * SEEDED_PATTERN_STRIDE


def _model_next_pattern(memory, record):
    """$1801e — the sequence walk. The reset reloads the table offset WITHOUT the index it had just
    added, so the restarted read takes entry 0 itself and the index is left at 2."""
    table = memory.read_word(record + CH_SEQUENCE_OFFSET)
    index = memory.read_word(record + CH_SEQUENCE_INDEX)
    entry = (table + index) & WORD_MASK
    next_index = (index + TABLE_ENTRY_LEN) & WORD_MASK
    if memory.read_word(_module_address(entry)) == 0:
        entry, next_index = table, TABLE_ENTRY_LEN
    # THE RE-READ COMES FIRST: `movea.w 0(a3,a2.w),a1` at $18036, and only then `move.w d0,10(a0)` at
    # $1803c. A table that names the index field itself therefore reads the OLD index.
    pattern = _module_address(memory.read_word(_module_address(entry)))
    memory.word(record + CH_SEQUENCE_INDEX, next_index)
    return pattern


def _model_noise_route(memory, record, bits, tracks_note):
    """$18044/$18064 — opcodes $8b and $8a, one `eor/and/eor` merge with two masks."""
    mask = memory.read(record + CH_MIXER_MASK)
    routing = memory.read(NOISE_ROUTE_MASK)
    memory.byte(NOISE_ROUTE_MASK, (((mask & bits) ^ routing) & mask) ^ routing)
    memory.byte(record + CH_NOISE_TRACKS_NOTE, tracks_note)


def _model_pattern_opcode(memory, record, index, cursor, trigger_channel):
    """One handler, keyed by the jump table's own index. Returns (exit, cursor)."""
    def operand(at):
        return memory.read_through_pointer(at), (at + 1) & LONGWORD_MASK

    if index == 0x00:                                       # $80 — rest
        memory.byte(record + CH_VOLUME, 0)
        return EXIT_ROW_DONE, cursor
    if index == 0x01:                                       # $81
        memory.byte(record + CH_PORTA_CONTROL, 0)
    elif index == 0x02:                                     # $82
        memory.byte(record + CH_PORTA_CONTROL, CH_PORTA_ENABLED)
    elif index in (0x03, 0x0d):                             # $83 and $8d, one handler
        memory.set_bits(record + CH_FLAGS, CH_FLAG_MARK)
    elif index == 0x04:                                     # $84 — vibrato on
        memory.word(record + CH_VIBRATO_ACC, 0)
        memory.set_bits(record + CH_FLAGS, CH_FLAG_VIBRATO)
        depth, cursor = operand(cursor)
        memory.byte(record + CH_VIBRATO_DEPTH, depth)
        speed, cursor = operand(cursor)
        memory.byte(record + CH_VIBRATO_SPEED, speed)
    elif index in (0x05, 0x06):                             # $86 falls into $85
        if index == 0x06:
            memory.set_bits(record + CH_FLAGS, CH_FLAG_SLIDE_UP)     # $86 FALLS INTO $85's `bset`
        memory.set_bits(record + CH_FLAGS, CH_FLAG_SLIDE)
    elif index == 0x07:                                     # $87
        cursor = _model_next_pattern(memory, record)
    elif index == 0x08:                                     # $88, which falls into $82
        step, cursor = operand(cursor)
        memory.byte(record + CH_PORTA_STEP, step)
        memory.byte(record + CH_PORTA_LIMIT, memory.read_through_pointer(cursor))
        current, cursor = operand(cursor)
        memory.byte(record + CH_PORTA_CURRENT, current)
        memory.byte(record + CH_PORTA_CONTROL, CH_PORTA_ENABLED)
    elif index == 0x09:                                     # $89
        value, cursor = operand(cursor)
        memory.byte(GLOBAL_TRANSPOSE, value)
    elif index == 0x0a:                                     # $8a
        _model_noise_route(memory, record, MIXER_NOISE_BITS, 0)
    elif index == 0x0b:                                     # $8b
        _model_noise_route(memory, record, NOISE_TONE_BITS, CH_TRACKS_NOTE_SET)
    elif index == 0x0c:                                     # $8c
        mask = memory.read(record + CH_MIXER_MASK)
        routing = memory.read(NOISE_ROUTE_MASK)
        memory.byte(NOISE_ROUTE_MASK, routing & (~mask & routing) & BYTE_MASK)
        memory.byte(record + CH_NOISE_TRACKS_NOTE, CH_TRACKS_NOTE_SET)
    elif index == 0x0e:                                     # $8e
        return EXIT_SONG_ENDED, cursor
    elif index == 0x0f:                                     # $8f
        memory.set_bits(record + CH_FLAGS, CH_FLAG_ENVELOPE)
        return EXIT_ROW_DONE, cursor
    elif index == 0x10:                                     # $90
        memory.byte(record + CH_YIELD, CH_YIELD_ASKED)
    elif index == 0x11:                                     # $91
        memory.byte(record + CH_YIELD, 0)
    elif index == 0x12:                                     # $92
        value, cursor = operand(cursor)
        memory.byte(record + CH_DETUNE, value)
    elif index == 0x13:                                     # $93 — two BYTES over one word field
        for offset in range(WORD_LEN):
            value, cursor = operand(cursor)
            memory.byte(record + CH_SEQUENCE_OFFSET + offset, value)
        memory.word(record + CH_SEQUENCE_INDEX, 0)
    elif index == 0x14:                                     # $94
        value, cursor = operand(cursor)
        memory.byte(SONG_SPEED, value)
        memory.byte(SONG_SPEED_COPY, memory.read(SONG_SPEED))
    elif index == 0x15:                                     # $95
        value, cursor = operand(cursor)
        memory.byte(FADE_RATE, value)
        memory.byte(FADE_COUNTDOWN, memory.read(FADE_RATE))
    elif index == 0x16:                                     # $96
        value, cursor = operand(cursor)
        memory.byte(MASTER_VOLUME, value)
    elif index == 0x17:                                     # $97 — on WHATEVER CHANNEL d1 HOLDS
        effect_id, cursor = operand(cursor)
        selector = trigger_channel & BYTE_MASK
        channel = selector if selector < CHANNELS else CHANNELS - 1
        for at, value in expected_writes(memory.mem, effect_id, channel).items():
            for offset, byte in enumerate(value):
                memory.byte(at + offset, byte)
    else:
        raise AssertionError(f"opcode index {index:#x} jumps past the table — no case may reach it")
    return EXIT_READ_NEXT, cursor


def _model_decode_pattern_byte(memory, record, byte, cursor, trigger_channel):
    """$181a6 — the range decoder, whose boundary is $b8 and whose third carry is never tested."""
    if byte < PATTERN_CMD_LIMIT:
        return _model_pattern_opcode(memory, record, byte & PATTERN_CMD_INDEX_MASK, cursor,
                                     trigger_channel)
    decoded = byte + PATTERN_DURATION_BIAS
    if decoded >> 8:
        memory.byte(record + CH_DURATION_RELOAD, (decoded & BYTE_MASK) + PATTERN_DURATION_MIN)
        return EXIT_READ_NEXT, cursor
    decoded = (decoded & BYTE_MASK) + PATTERN_INSTRUMENT_BIAS
    if decoded >> 8:
        stream = _module_table_entry(memory, INSTRUMENT_PTR_TABLE, decoded & BYTE_MASK)
        memory.long(record + CH_ENVELOPE_BASE, stream)
        memory.byte(record + CH_ENVELOPE_SPEED,
                    memory.read_through_pointer((stream - 1) & LONGWORD_MASK))
        return EXIT_READ_NEXT, cursor
    stream = _module_table_entry(memory, ARPEGGIO_PTR_TABLE,
                                 ((decoded & BYTE_MASK) + PATTERN_ARPEGGIO_BIAS) & BYTE_MASK)
    memory.long(record + CH_ARPEGGIO_CURSOR, stream)
    memory.long(record + CH_ARPEGGIO_BASE, stream)
    return EXIT_READ_NEXT, cursor


def _model_channel_step(memory, record, trigger_channel):
    """The whole of $18106, and which of its two endings it took."""
    if memory.decrement(record + CH_DURATION) != 0:
        flags = memory.read(record + CH_FLAGS)
        if flags & CH_FLAG_SLIDE:
            note = memory.read(record + CH_NOTE)
            memory.byte(record + CH_NOTE, note + (1 if flags & CH_FLAG_SLIDE_UP else -1))
        return STEP_RETURNED

    memory.byte(record + CH_FLAGS, 0)
    cursor = memory.read_long(record + CH_PATTERN_CURSOR)
    for _byte in range(STEP_PATTERN_BYTES + 1):
        byte = memory.read_through_pointer(cursor)
        cursor = (cursor + 1) & LONGWORD_MASK
        if byte < PATTERN_NOTE_LIMIT:
            _model_start_note(memory, record, byte)
            break
        exit_kind, cursor = _model_decode_pattern_byte(memory, record, byte, cursor,
                                                       trigger_channel)
        if exit_kind == EXIT_SONG_ENDED:
            return STEP_SONG_ENDED
        if exit_kind == EXIT_ROW_DONE:
            break
    else:
        raise AssertionError("the stream never closed its row inside STEP_PATTERN_BYTES")

    memory.byte(record + CH_DURATION, memory.read(record + CH_DURATION_RELOAD))
    memory.long(record + CH_PATTERN_CURSOR, cursor)
    _model_take_yield(memory, record)
    return STEP_RETURNED


def _model_start_note(memory, record, note):
    """$1811e — the note, and the instrument restart that comes with it."""
    memory.byte(record + CH_NOTE, note)
    if memory.read(record + CH_NOISE_TRACKS_NOTE) != 0:
        memory.byte(NOISE_PERIOD_BASE, note)
    envelope = memory.read_long(record + CH_ENVELOPE_BASE)
    memory.long(record + CH_ENVELOPE_CURSOR, envelope)
    first = memory.read_through_pointer(envelope)
    memory.byte(record + CH_ENVELOPE_LAST, first)
    memory.byte(record + CH_VOLUME, first)
    memory.byte(record + CH_ENVELOPE_COUNT, memory.read(record + CH_ENVELOPE_SPEED))
    memory.set_bits(record + CH_FLAGS, CH_FLAG_ENVELOPE)


def _model_take_yield(memory, record):
    """$18152 — the hand-over, blocked by any ARMED SFX channel whose noise is on."""
    if memory.read(record + CH_YIELD) == 0:
        return
    for channel in range(CHANNELS):
        if (memory.read(ACTIVE_FLAGS + channel) != 0
                and not memory.read(_channel_state(channel) + DESC_MIXER_BITS) & MIXER_NOISE_OFF):
            return
    memory.byte(record + CH_YIELD, CH_YIELD_ASKED)




def _step_pokes(salt, fields_by_record, globals_, streams, extra=None):
    """The module state a stepper case runs on: every mutable band it reads, seeded, then the three
    records, then the case's own streams and globals. The record's pattern CURSOR is injected here
    rather than left to STEP_RECORD_DEFAULTS, because each record walks a stream of its own."""
    records = {}
    for index in range(CHANNELS):
        fields = {CH_PATTERN_CURSOR: _seeded_pattern(index), **fields_by_record.get(index, {})}
        records[_music_channel(index)] = _record_bytes(index, salt, fields, STEP_RECORD_DEFAULTS)
    every_stream = {index: streams.get(index, bytes([FOLLOWING_NOTE])) for index in range(CHANNELS)}
    return overlay(
        {MUSIC_CHANNEL_STATE: leaf.keyed_block(MUSIC_CHANNEL_STATE, MUSIC_STATE_BLOCK_LEN, salt),
         GLOBALS_BLOCK: leaf.keyed_block(GLOBALS_BLOCK, GLOBALS_BLOCK_LEN, salt),
         STATE: leaf.keyed_block(STATE, SFX_STATE_BLOCK_LEN, salt),
         SEEDED_ENVELOPE: SEEDED_ENVELOPE_BYTES,
         SEEDED_ARPEGGIO: SEEDED_ARPEGGIO_BYTES,
         SEEDED_SEQUENCE: SEEDED_SEQUENCE_BYTES,
         SEEDED_NEXT_PATTERN: SEEDED_NEXT_PATTERN_BYTES},
        records,
        {_seeded_pattern(index): stream for index, stream in every_stream.items()},
        {addr: bytes([value]) for addr, value in STEP_GLOBAL_DEFAULTS.items()},
        {addr: bytes([value]) for addr, value in (globals_ or {}).items()},
        extra or {})


def _run_channel_step(index, what, fields=None, globals_=None, stream=None,
                      trigger_channel=0, extra=None):
    """One $18106 differential.

    A3 IS AN ENTRY REGISTER, as it is for $1aaca and $18208: the routine's first instruction is
    `subq.b #1,27(a0)` and not a `lea`, so it inherits the module base from its caller. So is d1,
    which nothing in the routine writes and only opcode $97 reads.
    """
    salt = leaf.case_salt(what)
    streams = {index: bytes([FOLLOWING_NOTE]) if stream is None else stream}
    pokes = _step_pokes(salt, {index: fields or {}}, globals_, streams, extra)
    record = _music_channel(index)

    memory = _Memory(_poked_image(pokes))
    status = _model_channel_step(memory, record, trigger_channel)
    info = leaf.run("snd_channel_step", _channel_step(record, trigger_channel),
                    write_bands(memory.written), what,
                    regs={"a3": MODULE_BASE, "a0": record, "d1": trigger_channel, "_pokes": pokes},
                    max_insns=CHANNEL_STEP_INSN_CAP)
    assert_written(info, memory.written, what)
    assert info["ret"] == status, (
        f"{what}: the reconstruction reported {info['ret']}, not the {status} the model gives")
    return memory


STEP_SEEDED_BANDS = ((MUSIC_CHANNEL_STATE, MUSIC_STATE_BLOCK_LEN),
                     (GLOBALS_BLOCK, GLOBALS_BLOCK_LEN),
                     (STATE, SFX_STATE_BLOCK_LEN))


def test_a_stepper_case_seeds_every_mutable_byte_it_reads():
    """The same guard the tick tier's own cases carry: all three bands ship DIRTY, and the hand-over
    ladder in particular reads the SFX state — so a case that left it on the residue would be
    deciding the ladder from a previous run's leftovers."""
    pokes = _step_pokes(0, {}, None, {0: bytes([FOLLOWING_NOTE])})
    assert_bands_are_seeded(pokes, STEP_SEEDED_BANDS, "a pattern-stepper case")


# --- the countdown and the pitch slide, which is everything a row that is still running does -------
# The mutants these rows buy: a countdown tested BEFORE the decrement rather than after (`bne`
# reads the result), a slide applied with the flag clear, and the two directions swapped.
STEP_COUNTDOWN_CASES = (
    ("a row still running with no slide armed", {CH_DURATION: 4}),
    ("a row still running with the slide armed DOWN", {CH_DURATION: 4, CH_FLAGS: CH_FLAG_SLIDE}),
    ("...and armed UP, which is bit 7 over the same bit 3",
     {CH_DURATION: 4, CH_FLAGS: CH_FLAG_SLIDE | CH_FLAG_SLIDE_UP}),
    ("bit 7 set WITHOUT bit 3, which slides nothing at all", {CH_DURATION: 4,
                                                              CH_FLAGS: CH_FLAG_SLIDE_UP}),
    ("a countdown of exactly TWO, the tick before the row closes", {CH_DURATION: 2,
                                                                    CH_FLAGS: CH_FLAG_SLIDE}),
    ("a countdown of ZERO, which the `subq` WRAPS to $ff rather than closing the row on",
     {CH_DURATION: 0, CH_FLAGS: CH_FLAG_SLIDE}),
    ("a note of $ff sliding UP, which wraps the note byte", {CH_DURATION: 4, CH_NOTE: 0xff,
                                                             CH_FLAGS: CH_FLAG_SLIDE
                                                             | CH_FLAG_SLIDE_UP}),
)


@pytest.mark.parametrize("why,fields", STEP_COUNTDOWN_CASES,
                         ids=[case[0][:40] for case in STEP_COUNTDOWN_CASES])
def test_a_row_that_is_still_running_only_spends_its_countdown_and_slides(why, fields):
    _run_channel_step(CHANNEL_A, why, fields=fields)


@pytest.mark.parametrize("index", range(CHANNEL_A + 1, CHANNELS))
def test_the_stepper_walks_whichever_record_it_is_handed(index):
    """The trim's own justification: $18106 has no per-channel code, so the grids above and below run
    on record 0 alone — and a body that had hardcoded record A's address passes every one of them and
    fails these two, which is the mutant this pair is here to buy."""
    _run_channel_step(index, f"a closing row on record {index}", fields={CH_DURATION: 1})


# --- the note range, and the instrument restart that comes with a note ----------------------------
# The mutants these rows buy: a noise base written whether or not +1 says so (rows 1 and 2 disagree),
# an envelope countdown reloaded from the wrong field, and an envelope cursor left where it was
# rather than reset to the instrument's base — a note RESTARTS the instrument.
STEP_NOTE_CASES = (
    ("a note byte with the noise NOT tracking it", {CH_DURATION: 1}, 0x30),
    ("a note byte with the noise TRACKING it, which also writes the module's noise base",
     {CH_DURATION: 1, CH_NOISE_TRACKS_NOTE: 1}, 0x2a),
    ("note $00, the lowest byte there is", {CH_DURATION: 1, CH_NOISE_TRACKS_NOTE: 1}, 0x00),
    ("note $7f, the last byte the `bmi` calls a note rather than a command",
     {CH_DURATION: 1}, 0x7f),
    ("a note whose envelope stream begins with a NEGATIVE byte, which is taken as the volume anyway "
     "because only $18208's own peek tests the sign", {CH_DURATION: 1,
                                                       CH_ENVELOPE_BASE: SEEDED_ENVELOPE + 4}, 0x40),
)


@pytest.mark.parametrize("why,fields,note", STEP_NOTE_CASES,
                         ids=[f"note_{case[2]:02x}" for case in STEP_NOTE_CASES])
def test_a_note_byte_closes_the_row_and_restarts_the_instrument(why, fields, note):
    _run_channel_step(CHANNEL_A, why, fields=fields, stream=bytes([note]))


# --- the twenty-four opcodes ----------------------------------------------------------------------
#
# THE CENSUS BELOW IS DERIVED, not transcribed: `_shipped_pattern_census` decodes every pattern the 17
# songs reach and counts what it finds, so the "shipped data reaches this handler" column on each row
# is the DATA's claim and not a note's. Eleven of the twenty-four are reached; the other thirteen are
# pinned from a seeded stream and each says so.

SONG_DIRECTORY = leaf.entry_of("snd_song_directory")
SONG_RECORD_LEN = 8                 # `mulu.w #8,d0` in snd_play_song
SONG_SEQUENCE_FIELD = 2             # the first of the three per-channel sequence offsets
SONGS = 17                          # 17 records; the 18th address is already sequence data
SHIPPED_PATTERNS = 106              # what the walk must find, and what ../notes says it finds
SHIPPED_SEQUENCE_TABLES = CHANNELS * SONGS  # one per song per channel, and all 51 distinct
END_SONG_OPCODE = PATTERN_NOTE_LIMIT + PATTERN_OPCODE_OF_HANDLER[
    PATTERN_HANDLER_NAMES.index("snd_pattern_op_8e_end_song")]
NEXT_PATTERN_OPCODE = PATTERN_NOTE_LIMIT + PATTERN_OPCODE_OF_HANDLER[
    PATTERN_HANDLER_NAMES.index("snd_pattern_op_87_next_pattern")]
SET_SEQUENCE_OPCODE = PATTERN_NOTE_LIMIT + PATTERN_OPCODE_OF_HANDLER[
    PATTERN_HANDLER_NAMES.index("snd_pattern_op_93_set_sequence")]
TRIGGER_SFX_OPCODE = PATTERN_NOTE_LIMIT + PATTERN_OPCODE_OF_HANDLER[
    PATTERN_HANDLER_NAMES.index("snd_pattern_op_97_trigger_sfx")]

# The three range floors, DERIVED from the decoder's own biases rather than transcribed: each
# `addi.b` carries exactly when the byte has reached $100 minus the biases still to come.
PATTERN_DURATION_MIN_BYTE = BYTE_LIMIT - PATTERN_DURATION_BIAS
PATTERN_INSTRUMENT_MIN_BYTE = PATTERN_DURATION_MIN_BYTE - PATTERN_INSTRUMENT_BIAS
PATTERN_ARPEGGIO_MIN_BYTE = PATTERN_INSTRUMENT_MIN_BYTE - PATTERN_ARPEGGIO_BIAS


def _shipped_sequence_tables():
    """Every sequence table the 17 songs reach, as {start: end} with `end` one past the 0000
    terminator, plus every pattern address they name.

    THE TABLES ARE NOT ONE BAND. ../notes/sound_module_recon.md's map shows 28 bytes at $18508, which
    is song 0's three; the 51 of them are interleaved with the pattern data and span $18508..$1a42a.
    Their extents are returned because the census's own closure guard needs them.
    """
    image = harness.BASE_IMAGE
    tables, patterns = {}, set()
    for song in range(SONGS):
        record = SONG_DIRECTORY + song * SONG_RECORD_LEN
        for channel in range(CHANNELS):
            table = _module_address(leaf.u16(image, record + SONG_SEQUENCE_FIELD
                                             + channel * TABLE_ENTRY_LEN))
            index = 0
            while leaf.u16(image, table + index) != 0:
                patterns.add(_module_address(leaf.u16(image, table + index)))
                index += TABLE_ENTRY_LEN
            tables[table] = table + index + TABLE_ENTRY_LEN
    return tables, patterns


SHIPPED_TABLES, SHIPPED_PATTERN_ADDRESSES = _shipped_sequence_tables()


def _derived_operand_lengths():
    """How many bytes each opcode takes out of the pattern stream, DERIVED from the MODEL's own
    cursor rather than transcribed.

    That closes the loop the census would otherwise dangle on: the entry pin checks each handler's
    `move.b (a1)+` instructions against the image, the differential checks the model against the
    original, and this reads the count back out of the model — so the published reachability column
    rests on the run and not on a third hand-written table. The finder's construction was $89
    transcribed as taking no operand: its operand byte then decodes as a NOTE and the census set
    comes out unchanged.

    A handler that REPLACES the cursor consumed nothing from the stream ($87's sequence walk is the
    only one), which the window test below is what says — not a name.
    """
    lengths = {}
    window = _seeded_pattern(CHANNEL_A)
    pokes = _step_pokes(0, {}, None, {CHANNEL_A: bytes([SHIPPED_CALL_IDS[0]]) * SEEDED_OPERAND_BYTES})
    for index in range(PATTERN_OPCODES):
        memory = _Memory(_poked_image(pokes))
        _exit, after = _model_pattern_opcode(memory, _music_channel(CHANNEL_A), index, window, 0)
        lengths[PATTERN_NOTE_LIMIT + index] = (after - window
                                               if window <= after < window + SEEDED_PATTERN_STRIDE
                                               else 0)
    return lengths


SEEDED_OPERAND_BYTES = 4            # more than any handler takes, so the derivation never runs off
PATTERN_OPCODE_OPERAND_LEN = _derived_operand_lengths()


def _shipped_pattern_census():
    """What the shipped patterns decode to: {opcode: count}, {arpeggio byte: count}, {instrument
    byte: count}, and every place opcode $93 RE-POINTS a channel's sequence table.

    A pattern's byte stream ends on whichever of $87 and $8e it reaches, since both leave it. Bytes
    at or above $b8 are counted by RANGE rather than skipped, so the plate's arpeggio and instrument
    tails are the walk's claims too.
    """
    image = harness.BASE_IMAGE
    census, arpeggios, instruments, aliased, retargets = {}, {}, {}, {}, []
    for pattern in SHIPPED_PATTERN_ADDRESSES:
        at = pattern
        while True:
            byte = image[at]
            at += 1
            if byte < PATTERN_NOTE_LIMIT:
                continue                                            # a note
            if byte >= PATTERN_CMD_LIMIT:
                bucket = (aliased if byte < PATTERN_ARPEGGIO_MIN_BYTE else
                          arpeggios if byte < PATTERN_INSTRUMENT_MIN_BYTE else
                          instruments if byte < PATTERN_DURATION_MIN_BYTE else None)
                if bucket is not None:
                    bucket[byte] = bucket.get(byte, 0) + 1
                continue                                            # ...or a duration
            census[byte] = census.get(byte, 0) + 1
            if byte == SET_SEQUENCE_OPCODE:
                retargets.append(_module_address(leaf.u16(image, at)))
            at += PATTERN_OPCODE_OPERAND_LEN.get(byte, 0)
            if byte in (NEXT_PATTERN_OPCODE, END_SONG_OPCODE):
                break
    return census, arpeggios, instruments, aliased, retargets


(SHIPPED_OPCODE_CENSUS, SHIPPED_ARPEGGIOS, SHIPPED_INSTRUMENTS, SHIPPED_ALIASED_ARPEGGIOS,
 SHIPPED_RETARGETS) = _shipped_pattern_census()
TESTABLE_OPCODES = tuple(op for op in range(PATTERN_NOTE_LIMIT, PATTERN_NOTE_LIMIT + PATTERN_OPCODES)
                         if op != END_SONG_OPCODE)
# One stream per opcode that takes operands. The values are unremarkable except where the field is
# read straight back — $93's two bytes are the seeded sequence table's own offset, so the record
# stays walkable, and $97's is an id the game itself passes.
PATTERN_OPCODE_OPERANDS = {
    0x84: bytes([0x03, 0x05]),
    0x88: bytes([0x06, 0x40]),
    0x89: bytes([0x0c]),
    0x92: bytes([0xf8]),
    0x93: SEEDED_SEQUENCE_OFFSET.to_bytes(WORD_LEN, "big"),
    0x94: bytes([0x31]),
    0x95: bytes([0x0a]),
    0x96: bytes([0x0b]),
}


def _opcode_stream(opcode_byte):
    """The opcode, its operands, and a NOTE behind them — so a handler that closed the row where it
    should have read on writes no note at all and reddens on the record's own bytes."""
    operands = PATTERN_OPCODE_OPERANDS.get(opcode_byte, b"")
    if opcode_byte == TRIGGER_SFX_OPCODE:                    # $97's operand is an SFX id
        operands = bytes([SHIPPED_CALL_IDS[0]])
    return bytes([opcode_byte]) + operands + bytes([FOLLOWING_NOTE])


@pytest.mark.parametrize("opcode_byte", TESTABLE_OPCODES,
                         ids=[f"op_{op:02x}" for op in TESTABLE_OPCODES])
def test_every_pattern_opcode_runs_the_handler_its_table_entry_names(opcode_byte):
    """One row per table entry, $8d included — it is a SECOND entry pointing at $83's handler, and
    running both is what says the table aliases rather than that the battery believes it does.

    $8e is the one opcode with no row here and cannot have one: its `addq.l #4,sp` pops the runner's
    own sentinel, so a standalone run would `rts` into nothing. It is pinned from the TICK's entry
    instead, where the stack holds the frame the instruction expects.
    """
    reached = SHIPPED_OPCODE_CENSUS.get(opcode_byte, 0)
    seeded = "" if reached else " (SEEDED: no shipped pattern contains this byte)"
    what = f"pattern opcode {opcode_byte:#04x}, reached {reached} times by the shipped data{seeded}"
    _run_channel_step(CHANNEL_A, what, fields={CH_DURATION: 1}, stream=_opcode_stream(opcode_byte))


# The two bytes the `cmp.b #$b8` keeps that the 24-entry table does not have: the first past it and
# the last before the arpeggio range. The original `jmp`s through a word of its own instruction
# stream for both, so neither can be a differential — what CAN be pinned is the refusal.
OUT_OF_RANGE_OPCODES = (PATTERN_NOTE_LIMIT + PATTERN_OPCODES, PATTERN_CMD_LIMIT - 1)
_channel_step_fn = leaf.bind("snd_channel_step", leaf.IMAGE_ARG + [ctypes.c_uint32] * 2,
                             ctypes.c_uint32)


def _refusals_stepping(stream):
    """Drive the CANDIDATE alone over ``stream`` and return its refusal tally.

    Alone, because there is no oracle run to pair it with: the original's answer to a $98 is a `jmp`
    through a word of the handlers' own code, which is not a run any differential can hold. The kit
    already has the mechanism for exactly this — `os_refused` tallies and harness.differential()
    raises on a non-zero candidate tally (tools/recreate_kit/include/os.h) — so all this has to show
    is that the reconstruction reaches it.
    """
    pokes = _step_pokes(0, {CHANNEL_A: {CH_DURATION: 1}}, None, {CHANNEL_A: stream})
    buffer = bytearray(_poked_image(pokes))
    image = (ctypes.c_uint8 * len(buffer)).from_buffer(buffer)
    harness._lib.g_os_refusal_reset()
    _channel_step_fn(image, _music_channel(CHANNEL_A), 0)
    return harness._lib.g_os_refusal_count()


@pytest.mark.parametrize("opcode_byte", OUT_OF_RANGE_OPCODES,
                         ids=[f"op_{op:02x}" for op in OUT_OF_RANGE_OPCODES])
def test_an_out_of_range_pattern_opcode_is_REFUSED_rather_than_walked_past(opcode_byte):
    """THE ALTITUDE THE `default:` ARM NEEDED. Returning PATTERN_READ_NEXT there and documenting it
    made an unported branch indistinguishable from an ordinary opcode to everything that is not a
    differential; `os_refused` makes it distinguishable to the harness, so a case that ever seeded
    such a byte is thrown away instead of compared against a fall-through the original does not do.

    The reachability claim is the census's ($98..$b7 occurs nowhere in the shipped patterns); this is
    what happens if it is ever wrong.
    """
    assert _refusals_stepping(bytes([opcode_byte, FOLLOWING_NOTE])) == 1, (
        f"a pattern byte of {opcode_byte:#04x} walked on instead of refusing")


def test_an_in_range_opcode_leaves_the_refusal_tally_alone():
    """The guard that keeps the pair above from passing on a tally something else raised — and the
    reason the whole suite is not one long refusal: every differential run in this file goes through
    a harness that clears the tally first and RAISES on a non-zero one afterwards."""
    assert _refusals_stepping(bytes([END_SONG_OPCODE - 1, FOLLOWING_NOTE])) == 0


def test_the_opcode_grid_covers_every_entry_the_jump_table_holds():
    """The guard on the grid: 24 entries, one row each bar $8e, whose reason is in the docstring."""
    assert len(TESTABLE_OPCODES) == PATTERN_OPCODES - 1
    assert END_SONG_OPCODE not in TESTABLE_OPCODES
    assert set(TESTABLE_OPCODES) | {END_SONG_OPCODE} == set(
        range(PATTERN_NOTE_LIMIT, PATTERN_NOTE_LIMIT + PATTERN_OPCODES))


def test_the_shipped_song_data_reaches_eleven_of_the_twenty_four_opcodes():
    """The census, and its own self-proof: every one of the 106 patterns ends in $87 or $8e, so those
    two counts have to add up to the pattern count exactly. That is what says the walk decoded the
    operand lengths right — a wrong one would desynchronise and land on rubbish."""
    assert len(SHIPPED_PATTERN_ADDRESSES) == SHIPPED_PATTERNS
    assert (SHIPPED_OPCODE_CENSUS[NEXT_PATTERN_OPCODE] + SHIPPED_OPCODE_CENSUS[END_SONG_OPCODE]
            == SHIPPED_PATTERNS), f"the census does not tile the patterns: {SHIPPED_OPCODE_CENSUS}"
    assert set(SHIPPED_OPCODE_CENSUS) == {0x80, 0x81, 0x82, 0x87, 0x88, 0x89, 0x8a, 0x8e, 0x8f,
                                          0x92, 0x93}, (
        f"the shipped data reaches {sorted(hex(op) for op in SHIPPED_OPCODE_CENSUS)}")
    # ...and the claim src/sound.c's unported `default:` rests on: the walk counts EVERY byte in
    # $80..$b7, so an out-of-range command anywhere in the data would appear here as an opcode above
    # the table's last entry. None does.
    assert max(SHIPPED_OPCODE_CENSUS) < PATTERN_NOTE_LIMIT + PATTERN_OPCODES, (
        f"a shipped pattern byte indexes past the jump table: {sorted(SHIPPED_OPCODE_CENSUS)}")


def test_the_census_walk_is_CLOSED_under_the_retargets_opcode_93_makes():
    """THE GUARD THE WALK'S 106 RESTS ON, and the one thing the tiling above cannot say.

    Opcode $93 re-points a channel's sequence table from two pattern bytes, so a pattern can send the
    replayer at a table the walk never visited — and the walk starts from the song directory alone.
    Today's three $93s all name mid-table tails of tables the walk already has, so the set really is
    closed; without this, a fresh-table $93 in different data would shrink the reachable set silently
    while 95 + 11 = 106 still passed, because both sides of the tiling would shrink together.
    """
    assert len(SHIPPED_RETARGETS) == SHIPPED_OPCODE_CENSUS[SET_SEQUENCE_OPCODE]
    for retarget in SHIPPED_RETARGETS:
        assert any(start <= retarget < end for start, end in SHIPPED_TABLES.items()), (
            f"opcode $93 re-points at {retarget:#x}, which is inside no table the walk visited — the "
            f"census is no longer closed and its 106 is a floor, not a count")


def test_the_shipped_sequence_tables_are_not_one_band_and_clear_every_music_record():
    """The corrected span, and the conclusion that rests on it. ../notes' module map shows 28 bytes
    at $18508, which is song 0's THREE tables; the 51 of them are interleaved with the pattern data.
    What the aliasing case above needs is only the second half — that none of them can name a byte of
    a music channel record — and that survives the correction with room to spare."""
    assert len(SHIPPED_TABLES) == SHIPPED_SEQUENCE_TABLES
    starts, ends = sorted(SHIPPED_TABLES), sorted(SHIPPED_TABLES.values())
    assert (starts[0], ends[-1]) == (0x18508, 0x1a42a), (
        f"the tables span {starts[0]:#x}..{ends[-1]:#x}")
    runs = leaf.merge_bands({at for start, end in SHIPPED_TABLES.items() for at in range(start, end)})
    assert len(runs) > 1, "the tables must not be one contiguous band — the map's row implies they are"
    assert sum(length for _start, length in runs) < ends[-1] - starts[0], (
        "...and the gaps between the runs are the pattern data they are interleaved with")
    records = (MUSIC_CHANNEL_STATE, MUSIC_CHANNEL_STATE + MUSIC_STATE_BLOCK_LEN)
    for start, end in SHIPPED_TABLES.items():
        assert start >= records[1] or end <= records[0], (
            f"the table at {start:#x} overlaps the music channel records")


def test_the_arpeggio_and_instrument_bytes_the_shipped_data_selects():
    """The plate's two tail claims, made by the WALK: the census counts bytes at or above $b8 by
    range, so `only $cf, twice` and `thirteen instruments, not the fifteen the range spans` are the
    data's statements. It also says NO shipped byte falls in $b8..$bf, which is what makes that whole
    range's case a seeded one."""
    assert SHIPPED_ARPEGGIOS == {0xcf: 2}, f"the arpeggio bytes are {SHIPPED_ARPEGGIOS}"
    assert SHIPPED_ALIASED_ARPEGGIOS == {}, (
        f"a shipped byte falls in the aliased arpeggio range: {SHIPPED_ALIASED_ARPEGGIOS}")
    assert set(SHIPPED_INSTRUMENTS) == {0xd0, 0xd1} | set(range(0xd4, 0xdf)), (
        f"the instrument bytes are {sorted(hex(b) for b in SHIPPED_INSTRUMENTS)}")
    assert len(SHIPPED_INSTRUMENTS) == 13, "thirteen distinct instruments, not the range's fifteen"


def test_the_three_range_floors_come_out_of_the_decoders_own_biases():
    """...and the ranges the census sorts by are the DECODER's, derived from the three `addi.b`
    immediates rather than transcribed as $c0/$d0/$e0."""
    assert (PATTERN_ARPEGGIO_MIN_BYTE, PATTERN_INSTRUMENT_MIN_BYTE,
            PATTERN_DURATION_MIN_BYTE) == (0xc0, 0xd0, 0xe0)
    assert PATTERN_CMD_LIMIT < PATTERN_ARPEGGIO_MIN_BYTE, (
        "the command range must end BELOW the arpeggio floor — that gap is $b8..$bf")


def test_the_operand_lengths_the_census_uses_come_out_of_the_model():
    """The guard on `_derived_operand_lengths`: the model is what the differential pins, so a length
    read back out of it is pinned too — but only if the derivation actually found some. A dict of
    all-zeroes would desynchronise the walk, which the tiling would then catch; a dict with ONE wrong
    zero is the case that motivated it, and this says which opcodes take operands at all."""
    taking = {op for op, count in PATTERN_OPCODE_OPERAND_LEN.items() if count}
    assert taking == {0x84, 0x88, 0x89, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97}
    assert PATTERN_OPCODE_OPERAND_LEN[NEXT_PATTERN_OPCODE] == 0, (
        "$87 REPLACES the cursor and consumes nothing from the stream")
    assert max(PATTERN_OPCODE_OPERAND_LEN.values()) < SEEDED_OPERAND_BYTES


# --- opcode $97, the module's one latent defect ---------------------------------------------------
# It sets d0 and never d1, so the effect lands on whatever channel the caller left there. Every one of
# these is SYNTHETIC: the byte occurs nowhere in the shipped data, so nothing has ever heard it.
TRIGGER_SELECTORS = (0, 1, 2, 0xff)


@pytest.mark.parametrize("selector", TRIGGER_SELECTORS, ids=[f"d1_{s:02x}" for s in
                                                             TRIGGER_SELECTORS])
def test_opcode_97_arms_whichever_channel_the_entry_d1_happens_to_hold(selector):
    """REPRODUCED, NOT FIXED. The four selectors are snd_trigger_effect's own three arms plus the
    `anything else is C` one, so a port that had quietly passed channel A fails on three of them."""
    what = (f"pattern opcode $97 entered with d1 = {selector:#04x} — the latent defect, and a "
            f"SEEDED stream: $97 occurs zero times in the shipped patterns")
    _run_channel_step(CHANNEL_A, what, fields={CH_DURATION: 1},
                      stream=_opcode_stream(TRIGGER_SFX_OPCODE), trigger_channel=selector)


# --- the range decoder past the command range -----------------------------------------------------
STEP_RANGE_CASES = (
    (0xb8, "the FIRST byte the `cmp.b #$b8` sends past the command range: its decoded arpeggio index "
           "is $f8, sixteen entries PAST the 16-word table the $c0 arm reads"),
    (0xbf, "...and the last of them, at index $ff"),
    (0xc0, "arpeggio 0, the first index the table really holds"),
    (0xcf, "arpeggio 15 — the ONLY arpeggio byte anywhere in the shipped data, twice"),
    (0xd0, "instrument 0, whose envelope SPEED is the byte below its stream"),
    (0xde, "instrument 14, the last one the shipped data selects"),
    (0xdf, "instrument 15, which no shipped pattern selects"),
    (0xe0, "a duration byte of $e0, which is ONE row"),
    (0xff, "...and $ff, which is 32 — the two ends of the last range"),
)


@pytest.mark.parametrize("byte,why", STEP_RANGE_CASES, ids=[f"byte_{c[0]:02x}" for c in
                                                            STEP_RANGE_CASES])
def test_a_pattern_byte_above_the_command_range_decodes_by_its_range(byte, why):
    """The chain of `addi.b`+`bcs`, each boundary from both sides. The mutant the $b8/$c0 pair buys is
    a decoder written as a MASK (`byte & $0f`), which agrees with the adds on $c0..$ff and sends
    $b8..$bf to arpeggio 8..15 instead of past the table."""
    _run_channel_step(CHANNEL_A, f"a pattern byte of {byte:#04x} — {why}", fields={CH_DURATION: 1},
                      stream=bytes([byte, FOLLOWING_NOTE]))


def test_the_range_sweep_reaches_both_sides_of_all_three_boundaries():
    """The guard on the sweep above: each of the decoder's three carries has to be produced AND not
    produced, or a boundary written one off would agree with every row."""
    seen = {byte for byte, _why in STEP_RANGE_CASES}
    for boundary in (0xc0, 0xd0, 0xe0):
        assert boundary in seen and any(boundary - 0x10 <= byte < boundary for byte in seen), (
            f"the sweep does not bracket {boundary:#04x} from both sides")
    # $b8's own lower side is the OPCODE grid, every row of which is a byte the `cmp.b` keeps.
    assert PATTERN_CMD_LIMIT in seen and max(TESTABLE_OPCODES) < PATTERN_CMD_LIMIT


# --- opcode $87: the sequence walk ----------------------------------------------------------------
SEQUENCE_CASES = (
    (WORD_LEN, "the second entry, which the walk takes and then leaves the index at 4"),
    (2 * WORD_LEN, "the 0000 TERMINATOR, which restarts at entry 0 and leaves the index at 2 — and "
                   "takes entry 0 itself, because the reset reloads the table offset without the "
                   "index it had just added to it"),
)


@pytest.mark.parametrize("index,why", SEQUENCE_CASES, ids=["entry_1", "terminator"])
def test_the_sequence_walk_advances_and_restarts(index, why):
    """The mutant the terminator row buys is a restart that took entry 0 PLUS one — the `moveq #2,d0`
    sets the index the walk leaves, not the entry it reads."""
    _run_channel_step(CHANNEL_A, f"opcode $87 with the sequence index at {index} — {why}",
                      fields={CH_DURATION: 1, CH_SEQUENCE_INDEX: index},
                      stream=bytes([NEXT_PATTERN_OPCODE]))


# A sequence table whose entry IS the record's own index word, which is what tells $18036's re-read
# apart from $1803c's store. Solve `(offset + index) & $ffff` for the a3-relative offset of the index
# field, so that the entry the walk resolves is the index it is about to overwrite: the entry it must
# read is the OLD index, and the module offset that index names is the case's own seeded pattern.
# The index names SEEDED_NEXT_PATTERN and NOT the case's own stream: the stream still has to be the
# $87 that starts the walk, so the pattern the walk RESOLVES has to be a different one.
SELF_NAMING_INDEX = SEEDED_NEXT_PATTERN_OFFSET
SELF_NAMING_OFFSET = (_module_displacement(_music_channel(CHANNEL_A) + CH_SEQUENCE_INDEX)
                      - SELF_NAMING_INDEX) & WORD_MASK


def test_the_sequence_entry_is_re_read_before_the_new_index_is_stored():
    """THE REVIEW GATE'S FINDING, and the only shape that can show it: `movea.w 0(a3,a2.w),a1` at
    $18036 fetches the entry again and `move.w d0,10(a0)` at $1803c stores the new index AFTER it, so
    a table that names the index field itself resolves the OLD index.

    A port that stored first resolves the index PLUS two and starts the row two bytes into the
    pattern — a different note. Only a SEEDED table can reach it: the 51 shipped tables span
    $18508..$1a42a in seventeen disjoint runs (interleaved with the pattern data, not one band), and
    the lowest byte any of them names is $18508 — above every record.
    """
    _run_channel_step(CHANNEL_A,
                      "opcode $87 over a sequence table that names the index word it is about to "
                      "write",
                      fields={CH_DURATION: 1, CH_SEQUENCE_OFFSET: SELF_NAMING_OFFSET,
                              CH_SEQUENCE_INDEX: SELF_NAMING_INDEX},
                      stream=bytes([NEXT_PATTERN_OPCODE]))


def test_the_self_naming_sequence_table_really_does_alias_the_index_word():
    """The guard on the case above: without the alias it is an ordinary walk and proves nothing."""
    entry = (SELF_NAMING_OFFSET + SELF_NAMING_INDEX) & WORD_MASK
    assert _module_address(entry) == _music_channel(CHANNEL_A) + CH_SEQUENCE_INDEX
    assert _module_address(SELF_NAMING_INDEX) == SEEDED_NEXT_PATTERN
    assert SEEDED_NEXT_PATTERN_BYTES[0] != SEEDED_NEXT_PATTERN_BYTES[TABLE_ENTRY_LEN], (
        "the two notes a store-first port would tell apart must differ")


# Every value this battery restates from include/sound.h, which layout.py does not scrape (none of
# them carries a WB_ prefix and none is a game constant, so `wb()` cannot reach them). CLAUDE.md's
# cross-language rule asks for one canonical definition or a test that pins the copy; the header is
# canonical and this is the test.
SOUND_H_CONSTANTS = {
    "SND_TRIGGER_CHANNEL_UNMODELLED": lambda: TICK_D1,
    "SND_STEP_RETURNED": lambda: STEP_RETURNED,
    "SND_STEP_SONG_ENDED": lambda: STEP_SONG_ENDED,
}


@pytest.mark.parametrize("name", sorted(SOUND_H_CONSTANTS))
def test_a_value_this_battery_restates_from_sound_h_is_the_headers_own(name):
    """A divergence here is silent in both directions: the enum comes back through ctypes as a bare
    int, and the unmodelled d1 is only ever read by an opcode no case may reach."""
    header = (pathlib.Path(__file__).resolve().parents[1] / "include" / "sound.h").read_text()
    declared = re.search(rf"\b{name}\s*=?\s*(\d+)", header)
    assert declared, f"include/sound.h no longer declares {name}"
    assert int(declared.group(1)) == SOUND_H_CONSTANTS[name](), (
        f"the header says {declared.group(1)} and this battery says "
        f"{SOUND_H_CONSTANTS[name]()}")


# --- the hand-over ladder at $18152 ---------------------------------------------------------------
# Three `tst`/`btst` pairs whose only shared exit is the `rts`, so ONE armed SFX channel with its
# noise on blocks the hand-over. The mutants: a ladder that tested only channel A (rows 1..3 differ),
# and one that read a neighbour's state block (the per-channel rows differ from each other).
NOISE_ON = 0x00                     # descriptor +6 bit 3 CLEAR is noise ON, in PSG polarity
NOISE_OFF = MIXER_NOISE_OFF


def _sfx_mixer_bytes(per_channel):
    """The three SFX channel states' descriptor +6, as a poke layer — the one byte per channel the
    hand-over ladder and the tick's mixdown both read."""
    return {_channel_state(channel) + DESC_MIXER_BITS: bytes([per_channel[channel]])
            for channel in range(CHANNELS)}


# The mixer byte is two-valued here, so the axis is not "three different bytes": it is that in every
# DECIDING row the channel whose noise is on DISAGREES with channel A's byte, and that two rows leave
# a noise bit on with nothing armed. Both shapes are the first sweep pass's findings and each names
# its mutant. Rows 5 and 6 kill "every rung reads channel A's state block" — A holds NOISE_OFF while
# the deciding channel holds NOISE_ON, so a ladder that read A's block never blocks. ROW 2 IS NOT
# TRIMMABLE: it is the only row where a noise bit is on and no flag is set, so it alone kills "the
# `tst.b` on the flag dropped", which every other row agrees with.
YIELD_LADDER_CASES = (
    ((), (NOISE_OFF, NOISE_OFF, NOISE_OFF),
     "nothing armed: the ladder falls all the way through and the channel is taken"),
    ((), (NOISE_ON, NOISE_ON, NOISE_ON),
     "nothing armed but every descriptor's noise ON — the `tst.b` on the flag is the whole of what "
     "keeps the hand-over"),
    ((0, 1, 2), (NOISE_OFF, NOISE_OFF, NOISE_OFF),
     "all three armed with their noise OFF, which does not block it"),
    ((0,), (NOISE_ON, NOISE_OFF, NOISE_OFF),
     "channel A armed with its noise ON — refused on the first rung"),
    ((1,), (NOISE_OFF, NOISE_ON, NOISE_OFF),
     "channel B armed with its noise ON, which ONLY B's own state block can say"),
    ((2,), (NOISE_OFF, NOISE_OFF, NOISE_ON),
     "channel C armed with its noise ON, the last rung"),
    ((0,), (NOISE_OFF, NOISE_ON, NOISE_ON),
     "channel A armed with its noise OFF while the two SILENT channels have theirs ON — taken"),
)


@pytest.mark.parametrize("armed,mixer_bits,why", YIELD_LADDER_CASES,
                         ids=[f"armed_{''.join(str(c) for c in case[0]) or 'none'}_"
                              f"{''.join(f'{b:02x}' for b in case[1])}"
                              for case in YIELD_LADDER_CASES])
def test_the_hand_over_ladder_is_blocked_by_any_armed_sfx_channel_with_its_noise_on(armed,
                                                                                    mixer_bits, why):
    _run_channel_step(CHANNEL_A, f"a yielding channel with {why}",
                      fields={CH_DURATION: 1, CH_YIELD: 1},
                      globals_={ACTIVE_FLAGS + channel: (ACTIVE if channel in armed else 0)
                                for channel in range(CHANNELS)},
                      extra=_sfx_mixer_bytes(mixer_bits))


def test_the_hand_over_case_that_is_refused_leaves_the_flag_as_it_found_it():
    """Stated as its own claim, because the ladder's refusal writes NOTHING — a port that stored the
    flag back unchanged would leave the same image and the same write set."""
    what = "a hand-over refused by channel B's armed noise"
    pokes = _step_pokes(leaf.case_salt(what), {CHANNEL_A: {CH_DURATION: 1, CH_YIELD: 1}},
                        {ACTIVE_FLAGS + 1: ACTIVE}, {CHANNEL_A: bytes([FOLLOWING_NOTE])},
                        _sfx_mixer_bytes((NOISE_OFF, NOISE_ON, NOISE_OFF)))
    record = _music_channel(CHANNEL_A)
    memory = _Memory(_poked_image(pokes))
    _model_channel_step(memory, record, 0)
    assert record + CH_YIELD not in memory.written, (
        "the refusal must write nothing at all: the model stored the yield flag back")


# --- $17ca0: the tick body ------------------------------------------------------------------------
#
# THE TOP OF THE TIER, and the only routine here that drives the chip on a path other than silence.
# Every case declares the mixer with `psg_seed` for the same reason snd_psg_silence's do: $17f08
# reads register 7 back and the merge keeps the bits the module does not own, so the byte the chip
# held is an INPUT of the run and inventing it would be a false green.
#
# THE CASES HERE ENTER BELOW THE TEMPO HEAD, and that is now a case-design choice rather than a
# boundary: they POKE WB_SND_TICK_DROP_VALUE, so all three of the values the head can write are
# reached with no machine to declare. The head itself is the section after next, entered at $17c74
# with `hw_seed=` — and a tiling case there is what says the byte these poke is the byte it writes.

TICK_BODY_INSNS = 160           # $17ca0's own instruction count, 644 bytes at ~4 bytes each
TICK_INSN_CAP = (TICK_BODY_INSNS + SFX_TICK_INSN_CAP + CHANNELS * CHANNEL_STEP_INSN_CAP
                 + CHANNELS * PERIOD_VOLUME_INSN_CAP + STOP_INSN_CAP + leaf.RUNNER_SENTINEL_INSN)
_tick = leaf.image_glue("snd_music_tick_body")

# The three values the tempo selector can leave in WB_SND_TICK_DROP_VALUE, and nothing else can —
# from the header the reconstruction reads, so this file cannot state a value the port does not.
TICK_DROP_VALUES = (TICK_DROP_50HZ, TICK_DROP_60HZ, TICK_DROP_MONO)
TICK_MIXER = MIXER_DIRECTION_BITS   # what TOS leaves: both port-direction bits set,
                                # which is the same byte and the same meaning as the
                                # stop chain's own MIXER_SEEDS[0]
ENGINE_ENABLED_SET = 0xff       # `st 2250(a3)` in snd_play_song
SONG_LOADED_SET = 0xff
TICK_SONG_SPEED = 0x30          # song 0's own speed byte — a row every 5.3 ticks
TICK_D1 = 0                     # include/sound.h's SND_TRIGGER_CHANNEL_UNMODELLED

# EVERY MODULE GLOBAL the tick reads, pinned rather than left to the keyed seed — GLOBAL_DEFAULTS'
# hazard one tier up, and with more to lose: the gate, the dropper, the fade and the row rate are all
# bytes of the same dirty band, so a salt-derived one would decide which arms a case ran.
TICK_GLOBAL_DEFAULTS = {
    **GLOBAL_DEFAULTS,
    **STEP_GLOBAL_DEFAULTS,
    ACTIVE_FLAGS + CHANNELS: 0,             # the pad byte the gate's `tst.l` also reads
    ENGINE_ENABLED: ENGINE_ENABLED_SET,
    MASTER_VOLUME: MASTER_VOLUME_FULL,
    SONG_SPEED: TICK_SONG_SPEED,
    SONG_SPEED_COPY: TICK_SONG_SPEED,
    SONG_LOADED: SONG_LOADED_SET,
    FADE_RATE: 0,
    FADE_COUNTDOWN: 0,
    SPEED_ACC: 0,
    NOISE_PERIOD_OUT: 0,
    PERIOD_SCRATCH: 0,
    PERIOD_SCRATCH + 1: 0,
    TICK_DROP_VALUE: 0,
    TICK_DROP_ACC: 0,
    **{CHANNEL_LOCKS + byte: 0 for byte in range(CHANNEL_LOCKS_LEN)},
}
# ...and the header names those addresses are reached by, so the guard below can say WHICH global the
# body reads that no default pins.
TICK_GLOBAL_NAMES = {
    "SND_ENGINE_ENABLED": ENGINE_ENABLED, "SND_MASTER_VOLUME": MASTER_VOLUME,
    "SND_SONG_SPEED": SONG_SPEED, "SND_SONG_SPEED_COPY": SONG_SPEED_COPY,
    "SND_SONG_LOADED": SONG_LOADED, "SND_FADE_RATE": FADE_RATE,
    "SND_FADE_COUNTDOWN": FADE_COUNTDOWN, "SND_SPEED_ACC": SPEED_ACC,
    "SND_TICK_DROP_VALUE": TICK_DROP_VALUE, "SND_TICK_DROP_ACC": TICK_DROP_ACC,
    "SND_NOISE_PERIOD_BASE": NOISE_PERIOD_BASE, "SND_NOISE_PERIOD_OUT": NOISE_PERIOD_OUT,
    "SND_PERIOD_SCRATCH": PERIOD_SCRATCH, "SND_CHANNEL_LOCKS": CHANNEL_LOCKS,
    "SND_SFX_ACTIVE_FLAGS": ACTIVE_FLAGS,
}


def test_the_tick_defaults_pin_every_module_global_its_body_names():
    """The guard on the table above, and the same shape as the period/volume pass's: a global that
    appears in the tick's own source but not in the defaults would be running on a salt-derived byte
    and the case naming it would be about something else."""
    body = pathlib.Path(__file__).resolve().parents[1] / "src" / "sound.c"
    tick_source = body.read_text().split("---- $17ca0:")[1]
    for name, address in sorted(TICK_GLOBAL_NAMES.items()):
        if f"WB_{name}" in tick_source:
            assert address in TICK_GLOBAL_DEFAULTS, (
                f"WB_{name} is read by the tick body and pinned by no default")


class _Psg:
    """The chip as the tick's output block leaves it: the ordered access ledger and the register
    file, which are the two surfaces the image cannot show. `silence_events`/`silence_file` state the
    stop chain's by hand; the tick's are long enough that they are RECORDED as the model runs."""

    def __init__(self, seed):
        self.values = bytearray(PSG_NREGS)
        self.known = 0
        for reg, value in seed.items():
            self.values[reg] = value
            self.known |= 1 << reg
        self.events = []

    def write(self, reg, value):
        self.values[reg] = value & BYTE_MASK
        self.known |= 1 << reg
        self.events.append((PSG_WRITE, reg, value & BYTE_MASK))

    def read(self, reg):
        self.events.append((PSG_READ, reg, self.values[reg]))
        return self.values[reg]


def _model_end_song(memory, psg):
    """$18016 — clear "song loaded", then the whole stop chain, whose `rts` returns to the tick's
    OWN caller. Spelt from the chain's constants rather than by calling its models, so the write set
    it contributes is stated in the tick's terms and the two are separate statements."""
    memory.byte(SONG_LOADED, SONG_UNLOADED)
    memory.byte(ENGINE_ENABLED, ENGINE_DISABLED)
    memory.long(ACTIVE_FLAGS, 0)
    memory.byte(PSG_SHADOW + PSG_REG_MIXER, PSG_MIXER_ALL_OFF)
    for reg in SILENCED_VOLUMES:
        memory.byte(PSG_SHADOW + reg, PSG_VOLUME_SILENT)
    psg.write(PSG_REG_MIXER, psg.read(PSG_REG_MIXER) | PSG_MIXER_ALL_OFF)
    for reg in SILENCED_VOLUMES:
        psg.write(reg, PSG_VOLUME_SILENT)


def _model_fade(memory):
    """$17cc2. A rate of zero disables it; a master volume already spent ends the song on the spot."""
    rate = memory.read(FADE_RATE)
    if rate == 0:
        return STEP_RETURNED
    if memory.read(MASTER_VOLUME) == 0:
        return STEP_SONG_ENDED
    if memory.decrement(FADE_COUNTDOWN) != 0:
        return STEP_RETURNED
    if memory.decrement(MASTER_VOLUME) == 0:
        return STEP_SONG_ENDED
    memory.byte(FADE_COUNTDOWN, rate)
    return STEP_RETURNED


def _model_rows(memory):
    """$17cea — the fractional row rate, and the three steps its carry runs."""
    total = memory.read(SPEED_ACC) + memory.read(SONG_SPEED)
    memory.byte(SPEED_ACC, total)
    if not total >> 8:
        return STEP_RETURNED
    for channel in range(CHANNELS):
        if _model_channel_step(memory, _music_channel(channel), TICK_D1) == STEP_SONG_ENDED:
            return STEP_SONG_ENDED
    return STEP_RETURNED


def _model_publish(memory):
    """$17d0c — three period/volume passes into the PSG shadow, the period split through the scratch
    word and the volume reduced by the master volume read as an ATTENUATION."""
    memory.byte(MASTER_VOLUME, memory.read(MASTER_VOLUME) & MASTER_VOLUME_MASK)
    for channel in range(CHANNELS):
        mix = _model_period_volume(memory, _music_channel(channel), 0)
        memory.word(PERIOD_SCRATCH, mix["d0"] & WORD_MASK)
        memory.byte(PSG_SHADOW + _shadow_tone(channel), mix["d0"])
        memory.byte(PSG_SHADOW + _shadow_tone(channel) + 1, memory.read(PERIOD_SCRATCH))

        attenuation = memory.read(MASTER_VOLUME) ^ MASTER_VOLUME_FULL
        volume = mix["d1"] & BYTE_MASK
        memory.byte(PSG_SHADOW + PSG_REG_VOLUME_A + channel,
                    volume - attenuation if volume >= attenuation else 0)
    memory.byte(PSG_SHADOW + PSG_REG_NOISE_PERIOD, memory.read(NOISE_PERIOD_OUT))


def _model_mixdown(memory):
    """$17d90 — an armed SFX channel overrides the shadow. Channel A's flag is tested TWICE, exactly
    as it is in snd_sfx_tick: a NEGATIVE one abandons the tick before the mask and the chip write."""
    for channel in range(CHANNELS):
        flag = memory.read(ACTIVE_FLAGS + channel)
        if flag == 0:
            continue
        if channel == CHANNEL_A and flag & SIGN_BIT_B:
            return False
        mix_period = _mix_period(channel)
        memory.byte(PSG_SHADOW + _shadow_tone(channel), memory.read(mix_period + MIX_PERIOD_LOW))
        memory.byte(PSG_SHADOW + _shadow_tone(channel) + 1, memory.read(mix_period))

        bits = memory.read(_channel_state(channel) + DESC_MIXER_BITS)
        if not bits & MIXER_NOISE_OFF:
            memory.byte(PSG_SHADOW + PSG_REG_NOISE_PERIOD, memory.read(MIX_NOISE))
        merged = memory.read(PSG_SHADOW + PSG_REG_MIXER) | _channel_mixer_bits(channel)
        memory.byte(PSG_SHADOW + PSG_REG_MIXER, merged)
        memory.byte(PSG_SHADOW + PSG_REG_MIXER, merged & _rol_byte(bits, channel))
        memory.byte(PSG_SHADOW + PSG_REG_VOLUME_A + channel, memory.read(MIX_VOLUME + channel))
    memory.byte(PSG_SHADOW + PSG_REG_MIXER,
                memory.read(PSG_SHADOW + PSG_REG_MIXER) & PSG_MIXER_ALL_OFF)
    return True


def _model_chip(memory, psg):
    """$17e34 — and a LOCKED channel is neither written nor allowed to vote in the mixer merge, so
    whatever the chip already held in its bits survives. The NOISE register needs all four lock bytes
    clear, because one noise generator is shared by the three channels."""
    owned = 0
    if memory.read_long(CHANNEL_LOCKS) == 0:
        psg.write(PSG_REG_NOISE_PERIOD, memory.read(PSG_SHADOW + PSG_REG_NOISE_PERIOD))
    for channel in range(CHANNELS):
        if memory.read(CHANNEL_LOCKS + channel) != 0:
            continue
        fine = _shadow_tone(channel)
        psg.write(fine, memory.read(PSG_SHADOW + fine))
        psg.write(fine + 1, memory.read(PSG_SHADOW + fine + 1))
        psg.write(PSG_REG_VOLUME_A + channel, memory.read(PSG_SHADOW + PSG_REG_VOLUME_A + channel))
        owned |= _channel_mixer_bits(channel)
    chip = psg.read(PSG_REG_MIXER)
    shadow = memory.read(PSG_SHADOW + PSG_REG_MIXER)
    psg.write(PSG_REG_MIXER, ((chip ^ shadow) & owned) ^ chip)


def _model_tick(memory, psg):
    """The whole of $17ca0."""
    if memory.read(ENGINE_ENABLED) == ENGINE_DISABLED and memory.read_long(ACTIVE_FLAGS) == 0:
        return
    total = memory.read(TICK_DROP_ACC) + memory.read(TICK_DROP_VALUE)
    memory.byte(TICK_DROP_ACC, total)
    if total >> 8:
        return                                  # the carry abandons the WHOLE tick

    _model_sfx_tick_into(memory)
    if memory.read(ENGINE_ENABLED) != ENGINE_DISABLED:
        if _model_fade(memory) == STEP_SONG_ENDED:
            return _model_end_song(memory, psg)
        memory.byte(NOISE_PERIOD_OUT, memory.read(NOISE_PERIOD_BASE))
        if _model_rows(memory) == STEP_SONG_ENDED:
            return _model_end_song(memory, psg)
        _model_publish(memory)
    if _model_mixdown(memory):
        _model_chip(memory, psg)


def _tick_pokes(salt, records=None, globals_=None, streams=None, armed=None):
    """The module state a tick case runs on: every mutable band the tier reads, then the three music
    records, then whatever `snd_trigger_effect` leaves for each ARMED channel (its own model, already
    proven against the original above), then the case's globals."""
    pokes = overlay(_mutable_seed(salt),
                    _step_pokes(salt, records or {}, None, streams or {}),
                    {PRNG_STATE: SFX_TICK_SEED.to_bytes(PRNG_STATE_LEN, "big")},
                    {addr: bytes([value]) for addr, value in TICK_GLOBAL_DEFAULTS.items()})
    for channel, effect_id in sorted((armed or {}).items()):
        pokes = overlay(pokes, expected_writes(_poked_image(pokes), effect_id, channel))
    return overlay(pokes, {addr: bytes([value]) for addr, value in (globals_ or {}).items()})


def _tick_body_model(memory, psg_seed):
    """...where $17ca0 has both, and RECORDS its ledger as the model runs rather than stating it: an
    unlocked tick leaves twelve accesses and an ended song five, which no by-hand list would keep."""
    psg = _Psg(psg_seed)
    _model_tick(memory, psg)
    return psg


def _run_tick(what, pokes, mixer=TICK_MIXER, ticks=1):
    """A3 IS AN ENTRY REGISTER HERE. $17ca0's first instruction is `tst.b 2250(a3)` — the `lea` is in
    the TEMPO HEAD above it — so the body inherits the module base exactly as $18106, $18208 and
    $1aaca do. `_run_whole_tick` below is the one runner that does NOT seed it, because entering at
    $17c74 runs that `lea`."""
    return _run_tick_sequence("snd_music_tick_body", _tick, _tick_body_model, TICK_INSN_CAP,
                              what, pokes, ticks, regs={"a3": MODULE_BASE},
                              psg_seed={PSG_REG_MIXER: mixer})[1]


def _tick_case(what, **kwargs):
    mixer = kwargs.pop("mixer", TICK_MIXER)
    ticks = kwargs.pop("ticks", 1)
    return _run_tick(what, _tick_pokes(leaf.case_salt(what), **kwargs), mixer=mixer, ticks=ticks)


TICK_SEEDED_BANDS = STEP_SEEDED_BANDS + ((MIX_PERIOD, MIX_BLOCK_LEN), (PSG_SHADOW, PSG_SHADOW_LEN),
                                         (PRNG_STATE, PRNG_STATE_LEN))


def test_a_tick_case_seeds_every_mutable_byte_the_whole_tier_reads():
    """The tick reaches all five bands — its own three plus the SFX mix block and the PSG shadow —
    and every one of them ships dirty."""
    assert_bands_are_seeded(_tick_pokes(0), TICK_SEEDED_BANDS, "a tick case")


def test_no_tick_case_puts_the_latent_sfx_opcode_in_a_pattern():
    """THE BOUNDARY include/sound.h's SND_TRIGGER_CHANNEL_UNMODELLED rests on. Opcode $97 hands the
    trigger the d1 snd_sfx_tick left, and snd_sfx_tick's outgoing registers are not reconstructed —
    so a tick case that reached $97 would be comparing against a register nothing models. None can:
    the byte occurs nowhere in the shipped patterns, and every stream this file seeds is checked."""
    assert TRIGGER_SFX_OPCODE not in SHIPPED_OPCODE_CENSUS
    for index in range(CHANNELS):
        assert TRIGGER_SFX_OPCODE not in _tick_pokes(0)[_seeded_pattern(index)]


# --- the gate: the engine flag, and the FOUR bytes the `tst.l` reads -------------------------------
# The mutants: a gate written with `||` where the `bne`/`beq` pair is an OR of two admissions (row 1
# against row 4), and one reading three flag bytes where the `tst.l` reads four (row 3 alone).
TICK_GATE_CASES = (
    ({ENGINE_ENABLED: ENGINE_DISABLED}, "engine off and every SFX flag clear: the `rts` at $17c72, "
                                        "and not one byte written"),
    ({ENGINE_ENABLED: ENGINE_DISABLED, ACTIVE_FLAGS + CHANNEL_A: ACTIVE},
     "engine off but channel A armed: the SFX half runs and the music half does not"),
    ({ENGINE_ENABLED: ENGINE_DISABLED, ACTIVE_FLAGS + CHANNELS: 1},
     "engine off and only the PAD byte past the three flags set — the `tst.l` reads it, so the tick "
     "runs; three `tst.b` would not"),
    ({}, "engine on with nothing armed: the whole music path"),
)


@pytest.mark.parametrize("globals_,why", TICK_GATE_CASES,
                         ids=[f"gate_{index}" for index in range(len(TICK_GATE_CASES))])
def test_the_gate_admits_the_tick_on_the_engine_flag_or_any_of_the_four_sfx_bytes(globals_, why):
    _tick_case(f"the tick's gate: {why}", globals_=globals_)


# --- the tick DROPPER, which is what the tempo head feeds ------------------------------------------
# Both sides of the wrap for each of the three values the head can write. The mutants: a carry test
# inverted, an `add.w` where the `add.b` is (the wrap would never happen), and a drop value read from
# the accumulator's own address.
TICK_DROP_CASES = (
    (0x00, 0xff, "the 50 Hz colour value: an accumulator of $ff plus 0 never carries, so no tick is "
                 "ever dropped"),
    (0x2b, 0xd4, "the 60 Hz value one below its wrap — $d4 + $2b is exactly $ff"),
    (0x2b, 0xd5, "...and AT it, which drops the whole tick"),
    (0x48, 0x00, "the mono value from a cleared accumulator, which is the first tick after a reset"),
)
# TRIMMED, batch-17's bar: the $48 pair either side of ITS wrap ($b7/$b8) was two more runs re-making
# the claim the $2b pair makes — every mutant this grid is for (the carry inverted, the accumulator
# added to itself, an `add.w` where the `add.b` is, the value read from the wrong address) dies on
# $2b already, checked at the mutant level before the rows were cut. The $48 row that stays is the
# one the three-value guard below needs.


@pytest.mark.parametrize("drop,accumulator,why", TICK_DROP_CASES,
                         ids=[f"drop_{c[0]:02x}_acc_{c[1]:02x}" for c in TICK_DROP_CASES])
def test_the_drop_accumulator_skips_a_whole_tick_on_its_carry(drop, accumulator, why):
    _tick_case(f"a tick-drop value of {drop:#04x} over an accumulator of {accumulator:#04x} ({why})",
               globals_={TICK_DROP_VALUE: drop, TICK_DROP_ACC: accumulator})


def test_the_drop_sweep_covers_the_three_values_the_tempo_head_can_write():
    """The guard on the sweep: the head writes ONE byte, and these are its three values.

    The rows above keep the literals while `TICK_DROP_VALUES` comes from the header, so the two sides
    stay independent statements. That the head really WRITES each of them, and to this address, is
    the tempo section's own tiling cases — this one is about the sweep's coverage of the body.
    """
    assert {drop for drop, _acc, _why in TICK_DROP_CASES} == set(TICK_DROP_VALUES)


# --- the fade, and the first of the two non-local exits --------------------------------------------
TICK_FADE_RATE = 5
TICK_FADE_CASES = (
    ({FADE_RATE: 0}, "a fade rate of ZERO, which disables the arm entirely"),
    ({FADE_RATE: TICK_FADE_RATE, MASTER_VOLUME: 0, FADE_COUNTDOWN: 3},
     "a fade started at SILENCE: the volume is already 0 and the song ends before the countdown is "
     "even touched"),
    ({FADE_RATE: TICK_FADE_RATE, MASTER_VOLUME: 8, FADE_COUNTDOWN: 3},
     "a countdown still turning, which spends one tick and nothing else"),
    ({FADE_RATE: TICK_FADE_RATE, MASTER_VOLUME: 8, FADE_COUNTDOWN: 1},
     "a countdown of ONE, the tick the volume steps on and the countdown reloads"),
    ({FADE_RATE: TICK_FADE_RATE, MASTER_VOLUME: 1, FADE_COUNTDOWN: 1},
     "the LAST step: the volume reaches 0 and the song ends through $18016"),
)


@pytest.mark.parametrize("globals_,why", TICK_FADE_CASES,
                         ids=[f"fade_{index}" for index in range(len(TICK_FADE_CASES))])
def test_the_fade_spends_the_countdown_and_ends_the_song_at_silence(globals_, why):
    """Two of these rows take the non-local exit at $18016 — "song loaded" cleared and the stop chain
    run, whose `rts` returns to the TICK's caller — so the PSG ledger they leave is silence's four
    accesses and NOT the twelve an unlocked output block leaves."""
    _tick_case(f"the tick's fade: {why}", globals_=globals_)


# --- the row rate, and the three steps its carry runs ----------------------------------------------
# The mutants: a carry ignored, so every tick steps a row (rows 1 and 2 disagree), and the end-of-song
# status not acted on by the tick — which row 3 reaches, since all three channels walk a pattern byte.
TICK_ROW_CASES = (
    ({SPEED_ACC: 0}, {}, "an accumulator that does not carry: no channel steps at all"),
    ({SPEED_ACC: 0xd0}, {}, "an accumulator that CARRIES, so all three channels spend a countdown"),
    ({SPEED_ACC: 0xd0}, {index: {CH_DURATION: 1} for index in range(CHANNELS)},
     "...with all three countdowns at ONE, so all three walk a pattern byte in the same tick"),
    ({SPEED_ACC: 0xff, SONG_SPEED: 1}, {}, "the smallest speed byte that can carry, from $ff"),
)


@pytest.mark.parametrize("globals_,records,why", TICK_ROW_CASES,
                         ids=[f"rows_{index}" for index in range(len(TICK_ROW_CASES))])
def test_the_row_rate_steps_every_channel_on_its_carry(globals_, records, why):
    _tick_case(f"the tick's row step: {why}", globals_=globals_, records=records)


# --- the master volume as an ATTENUATION -----------------------------------------------------------
# The mutants: the volume read as a LEVEL rather than through `eori.b #15` (rows 1 and 2 invert), the
# borrow WRAPPING instead of clamping at silence (row 2 alone), and the `andi.b #15` dropped (row 4).
TICK_VOLUME_CASES = (
    (MASTER_VOLUME_FULL, "full volume, whose attenuation is 0 and which subtracts nothing"),
    (0, "silence, whose attenuation is 15 — every channel clamps to 0 rather than wrapping"),
    (9, "a mid volume, so the subtraction is neither identity nor a clamp"),
    (0x1f, "a volume with rubbish above the nibble, which the `andi.b #15` masks BEFORE the "
           "attenuation is computed"),
)


@pytest.mark.parametrize("volume,why", TICK_VOLUME_CASES,
                         ids=[f"volume_{c[0]:02x}" for c in TICK_VOLUME_CASES])
def test_the_master_volume_attenuates_every_channel_and_clamps_at_silence(volume, why):
    _tick_case(f"a master volume of {volume:#04x} ({why})", globals_={MASTER_VOLUME: volume})


# --- the SFX mixdown -------------------------------------------------------------------------------
# Which shipped descriptors sit on either side of the noise test, derived rather than named: the arm
# copies the shared noise byte only when descriptor +6 bit 3 is CLEAR.
NOISE_ON_EFFECT = next(effect for effect in range(SFX_IDS)
                       if not harness.BASE_IMAGE[DESCRIPTORS + effect * DESCRIPTOR_LEN
                                                 + DESC_MIXER_BITS] & MIXER_NOISE_OFF)
NOISE_OFF_EFFECT = next(effect for effect in range(SFX_IDS)
                        if harness.BASE_IMAGE[DESCRIPTORS + effect * DESCRIPTOR_LEN
                                              + DESC_MIXER_BITS] & MIXER_NOISE_OFF)

SFX_FLAG_NEGATIVE = 0xff        # what only a seeded state can hold: the trigger `sf`s the byte
                                # to 0 and stores 1, so no shipped path ever writes a negative one

TICK_MIXDOWN_CASES = (
    ({CHANNEL_A: NOISE_ON_EFFECT}, {},
     "channel A armed with a descriptor whose noise is ON, so the shared noise byte reaches the "
     "shadow"),
    ({CHANNEL_A: NOISE_OFF_EFFECT}, {},
     "...and one whose noise is OFF, which is the `btst #3` from the other side"),
    ({1: NOISE_ON_EFFECT}, {}, "channel B alone, whose mixer byte is ROTATED one place"),
    ({2: NOISE_ON_EFFECT}, {}, "channel C alone, rotated two"),
    ({CHANNEL_A: 0, 1: 1, 2: 2}, {}, "all three armed with three different effects, so the shared "
                                     "noise byte belongs to whichever arm ran last"),
    ({CHANNEL_A: NOISE_ON_EFFECT}, {ACTIVE_FLAGS + CHANNEL_A: SFX_FLAG_NEGATIVE},
     "channel A's flag NEGATIVE, which abandons the tick before the mixer mask and before the chip "
     "is written at all — B and C are never even looked at"),
    ({1: NOISE_ON_EFFECT}, {ACTIVE_FLAGS + 1: SFX_FLAG_NEGATIVE},
     "channel B's flag NEGATIVE, which for B is merely NON-ZERO: its arm runs and the chip is "
     "written. The sign test is channel A's alone, and this row is the sweep's finding — without it "
     "a `bmi` on all three arms passed the whole grid"),
)


@pytest.mark.parametrize("armed,globals_,why", TICK_MIXDOWN_CASES,
                         ids=[f"mixdown_{index}" for index in range(len(TICK_MIXDOWN_CASES))])
def test_an_armed_sfx_channel_overrides_the_music_in_the_psg_shadow(armed, globals_, why):
    _tick_case(f"the SFX mixdown: {why}", armed=armed, globals_=globals_)


def test_the_mixdown_sweep_reaches_both_arms_of_the_noise_test():
    """The guard on the pair above: the two effect ids have to disagree about descriptor +6 bit 3, or
    a port that stored the noise byte unconditionally would pass both."""
    for effect, expected in ((NOISE_ON_EFFECT, 0), (NOISE_OFF_EFFECT, MIXER_NOISE_OFF)):
        bits = harness.BASE_IMAGE[DESCRIPTORS + effect * DESCRIPTOR_LEN + DESC_MIXER_BITS]
        assert bits & MIXER_NOISE_OFF == expected, f"sfx {effect} is on the wrong side of the test"


# --- the chip write, and the channel locks ---------------------------------------------------------
# The mutants: the NOISE register gated on one lock byte rather than on the `tst.l`'s four (row 5
# alone), and a locked channel still voting in the mixer merge (rows 2..4, each on its own bits).
TICK_LOCK_CASES = (
    ({}, "no channel locked: all ten registers written and all three sets of bits owned"),
    ({CHANNEL_LOCKS + 0: 1}, "channel A locked — its three registers are skipped AND its bits stay "
                             "out of the mixer merge, so the chip's own survive"),
    ({CHANNEL_LOCKS + 1: 1}, "channel B locked"),
    ({CHANNEL_LOCKS + 2: 1}, "channel C locked"),
    ({CHANNEL_LOCKS + 3: 1}, "only the unnamed FOURTH lock byte set: the `tst.l` sees it and the "
                             "NOISE register is skipped, but all three channels are still written"),
    ({CHANNEL_LOCKS + n: 1 for n in range(CHANNELS)},
     "all three locked, which leaves the merge with no bits to take from the shadow at all"),
)


@pytest.mark.parametrize("globals_,why", TICK_LOCK_CASES,
                         ids=[f"locks_{index}" for index in range(len(TICK_LOCK_CASES))])
def test_a_locked_channel_is_neither_written_nor_allowed_to_vote_in_the_mixer_merge(globals_, why):
    _tick_case(f"the chip write: {why}", globals_=globals_)


def _one_seed_per_direction_state(seeds):
    """The stop chain's own MIXER_SEEDS, thinned to one row per state of bits 6-7.

    TRIMMED rather than re-tupled: the tick's merge can own only the six enables, so what a row here
    buys is a direction-bit combination and nothing else — and the stop chain's seven rows carry only
    four of those. Taking them FROM that tuple keeps one source and keeps its guard.
    """
    chosen = {}
    for mixer, why in seeds:
        chosen.setdefault(mixer & MIXER_DIRECTION_BITS, (mixer, why))
    return tuple(chosen[state] for state in sorted(chosen))


TICK_MIXER_SEEDS = _one_seed_per_direction_state(MIXER_SEEDS)


def test_the_tick_mixer_sweep_still_reaches_all_four_states_of_the_preserved_bits():
    """The guard the trim above rests on — and it is not the stop chain's, which covers the tuple it
    thinned FROM."""
    assert {mixer & MIXER_DIRECTION_BITS for mixer, _why in TICK_MIXER_SEEDS} == {0x00, 0x40, 0x80,
                                                                                  0xc0}
    assert len(TICK_MIXER_SEEDS) < len(MIXER_SEEDS)


@pytest.mark.parametrize("mixer,why", TICK_MIXER_SEEDS,
                         ids=[f"mixer_{seed[0]:02x}" for seed in TICK_MIXER_SEEDS])
def test_the_mixer_read_back_keeps_every_bit_the_module_does_not_own(mixer, why):
    """The same claim the stop chain's `ori` makes, over the tick's own `eor/and/eor`: bits 6-7 are
    the port A/B direction lines and NOTHING in the tick can own them, so they come back from the
    chip whatever the shadow holds."""
    info = _tick_case(f"the tick's mixer merge over a chip mixer of {mixer:#04x} ({why})",
                      mixer=mixer)
    written = [value for kind, reg, value in info["regs"]["psg_events"]
               if kind == PSG_WRITE and reg == PSG_REG_MIXER]
    assert len(written) == 1 and written[0] & MIXER_DIRECTION_BITS == mixer & MIXER_DIRECTION_BITS, (
        f"the mixer was written {written}, whose direction bits are not the chip's {mixer:#04x}")


# --- the second non-local exit: pattern opcode $8e -------------------------------------------------

def test_pattern_opcode_8e_ends_the_song_from_inside_a_row_and_the_tick_never_comes_back():
    """THE ONE PLACE $8e CAN BE PINNED. Entered at $18106 its `addq.l #4,sp` pops the runner's own
    sentinel; entered here the stack holds the frame the instruction is written for, so it unwinds
    snd_channel_step, clears "song loaded" and runs the stop chain — and the tick's remaining two
    channel steps, its whole period/volume pass, its mixdown and its chip write never run.

    The PSG ledger is the proof: the FIVE entries `silence_events` states — a read of the mixer and
    four writes — and not the twelve the output block leaves (one per unlocked channel's three
    registers, the noise period, and the mixer's read and write)."""
    info = _tick_case("a pattern whose first byte is $8e, reached through a row step",
                      globals_={SPEED_ACC: 0xd0},
                      records={CHANNEL_A: {CH_DURATION: 1}},
                      streams={CHANNEL_A: bytes([END_SONG_OPCODE])})
    assert info["regs"]["psg_events"] == silence_events(TICK_MIXER), (
        "the end-of-song tail must leave silence's ledger and nothing else")


def test_the_fade_and_the_opcode_reach_the_same_tail_two_bytes_apart():
    """$18014 is `addq.l #4,sp` and $18016 is where the fade's two `beq.w`s aim — so the opcode's
    handler IS the tail plus one instruction, which is why the two endings write the same bytes."""
    entry = leaf.entry_of("snd_pattern_op_8e_end_song")
    assert END_SONG_TAIL == entry + ADDQ_L_SP_BYTES
    assert bytes(harness.BASE_IMAGE[entry:END_SONG_TAIL]) == opcode(ADDQ_L_AN | (4 << 9) | A7), (
        "opcode $8e's handler must be the frame unwind and then the tail the fade branches into")


# --- what the run LEAVES that no image byte can show ------------------------------------------------

def test_the_supervisor_save_destroys_the_channel_volume_d1_was_carrying():
    """A documented ORACLE fact, the precedent being the stop chain's saved SR in d2.

    d1 leaves $18208 holding the channel's volume in its low byte and the portamento's leftover in
    its second — and then `move.w sr,d1` at $17e34 overwrites the whole low WORD with the SR. The
    oracle enters every run at $2700, so the outgoing d1 is exactly that: the high half is zero
    because `moveq #0,d1` inside $18208 cleared it, which is the half of this the reconstruction
    could not fake even if it tried.
    """
    info = _tick_case("the registers the chip write leaves", globals_={SPEED_ACC: 0xd0})
    assert info["regs"]["d1"] == SUPERVISOR_SR, (
        f"d1 is {info['regs']['d1']:#010x}, not the saved SR over a d1 that $18208 had cleared")


# --- several ticks in a row -------------------------------------------------------------------------
TICK_SEQUENCE_TICKS = 5


def test_a_song_ticks_forward_over_several_frames():
    """Five ticks carried on one image, which is the only shape that reaches what a single tick
    cannot: the row accumulator carrying part-way through, the PRNG advancing (it steps EVERY tick and
    snd_play_song does not reset it), the envelope and vibrato counters turning, and a pattern byte
    being consumed on the tick the countdown finally expires."""
    _tick_case("five consecutive ticks of a song at speed $30",
               records={index: {CH_DURATION: 2, CH_FLAGS: CH_FLAG_ENVELOPE | CH_FLAG_VIBRATO}
                        for index in range(CHANNELS)},
               ticks=TICK_SEQUENCE_TICKS)


def test_five_ticks_of_an_armed_effect_run_both_engines_at_once():
    """...and the same with an SFX armed, which is the only case where the mixdown overrides a shadow
    the music half has just written in the SAME tick."""
    _tick_case("five ticks with a song playing and sfx 1 on channel B",
               armed={1: 1}, globals_={SPEED_ACC: 0xc0}, ticks=TICK_SEQUENCE_TICKS)


# --- $17c74: the TEMPO HEAD, and with it the whole tick ---------------------------------------------
#
# THE MODULE'S ONLY HARDWARE-STEERED CODE, and the first consumer anywhere of the kit's SEEDED
# HARDWARE READ model (TRAP_MODEL.md, "Phase 7"). 44 bytes that read two bytes outside the image and
# write one byte inside it, and the reason they were the sound module's last unported ones: before
# Phase 7 both reads answered a fabricated 0 on BOTH sides, so a port of this could not be wrong.
# `../PORTABILITY.md` §4 records what that looked like — a green run in 12 instructions, and the
# `$ffff820a` defect BuggyBoy shipped to real hardware, present here before a line was ported.
#
# THE CASES DECLARE A BIT, NOT A MACHINE. Each profile below is the tested bit alone and its
# COMPLEMENT — $80/$7f for the GPIP, $02/$fd for the sync — so every other bit of the byte carries
# the opposite value and a port testing bit 6 or bit 0 instead reads the branch backwards. The
# machine's real bytes are one further case, taken from `emu.hw_capture_profile()` rather than
# restated, and the kit's own suite makes the same choice for the same reason.
#
# THE MUTANTS, named before the grid: the three drop values swapped or wrong (each row carries one
# value, so each dies on its own row); either `btst` off by one (the complement bytes are what make
# that visible); either branch sense inverted (`bne` read as `beq` sends every row to the wrong arm);
# the sync register read UNCONDITIONALLY, which no image byte can show and which the mono row's read
# stream is the only witness to; and the two reads in the other order, which the stream catches
# because the two addresses carry different declared bytes.

# The bit's CLEAR meaning, as the byte with every OTHER bit set. The bit's SET meaning is the mask
# itself, spelt as the header's own name below. GPIP bit 7 is the mono-monitor detect line and is
# ACTIVE LOW — SET means a COLOUR monitor — so GPIP_MONO is the one with bit 7 clear.
GPIP_MONO = GPIP_COLOUR_MONITOR ^ BYTE_MASK
SYNC_AT_60HZ = SYNC_50HZ ^ BYTE_MASK

# The three machines the selector can be on, each as the declaration that puts it there.
TEMPO_MACHINES = {
    "mono": {leaf.MFP_GPIP: GPIP_MONO, leaf.SHIFTER_SYNC: SYNC_50HZ},
    "colour_60hz": {leaf.MFP_GPIP: GPIP_COLOUR_MONITOR, leaf.SHIFTER_SYNC: SYNC_AT_60HZ},
    "colour_50hz": {leaf.MFP_GPIP: GPIP_COLOUR_MONITOR, leaf.SHIFTER_SYNC: SYNC_50HZ},
}
# The mono row declares the sync byte it must NOT read, and declares it to the arm that would write a
# DIFFERENT drop value — so a port that fell through to the sync test reds on the image as well as on
# the read stream. Over-declaring is ordinary and the kit leaves it alone (its own case says so).

# The head's longest arm — `lea`, the default store, `btst`, `bne`, `btst`, `bne`, the 60 Hz store.
# The mono arm is six (`lea`, store, `btst`, `bne`, store, `bra`) and the 50 Hz arm six.
TEMPO_HEAD_INSNS = 7
WHOLE_TICK_INSN_CAP = TICK_INSN_CAP + TEMPO_HEAD_INSNS
_whole_tick = leaf.image_glue("snd_music_tick")


def _tempo_drop_value(hw_seed):
    """The selector, as the two `btst`+`bne` pairs read — the model's own statement of it, so a
    reconstruction that got the polarity backwards is contradicted rather than agreed with.

    A CLEAR GPIP bit 7 is a monochrome monitor (the line is active low); a CLEAR sync bit 1 is 60 Hz.
    Both branches are `bne`, so both arms below are the bit's CLEAR meaning.
    """
    if not hw_seed[leaf.MFP_GPIP] & GPIP_COLOUR_MONITOR:
        return TICK_DROP_MONO
    if not hw_seed[leaf.SHIFTER_SYNC] & SYNC_50HZ:
        return TICK_DROP_60HZ
    return TICK_DROP_50HZ


def _tempo_hw_events(hw_seed):
    """...and the ordered read stream that same walk makes. DERIVED from the value above rather than
    re-deciding the branch: the sync byte is read exactly when the mono arm was not taken."""
    events = [(leaf.MFP_GPIP, hw_seed[leaf.MFP_GPIP])]
    if _tempo_drop_value(hw_seed) != TICK_DROP_MONO:
        events.append((leaf.SHIFTER_SYNC, hw_seed[leaf.SHIFTER_SYNC]))
    return events


def _whole_tick_model(hw_seed):
    """$17c74: the selector's byte into WB_SND_TICK_DROP_VALUE, and then the whole of $17ca0.

    Writing the byte THROUGH `_Memory` is what makes the tiling real — the model does not hand the
    value to the body, it stores it where the head stores it and lets the body's own accumulator read
    it back, so a head writing the right value to the wrong address reds on the body's arithmetic.
    """
    def model(memory, psg_seed):
        memory.byte(TICK_DROP_VALUE, _tempo_drop_value(hw_seed))
        psg = _Psg(psg_seed)
        _model_tick(memory, psg)
        return psg
    return model


def _whole_tick_case(what, hw_seed, ticks=1, **kwargs):
    """One whole-tick differential, entered at $17c74 on the machine `hw_seed` declares.

    A3 IS NOT AN ENTRY REGISTER HERE, and this is the one routine of the tier where it is not:
    $17c74's first instruction is the `lea $1738c(pc),a3` that every other entry inherits. So no case
    below seeds a3, and a port that expected one would run the tick against a base of whatever the
    runner left. The mixer is `TICK_MIXER` and not a parameter: no case here is about a mixer other
    than the one TOS leaves, and the body's own runner already sweeps that.
    """
    return _run_tick_sequence("snd_music_tick", _whole_tick, _whole_tick_model(hw_seed),
                              WHOLE_TICK_INSN_CAP, what, _tick_pokes(leaf.case_salt(what), **kwargs),
                              ticks, psg_seed={PSG_REG_MIXER: TICK_MIXER}, hw_seed=hw_seed,
                              hw_events=_tempo_hw_events(hw_seed))[1]


@pytest.mark.parametrize("machine", sorted(TEMPO_MACHINES))
def test_the_tempo_selector_picks_the_drop_value_the_declared_machine_gives(machine):
    """One whole tick per machine, entered at $17c74 and run to the `rts` — the first time any case
    in this project has run the tick end to end.

    What each proves beyond the body's own cases: the drop byte the head writes is the byte the
    body's accumulator adds, the two hardware reads happened in the right order and no others did,
    and the module base came from the head's own `lea`.
    """
    hw_seed = TEMPO_MACHINES[machine]
    info = _whole_tick_case(f"a whole tick on a {machine} machine", hw_seed)
    assert leaf.read_bytes(info, TICK_DROP_VALUE, 1) == bytes([_tempo_drop_value(hw_seed)]), (
        f"{machine}: the selector left the wrong drop value in {TICK_DROP_VALUE:#x}")


def test_the_three_machines_are_the_three_drop_values_and_nothing_else():
    """The guard on the grid above: three declarations, three DISTINCT outcomes, and they are exactly
    the three the header says the head can write. A grid two of whose rows landed on the same value
    would pin one arm twice and the third not at all."""
    chosen = [_tempo_drop_value(hw_seed) for hw_seed in TEMPO_MACHINES.values()]
    assert sorted(chosen) == sorted(TICK_DROP_VALUES)


def test_the_mono_arms_expected_read_stream_stops_at_the_gpip():
    """The GUARD on the one claim here that NO image byte can carry: `bra.s $17ca0` at $17c8e skips
    the sync test, so a mono machine never touches the shifter. A port that read both bytes every
    time writes the same drop value and leaves the same image; only the stream is one entry longer.

    The DIFFERENTIAL proof is the mono rows above and below — every `_whole_tick_case` compares the
    oracle's stream against `_tempo_hw_events`. What no run can check is whether that expectation is
    self-fulfilling, so this states the model's own answer, which is the only thing left to get
    wrong. (Measured: the both-reads mutant is caught by the mono rows and by nothing else.)
    """
    assert _tempo_hw_events(TEMPO_MACHINES["mono"]) == [(leaf.MFP_GPIP, GPIP_MONO)]


def test_the_capture_profile_is_a_fifty_hertz_colour_machine():
    """THE MACHINE'S REAL BYTES, and the reconciliation the audio extraction rests on.

    `emu.hw_capture_profile()` declares $fffa01 = $b0 and $ff820a = $02. $b0 has bit 7 SET — and
    because the mono-detect line is ACTIVE LOW that means a COLOUR monitor, not a monochrome one —
    while its bits 5 and 4 are the FDC and ACIA interrupt lines, also active low and so set because
    idle. $02 has sync bit 1 set: 50 Hz. So the profile selects WB_SND_TICK_DROP_50HZ, no tick is
    dropped, and the captured songs play at the speed the composer wrote — which is what
    ../out/audio was extracted under.

    Asserted through a real differential rather than by reading the bytes, because the claim is about
    what the SELECTOR does with them. The bytes themselves come from the kit, not restated here.

    IT IS ALSO A PIN ON THE TWO MASKS ACROSS FILES. `WB_MFP_GPIP_COLOUR_MONITOR` and
    `WB_SHIFTER_SYNC_50HZ` are the game's own `btst` operands, and the kit names only the addresses,
    so this is the one case that runs the selector on the machine the KIT declares. It is a partial
    pin and says so: $b0 carries bits 7, 5 and 4, so a GPIP mask drifting onto 5 or 4 still reaches
    the colour arm here — caught instead by the entry pin (which assembles the bit NUMBER from the
    mask) and by GPIP_MONO, which is $7f and has both of them set.
    """
    profile = emu.hw_capture_profile()
    assert _tempo_drop_value(profile) == TICK_DROP_50HZ
    _whole_tick_case("a whole tick on the audio-capture profile's own machine", profile)


def test_a_tick_entered_at_the_head_declaring_no_machine_is_refused():
    """THE FALSE GREEN, stated from this project's side — the psg_seed case's twin one model over.

    Undeclared, both cores read 0 for both bytes, both take the MONO arm, both write $48 and the
    differential agrees with itself: green, and wrong on every colour ST the game shipped for. So the
    refusal is what this port's honesty rests on, exactly as `snd_psg_silence`'s is.

    IT IS A DIFFERENT REFUSAL FROM THE PSG MODEL'S, and the difference is the point. An undeclared
    PSG read sinks `emu.run` itself and raises RuntimeError for every caller; an undeclared hardware
    read is SERVED and merely recorded, and only `harness.differential` refuses — so this arrives as
    an AssertionError, and a bare `emu.run` of the same entry (test_audio_capture.py's) still works.

    The MIXER is declared, because it must be: an undeclared register-7 read-back would sink the run
    inside `emu.run` first and this case would pass for the other model's reason.

    THE REFUSAL NAMES ONE ADDRESS, NOT TWO, and that is the defect drawn from life: the fabricated 0
    took the mono arm, so the shifter was never reached and the run has no undeclared read of it to
    report. A reader who declares only what the message asks for gets the sync byte's refusal on the
    next run. Matched exactly, because "it named both" would mean the branch did not steer.
    """
    what = "a whole tick declaring no machine at all"
    with pytest.raises(AssertionError, match=r"hw_seed=\{0xfffa01: <byte>\} "):
        leaf.run("snd_music_tick", _whole_tick, [], what,
                 regs={"_pokes": _tick_pokes(leaf.case_salt(what))},
                 max_insns=WHOLE_TICK_INSN_CAP, psg_seed={PSG_REG_MIXER: TICK_MIXER})


# The drop value each machine gives, against an accumulator ONE BELOW its wrap and AT it. This is the
# TILING CASE: the head writes $17c6e, the body reads it one instruction later, and an accumulator
# chosen from the head's own arithmetic is what says the two meet on that byte rather than on two.
TEMPO_TILING_CASES = tuple(
    (machine, accumulator, carries)
    for machine, hw_seed in sorted(TEMPO_MACHINES.items())
    if _tempo_drop_value(hw_seed)                       # a drop of 0 can never carry — its own case
    for accumulator, carries in ((BYTE_LIMIT - _tempo_drop_value(hw_seed) - 1, False),
                                 (BYTE_LIMIT - _tempo_drop_value(hw_seed), True)))


@pytest.mark.parametrize("machine,accumulator,carries", TEMPO_TILING_CASES,
                         ids=[f"{c[0]}_acc_{c[1]:02x}" for c in TEMPO_TILING_CASES])
def test_the_drop_byte_the_head_writes_is_the_byte_the_body_accumulates(machine, accumulator,
                                                                        carries):
    """Either side of the wrap the DECLARED MACHINE puts the accumulator on.

    The accumulator is derived from the machine, not stated: $ff - $2b for a 60 Hz one, $ff - $48 for
    a mono one. So a head that wrote its value to the wrong address, or wrote the other machine's
    value, lands on the other side of the carry and the whole tick runs when it should have been
    dropped — visible as the SFX engine's writes, the chip's fifteen accesses and the row step, none
    of which a case entering at $17ca0 on a poked byte could attribute to the head.
    """
    hw_seed = TEMPO_MACHINES[machine]
    outcome = "the tick is dropped whole" if carries else "the tick runs"
    info = _whole_tick_case(f"a {machine} tick over an accumulator of {accumulator:#04x} — "
                            f"{outcome}", hw_seed, globals_={TICK_DROP_ACC: accumulator})
    assert bool(info["regs"]["psg_events"]) != carries, (
        f"{machine}: the carry decides whether the chip is written at all, and it did not")


def test_the_fifty_hertz_machine_never_drops_a_tick():
    """The third machine's own tiling claim, which the grid above cannot make: its drop value is 0, so
    an accumulator of $ff still does not carry and the tick always runs."""
    info = _whole_tick_case("a 50 Hz colour tick over an accumulator of $ff",
                            TEMPO_MACHINES["colour_50hz"], globals_={TICK_DROP_ACC: BYTE_MASK})
    assert leaf.read_bytes(info, TICK_DROP_ACC, 1) == bytes([BYTE_MASK]), (
        "the accumulator moved, so the head did not leave the 50 Hz value in the drop byte")
    assert info["regs"]["psg_events"], "the tick was dropped, which a drop value of 0 cannot do"


@pytest.mark.parametrize("machine", sorted(TEMPO_MACHINES))
def test_five_whole_ticks_of_a_song_on_each_machine(machine):
    """The tick end to end, five frames deep, on each of the three machines at once — the head, the
    dropper, the SFX engine, the fade, the row step, the period pass, the mixdown and the chip.

    Multi-tick is what makes the DROPPER's effect cumulative rather than incidental: at $2b the
    accumulator wraps once in every 5.95 ticks and at $48 once in every 3.56, so five ticks of the
    mono machine drop one and five of the 60 Hz one drop none — different frames of the same song,
    reached from nothing but the declared bytes.
    """
    _whole_tick_case(f"five whole ticks of a song on a {machine} machine", TEMPO_MACHINES[machine],
                     records={index: {CH_DURATION: 2, CH_FLAGS: CH_FLAG_ENVELOPE | CH_FLAG_VIBRATO}
                              for index in range(CHANNELS)},
                     ticks=TICK_SEQUENCE_TICKS)


def test_the_two_declared_addresses_are_the_ones_the_model_serves():
    """leaf.py spells the pair as literals — a fact about the GAME's `btst` operands, checkable
    against the disassembly — and the kit owns the set the model actually serves. Pin them equal
    here, the way the kit's own smoke project does, so a slot renumbered in os.h fails as a drift
    rather than as "the tick did not read the tempo pair"."""
    assert (leaf.MFP_GPIP, leaf.SHIFTER_SYNC) == emu.HW_ADDRS


# --- the tier's own geometry ------------------------------------------------------------------------

def test_the_tick_body_begins_where_the_tempo_selector_ends_and_ends_where_the_stop_does():
    """Self-bounding at all three joints, which is what says the head and the body TILE $17c74..$17f23
    between them: the head's own 44 assembled bytes end at the body's entry, and the body plus its
    644 is snd_stop. Nothing between them is unaccounted for, and neither pin can pass on a body of
    the wrong length."""
    assert len(ENTRY_BYTES["snd_music_tick"]) == TEMPO_HEAD_BYTES
    assert leaf.entry_of("snd_music_tick") + TEMPO_HEAD_BYTES \
        == leaf.entry_of("snd_music_tick_body")
    assert len(ENTRY_BYTES["snd_music_tick_body"]) == TICK_BODY_BYTES
    assert leaf.entry_of("snd_music_tick_body") + TICK_BODY_BYTES == leaf.entry_of("snd_stop")
    assert TICK_SHARED_RTS + len(RTS) == leaf.entry_of("snd_music_tick"), (
        "the `rts` the tick's four exits share must be the two bytes below its own entry")


def test_the_stepper_and_its_handlers_tile_the_module_from_the_jump_table_to_the_period_pass():
    """...and so is unit 4: the 24-word table abuts the handlers, the handlers abut the stepper, and
    the stepper abuts $18208. Without this the entry pins would pass on bodies of any length."""
    assert PATTERN_JUMP_TABLE + PATTERN_OPCODES * TABLE_ENTRY_LEN == PATTERN_HANDLER_BASE
    assert PATTERN_HANDLER_BASE + PATTERN_HANDLER_BYTES == leaf.entry_of("snd_channel_step")
    assert len(ENTRY_BYTES["snd_channel_step"]) == CHANNEL_STEP_BODY_BYTES
    assert leaf.entry_of("snd_channel_step") + CHANNEL_STEP_BODY_BYTES \
        == leaf.entry_of("snd_channel_period_and_volume")


def test_the_twenty_four_opcode_handlers_are_the_bytes_below_the_stepper():
    """The 306 bytes as one assert: every field offset, every module address, every operand count and
    every `bra` target, checked against the image at the block's own base."""
    handlers = _pattern_handlers()
    assert len(handlers) == PATTERN_HANDLER_BYTES
    actual = bytes(harness.BASE_IMAGE[PATTERN_HANDLER_BASE:PATTERN_HANDLER_BASE + len(handlers)])
    assert actual == handlers, (
        f"the handler block at {PATTERN_HANDLER_BASE:#x} is {actual.hex()}, not {handlers.hex()}")


def test_every_jump_table_entry_resolves_to_the_handler_the_name_map_gives():
    """The table itself, read out of the image and resolved the way the `jmp` does. This is what says
    the opcode -> handler column of ../names.txt's plate is the DATA's and not a reading of it — and
    that $8d really is a second entry pointing at $83's handler."""
    resolved = [_module_address(leaf.u16(harness.BASE_IMAGE,
                                         PATTERN_JUMP_TABLE + index * TABLE_ENTRY_LEN))
                for index in range(PATTERN_OPCODES)]
    for name, index in zip(PATTERN_HANDLER_NAMES, PATTERN_OPCODE_OF_HANDLER):
        assert resolved[index] == leaf.entry_of(name), (
            f"table entry {index:#04x} resolves to {resolved[index]:#x}, not {name}")
    assert resolved[PATTERN_ALIASED_OPCODE] == leaf.entry_of("snd_pattern_op_83_set_flag_bit1")
    assert len(set(resolved)) == PATTERN_OPCODES - 1, "exactly one pair of entries may share a target"


def test_the_three_mixdown_arms_carry_the_three_rotations_of_one_mixer_mask():
    """$09, $12, $24 — the `ori.b` immediates, the `rol.b` counts and the three records' own constant
    +47 are the same three bytes, which is why the reconstruction rotates one constant."""
    assert tuple(_channel_mixer_bits(channel) for channel in range(CHANNELS)) == SHIPPED_MIXER_MASKS
