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

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, RTS, add_w_dn_dn, branch_w_to, bsr_w, clr_b_d16, clr_w_d16,
                  longword, move_b_abs_l_dn, move_b_imm_abs_l, move_b_imm_d16, moveq, opcode, word)
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

LONGWORD_MASK = leaf.LONGWORD_MASK
LONGWORD_LEN = leaf.LONGWORD_BYTES
WORD_LEN = leaf.WORD_BYTES

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
        MIX_PERIOD + channel * MIX_PERIOD_LEN:
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
                    + _module_offset(MIX_PERIOD + channel * MIX_PERIOD_LEN)),
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


ENTRY_BYTES = {
    "snd_trigger_effect": _trigger_entry(),
    "snd_call_trigger_effect": _stub(*_TRIGGER_STUB),
    "snd_psg_silence": _silence_entry(),
    "snd_stop_all_sfx": _stop_all_entry(),
    "snd_stop": _stop_entry(),
}
SOUND_ROUTINE_COUNT = 5

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


def test_the_three_arms_fill_the_body_and_the_orphan_rts_follows_it():
    """Without this the entry pin would pass on a body of any length. The two bytes past the end are
    an `rts` no arm reaches — each ends with its own — and they belong to neither routine."""
    entry = leaf.entry_of("snd_trigger_effect")
    body = len(ENTRY_BYTES["snd_trigger_effect"])
    assert body == TRIGGER_BODY_BYTES, f"the three arms assemble to {body} bytes, not {body:#x}"
    orphan = bytes(harness.BASE_IMAGE[entry + body:entry + body + len(RTS)])
    assert orphan == RTS, f"the two bytes past the body are {orphan.hex()}, not an `rts`"


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
                      | set(range(MIX_PERIOD + channel * MIX_PERIOD_LEN,
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
