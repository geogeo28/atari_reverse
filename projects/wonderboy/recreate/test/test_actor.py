"""Differential test for src/actor.c — the followed actor's record, the two tests above it, and the
two passes that project actor records into screen coordinates.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and bounds (or states exactly) the original's write set.

THREE THINGS SHAPE THIS BATTERY.

  * THE WHOLE OUTPUT OF `$67e0` IS A REGISTER. It writes no memory at all, so a byte-for-byte diff
    proves nothing about it: every case compares the ORACLE's a1 against the record the case names
    AND against the reconstruction's return value, which is the only thing that pins it.
  * THE TWO MODE FLAGS ARE READ TWO DIFFERENT WAYS. `$67e0` tests WB_STATE_FLAG_A32 with `bne` and
    `$8e66` tests the same word with `bpl`; the image only ever writes it $0000 or $ffff, so a case
    seeding a SMALL POSITIVE word is the only thing that can tell the two readings apart. There is
    one per routine, and they are the reason the reconstruction spells each test as the original
    does rather than picking one.
  * NOTHING IS SEEDED FROM A CONSTANT THE CODE ALSO USES. The three actor tables and the screen
    array are zero in a fresh image, so every case fills the whole region ADDRESS-KEYED, with a
    record's worth of margin either side: a walk that ran one record long, took the wrong stride or
    read the wrong table lands on bytes that are wrong FOR WHERE THEY WERE WRITTEN rather than on
    zeros.

KNOWINGLY NOT PINNED
  * THE REGISTERS THE TWO PROJECTIONS LEAVE BEHIND. Both walk out with a0 one record past the last
    one they read and a1 at the end of the screen array; their one caller (game_main_loop) reloads
    everything before its next `jsr`, so the C returns neither. The cases below assert the ORACLE's
    a0/a1 against the model, which documents them without pinning the reconstruction.
  * WHAT THE TWO MODE FLAGS SELECT. ../names.txt names them for their mechanism; that one of the
    three tables is "the current level's actors" is not established here or anywhere else.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, RTS, add_w_dn_dn, addq_b_d16, backward_branch, branch,
                  branch_over, bsr_w, case_salt, cmpi_b_dn, dbf, dbf_over, keyed_block, lea_abs_l,
                  lea_d16, longword, lsl_w_imm_dn, merge_bands, move_b_d16_dn, move_l_imm_abs_l,
                  move_w_abs_l_dn, move_w_imm_dn, move_w_ind_dn, movea_l_abs_l, moveq_0_dn, opcode,
                  program_writes, s16, sub_w_dn_dn, subi_w_dn, tst_w_abs_w, u16, word)
from layout import wb

import loader   # noqa: E402  (harness puts the kit's oracle on sys.path)

# --- the globals and the geometry, from the header both languages read ---------------------------
FLAG_A30 = wb("STATE_FLAG_A30")
FLAG_A32 = wb("STATE_FLAG_A32")
TABLE_A30 = wb("ACTOR_TABLE_A30")
TABLE_A32 = wb("ACTOR_TABLE_A32")
TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
RECORD_BYTES = wb("ACTOR_RECORD_BYTES")
FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
FOLLOWED_A32 = wb("ACTOR_FOLLOWED_A32")
ACTOR_X = wb("ACTOR_X")
ACTOR_Y = wb("ACTOR_Y")
ACTOR_SPRITE = wb("ACTOR_SPRITE")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
SIDE_BIT = wb("ACTOR_FLAG_SIDE_BIT")
FLICKER_BIT = wb("ACTOR_FLAG_FLICKER_BIT")
OUT_OF_REACH = wb("ACTOR_OUT_OF_REACH")
SCREEN_RECORDS = wb("ACTOR_SCREEN_RECORDS")
SCREEN_RECORDS_END = wb("ACTOR_SCREEN_RECORDS_END")
SCREEN_RECORD_BYTES = wb("ACTOR_SCREEN_RECORD_BYTES")
SCREEN_RECORD_COUNT = wb("ACTOR_SCREEN_RECORD_COUNT")
FOLLOWED_SLOT = wb("ACTOR_FOLLOWED_SLOT")
SCREEN_X = wb("ACTOR_SCREEN_X")
SCREEN_Y = wb("ACTOR_SCREEN_Y")
SCREEN_SPRITE = wb("ACTOR_SCREEN_SPRITE")
SCREEN_X_BIAS = wb("ACTOR_SCREEN_X_BIAS")
SCREEN_Y_BIAS = wb("ACTOR_SCREEN_Y_BIAS")
SPRITE_HIDDEN = wb("ACTOR_SPRITE_HIDDEN")
FRAME_TOGGLE = wb("FRAME_TOGGLE")
FOLLOW_X = wb("SCROLL_FOLLOW_X")
POS_X = wb("BG_SCROLL_POS_X")
POS_Y = wb("BG_SCROLL_POS_Y")

# ...and the lifecycle's own
FREE_MARKER = wb("ACTOR_FREE_MARKER")
ACTOR_TYPE = wb("ACTOR_TYPE")
FLAGS2 = wb("ACTOR_FLAGS2")
SPEED = wb("ACTOR_SPEED")
FIELD_18 = wb("ACTOR_FIELD_18")
TEMPLATE_SLOT = wb("ACTOR_TEMPLATE_SLOT")
FIELD_30 = wb("ACTOR_FIELD_30")
FIELD_31 = wb("ACTOR_FIELD_31")
HALF_WIDTH = wb("ACTOR_HALF_WIDTH")
SIZE_SECOND = wb("ACTOR_SIZE_SECOND")
MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
FALLING_BIT = wb("ACTOR_FLAG_FALLING_BIT")
SPAWNED_BIT = wb("ACTOR_FLAGS2_SPAWNED_BIT")
FALL_SPEED_MAX = wb("ACTOR_FALL_SPEED_MAX")
ALLOC_LOW_FIRST = wb("ACTOR_ALLOC_LOW_FIRST")
ALLOC_LOW_SLOTS = wb("ACTOR_ALLOC_LOW_SLOTS")
ALLOC_HIGH_FIRST = wb("ACTOR_ALLOC_HIGH_FIRST")
ALLOC_HIGH_SLOTS = wb("ACTOR_ALLOC_HIGH_SLOTS")
ALLOC_NONE = wb("ACTOR_ALLOC_NONE")
SPAWN_TYPE = wb("SPAWN_TYPE")
SPAWN_SIZE = wb("SPAWN_SIZE")
SPAWN_X = wb("SPAWN_X")
SPAWN_Y = wb("SPAWN_Y")
SPAWN_RECORD_BYTES = wb("SPAWN_RECORD_BYTES")
SIZE_TABLE = wb("ACTOR_SIZE_TABLE")
TEMPLATE_SLOT_SHIFT = wb("ACTOR_TEMPLATE_SLOT_SHIFT")
TABLE_PTR = wb("TABLE_PTR_21E8C")

WORD_LEN = 2
LONGWORD_LEN = 4
TABLE_BYTES = SCREEN_RECORD_COUNT * RECORD_BYTES

# The routines are straight-line bar one loop of nineteen records; the cap is that loop's own
# geometry with room for the entry and the tail, so a case that ran away fails loudly.
LIST_INSN_CAP = 64 * SCREEN_RECORD_COUNT

# --- register numbers, and the opcodes only this battery spells -----------------------------------
A0, A1, A2, A6 = 0, 1, 2, 6
D0, D1, D2, D7 = 0, 1, 2, 7

BNE_W, BEQ_W, BPL_W, BLE_W, BLT_W, BGT_W, BRA_W = (0x6600, 0x6700, 0x6a00, 0x6f00,
                                                   0x6d00, 0x6e00, 0x6000)
# A branch is ONE opcode: a zero displacement byte means the word form follows, any other byte means
# the short form is the whole instruction. BNE_S and BSR_S name that second reading of the same two
# numbers — $8e66 closes its loop short and $67f8 calls short, where their neighbours spell both long.
BNE_S = BNE_W
BSR_S = 0x6100
BYTE_MASK = 0xff


def _bsr_s(here, target):
    """`bsr.s target` as assembled AT ``here`` — $67f8 spells its call short where $67c2 spells the
    same call long, so the two encodings are part of what the pins say."""
    displacement = target - (here + WORD_LEN)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bsr.s` byte displacement"
    return opcode(BSR_S | (displacement & BYTE_MASK))


def jsr_abs_w(addr):
    return opcode(0x4eb8) + word(addr)


def movea_l_an_an(destination, source):
    return opcode(0x2048 | (destination << 9) | source)


def move_w_dn_postinc(reg, destination):
    return opcode(0x30c0 | (destination << 9) | reg)


def move_w_imm_ind(reg, value):
    return opcode(0x30bc | (reg << 9)) + word(value)


def move_w_d16_ind(source, displacement, destination):
    """`move.w d16(As),(Ad)` — the projection's sprite arm."""
    return opcode(0x3080 | (destination << 9) | 0x28 | source) + word(displacement)


