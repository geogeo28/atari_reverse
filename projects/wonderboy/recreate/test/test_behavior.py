"""Differential test for src/behavior.c — the per-actor behaviour tier's foundation.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and bounds (or states exactly) the original's write set.

FOUR THINGS SHAPE THIS BATTERY.

  * THE PASS AND THE DISPATCHER WRITE NOTHING. `actor_behavior_pass` walks a table through a0 and
    `actor_dispatch_behavior` computes an address and jumps; between them they touch no image byte,
    so a byte-for-byte diff proves nothing about either. What pins them is the BOUNDARY: 59 of the
    62 table slots are unported, so the C returns the address it would have transferred to and the
    oracle is stopped at that same address with a coverage witness that the `jmp (a1)` really fired.
    One case per slot pins the C's table entry by entry against ../names.txt AND against the image's
    own 62 longwords.
  * THE TWO SLOTS THAT ARE PORTED MAKE THE WALK RUNNABLE. Slots 0 and 58 hold the bare `rts` at
    $a36, so a table of type-0 records runs the whole pass to its own `rts` in both cores — which is
    the only way the free-marker skip, the end marker and the WB_STATE_FLAG_A34 arm can be driven.
  * NOTHING IS SEEDED FROM A CONSTANT THE CODE ALSO USES. All three actor tables are zero in a fresh
    image, so every case fills them ADDRESS-KEYED with a record's margin either side: a walk that ran
    one record long or took the wrong stride lands on bytes that are wrong FOR WHERE THEY WERE
    WRITTEN rather than on zeros. The type word of every record a case walks is then poked
    explicitly, because a keyed byte would dispatch a slot the case did not choose.
  * SIX LEAVES CALL THE MAP PROBES, whose own write set test_map.py owns. Those cases BOUND the
    write set to the record and the probe's own band rather than stating it.

KNOWINGLY NOT PINNED
  * THE REGISTERS EVERY ROUTINE LEAVES BEHIND, except the three its callers read — $5c6e's d0,
    $23b6's d7 and $6d5a's a1. `clr.w d0` at $5c6e clears only the LOW WORD, so the caller's high
    half comes back in the result register; the reconstruction returns the low word alone and
    nothing in the image reads the other.
  * THE REFUSED DISPATCH. A type whose scaled offset leaves the table makes the original `jmp`
    through arbitrary data, which no differential can drive. The enumeration case below states the
    refusal set exactly instead — all 65,536 type values, against the C alone.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, addi_w_dn, addq_b_d16, andi_w_dn, branch_w_to,
                  brief_extension_word, bsr_w, btst_imm_dn, case_salt, clr_b_d16, clr_w_abs_l,
                  clr_w_dn, cmp_w_dn_dn, cmp_w_imm_dn, cmpi_w_d16, keyed_block, lea_abs_l, lea_d16,
                  lea_indexed, longword, lsl_w_imm_dn, merge_bands, move_b_d16_dn, move_b_imm_d16,
                  move_w_dn_dn, move_w_imm_abs_l, move_w_imm_dn, move_w_ind_dn, moveq_0_dn, opcode,
                  program_writes, s16, sub_w_dn_d16, sub_w_dn_dn, subi_w_dn, tst_b_d16, tst_w_abs_l,
                  tst_w_abs_w, tst_w_dn, word)
from layout import wb

# The record's own geometry and the register numbers come from the battery that owns the actor
# table — a second copy of "what a record looks like" could disagree with src/actor.c while both
# stayed green. Same rule test_scene.py follows for test_stage.py's window model.
from test_actor import (A0, A1, A2, BCLR_IMM, BEQ_W, BGT_W, BLT_W, BMI_W, BNE_W,   # noqa: E402
                        BPL_W, BRA_W, BSET_IMM, BTST_IMM, D0, D1, D2, D7,
                        TABLE_A32, bit_op_d16, cmpi_w_ind, move_w_imm_ind)

BLE_W = 0x6f00
BCHG_IMM = 0x0840
D3, D4, D5, D6 = 3, 4, 5, 6

# --- the globals and the geometry, from the headers both languages read ---------------------------
TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
RECORD_BYTES = wb("ACTOR_RECORD_BYTES")
RECORD_COUNT = wb("ACTOR_SCREEN_RECORD_COUNT")
FREE_MARKER = wb("ACTOR_FREE_MARKER")
TABLE_END = wb("ACTOR_TABLE_END")
FLAG_A32 = wb("STATE_FLAG_A32")
FLAG_A34 = wb("STATE_FLAG_A34")
FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
FOLLOWED_A32 = wb("ACTOR_FOLLOWED_A32")
FOLLOWED_SLOT = wb("ACTOR_FOLLOWED_SLOT")

ACTOR_X = wb("ACTOR_X")
ACTOR_Y = wb("ACTOR_Y")
ACTOR_TYPE = wb("ACTOR_TYPE")
ACTOR_SPRITE = wb("ACTOR_SPRITE")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
FLAGS2 = wb("ACTOR_FLAGS2")
SPEED = wb("ACTOR_SPEED")
FIELD_18 = wb("ACTOR_FIELD_18")
FIELD_22 = wb("ACTOR_FIELD_22")
FIELD_30 = wb("ACTOR_FIELD_30")
HALF_WIDTH = wb("ACTOR_HALF_WIDTH")
SIZE_SECOND = wb("ACTOR_SIZE_SECOND")

MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
SIDE_BIT = wb("ACTOR_FLAG_SIDE_BIT")
FALLING_BIT = wb("ACTOR_FLAG_FALLING_BIT")
CARRIED_BIT = wb("ACTOR_FLAG_CARRIED_BIT")
SPAWNED_BIT = wb("ACTOR_FLAGS2_SPAWNED_BIT")
LANDED_BIT = wb("ACTOR_FLAGS2_LANDED_BIT")
INVULNERABLE_BIT = wb("ACTOR_FLAGS2_INVULNERABLE_BIT")
STEP_BLOCKED = wb("ACTOR_STEP_BLOCKED")

# ...and the behaviour tier's own
BEHAVIOR_TABLE = wb("ACTOR_BEHAVIOR_TABLE")
BEHAVIOR_SLOTS = wb("ACTOR_BEHAVIOR_SLOTS")
BEHAVIOR_ENTRY = wb("ACTOR_BEHAVIOR_ENTRY")
BEHAVIOR_NULL = wb("ACTOR_BEHAVIOR_NULL")
FIXED_SKIP = wb("ACTOR_BEHAVIOR_FIXED_SKIP")
WALK_BUS_CYCLE = wb("ACTOR_WALK_BUS_CYCLE")
BUS_ADDR_MASK = wb("BUS_ADDR_MASK")
DISPATCH_RAN = wb("ACTOR_DISPATCH_RAN")
DISPATCH_REFUSED = wb("ACTOR_DISPATCH_REFUSED")
DISPATCH_UNBOUNDED = wb("ACTOR_DISPATCH_UNBOUNDED")

SPAWN_ANIM_FRAMES = wb("ACTOR_SPAWN_ANIM_FRAMES")
SPAWN_ANIM_MASK = wb("ACTOR_SPAWN_ANIM_MASK")
ANIM_FRAME_BYTES = wb("ACTOR_ANIM_FRAME_BYTES")
ANIM_LIST_ENTRY = wb("ACTOR_ANIM_LIST_ENTRY")
ANIM16_MASK = wb("ACTOR_ANIM16_MASK")
ANIM_5160_FRAMES = wb("ACTOR_ANIM_5160_FRAMES")
ANIM_5160_END = wb("ACTOR_ANIM_5160_END")
ANIM_5160_HOLD = wb("ACTOR_ANIM_5160_HOLD")
TIMER30_RELOAD = wb("ACTOR_TIMER30_RELOAD")
TIMER30_SPEED = wb("ACTOR_TIMER30_SPEED")
TIMER30_RNG_BIT = wb("ACTOR_TIMER30_RNG_BIT")
STEP_AWAY_PIXELS = wb("ACTOR_STEP_AWAY_PIXELS")
SPRITE_SUPPORTED = wb("ACTOR_SPRITE_SUPPORTED")
SPRITE_MOVING = wb("ACTOR_SPRITE_MOVING")
SPRITE_IDLE = wb("ACTOR_SPRITE_IDLE")
SPRITE_TABLE_6ED8 = wb("ACTOR_SPRITE_TABLE_6ED8")
SPRITE_6ED8_STRIDE = wb("ACTOR_SPRITE_6ED8_STRIDE")
FIELD_22_HOLD = wb("ACTOR_FIELD_22_HOLD")
PLATFORM_RIDDEN = wb("ACTOR_PLATFORM_RIDDEN")
PLATFORM_TOP = wb("ACTOR_PLATFORM_TOP")
PLATFORM_CATCH = wb("ACTOR_PLATFORM_CATCH")
BAND_LEFT = wb("ACTOR_BAND_LEFT")
BAND_WIDTH = wb("ACTOR_BAND_WIDTH")
RIDING_BIT = wb("ACTOR_FIELD_22_RIDING_BIT")

STRIKE_BIT = wb("ACTOR_OVERLAP_STRIKE_BIT")
BODY_BIT = wb("ACTOR_OVERLAP_BODY_BIT")
POINT_BIT = wb("ACTOR_OVERLAP_POINT_BIT")
STRIKE_LO = wb("FOLLOWED_SPRITE_STRIKE_LO")
STRIKE_HI = wb("FOLLOWED_SPRITE_STRIKE_HI")
STRIKE_FLIP = wb("FOLLOWED_SPRITE_STRIKE_FLIP")
STRIKE_BOX_NEAR = wb("ACTOR_STRIKE_BOX_NEAR")
STRIKE_BOX_FAR = wb("ACTOR_STRIKE_BOX_FAR")
STRIKE_BOX_FLIP = wb("ACTOR_STRIKE_BOX_FLIP")
STRIKE_BOX_TOP = wb("ACTOR_STRIKE_BOX_TOP")
STRIKE_BOX_DEPTH = wb("ACTOR_STRIKE_BOX_DEPTH")
POINT_LO = wb("FOLLOWED_SPRITE_POINT_LO")
POINT_HI = wb("FOLLOWED_SPRITE_POINT_HI")
POINT_RIGHT = wb("ACTOR_POINT_RIGHT")
POINT_FLIP = wb("ACTOR_POINT_FLIP")
POINT_UP = wb("ACTOR_POINT_UP")

FLASH_TIMER = wb("FLASH_TIMER")
FLASH_REACH = wb("ACTOR_FLASH_REACH")
SHOT_TYPE_LO = wb("ACTOR_SHOT_TYPE_LO")
SHOT_TYPE_HI = wb("ACTOR_SHOT_TYPE_HI")
SHOT_TYPE_KEPT = wb("ACTOR_SHOT_TYPE_KEPT")
SHOT_HIT_MARK = wb("ACTOR_SHOT_HIT_MARK")
ACTOR_HIT = wb("ACTOR_HIT")
ACTOR_NOT_HIT = wb("ACTOR_NOT_HIT")
ALLOC_HIGH_FIRST = wb("ACTOR_ALLOC_HIGH_FIRST")
ALLOC_HIGH_SLOTS = wb("ACTOR_ALLOC_HIGH_SLOTS")

TABLE_BYTES = RECORD_COUNT * RECORD_BYTES

# The three tables back to back, with a record's margin either side, so a walk that overran one
# lands inside the next (or in the margin) rather than on the image's own zeros.
TABLES_LO = TABLE_DEFAULT - RECORD_BYTES
TABLES_HI = TABLE_A32 + TABLE_BYTES + RECORD_BYTES

# A record that is neither free nor the terminator, for the slots a walk case wants stepped over
# without dispatching anything interesting. It is not FREE_MARKER and not $ffff.
OCCUPIED_X = 0x1234

# ...and a type whose slot this port does NOT have, for the records a walk must step over rather
# than dispatch. Slot 1 is the player's, the largest subtree behind the table.
UNPORTED_TYPE = 1


# --- the encodings only this battery spells -------------------------------------------------------
# FIVE of these are now a THIRD copy and are due to move to leaf.py under its own rule ("an encoding
# moves there on its third"): `move_w_dn_d16` (test_actor.py, test_map.py), `movea_l_ind`
# (test_blit.py, test_scene.py), `addq_w_dn` (test_blit.py, test_map.py), `add_w_d16_dn`
# (test_blit.py, test_map.py) and `neg_w_dn` (test_map.py, test_scroll.py). Hoisting them edits four
# other batteries, so ../STATUS.md registers the move rather than this batch making it; each is
# annotated ALSO IN below so the copies can be found from any of them. The rest are first or second
# copies, which the rule allows.
def move_w_ind_d16(source, destination, displacement):
    """`move.w (As),d16(Ad)` — how an animation stepper publishes a frame into the record."""
    return opcode(0x3150 | (destination << 9) | source) + word(displacement)


def move_w_postinc_d16(source, destination, displacement):
    """...and the POST-INCREMENT form, which is what makes the terminator the word AFTER the frame."""
    return opcode(0x3158 | (destination << 9) | source) + word(displacement)


def move_w_imm_d16(base, value, displacement):
    return opcode(0x317c | (base << 9)) + word(value) + word(displacement)


def move_w_dn_d16(reg, base, displacement):
    return opcode(0x3140 | (base << 9) | reg) + word(displacement)
    # ALSO IN test_actor.py, test_map.py — third copy, queued for leaf.py.


def move_b_dn_d16(reg, base, displacement):
    return opcode(0x1140 | (base << 9) | reg) + word(displacement)


def move_b_d16_d16(source, source_displacement, destination, destination_displacement):
    """`move.b d16(As),d16(Ad)` — $6872's `move.b 30(a0),11(a0)`, the countdown becoming the speed."""
    return (opcode(0x1168 | (destination << 9) | source)
            + word(source_displacement) + word(destination_displacement))


def movea_l_ind(reg, source):
    return opcode(0x2050 | (reg << 9) | source)
    # ALSO IN test_blit.py, test_scene.py — third copy, queued for leaf.py.


def movea_l_d16(reg, source, displacement):
    return opcode(0x2068 | (reg << 9) | source) + word(displacement)


def lea_indexed_pc(reg, index, displacement):
    """`lea d8(PC,Dn.w),An` — THE instruction PORTABILITY.md §0k is about. Mode 7 reg 3, and the
    displacement counts from the EXTENSION WORD, which is `leaf.BRANCH_EXTENSION`'s rule again."""
    return opcode(0x41fb | (reg << 9)) + brief_extension_word(index, displacement)


def lea_abs_w(reg, addr):
    return opcode(0x41f8 | (reg << 9)) + word(addr)


def jmp_ind(reg):
    return opcode(0x4ed0 | reg)


def cmpi_l_ind(reg, value):
    return opcode(0x0c90 | reg) + longword(value)


def cmpi_b_d16(base, value, displacement):
    return opcode(0x0c28 | base) + word(value & 0xff) + word(displacement)


def subq_b_d16(amount, base, displacement):
    return opcode(0x5128 | ((amount & 7) << 9) | base) + word(displacement)


def addq_w_dn(amount, reg):
    return opcode(0x5040 | ((amount & 7) << 9) | reg)
    # ALSO IN test_blit.py, test_map.py — third copy, queued for leaf.py.


def addi_b_dn(reg, value):
    return opcode(0x0600 | reg) + word(value & 0xff)


def andi_b_dn(reg, value):
    return opcode(0x0200 | reg) + word(value & 0xff)


def tst_b_dn(reg):
    return opcode(0x4a00 | reg)


def tst_w_ind(reg):
    return opcode(0x4a50 | reg)


def clr_b_ind(reg):
    return opcode(0x4210 | reg)


def add_w_dn_ind(reg, base):
    return opcode(0xd150 | (reg << 9) | base)


def sub_w_dn_ind(reg, base):
    return opcode(0x9150 | (reg << 9) | base)


def add_w_dn_d16(reg, base, displacement):
    return opcode(0xd168 | (reg << 9) | base) + word(displacement)


