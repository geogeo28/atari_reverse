"""Differential test for src/player.c — the player's own frame, below behaviour slot 1.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and states (or bounds) the original's write set.

WHAT SHAPES THIS BATTERY, and it is not what shaped test_behavior.py's.

  * NOTHING HERE IS A DISPATCH ROW. These five routines are reached by `bsr` from
    `actor_behavior_type01_player` ($a38) and from each other, so a case enters each at its own
    address with the record in a0 — the leaf convention, not the handler one. The census behind that
    claim is a case of its own: four of the five are named by exactly ONE instruction in the whole
    image and the fifth by two.
  * NO MAP PROBE IS REACHED. The frame's walk ($ec8) is the routine that steps the record against the
    collision map and it is not in this batch, so no case here seeds a map — which is why the pokes
    below are a record and a handful of globals rather than test_behavior.py's whole tier.
  * THE GLOBALS ARE THE OUTPUT. Three of the five write more outside the record than in it: the two
    WB_TILE_33_* words, the two HUD slots, the message pair, the meter and the four words the death
    arm raises. Every case states them exactly.
  * ONE ARM REACHES THE SOUND MODULE THROUGH STUB +0. The death arm starts a song, so its case
    declares the chip's mixer and takes `snd_play_song`'s whole write set from test_sound.py — the
    battery that owns it — exactly as test_stage.py and test_behavior.py's slot 61 do.

KNOWINGLY NOT PINNED
  * THE REGISTERS EACH ROUTINE LEAVES BEHIND. None of the five hands one back that a caller reads:
    $a4e overwrites `player_step_and_arm`'s d0 unread and the other four are entered for their
    memory alone. The reconstruction returns nothing and nothing compares one.
  * THE TWO WRITES `player_climb` MAKES TO ONE WORD. `andi.w #$fff1,(a0)` then `addq.w #8,(a0)` are
    two stores to the x, and `subq.w #2,2(a0)` then `andi.w #$fffe,2(a0)` two to the y; the write
    ledger records FINAL values, so a port that folds each pair into one expression is
    indistinguishable from one that does not. Reproduced as the arithmetic, stated here as the
    silence.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, addq_b_dn, addq_w_d16, addq_w_ind, bcc,
                  bsr, case_salt, clr_w_abs_l, clr_w_dn, jsr_ind, keyed_block, lab, lea_abs_l,
                  lea_d16, merge_bands, move_b_d16_dn, move_b_dn_d16, move_b_imm_abs_l,
                  move_b_imm_d16, move_w_abs_l_dn, move_w_imm_abs_l, move_w_imm_abs_w,
                  move_w_imm_dn, movea_l_abs_l, moveq, opcode, program_writes, sub_w_dn_d16,
                  subq_b_d16, subq_w_d16, tst_b_abs_l, tst_w_abs_l, tst_w_abs_w, word)
from layout import wb

# The record's geometry, the register ordinals and the three BIT opcodes come from the battery that
# owns the actor table — a second copy of "what a record looks like" could disagree with src/actor.c
# while both stayed green. Same rule test_behavior.py follows.
from leaf import A0, A1, A2, A3, D0, D1                                       # noqa: E402
from test_actor import (BCLR_IMM, BEQ_W, BMI_W, BNE_W, BSET_IMM, BTST_IMM,   # noqa: E402
                        RECORD_BYTES, TABLE_DEFAULT, _sfx_bytes, bit_op_d16, jsr_d16_an)
# ...and the sound module's, from the battery that owns snd_play_song.
from test_sound import (PLAY_SONG_INSN_CAP, PLAY_SONG_MIXER, PLAY_SONG_SEEDED_BANDS,   # noqa: E402
                        PSG_REG_MIXER, STUB_TABLE_BASE, STUB_TRIGGER_OFFSET, model_play_song)


# --- the globals, from the header both languages read ---------------------------------------------
ACTOR_X = wb("ACTOR_X")
ACTOR_Y = wb("ACTOR_Y")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
FIELD_10 = wb("ACTOR_FIELD_10")
SPEED = wb("ACTOR_SPEED")
MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
FLICKER_BIT = wb("ACTOR_FLAG_FLICKER_BIT")

JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")
JOY1_UP_BIT = wb("JOY1_UP_BIT")
JOY1_DOWN_BIT = wb("JOY1_DOWN_BIT")

TILE_33_FLAG = wb("TILE_33_FLAG")
TILE_33_MODE = wb("TILE_33_MODE")
TILE_33_STEP = wb("TILE_33_STEP")
TILE_33_MODE_UP = wb("TILE_33_MODE_UP")
TILE_33_MODE_DOWN = wb("TILE_33_MODE_DOWN")
TILE_33_STEP_RAISED = wb("TILE_33_STEP_RAISED")
LADDER_STEP = wb("PLAYER_LADDER_STEP")
LADDER_X_MASK = wb("PLAYER_LADDER_X_MASK")
LADDER_X_BIAS = wb("PLAYER_LADDER_X_BIAS")
LADDER_Y_MASK = wb("PLAYER_LADDER_Y_MASK")

EFFECT_STATE_BD6A = wb("EFFECT_STATE_BD6A")
JUMP_STRENGTH_BIAS = wb("PLAYER_JUMP_STRENGTH_BIAS")
SPEED_AFTER_JUMP = wb("PLAYER_SPEED_AFTER_JUMP")
JUMP_SFX = wb("PLAYER_JUMP_SFX")
DEATH_SFX = wb("PLAYER_DEATH_SFX")
DEATH_SONG = wb("PLAYER_DEATH_SONG")
DEATH_FLAG_SET = wb("PLAYER_DEATH_FLAG_SET")
METER_REVIVE = wb("PLAYER_METER_REVIVE")

HUD_SLOT_BBC2 = wb("HUD_SLOT_BBC2")
HUD_SLOT_BBC6 = wb("HUD_SLOT_BBC6")
HUD_SLOT_REARM = wb("HUD_SLOT_REARM")
HUD_METER_VALUE = wb("HUD_METER_VALUE")
KEY_SEQUENCE_MATCHED = wb("KEY_SEQUENCE_MATCHED")
KEY_SEQUENCE_MATCHED_SET = wb("KEY_SEQUENCE_MATCHED_SET")

TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")
MESSAGE_REVIVAL_USED = wb("TEXT_MESSAGE_REVIVAL_USED")
MESSAGE_WING_BOOTS_LOST = wb("TEXT_MESSAGE_WING_BOOTS_LOST")

STAGE_RESET_BLOCK = wb("STAGE_RESET_BLOCK")
STATE_FLAG_A34 = wb("STATE_FLAG_A34")
SCROLL_FOLLOW_FROZEN = wb("SCROLL_FOLLOW_FROZEN")
PANEL_FRAME_HOLD = wb("PANEL_FRAME_HOLD")
SND_CHANNEL_A = wb("SND_CHANNEL_A")

RECORD_PTR_10420 = wb("RECORD_PTR_10420")
SCENE_SPAWN_POSITION = wb("SCENE_SPAWN_POSITION")
SPAWN_TEMPLATE_UNREAD = wb("SPAWN_TEMPLATE_UNREAD")
TYPE35_TEMPLATE = wb("ACTOR_TYPE35_TEMPLATE")

# Where a case puts the player's record: an ordinary slot of the default table, with a record's
# margin either side seeded so that a write one field or one record out lands on bytes that are wrong
# FOR WHERE THEY WERE WRITTEN rather than on zeros.
ACTOR = TABLE_DEFAULT + 5 * RECORD_BYTES
SEEDED_LO = ACTOR - RECORD_BYTES
SEEDED_LEN = 3 * RECORD_BYTES

# A value no arm of any routine here writes, so a byte still holding it was not written.
MARKER = 0x5a


def _pokes(what, fields=None):
    """A seeded image: the record and its margin, address-keyed, plus whatever the case states.

    The GLOBALS are deliberately NOT keyed. Every one of them steers a branch, so a keyed byte would
    choose the arm instead of the case; each is seeded explicitly by the case that reads it, and the
    two the routines merely OVERWRITE (the message pair) are seeded to MARKER here so that writing
    them is a change the ledger can see."""
    base = {SEEDED_LO: keyed_block(SEEDED_LO, SEEDED_LEN, case_salt(what)),
            TEXT_REQUEST: bytes([MARKER]),
            TEXT_LIFETIME_REQUEST: word(MARKER),
            TILE_33_STEP: word(MARKER)}
    return leaf.overlay(base, fields or {})


def _assert_writes(info, expected, what):
    """The oracle's write set, stated EXACTLY — every case here can say what it wrote."""
    leaf.assert_written_is(info, {addr: bytes([value]) if isinstance(value, int) else value
                                  for addr, value in expected.items()}, what)


