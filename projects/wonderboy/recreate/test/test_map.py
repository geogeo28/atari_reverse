"""Differential test for src/map.c — the collision map: the leftward step probe ($10a2), the
platform settle ($1400) and the 2x2 tile stamp ($1af0).

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and states the original's write set EXACTLY against a
Python model of the routine.

FOUR THINGS SHAPE THIS BATTERY.

  * THE MAP IS SEEDED, BECAUSE THE GAME LOADS IT. WB_COLLISION_MAP_A32 is all zero in the .PRG
    below its stride word and WB_COLLISION_MAP_DEFAULT lies past the program's last byte
    altogether, so neither carries shipped data a case could read. Both are plain RAM the game
    fills at run time, so every case seeds a window of each ADDRESS-KEYED and then pokes the
    handful of cells it means to test — no shipped record is fabricated, which is the distinction
    CLAUDE.md's coverage rule draws.
  * THE TWO STRIDES ARE SEEDED APART. $10a2 picks its map with `tst.w $a32.w` but reads the row
    stride its ground test walks by from WB_COLLISION_MAP_DEFAULT unconditionally. Seeding the two
    stride words to the same number would hide that; every case here gives them different values,
    and `test_the_ground_test_walks_by_the_default_maps_stride` is the case a "fixed" port fails.
  * NEITHER PROBE RUNS THE ATTRIBUTION (POISON) PASS. Both READ the actor x word they also write
    ($10a2 in its own retry loop), so poisoning the oracle's outputs feeds a different position
    back into the walk — the two cores would still agree, but on a case nobody chose, and a
    poisoned x can make the loop run 65,535 times. They run with `poison=False` and an EXACT write
    set compared against a model instead, which is `text_run_message_box`'s reason and precedent.
  * THE WHOLE RESULT OF $10a2 IS TWO REGISTERS. d0 carries the outcome byte over a low word that
    still holds the probe's map column, and d1 the ground flags over a high word the `mulu.w` left
    there. The reconstruction returns d0 and hands d1 back through a pointer, and every case
    compares BOTH against the oracle's own.

KNOWINGLY NOT PINNED
  * WHAT THE TILE CODES MEAN. $1, $2 and $23 are named for the tests that read them; that they are
    "wall", "ledge" and "platform" is not established.
  * WHAT WB_RECORD_PTR_10420 POINTS AT. The stamp reads two of its fields and nothing here bounds
    the record or says which of its twenty readers — fourteen `movea.l` sites plus six that copy the
    pointer to its neighbour — agree about its shape.
  * $13c8, WHICH HANDS $1400 THREE OF ITS FOUR ARGUMENTS. It writes no memory, so a case could only
    compare the registers it leaves: d0 (the probe's column) and d1 (its row) the kit's oracle DOES
    report, but the LOAD-BEARING output — the map it selected, the cell pointer, the span and the
    sub-cell — is a6/d2/d3/d7, and none of those are reportable. Half-covering it is not worth a
    reconstruction, so it is not ported — see ../STATUS.md. The cases below supply those registers
    directly.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, RTS, branch, branch_over, case_salt, keyed_block, lea_abs_l,
                  lea_indexed, longword, merge_bands, move_w_abs_l_dn, move_w_ind_dn, moveq_0_dn,
                  opcode, program_writes, s16, sub_w_dn_dn, subi_w_dn, tst_w_abs_w, u16, word)
from layout import wb

# --- the globals and the geometry, from the header both languages read ---------------------------
FLAG_A32 = wb("STATE_FLAG_A32")
MAP_A32 = wb("COLLISION_MAP_A32")
MAP_DEFAULT = wb("COLLISION_MAP_DEFAULT")
MAP_CELLS = wb("COLLISION_MAP_CELLS")
CELL_SHIFT = wb("MAP_CELL_SHIFT")
CELL_PIXELS = wb("MAP_CELL_PIXELS")
CELL_MASK = wb("MAP_CELL_MASK")
TILE_BLOCK = wb("MAP_TILE_BLOCK")
TILE_LEDGE = wb("MAP_TILE_LEDGE")
TILE_PLATFORM = wb("MAP_TILE_PLATFORM")
STEP_CLEAR = wb("MAP_STEP_CLEAR")
STEP_BLOCKED = wb("MAP_STEP_BLOCKED")
GROUND_HEAD_BIT = wb("MAP_GROUND_HEAD_BIT")
GROUND_NEAR_BIT = wb("MAP_GROUND_NEAR_BIT")
GROUND_FAR_BIT = wb("MAP_GROUND_FAR_BIT")
PLATFORM_Y = wb("PLATFORM_Y")
PLATFORM_Y_ABOVE = wb("PLATFORM_Y_ABOVE")
PLATFORM_Y_BAND = wb("PLATFORM_Y_BAND")
PLATFORM_STAND_OFFSET = wb("PLATFORM_STAND_OFFSET")
RECORD_PTR = wb("RECORD_PTR_10420")
RECORD_VARIANT = wb("RECORD_10420_VARIANT")
RECORD_CELL = wb("RECORD_10420_CELL")
STAMP_VARIANT_SELECTOR = wb("STAMP_VARIANT_SELECTOR")
STAMP_CELL_BIAS = wb("STAMP_CELL_BIAS")
STAMP_TILES_FIRST = wb("STAMP_TILES_FIRST")
STAMP_TILES_SECOND = wb("STAMP_TILES_SECOND")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")

ACTOR_X = wb("ACTOR_X")
ACTOR_Y = wb("ACTOR_Y")
ACTOR_TYPE = wb("ACTOR_TYPE")
ACTOR_TYPE_PLAYER = wb("ACTOR_TYPE_PLAYER")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
FLAGS2 = wb("ACTOR_FLAGS2")
SPEED = wb("ACTOR_SPEED")
HALF_WIDTH = wb("ACTOR_HALF_WIDTH")
FIELD_22 = wb("ACTOR_FIELD_22")
SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
FALLING_BIT = wb("ACTOR_FLAG_FALLING_BIT")
LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
LANDED_BIT = wb("ACTOR_FLAGS2_LANDED_BIT")
TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
RECORD_BYTES = wb("ACTOR_RECORD_BYTES")

WORD_LEN = 2
BYTE_MASK = 0xff
WORD_MASK = 0xffff

# --- register numbers, and the opcodes only this battery spells ------------------------------------
A0, A1, A2, A6 = 0, 1, 2, 6
D0, D1, D2, D3, D6, D7 = 0, 1, 2, 3, 6, 7

BNE_W, BEQ_W, BPL_W, BLT_W, BGT_W, BRA_W = 0x6600, 0x6700, 0x6a00, 0x6d00, 0x6e00, 0x6000
BSET_IMM, BCLR_IMM, BTST_IMM = 0x08c0, 0x0880, 0x0800


def branch_s_back(condition, spanned_bytes):
    """A SHORT branch back over ``spanned_bytes`` — the two probes close their loops with these,
    and $1400 rejoins its unsupported arm from two places the same way."""
    displacement = -(spanned_bytes + BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a byte displacement"
    return opcode(condition | (displacement & BYTE_MASK))


def move_b_imm_dn(reg, value):
    return opcode(0x103c | (reg << 9)) + word(value)


def move_b_dn_dn(destination, source):
    return opcode(0x1000 | (destination << 9) | source)


def move_w_dn_dn(destination, source):
    return opcode(0x3000 | (destination << 9) | source)


def move_w_postinc_dn(reg, base):
    return opcode(0x3018 | (reg << 9) | base)


def move_w_d16_ind(source, displacement, destination):
    return opcode(0x3080 | (destination << 9) | 0x28 | source) + word(displacement)


def move_w_abs_l_d16(addr, base, displacement):
    return opcode(0x3179 | (base << 9)) + longword(addr) + word(displacement)


def movea_l_abs_l(reg, addr):
    return opcode(0x2079 | (reg << 9)) + longword(addr)


def sub_w_d16_dn(reg, base, displacement):
    return opcode(0x9068 | (reg << 9) | base) + word(displacement)


def sub_w_dn_ind(reg, base):
    return opcode(0x9150 | (reg << 9) | base)


def add_w_dn_dn(destination, source):
    return opcode(0xd040 | (destination << 9) | source)


def mulu_w_dn_dn(destination, source):
    return opcode(0xc0c0 | (destination << 9) | source)


def asr_w_imm_dn(count, reg):
    return opcode(0xe040 | ((count & 7) << 9) | reg)


def neg_w_dn(reg):
    return opcode(0x4440 | reg)


def tst_w_dn(reg):
    return opcode(0x4a40 | reg)


def clr_w_dn(reg):
    return opcode(0x4240 | reg)


def clr_b_d16(base, displacement):
    return opcode(0x4228 | base) + word(displacement)


def andi_w_dn(reg, value):
    return opcode(0x0240 | reg) + word(value)


def addi_w_dn(reg, value):
    return opcode(0x0640 | reg) + word(value)


def ori_w_dn(reg, value):
    return opcode(0x0040 | reg) + word(value)


def subi_w_d16(base, value, displacement):
    return opcode(0x0468 | base) + word(value) + word(displacement)


def subq_w_dn(amount, reg):
    return opcode(0x5140 | ((amount & 7) << 9) | reg)


def addq_w_dn(amount, reg):
    return opcode(0x5040 | ((amount & 7) << 9) | reg)


def addq_l_an(amount, reg):
    return opcode(0x5088 | ((amount & 7) << 9) | reg)


def cmp_w_dn_dn(destination, source):
    return opcode(0xb040 | (destination << 9) | source)


def cmp_w_d16_dn(reg, base, displacement):
    return opcode(0xb068 | (reg << 9) | base) + word(displacement)


def cmpi_b_ind(base, value):
    return opcode(0x0c10 | base) + word(value)


def cmpi_b_indexed(base, index, value):
    """`cmpi.b #imm,0(An,Dn.w)` — how the ground test reaches a row up or down."""
    return opcode(0x0c30 | base) + word(value) + word(index << 12)


def cmpi_w_dn(reg, value):
    return opcode(0x0c40 | reg) + word(value)


def cmpi_w_d16(base, value, displacement):
    return opcode(0x0c68 | base) + word(value) + word(displacement)


def bit_op_d16(op, bit, reg, displacement):
    return opcode(op | 0x28 | reg) + word(bit) + word(displacement)


def move_b_imm_ind(base, value):
    return opcode(0x10bc | (base << 9)) + word(value)


def move_b_imm_postinc(base, value):
    return opcode(0x10fc | (base << 9)) + word(value)


def move_b_imm_d16(base, value, displacement):
    return opcode(0x117c | (base << 9)) + word(value) + word(displacement)


def adda_w_abs_l(reg, addr):
    return opcode(0xd0f9 | (reg << 9)) + longword(addr)


# --- the entry pins -------------------------------------------------------------------------------
# Each is the routine's WHOLE body, assembled from the header's constants and the geometry.
#
# A word-form branch is one opcode plus its displacement; a short one is the opcode alone. Both
# lengths are needed BEFORE the blocks they jump over can be assembled, so they come off the
# encoders rather than being written as 4 and 2.
BRANCH_W_LEN = len(branch_over(BRA_W, 0))
BRANCH_S_LEN = len(branch_s_back(BRA_W, 0))


def _cell_lookup(column_reg, row_reg):
    """The five instructions that turn a (column, row) pair into a cell pointer — the block $13c8
    spells too, and the reason src/map.c has one `cell_pointer` helper rather than two."""
    return (tst_w_abs_w(FLAG_A32)
            + branch(BEQ_W, lea_abs_l(A6, MAP_A32), branch(BRA_W, b""))
            + lea_abs_l(A6, MAP_A32) + branch(BRA_W, lea_abs_l(A6, MAP_DEFAULT))
            + lea_abs_l(A6, MAP_DEFAULT)
            + move_w_postinc_dn(D2, A6) + mulu_w_dn_dn(row_reg, D2)
            + add_w_dn_dn(row_reg, column_reg)
            + lea_indexed(A6, row_reg, MAP_CELLS - WORD_LEN))


def _ground_test():
    """The tail: the cell itself, then one row and two rows away by the DEFAULT map's stride."""
    probe_near = cmpi_b_indexed(A6, D7, TILE_BLOCK)
    ledge_test = cmpi_b_indexed(A6, D7, TILE_LEDGE)
    far_flag = ori_w_dn(D1, GROUND_FAR_BIT)
    head_flag = ori_w_dn(D1, GROUND_HEAD_BIT)
    done = RTS
    far_arm = (ori_w_dn(D1, GROUND_NEAR_BIT) + add_w_dn_dn(D7, D7)
               + cmpi_b_indexed(A6, D7, TILE_BLOCK)
               + branch_over(BEQ_W, len(ledge_test) + BRANCH_W_LEN + len(far_flag))
               + ledge_test + branch(BEQ_W, far_flag)
               + far_flag + done)
    below_arm = (probe_near
                 + branch_over(BEQ_W, len(ledge_test) + BRANCH_W_LEN + len(far_arm) - len(done))
                 + ledge_test
                 + branch_over(BEQ_W, len(far_arm) - len(done))
                 + far_arm)
    above_arm = (neg_w_dn(D7) + probe_near
                 + branch_over(BEQ_W, len(head_flag) + len(RTS) + len(below_arm) - len(done))
                 + head_flag + RTS)
    return (move_w_abs_l_dn(D7, MAP_DEFAULT) + clr_w_dn(D1)
            + cmpi_b_ind(A6, TILE_BLOCK) + branch(BNE_W, above_arm)
            + above_arm + below_arm)