def cmp_w_dn_dn(destination, source):
    return opcode(0xb040 | (destination << 9) | source)


def clr_w_dn(reg):
    return opcode(0x4240 | reg)


def cmpa_l_imm(reg, value):
    return opcode(0xb1fc | (reg << 9)) + longword(value)


def bit_op_d16(op, bit, reg, displacement):
    """`bset`/`bclr`/`btst #n,d16(An)` — a BYTE operation on memory, whatever the register form is."""
    return opcode(op | 0x28 | reg) + word(bit) + word(displacement)


BSET_IMM, BCLR_IMM, BTST_IMM = 0x08c0, 0x0880, 0x0800


# ...and the encodings only the LIFECYCLE routines use.
def move_l_imm_postinc(reg, value):
    return opcode(0x20fc | (reg << 9)) + longword(value)


def clr_l_postinc(reg):
    return opcode(0x4298 | reg)


def cmpi_w_ind(reg, value):
    return opcode(0x0c50 | reg) + word(value)


def movea_l_imm(reg, value):
    return opcode(0x207c | (reg << 9)) + longword(value)


def clr_w_d16(reg, displacement):
    return opcode(0x4268 | reg) + word(displacement)


def clr_b_d16(reg, displacement):
    return opcode(0x4228 | reg) + word(displacement)


def move_w_d16_d16(source, source_displacement, destination, destination_displacement):
    """`move.w d16(As),d16(Ad)` — how the spawn copies a template field into a record.

    The destination's register and mode sit in the HIGH half of the opcode word but its extension
    word comes SECOND: a `move` emits the source EA's extensions first. The spawn's own arm copying
    14(a0) to 14(a1) has the two displacements equal and so cannot tell the order apart; the two
    that copy 26(a0) to 2(a1) and 12(a0) to 4(a1) can, and the entry pin is where they do.
    """
    return (opcode(0x3168 | (destination << 9) | source)
            + word(source_displacement) + word(destination_displacement))


def cmp_w_imm_dn(reg, value):
    return opcode(0xb07c | (reg << 9)) + word(value)


def move_l_indexed_d16(base, index, destination, displacement):
    """`move.l (0,Ab,Dn.l),d16(Ad)` — the size table's lookup, with a LONGWORD index."""
    return (opcode(0x2170 | (destination << 9) | base) + word((index << 12) | 0x800)
            + word(displacement))


def move_l_an_dn(reg, source):
    return opcode(0x2008 | (reg << 9) | source)


def move_l_abs_l_dn(reg, addr):
    return opcode(0x2039 | (reg << 9)) + longword(addr)


def sub_l_dn_dn(destination, source):
    return opcode(0x9080 | (destination << 9) | source)


def asr_l_imm_dn(count, reg):
    return opcode(0xe080 | ((count & 7) << 9) | reg)


def move_b_dn_d16(reg, base, displacement):
    return opcode(0x1140 | (base << 9) | reg) + word(displacement)


def bra_s_back(spanned_bytes):
    """`bra.s` back over ``spanned_bytes`` — the spawn's own-size arm rejoins the common tail.

    BRA_W and BRA_S are the same opcode word read two ways, exactly as BNE_S is above."""
    displacement = -(spanned_bytes + BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bra.s` byte displacement"
    return opcode(BRA_W | (displacement & BYTE_MASK))


# --- the entry pins -------------------------------------------------------------------------------
# Each is the routine's WHOLE body, assembled from the header's constants and the geometry, so a
# wrong address, bias or displacement fails at its own entry instead of surfacing as a diff.

def _followed_record_entry():
    default = lea_abs_l(A1, FOLLOWED_DEFAULT) + RTS
    return (tst_w_abs_w(FLAG_A32) + branch(BNE_W, default) + default
            + lea_abs_l(A1, FOLLOWED_A32) + RTS)


def _side_flag_entry():
    here = leaf.entry_of("actor_set_side_flag")
    raise_bit = bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS) + RTS
    return (bsr_w(here, leaf.entry_of("followed_actor_record"))
            + move_w_ind_dn(D0, A1, ACTOR_X)
            + move_w_ind_dn(D1, A0, ACTOR_X)
            + cmp_w_dn_dn(D1, D0)
            + branch(BLE_W, raise_bit) + raise_bit
            + bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS) + RTS)


def _within_entry():
    here = leaf.entry_of("actor_followed_x_within")
    out_of_reach = move_w_imm_dn(D0, OUT_OF_REACH) + RTS
    in_reach = clr_w_dn(D0) + RTS
    followed_ahead = (add_w_dn_dn(D1, D0) + cmp_w_dn_dn(D2, D1)
                      + branch(BGT_W, in_reach) + in_reach)
    followed_behind = (add_w_dn_dn(D2, D0) + cmp_w_dn_dn(D2, D1)
                       + branch(BLT_W, in_reach, followed_ahead) + in_reach)
    return (_bsr_s(here, leaf.entry_of("followed_actor_record"))
            + move_w_ind_dn(D1, A0, ACTOR_X)
            + move_w_ind_dn(D2, A1, ACTOR_X)
            + cmp_w_dn_dn(D2, D1)
            + branch(BGT_W, followed_behind) + followed_behind
            + followed_ahead + out_of_reach)


def _projection_block():
    """The sixty-eight bytes $8dfe and $8e66 spell identically: one actor record into one screen
    record, ending with both cursors moved on. Assembled once, which is the same claim src/actor.c's
    `project_actor` makes — and pinned twice, at both entries."""
    # The destination cursor has already walked the two words the post-increment stores moved it,
    # so its `lea` carries only the rest of a record — which is what says the sprite word is the
    # THIRD one and not a fourth address the routine skips to.
    step = lea_d16(A0, RECORD_BYTES) + lea_d16(A1, SCREEN_RECORD_BYTES - 2 * WORD_LEN)
    hidden = move_w_imm_ind(A1, SPRITE_HIDDEN) + step
    visible = move_w_d16_ind(A0, ACTOR_SPRITE, A1) + step
    return (move_w_ind_dn(D2, A0, ACTOR_X) + subi_w_dn(D2, SCREEN_X_BIAS) + sub_w_dn_dn(D2, D0)
            + move_w_dn_postinc(D2, A1)
            + move_w_ind_dn(D2, A0, ACTOR_Y) + subi_w_dn(D2, SCREEN_Y_BIAS) + sub_w_dn_dn(D2, D1)
            + move_w_dn_postinc(D2, A1)
            + bit_op_d16(BTST_IMM, FLICKER_BIT, A0, ACTOR_FLAGS)
            + branch(BEQ_W, tst_w_abs_w(FRAME_TOGGLE), branch(BEQ_W, visible), hidden,
                     branch(BRA_W, visible))
            + tst_w_abs_w(FRAME_TOGGLE) + branch(BEQ_W, hidden, branch(BRA_W, visible))
            + hidden + branch(BRA_W, visible)
            + visible)


def _project_followed_entry():
    return (tst_w_abs_w(FLAG_A30) + branch(BPL_W, RTS) + RTS
            + jsr_abs_w(leaf.entry_of("followed_actor_record"))
            + movea_l_an_an(A0, A1)
            + lea_abs_l(A1, FOLLOW_X)
            + move_w_abs_l_dn(D0, POS_X) + move_w_abs_l_dn(D1, POS_Y)
            + _projection_block() + RTS)


def _project_list_entry():
    publish_a32 = move_l_imm_abs_l(TABLE_A32, TABLE_SELECTED)
    publish_default = move_l_imm_abs_l(TABLE_DEFAULT, TABLE_SELECTED)
    a32_arm = (tst_w_abs_w(FLAG_A32) + branch(BPL_W, publish_a32, branch(BRA_W, publish_default))
               + publish_a32 + branch(BRA_W, publish_default) + publish_default)
    body = _projection_block()
    tail = cmpa_l_imm(A1, SCREEN_RECORDS_END)
    return (tst_w_abs_w(FLAG_A30)
            + branch(BPL_W, move_l_imm_abs_l(TABLE_A30, TABLE_SELECTED), branch(BRA_W, a32_arm))
            + move_l_imm_abs_l(TABLE_A30, TABLE_SELECTED) + branch(BRA_W, a32_arm)
            + a32_arm
            + movea_l_abs_l(A0, TABLE_SELECTED) + lea_abs_l(A1, SCREEN_RECORDS)
            + move_w_abs_l_dn(D0, POS_X) + move_w_abs_l_dn(D1, POS_Y)
            + body + tail
            + opcode(BNE_S | (backward_branch(len(body) + len(tail))[1] & BYTE_MASK))
            + RTS)


def _table_reset_entry():
    """A `move.l` of the marker plus enough `clr.l`s to finish the record — the count comes out of
    WB_ACTOR_RECORD_BYTES, so a record that changed size fails here rather than under-clearing."""
    record = (move_l_imm_postinc(A0, FREE_MARKER << 16)
              + clr_l_postinc(A0) * (RECORD_BYTES // LONGWORD_LEN - 1))
    return (move_w_imm_dn(D0, SCREEN_RECORD_COUNT - 1) + record + dbf(D0, record) + RTS)


def _mark_free_entry():
    record = move_w_imm_ind(A6, FREE_MARKER) + lea_d16(A6, RECORD_BYTES)
    return record + dbf(D7, record) + RTS


def _alloc_entry(first, slots):
    """The thirty-eight bytes both allocators spell, parametrised by the two operands that differ.
    src/actor.c makes the same claim by having one function behind both names, and
    `test_the_two_allocators_are_one_routine_with_two_operands` is what makes that legitimate."""
    probe = cmpi_w_ind(A1, FREE_MARKER)
    step = lea_d16(A1, RECORD_BYTES)
    close = dbf_over(D0, 0)          # the loop's own `dbf`; only its LENGTH is wanted here
    empty = movea_l_imm(A1, ALLOC_NONE)
    body = probe + branch_over(BEQ_W, len(step) + len(close) + len(empty)) + step
    return (movea_l_abs_l(A1, TABLE_SELECTED)
            + lea_d16(A1, first * RECORD_BYTES)
            + move_w_imm_dn(D0, slots - 1)
            + body + dbf(D0, body)
            + empty + RTS)


# `cmp.w #$36/$37/$38/$3b/$3c,d0`, in the original's own order: the types whose footprint comes
# out of the TEMPLATE rather than out of WB_ACTOR_SIZE_TABLE. src/actor.c carries the same list.
SPAWN_TYPES_WITH_OWN_SIZE = (0x36, 0x37, 0x38, 0x3b, 0x3c)
SPAWN_SIZE_SHIFT = 2       # `lsl.w #2`: WB_ACTOR_SIZE_TABLE is one LONGWORD per type


def _spawn_entry():
    tail = (clr_w_d16(A1, ACTOR_SPRITE)
            + clr_b_d16(A1, FIELD_30) + clr_b_d16(A1, FIELD_31) + clr_b_d16(A1, FIELD_18)
            + bit_op_d16(BSET_IMM, SPAWNED_BIT, A1, FLAGS2)
            + move_l_an_dn(D0, A0) + move_l_abs_l_dn(D1, TABLE_PTR) + sub_l_dn_dn(D0, D1)
            + asr_l_imm_dn(TEMPLATE_SLOT_SHIFT, D0)
            + move_b_dn_d16(D0, A1, TEMPLATE_SLOT) + RTS)
    own_size = (move_w_d16_d16(A0, SPAWN_SIZE, A1, HALF_WIDTH)
                + move_w_d16_d16(A0, SPAWN_SIZE + WORD_LEN, A1, SIZE_SECOND))
    from_table = (lsl_w_imm_dn(SPAWN_SIZE_SHIFT, D0) + lea_abs_l(A2, SIZE_TABLE)
                  + move_l_indexed_d16(A2, D0, A1, HALF_WIDTH))

    # Every one of the five `beq`s lands on the same arm, so each spans the compares still to come
    # plus the table lookup and the whole tail.
    selectors = b""
    for index, spawn_type in enumerate(SPAWN_TYPES_WITH_OWN_SIZE):
        remaining = (len(SPAWN_TYPES_WITH_OWN_SIZE) - 1 - index) * (
            len(cmp_w_imm_dn(D0, 0)) + len(branch(BEQ_W, b"")))
        selectors += cmp_w_imm_dn(D0, spawn_type) + branch_over(
            BEQ_W, remaining + len(from_table) + len(tail))

    return (clr_w_d16(A1, ACTOR_FLAGS)
            + move_w_d16_ind(A0, SPAWN_X, A1)
            + move_w_d16_d16(A0, SPAWN_Y, A1, ACTOR_Y)
            + move_w_d16_d16(A0, SPAWN_TYPE, A1, ACTOR_TYPE)
            + moveq_0_dn(D0) + move_w_ind_dn(D0, A0, SPAWN_TYPE)
            + selectors + from_table + tail
            + own_size + bra_s_back(len(own_size) + len(tail)))


def _start_motion_entry():
    return (bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
            + bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS)
            + bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS)
            + move_b_dn_d16(D0, A0, SPEED) + RTS)