def _put_word(expected, addr, value):
    expected[addr] = (value >> 8) & 0xff
    expected[addr + 1] = value & 0xff


# --- the encodings this battery's entry pins need --------------------------------------------------
# Everything already in leaf.py is imported above; these are the forms no battery had. They are
# spelt from the 68000's own field layout rather than transcribed, so a wrong register or a wrong
# operand size fails on the image's bytes.

def btst_imm_abs_w(bit, addr):
    """`btst #n,addr.w` — how the player's tier reads the joystick's HELD state, against the
    `btst #n,Dn` its edge tests use."""
    return opcode(0x0838) + word(bit) + word(addr)


def andi_w_ind(base, value):
    """`andi.w #imm,(An)` — the ladder's x snap, applied IN MEMORY."""
    return opcode(0x0250 | base) + word(value)


def andi_w_d16(base, value, displacement):
    """...and the same over d16(An), for the y."""
    return opcode(0x0268 | base) + word(value) + word(displacement)







def subq_b_abs_l(amount, addr):
    return opcode(0x5139 | leaf.quick_field(amount)) + addr.to_bytes(LONGWORD_BYTES, "big")



def addi_b_dn(reg, value):
    """`addi.b #imm,Dn` — the jump strength's own add, and a BYTE one where the walk's is a word."""
    return opcode(0x0600 | reg) + word(value & 0xff)



def move_l_d16_postinc(source, destination, displacement):
    """`move.l d16(As),(Ad)+` — the scene descriptor's position longword."""
    return opcode(0x20c0 | (destination << 9) | (5 << 3) | source) + word(displacement)


def move_l_postinc_postinc(source, destination):
    """`move.l (As)+,(Ad)+` — the seven the template supplies."""
    return opcode(0x20d8 | (destination << 9) | source)


# --- the entry pins ---------------------------------------------------------------------------------
JOY1_NEWLY_PRESSED = "joy1_newly_pressed"