def _step_left_entry():
    tail = _ground_test()
    commit = sub_w_dn_ind(D7, A0) + move_b_dn_dn(D0, D6)
    clamped = move_b_imm_dn(D0, STEP_BLOCKED) + branch(BRA_W, commit)
    head = (moveq_0_dn(D0) + moveq_0_dn(D1)
            + move_w_ind_dn(D0, A0, ACTOR_X) + sub_w_d16_dn(D0, A0, HALF_WIDTH)
            + sub_w_dn_dn(D0, D7) + move_w_dn_dn(D3, D0) + asr_w_imm_dn(CELL_SHIFT, D0)
            + move_w_ind_dn(D1, A0, ACTOR_Y) + subq_w_dn(1, D1) + asr_w_imm_dn(CELL_SHIFT, D1)
            + _cell_lookup(D0, D1))
    clamp_x = move_w_d16_ind(A0, HALF_WIDTH, A0)
    # The clear arm's own length, needed by the blocked arm's two BACKWARD branches before the arm
    # itself can be assembled — its own forward branches depend on the blocked arm in turn.
    clear_arm_len = (len(cmpi_b_ind(A6, TILE_BLOCK)) + BRANCH_W_LEN + len(tst_w_dn(D3))
                     + BRANCH_W_LEN + len(clamp_x) + BRANCH_W_LEN)

    blocked = move_b_imm_dn(D6, STEP_BLOCKED) + subq_w_dn(1, D7)
    player_test = cmpi_w_d16(A0, ACTOR_TYPE_PLAYER, ACTOR_TYPE)
    clear_field = clr_b_d16(A0, FIELD_22)
    # Both loop-closing branches jump back to `head`, i.e. past the entry's one leading instruction.
    to_head = len(head) + clear_arm_len
    at_bne = len(blocked) + BRANCH_W_LEN + len(player_test)
    at_bra = at_bne + BRANCH_S_LEN + len(clear_field)
    retry = player_test + branch_s_back(BNE_W, to_head + at_bne) + clear_field
    blocked_arm = (blocked
                   + branch_over(BEQ_W, len(retry) + BRANCH_S_LEN + len(clamped))
                   + retry
                   + branch_s_back(BRA_W, to_head + at_bra))

    clear_arm = (cmpi_b_ind(A6, TILE_BLOCK)
                 + branch_over(BEQ_W, len(tst_w_dn(D3)) + BRANCH_W_LEN + len(clamp_x)
                               + BRANCH_W_LEN)
                 + tst_w_dn(D3)
                 + branch_over(BPL_W, len(clamp_x) + BRANCH_W_LEN + len(blocked_arm)
                               + len(clamped))
                 + clamp_x
                 + branch_over(BRA_W, len(blocked_arm)))
    assert len(clear_arm) == clear_arm_len
    return (move_b_imm_dn(D6, STEP_CLEAR) + head + clear_arm + blocked_arm + clamped + commit
            + tail)