def _accelerate_fall_entry():
    step = addq_b_d16(1, A0, SPEED)
    return (bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
            + bit_op_d16(BSET_IMM, FALLING_BIT, A0, ACTOR_FLAGS)
            + moveq_0_dn(D0) + move_b_d16_dn(D0, A0, SPEED)
            + cmpi_b_dn(D0, FALL_SPEED_MAX) + branch(BEQ_W, step) + step + RTS)


ENTRY_BYTES = {
    "followed_actor_record": _followed_record_entry(),
    "actor_set_side_flag": _side_flag_entry(),
    "actor_followed_x_within": _within_entry(),
    "project_followed_actor": _project_followed_entry(),
    "project_actor_list": _project_list_entry(),
    "actor_table_reset": _table_reset_entry(),
    "actor_slots_mark_free": _mark_free_entry(),
    "actor_alloc_slot_low": _alloc_entry(ALLOC_LOW_FIRST, ALLOC_LOW_SLOTS),
    "actor_alloc_slot_high": _alloc_entry(ALLOC_HIGH_FIRST, ALLOC_HIGH_SLOTS),
    "actor_spawn_from_template": _spawn_entry(),
    "actor_start_motion_at_speed": _start_motion_entry(),
    "actor_accelerate_fall": _accelerate_fall_entry(),
}
RECONSTRUCTED_ROUTINES = 12


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("followed_actor_record", 24),
    ("actor_set_side_flag", 30),
    ("actor_followed_x_within", 42),
    ("project_followed_actor", 104),
    ("project_actor_list", 156),
    ("actor_table_reset", 30),
    ("actor_slots_mark_free", 14),
    ("actor_alloc_slot_low", 38),
    ("actor_alloc_slot_high", 38),
    ("actor_spawn_from_template", 134),
    ("actor_start_motion_at_speed", 24),
    ("actor_accelerate_fall", 32),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The pins above would still pass on a PREFIX of a routine. These are the sizes the Ghidra
    function table gives (../out/hw_scan.tsv), so a body reconstructed one instruction short fails
    here instead of leaving the tail unpinned."""
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records")


# --- what the two arrays are ----------------------------------------------------------------------

def test_the_scrolls_follow_words_are_screen_record_twelve():
    """WB_SCROLL_FOLLOW_X is not an address of its own: it is record WB_ACTOR_FOLLOWED_SLOT of the
    screen array, which is the whole reason $8dfe exists and the reason ../names.txt can call
    $9aec/$9fb4 "the followed actor". Both halves of the claim are arithmetic over the header's own
    constants, so a moved constant fails here rather than quietly decoupling the two names."""
    assert SCREEN_RECORDS + FOLLOWED_SLOT * SCREEN_RECORD_BYTES == FOLLOW_X, (
        f"screen record {FOLLOWED_SLOT} is at "
        f"{SCREEN_RECORDS + FOLLOWED_SLOT * SCREEN_RECORD_BYTES:#x}, not at scroll_follow_x "
        f"{FOLLOW_X:#x}")
    assert (SCREEN_RECORDS_END - SCREEN_RECORDS) == SCREEN_RECORD_COUNT * SCREEN_RECORD_BYTES, (
        f"the array spans {SCREEN_RECORDS_END - SCREEN_RECORDS} bytes, which is not "
        f"{SCREEN_RECORD_COUNT} records of {SCREEN_RECORD_BYTES}")
    for table, followed in ((TABLE_DEFAULT, FOLLOWED_DEFAULT), (TABLE_A32, FOLLOWED_A32)):
        assert table + FOLLOWED_SLOT * RECORD_BYTES == followed, (
            f"{followed:#x} is not slot {FOLLOWED_SLOT} of the table at {table:#x}")


def test_the_projection_is_one_block_the_two_passes_share():
    """Both entry pins are built from `_projection_block`, so this states the claim that makes that
    legitimate: the sixty-eight bytes really are byte-identical at both addresses in the image."""
    block = _projection_block()
    at_followed = leaf.entry_of("project_followed_actor") + len(ENTRY_BYTES[
        "project_followed_actor"]) - len(block) - len(RTS)
    at_list = leaf.entry_of("project_actor_list") + len(ENTRY_BYTES["project_actor_list"]) - (
        len(block) + len(cmpa_l_imm(A1, SCREEN_RECORDS_END)) + WORD_LEN + len(RTS))
    for name, at in (("project_followed_actor", at_followed), ("project_actor_list", at_list)):
        actual = bytes(harness.BASE_IMAGE[at:at + len(block)])
        assert actual == block, f"{name}'s projection block at {at:#x} is not the shared one"


# --- seeding --------------------------------------------------------------------------------------
# One band covers the screen array, all three actor tables and the published pointer between them,
# with a record's worth of margin at each end. Keying on the ADDRESS is what makes an over-run
# visible: a walk that took the wrong stride or the wrong table lands on bytes that are wrong for
# where they were written, not on zeros. One band rather than several also means the overlapping
# margins cannot disagree with each other.
SEED_MARGIN = RECORD_BYTES
SEED_LO = SCREEN_RECORDS - SEED_MARGIN
SEED_HI = TABLE_A32 + TABLE_BYTES + SEED_MARGIN


def _state_pokes(salt, words):
    """The seeded band, plus the state words a case names — `{address: value}`, since the addresses
    are numbers rather than keyword names."""
    pokes = {SEED_LO: keyed_block(SEED_LO, SEED_HI - SEED_LO, salt)}
    for addr, value in words.items():
        pokes[addr] = word(value)
    return pokes


def _put_word(out, addr, value):
    for offset, byte in enumerate(word(value)):
        out[addr + offset] = byte


def _put_long(out, addr, value):
    for offset, byte in enumerate(longword(value)):
        out[addr + offset] = byte


def _model_projection(image, record, screen):
    """One actor record into one screen record: {address: byte}."""
    out = {}
    scroll_x = u16(image, POS_X)
    scroll_y = u16(image, POS_Y)
    _put_word(out, screen + SCREEN_X,
              u16(image, record + ACTOR_X) - SCREEN_X_BIAS - scroll_x)
    _put_word(out, screen + SCREEN_Y,
              u16(image, record + ACTOR_Y) - SCREEN_Y_BIAS - scroll_y)
    flickering = (image[record + ACTOR_FLAGS] & (1 << FLICKER_BIT)) and u16(image, FRAME_TOGGLE)
    _put_word(out, screen + SCREEN_SPRITE,
              SPRITE_HIDDEN if flickering else u16(image, record + ACTOR_SPRITE))
    return out


def _assert_writes(info, expected, what):
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {sorted(hex(a) for a in written)} against the model's "
        f"{sorted(hex(a) for a in expected)}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")


# --- glue -------------------------------------------------------------------------------------------
_FOLLOWED_RECORD = leaf.register_glue("followed_actor_record", [], ctypes.c_uint32)
_SIDE_FLAG = leaf.register_glue("actor_set_side_flag", [ctypes.c_uint32])
_WITHIN = leaf.register_glue("actor_followed_x_within", [ctypes.c_uint32] * 2, ctypes.c_uint32)
_PROJECT_FOLLOWED = leaf.image_glue("project_followed_actor")
_PROJECT_LIST = leaf.image_glue("project_actor_list")


# --- $67e0: the record selector -------------------------------------------------------------------
# The `bne` reading and the `bpl` reading agree on $0000 and $ffff, which is all the image ever
# writes; $0001 and $7fff are where they part company, and $8000 is the other side of the sign.
SELECTOR_CASES = [
    ("clear", 0x0000, FOLLOWED_DEFAULT),
    ("all-ones", 0xffff, FOLLOWED_A32),
    ("one", 0x0001, FOLLOWED_A32),
    ("largest-positive", 0x7fff, FOLLOWED_A32),
    ("sign-boundary", 0x8000, FOLLOWED_A32),
]


@pytest.mark.parametrize("case,flag,expected", SELECTOR_CASES, ids=[c[0] for c in SELECTOR_CASES])
def test_the_selector_names_the_record_the_flag_picks(case, flag, expected):
    """$67e0 writes NO memory, so its a1 is the whole surface. `one` and `largest-positive` are the
    cases the `bne` passes and a `bpl` would fail — the reading the game itself cannot distinguish.
    """
    pokes = _state_pokes(case_salt(case), {FLAG_A32: flag})
    what = f"followed_actor_record a32={flag:#06x}"
    info = leaf.run("followed_actor_record", _FOLLOWED_RECORD(), [], what,
                    regs={"_pokes": pokes})

    assert not program_writes(info), f"{what}: it wrote memory, which this routine does not"
    assert info["regs"]["a1"] == expected, (
        f"{what}: the original returned a1={info['regs']['a1']:#x}, not {expected:#x}")
    assert info["ret"] == info["regs"]["a1"], (
        f"{what}: the reconstruction returned {info['ret']:#x} against the original's "
        f"{info['regs']['a1']:#x}")


# --- $67c2: the side flag -------------------------------------------------------------------------
# (followed x, actor x): both sides of the comparison, the equal case the `ble` clamps on, and the
# two that make it a SIGNED comparison rather than an unsigned one.
SIDE_CASES = [
    ("actor-right", 0x0100, 0x0140),
    ("actor-left", 0x0140, 0x0100),
    ("equal", 0x0120, 0x0120),
    ("one-apart", 0x0120, 0x0121),
    ("one-apart-other-way", 0x0121, 0x0120),
    ("actor-negative", 0x0010, 0xffff),
    ("followed-negative", 0xffff, 0x0010),
    ("sign-boundary", 0x7fff, 0x8000),
    ("sign-boundary-other-way", 0x8000, 0x7fff),
]
# The flag byte seeds: bit 3 already raised (so the `bclr` arm has something to clear), already
# clear, and both with the neighbouring bits set — a byte-wide op must leave them alone.
FLAG_SEEDS = (0x00, 1 << SIDE_BIT, 0xf7, 0xff)


@pytest.mark.parametrize("flag_seed", FLAG_SEEDS, ids=lambda v: f"flags{v:#04x}")
@pytest.mark.parametrize("case,followed_x,actor_x", SIDE_CASES, ids=[c[0] for c in SIDE_CASES])
def test_the_side_flag_says_which_way_the_followed_actor_is(case, followed_x, actor_x, flag_seed):
    actor = TABLE_DEFAULT + 3 * RECORD_BYTES         # any record but the followed one
    salt = case_salt(f"{case}-{flag_seed}")
    pokes = _state_pokes(salt, {FLAG_A32: 0})
    pokes[FOLLOWED_DEFAULT + ACTOR_X] = word(followed_x)
    pokes[actor + ACTOR_X] = word(actor_x)
    pokes[actor + ACTOR_FLAGS] = bytes([flag_seed])

    what = f"actor_set_side_flag followed={followed_x:#06x} actor={actor_x:#06x}"
    info = leaf.run("actor_set_side_flag", _SIDE_FLAG(actor), [(actor + ACTOR_FLAGS, 1)], what,
                    regs={"a0": actor, "_pokes": pokes})

    raised = s16(actor_x) > s16(followed_x)
    expected = flag_seed | (1 << SIDE_BIT) if raised else flag_seed & ~(1 << SIDE_BIT)
    _assert_writes(info, {actor + ACTOR_FLAGS: expected}, what)


def test_the_side_flag_reaches_the_a32_record_too():
    """The flag routine's own comparison is against whatever `followed_actor_record` returned, so
    one case per table: a port that hardcoded either address passes half of them."""
    actor = TABLE_A32 + 5 * RECORD_BYTES
    pokes = _state_pokes(case_salt("side-a32"), {FLAG_A32: 0xffff})
    pokes[FOLLOWED_A32 + ACTOR_X] = word(0x0100)
    pokes[FOLLOWED_DEFAULT + ACTOR_X] = word(0x0900)     # what a hardcoded port would read
    pokes[actor + ACTOR_X] = word(0x0500)
    pokes[actor + ACTOR_FLAGS] = bytes([0x00])

    info = leaf.run("actor_set_side_flag", _SIDE_FLAG(actor), [(actor + ACTOR_FLAGS, 1)],
                    "actor_set_side_flag against the a32 record",
                    regs={"a0": actor, "_pokes": pokes})
    _assert_writes(info, {actor + ACTOR_FLAGS: 1 << SIDE_BIT},
                   "actor_set_side_flag against the a32 record")


# --- $67f8: the horizontal reach ------------------------------------------------------------------
# (followed x, actor x, reach): both arms of the `bgt`, both sides of each arm's boundary, and the
# two cases where the 16-bit ADD wraps into the compare that reads it.
REACH = 0x40
WITHIN_CASES = [
    ("followed-ahead-inside", 0x0140, 0x0110, REACH),
    ("followed-ahead-on-the-boundary", 0x0150, 0x0110, REACH),
    ("followed-ahead-outside", 0x0151, 0x0110, REACH),
    ("followed-behind-inside", 0x0110, 0x0140, REACH),
    ("followed-behind-on-the-boundary", 0x0110, 0x0150, REACH),
    ("followed-behind-outside", 0x0110, 0x0151, REACH),
    ("same-place", 0x0120, 0x0120, REACH),
    ("zero-reach-together", 0x0120, 0x0120, 0),
    ("zero-reach-apart", 0x0120, 0x0121, 0),
    ("both-negative", 0xff00, 0xff20, REACH),
    ("across-zero", 0xffe0, 0x0010, REACH),
    # The ADD wraps out of the positive half, and the compare that follows reads the wrapped sum:
    # an unbounded model answers the other way round on both of these.
    ("actor-sum-wraps", 0x7000, 0x7ff0, 0x2000),
    ("followed-sum-wraps", 0x7ff8, 0x7ff0, 0x2000),
]
# d0 is IN AND OUT and only its low word is written, so the high half a case enters with must come
# back untouched — which is what makes this a longword comparison rather than a word one.
REACH_HIGH_HALVES = (0x00000000, 0xdead0000)


@pytest.mark.parametrize("high", REACH_HIGH_HALVES, ids=lambda v: f"d0hi{v >> 16:#06x}")
@pytest.mark.parametrize("case,followed_x,actor_x,reach", WITHIN_CASES,
                         ids=[c[0] for c in WITHIN_CASES])
def test_the_reach_test_answers_for_the_wrapped_sum(case, followed_x, actor_x, reach, high):
    actor = TABLE_DEFAULT + 7 * RECORD_BYTES
    pokes = _state_pokes(case_salt(f"{case}-{high}"), {FLAG_A32: 0})
    pokes[FOLLOWED_DEFAULT + ACTOR_X] = word(followed_x)
    pokes[actor + ACTOR_X] = word(actor_x)

    what = f"actor_followed_x_within followed={followed_x:#06x} actor={actor_x:#06x} reach={reach}"
    info = leaf.run("actor_followed_x_within", _WITHIN(actor, high | reach), [], what,
                    regs={"a0": actor, "d0": high | reach, "_pokes": pokes})

    here, followed = s16(actor_x), s16(followed_x)
    if followed > here:
        outside = followed > s16(here + reach)
    else:
        outside = s16(followed + reach) < here
    expected = high | (OUT_OF_REACH if outside else 0)

    assert not program_writes(info), f"{what}: it wrote memory, which this routine does not"
    assert info["regs"]["d0"] == expected, (
        f"{what}: the original returned d0={info['regs']['d0']:#010x}, not {expected:#010x}")
    assert info["ret"] == info["regs"]["d0"], (
        f"{what}: the reconstruction returned {info['ret']:#010x} against the original's "
        f"{info['regs']['d0']:#010x}")


def test_the_reach_test_reaches_the_a32_record_too():
    actor = TABLE_A32 + 9 * RECORD_BYTES
    pokes = _state_pokes(case_salt("within-a32"), {FLAG_A32: 0xffff})
    pokes[FOLLOWED_A32 + ACTOR_X] = word(0x0080)         # well outside the reach
    pokes[FOLLOWED_DEFAULT + ACTOR_X] = word(0x0110)     # what a hardcoded port would read: inside
    pokes[actor + ACTOR_X] = word(0x0120)

    info = leaf.run("actor_followed_x_within", _WITHIN(actor, REACH), [],
                    "actor_followed_x_within against the a32 record",
                    regs={"a0": actor, "d0": REACH, "_pokes": pokes})
    assert info["regs"]["d0"] == OUT_OF_REACH, (
        "the a32 record is far outside the reach where the default one is inside it, so a port "
        "reading the wrong record answers 0 here")
    assert info["ret"] == info["regs"]["d0"]


# --- $8dfe: the followed actor's own projection ---------------------------------------------------
# Every combination of the two flags the gate and the selector read, the four the flicker `btst` and
# `tst.w` make, and positions that wrap the two subtractions.
PROJECT_STATE = dict(a30=0x0000, a32=0x0000, toggle=0x0000, pos_x=0x0040, pos_y=0x0020,
                     x=0x0100, y=0x0080, sprite=0x1234, flags=0x00)


def _project_pokes(salt, **overrides):
    state = dict(PROJECT_STATE, **overrides)
    record = FOLLOWED_A32 if state["a32"] else FOLLOWED_DEFAULT
    pokes = _state_pokes(salt, {FLAG_A30: state["a30"], FLAG_A32: state["a32"],
                                FRAME_TOGGLE: state["toggle"],
                                POS_X: state["pos_x"], POS_Y: state["pos_y"]})
    pokes[record + ACTOR_X] = word(state["x"])
    pokes[record + ACTOR_Y] = word(state["y"])
    pokes[record + ACTOR_SPRITE] = word(state["sprite"])
    pokes[record + ACTOR_FLAGS] = bytes([state["flags"]])
    return pokes, record


FOLLOWED_CASES = [
    ("plain", {}),
    ("a32-record", dict(a32=0xffff)),
    ("a32-small-positive", dict(a32=0x0001)),         # `bne` picks the a32 record, `bpl` would not
    ("flag-a30-zero", dict(a30=0x0000)),
    ("flag-a30-positive", dict(a30=0x7fff)),          # `bpl` runs the body; a `bne` would not
    ("flicker-armed-toggle-off", dict(flags=1 << FLICKER_BIT, toggle=0x0000)),
    ("flicker-armed-toggle-on", dict(flags=1 << FLICKER_BIT, toggle=0xffff)),
    ("flicker-idle-toggle-on", dict(flags=0xff & ~(1 << FLICKER_BIT), toggle=0xffff)),
    ("flicker-armed-toggle-one", dict(flags=0xff, toggle=0x0001)),
    ("position-wraps", dict(x=0x0010, y=0x0008, pos_x=0x0100, pos_y=0x0100)),
    ("position-large", dict(x=0x7fff, y=0x8000, pos_x=0xff00, pos_y=0x0100)),
]


@pytest.mark.parametrize("case,overrides", FOLLOWED_CASES, ids=[c[0] for c in FOLLOWED_CASES])
def test_the_followed_projection_writes_screen_record_twelve(case, overrides):
    pokes, record = _project_pokes(case_salt(case), **overrides)
    image = harness.make_image(pokes)
    expected = _model_projection(image, record, FOLLOW_X)

    what = f"project_followed_actor {case}"
    info = leaf.run("project_followed_actor", _PROJECT_FOLLOWED, merge_bands(expected), what,
                    regs={"_pokes": pokes})
    _assert_writes(info, expected, what)

    # The registers it walks out with — the model's, not the reconstruction's (it returns neither).
    assert info["regs"]["a0"] == record + RECORD_BYTES, what
    assert info["regs"]["a1"] == FOLLOW_X + SCREEN_RECORD_BYTES, what


@pytest.mark.parametrize("flag", (0xffff, 0x8000), ids=lambda v: f"a30{v:#06x}")
def test_the_followed_projection_does_nothing_while_the_mode_flag_is_negative(flag):
    """The `bpl` gate reads N alone, so $8000 is as negative as $ffff. Nothing may be written — not
    the screen record, and not the neighbouring ones the margin covers."""
    pokes, _record = _project_pokes(case_salt(f"gated-{flag}"), a30=flag)
    what = f"project_followed_actor gated a30={flag:#06x}"
    info = leaf.run("project_followed_actor", _PROJECT_FOLLOWED, [], what, regs={"_pokes": pokes})

    assert not program_writes(info), f"{what}: the gated arm wrote memory"
    assert info["regs"]["a0"] == 0 and info["regs"]["a1"] == 0, (
        f"{what}: the gated arm changed a0/a1, which it returns without touching")


# --- $8e66: the whole list ------------------------------------------------------------------------
LIST_CASES = [
    ("default-table", 0x0000, 0x0000, TABLE_DEFAULT),
    ("a32-table", 0x0000, 0xffff, TABLE_A32),
    ("a30-table", 0xffff, 0x0000, TABLE_A30),
    ("a30-wins", 0xffff, 0xffff, TABLE_A30),
    ("a30-sign-boundary", 0x8000, 0x0000, TABLE_A30),
    # `bpl` on a SMALL POSITIVE word picks the default table where $67e0's `bne` picks the a32 one:
    # the one place the list pass and the selector disagree, and the game cannot reach it.
    ("a32-small-positive", 0x0000, 0x0001, TABLE_DEFAULT),
    ("a32-sign-boundary", 0x0000, 0x8000, TABLE_A32),
]


def _list_pokes(salt, a30, a32, toggle=0xffff, pos_x=0x0040, pos_y=0x0020):
    """Every record is left at whatever the address-keyed seed made it — including its flag byte, so
    the flicker arm and the plain one both run inside a single pass and neither is a special case."""
    return _state_pokes(salt, {FLAG_A30: a30, FLAG_A32: a32, FRAME_TOGGLE: toggle,
                               POS_X: pos_x, POS_Y: pos_y})


@pytest.mark.parametrize("toggle", (0x0000, 0xffff), ids=lambda v: f"toggle{v:#06x}")
@pytest.mark.parametrize("case,a30,a32,table", LIST_CASES, ids=[c[0] for c in LIST_CASES])
def test_the_list_pass_projects_the_table_the_flags_name(case, a30, a32, table, toggle):
    pokes = _list_pokes(case_salt(f"{case}-{toggle}"), a30, a32, toggle=toggle)
    image = harness.make_image(pokes)

    expected = {}
    _put_long(expected, TABLE_SELECTED, table)
    for slot in range(SCREEN_RECORD_COUNT):
        expected.update(_model_projection(image, table + slot * RECORD_BYTES,
                                          SCREEN_RECORDS + slot * SCREEN_RECORD_BYTES))

    what = f"project_actor_list {case} toggle={toggle:#06x}"
    info = leaf.run("project_actor_list", _PROJECT_LIST, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=LIST_INSN_CAP)
    _assert_writes(info, expected, what)

    assert info["regs"]["a0"] == table + SCREEN_RECORD_COUNT * RECORD_BYTES, what
    assert info["regs"]["a1"] == SCREEN_RECORDS_END, what


def test_the_list_pass_reaches_both_flicker_arms_in_one_sweep():
    """The seeded flag bytes are what make the sweep above cover the flicker `btst` at all, so the
    cover is measured rather than assumed: with the toggle on, some records publish a sprite and
    some publish none, and a pass that reached only one arm would leave that branch untested."""
    pokes = _list_pokes(case_salt("flicker-cover"), a30=0, a32=0, toggle=0xffff)
    image = harness.make_image(pokes)
    armed = [slot for slot in range(SCREEN_RECORD_COUNT)
             if image[TABLE_DEFAULT + slot * RECORD_BYTES + ACTOR_FLAGS] & (1 << FLICKER_BIT)]
    assert 0 < len(armed) < SCREEN_RECORD_COUNT, (
        f"{len(armed)} of {SCREEN_RECORD_COUNT} seeded records arm the flicker bit, so the sweep "
        f"no longer reaches both arms of the `btst`")


def test_the_list_pass_republishes_the_pointer_it_reads():
    """`movea.l $a098.l,a0` re-reads the longword the routine has just written, so whatever a caller
    left there has no say. Seeded with the WRONG table, the pass must still project the right one.
    """
    pokes = _list_pokes(case_salt("republish"), a30=0, a32=0)
    pokes[TABLE_SELECTED] = longword(TABLE_A30)
    image = harness.make_image(pokes)

    expected = {}
    _put_long(expected, TABLE_SELECTED, TABLE_DEFAULT)
    for slot in range(SCREEN_RECORD_COUNT):
        expected.update(_model_projection(image, TABLE_DEFAULT + slot * RECORD_BYTES,
                                          SCREEN_RECORDS + slot * SCREEN_RECORD_BYTES))

    what = "project_actor_list over a stale published pointer"
    info = leaf.run("project_actor_list", _PROJECT_LIST, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=LIST_INSN_CAP)
    _assert_writes(info, expected, what)


def test_the_list_pass_touches_exactly_the_screen_array_and_the_pointer():
    """The write set stated as the GEOMETRY rather than as whatever the model produced: nineteen
    six-byte records, back to back, plus the published longword and nothing else."""
    pokes = _list_pokes(case_salt("extent"), a30=0, a32=0)
    info = leaf.run("project_actor_list", _PROJECT_LIST,
                    [(SCREEN_RECORDS, SCREEN_RECORDS_END - SCREEN_RECORDS),
                     (TABLE_SELECTED, LONGWORD_LEN)],
                    "project_actor_list extent", regs={"_pokes": pokes}, max_insns=LIST_INSN_CAP)

    written = sorted(program_writes(info))
    assert written == (list(range(SCREEN_RECORDS, SCREEN_RECORDS_END))
                       + list(range(TABLE_SELECTED, TABLE_SELECTED + LONGWORD_LEN))), (
        f"the pass wrote {len(written)} bytes, not the "
        f"{SCREEN_RECORDS_END - SCREEN_RECORDS + LONGWORD_LEN} the geometry gives")


# --- what the image says about the tier -----------------------------------------------------------

def test_the_selector_is_called_and_never_read_as_data():
    """A whole-image scan for $67e0: fifteen references and every one of them a CALL — which is what
    makes `followed_actor_record` a routine the tier goes through rather than an address anything
    could also read. The two `jsr` spellings matter as well: $8dfe reaches it as `jsr $67e0.w`,
    which only works because the entry is below $8000."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    entry = leaf.entry_of("followed_actor_record")
    assert entry < 0x8000, (
        f"{entry:#x} is out of an abs.w operand's reach, so the `jsr $67e0.w` at $8e08 could not "
        f"name it and this scan's two spellings are not the whole story")

    as_data = [at for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN)
               if int.from_bytes(program[at:at + LONGWORD_LEN], "big") == entry]
    # Every longword spelling the address must be the operand of one of the two `jsr` forms, i.e.
    # preceded by that opcode — a bare pointer to it in a table would fail here.
    for at in as_data:
        assert program[at - WORD_LEN:at] == opcode(0x4eb9), (
            f"{entry:#x} appears as a longword at {at:#x} that is not a `jsr $67e0.l` operand")
    assert len(as_data) == 2, f"{len(as_data)} `jsr $67e0.l` sites, not the two the scan records"

    abs_w = [at for at in range(0, len(program) - WORD_LEN, WORD_LEN)
             if program[at:at + WORD_LEN] == word(entry)
             and program[at - WORD_LEN:at] == opcode(0x4eb8)]
    assert len(abs_w) == 2, f"{len(abs_w)} `jsr $67e0.w` sites, not the two the scan records"