def _meter_empty_pieces():
    """$a76 — the death check. Two arms and one shared `rts`."""
    return [
        tst_w_abs_l(HUD_METER_VALUE),
        bcc(BNE_W, "out"),
        tst_b_abs_l(HUD_SLOT_BBC6),
        bcc(BNE_W, "revive"),
        tst_w_abs_w(KEY_SEQUENCE_MATCHED),
        bcc(BEQ_W, "die"),
        lab("revive"),
        move_w_imm_dn(D0, DEATH_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        tst_w_abs_w(KEY_SEQUENCE_MATCHED),
        bcc(BNE_W, "post"),
        move_w_imm_abs_l(HUD_SLOT_REARM, HUD_SLOT_BBC6),
        lab("post"),
        move_b_imm_abs_l(MESSAGE_REVIVAL_USED, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        move_w_imm_abs_l(METER_REVIVE, HUD_METER_VALUE),
        RTS,
        lab("die"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        tst_w_abs_l(STAGE_RESET_BLOCK),
        bcc(BMI_W, "out"),
        move_w_imm_abs_w(DEATH_FLAG_SET, STATE_FLAG_A34),
        lea_abs_l(A1, STUB_TABLE_BASE),
        move_w_imm_dn(D0, DEATH_SONG),
        jsr_ind(A1),
        move_w_imm_abs_l(DEATH_FLAG_SET, STAGE_RESET_BLOCK),
        move_w_imm_abs_l(DEATH_FLAG_SET, SCROLL_FOLLOW_FROZEN),
        move_w_imm_abs_l(DEATH_FLAG_SET, PANEL_FRAME_HOLD),
        lab("out"),
        RTS,
    ]


def _jump_step_pieces():
    """$e06 — the jump machine. Three exclusive arms over WB_ACTOR_FLAGS, and a head that runs on
    every one of them."""
    return [
        clr_w_abs_l(TILE_33_STEP),
        move_w_abs_l_dn(D0, EFFECT_STATE_BD6A),
        addi_b_dn(D0, JUMP_STRENGTH_BIAS),
        move_b_dn_d16(D0, A0, FIELD_10),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "ascend"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "launch"),
        # the wing boots
        tst_b_abs_l(HUD_SLOT_BBC2),
        bcc(BEQ_W, "out"),
        btst_imm_abs_w(JOY1_UP_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "out"),
        move_b_imm_d16(A0, SPEED_AFTER_JUMP, SPEED),
        subq_b_abs_l(1, HUD_SLOT_BBC2),
        bcc(BNE_W, "out"),
        move_w_imm_abs_l(HUD_SLOT_REARM, HUD_SLOT_BBC2),
        move_b_imm_abs_l(MESSAGE_WING_BOOTS_LOST, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        lab("out"),
        RTS,
        lab("launch"),
        bsr(JOY1_NEWLY_PRESSED),
        leaf.btst_imm_dn(JOY1_UP_BIT, D0),
        bcc(BNE_W, "fire"),
        RTS,
        lab("fire"),
        move_w_imm_dn(D0, JUMP_SFX),
        move_w_imm_dn(D1, SND_CHANNEL_A),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        move_b_d16_dn(D0, A0, FIELD_10),
        move_b_dn_d16(D0, A0, SPEED),
        RTS,
        lab("ascend"),
        moveq(0, D0),
        move_b_d16_dn(D0, A0, SPEED),
        sub_w_dn_d16(D0, A0, ACTOR_Y),
        subq_b_d16(1, A0, SPEED),
        bcc(BNE_W, "done"),
        bit_op_d16(BCLR_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, SPEED_AFTER_JUMP, SPEED),
        lab("done"),
        RTS,
    ]


def _climb_arm(mode, step_op):
    """The ladder's two arms, which are one body with the mode word and the y step exchanged."""
    return [
        bit_op_d16(BCLR_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_w_imm_abs_l(TILE_33_STEP_RAISED, TILE_33_STEP),
        andi_w_ind(A0, LADDER_X_MASK),
        addq_w_ind(LADDER_X_BIAS, A0),
        move_w_imm_abs_l(mode, TILE_33_MODE),
        step_op,
        andi_w_d16(A0, LADDER_Y_MASK, ACTOR_Y),
        RTS,
    ]


def _apply_joystick_pieces():
    """$d84 — the ladder. Its LAST instruction is an `rts` at $e04, which is what says it does not
    fall into the jump machine at $e06 below it."""
    return ([
        tst_w_abs_l(TILE_33_FLAG),
        bcc(BEQ_W, "none"),
        btst_imm_abs_w(JOY1_UP_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "down"),
    ] + _climb_arm(TILE_33_MODE_UP, subq_w_d16(LADDER_STEP, A0, ACTOR_Y)) + [
        lab("down"),
        btst_imm_abs_w(JOY1_DOWN_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "none"),
    ] + _climb_arm(TILE_33_MODE_DOWN, addq_w_d16(LADDER_STEP, A0, ACTOR_Y)) + [
        lab("none"),
        clr_w_abs_l(TILE_33_STEP),
        RTS,
    ])


def _reset_ground_pieces():
    """$107c — leaving the ladder. The one instruction that separates it from the jump machine's own
    head is the operand size: `addq.b #8,d0` where $e12 spells `addi.b #$8,d0`."""
    return [
        clr_w_abs_l(TILE_33_MODE),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_w_abs_l_dn(D0, EFFECT_STATE_BD6A),
        addq_b_dn(JUMP_STRENGTH_BIAS, D0),
        move_b_dn_d16(D0, A0, SPEED),
        RTS,
    ]


def _copy_record_pieces():
    """$539e — eight longwords, and the first is not the template's."""
    return ([
        movea_l_abs_l(A3, RECORD_PTR_10420),
        move_l_d16_postinc(A3, A2, SCENE_SPAWN_POSITION),
        lea_d16(A1, SPAWN_TEMPLATE_UNREAD, A1),
    ] + [move_l_postinc_postinc(A1, A2)] * TEMPLATE_LONGWORDS + [RTS])


TEMPLATE_LONGWORDS = (RECORD_BYTES - LONGWORD_BYTES) // LONGWORD_BYTES

ENTRY_PIECES = {
    "player_meter_empty_check": _meter_empty_pieces(),
    "player_jump_step": _jump_step_pieces(),
    "player_apply_joystick": _apply_joystick_pieces(),
    "player_reset_ground_state": _reset_ground_pieces(),
    "scene_copy_record_fields": _copy_record_pieces(),
}
RECONSTRUCTED_ROUTINES = 5

ENTRY_BYTES = {name: leaf.asm(leaf.entry_of(name), pieces)
               for name, pieces in ENTRY_PIECES.items()}
INSN_COUNT = {name: leaf.instruction_count(pieces) for name, pieces in ENTRY_PIECES.items()}

# The two callees this file's bodies reach, as upper bounds on one call. Both belong to other
# batteries; `joy1_newly_pressed`'s body is five instructions and test_input.py pins it, and the SFX
# stub's cap comes from the battery that owns the sound module.
from test_sound import STUB_INSN_CAP    # noqa: E402
JOY_EDGE_INSNS = 8


def _cap(name, extra=0):
    """A run's instruction cap, DERIVED from the pin: every instruction of the body once, plus the
    runner's sentinel, plus whatever a callee adds. Nothing here states a round number."""
    return INSN_COUNT[name] + leaf.RUNNER_SENTINEL_INSN + extra


JUMP_STEP_CAP = _cap("player_jump_step", extra=JOY_EDGE_INSNS + STUB_INSN_CAP)
# The death arm's is the widest here: the trigger's stub on one arm, stub +0 and the whole song start
# on the other, so the cap carries both rather than being split per arm.
METER_EMPTY_CAP = _cap("player_meter_empty_check", extra=STUB_INSN_CAP + PLAY_SONG_INSN_CAP)


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


# The extents, so a pin that stopped one instruction short fails here rather than leaving the tail
# unpinned. Each is bounded by the next routine's own entry or by the data that follows it.
BODY_SIZES = {
    "player_meter_empty_check": 146,    # $a76..$b07, bounded by WB_STAGE_RESET_BLOCK's 18 bytes
    "player_apply_joystick": 130,       # $d84..$e05 — and NOT on to $e06: the `rts` at $e04 is its
                                        # own, which is the plate correction this batch makes
    "player_jump_step": 194,            # $e06..$ec7, bounded by player_step_and_arm's entry
    "player_reset_ground_state": 38,    # $107c..$10a1, bounded by actor_step_left_against_map
    "scene_copy_record_fields": 30,     # $539e..$53bb, bounded by actor_behavior_type36's entry
}


@pytest.mark.parametrize("name", sorted(BODY_SIZES), ids=sorted(BODY_SIZES))
def test_the_pin_is_the_whole_body(name):
    assert len(ENTRY_BYTES[name]) == BODY_SIZES[name], (
        f"{name}'s pin covers {len(ENTRY_BYTES[name])} bytes of a {BODY_SIZES[name]}-byte body")


# --- the census: how each of these routines is reached ----------------------------------------------
# "Reached only from the player's frame" is what ../names.txt's plates say, and batch 31's hidden
# `jsr $6f9e.w` is why it is measured rather than assumed. The scan is test_behavior.py's — every way
# an instruction can name an address, keyed by target — and it is imported rather than restated so
# the two censuses cannot disagree about the same instruction.
from test_behavior import CONTROL_FLOW_TARGETS, PC_RELATIVE_SOURCE_TARGETS   # noqa: E402

CALLERS = {
    # the frame's own `bsr`s, at $a38..$a73
    "player_meter_empty_check": (0xa38,),
    "player_apply_joystick": (0xa60,),
    # $e06 has exactly ONE entrance and it is the gate's `beq.w`, which is what retires the plate's
    # claim that player_apply_joystick "also falls into" it.
    "player_jump_step": (0xd7e,),
    # ...and $107c has TWO, both inside player_step_and_arm's walk arms.
    "player_reset_ground_state": (0xfb2, 0x101e),
    "scene_copy_record_fields": (0xc5e,),
}


@pytest.mark.parametrize("name", sorted(CALLERS), ids=sorted(CALLERS))
def test_each_routine_is_named_by_exactly_the_instructions_the_plate_says(name):
    entry = leaf.entry_of(name)
    assert tuple(sorted(CONTROL_FLOW_TARGETS.get(entry, []))) == CALLERS[name], (
        f"{name} @ {entry:#x} is named by "
        f"{[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}, not {CALLERS[name]}")


@pytest.mark.parametrize("name", sorted(CALLERS), ids=sorted(CALLERS))
def test_no_pc_relative_read_anywhere_in_the_program_names_one_of_these_entries(name):
    """The NEGATIVE half, and the one the mode-shaped sweep exists for: not even a scan that decodes
    every word in the program as a PC-relative read finds one aimed here."""
    entry = leaf.entry_of(name)
    assert entry not in PC_RELATIVE_SOURCE_TARGETS, (
        f"{name} @ {entry:#x} is read PC-relatively by "
        f"{[hex(at) for at, _op in PC_RELATIVE_SOURCE_TARGETS[entry]]}")


# --- $107c: leaving the ladder ------------------------------------------------------------------
_RESET_GROUND = leaf.register_glue("player_reset_ground_state", [ctypes.c_uint32])


@pytest.mark.parametrize("strength,flags", [(0x0000, 0x00), (0x0021, 0xff), (0x00f8, 1 << MOVING_BIT),
                                            (0xff7f, 0x00)],
                         ids=["zero", "all-flags", "byte-wrap", "high-half"])
def test_leaving_the_ladder_puts_the_record_back_into_a_fall(strength, flags):
    """`byte-wrap` is the row the operand size turns on: `addq.b #8,d0` over a state word of $f8
    leaves ZERO in the byte and does NOT carry into the high half, so the speed stamped is 0 and not
    $100. `high-half` says the same from the other side — only the low byte is read."""
    what = f"player_reset_ground_state strength={strength:#06x} flags={flags:#04x}"
    pokes = _pokes(what, {TILE_33_MODE: word(TILE_33_MODE_DOWN),
                          EFFECT_STATE_BD6A: word(strength),
                          ACTOR + ACTOR_FLAGS: bytes([flags]),
                          ACTOR + SPEED: bytes([MARKER])})

    expected = {}
    _put_word(expected, TILE_33_MODE, 0)
    expected[ACTOR + ACTOR_FLAGS] = (flags & ~(1 << SUPPORTED_BIT)) | (1 << MOVING_BIT) \
        | (1 << LAUNCHED_BIT)
    expected[ACTOR + SPEED] = (strength + JUMP_STRENGTH_BIAS) & 0xff

    info = leaf.run("player_reset_ground_state", _RESET_GROUND(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("player_reset_ground_state"))
    _assert_writes(info, expected, what)


# --- $d84: the ladder -------------------------------------------------------------------------------
_APPLY_JOYSTICK = leaf.register_glue("player_apply_joystick", [ctypes.c_uint32])


def _run_ladder(what, pokes, expected):
    info = leaf.run("player_apply_joystick", _APPLY_JOYSTICK(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=_cap("player_apply_joystick"))
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("held", [0x00, 1 << JOY1_UP_BIT, 1 << JOY1_DOWN_BIT, 0xff],
                         ids=["idle", "up", "down", "everything"])
def test_the_ladder_does_nothing_but_lower_the_step_flag_while_the_tile_flag_is_down(held):
    """The gate is WB_TILE_33_FLAG and not the joystick: with the flag down, every direction —
    including both at once — clears WB_TILE_33_STEP and returns."""
    what = f"player_apply_joystick flag down held={held:#04x}"
    pokes = _pokes(what, {TILE_33_FLAG: word(0), JOY1_CURRENT: bytes([held])})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    _run_ladder(what, pokes, expected)


def test_neither_direction_held_on_a_ladder_clears_the_step_flag_too():
    """The third path to the same two bytes, and the one that says the arms are exclusive rather
    than the flag being the only test."""
    what = "player_apply_joystick on a ladder, idle"
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff), JOY1_CURRENT: bytes([0])})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    _run_ladder(what, pokes, expected)


@pytest.mark.parametrize("x", [0x0100, 0x0101, 0x010f, 0x0108],
                         ids=["even-aligned", "odd", "cell-top", "already-centred"])
@pytest.mark.parametrize("held,mode,step", [(1 << JOY1_UP_BIT, TILE_33_MODE_UP, -1),
                                            (1 << JOY1_DOWN_BIT, TILE_33_MODE_DOWN, +1)],
                         ids=["up", "down"])
def test_climbing_snaps_the_x_to_the_ladders_centre_and_keeps_its_low_bit(x, held, mode, step):
    """`andi.w #$fff1,(a0)` KEEPS BIT 0 — the mask is not $fff0 — so an odd x is still odd after the
    snap; the `odd` row is what a port that rounded to the cell would fail. The two arms differ in
    the mode word they publish and in the direction of the y step, and in nothing else."""
    what = f"player_apply_joystick climb mode={mode:#06x} x={x:#06x}"
    y, flags = 0x0141, 0xff
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff), JOY1_CURRENT: bytes([held]),
                          ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                          ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {}
    expected[ACTOR + ACTOR_FLAGS] = flags & ~((1 << MOVING_BIT) | (1 << LAUNCHED_BIT))
    _put_word(expected, TILE_33_STEP, TILE_33_STEP_RAISED)
    _put_word(expected, ACTOR + ACTOR_X, (x & LADDER_X_MASK) + LADDER_X_BIAS)
    _put_word(expected, TILE_33_MODE, mode)
    _put_word(expected, ACTOR + ACTOR_Y, (y + step * LADDER_STEP) & LADDER_Y_MASK)
    _run_ladder(what, pokes, expected)


def test_holding_both_directions_climbs_UP_because_bit_0_is_tested_first():
    """The order of the two `btst`s, as a case: nothing else in the routine separates them."""
    what = "player_apply_joystick both directions"
    x, y = 0x0100, 0x0140
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff),
                          JOY1_CURRENT: bytes([(1 << JOY1_UP_BIT) | (1 << JOY1_DOWN_BIT)]),
                          ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                          ACTOR + ACTOR_FLAGS: bytes([0])})

    expected = {}
    expected[ACTOR + ACTOR_FLAGS] = 0
    _put_word(expected, TILE_33_STEP, TILE_33_STEP_RAISED)
    _put_word(expected, ACTOR + ACTOR_X, (x & LADDER_X_MASK) + LADDER_X_BIAS)
    _put_word(expected, TILE_33_MODE, TILE_33_MODE_UP)
    _put_word(expected, ACTOR + ACTOR_Y, (y - LADDER_STEP) & LADDER_Y_MASK)
    _run_ladder(what, pokes, expected)