def _settle_entry():
    landed = (move_w_abs_l_d16(PLATFORM_Y, A0, ACTOR_Y)
              + subi_w_d16(A0, PLATFORM_STAND_OFFSET, ACTOR_Y)
              + bit_op_d16(BSET_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BSET_IMM, LANDED_BIT, A0, FLAGS2)
              + bit_op_d16(BCLR_IMM, FALLING_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BCLR_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS)
              + clr_b_d16(A0, SPEED) + RTS)
    unsupported = (bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
                   + branch(BNE_W, bit_op_d16(BSET_IMM, FALLING_BIT, A0, ACTOR_FLAGS))
                   + bit_op_d16(BSET_IMM, FALLING_BIT, A0, ACTOR_FLAGS)
                   + bit_op_d16(BCLR_IMM, LANDED_BIT, A0, FLAGS2) + RTS)
    probe = addq_l_an(1, A6) + cmpi_b_ind(A6, TILE_PLATFORM)
    subcell = (moveq_0_dn(D0) + move_w_dn_dn(D0, D7) + asr_w_imm_dn(1, D0) + neg_w_dn(D0)
               + andi_w_dn(D0, CELL_MASK) + cmp_w_dn_dn(D2, D0)
               + branch_over(BLT_W, len(probe) + BRANCH_W_LEN)
               + probe + branch_over(BEQ_W, len(unsupported)))
    step = addq_l_an(1, A6) + subi_w_dn(D7, CELL_PIXELS)
    span_test = cmpi_w_dn(D7, CELL_PIXELS)
    scan = (cmpi_b_ind(A6, TILE_PLATFORM)
            + branch_over(BEQ_W, len(span_test) + BRANCH_W_LEN + len(step) + BRANCH_S_LEN
                          + len(subcell) + len(unsupported))
            + span_test
            + branch_over(BLT_W, len(step) + BRANCH_S_LEN)
            + step)
    scan += branch_s_back(BRA_W, len(scan))
    band = (move_w_abs_l_dn(D0, PLATFORM_Y) + move_w_ind_dn(D1, A0, ACTOR_Y)
            + subi_w_dn(D0, PLATFORM_Y_ABOVE) + cmp_w_dn_dn(D0, D1))
    # Both band branches rejoin `unsupported`, which sits directly above the landing arm.
    tail = addq_w_dn(PLATFORM_Y_BAND, D0) + cmp_w_d16_dn(D0, A0, ACTOR_Y)
    return (scan + subcell + unsupported
            + band + branch_s_back(BGT_W, len(unsupported) + len(band))
            + tail + branch_s_back(BLT_W, len(unsupported) + len(band) + BRANCH_S_LEN + len(tail))
            + landed)


def _stamp_arm(first_tile):
    return (move_b_imm_ind(A2, first_tile)
            + move_b_imm_d16(A2, first_tile + 1, 1)
            + adda_w_abs_l(A2, MAP_ROW_STRIDE)
            + move_b_imm_postinc(A2, first_tile + 2)
            + move_b_imm_postinc(A2, first_tile + 3) + RTS)


def _stamp_entry():
    return (movea_l_abs_l(A1, RECORD_PTR)
            + move_w_ind_dn(D0, A1, RECORD_CELL) + addi_w_dn(D0, STAMP_CELL_BIAS)
            + lea_abs_l(A2, MAP_ROW_STRIDE) + lea_indexed(A2, D0)
            + cmpi_w_d16(A1, STAMP_VARIANT_SELECTOR, RECORD_VARIANT)
            + branch(BEQ_W, _stamp_arm(STAMP_TILES_FIRST))
            + _stamp_arm(STAMP_TILES_FIRST) + _stamp_arm(STAMP_TILES_SECOND))