def add_w_d16_dn(reg, base, displacement):
    return opcode(0xd068 | (reg << 9) | base) + word(displacement)
    # ALSO IN test_blit.py, test_map.py — third copy, queued for leaf.py.


def sub_w_d16_dn(reg, base, displacement):
    return opcode(0x9068 | (reg << 9) | base) + word(displacement)


def cmp_w_ind_dn(reg, base):
    return opcode(0xb050 | (reg << 9) | base)


def bset_imm_dn(bit, reg):
    return opcode(0x08c0 | reg) + word(bit)


def neg_w_dn(reg):
    return opcode(0x4440 | reg)
    # ALSO IN test_map.py, test_scroll.py — third copy, queued for leaf.py.


def adda_w_dn(reg, base):
    return opcode(0xd0c0 | (base << 9) | reg)


def dbf_to(reg, target):
    return _Ref(4, lambda at, labels: opcode(leaf.DBF_DN | reg)
                + word(labels[target] - (at + leaf.BRANCH_EXTENSION)))


# --- a two-pass assembler with LABELS -------------------------------------------------------------
# `leaf.assemble` hands each piece its address, which covers a `bsr.w`; a body with fourteen forward
# branches into six shared exits needs the target's address too. Summing the lengths of the pieces a
# branch spans (the `branch_over` idiom) does not scale past two or three arms and gets silently
# wrong when an arm changes — so a branch here names the LABEL it aims at and the offsets come out of
# a first pass. Every piece knows its own length, so one pass is enough to place the labels.
class _Ref:
    """A piece whose bytes depend on where it sits and on where the labels are."""

    def __init__(self, length, build):
        self.length = length
        self.build = build


def _lab(name):
    return ("label", name)


def _bcc(condition, target):
    """`bcc.w`/`bra.w` aimed at a label."""
    return _Ref(4, lambda at, labels: branch_w_to(condition, at, labels[target]))


def _bcc_abs(condition, address):
    """...and at an address outside the body — the tail jumps two of these routines end in."""
    return _Ref(4, lambda at, _labels: branch_w_to(condition, at, address))


def _bra_s(target):
    """`bra.s` aimed at a label: the pass closes its loop short where every other branch is long."""
    def build(at, labels):
        displacement = labels[target] - (at + leaf.BRANCH_EXTENSION)
        assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bra.s` byte"
        return opcode(BRA_W | (displacement & 0xff))

    return _Ref(2, build)


def _bsr(routine):
    return _Ref(4, lambda at, _labels: bsr_w(at, leaf.entry_of(routine)))


def _bsr_s(routine):
    """`bsr.s` — $6840 calls short where $2fce spells the same call long, and the pin says so."""
    def build(at, _labels):
        displacement = leaf.entry_of(routine) - (at + leaf.BRANCH_EXTENSION)
        assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bsr.s` byte"
        return opcode(0x6100 | (displacement & 0xff))

    return _Ref(2, build)


def _place(base, pieces):
    """{label: address} for ``pieces`` laid out from ``base``."""
    labels, at = {}, base
    for piece in pieces:
        if isinstance(piece, tuple):
            assert piece[1] not in labels, f"duplicate label {piece[1]!r}"
            labels[piece[1]] = at
        else:
            at += len(piece) if isinstance(piece, bytes) else piece.length
    return labels


def _asm(base, pieces):
    labels, body, at = _place(base, pieces), b"", base
    for piece in pieces:
        if isinstance(piece, tuple):
            continue
        emitted = piece if isinstance(piece, bytes) else piece.build(at, labels)
        assert isinstance(piece, bytes) or len(emitted) == piece.length
        body += emitted
        at += len(emitted)
    return body


def _instructions(pieces):
    """How many INSTRUCTIONS a piece list holds — labels are not instructions. Every run's cap is
    derived from this rather than stated, which is batch 27's structural fix adopted from the
    start: a cap cannot then drift away from the body it is meant to bound."""
    return sum(1 for piece in pieces if not isinstance(piece, tuple))


# --- the entry pins -------------------------------------------------------------------------------
STEP_LEFT = "actor_step_left_against_map"
STEP_RIGHT = "actor_step_right_against_map"
SIDE_FLAG = "actor_set_side_flag"
FOLLOWED_RECORD = "followed_actor_record"
WITHIN = "actor_followed_x_within"
RNG_NEXT = "rng_next"
DISPATCHER = "actor_dispatch_behavior"


def _pass_pieces():
    """$8d0 — the walk. Its A34 arm ends in a `bra.w` TAIL into the dispatcher rather than a call,
    which is why the last piece names an address instead of a label."""
    return [
        leaf.movea_l_abs_l(A0, TABLE_SELECTED),
        tst_w_abs_l(FLAG_A34),
        _bcc(BNE_W, "fixed"),
        _lab("loop"),
        cmpi_l_ind(A0, TABLE_END),
        _bcc(BEQ_W, "done"),
        cmpi_w_ind(A0, FREE_MARKER),
        _bcc(BNE_W, "live"),
        lea_d16(A0, RECORD_BYTES),
        _bra_s("loop"),
        _lab("live"),
        _bsr(DISPATCHER),
        lea_d16(A0, RECORD_BYTES),
        _bra_s("loop"),
        _lab("done"),
        RTS,
        _lab("fixed"),
        cmpi_w_ind(A0, FREE_MARKER),
        _bcc(BEQ_W, "second"),
        _bsr(DISPATCHER),
        _lab("second"),
        lea_d16(A0, RECORD_BYTES),
        cmpi_w_ind(A0, FREE_MARKER),
        _bcc(BEQ_W, "third"),
        _bsr(DISPATCHER),
        _lab("third"),
        lea_d16(A0, FIXED_SKIP),
        _bcc_abs(BRA_W, leaf.entry_of(DISPATCHER)),
    ]


def _dispatch_pieces():
    """$928 — and the `lea`'s displacement is DERIVED from WB_ACTOR_BEHAVIOR_TABLE minus the
    extension word's own address, which is what says the base really is that table."""
    entry = leaf.entry_of(DISPATCHER)
    extension_at = (entry + len(moveq_0_dn(D1)) + len(move_w_ind_dn(D1, A0, ACTOR_TYPE))
                    + len(lsl_w_imm_dn(2, D1)) + WORD_BYTES)
    return [
        moveq_0_dn(D1),
        move_w_ind_dn(D1, A0, ACTOR_TYPE),
        lsl_w_imm_dn(2, D1),
        lea_indexed_pc(A1, D1, BEHAVIOR_TABLE - extension_at),
        movea_l_ind(A1, A1),
        jmp_ind(A1),
    ]


def _null_pieces():
    return [RTS]


def _spawn_anim_pieces():
    return [
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, SPAWN_ANIM_FRAMES),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, SPAWN_ANIM_MASK),
        _bcc(BEQ_W, "wrap"),
        addq_b_d16(ANIM_FRAME_BYTES, A0, FIELD_18),
        RTS,
        _lab("wrap"),
        bit_op_d16(BCLR_IMM, SPAWNED_BIT, A0, FLAGS2),
        clr_b_d16(A0, FIELD_18),
        RTS,
    ]


def _step_facing_pieces():
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "after"),
        _lab("left"),
        _bsr(STEP_LEFT),
        _lab("after"),
        tst_b_dn(D0),
        _bcc(BNE_W, "out"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("out"),
        RTS,
    ]


def _tick_timer30_pieces():
    return [
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "reload"),
        subq_b_d16(1, A0, FIELD_30),
        RTS,
        _lab("reload"),
        move_b_imm_d16(A0, TIMER30_RELOAD, FIELD_30),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "out"),
        _bsr(RNG_NEXT),
        btst_imm_dn(TIMER30_RNG_BIT, D0),
        _bcc(BNE_W, "out"),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, TIMER30_SPEED, SPEED),
        clr_b_d16(A0, FIELD_18),
        _lab("out"),
        RTS,
    ]


def _face_and_step_pieces(head, set_arm, clear_arm):
    """$2fce and $2fe8 are ONE shape with the two arms EXCHANGED, which is the whole difference
    between them — so they are one pin taken twice rather than two transcriptions."""
    return [
        *head,
        _bsr(SIDE_FLAG),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "set"),
        _bsr(clear_arm),
        RTS,
        _lab("set"),
        _bsr(set_arm),
        RTS,
    ]


def _anim_step_facing_list_pieces():
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "side"),
        movea_l_d16(A1, A1, ANIM_LIST_ENTRY),
        _bcc(BRA_W, "go"),
        _lab("side"),
        movea_l_ind(A1, A1),
        _lab("go"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_postinc_d16(A1, A0, ACTOR_SPRITE),
        tst_w_ind(A1),
        _bcc(BPL_W, "step"),
        clr_b_d16(A0, FIELD_18),
        RTS,
        _lab("step"),
        addq_b_d16(ANIM_FRAME_BYTES, A0, FIELD_18),
        RTS,
    ]


def _select_sprite_pieces():
    return [
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "not-supported"),
        move_w_imm_d16(A0, SPRITE_SUPPORTED, ACTOR_SPRITE),
        _bcc(BRA_W, "out"),
        _lab("not-supported"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "idle"),
        move_w_imm_d16(A0, SPRITE_MOVING, ACTOR_SPRITE),
        _bcc(BRA_W, "out"),
        _lab("idle"),
        move_w_imm_d16(A0, SPRITE_IDLE, ACTOR_SPRITE),
        _lab("out"),
        RTS,
    ]


def _hop_ascend_pieces():
    return [
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "go"),
        RTS,
        _lab("go"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, SPEED),
        sub_w_dn_d16(D0, A0, ACTOR_Y),
        subq_b_d16(1, A0, SPEED),
        _bcc(BNE_W, "out"),
        bit_op_d16(BCLR_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, 1, SPEED),
        _lab("out"),
        RTS,
    ]


def _advance_anim16_pieces():
    return [
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
    ]


def _step_toward_followed_pieces():
    return [
        _bsr_s(FOLLOWED_RECORD),
        move_w_ind_dn(D0, A1),
        move_w_ind_dn(D1, A0),
        cmp_w_dn_dn(D1, D0),
        _bcc(BGT_W, "sub-x"),
        add_w_dn_ind(D7, A0),
        _bcc(BRA_W, "y-axis"),
        _lab("sub-x"),
        sub_w_dn_ind(D7, A0),
        _lab("y-axis"),
        move_w_ind_dn(D0, A1, ACTOR_Y),
        move_w_ind_dn(D1, A0, ACTOR_Y),
        subi_w_dn(D0, PLATFORM_TOP),
        cmp_w_dn_dn(D1, D0),
        _bcc(BGT_W, "sub-y"),
        add_w_dn_d16(D7, A0, ACTOR_Y),
        RTS,
        _lab("sub-y"),
        sub_w_dn_d16(D7, A0, ACTOR_Y),
        RTS,
    ]


def _relaunch_and_anim_5160_pieces():
    return [
        lea_abs_w(A1, ANIM_5160_FRAMES),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "anim"),
        cmpi_b_d16(A0, ANIM_5160_HOLD, FIELD_30),
        _bcc(BEQ_W, "anim"),
        subq_b_d16(1, A0, FIELD_30),
        move_b_d16_d16(A0, FIELD_30, A0, SPEED),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        _lab("anim"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_postinc_d16(A1, A0, ACTOR_SPRITE),
        addq_b_d16(ANIM_FRAME_BYTES, A0, FIELD_18),
        cmpi_w_ind(A1, ANIM_5160_END),
        _bcc(BNE_W, "out"),
        clr_b_d16(A0, FIELD_18),
        _lab("out"),
        RTS,
    ]


def _sprite_from_6ed8_pieces():
    return [
        move_w_ind_dn(D0, A0, HALF_WIDTH),
        lsl_w_imm_dn(3, D0),
        lea_abs_l(A2, SPRITE_TABLE_6ED8),
        adda_w_dn(D0, A2),
        move_w_ind_d16(A2, A0, ACTOR_SPRITE),
        _bcc_abs(BRA_W, leaf.entry_of(FOLLOWED_RECORD)),
    ]


def _platform_carry_pieces():
    return [
        move_w_ind_dn(D0, A1, ACTOR_Y),
        move_w_ind_dn(D1, A0, ACTOR_Y),
        subi_w_dn(D1, PLATFORM_TOP),
        sub_w_dn_dn(D0, D1),
        _bcc(BMI_W, "out"),
        cmp_w_imm_dn(D0, PLATFORM_CATCH),
        _bcc(BGT_W, "out"),
        move_w_ind_dn(D0, A0),
        sub_w_d16_dn(D0, A2, BAND_LEFT),
        move_w_ind_dn(D2, A1),
        cmp_w_dn_dn(D2, D0),
        _bcc(BLT_W, "out"),
        add_w_d16_dn(D0, A2, BAND_WIDTH),
        cmp_w_dn_dn(D2, D0),
        _bcc(BGT_W, "out"),
        move_w_imm_abs_l(1, PLATFORM_RIDDEN),
        bit_op_d16(BSET_IMM, RIDING_BIT, A0, FIELD_22),
        move_w_dn_d16(D1, A1, ACTOR_Y),
        bit_op_d16(BSET_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, FALLING_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, MOVING_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, LAUNCHED_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, CARRIED_BIT, A1, ACTOR_FLAGS),
        clr_b_d16(A1, SPEED),
        _lab("out"),
        RTS,
    ]


def _platform_release_pieces():
    return [
        move_w_ind_dn(D0, A0),
        sub_w_d16_dn(D0, A2, BAND_LEFT),
        move_w_ind_dn(D2, A1),
        cmp_w_dn_dn(D2, D0),
        _bcc(BLT_W, "release"),
        add_w_d16_dn(D0, A2, BAND_WIDTH),
        cmp_w_dn_dn(D2, D0),
        _bcc(BGT_W, "release"),
        bit_op_d16(BTST_IMM, LANDED_BIT, A1, FLAGS2),
        _bcc(BNE_W, "release"),
        bit_op_d16(BTST_IMM, INVULNERABLE_BIT, A1, FLAGS2),
        _bcc(BNE_W, "release"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A1, ACTOR_FLAGS),
        _bcc(BEQ_W, "out"),
        _lab("release"),
        bit_op_d16(BCLR_IMM, RIDING_BIT, A0, FIELD_22),
        clr_w_abs_l(PLATFORM_RIDDEN),
        _lab("out"),
        RTS,
    ]