# --- the table's lifecycle ------------------------------------------------------------------------
# Every case seeds all three tables address-keyed with `_state_pokes`, so a walk that ran one record
# long, took the wrong stride or read the wrong table lands on bytes that are wrong FOR WHERE THEY
# WERE WRITTEN. What each case adds on top is only the records it is about.
#
# The instruction caps come from each routine's own loop geometry.
RESET_INSN_PER_RECORD = 10
MARK_FREE_INSN_PER_RECORD = 4
ALLOC_INSN_PER_SLOT = 4
LOOP_INSN_TAIL = 16

_TABLE_RESET = leaf.register_glue("actor_table_reset", [ctypes.c_uint32])
_MARK_FREE = leaf.register_glue("actor_slots_mark_free", [ctypes.c_uint32] * 2)
_ALLOC_LOW = leaf.register_glue("actor_alloc_slot_low", [], ctypes.c_uint32)
_ALLOC_HIGH = leaf.register_glue("actor_alloc_slot_high", [], ctypes.c_uint32)
_SPAWN = leaf.register_glue("actor_spawn_from_template", [ctypes.c_uint32] * 2)
_START_MOTION = leaf.register_glue("actor_start_motion_at_speed", [ctypes.c_uint32] * 2)
_ACCELERATE_FALL = leaf.register_glue("actor_accelerate_fall", [ctypes.c_uint32])