ENTRY_BYTES = {
    "actor_step_left_against_map": _step_left_entry(),
    "actor_settle_on_platform": _settle_entry(),
    "map_stamp_block": _stamp_entry(),
}
RECONSTRUCTED_ROUTINES = 3


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("actor_step_left_against_map", 206),
    ("actor_settle_on_platform", 146),
    ("map_stamp_block", 86),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The pins above would still pass on a PREFIX. These are the sizes the Ghidra function table
    records (../out/hw_scan.tsv), so a body one instruction short fails here."""
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records")


def test_the_two_tile_runs_the_stamp_writes_are_consecutive():
    """src/map.c writes `tile`, `tile + 1`, `tile + 2`, `tile + 3` where the original spells four
    separate immediates. The entry pin is built the same way, so this is what says the abstraction
    is legitimate: the eight bytes really are two runs of four."""
    entry = leaf.entry_of("map_stamp_block")
    body = bytes(harness.BASE_IMAGE[entry:entry + len(ENTRY_BYTES["map_stamp_block"])])
    for first in (STAMP_TILES_FIRST, STAMP_TILES_SECOND):
        for step in range(4):
            assert body.count(word(first + step)) >= 1, (
                f"the stamp never writes {first + step:#04x}, so its four tiles are not the "
                f"consecutive run src/map.c assumes")
    assert STAMP_TILES_SECOND == STAMP_TILES_FIRST + 4, (
        f"the two runs are not back to back ({STAMP_TILES_FIRST:#x}, {STAMP_TILES_SECOND:#x})")


def test_the_platform_word_is_actor_slot_eights_own_y():
    """WB_PLATFORM_Y is not a global of its own: it is a record of the default actor table. Stated
    as arithmetic over the header's constants, so a moved table fails here rather than silently
    decoupling the two names. Which actor occupies that slot is NOT established."""
    slot = (PLATFORM_Y - ACTOR_Y - TABLE_DEFAULT) / RECORD_BYTES
    assert slot == int(slot) and 0 <= slot, (
        f"{PLATFORM_Y:#x} is not a whole record into the table at {TABLE_DEFAULT:#x}")
    assert TABLE_DEFAULT + int(slot) * RECORD_BYTES + ACTOR_Y == PLATFORM_Y


def test_the_cell_lookups_bias_is_the_background_maps_own():
    """`lea 2(a6,d3.w)` after a `move.w (a6)+` puts cell 0 at base + 4 — the same offset
    WB_MAP_DATA_ROW sits at above WB_MAP_ROW_STRIDE, which is what says the two maps share a
    layout. The stamp's `addi.w #$4` is the third spelling of the same number."""
    assert wb("MAP_DATA_ROW") - wb("MAP_ROW_STRIDE") == MAP_CELLS
    assert STAMP_CELL_BIAS == MAP_CELLS
    assert CELL_PIXELS == 1 << CELL_SHIFT
    assert CELL_MASK == CELL_PIXELS - 1


# --- seeding --------------------------------------------------------------------------------------
# The two maps and the background map the stamp writes into, each as a window big enough for the
# rows a case reaches, seeded ADDRESS-KEYED so that a walk that took the wrong stride, the wrong
# map or the wrong bias lands on bytes that are wrong FOR WHERE THEY WERE WRITTEN.
#
# The two STRIDES are deliberately different numbers: $10a2 looks its cell up in the map
# WB_STATE_FLAG_A32 names but steps its ground test by WB_COLLISION_MAP_DEFAULT's stride whatever
# that flag says, and equal strides would make the two indistinguishable.
A32_STRIDE = 0x28
DEFAULT_STRIDE = 0x20
MAP_WINDOW_ROWS = 12
MAP_WINDOW_COLUMNS = 0x240          # wide enough for the far-column case below
PROBE_ROW = 5                       # comfortably inside the window, with rows above and below
MARGIN = 0x20                       # ...and a margin either side, so an over-run is visible


def _map_window(stride):
    return MAP_CELLS + stride * MAP_WINDOW_ROWS + MAP_WINDOW_COLUMNS + MARGIN


def _cell_of(base, stride, column, row):
    return base + MAP_CELLS + stride * row + column


ACTOR = TABLE_DEFAULT + 3 * RECORD_BYTES      # any record but the followed one or slot 8


def _map_pokes(salt, a32_stride=A32_STRIDE, default_stride=DEFAULT_STRIDE):
    """Both maps seeded, their stride words set, and a margin below each."""
    pokes = {}
    for base, stride in ((MAP_A32, a32_stride), (MAP_DEFAULT, default_stride)):
        window = _map_window(stride)
        pokes[base - MARGIN] = keyed_block(base - MARGIN, window + MARGIN, salt)
        pokes[base] = word(stride)
    return pokes


def _assert_writes(info, expected, what):
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {sorted(hex(a) for a in written)} against the model's "
        f"{sorted(hex(a) for a in expected)}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")


def _put_word(out, addr, value):
    for offset, byte in enumerate(word(value)):
        out[addr + offset] = byte


# --- glue -------------------------------------------------------------------------------------------
_SETTLE = leaf.register_glue("actor_settle_on_platform", [ctypes.c_uint32] * 4)
_STAMP = leaf.image_glue("map_stamp_block")
_STEP_LEFT_FN = leaf.bind("actor_step_left_against_map",
                          leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.c_uint32,
                                            ctypes.POINTER(ctypes.c_uint32)],
                          ctypes.c_uint32)


def _step_left_glue(actor, step, ground):
    """$10a2's result is TWO registers, so the reconstruction hands d1 back through a pointer and
    the case reads it after the run — `leaf.register_glue` covers only a d0."""
    return lambda _lib, image: _STEP_LEFT_FN(image, actor, step, ctypes.byref(ground))


# --- $10a2: the leftward step ---------------------------------------------------------------------
# The retry loop is ~20 instructions and runs at most `step` times; the tail adds a handful. The cap
# is that geometry, so a case that ran away fails loudly instead of returning something plausible.
STEP_INSN_PER_RETRY = 24
STEP_INSN_TAIL = 32