def _face_followed_reset_22_pieces():
    return [
        _bsr(FOLLOWED_RECORD),
        bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_w_ind_dn(D0, A1),
        cmp_w_ind_dn(D0, A0),
        _bcc(BGT_W, "keep"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("keep"),
        tst_b_d16(A0, FIELD_22),
        _bcc(BEQ_W, "out"),
        move_b_imm_d16(A0, FIELD_22_HOLD, FIELD_22),
        _lab("out"),
        RTS,
    ]


def _overlap_mask_pieces():
    """$5c6e — the biggest pin here. Its three blocks fall through into one another and every arm
    exits to the NEXT block's label, which is what the labels make legible."""
    return [
        clr_w_dn(D0),
        move_w_ind_dn(D1, A0),
        move_w_dn_dn(D3, D1),
        move_w_ind_dn(D2, A0, ACTOR_Y),
        move_w_dn_dn(D4, D2),
        sub_w_d16_dn(D2, A0, SIZE_SECOND),
        sub_w_d16_dn(D1, A0, HALF_WIDTH),
        add_w_d16_dn(D3, A0, HALF_WIDTH),
        lea_abs_l(A1, FOLLOWED_DEFAULT),
        tst_w_abs_w(FLAG_A32),
        _bcc(BEQ_W, "selected"),
        lea_abs_l(A1, FOLLOWED_A32),
        _lab("selected"),
        move_w_ind_dn(D7, A1, ACTOR_SPRITE),
        cmp_w_imm_dn(D7, STRIKE_LO),
        _bcc(BLT_W, "body"),
        cmp_w_imm_dn(D7, STRIKE_HI),
        _bcc(BGT_W, "body"),
        move_w_ind_dn(D5, A1, ACTOR_Y),
        subi_w_dn(D5, STRIKE_BOX_TOP),
        cmp_w_dn_dn(D4, D5),
        _bcc(BLT_W, "body"),
        addq_w_dn(STRIKE_BOX_DEPTH, D5),
        cmp_w_dn_dn(D2, D5),
        _bcc(BGT_W, "body"),
        move_w_ind_dn(D5, A1),
        move_w_dn_dn(D6, D5),
        addq_w_dn(STRIKE_BOX_NEAR, D5),
        addi_w_dn(D6, STRIKE_BOX_FAR),
        cmp_w_imm_dn(D7, STRIKE_FLIP),
        _bcc(BLE_W, "no-flip"),
        subi_w_dn(D5, STRIKE_BOX_FLIP),
        subi_w_dn(D6, STRIKE_BOX_FLIP),
        _lab("no-flip"),
        cmp_w_dn_dn(D3, D5),
        _bcc(BLT_W, "body"),
        cmp_w_dn_dn(D1, D6),
        _bcc(BGT_W, "body"),
        bset_imm_dn(STRIKE_BIT, D0),
        _lab("body"),
        move_w_ind_dn(D5, A1),
        move_w_ind_dn(D6, A1, ACTOR_Y),
        sub_w_d16_dn(D5, A1, HALF_WIDTH),
        sub_w_d16_dn(D6, A1, SIZE_SECOND),
        cmp_w_dn_dn(D5, D3),
        _bcc(BGT_W, "point"),
        cmp_w_dn_dn(D6, D4),
        _bcc(BGT_W, "point"),
        move_w_ind_dn(D5, A1),
        move_w_ind_dn(D6, A1, ACTOR_Y),
        add_w_d16_dn(D5, A1, HALF_WIDTH),
        cmp_w_dn_dn(D5, D1),
        _bcc(BLT_W, "point"),
        cmp_w_dn_dn(D6, D2),
        _bcc(BLT_W, "point"),
        bset_imm_dn(BODY_BIT, D0),
        _lab("point"),
        move_w_ind_dn(D5, A1),
        addi_w_dn(D5, POINT_RIGHT),
        cmp_w_imm_dn(D7, POINT_LO),
        _bcc(BEQ_W, "point-y"),
        cmp_w_imm_dn(D7, POINT_HI),
        _bcc(BNE_W, "out"),
        subi_w_dn(D5, POINT_FLIP),
        _lab("point-y"),
        move_w_ind_dn(D6, A1, ACTOR_Y),
        subi_w_dn(D6, POINT_UP),
        cmp_w_dn_dn(D5, D1),
        _bcc(BLT_W, "out"),
        cmp_w_dn_dn(D5, D3),
        _bcc(BGT_W, "out"),
        cmp_w_dn_dn(D6, D2),
        _bcc(BLT_W, "out"),
        cmp_w_dn_dn(D6, D4),
        _bcc(BGT_W, "out"),
        bset_imm_dn(POINT_BIT, D0),
        _lab("out"),
        RTS,
    ]


def _hit_by_shot_pieces():
    """$23b6 — the `dbf` loop, and the `clr.w d7` at its foot that is a deliberate no-op."""
    return [
        moveq_0_dn(D7),
        tst_w_abs_w(FLASH_TIMER),
        _bcc(BEQ_W, "scan"),
        move_w_imm_dn(D0, FLASH_REACH),
        _bsr(WITHIN),
        tst_w_dn(D0),
        _bcc(BMI_W, "scan"),
        move_w_imm_dn(D7, ACTOR_HIT),
        RTS,
        _lab("scan"),
        leaf.movea_l_abs_l(A1, TABLE_SELECTED),
        lea_d16(A1, ALLOC_HIGH_FIRST * RECORD_BYTES),
        move_w_imm_dn(D6, ALLOC_HIGH_SLOTS - 1),
        _lab("loop"),
        cmpi_w_ind(A1, FREE_MARKER),
        _bcc(BEQ_W, "next"),
        cmpi_w_d16(A1, SHOT_TYPE_HI, ACTOR_TYPE),
        _bcc(BGT_W, "next"),
        cmpi_w_d16(A1, SHOT_TYPE_LO, ACTOR_TYPE),
        _bcc(BLT_W, "next"),
        move_w_ind_dn(D0, A0, HALF_WIDTH),
        move_w_ind_dn(D1, A1, HALF_WIDTH),
        leaf.add_w_dn_dn(D1, D0),
        move_w_ind_dn(D2, A0),
        move_w_ind_dn(D3, A1),
        sub_w_dn_dn(D3, D2),
        _bcc(BPL_W, "x-abs"),
        neg_w_dn(D3),
        _lab("x-abs"),
        cmp_w_dn_dn(D3, D1),
        _bcc(BGT_W, "next"),
        move_w_ind_dn(D0, A0, SIZE_SECOND),
        move_w_ind_dn(D1, A1, SIZE_SECOND),
        leaf.add_w_dn_dn(D1, D0),
        move_w_ind_dn(D2, A0, ACTOR_Y),
        move_w_ind_dn(D3, A1, ACTOR_Y),
        sub_w_dn_dn(D3, D2),
        _bcc(BPL_W, "y-abs"),
        neg_w_dn(D3),
        _lab("y-abs"),
        cmp_w_dn_dn(D3, D1),
        _bcc(BGT_W, "next"),
        move_w_imm_dn(D7, ACTOR_HIT),
        cmpi_w_d16(A1, SHOT_TYPE_KEPT, ACTOR_TYPE),
        _bcc(BEQ_W, "mark"),
        move_w_imm_ind(A1, FREE_MARKER),
        RTS,
        _lab("mark"),
        move_b_imm_d16(A1, SHOT_HIT_MARK, FIELD_30),
        RTS,
        _lab("next"),
        lea_d16(A1, RECORD_BYTES),
        dbf_to(D6, "loop"),
        clr_w_dn(D7),
        RTS,
    ]


ENTRY_PIECES = {
    "actor_behavior_pass": _pass_pieces(),
    "actor_dispatch_behavior": _dispatch_pieces(),
    "actor_behavior_null": _null_pieces(),
    "actor_spawn_anim_step": _spawn_anim_pieces(),
    "actor_step_facing": _step_facing_pieces(),
    "actor_tick_timer30": _tick_timer30_pieces(),
    "actor_face_and_step_toward": _face_and_step_pieces([], STEP_LEFT, STEP_RIGHT),
    "actor_face_and_step_away4": _face_and_step_pieces([move_w_imm_dn(D7, STEP_AWAY_PIXELS)],
                                                       STEP_RIGHT, STEP_LEFT),
    "actor_anim_step_facing_list": _anim_step_facing_list_pieces(),
    "actor_select_sprite_by_flag": _select_sprite_pieces(),
    "actor_hop_ascend_step": _hop_ascend_pieces(),
    "actor_advance_anim16": _advance_anim16_pieces(),
    "actor_followed_overlap_mask": _overlap_mask_pieces(),
    "actor_step_toward_followed": _step_toward_followed_pieces(),
    "actor_relaunch_and_anim_5160": _relaunch_and_anim_5160_pieces(),
    "actor_sprite_from_6ed8": _sprite_from_6ed8_pieces(),
    "actor_platform_carry_followed": _platform_carry_pieces(),
    "actor_platform_release_check": _platform_release_pieces(),
    "actor_face_followed_reset_22": _face_followed_reset_22_pieces(),
    "actor_hit_by_player_shot": _hit_by_shot_pieces(),
}
RECONSTRUCTED_ROUTINES = 20

ENTRY_BYTES = {name: _asm(leaf.entry_of(name), pieces) for name, pieces in ENTRY_PIECES.items()}
INSN_COUNT = {name: _instructions(pieces) for name, pieces in ENTRY_PIECES.items()}


def _cap(name, extra=0):
    """A run's instruction cap, DERIVED from the pin: every instruction of the body once, plus the
    runner's sentinel, plus whatever a callee or a loop adds. Nothing here states a round number."""
    return INSN_COUNT[name] + leaf.RUNNER_SENTINEL_INSN + extra


# The callees these routines reach, as instruction counts, so a cap that includes one says which.
# The two map probes and the PRNG are the only ones; their bodies are test_map.py's and
# test_rng.py's, and the numbers here are upper bounds on what one call executes.
MAP_PROBE_INSNS = 200
RNG_INSNS = 40
FOLLOWED_INSNS = 8
SIDE_FLAG_INSNS = FOLLOWED_INSNS + 6
WITHIN_INSNS = FOLLOWED_INSNS + 12


# --- the entry pins, as cases ---------------------------------------------------------------------
def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


# The extents, so a pin that stopped one instruction short fails here rather than leaving the tail
# unpinned. Each is bounded by the next routine's own entry or by the data that follows it — the
# behaviour tier has no Ghidra function table of its own until batch 28's names landed.
BODY_SIZES = {
    "actor_behavior_pass": 88,          # $8d0..$927, bounded by the dispatcher's entry
    "actor_dispatch_behavior": 16,      # ...which ends exactly where the table begins
    "actor_behavior_null": 2,           # the `rts` the table's slots 0 and 58 hold
    "actor_spawn_anim_step": 50,        # $698a..$69bb, then a $0000 pad and the frame table
    "actor_step_facing": 36,
    "actor_tick_timer30": 72,
    "actor_face_and_step_toward": 26,
    "actor_face_and_step_away4": 30,
    "actor_anim_step_facing_list": 52,
    "actor_select_sprite_by_flag": 48,
    "actor_hop_ascend_step": 44,
    "actor_advance_anim16": 18,         # then the word DATA at $5a4e
    "actor_followed_overlap_mask": 244,  # $5c6e..$5d61, ending where rad_depack begins
    "actor_step_toward_followed": 50,
    "actor_relaunch_and_anim_5160": 84,
    "actor_sprite_from_6ed8": 22,       # 22 including its `bra.w` tail into $67e0
    "actor_platform_carry_followed": 104,
    "actor_platform_release_check": 68,
    "actor_face_followed_reset_22": 40,
    "actor_hit_by_player_shot": 172,    # $23b6..$2461, bounded by slot 2's own entry
}


@pytest.mark.parametrize("name", sorted(BODY_SIZES), ids=sorted(BODY_SIZES))
def test_the_reconstructed_body_is_the_whole_routine(name):
    assert len(ENTRY_BYTES[name]) == BODY_SIZES[name], (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {BODY_SIZES[name]} recorded")


def test_the_two_step_routines_are_one_shape_with_the_arms_exchanged():
    """The plate correction this batch makes, as a CHECKED property: $2fe8 is NOT $2fce with a
    different d7.

    Both shapes are assembled at ONE address — the two really sit 26 bytes apart, so every `bsr.w`
    displacement would differ otherwise and say nothing — and what is left differing is exactly the
    two arm calls' displacement WORDS: each arm aims at the callee the other's arm has.
    """
    base = leaf.entry_of("actor_face_and_step_toward")
    toward = _asm(base, _face_and_step_pieces([], STEP_LEFT, STEP_RIGHT))
    away = _asm(base, _face_and_step_pieces([], STEP_RIGHT, STEP_LEFT))
    assert len(toward) == len(away)

    differing = [at for at in range(len(toward)) if toward[at] != away[at]]
    assert len(differing) == 4, f"the two shapes differ in {len(differing)} bytes, not 4"
    assert differing[1] - differing[0] == 1 and differing[3] - differing[2] == 1, (
        "the differing bytes are not two whole displacement words")
    # ...and the two calls really are the two probes, in the two orders.
    assert differing[2] - differing[1] == len(RTS) + len(opcode(0)) + 1


# --- the table, pinned entry by entry --------------------------------------------------------------
# ../names.txt names every slot for the STRUCTURE it has — `actor_behavior_typeNN` is slot NN — so
# the regular rows are generated from the slot number and only the four that are not are spelt out.
# The pin is then "the image's Nth longword is the address the name map gives that name", which is
# what makes a table row that moved fail on the address rather than on a comment.
TABLE_TARGETS = {0: "actor_behavior_null", 1: "actor_behavior_type01_player",
                 38: "actor_behavior_type38_pickup", 58: "actor_behavior_null"}
for _slot in range(BEHAVIOR_SLOTS):
    TABLE_TARGETS.setdefault(_slot, f"actor_behavior_type{_slot:02d}")

# The two slots this port HAS a reconstruction for; every other slot is the boundary.
PORTED_SLOTS = tuple(slot for slot, name in sorted(TABLE_TARGETS.items())
                     if name == "actor_behavior_null")


def _image_slot(slot):
    at = BEHAVIOR_TABLE + slot * BEHAVIOR_ENTRY
    return int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")


@pytest.mark.parametrize("slot", range(BEHAVIOR_SLOTS), ids=lambda v: f"slot{v:02d}")
def test_the_image_table_holds_the_address_names_txt_names(slot):
    expected = leaf.entry_of(TABLE_TARGETS[slot])
    assert _image_slot(slot) == expected, (
        f"slot {slot} of the table at {BEHAVIOR_TABLE:#x} holds {_image_slot(slot):#x}, not "
        f"{TABLE_TARGETS[slot]}'s {expected:#x}")


def test_the_two_null_slots_are_the_one_address_and_the_rest_are_distinct():
    """61 distinct targets across 62 slots, which is the whole of what makes slot 58 interesting."""
    targets = [_image_slot(slot) for slot in range(BEHAVIOR_SLOTS)]
    assert len(set(targets)) == BEHAVIOR_SLOTS - 1
    assert [slot for slot, target in enumerate(targets) if target == BEHAVIOR_NULL] \
        == list(PORTED_SLOTS)


def test_the_table_is_bounded_by_its_own_first_target():
    """What says the table is 62 entries and not 63: slot 0's target is the `rts` at $a36, and
    between the last longword and it sit exactly the three state-flag words."""
    state_flags = 3
    assert BEHAVIOR_NULL == (BEHAVIOR_TABLE + BEHAVIOR_SLOTS * BEHAVIOR_ENTRY
                             + state_flags * WORD_BYTES)


def test_no_table_entry_can_be_mistaken_for_a_dispatch_CODE():
    """src/behavior.c returns an ADDRESS for an unported slot and WB_ACTOR_DISPATCH_RAN/_REFUSED
    otherwise, so the two codes must be values no slot holds — checked against the image rather
    than assumed."""
    targets = {_image_slot(slot) for slot in range(BEHAVIOR_SLOTS)}
    assert DISPATCH_RAN not in targets and DISPATCH_REFUSED not in targets


def test_the_runaway_walk_has_a_code_of_its_own_and_no_seed_can_reach_it():
    """WB_ACTOR_DISPATCH_UNBOUNDED is a BACKSTOP, and this case is the measurement that says so
    rather than a pin.

    To reach it a walk must dispatch WB_ACTOR_WALK_BUS_CYCLE records without one refusing — and the
    cursor's stride sweeps the WHOLE 24-bit bus, so it necessarily passes through the program image,
    where the words at record offset 4 are ordinary instruction bytes and one of them scales to an
    offset outside the table. Every seed therefore ends in a refusal or a boundary first: the code
    exists so that a runaway would be REPORTABLE, not because a case can produce one. What is
    checkable is that it could not be confused with anything else if it did fire, and that is what
    this asserts. ../STATUS.md carries it in the not-pinned list.
    """
    codes = (DISPATCH_RAN, DISPATCH_REFUSED, DISPATCH_UNBOUNDED)
    assert len(set(codes)) == len(codes), "two of the three dispatch codes are the same value"
    targets = {_image_slot(slot) for slot in range(BEHAVIOR_SLOTS)}
    assert not targets & set(codes), "a table entry collides with a dispatch code"


def test_the_reconstructed_target_is_matched_by_ADDRESS_not_by_slot():
    """The dispatcher FETCHES the longword (`movea.l (a1),a1`), so which reconstruction stands in is
    a property of the ADDRESS it fetched and not of the slot it fetched it from. Poking slot 0's
    longword to an unported handler is what separates the two readings: the original jumps there,
    and a port that had memorised "slot 0 is the null handler" would run nothing and report that it
    had."""
    slot, target_slot = 0, 2
    actor = _record(TABLE_DEFAULT, 3)
    target = leaf.entry_of(TABLE_TARGETS[target_slot])
    what = "actor_dispatch_behavior through a poked table entry"
    pokes = _tier_pokes(case_salt(what), {
        actor + ACTOR_TYPE: word(slot),
        BEHAVIOR_TABLE + slot * BEHAVIOR_ENTRY: longword(target)})

    info = leaf.run_reaching(DISPATCHER, _DISPATCH(actor), [], what, DISPATCH_JMP_PC,
                             regs={"a0": actor, "_pokes": pokes}, stop_pc=target,
                             max_insns=_cap(DISPATCHER))
    assert info["ret"] == target, (
        f"{what}: the reconstruction reported {info['ret']:#x} — it read the slot, not the table")


def test_the_walk_cap_is_the_bus_cycle_the_stride_divides():
    """WB_ACTOR_WALK_BUS_CYCLE is the one number in src/behavior.c the original does not have, and
    this is the derivation it claims: every 32-byte-aligned position the 24-bit bus has."""
    assert WALK_BUS_CYCLE * RECORD_BYTES == BUS_ADDR_MASK + 1


# --- glue -----------------------------------------------------------------------------------------
_PASS = leaf.image_glue("actor_behavior_pass", ctypes.c_uint32)
_DISPATCH = leaf.register_glue("actor_dispatch_behavior", [ctypes.c_uint32], ctypes.c_uint32)
_SPAWN_ANIM = leaf.register_glue("actor_spawn_anim_step", [ctypes.c_uint32])
_STEP_FACING = leaf.register_glue("actor_step_facing", [ctypes.c_uint32] * 2)
_TICK_TIMER30 = leaf.register_glue("actor_tick_timer30", [ctypes.c_uint32])
_FACE_TOWARD = leaf.register_glue("actor_face_and_step_toward", [ctypes.c_uint32] * 2)
_FACE_AWAY = leaf.register_glue("actor_face_and_step_away4", [ctypes.c_uint32])
_ANIM_LIST = leaf.register_glue("actor_anim_step_facing_list", [ctypes.c_uint32] * 2)
_SELECT_SPRITE = leaf.register_glue("actor_select_sprite_by_flag", [ctypes.c_uint32])
_HOP = leaf.register_glue("actor_hop_ascend_step", [ctypes.c_uint32])
_ANIM16 = leaf.register_glue("actor_advance_anim16", [ctypes.c_uint32] * 3, ctypes.c_uint32)
_OVERLAP = leaf.register_glue("actor_followed_overlap_mask", [ctypes.c_uint32], ctypes.c_uint32)
_TOWARD = leaf.register_glue("actor_step_toward_followed", [ctypes.c_uint32] * 2)
_ANIM_5160 = leaf.register_glue("actor_relaunch_and_anim_5160", [ctypes.c_uint32])
_SPRITE_6ED8 = leaf.register_glue("actor_sprite_from_6ed8", [ctypes.c_uint32], ctypes.c_uint32)
_CARRY = leaf.register_glue("actor_platform_carry_followed", [ctypes.c_uint32] * 3)
_RELEASE = leaf.register_glue("actor_platform_release_check", [ctypes.c_uint32] * 3)
_FACE_RESET = leaf.register_glue("actor_face_followed_reset_22", [ctypes.c_uint32])
_HIT_BY_SHOT = leaf.register_glue("actor_hit_by_player_shot", [ctypes.c_uint32], ctypes.c_uint32)


# --- seeding ---------------------------------------------------------------------------------------
def _tier_pokes(salt, overrides=None):
    """All three actor tables ADDRESS-KEYED with a record's margin either side, the two mode flags,
    the published table pointer, the flash timer and the platform word — every mutable input any
    routine in this file reads. `overrides` is applied last, per address."""
    pokes = {TABLES_LO: keyed_block(TABLES_LO, TABLES_HI - TABLES_LO, salt)}
    base = {FLAG_A32: word(0), FLAG_A34: word(0), TABLE_SELECTED: longword(TABLE_DEFAULT),
            FLASH_TIMER: word(0), PLATFORM_RIDDEN: word(0)}
    return leaf.overlay(pokes, base, overrides or {})


def _record(table, slot):
    return table + slot * RECORD_BYTES


def _walk_pokes(salt, types, overrides=None):
    """A table whose records are the `types` given, in slot order, and a terminator after them.

    A type of None means the record is FREE. Everything the walk reads is stated: the x word (the
    free marker and the terminator both live in it) and the type word. The rest of each record stays
    address-keyed, so a dispatch that read the wrong offset lands on a byte that is wrong for where
    it was written.
    """
    fields = {}
    for slot, kind in enumerate(types):
        record = _record(TABLE_DEFAULT, slot)
        if kind is None:
            fields[record + ACTOR_X] = word(FREE_MARKER)
            # A free record's type is left a slot NOTHING is reconstructed for, so a walk that
            # dispatched one instead of skipping it stops at a boundary and fails loudly.
            fields[record + ACTOR_TYPE] = word(UNPORTED_TYPE)
        else:
            fields[record + ACTOR_X] = word(OCCUPIED_X)
            fields[record + ACTOR_TYPE] = word(kind)
    terminator = _record(TABLE_DEFAULT, len(types))
    fields[terminator + ACTOR_X] = longword(TABLE_END)
    return _tier_pokes(salt, leaf.overlay(fields, overrides or {}))


# The `jmp (a1)` at the dispatcher's foot: the witness that a boundary run really transferred rather
# than returning. Its address comes out of the pin — every instruction before it — rather than being
# transcribed, so a body read one instruction short cannot leave the witness pointing at the wrong
# word.
DISPATCH_JMP_PC = (leaf.entry_of(DISPATCHER)
                   + len(_asm(leaf.entry_of(DISPATCHER), _dispatch_pieces()[:-1])))


# --- $928: the dispatch, entry by entry -------------------------------------------------------------
@pytest.mark.parametrize("slot", range(BEHAVIOR_SLOTS), ids=lambda v: f"slot{v:02d}")
def test_the_dispatcher_transfers_to_the_slot_the_type_names(slot):
    """ONE CASE PER TABLE ENTRY, and it is the whole pin on src/behavior.c's BEHAVIOR_SLOTS array.

    For an UNPORTED slot the reconstruction returns the address it would have transferred to and the
    oracle is stopped at that same address — so the two agree on WHICH handler, with `cov_visited`
    on the `jmp (a1)` as the positive evidence that the transfer fired rather than the routine
    having returned. For the two slots that ARE ported the run goes to the `rts` at $a36 and the
    reconstruction reports that it ran.
    """
    actor = _record(TABLE_DEFAULT, 3)
    what = f"actor_dispatch_behavior type {slot}"
    pokes = _tier_pokes(case_salt(what), {actor + ACTOR_TYPE: word(slot)})
    target = leaf.entry_of(TABLE_TARGETS[slot])
    regs = {"a0": actor, "_pokes": pokes}
    cap = _cap(DISPATCHER, extra=INSN_COUNT["actor_behavior_null"])

    if slot in PORTED_SLOTS:
        info = leaf.run(DISPATCHER, _DISPATCH(actor), [], what, regs=regs, max_insns=cap)
        assert info["ret"] == DISPATCH_RAN, (
            f"{what}: the reconstruction reported {info['ret']:#x}, not that it ran")
    else:
        info = leaf.run_reaching(DISPATCHER, _DISPATCH(actor), [], what, DISPATCH_JMP_PC,
                                 regs=regs, stop_pc=target, max_insns=cap)
        assert info["ret"] == target, (
            f"{what}: the reconstruction reported {info['ret']:#x} against the table's {target:#x}")
    assert not program_writes(info), f"{what}: the dispatcher wrote memory, which it does not"


def _dispatched_slot(type_word):
    """What src/behavior.c's guard makes of `type_word`, as this battery's own model of the wrapped
    offset: `lsl.w #2` wraps in sixteen bits and the extension word then sign-extends."""
    offset = s16((type_word * BEHAVIOR_ENTRY) & 0xffff)
    if 0 <= offset < BEHAVIOR_SLOTS * BEHAVIOR_ENTRY:
        return offset // BEHAVIOR_ENTRY
    return None


TYPE_CHUNKS = 8
TYPES_PER_CHUNK = 0x10000 // TYPE_CHUNKS


@pytest.mark.parametrize("chunk", range(TYPE_CHUNKS), ids=lambda v: f"chunk{v}")
def test_every_type_value_dispatches_the_wrapped_offset_or_is_refused(chunk):
    """ALL 65,536 TYPES, against the reconstruction alone — batch 27's aliasing pin at a bigger
    table, and the only surface a REFUSAL has (the original would `jmp` through arbitrary data, so
    no differential can drive one).

    The alias bands are what a guard on the raw type would get wrong: `lsl.w #2` wraps at $4000, so
    $4000..$403d, $8000..$803d and $c000..$c03d reach slots 0..61 exactly as 0..61 do — 248 of the
    65,536 values dispatch, and a raw-index guard would refuse 186 of them.
    """
    actor = _record(TABLE_DEFAULT, 3)
    image = harness.make_image(_tier_pokes(case_salt(f"types{chunk}")))
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(bytearray(image))
    dispatch = leaf.bind("actor_dispatch_behavior", [ctypes.POINTER(ctypes.c_uint8),
                                                     ctypes.c_uint32], ctypes.c_uint32)
    dispatched = 0

    for type_word in range(chunk * TYPES_PER_CHUNK, (chunk + 1) * TYPES_PER_CHUNK):
        buf[actor + ACTOR_TYPE] = type_word >> 8
        buf[actor + ACTOR_TYPE + 1] = type_word & 0xff
        slot = _dispatched_slot(type_word)
        answer = dispatch(buf, actor)
        if slot is None:
            assert answer == DISPATCH_REFUSED, (
                f"type {type_word:#06x} answered {answer:#x}, not the refusal its offset earns")
            continue
        dispatched += 1
        expected = DISPATCH_RAN if slot in PORTED_SLOTS else leaf.entry_of(TABLE_TARGETS[slot])
        assert answer == expected, (
            f"type {type_word:#06x} answered {answer:#x} against slot {slot}'s {expected:#x}")

    # $4000 is exactly half a chunk here, so a band lands wholly inside one chunk: the chunks that
    # contain one dispatch all 62 slots and the rest dispatch nothing.
    assert dispatched == (BEHAVIOR_SLOTS if chunk % (TYPE_CHUNKS // 4) == 0 else 0)


def test_the_alias_bands_are_exactly_four_and_the_refusal_set_is_the_rest():
    """The counting half of the enumeration above, stated once rather than per chunk."""
    dispatched = [t for t in range(0x10000) if _dispatched_slot(t) is not None]
    bands = sorted({t & ~0x3fff for t in dispatched})
    assert len(dispatched) == BEHAVIOR_SLOTS * len(bands)
    assert bands == [0x0000, 0x4000, 0x8000, 0xc000]
    # ...and a raw-index guard would have refused every alias, which is the defect this shape avoids.
    assert len([t for t in dispatched if t >= BEHAVIOR_SLOTS]) == BEHAVIOR_SLOTS * 3


@pytest.mark.parametrize("type_word,slot", [(0x4000 + 2, 2), (0x8000 + 7, 7), (0xc000 + 61, 61)],
                         ids=["band-4000", "band-8000", "band-c000"])
def test_an_aliased_type_dispatches_the_ordinary_slot(type_word, slot):
    """One per band, against the ORACLE: the original really does transfer to the same handler for
    $4002 as for $0002, which is what the enumeration above can only assert about the C."""
    actor = _record(TABLE_DEFAULT, 3)
    what = f"actor_dispatch_behavior aliased type {type_word:#06x}"
    pokes = _tier_pokes(case_salt(what), {actor + ACTOR_TYPE: word(type_word)})
    target = leaf.entry_of(TABLE_TARGETS[slot])

    info = leaf.run_reaching(DISPATCHER, _DISPATCH(actor), [], what, DISPATCH_JMP_PC,
                             regs={"a0": actor, "_pokes": pokes}, stop_pc=target,
                             max_insns=_cap(DISPATCHER))
    assert info["ret"] == target


# --- $8d0: the walk ---------------------------------------------------------------------------------
# One record costs the loop's own instructions plus a dispatch and the null handler; the cap is that
# per record, which is the loop's geometry rather than a round number.
WALK_INSN_PER_RECORD = (INSN_COUNT["actor_behavior_pass"] + INSN_COUNT["actor_dispatch_behavior"]
                        + INSN_COUNT["actor_behavior_null"])


WALK_CASES = [
    ("empty", []),
    ("one-live", [0]),
    ("one-free", [None]),
    ("alternating", [0, None, 0, None, 58]),
    ("all-free", [None] * 5),
    ("eight-live", [0] * 8),
]


@pytest.mark.parametrize("case,types", WALK_CASES, ids=[c[0] for c in WALK_CASES])
def test_the_walk_runs_to_its_own_rts_over_ported_slots(case, types):
    """The walk itself, with every live record a slot this port HAS: the free marker is skipped, the
    $ffffffff longword ends it, and both cores reach the `rts`. The pass writes nothing at all, so
    what the differential adds is that the ORACLE's a0 walked out where the model says."""
    what = f"actor_behavior_pass {case}"
    pokes = _walk_pokes(case_salt(what), types)
    info = leaf.run("actor_behavior_pass", _PASS, [], what, regs={"_pokes": pokes},
                    max_insns=WALK_INSN_PER_RECORD * (len(types) + 1) + leaf.LEAF_INSN_CAP)

    assert not program_writes(info), f"{what}: the pass wrote memory, which it does not"
    assert info["ret"] == DISPATCH_RAN, f"{what}: the reconstruction reported {info['ret']:#x}"
    assert info["regs"]["a0"] == _record(TABLE_DEFAULT, len(types)), (
        f"{what}: a0 stopped at {info['regs']['a0']:#x}, not on the terminator")


def test_the_end_marker_is_a_longword_and_the_free_marker_only_a_word():
    """A record whose x word is $ffff but whose type is not ends NOTHING — `cmpi.l` reads both — so
    the walk DISPATCHES it.

    THE TYPE HAS TO BE AN UNPORTED ONE. A ported one would make the reconstruction answer
    WB_ACTOR_DISPATCH_RAN whether it dispatched the record or stopped on it, and the pass writes no
    memory, so nothing would separate the two readings — the sweep's `end-marker-as-a-word` mutant
    survived exactly that shape. With an unported type the answer is the handler's own address.
    """
    what = "actor_behavior_pass ffff-x but not the terminator"
    slot = 2
    record = _record(TABLE_DEFAULT, 0)
    pokes = _walk_pokes(case_salt(what), [slot], {record + ACTOR_X: word(0xffff)})
    target = leaf.entry_of(TABLE_TARGETS[slot])

    info = leaf.run_reaching("actor_behavior_pass", _PASS, [], what, DISPATCH_JMP_PC,
                             regs={"_pokes": pokes}, stop_pc=target,
                             max_insns=WALK_INSN_PER_RECORD * 2 + leaf.LEAF_INSN_CAP)
    assert info["ret"] == target, (
        f"{what}: the reconstruction reported {info['ret']:#x}, so it read the terminator as a "
        f"WORD and ended the walk")


@pytest.mark.parametrize("slot", [2, 38, 61], ids=lambda v: f"handler{v:02d}")
def test_the_walk_stops_at_the_first_unported_handler(slot):
    """THE BOUNDARY, through the pass rather than the dispatcher: two free records, one ported one
    and then a record whose type this port does not have. The reconstruction reports that handler's
    address and the oracle is stopped there, with the `jmp (a1)` as the witness."""
    what = f"actor_behavior_pass boundary at slot {slot}"
    pokes = _walk_pokes(case_salt(what), [None, 0, None, slot, 0])
    target = leaf.entry_of(TABLE_TARGETS[slot])

    info = leaf.run_reaching("actor_behavior_pass", _PASS, [], what, DISPATCH_JMP_PC,
                             regs={"_pokes": pokes}, stop_pc=target,
                             max_insns=WALK_INSN_PER_RECORD * 6)
    assert info["ret"] == target, (
        f"{what}: the reconstruction reported {info['ret']:#x} against {target:#x}")
    assert not program_writes(info), f"{what}: the pass wrote memory before the boundary"


@pytest.mark.parametrize("flag", [0x0001, 0x8000, 0xffff], ids=lambda v: f"a34={v:#06x}")
def test_the_a34_arm_runs_three_fixed_records_and_no_walk(flag):
    """`tst.w / bne` — any nonzero word takes the fixed path, negative or not. Slot 0, slot 1 and
    then WB_ACTOR_BEHAVIOR_FIXED_SKIP on, which lands on WB_ACTOR_FOLLOWED_SLOT: seeded here as a
    ported type, with a TERMINATOR at slot 2 that the arm must not stop on."""
    what = f"actor_behavior_pass a34 {flag:#06x}"
    fields = {}
    for slot in (0, 1, FOLLOWED_SLOT):
        fields[_record(TABLE_DEFAULT, slot) + ACTOR_X] = word(OCCUPIED_X)
        fields[_record(TABLE_DEFAULT, slot) + ACTOR_TYPE] = word(0)
    fields[_record(TABLE_DEFAULT, 2) + ACTOR_X] = longword(TABLE_END)
    pokes = _tier_pokes(case_salt(what), leaf.overlay(fields, {FLAG_A34: word(flag)}))

    info = leaf.run("actor_behavior_pass", _PASS, [], what, regs={"_pokes": pokes},
                    max_insns=WALK_INSN_PER_RECORD * 4)
    assert info["ret"] == DISPATCH_RAN
    assert info["regs"]["a0"] == _record(TABLE_DEFAULT, FOLLOWED_SLOT), (
        f"{what}: a0 stopped at {info['regs']['a0']:#x}, not on slot {FOLLOWED_SLOT}")


def test_the_a34_arms_third_dispatch_is_not_guarded_by_the_free_marker():
    """THE PLATE CORRECTION, as a case. The first two fixed records are skipped when free; the third
    is reached by `lea 352(a0),a0 / bra.w $928` with no test at all, so a FREE followed slot is
    dispatched on whatever type word its bytes hold. Seeded free AND with an unported type, so the
    boundary the run reports is the proof it dispatched."""
    what = "actor_behavior_pass a34 free followed slot"
    slot = 5
    fields = {_record(TABLE_DEFAULT, 0) + ACTOR_X: word(FREE_MARKER),
              _record(TABLE_DEFAULT, 1) + ACTOR_X: word(FREE_MARKER),
              _record(TABLE_DEFAULT, FOLLOWED_SLOT) + ACTOR_X: word(FREE_MARKER),
              _record(TABLE_DEFAULT, FOLLOWED_SLOT) + ACTOR_TYPE: word(slot)}
    pokes = _tier_pokes(case_salt(what), leaf.overlay(fields, {FLAG_A34: word(0xffff)}))
    target = leaf.entry_of(TABLE_TARGETS[slot])

    info = leaf.run_reaching("actor_behavior_pass", _PASS, [], what, DISPATCH_JMP_PC,
                             regs={"_pokes": pokes}, stop_pc=target,
                             max_insns=WALK_INSN_PER_RECORD * 4)
    assert info["ret"] == target


def test_the_a34_arm_walks_whichever_table_was_published():
    """a0 comes out of WB_ACTOR_TABLE_SELECTED, so a port that hardcoded a table passes only one of
    these — the same pin test_actor.py's allocators carry."""
    what = "actor_behavior_pass a34 over the a32 table"
    fields = {}
    for slot in (0, 1, FOLLOWED_SLOT):
        fields[_record(TABLE_A32, slot) + ACTOR_X] = word(OCCUPIED_X)
        fields[_record(TABLE_A32, slot) + ACTOR_TYPE] = word(0)
    # ...and the DEFAULT table's same three slots hold an unported type, so a hardcoded port stops.
    for slot in (0, 1, FOLLOWED_SLOT):
        fields[_record(TABLE_DEFAULT, slot) + ACTOR_X] = word(OCCUPIED_X)
        fields[_record(TABLE_DEFAULT, slot) + ACTOR_TYPE] = word(7)
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        fields, {FLAG_A34: word(0xffff), TABLE_SELECTED: longword(TABLE_A32)}))

    info = leaf.run("actor_behavior_pass", _PASS, [], what, regs={"_pokes": pokes},
                    max_insns=WALK_INSN_PER_RECORD * 4)
    assert info["ret"] == DISPATCH_RAN
    assert info["regs"]["a0"] == _record(TABLE_A32, FOLLOWED_SLOT)


# --- the shared leaves ------------------------------------------------------------------------------
# Every case below states its write set EXACTLY, except the three that call the map probes: those
# BOUND it to the record and the two words the probes are entitled to touch, because modelling
# $10a2/$1170's own arithmetic here would be a second copy of test_map.py's model.
ACTOR_SLOT = 3                       # any record but the followed one
ACTOR = _record(TABLE_DEFAULT, ACTOR_SLOT)


def _put(out, addr, value, length=WORD_BYTES):
    for offset in range(length):
        out[addr + offset] = (value >> (8 * (length - 1 - offset))) & 0xff


def _assert_writes(info, expected, what):
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {sorted(hex(a) for a in written)} against the model's "
        f"{sorted(hex(a) for a in expected)}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")


def _record_fields(record, fields):
    """{address: bytes} for a record's named fields — `fields` is {offset: (value, length)}."""
    return {record + offset: value.to_bytes(length, "big")
            for offset, (value, length) in fields.items()}


def _image_word(addr):
    return int.from_bytes(harness.BASE_IMAGE[addr:addr + WORD_BYTES], "big")


# --- $698a: the spawn animation ---------------------------------------------------------------------
# The frame table is SHIPPED image data, so the expected sprite comes out of the image rather than
# being transcribed — a case that restated the frames would pass on its own transcription.
# The last row is the SWEEP'S OWN FINDING: every other cursor here answers the same under a $f mask
# as under a $1f one (both wrap at 16 and at 32, and both step at 34), so a battery without it would
# pass with the sixteen-byte stepper's mask in this routine — which is exactly the defect a mutation
# run left in the tree and this row now catches.
SPAWN_ANIM_CURSORS = [0, 2, SPAWN_ANIM_MASK - 1, SPAWN_ANIM_MASK + 1, 0x40, 0xfe, 0xff,
                      ANIM16_MASK - 1]


@pytest.mark.parametrize("flags2", [0x00, 1 << SPAWNED_BIT, 0xff], ids=lambda v: f"flags2{v:#04x}")
@pytest.mark.parametrize("cursor", SPAWN_ANIM_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_the_spawn_animation_steps_a_word_and_releases_the_record_on_the_wrap(cursor, flags2):
    """The cursor is a BYTE OFFSET masked to WB_ACTOR_SPAWN_ANIM_MASK, so $20 and $40 both wrap and
    $ff steps to $01 — the byte `addq` and the word `andi` agreeing is the whole subtlety. On the
    wrap the SPAWNED bit comes down, which is what releases the record to its real handler."""
    what = f"actor_spawn_anim_step cursor={cursor:#04x} flags2={flags2:#04x}"
    pokes = _tier_pokes(case_salt(what), _record_fields(ACTOR, {
        FIELD_18: (cursor, 1), FLAGS2: (flags2, 1), ACTOR_SPRITE: (0x0000, 2)}))

    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + cursor))
    if ((cursor + ANIM_FRAME_BYTES) & SPAWN_ANIM_MASK) != 0:
        expected[ACTOR + FIELD_18] = (cursor + ANIM_FRAME_BYTES) & 0xff
    else:
        expected[ACTOR + FIELD_18] = 0
        expected[ACTOR + FLAGS2] = flags2 & ~(1 << SPAWNED_BIT)

    info = leaf.run("actor_spawn_anim_step", _SPAWN_ANIM(ACTOR),
                    merge_bands(expected), what, regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_spawn_anim_step"))
    _assert_writes(info, expected, what)


def test_the_spawn_animations_second_half_is_out_of_the_cursors_reach():
    """The batch-28 open question, as a property rather than a comment: the mask reaches sixteen
    words, so half the run laid out at $69be is unreachable from the only routine that reads it."""
    frames = (SPAWN_ANIM_MASK + 1) // ANIM_FRAME_BYTES
    assert frames == 16
    # ...and the run itself is 32 words, which is what makes the upper half unreached data.
    assert (leaf.entry_of("actor_damage_followed") - SPAWN_ANIM_FRAMES) // WORD_BYTES == 2 * frames


# --- $2f86: the countdown and its relaunch -----------------------------------------------------------
# rng_next STEPS THREE COUNTERS, so a case that reaches it has those three words in its write set —
# imported from the battery that owns them rather than restated.
from test_rng import FRAME_TICK, model_rng                      # noqa: E402

# The generator's word is the frame tick plus its three counters (the off-image entropy byte reads
# zero on both sides), so the tick is the ONE input a case can steer the relaunch's `btst #2` with.
# Both values are needed: with only one of them the VETO arm never runs and dropping the guard
# altogether passes — which is exactly what the sweep found.
TICKS_BY_RNG_BIT = {0: 0x0000, 1: 0x0004}


@pytest.mark.parametrize("tick", sorted(TICKS_BY_RNG_BIT.values()), ids=lambda v: f"tick{v:#06x}")
@pytest.mark.parametrize("flags", [0x00, 1 << SUPPORTED_BIT, 0xff], ids=lambda v: f"flags{v:#04x}")
@pytest.mark.parametrize("timer", [0, 1, 2, 0x32, 0xff], ids=lambda v: f"timer{v:#04x}")
def test_the_timer_counts_down_and_only_a_supported_record_relaunches(timer, flags, tick):
    """Three arms: the ordinary decrement, the reload alone, and the reload plus the relaunch. The
    reload runs BEFORE the supported test, so an unsupported record still gets a fresh countdown —
    which is the arm a port that guarded the whole tail would get wrong. The two ticks drive
    `btst #2` of the generator's word BOTH ways, so the VETO is exercised and not only the launch.
    """
    what = f"actor_tick_timer30 timer={timer:#04x} flags={flags:#04x} tick={tick:#06x}"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(ACTOR, {FIELD_30: (timer, 1), ACTOR_FLAGS: (flags, 1),
                               SPEED: (0x11, 1), FIELD_18: (0x22, 1)}),
        {FRAME_TICK: word(tick)}))

    expected = {}
    if timer != 0:
        expected[ACTOR + FIELD_30] = timer - 1
    else:
        expected[ACTOR + FIELD_30] = TIMER30_RELOAD
        if flags & (1 << SUPPORTED_BIT):
            drawn, counters = model_rng(harness.make_image(pokes), 0)
            expected.update(counters)
            if not drawn & (1 << TIMER30_RNG_BIT):
                relaunched = flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
                expected[ACTOR + ACTOR_FLAGS] = relaunched & ~(1 << SUPPORTED_BIT)
                expected[ACTOR + SPEED] = TIMER30_SPEED
                expected[ACTOR + FIELD_18] = 0

    info = leaf.run("actor_tick_timer30", _TICK_TIMER30(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_tick_timer30", extra=RNG_INSNS))
    _assert_writes(info, expected, what)


# --- $3006, $5a3c, $6872: the three animation steppers ------------------------------------------------
# A frame list a case controls goes in a band of the image no routine here reads, so a stepper that
# followed the wrong pointer lands on the .PRG's own bytes rather than on a plausible frame.
SCRATCH = 0x30000
FRAME_LIST_LEFT = SCRATCH + 0x40
FRAME_LIST_RIGHT = SCRATCH + 0x80
LIST_PAIR = SCRATCH

# Frames a case can tell apart from every other seed, and a NEGATIVE terminator, which is what ends
# a $3006 list (the $6872 list's is WB_ACTOR_ANIM_5160_END and lives in the image).
LEFT_FRAMES = (0x0101, 0x0102, 0x0103)
RIGHT_FRAMES = (0x0201, 0x0202)
LIST_TERMINATOR = 0x8000


# Two POSITIVE words past each terminator, so a cursor sitting ON the terminator still reads a
# seeded word rather than the .PRG's own bytes — the stepper reads one word past the frame it
# publishes, and a case has to have seeded that one too.
LIST_PADDING = (0x0001, 0x0002)


def _frame_list(base, frames):
    body = b"".join(word(frame) for frame in tuple(frames) + (LIST_TERMINATOR,) + LIST_PADDING)
    return {base: body}


def _list_pokes(salt, fields):
    return _tier_pokes(salt, leaf.overlay(
        {LIST_PAIR: longword(FRAME_LIST_LEFT) + longword(FRAME_LIST_RIGHT)},
        _frame_list(FRAME_LIST_LEFT, LEFT_FRAMES),
        _frame_list(FRAME_LIST_RIGHT, RIGHT_FRAMES),
        fields))


def test_the_timer_cases_drive_the_relaunch_veto_both_ways():
    """A tick table that only ever cleared the bit would leave `btst #2,d0 / bne` — half of every
    real reload — untested, and deleting the guard would pass. This states which tick does which."""
    for expected_bit, tick in TICKS_BY_RNG_BIT.items():
        pokes = _tier_pokes(case_salt("veto-coverage"), {FRAME_TICK: word(tick)})
        drawn, _counters = model_rng(harness.make_image(pokes), 0)
        assert ((drawn >> TIMER30_RNG_BIT) & 1) == expected_bit, (
            f"tick {tick:#06x} draws {drawn:#x}, whose bit {TIMER30_RNG_BIT} is not {expected_bit}")


@pytest.mark.parametrize("cursor", [0, 2, 4, 6], ids=lambda v: f"cursor{v}")
@pytest.mark.parametrize("side", [0, 1 << SIDE_BIT], ids=["side-clear", "side-set"])
def test_the_facing_list_stepper_publishes_a_frame_and_stops_on_a_negative_word(side, cursor):
    """The SIDE bit picks (a1) or 4(a1) — two whole frame lists of different lengths, so a port that
    read the wrong longword publishes the wrong frame. Cursor 4 is the last frame of the LEFT list
    and 6 its terminator's own slot, which is where the two lists' lengths part company."""
    what = f"actor_anim_step_facing_list side={side} cursor={cursor}"
    pokes = _list_pokes(case_salt(what), _record_fields(ACTOR, {
        FIELD_18: (cursor, 1), ACTOR_FLAGS: (side, 1), ACTOR_SPRITE: (0, 2)}))

    # The list is read back OUT OF THE COMPOSED IMAGE rather than from the tuple above, so the
    # model cannot disagree with what the case actually seeded.
    image = harness.make_image(pokes)
    frame = (FRAME_LIST_LEFT if side else FRAME_LIST_RIGHT) + cursor
    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE, leaf.u16(image, frame))
    expected[ACTOR + FIELD_18] = (0 if s16(leaf.u16(image, frame + WORD_BYTES)) < 0
                                  else cursor + ANIM_FRAME_BYTES)

    info = leaf.run("actor_anim_step_facing_list", _ANIM_LIST(ACTOR, LIST_PAIR),
                    merge_bands(expected), what,
                    regs={"a0": ACTOR, "a1": LIST_PAIR, "_pokes": pokes},
                    max_insns=_cap("actor_anim_step_facing_list"))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("cursor", [0x00, 0x0e, 0x10, 0xff],
                         ids=lambda v: f"cursor{v:#04x}")
def test_the_sixteen_byte_stepper_wraps_its_cursor_in_a_byte(cursor):
    """$5a3c takes BOTH its registers from the caller and hands the wrapped cursor back in d0 —
    which $5a14 `tst.b`s, so the return is part of the interface. `andi.b` writes only the low byte,
    so a caller's upper three come back untouched, and the entry d0 carries them."""
    entry_d0 = 0xdead0000 | cursor
    what = f"actor_advance_anim16 cursor={cursor:#04x}"
    pokes = _list_pokes(case_salt(what), _record_fields(ACTOR, {
        FIELD_18: (0x77, 1), ACTOR_SPRITE: (0, 2)}))

    stepped = (cursor + ANIM_FRAME_BYTES) & ANIM16_MASK
    expected = {ACTOR + FIELD_18: stepped}
    _put(expected, ACTOR + ACTOR_SPRITE, leaf.u16(harness.make_image(pokes), FRAME_LIST_LEFT))

    info = leaf.run("actor_advance_anim16", _ANIM16(ACTOR, FRAME_LIST_LEFT, entry_d0),
                    merge_bands(expected), what,
                    regs={"a0": ACTOR, "a1": FRAME_LIST_LEFT, "d0": entry_d0, "_pokes": pokes},
                    max_insns=_cap("actor_advance_anim16"))
    _assert_writes(info, expected, what)
    assert info["ret"] == (entry_d0 & ~0xff) | stepped, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not the caller's high bytes over "
        f"the wrapped cursor")
    assert info["regs"]["d0"] == info["ret"], f"{what}: the original's d0 disagrees"