def test_the_two_ladder_modes_are_different_words_and_the_case_above_can_tell_them_apart():
    """A guard on the seeding, not on the game: if the two mode constants were equal the parametrised
    case above would pin neither arm's publish."""
    assert TILE_33_MODE_UP != TILE_33_MODE_DOWN
    assert TILE_33_MODE_UP != 0 and TILE_33_MODE_DOWN != 0


# --- $e06: the jump machine ---------------------------------------------------------------------
_JUMP_STEP = leaf.register_glue("player_jump_step", [ctypes.c_uint32])
STRENGTH = 0x0021          # a state word whose low byte + the bias is neither 0 nor the seed


def _jump_pokes(what, flags, fields=None):
    base = {ACTOR + ACTOR_FLAGS: bytes([flags]),
            ACTOR + FIELD_10: bytes([MARKER]),
            ACTOR + SPEED: bytes([MARKER]),
            EFFECT_STATE_BD6A: word(STRENGTH),
            HUD_SLOT_BBC2: bytes([0]),
            JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([0])}
    return _pokes(what, leaf.overlay(base, fields or {}))


def _jump_head(expected):
    """The two bytes every arm writes before the three-way test."""
    _put_word(expected, TILE_33_STEP, 0)
    expected[ACTOR + FIELD_10] = (STRENGTH + JUMP_STRENGTH_BIAS) & 0xff
    return expected