def _model_step_left(image, actor, step, a32):
    """{writes}, d0, d1 — the original's own arithmetic, in Python."""
    remaining = step & WORD_MASK
    outcome = STEP_CLEAR
    writes = {}
    map_base = MAP_A32 if a32 else MAP_DEFAULT

    while True:
        probe = (u16(image, actor + ACTOR_X) - u16(image, actor + HALF_WIDTH)
                 - remaining) & WORD_MASK
        column = (s16(probe) >> CELL_SHIFT) & WORD_MASK
        row = (s16((u16(image, actor + ACTOR_Y) - 1) & WORD_MASK) >> CELL_SHIFT) & WORD_MASK
        product = (u16(image, map_base) * row) & 0xffffffff
        index = (product + column) & WORD_MASK
        cell = (map_base + MAP_CELLS + s16(index)) & 0xffffffff

        def tile(at):
            return writes.get(at, image[at])

        if tile(cell) != TILE_BLOCK:
            if s16(probe) >= 0:
                _put_word(writes, actor + ACTOR_X,
                          u16(image, actor + ACTOR_X) - remaining)
            else:
                _put_word(writes, actor + ACTOR_X, u16(image, actor + HALF_WIDTH))
                outcome = STEP_BLOCKED
            break
        outcome = STEP_BLOCKED
        remaining = (remaining - 1) & WORD_MASK
        if remaining == 0:
            _put_word(writes, actor + ACTOR_X, u16(image, actor + ACTOR_X) - remaining)
            break
        if u16(image, actor + ACTOR_TYPE) == ACTOR_TYPE_PLAYER:
            writes[actor + FIELD_22] = 0

    stride = u16(image, MAP_DEFAULT)

    def at(offset):
        return image[(cell + s16(offset)) & 0xffffffff]

    if image[cell] == TILE_BLOCK:
        flags = 0 if at(-stride & WORD_MASK) == TILE_BLOCK else GROUND_HEAD_BIT
    elif at(stride) in (TILE_BLOCK, TILE_LEDGE):
        flags = 0
    else:
        flags = GROUND_NEAR_BIT
        if at((stride + stride) & WORD_MASK) not in (TILE_BLOCK, TILE_LEDGE):
            flags |= GROUND_FAR_BIT

    d0 = (column & 0xff00) | outcome
    d1 = (product & 0xffff0000) | flags
    return writes, d0, d1


def probe_cell(actor_x, half_width, step):
    """The COLUMN and ROW the first probe lands in — `(x - half_width - step) asr.w #4` and
    `(y - 1) asr.w #4`. A case's tiles are keyed relative to this, because the step is part of the
    column: keying them off `x - half_width` alone plants them a cell away from where the routine
    actually looks, and the case then passes on bytes it did not mean to seed."""
    probe = (actor_x - half_width - step) & WORD_MASK
    return s16(probe) >> CELL_SHIFT, PROBE_ROW


def _run_step_left(case, actor_x, half_width, step, tiles, a32=False, actor_type=0,
                   default_stride=DEFAULT_STRIDE, actor_y=None):
    """One step-left case. ``tiles`` is {(column offset, row offset): code} RELATIVE to the cell the
    first probe lands in, in the SELECTED map's own grid."""
    salt = case_salt(case)
    pokes = _map_pokes(salt, default_stride=default_stride)
    pokes[FLAG_A32] = word(0xffff if a32 else 0)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_X] = word(actor_x)
    pokes[ACTOR + ACTOR_Y] = word(PROBE_ROW * CELL_PIXELS + 1 if actor_y is None else actor_y)
    pokes[ACTOR + HALF_WIDTH] = word(half_width)
    pokes[ACTOR + ACTOR_TYPE] = word(actor_type)

    stride = A32_STRIDE if a32 else default_stride
    base = MAP_A32 if a32 else MAP_DEFAULT
    column, row = probe_cell(actor_x, half_width, step & WORD_MASK)
    for (dcolumn, drow), code in tiles.items():
        pokes[_cell_of(base, stride, column + dcolumn, row + drow)] = bytes([code])

    image = harness.make_image(pokes)
    expected, d0, d1 = _model_step_left(image, ACTOR, step, a32)

    ground = ctypes.c_uint32(0)
    what = f"actor_step_left_against_map {case}"
    info = leaf.run("actor_step_left_against_map", _step_left_glue(ACTOR, step, ground),
                    merge_bands(expected), what, regs={"a0": ACTOR, "d7": step, "_pokes": pokes},
                    poison=False,
                    max_insns=STEP_INSN_PER_RETRY * ((step & WORD_MASK) + 1) + STEP_INSN_TAIL)

    _assert_writes(info, expected, what)
    assert info["regs"]["d0"] == d0, (
        f"{what}: the original returned d0={info['regs']['d0']:#010x}, not {d0:#010x}")
    assert info["ret"] == d0, (
        f"{what}: the reconstruction returned {info['ret']:#010x} against the original's {d0:#010x}")
    assert info["regs"]["d1"] == d1, (
        f"{what}: the original returned d1={info['regs']['d1']:#010x}, not {d1:#010x}")
    assert ground.value == d1, (
        f"{what}: the reconstruction's ground word is {ground.value:#010x}, not {d1:#010x}")
    return info


# Every case below is written against actor_x = $200 and half_width = $10; `tiles` keys are
# offsets from the cell the FIRST probe lands in, which `probe_cell` computes.
STEP_X = 0x200
STEP_HALF_WIDTH = 0x10
HERE = (0, 0)