# $5160's own terminator, found in the image rather than transcribed: the cursor that publishes the
# last frame is the one whose NEXT word is WB_ACTOR_ANIM_5160_END.
ANIM_5160_LAST = next(cursor for cursor in range(0, 0x100, WORD_BYTES)
                      if _image_word(ANIM_5160_FRAMES + cursor + WORD_BYTES) == ANIM_5160_END)


@pytest.mark.parametrize("timer", [0, 1, 2, 0xff], ids=lambda v: f"timer{v:#04x}")
@pytest.mark.parametrize("cursor", [0, 2, ANIM_5160_LAST], ids=lambda v: f"cursor{v}")
@pytest.mark.parametrize("flags", [0x00, 1 << SUPPORTED_BIT], ids=["free", "supported"])
def test_the_5160_stepper_relaunches_on_the_tick_that_reaches_its_hold_value(flags, cursor, timer):
    """The countdown stops ON WB_ACTOR_ANIM_5160_HOLD rather than on zero, so a timer of 1 does
    nothing at all and a timer of 2 is the tick that launches — and the speed it launches at is the
    decremented byte, which is that same 1. A timer of 0 wraps to $ff and counts the long way."""
    what = f"actor_relaunch_and_anim_5160 flags={flags:#04x} cursor={cursor} timer={timer:#04x}"
    pokes = _tier_pokes(case_salt(what), _record_fields(ACTOR, {
        ACTOR_FLAGS: (flags, 1), FIELD_18: (cursor, 1), FIELD_30: (timer, 1),
        SPEED: (0x55, 1), ACTOR_SPRITE: (0, 2)}))

    expected = {}
    if flags & (1 << SUPPORTED_BIT) and timer != ANIM_5160_HOLD:
        expected[ACTOR + FIELD_30] = (timer - 1) & 0xff
        expected[ACTOR + SPEED] = (timer - 1) & 0xff
        launched = (flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & ~(1 << SUPPORTED_BIT)
        expected[ACTOR + ACTOR_FLAGS] = launched
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(ANIM_5160_FRAMES + cursor))
    wrapped = _image_word(ANIM_5160_FRAMES + cursor + WORD_BYTES) == ANIM_5160_END
    expected[ACTOR + FIELD_18] = 0 if wrapped else (cursor + ANIM_FRAME_BYTES) & 0xff

    info = leaf.run("actor_relaunch_and_anim_5160", _ANIM_5160(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_relaunch_and_anim_5160"))
    _assert_writes(info, expected, what)


# --- $4fea, $501a, $701c: three record-only leaves ---------------------------------------------------
@pytest.mark.parametrize("flags", [0x00, 1 << SUPPORTED_BIT, 1 << MOVING_BIT,
                                   (1 << SUPPORTED_BIT) | (1 << MOVING_BIT), 0xff],
                         ids=lambda v: f"flags{v:#04x}")
def test_the_sprite_select_tests_supported_first_then_moving(flags):
    what = f"actor_select_sprite_by_flag flags={flags:#04x}"
    pokes = _tier_pokes(case_salt(what), _record_fields(ACTOR, {
        ACTOR_FLAGS: (flags, 1), ACTOR_SPRITE: (0, 2)}))

    sprite = (SPRITE_SUPPORTED if flags & (1 << SUPPORTED_BIT)
              else SPRITE_MOVING if flags & (1 << MOVING_BIT) else SPRITE_IDLE)
    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE, sprite)

    info = leaf.run("actor_select_sprite_by_flag", _SELECT_SPRITE(ACTOR), merge_bands(expected),
                    what, regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_select_sprite_by_flag"))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("speed", [0, 1, 2, 8, 0xff], ids=lambda v: f"speed{v:#04x}")
@pytest.mark.parametrize("flags", [0x00, 1 << MOVING_BIT, 0xff], ids=lambda v: f"flags{v:#04x}")
def test_the_hop_lifts_by_its_own_speed_and_ends_when_the_byte_runs_out(flags, speed):
    """A speed of 0 is the case that says the decrement is a BYTE one: $00 - 1 is $ff, not the end
    of the hop, so the record rises for another 255 frames."""
    y = 0x0140
    what = f"actor_hop_ascend_step flags={flags:#04x} speed={speed:#04x}"
    pokes = _tier_pokes(case_salt(what), _record_fields(ACTOR, {
        ACTOR_FLAGS: (flags, 1), SPEED: (speed, 1), ACTOR_Y: (y, 2)}))

    expected = {}
    if flags & (1 << MOVING_BIT):
        _put(expected, ACTOR + ACTOR_Y, (y - speed) & 0xffff)
        stepped = (speed - 1) & 0xff
        expected[ACTOR + SPEED] = 1 if stepped == 0 else stepped
        if stepped == 0:
            expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << MOVING_BIT)

    info = leaf.run("actor_hop_ascend_step", _HOP(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=_cap("actor_hop_ascend_step"))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("field22", [0x00, 0x01, 0xff], ids=lambda v: f"f22={v:#04x}")
@pytest.mark.parametrize("followed_x,actor_x", [(0x0140, 0x0100), (0x0100, 0x0140), (0x120, 0x120)],
                         ids=["followed-right", "followed-left", "equal"])
def test_the_side_flag_this_routine_writes_is_the_opposite_polarity(followed_x, actor_x, field22):
    """THE FINDING, as a case: $67c2 raises the bit while the followed record is to the LEFT and
    $701c raises it while it is to the RIGHT. `followed-right` is the row that separates them — a
    port that called actor_set_side_flag here would clear the bit exactly where this sets it."""
    what = f"actor_face_followed_reset_22 followed={followed_x:#06x} actor={actor_x:#06x}"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(ACTOR, {ACTOR_X: (actor_x, 2), ACTOR_FLAGS: (0, 1),
                               FIELD_22: (field22, 1)}),
        _record_fields(FOLLOWED_DEFAULT, {ACTOR_X: (followed_x, 2)})))

    expected = {ACTOR + ACTOR_FLAGS: (1 << SIDE_BIT) if s16(followed_x) > s16(actor_x) else 0}
    if field22 != 0:
        expected[ACTOR + FIELD_22] = FIELD_22_HOLD

    info = leaf.run("actor_face_followed_reset_22", _FACE_RESET(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_face_followed_reset_22", extra=FOLLOWED_INSNS))
    _assert_writes(info, expected, what)


# --- $6840 and $6d5a: the two that read the followed record ------------------------------------------
@pytest.mark.parametrize("step", [0, 1, 4, 0x8000], ids=lambda v: f"step{v:#06x}")
# The third row puts BOTH compares exactly on their boundary — `bgt` takes the equal case the other
# way from `bge`, and with only the two strict rows an inverted compare ships green.
@pytest.mark.parametrize("followed_x,followed_y",
                         [(0x0140, 0x0200), (0x0100, 0x0100), (0x0120, 0x0190)],
                         ids=["followed-right-below", "followed-left-above", "both-axes-equal"])
def test_the_homing_step_moves_both_axes_toward_the_followed_record(followed_x, followed_y, step):
    """Each axis compares and then adds or subtracts d7, and the VERTICAL one aims at
    WB_ACTOR_PLATFORM_TOP above the followed record's y rather than at it. `step` of $8000 is the
    wrap: `add.w`/`sub.w` are word operations and the x word really does come back round."""
    x, y = 0x0120, 0x0180
    what = f"actor_step_toward_followed followed=({followed_x:#x},{followed_y:#x}) step={step:#x}"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(ACTOR, {ACTOR_X: (x, 2), ACTOR_Y: (y, 2)}),
        _record_fields(FOLLOWED_DEFAULT, {ACTOR_X: (followed_x, 2), ACTOR_Y: (followed_y, 2)})))

    target_y = s16((followed_y - PLATFORM_TOP) & 0xffff)
    expected = {}
    _put(expected, ACTOR + ACTOR_X, (x - step if s16(x) > s16(followed_x) else x + step) & 0xffff)
    _put(expected, ACTOR + ACTOR_Y, (y - step if s16(y) > target_y else y + step) & 0xffff)

    info = leaf.run("actor_step_toward_followed", _TOWARD(ACTOR, step), merge_bands(expected), what,
                    regs={"a0": ACTOR, "d7": step, "_pokes": pokes},
                    max_insns=_cap("actor_step_toward_followed", extra=FOLLOWED_INSNS))
    _assert_writes(info, expected, what)


# $2000 scales to $10000, whose low word is 0 — the index wraps back onto the table's own first row;
# $1000 scales to $8000, which `adda.w` sign-extends to -32768 and addresses BELOW the table. Without
# those two the `lsl.w`/`adda.w` pair is unpinned and dropping the sign extension passes.
@pytest.mark.parametrize("index", [0, 1, 2, 0x1000, 0x2000], ids=lambda v: f"row{v:#x}")
@pytest.mark.parametrize("a32", [0x0000, 0xffff], ids=["a32-clear", "a32-set"])
def test_the_6ed8_lookup_publishes_a_row_and_hands_back_the_followed_record(a32, index):
    """Two results: the sprite word it writes and the a1 its `bra.w` tail leaves — the second is
    `followed_actor_record`'s whole output, so a port that returned the wrong table fails on it."""
    what = f"actor_sprite_from_6ed8 index={index} a32={a32:#06x}"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(ACTOR, {HALF_WIDTH: (index, 2), ACTOR_SPRITE: (0, 2)}),
        {FLAG_A32: word(a32)}))

    # The row address is modelled the way the routine computes it — `lsl.w #3` inside the WORD, then
    # `adda.w`'s SIGN EXTENSION, then the 24-bit bus — and read back with the same off-image answer
    # the shim gives, so the two large indices are pinned rather than assumed.
    row = (SPRITE_TABLE_6ED8 + s16((index * SPRITE_6ED8_STRIDE) & 0xffff)) & BUS_ADDR_MASK
    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE,
         _image_word(row) if row + WORD_BYTES <= harness.IMAGE_SIZE else 0)
    followed = FOLLOWED_A32 if a32 else FOLLOWED_DEFAULT

    info = leaf.run("actor_sprite_from_6ed8", _SPRITE_6ED8(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_sprite_from_6ed8", extra=FOLLOWED_INSNS))
    _assert_writes(info, expected, what)
    assert info["regs"]["a1"] == followed, f"{what}: the original left a1={info['regs']['a1']:#x}"
    assert info["ret"] == followed, f"{what}: the reconstruction returned {info['ret']:#x}"


# --- $6d70 / $6dd8: the moving platform ----------------------------------------------------------------
BAND = SCRATCH + 0x100
BAND_BACK = 0x10           # 4(a2): how far left of the platform's x the band starts
BAND_SPAN = 0x30           # 6(a2): and how wide it is
PLATFORM_X, PLATFORM_Y = 0x0180, 0x0140
PLATFORM_RIDE_Y = PLATFORM_Y - PLATFORM_TOP


def _platform_pokes(salt, followed_x, followed_y, followed_flags=0, followed_flags2=0,
                    field22=0, ridden=0):
    return _tier_pokes(salt, leaf.overlay(
        {BAND + BAND_LEFT: word(BAND_BACK), BAND + BAND_WIDTH: word(BAND_SPAN),
         PLATFORM_RIDDEN: word(ridden)},
        _record_fields(ACTOR, {ACTOR_X: (PLATFORM_X, 2), ACTOR_Y: (PLATFORM_Y, 2),
                               FIELD_22: (field22, 1)}),
        _record_fields(FOLLOWED_DEFAULT, {
            ACTOR_X: (followed_x & 0xffff, 2), ACTOR_Y: (followed_y & 0xffff, 2),
            ACTOR_FLAGS: (followed_flags, 1), FLAGS2: (followed_flags2, 1), SPEED: (0x33, 1)})))


CARRY_CASES = [
    ("centred", PLATFORM_X, PLATFORM_RIDE_Y, True),
    ("on-the-top", PLATFORM_X, PLATFORM_RIDE_Y, True),
    ("one-above", PLATFORM_X, PLATFORM_RIDE_Y - 1, False),
    ("at-the-catch-depth", PLATFORM_X, PLATFORM_RIDE_Y + PLATFORM_CATCH, True),
    ("one-past-the-catch", PLATFORM_X, PLATFORM_RIDE_Y + PLATFORM_CATCH + 1, False),
    ("band-left-edge", PLATFORM_X - BAND_BACK, PLATFORM_RIDE_Y, True),
    ("one-left-of-the-band", PLATFORM_X - BAND_BACK - 1, PLATFORM_RIDE_Y, False),
    ("band-right-edge", PLATFORM_X - BAND_BACK + BAND_SPAN, PLATFORM_RIDE_Y, True),
    ("one-right-of-the-band", PLATFORM_X - BAND_BACK + BAND_SPAN + 1, PLATFORM_RIDE_Y, False),
]


@pytest.mark.parametrize("case,followed_x,followed_y,caught", CARRY_CASES,
                         ids=[c[0] for c in CARRY_CASES])
def test_the_platform_catches_the_followed_record_inside_its_band(case, followed_x, followed_y,
                                                                  caught):
    """Both edges of both gates, one row either side of each: the vertical one is `0 <= below <=
    WB_ACTOR_PLATFORM_CATCH` and the horizontal one the caller's band, inclusive at both ends."""
    # Every bit the catch clears is seeded SET, or clearing it writes nothing and a dropped
    # `bclr` survives — the sweep's `carry-launched-bit` finding.
    followed_flags = (1 << FALLING_BIT) | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
    what = f"actor_platform_carry_followed {case}"
    pokes = _platform_pokes(case_salt(what), followed_x, followed_y, followed_flags, field22=0)

    expected = {}
    if caught:
        _put(expected, PLATFORM_RIDDEN, 1)
        expected[ACTOR + FIELD_22] = 1 << RIDING_BIT
        _put(expected, FOLLOWED_DEFAULT + ACTOR_Y, PLATFORM_RIDE_Y)
        carried = followed_flags | (1 << SUPPORTED_BIT) | (1 << CARRIED_BIT)
        carried &= ~((1 << FALLING_BIT) | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT))
        expected[FOLLOWED_DEFAULT + ACTOR_FLAGS] = carried
        expected[FOLLOWED_DEFAULT + SPEED] = 0

    info = leaf.run("actor_platform_carry_followed", _CARRY(ACTOR, FOLLOWED_DEFAULT, BAND),
                    merge_bands(expected), what,
                    regs={"a0": ACTOR, "a1": FOLLOWED_DEFAULT, "a2": BAND, "_pokes": pokes},
                    max_insns=_cap("actor_platform_carry_followed"))
    _assert_writes(info, expected, what)


def test_the_bands_right_edge_wraps_in_sixteen_bits():
    """`add.w 6(a2),d0` is a WORD add, so a band whose left edge is high and whose width carries past
    $ffff comes back round BELOW it — and the followed record is then out of the band on the right
    where a 32-bit sum would have kept it in. Without this the cast in
    `followed_is_over_platform` can be widened to int32_t and nothing notices."""
    what = "actor_platform_carry_followed band wrapping the word"
    platform_x, band_back, band_span = 0x7f00, 0, 0x0200
    followed_x = 0x7f80                       # inside a 32-bit band, outside the wrapped one
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        {BAND + BAND_LEFT: word(band_back), BAND + BAND_WIDTH: word(band_span)},
        _record_fields(ACTOR, {ACTOR_X: (platform_x, 2), ACTOR_Y: (PLATFORM_Y, 2),
                               FIELD_22: (0, 1)}),
        _record_fields(FOLLOWED_DEFAULT, {ACTOR_X: (followed_x, 2),
                                          ACTOR_Y: (PLATFORM_RIDE_Y, 2)})))

    # The wrapped right edge is NEGATIVE, so `cmp.w d0,d2 / bgt` rejects: nothing is written.
    assert s16((platform_x - band_back + band_span) & 0xffff) < 0, (
        "the case does not actually wrap — pick a wider band")

    info = leaf.run("actor_platform_carry_followed", _CARRY(ACTOR, FOLLOWED_DEFAULT, BAND),
                    [], what,
                    regs={"a0": ACTOR, "a1": FOLLOWED_DEFAULT, "a2": BAND, "_pokes": pokes},
                    max_insns=_cap("actor_platform_carry_followed"))
    assert not program_writes(info), f"{what}: the wrapped band caught the record"