def _run_jump(what, pokes, expected, extra_band=()):
    info = leaf.run("player_jump_step", _JUMP_STEP(ACTOR),
                    merge_bands(expected) + list(extra_band), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=JUMP_STEP_CAP)
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("strength", [0x0000, 0x0021, 0x00f8, 0xff01],
                         ids=["zero", "ordinary", "byte-wrap", "high-half"])
def test_every_frame_restamps_the_jump_strength_from_the_state_word(strength):
    """`addi.b #$8,d0` on the LOW BYTE of WB_EFFECT_STATE_BD6A — the same number
    player_reset_ground_state adds with `addq.b`, and the same wrap. The record is seeded AIRBORNE
    with no wing-boot charge, so the head is the whole of the frame."""
    what = f"player_jump_step head strength={strength:#06x}"
    pokes = _jump_pokes(what, flags=0, fields={EFFECT_STATE_BD6A: word(strength)})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    expected[ACTOR + FIELD_10] = (strength + JUMP_STRENGTH_BIAS) & 0xff
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("speed", [2, 8, 0xff], ids=lambda v: f"speed{v:#04x}")
def test_an_ascending_record_rises_by_its_own_speed_and_spends_one(speed):
    """`sub.w d0,2(a0)` on a ZERO-EXTENDED byte, so the record always rises — a speed of $ff lifts it
    255 pixels rather than dropping it one."""
    what = f"player_jump_step ascending speed={speed:#04x}"
    y = 0x0140
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={ACTOR + SPEED: bytes([speed]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, (y - speed) & 0xffff)
    expected[ACTOR + SPEED] = speed - 1
    _run_jump(what, pokes, expected)


def test_the_ascent_ends_on_the_frame_the_speed_reaches_zero():
    """...and what it leaves behind is a speed of 1, which is what makes the record start falling at
    one pixel a frame rather than at none."""
    what = "player_jump_step ascent ending"
    y, flags = 0x0140, (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
    pokes = _jump_pokes(what, flags=flags,
                        fields={ACTOR + SPEED: bytes([1]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - 1)
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << MOVING_BIT)
    _run_jump(what, pokes, expected)


def test_an_ascent_entered_on_a_zero_speed_wraps_the_byte_instead_of_ending():
    """`subq.b #1` on $00 is $ff, and the `bne` reads THAT — so the climb does not end, it runs for
    another 255 frames. The row a port that tested the byte BEFORE the decrement would fail."""
    what = "player_jump_step ascent on a zero speed"
    y = 0x0140
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={ACTOR + SPEED: bytes([0]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = 0xff
    # The y IS in the expected set even though it does not change: `sub.w d0,2(a0)` with d0 = 0
    # STORES the value already there, and the oracle's ledger records the store rather than the
    # difference — so a port that skipped the subtraction on a zero speed would redden here.
    _put_word(expected, ACTOR + ACTOR_Y, y)
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("prev,current", [(0, 0), (1 << JOY1_UP_BIT, 1 << JOY1_UP_BIT), (0xff, 0xff),
                                          (0, 1 << JOY1_DOWN_BIT)],
                         ids=["idle", "held", "everything-held", "wrong-direction"])
def test_a_standing_record_needs_a_RISING_up_edge_to_launch(prev, current):
    """`bsr $682 / btst #0,d0` — the EDGE, not the level: a stick already up when the frame begins
    launches nothing. The `everything-held` row is what separates the edge test from a level one."""
    what = f"player_jump_step standing prev={prev:#04x} current={current:#04x}"
    pokes = _jump_pokes(what, flags=1 << SUPPORTED_BIT,
                        fields={JOY1_PREV: bytes([prev]), JOY1_CURRENT: bytes([current])})

    _run_jump(what, pokes, _jump_head({}))


def test_the_launch_fires_its_effect_and_loads_the_speed_from_the_strength_byte():
    """The whole of the launch: the SFX through stub +56 (whose write set comes from the battery that
    owns the trigger), the two motion bits up, the supported bit down, and WB_ACTOR_SPEED loaded from
    the byte the HEAD of this same frame has just written — so the height is this frame's."""
    what = "player_jump_step launching"
    flags = 1 << SUPPORTED_BIT
    pokes = _jump_pokes(what, flags=flags,
                        fields={JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})
    image = harness.make_image(pokes)

    expected = _jump_head({})
    expected.update(_sfx_bytes(image, JUMP_SFX, SND_CHANNEL_A))
    expected[ACTOR + ACTOR_FLAGS] = (flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) \
        & ~(1 << SUPPORTED_BIT)
    expected[ACTOR + SPEED] = (STRENGTH + JUMP_STRENGTH_BIAS) & 0xff
    _run_jump(what, pokes, expected)


def test_a_STANDING_record_with_wing_boots_burns_NONE_of_them():
    """THE THREE ARMS ARE EXCLUSIVE, which no case here said until the independent gate asked. Every
    hover case seeds the record airborne and every launch case seeds an empty slot, so a port that
    ran the hover BELOW the launch instead of instead of it answered the same on all of them — and
    the state it gets wrong is ordinary: the frame after landing with boots still on, where the
    charge would burn away while the player stands still.

    The seed is SUPPORTED with a full slot and UP HELD but not newly pressed, so the launch arm is
    entered and declines, and the whole frame must be the head."""
    what = "player_jump_step standing on wing boots"
    charge = 4
    pokes = _jump_pokes(what, flags=1 << SUPPORTED_BIT,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    _run_jump(what, pokes, _jump_head({}))


def test_an_ASCENDING_record_with_wing_boots_burns_none_of_them_either():
    """...and the same for the first arm, which the same mutant also reaches: a rising record with a
    full slot spends its own speed and none of the charge."""
    what = "player_jump_step ascending on wing boots"
    y, charge, speed = 0x0140, 4, 3
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                ACTOR + SPEED: bytes([speed]), ACTOR + ACTOR_Y: word(y),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - speed)
    expected[ACTOR + SPEED] = speed - 1
    _run_jump(what, pokes, expected)


def test_the_ascending_bit_is_tested_before_the_supported_one():
    """A record carrying BOTH takes the ascent, which is what says the three arms are ordered rather
    than exclusive by construction — and a launch would have been visible, because this seed also
    supplies the rising edge the launch needs."""
    what = "player_jump_step ascending and supported"
    y = 0x0140
    flags = (1 << MOVING_BIT) | (1 << SUPPORTED_BIT)
    pokes = _jump_pokes(what, flags=flags,
                        fields={ACTOR + SPEED: bytes([4]), ACTOR + ACTOR_Y: word(y),
                                JOY1_PREV: bytes([0]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - 4)
    expected[ACTOR + SPEED] = 3
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("charge,held", [(0, 1 << JOY1_UP_BIT), (3, 0), (0, 0)],
                         ids=["no-charge", "not-held", "neither"])
def test_the_wing_boots_need_a_charge_AND_the_stick_held(charge, held):
    """Two tests in series, and this is both of their negatives."""
    what = f"player_jump_step hover charge={charge} held={held:#04x}"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]), JOY1_CURRENT: bytes([held])})

    _run_jump(what, pokes, _jump_head({}))


def test_the_wing_boots_read_the_stick_HELD_and_not_its_rising_edge():
    """The row that separates `btst #0,$8cf.w` from the `bsr $682 / btst #0,d0` one instruction
    arm up: the stick was ALREADY up last frame, so there is no edge — and the boots still burn. Every
    other hover case seeds a clear previous frame, where the two readings answer the same."""
    what = "player_jump_step hovering with the stick already up"
    charge = 4
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[HUD_SLOT_BBC2] = charge - 1
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("charge", [2, 0x80, 0xff], ids=lambda v: f"charge{v:#04x}")
def test_the_wing_boots_hold_the_fall_at_one_pixel_and_spend_a_charge(charge):
    """Every frame the stick is held: the fall speed forced to 1 and one charge off the slot's VALUE
    byte, which is a BYTE write into the low half of a slot whose other half is the redraw request."""
    what = f"player_jump_step hovering charge={charge:#04x}"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[HUD_SLOT_BBC2] = charge - 1
    _run_jump(what, pokes, expected)


def test_the_last_charge_rearms_the_slot_and_posts_the_message_that_names_it():
    """WHAT THE SLOT IS, as a case: message WB_TEXT_MESSAGE_WING_BOOTS_LOST is "You lost wing boots."
    and this is the only routine that posts it. The rearm is a WORD, so the value goes back to zero
    and the request byte beside it comes up — WB_HUD_SLOT_REARM, the same word both damage paths
    write."""
    what = "player_jump_step spending the last wing-boot charge"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([1]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    _put_word(expected, HUD_SLOT_BBC2, HUD_SLOT_REARM)
    expected[TEXT_REQUEST] = MESSAGE_WING_BOOTS_LOST
    _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    _run_jump(what, pokes, expected)


def test_the_message_the_wing_boots_post_is_the_one_the_shipped_string_names():
    """The id is 1-based into WB_TEXT_MESSAGE_TABLE, so the claim above is checkable against the
    image's own bytes rather than against this battery's reading of them."""
    table = wb("TEXT_MESSAGE_TABLE")
    first = wb("TEXT_MESSAGE_FIRST_ID")
    shift = wb("TEXT_MESSAGE_PTR_SHIFT")
    at = table + (MESSAGE_WING_BOOTS_LOST - first) * (1 << shift)
    where = int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")
    text = bytes(harness.BASE_IMAGE[where:where + 32])
    assert b"wing boots" in text.lower(), f"message {MESSAGE_WING_BOOTS_LOST:#x} reads {text!r}"


# --- $a76: the death check --------------------------------------------------------------------------
_METER_EMPTY = leaf.register_glue("player_meter_empty_check", [ctypes.c_uint32])


def _death_pokes(what, fields=None):
    """The death check's own inputs, and the sound module's state seeded AWAY from what a song start
    writes so that each of its stores is a change rather than a coincidence."""
    base = {ACTOR + ACTOR_FLAGS: bytes([0xff]),
            HUD_METER_VALUE: word(0),
            HUD_SLOT_BBC6: bytes([0]),
            STAGE_RESET_BLOCK: word(0),
            STATE_FLAG_A34: word(MARKER),
            SCROLL_FOLLOW_FROZEN: word(MARKER),
            PANEL_FRAME_HOLD: word(MARKER)}
    salt = case_salt(what)
    base.update({lo: keyed_block(lo, length, salt) for lo, length in PLAY_SONG_SEEDED_BANDS})
    return _pokes(what, leaf.overlay(base, fields or {}))


@pytest.mark.parametrize("meter", [1, 0x14, 0xffff], ids=lambda v: f"meter{v:#06x}")
def test_a_meter_with_anything_left_in_it_makes_the_whole_routine_a_no_op(meter):
    """`tst.w $b6fa / bne` — the routine's first instruction, and on all but one frame of a life the
    whole of it."""
    what = f"player_meter_empty_check meter={meter:#06x}"
    pokes = _death_pokes(what, {HUD_METER_VALUE: word(meter)})

    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    assert not program_writes(info), f"{what}: the check wrote memory on a live meter"


def _revive_expected(image, rearm):
    expected = _sfx_bytes(image, DEATH_SFX, SND_CHANNEL_A)
    if rearm:
        _put_word(expected, HUD_SLOT_BBC6, HUD_SLOT_REARM)
    expected[TEXT_REQUEST] = MESSAGE_REVIVAL_USED
    _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    _put_word(expected, HUD_METER_VALUE, METER_REVIVE)
    return expected


@pytest.mark.parametrize("charge", [1, 0x80, 0xff], ids=lambda v: f"charge{v:#04x}")
def test_an_empty_meter_with_a_revival_medicine_spends_it_and_refills(charge):
    """WHAT THE SLOT IS: message WB_TEXT_MESSAGE_REVIVAL_USED is "Used the revival medicine." and
    this is its only writer. Note the meter comes back on WB_PLAYER_METER_REVIVE and not on
    WB_HUD_METER_MAX — a revived player gets twenty units whatever the maximum is."""
    what = f"player_meter_empty_check reviving charge={charge:#04x}"
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: bytes([charge])})
    image = harness.make_image(pokes)

    expected = _revive_expected(image, rearm=True)
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


# --- THE ONE ARM NO CASE HERE CAN DRIVE, and why -------------------------------------------------
#
# WB_KEY_SEQUENCE_MATCHED steers both of the death check's tests — a raised word takes the revival
# arm with an EMPTY medicine slot and then SKIPS the rearm, so a cheating player revives for ever —
# and no case in this file can put a value there. The word lives at $604, inside the kit's
# harness-poked input block ($600..$61f), which for this project lies inside the game's own program
# because it loads at $3f8. `harness.make_image` REFUSES any poke landing in that block, and it is
# right to: nothing can tell a poke staging kit model state from one patching the program at the
# same address (test_poked_input_guard.py owns the waiver and its three guards).
#
# So the two cases below state the limitation instead of hiding it. What the differential DOES cover
# is the ordinary machine: the shipped word is zero, every case above runs on that, and the arm they
# drive is the medicine slot's own. The cheat arm is reproduced in src/player.c and is UNPINNED.


def test_a_REARMED_medicine_slot_is_an_empty_one_to_this_test():
    """`tst.b $bbc6.l` reads the slot's VALUE byte, not the word: a slot holding WB_HUD_SLOT_REARM —
    value zero with the redraw request beside it up — is EMPTY here and the frame dies. The row that
    separates the byte test from a word one, and the only seed in this file that puts anything in a
    slot's second byte."""
    what = "player_meter_empty_check on a rearmed medicine slot"
    flags = 0xff
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: word(HUD_SLOT_REARM),
                                STAGE_RESET_BLOCK: word(0xffff),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {ACTOR + ACTOR_FLAGS: flags & ~(1 << FLICKER_BIT)}
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


def test_the_cheat_word_is_zero_in_the_shipped_image_so_every_case_here_runs_without_it():
    """Which is what makes the revival cases above the SLOT's arm rather than the cheat's."""
    at = KEY_SEQUENCE_MATCHED
    assert int.from_bytes(harness.BASE_IMAGE[at:at + WORD_BYTES], "big") == 0


def test_the_cheat_word_cannot_be_SEEDED_because_it_shares_the_poked_input_block():
    """The limitation, as a tripwire. If the kit's block ever moves clear of this program — or the
    project's load base rises — this case fails and the arm above becomes drivable, which is exactly
    when someone should come back and write the differential this comment stands in for."""
    with pytest.raises(RuntimeError, match="harness-poked input block"):
        harness.make_image({KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET)})


def test_a_death_already_in_progress_only_lowers_the_flicker_bit():
    """`tst.w $b08 / bmi` is a SIGN test and not a zero one: the word this arm raises is $ffff, so a
    second death on a later frame stops at the test. Everything below it — the song, the three
    words — is therefore missing from the write set."""
    what = "player_meter_empty_check on a death already in progress"
    flags = 0xff
    pokes = _death_pokes(what, {STAGE_RESET_BLOCK: word(0xffff),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {ACTOR + ACTOR_FLAGS: flags & ~(1 << FLICKER_BIT)}
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("block", [0, 1, 0x7fff], ids=["zero", "one", "largest-positive"])
def test_the_death_arm_starts_the_song_and_raises_the_four_words(block):
    """THE ARM THAT REACHES THE SOUND MODULE, through stub +0 with d0 = WB_PLAYER_DEATH_SONG. What
    the frame writes is snd_play_song's whole write set — taken from the battery that OWNS it — plus
    the flicker bit and the four words. `largest-positive` is the row that says the guard above is a
    SIGN test: $7fff is not negative, so the death runs."""
    what = f"player_meter_empty_check dying block={block:#06x}"
    flags = 0xff
    pokes = _death_pokes(what, {STAGE_RESET_BLOCK: word(block),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})
    image = harness.make_image(pokes)

    song = model_play_song(image, DEATH_SONG)
    expected = {addr + index: value[index]
                for addr, value in song.items() for index in range(len(value))}
    expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << FLICKER_BIT)
    for global_word in (STATE_FLAG_A34, STAGE_RESET_BLOCK, SCROLL_FOLLOW_FROZEN, PANEL_FRAME_HOLD):
        _put_word(expected, global_word, DEATH_FLAG_SET)

    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP,
                    psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    _assert_writes(info, expected, what)


def test_the_message_the_revival_arm_posts_is_the_one_the_shipped_string_names():
    """The other half of the pair above, read off the image."""
    table = wb("TEXT_MESSAGE_TABLE")
    first = wb("TEXT_MESSAGE_FIRST_ID")
    shift = wb("TEXT_MESSAGE_PTR_SHIFT")
    at = table + (MESSAGE_REVIVAL_USED - first) * (1 << shift)
    where = int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")
    text = bytes(harness.BASE_IMAGE[where:where + 40])
    assert b"revival" in text.lower(), f"message {MESSAGE_REVIVAL_USED:#x} reads {text!r}"


# --- $539e: the event actor's spawn -----------------------------------------------------------------
_COPY_RECORD = leaf.register_glue("scene_copy_record_fields", [ctypes.c_uint32] * 2)

# Where a case puts the scene descriptor and the record being filled. Both are ordinary table slots,
# so the copy's destination has a seeded margin either side exactly as every other case's record has.
SCENE = TABLE_DEFAULT + 1 * RECORD_BYTES
DESTINATION = TABLE_DEFAULT + 8 * RECORD_BYTES
COPY_SEEDED_LO = TABLE_DEFAULT
COPY_SEEDED_LEN = 10 * RECORD_BYTES


def _copy_pokes(what, template):
    salt = case_salt(what)
    return {COPY_SEEDED_LO: keyed_block(COPY_SEEDED_LO, COPY_SEEDED_LEN, salt),
            RECORD_PTR_10420: SCENE.to_bytes(LONGWORD_BYTES, "big"),
            template: keyed_block(template, RECORD_BYTES, salt ^ 1)}


def _image_long(image, at):
    return int.from_bytes(image[at:at + LONGWORD_BYTES], "big")


@pytest.mark.parametrize("template", [TYPE35_TEMPLATE, TABLE_DEFAULT + 15 * RECORD_BYTES],
                         ids=["shipped", "seeded"])
def test_the_copy_is_eight_longwords_and_the_first_is_the_SCENES(template):
    """The plate said "20(record_ptr) and four following longwords"; it is SEVEN following, and the
    `lea 4(a1),a1` between them means the template's own first longword is never read. Both halves
    are asserted: the destination's x,y is the scene descriptor's, and its remaining 28 bytes are the
    template's bytes 4..31.

    The `shipped` row runs it on the real WB_ACTOR_TYPE35_TEMPLATE, which is what
    player_pending_event_gate hands it; the `seeded` row proves the routine reads a1 rather than that
    address."""
    what = f"scene_copy_record_fields template={template:#x}"
    pokes = _copy_pokes(what, template)
    image = harness.make_image(pokes)

    expected = {}
    _put_long(expected, DESTINATION, _image_long(image, SCENE + SCENE_SPAWN_POSITION))
    for i in range(TEMPLATE_LONGWORDS):
        _put_long(expected, DESTINATION + (i + 1) * LONGWORD_BYTES,
                  _image_long(image, template + SPAWN_TEMPLATE_UNREAD + i * LONGWORD_BYTES))

    info = leaf.run("scene_copy_record_fields", _COPY_RECORD(template, DESTINATION),
                    merge_bands(expected), what,
                    regs={"a1": template, "a2": DESTINATION, "_pokes": pokes},
                    max_insns=_cap("scene_copy_record_fields"))
    _assert_writes(info, expected, what)


def test_the_template_the_gate_hands_it_carries_the_slot_number_of_the_event_actor():
    """WHY THE FIRST LONGWORD IS UNREAD, from the shipped bytes: WB_ACTOR_TYPE35_TEMPLATE's first four
    bytes are where the record's x and y would be, and the scene's position takes their place. What
    the template really supplies begins at +4 with the TYPE word, which is the only shipped datum in
    the image that names a behaviour slot by number."""
    at = TYPE35_TEMPLATE + SPAWN_TEMPLATE_UNREAD
    assert int.from_bytes(harness.BASE_IMAGE[at:at + WORD_BYTES], "big") == 35, (
        "the template's type word is not slot 35's")


def _put_long(expected, addr, value):
    for index in range(LONGWORD_BYTES):
        expected[addr + index] = (value >> (8 * (LONGWORD_BYTES - 1 - index))) & 0xff