@pytest.mark.parametrize("case,step,tiles,expect_blocked", [
    # Nothing in the way: the first probe is already clear and the whole step is committed.
    ("clear", 8, {}, False),
    # The cell the first probe lands in is a block, and backing off leaves it in the next cell.
    ("blocked-then-clear", 0x11, {HERE: TILE_BLOCK}, True),
    # ...and a case where backing off has to cross a whole further cell.
    ("blocked-two-cells", 0x21, {HERE: TILE_BLOCK, (1, 0): TILE_BLOCK}, True),
    # A zero step: the probe is the actor's own left edge, and the commit writes x unchanged.
    ("zero-step", 0, {}, False),
    # ...and a block the actor can never back out of, which runs the step down to an EXACT zero and
    # commits a move of nothing — the one arm that writes x without having gone anywhere.
    ("blocked-everywhere", 4, {HERE: TILE_BLOCK}, True),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_step_stops_at_the_first_blocking_cell(case, step, tiles, expect_blocked):
    info = _run_step_left(case, STEP_X, STEP_HALF_WIDTH, step, tiles)
    blocked = (info["regs"]["d0"] & BYTE_MASK) == STEP_BLOCKED
    assert blocked == expect_blocked, (
        f"{case}: the routine reported {'blocked' if blocked else 'clear'}, which is not what this "
        f"case is about")


def test_the_step_parks_the_actor_against_the_maps_left_edge():
    """`tst.w d3 / bpl` reads the wrapped probe's own SIGN, so a probe that went past the origin
    takes the arm that writes `x := half_width` instead of committing the move."""
    _run_step_left("off-the-left-edge", actor_x=0x08, half_width=0x10, step=4, tiles={})


def test_the_step_clears_the_players_own_byte_on_every_retry():
    """`cmpi.w #$1,4(a0) / bne` — only a record whose type word is WB_ACTOR_TYPE_PLAYER has
    WB_ACTOR_FIELD_22 cleared, and only on a retry, so this is the one case whose write set is
    larger than the x word."""
    info = _run_step_left("player-retry", STEP_X, STEP_HALF_WIDTH, 0x11, {HERE: TILE_BLOCK},
                          actor_type=ACTOR_TYPE_PLAYER)
    assert ACTOR + FIELD_22 in program_writes(info), (
        "the player arm did not clear its byte, so this case is testing the other one")


def test_a_record_that_is_not_the_player_leaves_that_byte_alone():
    info = _run_step_left("other-retry", STEP_X, STEP_HALF_WIDTH, 0x11, {HERE: TILE_BLOCK},
                          actor_type=ACTOR_TYPE_PLAYER + 1)
    assert ACTOR + FIELD_22 not in program_writes(info)


# The tail reads the cell the walk stopped on, the one a row down and the one two rows down. Every
# case here uses a step of 0, so the cell it stops on IS the cell its tiles are keyed to.
# The tail reads the cell the walk STOPPED on. A walk only stops on a cell that is not a block, so
# the two cases whose cell IS one reach that arm the only way the routine allows: a step of 1 into a
# block, which retries once, runs the step down to zero and commits there.
GROUND_CASES = [
    ("cell-is-a-block-with-air-above", 1, {HERE: TILE_BLOCK}, GROUND_HEAD_BIT),
    ("cell-is-a-block-under-a-block", 1, {HERE: TILE_BLOCK, (0, -1): TILE_BLOCK}, 0),
    ("solid-ground-one-row-down", 0, {(0, 1): TILE_BLOCK}, 0),
    ("ledge-one-row-down", 0, {(0, 1): TILE_LEDGE}, 0),
    ("solid-ground-two-rows-down", 0, {(0, 2): TILE_BLOCK}, GROUND_NEAR_BIT),
    ("ledge-two-rows-down", 0, {(0, 2): TILE_LEDGE}, GROUND_NEAR_BIT),
    ("nothing-underneath", 0, {}, GROUND_NEAR_BIT | GROUND_FAR_BIT),
]


@pytest.mark.parametrize("case,step,tiles,flags", GROUND_CASES, ids=[c[0] for c in GROUND_CASES])
def test_the_ground_flags_report_what_is_under_the_cell(case, step, tiles, flags):
    """All three arms of the tail, plus both tile codes its two tests accept. The model computes the
    expected d1 from the same seeded map and every case compares it against the ORACLE's — and each
    case also STATES the flag word it is about, so a seeded byte that happened to spell $1 or $2
    fails here instead of quietly turning the case into a different one."""
    info = _run_step_left(case, STEP_X, STEP_HALF_WIDTH, step, dict(tiles))
    assert info["regs"]["d1"] & WORD_MASK == flags, (
        f"{case}: the tail reported {info['regs']['d1'] & WORD_MASK:#x}, not the {flags:#x} this "
        f"case is about — a seeded neighbour is spelling a tile code by itself")


def test_the_ground_test_walks_by_the_default_maps_stride():
    """THE ASYMMETRY, and the case a tidied port fails. The cell is looked up in
    WB_COLLISION_MAP_A32 at its own stride, and the row below it is then reached by
    WB_COLLISION_MAP_DEFAULT's — so the byte the ground test reads is NOT the cell one row down in
    the map that was walked. The two strides differ here by A32_STRIDE - DEFAULT_STRIDE."""
    assert A32_STRIDE != DEFAULT_STRIDE, "the two strides must differ for this case to mean anything"
    info = _run_step_left("a32-map-default-stride", STEP_X, STEP_HALF_WIDTH, 0,
                          {(0, 1): TILE_BLOCK, (0, 2): TILE_BLOCK}, a32=True)
    # The two blocks sit a whole A32_STRIDE and two of them below the cell. The tail steps by
    # DEFAULT_STRIDE instead, so it lands between them and reports open ground both times.
    assert (info["regs"]["d1"] & WORD_MASK) == GROUND_NEAR_BIT | GROUND_FAR_BIT, (
        f"the tail read d1={info['regs']['d1'] & WORD_MASK:#x}, so it stepped by the map it walked "
        f"rather than by WB_COLLISION_MAP_DEFAULT's stride")


@pytest.mark.parametrize("high", [0x00000000, 0xdead0000], ids=lambda v: f"d7hi{v >> 16:#06x}")
def test_only_the_low_word_of_the_step_is_read(high):
    """`sub.w d7,d0`, `subq.w #1,d7` and `sub.w d7,(a0)` are all word operations, so a caller's
    rubbish above the step must not reach the walk."""
    _run_step_left(f"step-high-{high:#x}", STEP_X, STEP_HALF_WIDTH, high | 8, {})


def test_the_ground_word_sits_over_the_row_products_high_half():
    """`clr.w d1` clears the LOW word and leaves whatever the `mulu.w` put in the high one, so a
    row times a stride that overflows sixteen bits comes back in the result. The map's own stride
    and the actor's row are both seeded large enough here to reach it."""
    info = _run_step_left("product-over-65535", STEP_X, STEP_HALF_WIDTH, 0, {},
                          default_stride=0x100, actor_y=0x4001)
    assert info["regs"]["d1"] >> 16 != 0, (
        "the row product's high half is zero here, so this case does not reach what it is about")


def test_the_outcome_byte_sits_over_the_probes_own_column():
    """`move.b d6,d0` writes ONE byte of a d0 whose low word still holds the map column, so a
    column above $ff comes back in the result's second byte. An x this far into the map reaches
    it; the model states the whole longword and every case compares it."""
    info = _run_step_left("column-over-255", actor_x=0x2000, half_width=0x10, step=8, tiles={})
    assert info["regs"]["d0"] >> 8 != 0, (
        "the column's high byte is zero here, so this case does not reach what it is about")


# --- $1400: the platform settle -------------------------------------------------------------------
# The scan steps one cell per WB_MAP_CELL_PIXELS of span; the cap is that geometry plus the band
# test and whichever arm runs.
SETTLE_INSN_PER_CELL = 8
SETTLE_INSN_TAIL = 48
SETTLE_COLUMN = 0x20            # the cell $13c8 would have handed over, mid-window


def _model_settle(image, actor, cell, span, subcell):
    remaining = span & WORD_MASK
    cursor = cell
    while image[cursor] != TILE_PLATFORM and s16(remaining) >= CELL_PIXELS:
        cursor = (cursor + 1) & 0xffffffff
        remaining = (remaining - CELL_PIXELS) & WORD_MASK
    found = image[cursor] == TILE_PLATFORM
    if not found:
        edge = (-(s16(remaining) >> 1)) & CELL_MASK
        if s16(subcell & WORD_MASK) >= edge:
            cursor = (cursor + 1) & 0xffffffff
            found = image[cursor] == TILE_PLATFORM

    writes = {}
    flags = image[actor + ACTOR_FLAGS]
    if found:
        actor_y = s16(u16(image, actor + ACTOR_Y))
        top = s16(u16(image, PLATFORM_Y) - PLATFORM_Y_ABOVE)
        if not top > actor_y and not s16(top + PLATFORM_Y_BAND) < actor_y:
            _put_word(writes, actor + ACTOR_Y,
                      u16(image, PLATFORM_Y) - PLATFORM_STAND_OFFSET)
            writes[actor + ACTOR_FLAGS] = ((flags | (1 << SUPPORTED_BIT))
                                           & ~(1 << FALLING_BIT) & ~(1 << LAUNCHED_BIT)) & BYTE_MASK
            writes[actor + FLAGS2] = image[actor + FLAGS2] | (1 << LANDED_BIT)
            writes[actor + SPEED] = 0
            return writes

    if not flags & (1 << SUPPORTED_BIT):
        writes[actor + ACTOR_FLAGS] = flags | (1 << FALLING_BIT)
    writes[actor + FLAGS2] = image[actor + FLAGS2] & ~(1 << LANDED_BIT) & BYTE_MASK
    return writes


def _run_settle(case, span, subcell, tiles, actor_y, platform_y, flags=0):
    salt = case_salt(case)
    pokes = _map_pokes(salt)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_Y] = word(actor_y)
    pokes[ACTOR + ACTOR_FLAGS] = bytes([flags])
    pokes[PLATFORM_Y] = word(platform_y)

    cell = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE, SETTLE_COLUMN, PROBE_ROW)
    for column, code in tiles.items():
        pokes[cell + column] = bytes([code])

    image = harness.make_image(pokes)
    expected = _model_settle(image, ACTOR, cell, span, subcell)

    what = f"actor_settle_on_platform {case}"
    info = leaf.run("actor_settle_on_platform", _SETTLE(ACTOR, cell, span, subcell),
                    merge_bands(expected), what, poison=False,
                    regs={"a0": ACTOR, "a6": cell, "d7": span, "d2": subcell, "_pokes": pokes},
                    max_insns=SETTLE_INSN_PER_CELL * (max(s16(span & WORD_MASK), 0) // CELL_PIXELS
                                                      + 1) + SETTLE_INSN_TAIL)
    _assert_writes(info, expected, what)
    return info