def _model_table_reset(table):
    """{address: byte} — the marker in each record's first word and zero over the rest of it."""
    out = {}
    for slot in range(SCREEN_RECORD_COUNT):
        record = table + slot * RECORD_BYTES
        _put_word(out, record + ACTOR_X, FREE_MARKER)
        for offset in range(WORD_LEN, RECORD_BYTES):
            out[record + offset] = 0
    return out


@pytest.mark.parametrize("table", [TABLE_DEFAULT, TABLE_A30, TABLE_A32],
                         ids=lambda v: f"table{v:#x}")
def test_the_reset_marks_every_record_free_and_zeroes_the_rest(table):
    """All three tables, since a0 is the only thing that says which one — and the seeded band
    covers all three back to back, so a walk that overran one lands in the next."""
    expected = _model_table_reset(table)
    what = f"actor_table_reset {table:#x}"
    info = leaf.run("actor_table_reset", _TABLE_RESET(table), merge_bands(expected), what,
                    regs={"a0": table, "_pokes": _state_pokes(case_salt(what), {})},
                    max_insns=RESET_INSN_PER_RECORD * SCREEN_RECORD_COUNT + LOOP_INSN_TAIL)
    _assert_writes(info, expected, what)
    assert info["regs"]["a0"] == table + SCREEN_RECORD_COUNT * RECORD_BYTES, (
        f"{what}: a0 walked out at {info['regs']['a0']:#x}, not one record past the last")