RELEASE_CASES = [
    ("still-riding", PLATFORM_X, 0, 0, False),
    ("left-the-band", PLATFORM_X - BAND_BACK - 1, 0, 0, True),
    ("right-of-the-band", PLATFORM_X - BAND_BACK + BAND_SPAN + 1, 0, 0, True),
    ("landed", PLATFORM_X, 0, 1 << LANDED_BIT, True),
    ("invulnerable", PLATFORM_X, 0, 1 << INVULNERABLE_BIT, True),
    ("moving", PLATFORM_X, 1 << MOVING_BIT, 0, True),
]


@pytest.mark.parametrize("case,followed_x,flags,flags2,released", RELEASE_CASES,
                         ids=[c[0] for c in RELEASE_CASES])
def test_the_platform_lets_go_on_any_of_four_conditions(case, followed_x, flags, flags2, released):
    """FOUR ways out and ONE way to stay: the `beq` on WB_ACTOR_FLAG_MOVING_BIT is the only path
    that returns without writing, which is why `still-riding` is the row with an empty write set."""
    what = f"actor_platform_release_check {case}"
    pokes = _platform_pokes(case_salt(what), followed_x, PLATFORM_RIDE_Y, flags, flags2,
                            field22=0xff, ridden=1)

    expected = {}
    if released:
        expected[ACTOR + FIELD_22] = 0xff & ~(1 << RIDING_BIT)
        _put(expected, PLATFORM_RIDDEN, 0)

    info = leaf.run("actor_platform_release_check", _RELEASE(ACTOR, FOLLOWED_DEFAULT, BAND),
                    merge_bands(expected), what,
                    regs={"a0": ACTOR, "a1": FOLLOWED_DEFAULT, "a2": BAND, "_pokes": pokes},
                    max_insns=_cap("actor_platform_release_check"))
    _assert_writes(info, expected, what)