# The actor stands at ON_PLATFORM_Y when the band test accepts it: the arm needs
# `platform - $12 <= y <= platform - $12 + 6`.
PLATFORM = 0x100
IN_BAND_TOP = PLATFORM - PLATFORM_Y_ABOVE
IN_BAND_BOTTOM = IN_BAND_TOP + PLATFORM_Y_BAND


@pytest.mark.parametrize("case,span,subcell,tiles", [
    ("under-the-first-cell", 0, 0, {0: TILE_PLATFORM}),
    ("one-cell-along", CELL_PIXELS, 0, {1: TILE_PLATFORM}),
    ("two-cells-along", 2 * CELL_PIXELS, 0, {2: TILE_PLATFORM}),
    # The leftover span puts the footprint's edge into one more cell only when d2 reaches it.
    ("subcell-reaches-the-next", 2, CELL_MASK, {1: TILE_PLATFORM}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_scan_finds_the_platform_across_the_footprint(case, span, subcell, tiles):
    info = _run_settle(case, span, subcell, tiles, IN_BAND_TOP, PLATFORM)
    assert program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        f"{case}: the actor did not land, so this case is testing the other arm")


def test_the_subcell_test_refuses_the_next_cell_when_the_actor_is_not_far_enough_in():
    """`cmp.w d0,d2 / blt` — d2 BELOW the edge the leftover span computes skips the extra cell, so
    the platform one cell along is not found. The pair with the case above is what pins the
    comparison's direction."""
    info = _run_settle("subcell-short", 2, 0, {1: TILE_PLATFORM}, IN_BAND_TOP, PLATFORM)
    assert not program_writes(info).get(ACTOR + ACTOR_FLAGS, 0) & (1 << SUPPORTED_BIT)


@pytest.mark.parametrize("case,actor_y,lands", [
    ("above-the-band", IN_BAND_TOP - 1, False),
    ("on-the-bands-top", IN_BAND_TOP, True),
    ("inside-the-band", IN_BAND_TOP + 3, True),
    ("on-the-bands-bottom", IN_BAND_BOTTOM, True),
    ("below-the-band", IN_BAND_BOTTOM + 1, False),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_band_test_is_a_signed_comparison_of_both_ends(case, actor_y, lands):
    """Both ends and both sides of each: `cmp.w d1,d0 / bgt` above and `cmp.w 2(a0),d0 / blt`
    below, each a signed comparison of the OPERANDS."""
    info = _run_settle(case, 0, 0, {0: TILE_PLATFORM}, actor_y, PLATFORM)
    landed = bool(program_writes(info).get(ACTOR + ACTOR_FLAGS, 0) & (1 << SUPPORTED_BIT))
    assert landed == lands, f"{case}: landed={landed}, which is not what this case is about"


def test_a_platform_word_that_wraps_the_subtraction():
    """`subi.w #$12,d0` on a small platform y wraps into the negative half, and the `bgt` that
    follows reads the wrapped word as an operand. The model does the same, so a port that widened
    the arithmetic answers differently here."""
    _run_settle("platform-wraps", 0, 0, {0: TILE_PLATFORM}, actor_y=0x7fff, platform_y=8)


@pytest.mark.parametrize("case,flags,starts_falling", [
    ("already-supported", 1 << SUPPORTED_BIT, False),
    ("not-supported", 0, True),
    ("already-falling", 1 << FALLING_BIT, True),
], ids=lambda v: v if isinstance(v, str) else "")
def test_nothing_underfoot_starts_a_fall_only_once(case, flags, starts_falling):
    """`btst #2,8(a0) / bne` over the `bset`: a record still marked supported is left alone, which
    is the gate a zero test would get the wrong way round."""
    info = _run_settle(case, 0, 0, {}, IN_BAND_TOP, PLATFORM, flags=flags)
    written = program_writes(info)
    wrote_flags = ACTOR + ACTOR_FLAGS in written
    assert wrote_flags == starts_falling, (
        f"{case}: the flags byte was {'written' if wrote_flags else 'left alone'}, which is not "
        f"what this case is about")
    assert ACTOR + FLAGS2 in written, "the landed bit is cleared on BOTH unsupported arms"


def test_a_negative_span_never_enters_the_scan():
    """`cmpi.w #$10,d7 / blt` is a SIGNED comparison of the operand, so a span with its top bit set
    fails it at once instead of walking 4096 cells."""
    _run_settle("negative-span", 0x8000, 0, {}, IN_BAND_TOP, PLATFORM)


def test_a_negative_span_still_reaches_the_sub_cell_test():
    """The case that makes the comparison's SIGNEDNESS observable rather than merely cheap: a
    negative span leaves the scan on the cell it started at, and the sub-cell test then finds the
    platform one along. An unsigned reading walks 2049 cells first and lands nowhere near it."""
    info = _run_settle("negative-span-sub-cell", 0x8010, CELL_MASK, {1: TILE_PLATFORM},
                       IN_BAND_TOP, PLATFORM)
    assert program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        "the actor did not land, so this case is not reaching the sub-cell arm")


def test_the_span_is_read_as_a_word():
    """`cmpi.w`/`subi.w` on d7 and `move.w d7,d0` in the sub-cell test: a caller's high half must
    not reach either."""
    _run_settle("span-high-half", 0xdead0000 | CELL_PIXELS, 0, {1: TILE_PLATFORM},
                IN_BAND_TOP, PLATFORM)


# --- $1af0: the 2x2 stamp -------------------------------------------------------------------------
STAMP_INSN_CAP = 24
STAMP_RECORD = 0x30000          # plain RAM, well clear of both maps and the actor tables
STAMP_WINDOW_ROWS = 4


def _model_stamp(image):
    record = int.from_bytes(bytes(image[RECORD_PTR:RECORD_PTR + 4]), "big")
    cell = (u16(image, record + RECORD_CELL) + STAMP_CELL_BIAS) & WORD_MASK
    at = (MAP_ROW_STRIDE + s16(cell)) & 0xffffffff
    tile = (STAMP_TILES_SECOND
            if u16(image, record + RECORD_VARIANT) == STAMP_VARIANT_SELECTOR
            else STAMP_TILES_FIRST)
    below = (at + s16(u16(image, MAP_ROW_STRIDE))) & 0xffffffff
    return {at: tile, at + 1: tile + 1, below: tile + 2, below + 1: tile + 3}


def _run_stamp(case, cell, variant):
    salt = case_salt(case)
    window = STAMP_CELL_BIAS + DEFAULT_STRIDE * STAMP_WINDOW_ROWS + MARGIN
    pokes = {
        MAP_ROW_STRIDE - MARGIN: keyed_block(MAP_ROW_STRIDE - MARGIN, window + MARGIN, salt),
        MAP_ROW_STRIDE: word(DEFAULT_STRIDE),
        STAMP_RECORD: keyed_block(STAMP_RECORD, RECORD_CELL + WORD_LEN, salt),
        RECORD_PTR: longword(STAMP_RECORD),
        STAMP_RECORD + RECORD_CELL: word(cell),
        STAMP_RECORD + RECORD_VARIANT: word(variant),
    }
    image = harness.make_image(pokes)
    expected = _model_stamp(image)

    what = f"map_stamp_block {case}"
    info = leaf.run("map_stamp_block", _STAMP, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=STAMP_INSN_CAP)
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("variant,tile", [(0, STAMP_TILES_FIRST),
                                          (STAMP_VARIANT_SELECTOR, STAMP_TILES_SECOND)],
                         ids=["first-tile-set", "second-tile-set"])
@pytest.mark.parametrize("cell", [0, 1, DEFAULT_STRIDE, 2 * DEFAULT_STRIDE + 3],
                         ids=lambda v: f"cell{v}")
def test_the_stamp_writes_two_by_two_a_row_apart(cell, variant, tile):
    """Both tile sets x four cells, including an ODD one — the two rows are a whole
    WB_MAP_ROW_STRIDE apart and nothing about the pair is aligned."""
    info = _run_stamp(f"stamp-{cell}-{variant}", cell, variant)
    written = program_writes(info)
    assert sorted(written.values()) == [tile, tile + 1, tile + 2, tile + 3], (
        f"the four bytes written are {sorted(written.values())}, not the run from {tile:#x}")


def test_the_stamps_variant_test_is_a_word():
    """`cmpi.w #$4,2(a1)` — a record whose LOW byte alone matches must take the first arm."""
    info = _run_stamp("variant-high-half", 0, (STAMP_VARIANT_SELECTOR << 8)
                      | STAMP_VARIANT_SELECTOR)
    assert min(program_writes(info).values()) == STAMP_TILES_FIRST, (
        "a variant word whose high half is set took the second arm, so the test read a byte")


def test_the_stamps_cell_offset_is_sign_extended():
    """`lea 0(a2,d0.w)` takes the low word SIGN-EXTENDED, so a cell above $7fff addresses BELOW
    WB_MAP_ROW_STRIDE rather than far above it — the seeded margin is where it lands."""
    info = _run_stamp("cell-negative", (-8 - STAMP_CELL_BIAS) & WORD_MASK, 0)
    assert min(program_writes(info)) < MAP_ROW_STRIDE, (
        "the stamp landed above the map's base, so the index was not sign-extended")


def test_the_row_step_is_sign_extended_too():
    """`adda.w $22090.l,a2` sign-extends as well, so a stride word with its top bit set puts the
    block's second row ABOVE the first."""
    salt = case_salt("row-step-negative")
    window = STAMP_CELL_BIAS + DEFAULT_STRIDE * STAMP_WINDOW_ROWS + MARGIN
    negative_stride = (-DEFAULT_STRIDE) & WORD_MASK
    pokes = {
        MAP_ROW_STRIDE - MARGIN: keyed_block(MAP_ROW_STRIDE - MARGIN, window + MARGIN, salt),
        MAP_ROW_STRIDE: word(negative_stride),
        STAMP_RECORD: keyed_block(STAMP_RECORD, RECORD_CELL + WORD_LEN, salt),
        RECORD_PTR: longword(STAMP_RECORD),
        STAMP_RECORD + RECORD_CELL: word(DEFAULT_STRIDE * 2),
        STAMP_RECORD + RECORD_VARIANT: word(0),
    }
    image = harness.make_image(pokes)
    expected = _model_stamp(image)
    what = "map_stamp_block row-step-negative"
    info = leaf.run("map_stamp_block", _STAMP, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=STAMP_INSN_CAP)
    _assert_writes(info, expected, what)
    assert min(expected) < MAP_ROW_STRIDE + STAMP_CELL_BIAS + DEFAULT_STRIDE * 2, (
        "the second row did not land above the first, so this case does not reach what it is about")