@pytest.mark.parametrize("count", [0, 1, 5, SCREEN_RECORD_COUNT - 1],
                         ids=lambda v: f"dbf{v}")
@pytest.mark.parametrize("first_slot", [0, 3, 13], ids=lambda v: f"from{v}")
def test_marking_a_run_free_touches_only_the_marker_words(first_slot, count):
    """A `dbf` count of N marks N + 1 records, and NOTHING but their first words — which is the
    whole difference between this routine and the reset above."""
    first = TABLE_DEFAULT + first_slot * RECORD_BYTES
    expected = {}
    for slot in range(count + 1):
        _put_word(expected, first + slot * RECORD_BYTES + ACTOR_X, FREE_MARKER)

    what = f"actor_slots_mark_free from slot {first_slot}, dbf {count}"
    info = leaf.run("actor_slots_mark_free", _MARK_FREE(first, count), merge_bands(expected), what,
                    regs={"a6": first, "d7": count, "_pokes": _state_pokes(case_salt(what), {})},
                    max_insns=MARK_FREE_INSN_PER_RECORD * (count + 1) + LOOP_INSN_TAIL)
    _assert_writes(info, expected, what)


def test_the_free_run_reads_only_the_low_word_of_its_count():
    """`dbf d7` counts in a WORD, so a caller's rubbish above it must not reach the loop."""
    first = TABLE_DEFAULT + 3 * RECORD_BYTES
    expected = {}
    for slot in range(3):
        _put_word(expected, first + slot * RECORD_BYTES + ACTOR_X, FREE_MARKER)
    what = "actor_slots_mark_free with a high half in d7"
    info = leaf.run("actor_slots_mark_free", _MARK_FREE(first, 0xdead0002), merge_bands(expected),
                    what, regs={"a6": first, "d7": 0xdead0002,
                                "_pokes": _state_pokes(case_salt(what), {})},
                    max_insns=MARK_FREE_INSN_PER_RECORD * 3 + LOOP_INSN_TAIL)
    _assert_writes(info, expected, what)