# --- $5c6e: the three-bit overlap mask ------------------------------------------------------------
# IT WRITES NO MEMORY, so the byte-for-byte diff is vacuous for it and the whole pin is d0: the
# reconstruction's return is compared against the ORACLE's register AND against a model transcribed
# here from the disassembly independently of src/behavior.c. The oracle is what makes a shared
# misreading fail; the model is what makes a wrong ANSWER fail where it is wrong.
OVERLAP_ACTOR_X, OVERLAP_ACTOR_Y = 0x0200, 0x0180
OVERLAP_ACTOR_HALF_WIDTH, OVERLAP_ACTOR_HEIGHT = 0x10, 0x20
FOLLOWED_HALF_WIDTH, FOLLOWED_HEIGHT = 8, 8


def _sw(value):
    """One 16-bit signed lane — every arithmetic step in $5c6e is a `.w` one and wraps."""
    return s16(value & 0xffff)


def _model_overlap_mask(image, actor, followed):
    read = lambda base, offset: _sw(leaf.u16(image, base + offset))   # noqa: E731
    x, y = read(actor, ACTOR_X), read(actor, ACTOR_Y)
    left = _sw(x - read(actor, HALF_WIDTH))
    right = _sw(x + read(actor, HALF_WIDTH))
    top = _sw(y - read(actor, SIZE_SECOND))
    bottom = y

    fx, fy = read(followed, ACTOR_X), read(followed, ACTOR_Y)
    sprite = read(followed, ACTOR_SPRITE)
    mask = 0

    if STRIKE_LO <= sprite <= STRIKE_HI:
        box_top = _sw(fy - STRIKE_BOX_TOP)
        if bottom >= box_top and top <= _sw(box_top + STRIKE_BOX_DEPTH):
            near, far = _sw(fx + STRIKE_BOX_NEAR), _sw(fx + STRIKE_BOX_FAR)
            if sprite > STRIKE_FLIP:
                near, far = _sw(near - STRIKE_BOX_FLIP), _sw(far - STRIKE_BOX_FLIP)
            if right >= near and left <= far:
                mask |= 1 << STRIKE_BIT

    if (_sw(fx - read(followed, HALF_WIDTH)) <= right
            and _sw(fy - read(followed, SIZE_SECOND)) <= bottom
            and _sw(fx + read(followed, HALF_WIDTH)) >= left
            and fy >= top):
        mask |= 1 << BODY_BIT

    if sprite in (POINT_LO, POINT_HI):
        point_x = _sw(fx + POINT_RIGHT)
        if sprite == POINT_HI:
            point_x = _sw(point_x - POINT_FLIP)
        point_y = _sw(fy - POINT_UP)
        if left <= point_x <= right and top <= point_y <= bottom:
            mask |= 1 << POINT_BIT
    return mask


