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

KNOWINGLY NOT PINNED
  * EVERYTHING THE TRIGGER ARMS. It sets a channel's state and returns; the sound is made by the
    tick, which is not ported. A green suite here says nothing about audio.
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
"""
import ctypes
import pathlib

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, RTS, add_w_dn_dn, addi_w_dn, branch_w_to, bsr_w, btst_imm_dn,
                  assert_bands_are_seeded, clr_b_d16, clr_w_d16, clr_w_dn, longword, lsl_w_imm_dn,
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

def _module_pointer(image, table, byte_index):
    """One entry of an a3-relative WORD table, resolved as `movea.w 0(An,Dn.w),An / adda.l a3,An`
    does: a signed byte doubled into the index, and the ENTRY itself sign-extended before the module
    base is added to it."""
    entry = (table + TABLE_ENTRY_LEN * leaf.s8(byte_index)) & LONGWORD_MASK
    return (MODULE_BASE + leaf.s16(leaf.u16(image, entry))) & LONGWORD_MASK


def _descriptor_of(image, effect_id):
    return _module_pointer(image, PTR_TABLE, effect_id)


def _channel_state(channel):
    return STATE + channel * STATE_LEN


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
CMP_B_IMM_DN = 0xb03c           # cmp.b #imm,Dn.  ALSO IN test_text.py (`cmp_b_imm_dn`)
BNE_S = 0x6600
MOVEM_L_TO_PREDEC_A7 = 0x48e7   # ALSO IN test_hud.py, inside `MOVEM_L_SAVE_A0_A1`'s literal
MOVEM_L_FROM_POSTINC_A7 = 0x4cdf  # ...and `MOVEM_L_RESTORE_A0_A1`'s
MOVE_L_AN_PREDEC_A7 = 0x2f08
MOVEA_L_POSTINC_A7_AN = 0x205f  # ALSO IN test_copylock.py's `MOVEA_L_POSTINC_A7_A0_RTS`

# The registers the arms use, named once so a builder cannot pin one and the reconstruction read
# another: a3 is the module base, a0 the descriptor cursor, a1 the state cursor, a2 the stream.
D0, D1 = 0, 1
A0, A1, A2, A3 = 0, 1, 2, 3

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


ENTRY_BYTES = {
    "snd_trigger_effect": _trigger_entry(),
    "snd_call_trigger_effect": _stub(*_TRIGGER_STUB),
    "snd_psg_silence": _silence_entry(),
    "snd_stop_all_sfx": _stop_all_entry(),
    "snd_stop": _stop_entry(),
    "snd_prng_step": _prng_entry(),
    "snd_sfx_tick": _sfx_tick_entry(),
    "snd_channel_period_and_volume": _period_volume_entry(),
}
SOUND_ROUTINE_COUNT = 8

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
    """The two off-image surfaces, against the models above. Nothing in the image can show either:
    a run that silenced the wrong register, or none at all, writes exactly the same memory."""
    events = info["regs"]["psg_events"]
    expected = silence_events(psg_seed[PSG_REG_MIXER])
    assert events == expected, (
        f"{what}: the chip saw {events}, not {expected} "
        f"(each entry is (kind, register, value); kind {PSG_READ} is a read-back)")
    values, known = silence_file(psg_seed)
    assert (info["regs"]["psg_file"], info["regs"]["psg_known"]) == (values, known), (
        f"{what}: the register file ended {info['regs']['psg_file'].hex()} "
        f"(known {info['regs']['psg_known']:#06x}), not {values.hex()} (known {known:#06x})")


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


def _model_sfx_tick(image):
    """The whole of $1a5da: the PRNG step, then one arm per armed channel."""
    memory = _Memory(image)
    _model_prng(memory)
    if memory.read(ACTIVE_FLAGS + CHANNEL_A) & SIGN_BIT_B:
        return memory                                       # `bmi` — B and C do not run either
    for channel in range(CHANNELS):
        if memory.read(ACTIVE_FLAGS + channel) != 0:
            _model_sfx_arm(memory, channel)
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


def _run_ticks(what, pokes, ticks):
    """``ticks`` consecutive tick differentials, each entered on the state the last one left.

    A single tick reaches almost nothing — a freshly armed effect spends its first ticks counting
    down — so the sequence is what walks the volume stream, empties the duration and reaches the
    end-of-effect arm from the game's own descriptors. Each tick is its own whole-image differential;
    the state is carried forward through the POKES, so nothing is taken on trust from the run before.
    """
    for tick in range(ticks):
        label = f"{what}, tick {tick}"
        memory = _model_sfx_tick(_poked_image(pokes))
        info = leaf.run("snd_sfx_tick", _sfx_tick, write_bands(memory.written), label,
                        regs={"_pokes": pokes}, max_insns=SFX_TICK_INSN_CAP)
        assert_written(info, memory.written, label)
        pokes = overlay(pokes, memory.written)
    return pokes


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
    CH_FLAGS: 1, CH_VIBRATO_ACC: WORD_LEN, CH_ARPEGGIO_BASE: LONGWORD_LEN,
    CH_ARPEGGIO_CURSOR: LONGWORD_LEN, CH_VIBRATO_DEPTH: 1, CH_VIBRATO_SPEED: 1,
    CH_ENVELOPE_SPEED: 1, CH_NOTE: 1, CH_VOLUME: 1, CH_ENVELOPE_COUNT: 1,
    CH_ENVELOPE_CURSOR: LONGWORD_LEN, CH_ENVELOPE_LAST: 1, CH_PORTA_LIMIT: 1, CH_PORTA_STEP: 1,
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
SHIPPED_MIXER_MASKS = tuple(harness.BASE_IMAGE[MUSIC_CHANNEL_STATE + index * MUSIC_CHANNEL_LEN
                                               + CH_MIXER_MASK] for index in range(CHANNELS))


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


def _music_channel(index):
    return MUSIC_CHANNEL_STATE + index * MUSIC_CHANNEL_LEN


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


def _record_bytes(index, salt, fields):
    """One 48-byte music channel record: ADDRESS-KEYED bytes with the case's own fields over them.

    Keyed rather than zeroed because the band ships dirty and a zero would be indistinguishable from
    a field the routine cleared; keyed on the address so a read at the wrong offset lands on a byte
    that is wrong for where it was written.
    """
    record = bytearray(leaf.keyed_block(_music_channel(index), MUSIC_CHANNEL_LEN, salt))
    fields = {**RECORD_DEFAULTS, CH_MIXER_MASK: SHIPPED_MIXER_MASKS[index], **fields}
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