# A word that is NOT the free marker, stamped into every record a pool case does not want free —
# the address-keyed seed could in principle spell $ffbe by itself, and a case that silently found
# an extra free slot would be testing nothing.
OCCUPIED = 0x1234


def _pool_pokes(salt, table, free_slots):
    """All three tables seeded, `table`'s records all occupied, and `free_slots` of it marked."""
    pokes = _state_pokes(salt, {})
    for slot in range(SCREEN_RECORD_COUNT):
        pokes[table + slot * RECORD_BYTES + ACTOR_X] = word(
            FREE_MARKER if slot in free_slots else OCCUPIED)
    pokes[TABLE_SELECTED] = longword(table)
    return pokes


POOLS = {
    "low": (_ALLOC_LOW, "actor_alloc_slot_low", ALLOC_LOW_FIRST, ALLOC_LOW_SLOTS),
    "high": (_ALLOC_HIGH, "actor_alloc_slot_high", ALLOC_HIGH_FIRST, ALLOC_HIGH_SLOTS),
}


def _run_alloc(pool, case, free_slots, expected, table=TABLE_DEFAULT):
    glue, name, first, slots = POOLS[pool]
    what = f"{name} {case}"
    pokes = _pool_pokes(case_salt(what), table, free_slots)
    info = leaf.run(name, glue(), [], what, regs={"_pokes": pokes},
                    max_insns=ALLOC_INSN_PER_SLOT * slots + LOOP_INSN_TAIL)
    assert not program_writes(info), f"{what}: it wrote memory, which this routine does not"
    assert info["regs"]["a1"] == expected, (
        f"{what}: the original returned a1={info['regs']['a1']:#x}, not {expected:#x}")
    assert info["ret"] == info["regs"]["a1"], (
        f"{what}: the reconstruction returned {info['ret']:#x} against the original's "
        f"{info['regs']['a1']:#x}")


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
def test_an_allocator_hands_back_the_first_free_slot_of_its_own_pool(pool):
    _glue, _name, first, slots = POOLS[pool]
    for offset in range(slots):
        _run_alloc(pool, f"only slot {first + offset} free", {first + offset},
                   TABLE_DEFAULT + (first + offset) * RECORD_BYTES)


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
def test_an_allocator_takes_the_lowest_of_several_free_slots(pool):
    _glue, _name, first, slots = POOLS[pool]
    free = {first, first + 1, first + slots - 1}
    _run_alloc(pool, "several free", free, TABLE_DEFAULT + first * RECORD_BYTES)


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
def test_a_full_pool_comes_back_empty_handed(pool):
    _run_alloc(pool, "nothing free", set(), ALLOC_NONE)


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
def test_no_allocator_can_reach_the_followed_actors_slot(pool):
    """THE case the two pools exist for: slot WB_ACTOR_FOLLOWED_SLOT is free and it is the ONLY
    free record, and neither allocator returns it — the low pool stops one short of it and the high
    one starts one past it. Slots 0..2 are equally out of reach, which the next case covers."""
    _run_alloc(pool, "only the followed slot free", {FOLLOWED_SLOT}, ALLOC_NONE)


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
def test_an_allocator_ignores_every_free_slot_outside_its_pool(pool):
    """Every slot the pool does not own, free at once. A `lea` with the wrong first record or a
    `dbf` with the wrong count returns one of them instead of nothing."""
    _glue, _name, first, slots = POOLS[pool]
    outside = set(range(SCREEN_RECORD_COUNT)) - set(range(first, first + slots))
    _run_alloc(pool, "only slots outside the pool free", outside, ALLOC_NONE)


def test_the_pools_tile_the_table_around_the_followed_slot():
    """The claim src/actor.c's header makes, as arithmetic over the header's own constants: the two
    runs are 3..11 and 13..18, so they meet either side of slot 12 and cover everything above it."""
    assert ALLOC_LOW_FIRST + ALLOC_LOW_SLOTS == FOLLOWED_SLOT
    assert ALLOC_HIGH_FIRST == FOLLOWED_SLOT + 1
    assert ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS == SCREEN_RECORD_COUNT


@pytest.mark.parametrize("pool", sorted(POOLS), ids=sorted(POOLS))
@pytest.mark.parametrize("table", [TABLE_A30, TABLE_A32], ids=lambda v: f"table{v:#x}")
def test_an_allocator_walks_whichever_table_was_published(pool, table):
    """`movea.l $a098.l,a1` — the pool is an offset into the table `project_actor_list` last
    published, not into a table of its own. The other two tables are seeded with no free record at
    all, so a port that hardcoded one comes back empty-handed."""
    _glue, _name, first, _slots = POOLS[pool]
    what = f"{_name} against the table at {table:#x}"
    pokes = _pool_pokes(case_salt(what), table, {first})
    for other in (TABLE_DEFAULT, TABLE_A30, TABLE_A32):
        if other != table:
            for slot in range(SCREEN_RECORD_COUNT):
                pokes[other + slot * RECORD_BYTES + ACTOR_X] = word(OCCUPIED)
    info = leaf.run(_name, _glue(), [], what, regs={"_pokes": pokes},
                    max_insns=ALLOC_INSN_PER_SLOT * SCREEN_RECORD_COUNT + LOOP_INSN_TAIL)
    assert info["regs"]["a1"] == table + first * RECORD_BYTES
    assert info["ret"] == info["regs"]["a1"]


# --- $ffe4: the spawn -----------------------------------------------------------------------------
# The template table and the size table both live outside the actor band, so a spawn case seeds
# three regions: the actor tables (for the destination record), a template table in plain RAM, and
# a window of WB_ACTOR_SIZE_TABLE, which is program data the game overwrites at run time.
SPAWN_INSN_CAP = 48
TEMPLATE_TABLE = 0x31000                 # plain RAM, clear of everything else a case seeds
TEMPLATE_SLOTS = 8
SIZE_TABLE_ENTRIES = 0x100
SPAWN_TYPES_FROM_TABLE = (0, 1, 0x35, 0x39, 0x3d, 0xff)


def _spawn_pokes(salt, template_slot, spawn_type, table_base=TEMPLATE_TABLE):
    pokes = _state_pokes(salt, {})
    pokes[table_base] = keyed_block(table_base, TEMPLATE_SLOTS * SPAWN_RECORD_BYTES, salt)
    pokes[SIZE_TABLE] = keyed_block(SIZE_TABLE, SIZE_TABLE_ENTRIES * LONGWORD_LEN, salt)
    pokes[TABLE_PTR] = longword(table_base)
    pokes[table_base + template_slot * SPAWN_RECORD_BYTES + SPAWN_TYPE] = word(spawn_type)
    return pokes