# (name, followed x, followed y, followed sprite). The rows either side of every boundary the
# routine has: both ends of the strike band, both sides of the flip, the two point sprites and the
# one that is neither.
OVERLAP_CASES = [
    ("far-away", 0x0400, 0x0400, 0x0100),
    ("bodies-overlap", 0x0200, 0x0170, 0x0100),
    ("strike-band-low", 0x01f0, 0x0170, STRIKE_LO),
    ("strike-one-below-the-band", 0x01f0, 0x0170, STRIKE_LO - 1),
    ("strike-band-high", 0x01f0, 0x0170, STRIKE_HI),
    ("strike-one-above-the-band", 0x01f0, 0x0170, STRIKE_HI + 1),
    ("strike-at-the-flip", 0x01f0, 0x0170, STRIKE_FLIP),
    ("strike-past-the-flip", 0x01f0, 0x0170, STRIKE_FLIP + 1),
    ("strike-past-the-flip-reaches-left", 0x0230, 0x0170, STRIKE_FLIP + 1),
    ("strike-vertically-out", 0x01f0, 0x0300, STRIKE_LO),
    ("point-lo-inside", 0x01f0, 0x0170, POINT_LO),
    ("point-lo-outside", 0x0300, 0x0170, POINT_LO),
    ("point-hi-mirrored-out", 0x01f0, 0x0170, POINT_HI),
    ("point-hi-mirrored-in", 0x0220, 0x0170, POINT_HI),
    ("point-sprite-below-the-pair", 0x01f0, 0x0170, POINT_LO - 1),
    # ...and three rows sitting EXACTLY on an edge, so one pixel either way changes the answer.
    # Without them the box offsets are unpinned: the sweep's `strike-box-near` and `point-flip`
    # mutants both survived a table that only had rows well inside and well outside.
    ("strike-near-edge-exactly", 0x0209, 0x0170, STRIKE_LO),
    ("point-lo-on-the-right-edge", 0x01fa, 0x0170, POINT_LO),
    ("point-hi-on-the-left-edge", 0x0206, 0x0170, POINT_HI),
    # ...and the RIGHT edge too: the mirrored point has to be pinned from BOTH sides, since a
    # one-pixel shift only leaves the box on one of them (the sweep's second `point-flip` finding).
    ("point-hi-on-the-right-edge", 0x0226, 0x0170, POINT_HI),
]


def _overlap_pokes(salt, followed_x, followed_y, sprite, a32=0):
    followed = FOLLOWED_A32 if a32 else FOLLOWED_DEFAULT
    other = FOLLOWED_DEFAULT if a32 else FOLLOWED_A32
    return _tier_pokes(salt, leaf.overlay(
        _record_fields(ACTOR, {
            ACTOR_X: (OVERLAP_ACTOR_X, 2), ACTOR_Y: (OVERLAP_ACTOR_Y, 2),
            HALF_WIDTH: (OVERLAP_ACTOR_HALF_WIDTH, 2), SIZE_SECOND: (OVERLAP_ACTOR_HEIGHT, 2)}),
        _record_fields(followed, {
            ACTOR_X: (followed_x, 2), ACTOR_Y: (followed_y, 2), ACTOR_SPRITE: (sprite, 2),
            HALF_WIDTH: (FOLLOWED_HALF_WIDTH, 2), SIZE_SECOND: (FOLLOWED_HEIGHT, 2)}),
        # ...and the OTHER table's followed record put somewhere a port reading it would answer
        # differently, so the flag really is what selects.
        _record_fields(other, {
            ACTOR_X: (0x1000, 2), ACTOR_Y: (0x1000, 2), ACTOR_SPRITE: (0, 2),
            HALF_WIDTH: (0, 2), SIZE_SECOND: (0, 2)}),
        {FLAG_A32: word(0xffff if a32 else 0)}))


@pytest.mark.parametrize("a32", [0, 1], ids=["a32-clear", "a32-set"])
@pytest.mark.parametrize("case,followed_x,followed_y,sprite", OVERLAP_CASES,
                         ids=[c[0] for c in OVERLAP_CASES])