def _model_spawn(image, template, record):
    out = {}
    spawn_type = u16(image, template + SPAWN_TYPE)
    _put_word(out, record + ACTOR_FLAGS, 0)
    _put_word(out, record + ACTOR_X, u16(image, template + SPAWN_X))
    _put_word(out, record + ACTOR_Y, u16(image, template + SPAWN_Y))
    _put_word(out, record + ACTOR_TYPE, spawn_type)
    if spawn_type in SPAWN_TYPES_WITH_OWN_SIZE:
        _put_word(out, record + HALF_WIDTH, u16(image, template + SPAWN_SIZE))
        _put_word(out, record + SIZE_SECOND, u16(image, template + SPAWN_SIZE + WORD_LEN))
    else:
        index = (spawn_type << SPAWN_SIZE_SHIFT) & 0xffff
        _put_long(out, record + HALF_WIDTH, int.from_bytes(
            bytes(image[SIZE_TABLE + index:SIZE_TABLE + index + LONGWORD_LEN]), "big"))
    _put_word(out, record + ACTOR_SPRITE, 0)
    out[record + FIELD_30] = 0
    out[record + FIELD_31] = 0
    out[record + FIELD_18] = 0
    # `clr.w 8(a1)` cleared both flag bytes before the `bset`, so the raised bit is the only one.
    out[record + FLAGS2] = 1 << SPAWNED_BIT
    delta = template - int.from_bytes(bytes(image[TABLE_PTR:TABLE_PTR + LONGWORD_LEN]), "big")
    if delta >= 0x80000000:
        delta -= 0x100000000
    out[record + TEMPLATE_SLOT] = (delta >> TEMPLATE_SLOT_SHIFT) & 0xff
    return out


def _run_spawn(case, template_slot, spawn_type, record_slot=5, table_base=TEMPLATE_TABLE):
    what = f"actor_spawn_from_template {case}"
    pokes = _spawn_pokes(case_salt(what), template_slot, spawn_type, table_base)
    template = table_base + template_slot * SPAWN_RECORD_BYTES
    record = TABLE_DEFAULT + record_slot * RECORD_BYTES

    image = harness.make_image(pokes)
    expected = _model_spawn(image, template, record)
    info = leaf.run("actor_spawn_from_template", _SPAWN(template, record), merge_bands(expected),
                    what, regs={"a0": template, "a1": record, "_pokes": pokes},
                    max_insns=SPAWN_INSN_CAP)
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("spawn_type", SPAWN_TYPES_WITH_OWN_SIZE, ids=lambda v: f"own{v:#04x}")
def test_the_five_types_that_carry_their_own_size_copy_it_from_the_template(spawn_type):
    """All five `cmp.w` arms. Each takes the template's own pair rather than the size table's, and
    the seeded size table holds different bytes, so an arm that fell through fails."""
    _run_spawn(f"own-size type {spawn_type:#x}", 2, spawn_type)


@pytest.mark.parametrize("spawn_type", SPAWN_TYPES_FROM_TABLE, ids=lambda v: f"table{v:#04x}")
def test_every_other_type_takes_its_size_from_the_table(spawn_type):
    """Including the two types either side of the $36..$38 run and the two either side of $3b/$3c,
    so a compare written as a RANGE rather than as five equalities fails."""
    _run_spawn(f"table-size type {spawn_type:#x}", 2, spawn_type)


def test_the_size_index_is_a_word_and_wraps():
    """`lsl.w #2` on a word: a type from $4000 up indexes back to the start of the size table
    instead of past its end. Unreachable from the shipped templates, which is why it is a seeded
    case and not a claim about the data."""
    _run_spawn("wrapping size index", 2, 0x4000)


@pytest.mark.parametrize("template_slot", [0, 1, TEMPLATE_SLOTS - 1],
                         ids=lambda v: f"slot{v}")
def test_the_spawn_records_which_template_it_came_from(template_slot):
    _run_spawn(f"template slot {template_slot}", template_slot, 0x10)


def test_the_slot_bytes_signed_shift_is_an_equivalence_at_the_byte():
    """`asr.l #5` is arithmetic and `lsr.l #5` is not, but only their top five bits differ — and the
    spawn stores the LOW BYTE, which is bits 5..12 of the difference either way. So a reconstruction
    that used an unsigned shift cannot be told apart by any input, and the mutation sweep's survivor
    is stated here as the equivalence it is rather than left as a coverage hole."""
    for delta in (0, 32, -32, -1, 1 << 31, (1 << 31) + 96, -(1 << 20) - 64):
        signed = (delta >> TEMPLATE_SLOT_SHIFT) & 0xff
        unsigned = ((delta & 0xffffffff) >> TEMPLATE_SLOT_SHIFT) & 0xff
        assert signed == unsigned, (
            f"the two shifts differ at delta={delta}, so the survivor is a real hole after all")


def test_the_slot_byte_is_a_signed_shift_of_the_whole_longword():
    """The pointer is moved a record ABOVE the template, so the difference is negative and the
    stored byte is the low byte of `-1`."""
    what = "actor_spawn_from_template with the pointer above the template"
    pokes = _spawn_pokes(case_salt(what), 0, 0x10)
    pokes[TABLE_PTR] = longword(TEMPLATE_TABLE + SPAWN_RECORD_BYTES)
    template = TEMPLATE_TABLE
    record = TABLE_DEFAULT + 5 * RECORD_BYTES

    image = harness.make_image(pokes)
    expected = _model_spawn(image, template, record)
    assert expected[record + TEMPLATE_SLOT] == 0xff, (
        "this case is meant to reach the negative shift, and its model says otherwise")
    info = leaf.run("actor_spawn_from_template", _SPAWN(template, record), merge_bands(expected),
                    what, regs={"a0": template, "a1": record, "_pokes": pokes},
                    max_insns=SPAWN_INSN_CAP)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("record_slot", [0, FOLLOWED_SLOT, SCREEN_RECORD_COUNT - 1],
                         ids=lambda v: f"into{v}")
def test_the_spawn_fills_in_whichever_record_it_is_handed(record_slot):
    """a1 is the only thing that says where the record is, and the seeded band puts different bytes
    in every one of them."""
    _run_spawn(f"into slot {record_slot}", 2, 0x10, record_slot=record_slot)


# --- $2af2 and $14d6: the two state steps ----------------------------------------------------------
# The flag seeds are the same four the side-flag battery uses: the bits this routine touches already
# raised, already clear, and both with every NEIGHBOURING bit set, which a byte-wide `bset`/`bclr`
# must leave alone.
STATE_INSN_CAP = 16
STATE_FLAG_SEEDS = (0x00, 0xff, 1 << SUPPORTED_BIT, 0xff ^ (1 << SUPPORTED_BIT))
LAUNCH_SPEEDS = (0, 1, FALL_SPEED_MAX, 0xff, 0xdeadbe07)


@pytest.mark.parametrize("speed", LAUNCH_SPEEDS, ids=lambda v: f"d0{v:#x}")
@pytest.mark.parametrize("flags", STATE_FLAG_SEEDS, ids=lambda v: f"flags{v:#04x}")
def test_the_launch_clears_the_supported_bit_and_stores_the_speed_byte(flags, speed):
    """`move.b d0,11(a0)` takes ONE byte of d0, which the last seed is what pins."""
    actor = TABLE_DEFAULT + 4 * RECORD_BYTES
    what = f"actor_start_motion_at_speed flags={flags:#04x} d0={speed:#x}"
    pokes = _state_pokes(case_salt(what), {})
    pokes[actor + ACTOR_FLAGS] = bytes([flags])

    expected = {
        actor + ACTOR_FLAGS: (flags & ~(1 << SUPPORTED_BIT)
                              | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & 0xff,
        actor + SPEED: speed & 0xff,
    }
    info = leaf.run("actor_start_motion_at_speed", _START_MOTION(actor, speed),
                    merge_bands(expected), what,
                    regs={"a0": actor, "d0": speed, "_pokes": pokes}, max_insns=STATE_INSN_CAP)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("speed", [0, 1, FALL_SPEED_MAX - 1, FALL_SPEED_MAX, FALL_SPEED_MAX + 1,
                                   0xff], ids=lambda v: f"speed{v:#04x}")
@pytest.mark.parametrize("flags", STATE_FLAG_SEEDS, ids=lambda v: f"flags{v:#04x}")
def test_the_fall_accelerates_up_to_an_exact_terminal_speed(flags, speed):
    """Both sides of the `cmpi.b #$8` and the two cases that show it is an EQUALITY: a record
    already ABOVE the terminal speed keeps climbing, and $ff wraps to 0 rather than saturating."""
    actor = TABLE_DEFAULT + 4 * RECORD_BYTES
    what = f"actor_accelerate_fall flags={flags:#04x} speed={speed:#04x}"
    pokes = _state_pokes(case_salt(what), {})
    pokes[actor + ACTOR_FLAGS] = bytes([flags])
    pokes[actor + SPEED] = bytes([speed])

    expected = {actor + ACTOR_FLAGS: (flags & ~(1 << SUPPORTED_BIT)
                                      | (1 << FALLING_BIT)) & 0xff}
    if speed != FALL_SPEED_MAX:
        expected[actor + SPEED] = (speed + 1) & 0xff
    info = leaf.run("actor_accelerate_fall", _ACCELERATE_FALL(actor), merge_bands(expected), what,
                    regs={"a0": actor, "_pokes": pokes}, max_insns=STATE_INSN_CAP)
    _assert_writes(info, expected, what)
    assert info["regs"]["d0"] == speed, (
        f"{what}: the original left d0={info['regs']['d0']:#x}, not the pre-increment {speed:#x}")