def test_the_overlap_mask_answers_three_independent_tests(case, followed_x, followed_y, sprite,
                                                          a32):
    what = f"actor_followed_overlap_mask {case} a32={a32}"
    pokes = _overlap_pokes(case_salt(what), followed_x, followed_y, sprite, a32)
    followed = FOLLOWED_A32 if a32 else FOLLOWED_DEFAULT
    expected = _model_overlap_mask(harness.make_image(pokes), ACTOR, followed)

    info = leaf.run("actor_followed_overlap_mask", _OVERLAP(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_followed_overlap_mask"))

    assert not program_writes(info), f"{what}: it wrote memory, which this routine does not"
    assert info["regs"]["d0"] & 0xffff == expected, (
        f"{what}: the ORIGINAL answered {info['regs']['d0'] & 0xffff:#x}, not the model's "
        f"{expected:#x}")
    assert info["ret"] == expected, (
        f"{what}: the reconstruction answered {info['ret']:#x} against {expected:#x}")


def test_the_overlap_cases_reach_every_bit_both_ways():
    """A truth table with a bit that is never set (or never clear) would pass whatever the port did
    to it, so the coverage the rows above buy is asserted rather than assumed."""
    seen = set()
    for case, followed_x, followed_y, sprite in OVERLAP_CASES:
        pokes = _overlap_pokes(case_salt(f"{case} a32=0"), followed_x, followed_y, sprite)
        mask = _model_overlap_mask(harness.make_image(pokes), ACTOR, FOLLOWED_DEFAULT)
        for bit in (STRIKE_BIT, BODY_BIT, POINT_BIT):
            seen.add((bit, bool(mask & (1 << bit))))
    for bit in (STRIKE_BIT, BODY_BIT, POINT_BIT):
        assert (bit, True) in seen and (bit, False) in seen, f"bit {bit} is never driven both ways"


# --- $23b6: did anything the player threw land ------------------------------------------------------
SHOT_ACTOR_X, SHOT_ACTOR_Y = 0x0300, 0x0280
SHOT_HALF_WIDTH, SHOT_HEIGHT = 0x10, 0x10
SHOT_SLOT = ALLOC_HIGH_FIRST + 2       # inside the high pool, with slots either side of it


def _shot_pokes(salt, flash=0, followed_x=None, shots=(), scan_from=ALLOC_HIGH_FIRST):
    """The actor, the followed record and the six records of the HIGH pool.

    Every slot the scan walks is stated: the ones a case does not name are FREE, and the slots BELOW
    the pool carry a record that would be a hit if the scan started there — so a walk that began at
    the wrong slot answers differently rather than answering the same by luck.
    """
    fields = _record_fields(ACTOR, {
        ACTOR_X: (SHOT_ACTOR_X, 2), ACTOR_Y: (SHOT_ACTOR_Y, 2),
        HALF_WIDTH: (SHOT_HALF_WIDTH, 2), SIZE_SECOND: (SHOT_HEIGHT, 2)})
    followed = FOLLOWED_DEFAULT
    fields.update(_record_fields(followed, {
        ACTOR_X: ((SHOT_ACTOR_X if followed_x is None else followed_x) & 0xffff, 2)}))

    # Every slot below the high pool: a live record that WOULD be a hit, to catch a scan that began
    # at the wrong one. (Slot 12 is the followed record and keeps the x above.)
    for slot in range(scan_from):
        if slot == FOLLOWED_SLOT:
            continue
        fields.update(_record_fields(_record(TABLE_DEFAULT, slot), {
            ACTOR_X: (SHOT_ACTOR_X, 2), ACTOR_Y: (SHOT_ACTOR_Y, 2), ACTOR_TYPE: (SHOT_TYPE_LO, 2),
            HALF_WIDTH: (SHOT_HALF_WIDTH, 2), SIZE_SECOND: (SHOT_HEIGHT, 2)}))
    for slot in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        record = _record(TABLE_DEFAULT, slot)
        shot = dict(shots).get(slot)
        if shot is None:
            fields.update(_record_fields(record, {ACTOR_X: (FREE_MARKER, 2)}))
            continue
        kind, x, y = shot
        fields.update(_record_fields(record, {
            ACTOR_X: (x & 0xffff, 2), ACTOR_Y: (y & 0xffff, 2), ACTOR_TYPE: (kind & 0xffff, 2),
            HALF_WIDTH: (SHOT_HALF_WIDTH, 2), SIZE_SECOND: (SHOT_HEIGHT, 2),
            FIELD_30: (0, 1)}))
    return _tier_pokes(salt, leaf.overlay(fields, {FLASH_TIMER: word(flash)}))


FLASH_CASES = [
    ("flash-off-and-close", 0, SHOT_ACTOR_X, False),
    ("flash-on-and-close", 1, SHOT_ACTOR_X, True),
    ("flash-on-at-the-reach", 0xffff, SHOT_ACTOR_X + FLASH_REACH, True),
    ("flash-on-past-the-reach", 1, SHOT_ACTOR_X + FLASH_REACH + 1, False),
]


@pytest.mark.parametrize("case,flash,followed_x,hit", FLASH_CASES, ids=[c[0] for c in FLASH_CASES])
def test_the_screen_flash_hits_every_actor_within_reach_of_the_followed_record(case, flash,
                                                                               followed_x, hit):
    """The first way in, and the one with no projectile at all: while WB_FLASH_TIMER runs, being
    within WB_ACTOR_FLASH_REACH of the followed record horizontally IS the hit. Nothing is consumed
    and nothing is written on this arm, whichever way it answers."""
    what = f"actor_hit_by_player_shot {case}"
    pokes = _shot_pokes(case_salt(what), flash=flash, followed_x=followed_x)

    info = leaf.run("actor_hit_by_player_shot", _HIT_BY_SHOT(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_hit_by_player_shot",
                                   extra=WITHIN_INSNS + ALLOC_HIGH_SLOTS * 4))
    expected = ACTOR_HIT if hit else ACTOR_NOT_HIT
    assert not program_writes(info), f"{what}: the flash arm wrote memory, which it does not"
    assert info["regs"]["d7"] & 0xffff == expected, (
        f"{what}: the ORIGINAL answered d7={info['regs']['d7'] & 0xffff:#x}, not {expected:#x}")
    assert info["ret"] == expected, f"{what}: the reconstruction answered {info['ret']:#x}"


# (name, {slot: (type, x, y)}, hit, the slot the scan consumes)
NEAR = (SHOT_ACTOR_X, SHOT_ACTOR_Y)
FAR = (SHOT_ACTOR_X + 2 * SHOT_HALF_WIDTH + 1, SHOT_ACTOR_Y)
SHOT_CASES = [
    ("empty-pool", {}, False, None),
    ("type-lo-overlapping", {SHOT_SLOT: (SHOT_TYPE_LO, *NEAR)}, True, SHOT_SLOT),
    ("type-hi-overlapping", {SHOT_SLOT: (SHOT_TYPE_HI, *NEAR)}, True, SHOT_SLOT),
    ("type-kept-overlapping", {SHOT_SLOT: (SHOT_TYPE_KEPT, *NEAR)}, True, SHOT_SLOT),
    ("one-type-below-the-band", {SHOT_SLOT: (SHOT_TYPE_LO - 1, *NEAR)}, False, None),
    ("one-type-above-the-band", {SHOT_SLOT: (SHOT_TYPE_HI + 1, *NEAR)}, False, None),
    ("horizontally-out", {SHOT_SLOT: (SHOT_TYPE_LO, *FAR)}, False, None),
    ("at-the-horizontal-reach",
     {SHOT_SLOT: (SHOT_TYPE_LO, SHOT_ACTOR_X + 2 * SHOT_HALF_WIDTH, SHOT_ACTOR_Y)},
     True, SHOT_SLOT),
    ("vertically-out",
     {SHOT_SLOT: (SHOT_TYPE_LO, SHOT_ACTOR_X, SHOT_ACTOR_Y + 2 * SHOT_HEIGHT + 1)}, False, None),
    ("negative-distance-is-taken-absolute",
     {SHOT_SLOT: (SHOT_TYPE_LO, SHOT_ACTOR_X - 2 * SHOT_HALF_WIDTH, SHOT_ACTOR_Y)},
     True, SHOT_SLOT),
    ("the-first-of-two-wins",
     {ALLOC_HIGH_FIRST: (SHOT_TYPE_LO, *NEAR), SHOT_SLOT: (SHOT_TYPE_KEPT, *NEAR)},
     True, ALLOC_HIGH_FIRST),
    ("the-last-slot-is-reached",
     {ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS - 1: (SHOT_TYPE_LO, *NEAR)},
     True, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS - 1),
    # A FREE slot whose leftover type and footprint would BOTH match: the only thing between it and
    # a spurious hit is `cmpi.w #$ffbe,(a1) / beq`. Without this row that test can be deleted and
    # the battery stays green (the sweep's finding).
    ("a-free-slot-that-would-otherwise-match", {SHOT_SLOT: (SHOT_TYPE_LO, FREE_MARKER, SHOT_ACTOR_Y)},
     False, None),
]


@pytest.mark.parametrize("case,shots,hit,consumed", SHOT_CASES, ids=[c[0] for c in SHOT_CASES])
def test_the_scan_consumes_the_first_overlapping_shot_of_the_high_pool(case, shots, hit, consumed):
    """The second way in. The scan is SIX records from the high pool's own first slot, the type band
    is inclusive at both ends, and the footprint test sums the two records' half extents on each
    axis with `neg.w` on the negative side. What it finds it FREES — except
    WB_ACTOR_SHOT_TYPE_KEPT, which is marked and left alive."""
    what = f"actor_hit_by_player_shot {case}"
    pokes = _shot_pokes(case_salt(what), shots=shots)

    expected = {}
    if consumed is not None:
        record = _record(TABLE_DEFAULT, consumed)
        if shots[consumed][0] == SHOT_TYPE_KEPT:
            expected[record + FIELD_30] = SHOT_HIT_MARK
        else:
            _put(expected, record + ACTOR_X, FREE_MARKER)

    info = leaf.run("actor_hit_by_player_shot", _HIT_BY_SHOT(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_hit_by_player_shot",
                                   extra=WITHIN_INSNS + ALLOC_HIGH_SLOTS * 24))
    _assert_writes(info, expected, what)
    answer = ACTOR_HIT if hit else ACTOR_NOT_HIT
    assert info["regs"]["d7"] & 0xffff == answer, (
        f"{what}: the ORIGINAL answered d7={info['regs']['d7'] & 0xffff:#x}, not {answer:#x}")
    assert info["ret"] == answer, f"{what}: the reconstruction answered {info['ret']:#x}"


def test_the_double_write_the_5160_stepper_makes_is_unobservable():
    """A MUTATION SURVIVOR, named here rather than left silent.

    $6872 commits `addq.b #2,18(a0)` and THEN, on the terminator, `clr.b 18(a0)` — two writes to one
    byte on the wrapping path. Reordering them into an if/else leaves the same final byte, and the
    oracle's write ledger is address-keyed (the last value wins), so no differential can separate
    the two. The reconstruction spells the original's order anyway; this states why nothing checks
    it, and what a surface that could would have to be (an ORDERED write ledger, registered in
    ../STATUS.md).
    """
    entry = ENTRY_BYTES["actor_relaunch_and_anim_5160"]
    advance = addq_b_d16(ANIM_FRAME_BYTES, A0, FIELD_18)
    reset = clr_b_d16(A0, FIELD_18)
    assert entry.index(advance) < entry.index(reset), (
        "the original advances the cursor before it reads the terminator; the reconstruction does "
        "the same, and only this ordering claim says so")


def test_a_free_slot_is_skipped_even_when_it_would_otherwise_hit():
    """THE FREE-MARKER GUARD, driven. A free record's x IS the marker, so it can only overlap an
    actor standing at that same coordinate — which is why an ordinary row leaves `cmpi.w #$ffbe,(a1)
    / beq` deletable. This puts the actor exactly there: the leftover type is in band and both
    footprints coincide, so the guard is the ONLY thing between it and a reported hit."""
    what = "actor_hit_by_player_shot a free slot at the actor's own x"
    actor_x = FREE_MARKER
    fields = _record_fields(ACTOR, {
        ACTOR_X: (actor_x, 2), ACTOR_Y: (SHOT_ACTOR_Y, 2),
        HALF_WIDTH: (SHOT_HALF_WIDTH, 2), SIZE_SECOND: (SHOT_HEIGHT, 2)})
    fields.update(_record_fields(FOLLOWED_DEFAULT, {ACTOR_X: (actor_x, 2)}))
    for slot in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        fields.update(_record_fields(_record(TABLE_DEFAULT, slot), {
            ACTOR_X: (FREE_MARKER, 2), ACTOR_Y: (SHOT_ACTOR_Y, 2),
            ACTOR_TYPE: (SHOT_TYPE_LO, 2), HALF_WIDTH: (SHOT_HALF_WIDTH, 2),
            SIZE_SECOND: (SHOT_HEIGHT, 2), FIELD_30: (0, 1)}))
    pokes = _tier_pokes(case_salt(what), leaf.overlay(fields, {FLASH_TIMER: word(0)}))

    info = leaf.run("actor_hit_by_player_shot", _HIT_BY_SHOT(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("actor_hit_by_player_shot",
                                   extra=WITHIN_INSNS + ALLOC_HIGH_SLOTS * 24))
    assert not program_writes(info), f"{what}: a free record was consumed"
    assert info["regs"]["d7"] & 0xffff == ACTOR_NOT_HIT
    assert info["ret"] == ACTOR_NOT_HIT, f"{what}: the reconstruction answered {info['ret']:#x}"


def test_the_homing_steps_vertical_half_reads_after_the_horizontal_store():
    """$6840 stores x and only THEN reads 2(a1) and 2(a0), so a caller whose two records overlap by
    two bytes sees the first store in the second comparison. `actor = followed + 2` aliases the
    actor's x word onto the followed record's y word exactly, which is the one arrangement that can
    tell the original's order from the tidier one."""
    step = STEP_PIXELS
    followed = FOLLOWED_DEFAULT
    actor = followed + WORD_BYTES                    # actor.x IS followed.y
    followed_y = 0x0200
    # The actor's y sits in the WINDOW the two readings disagree over: the ride height off the
    # PRE-store followed y is followed_y - $10, off the POST-store one it is `step` lower, and a y
    # between them takes the compare one way in each. Outside that window the reorder is invisible,
    # which is why an ordinary seed leaves it unpinned.
    actor_y = followed_y - PLATFORM_TOP
    what = "actor_step_toward_followed with the two records overlapped"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(followed, {ACTOR_X: (0x0100, 2), ACTOR_Y: (followed_y, 2)}),
        _record_fields(actor, {ACTOR_Y: (actor_y, 2)})))

    expected = {}
    # The x store lands on the followed record's y word, and the vertical compare then reads it
    # back: `actor.x - step` against `actor.y`, which is one lower than the pre-store reading.
    _put(expected, actor + ACTOR_X, followed_y - step)
    _put(expected, actor + ACTOR_Y, actor_y - step)

    info = leaf.run("actor_step_toward_followed", _TOWARD(actor, step), merge_bands(expected),
                    what, regs={"a0": actor, "d7": step, "_pokes": pokes},
                    max_insns=_cap("actor_step_toward_followed", extra=FOLLOWED_INSNS))
    _assert_writes(info, expected, what)


def test_the_scan_starts_at_the_high_pools_own_first_slot():
    """`lea 416(a1),a1` == WB_ACTOR_ALLOC_HIGH_FIRST records, which is what makes the routine about
    the pool the player's own projectiles are allocated out of."""
    assert ALLOC_HIGH_FIRST * RECORD_BYTES == 416


# --- $2f22, $2fce, $2fe8: the three that probe the collision map ---------------------------------------
# The maps are seeded by the battery that owns them (test_map.py), with the DEFAULT map's CELLS then
# forced to one tile so the probe's verdict is a property of the case rather than of a keyed byte.
import test_map as mp                                            # noqa: E402

MAP_CELL_BAND = mp.map_window(mp.DEFAULT_STRIDE) - mp.MAP_CELLS
STEP_ACTOR_X = 0x0100
STEP_HALF_WIDTH = 8
STEP_PIXELS = 4
# $1170 clamps the right step at WB_BG_SCROLL_LIMIT_X + WB_BG_SCROLL_LIMIT_BIAS, so the limit is
# seeded well past the probe: this battery is about the DIRECTION, and test_map.py owns the clamp.
STEP_SCROLL_LIMIT = 0x0400
# A type that is NOT WB_ACTOR_TYPE_PLAYER, so the probes' retry arm does not also clear 22(a0).
STEP_ACTOR_TYPE = 3


def _map_step_pokes(salt, tile, flags, followed_x):
    return _tier_pokes(salt, leaf.overlay(
        mp.map_pokes(salt),
        {mp.MAP_DEFAULT + mp.MAP_CELLS: bytes([tile]) * MAP_CELL_BAND,
         mp.SCROLL_LIMIT_X: word(STEP_SCROLL_LIMIT)},
        _record_fields(ACTOR, {
            ACTOR_X: (STEP_ACTOR_X, 2), ACTOR_Y: (mp.DEFAULT_PROBE_Y, 2),
            HALF_WIDTH: (STEP_HALF_WIDTH, 2), ACTOR_TYPE: (STEP_ACTOR_TYPE, 2),
            ACTOR_FLAGS: (flags, 1)}),
        _record_fields(FOLLOWED_DEFAULT, {ACTOR_X: (followed_x & 0xffff, 2)})))


CLEAR_TILE = 0


@pytest.mark.parametrize("side", [0, 1 << SIDE_BIT], ids=["side-clear", "side-set"])
def test_the_facing_step_walks_the_way_the_side_bit_points(side):
    """SET means the followed record is to the actor's LEFT ($67c2), and this steps that way — over
    a clear map, so the probe commits the whole of d7 and the side bit is left alone."""
    what = f"actor_step_facing side={side}"
    pokes = _map_step_pokes(case_salt(what), CLEAR_TILE, side, STEP_ACTOR_X)
    moved = STEP_ACTOR_X - STEP_PIXELS if side else STEP_ACTOR_X + STEP_PIXELS
    expected = {}
    _put(expected, ACTOR + ACTOR_X, moved)

    info = leaf.run("actor_step_facing", _STEP_FACING(ACTOR, STEP_PIXELS), merge_bands(expected),
                    what, regs={"a0": ACTOR, "d7": STEP_PIXELS, "_pokes": pokes},
                    max_insns=_cap("actor_step_facing", extra=MAP_PROBE_INSNS))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("side", [0, 1 << SIDE_BIT], ids=["side-clear", "side-set"])
def test_a_blocked_step_flips_the_side_bit(side):
    """Every cell a block, so the probe backs off to nothing and reports WB_ACTOR_STEP_BLOCKED —
    which is the ONLY thing that makes this routine touch the flag byte."""
    what = f"actor_step_facing blocked side={side}"
    pokes = _map_step_pokes(case_salt(what), mp.TILE_BLOCK, side, STEP_ACTOR_X)
    expected = {ACTOR + ACTOR_FLAGS: side ^ (1 << SIDE_BIT)}
    _put(expected, ACTOR + ACTOR_X, STEP_ACTOR_X)

    info = leaf.run("actor_step_facing", _STEP_FACING(ACTOR, STEP_PIXELS), merge_bands(expected),
                    what, regs={"a0": ACTOR, "d7": STEP_PIXELS, "_pokes": pokes},
                    max_insns=_cap("actor_step_facing", extra=MAP_PROBE_INSNS))
    _assert_writes(info, expected, what)


# (name, the followed record's x, the side bit `actor_set_side_flag` will leave, the way each of the
# two routines then steps). $67c2 raises the bit while the actor is strictly to the RIGHT.
FACE_CASES = [
    ("followed-to-the-left", STEP_ACTOR_X - 0x40, 1 << SIDE_BIT, -STEP_PIXELS, +STEP_PIXELS),
    ("followed-to-the-right", STEP_ACTOR_X + 0x40, 0, +STEP_PIXELS, -STEP_PIXELS),
]


@pytest.mark.parametrize("case,followed_x,side,toward,away", FACE_CASES,
                         ids=[c[0] for c in FACE_CASES])
def test_the_two_face_and_step_routines_walk_opposite_ways(case, followed_x, side, toward, away):
    """THE PLATE CORRECTION, driven: given the same followed record, $2fce walks TOWARD it and
    $2fe8 walks AWAY. Both set the flag first, so the flag byte is in both write sets."""
    for name, glue, delta, step in (("actor_face_and_step_toward", _FACE_TOWARD, toward,
                                     STEP_PIXELS),
                                    ("actor_face_and_step_away4", _FACE_AWAY, away,
                                     STEP_AWAY_PIXELS)):
        what = f"{name} {case}"
        pokes = _map_step_pokes(case_salt(what), CLEAR_TILE, 0, followed_x)
        expected = {ACTOR + ACTOR_FLAGS: side}
        _put(expected, ACTOR + ACTOR_X, STEP_ACTOR_X + delta)

        args = (ACTOR, step) if name.endswith("toward") else (ACTOR,)
        regs = {"a0": ACTOR, "d7": step, "_pokes": pokes}
        info = leaf.run(name, glue(*args), merge_bands(expected), what, regs=regs,
                        max_insns=_cap(name, extra=MAP_PROBE_INSNS + SIDE_FLAG_INSNS))
        _assert_writes(info, expected, what)


def test_the_step_away_routine_ignores_its_callers_d7():
    """`move.w #$4,d7` is the FIRST instruction, so whatever the handler had in d7 is discarded —
    which is what makes WB_ACTOR_STEP_AWAY_PIXELS a property of the routine and not of its caller."""
    what = "actor_face_and_step_away4 with a caller's d7"
    pokes = _map_step_pokes(case_salt(what), CLEAR_TILE, 0, STEP_ACTOR_X + 0x40)
    expected = {ACTOR + ACTOR_FLAGS: 0}
    _put(expected, ACTOR + ACTOR_X, STEP_ACTOR_X - STEP_AWAY_PIXELS)

    info = leaf.run("actor_face_and_step_away4", _FACE_AWAY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "d7": 0x40, "_pokes": pokes},
                    max_insns=_cap("actor_face_and_step_away4",
                                   extra=MAP_PROBE_INSNS + SIDE_FLAG_INSNS))
    _assert_writes(info, expected, what)
