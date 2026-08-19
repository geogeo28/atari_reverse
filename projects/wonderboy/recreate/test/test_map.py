"""Differential test for src/map.c — the collision map: the two step probes ($10a2 leftward, $1170
rightward), the cell lookup below them ($13be/$13c8), the two settles ($1400 onto a platform tile,
$1492 onto a block or a ledge), the fall pass above them ($1334) and the 2x2 tile stamp ($1af0).

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and states the original's write set EXACTLY against a
Python model of the routine.

TEN THINGS SHAPE THIS BATTERY.

  * THE MAP IS SEEDED, BECAUSE THE GAME LOADS IT. WB_COLLISION_MAP_A32 is all zero in the .PRG
    below its stride word and WB_COLLISION_MAP_DEFAULT lies past the program's last byte
    altogether, so neither carries shipped data a case could read. Both are plain RAM the game
    fills at run time, so every case seeds a window of each ADDRESS-KEYED and then pokes the
    handful of cells it means to test — no shipped record is fabricated, which is the distinction
    CLAUDE.md's coverage rule draws.
  * THE TWO STRIDES ARE SEEDED APART. Both probes pick their map with `tst.w $a32.w` but read the
    row stride the ground test walks by from WB_COLLISION_MAP_DEFAULT unconditionally. Seeding the
    two stride words to the same number would hide that; every case here gives them different
    values, and `test_the_ground_test_walks_by_the_default_maps_stride` (plus its rightward twin) is
    the case a "fixed" port fails.
  * NO PROBE RUNS THE ATTRIBUTION (POISON) PASS. All three READ the actor x word they also write
    ($10a2 and $1170 in their own retry loops), so poisoning the oracle's outputs feeds a different
    position back into the walk — the two cores would still agree, but on a case nobody chose, and a
    poisoned x can make the loop run 65,535 times. They run with `poison=False` and an EXACT write
    set compared against a model instead, which is `text_run_message_box`'s reason and precedent.
  * THE WHOLE RESULT OF $10a2 IS TWO REGISTERS. d0 carries the outcome byte over a low word that
    still holds the probe's map column, and d1 the ground flags over a high word the `mulu.w` left
    there. The reconstruction returns d0 and hands d1 back through a pointer, and every case
    compares BOTH against the oracle's own.
  * $1170's d0 IS THE SAME BYTE OVER THREE DIFFERENT LOW WORDS, one per exit — the column, the clamp
    limit, or the x it just parked — so its cases state the whole longword and three of them are
    about nothing else. Its runner also states the FIVE registers the reconstruction does not owe
    (d2, d3, d6, d7, a6), because "no caller reads these" is a claim, and a model that says what
    they hold is how it is kept honest.
  * THE TAIL IS ONE PIECE OF CODE, SO IT IS ONE MODEL. $1170 has no `rts`: both exits `bra.w $111a`,
    inside $10a2. `_model_ground` is the Python of those instructions, called by both probes' models
    exactly as `map_ground_under_cell` is called by both reconstructions, and
    `test_the_rightward_probe_has_no_rts_and_branches_into_the_leftward_ones_tail` is the scan that
    says the sharing is the original's and not the port's idea.
  * AND THE WHOLE RESULT OF $13c8 IS *SIX* REGISTERS — it writes no memory at all, so the write set
    every other case here states is EMPTY and the registers are the entire surface. That is why it
    was not portable until the kit's oracle began reporting the full set: a6, d2, d3 and d7 (the
    map it selected, the sub-cell and the span) are what its callers use, and d0/d1 alone were
    by-products. Each case runs a Python model, then requires BOTH the oracle's six registers and
    the reconstruction's six `map_cell_probe` fields to equal it — three-way, because two sides
    agreeing on a value neither case chose is what the model exists to refuse.

  * ONE ROUTINE'S BODY CONTAINS ANOTHER'S. actor_accelerate_fall's 32 bytes sit INSIDE $1492's
    span, and $1492 reaches them by a `blt.w` and by falling through — so its entry pin is 130
    bytes where the Ghidra scan records 98, and `test_the_enclosed_routine_is_actor_accelerate_fall`
    is what ties the enclosed block to that routine's own address and length. The 32 bytes are
    assembled here as well as in test_actor.py: that is the SECOND user of the encoding, which the
    batch-7 rule keeps local and STATUS.md registers, and the two independent assemblies of the same
    instructions are both compared against the image.
  * $1334's MODEL COMPOSES rather than restates. It calls the models of $13c8, $13be, $1492, $1400
    and $14d6 in the order the body calls them, each handed the memory the ones before it left —
    which is the only way the two cell lookups take their row from the y the pass has just moved.
  * AND ITS CASES ARE KEYED TO THE CELLS THE ROUTINE ACTUALLY READS, which are three different
    expressions: the head's is the record's OWN x at its pre-step y, and both settles' are its left
    edge at its post-step y. `_tile_33_cell` and `_settle_cell` are those expressions, and the
    runner refuses a case whose head cell is one its `tiles` also seeds.

KNOWINGLY NOT PINNED
  * WHAT THE TILE CODES MEAN. $1, $2, $23 and $33 are named for the tests that read them; that they
    are "wall", "ledge", "platform" and whatever $33 is, is not established. Nor is what the three
    WB_TILE_33_* words the fall pass raises and clears select — every reader in the image is a bare
    `tst.w`, so even the two DIFFERENT nonzero values $d84 writes into WB_TILE_33_MODE are
    indistinguishable to everything that reads it.
  * WHAT WB_RECORD_PTR_10420 POINTS AT. The stamp reads two of its fields and nothing here bounds
    the record or says which of its twenty readers — fourteen `movea.l` sites plus six that copy the
    pointer to its neighbour — agree about its shape.
  * THE CELL $13c8 NAMES IS NEVER READ, BY IT OR BY THESE CASES. The routine computes a6 and stops;
    what lies there is $1400's and $10a2's business, and those cases seed it. So a case here is free
    to send the pointer outside the seeded window (the sign-extension case does exactly that) —
    nothing dereferences it.
  * WHAT WB_BG_SCROLL_LIMIT_BIAS MEASURES. $1170's clamp adds $f0 to the scroll limit, and
    `test_the_clamps_bias_is_the_one_the_limit_word_was_built_with` shows $fb18 SUBTRACTING the same
    $f0 from a shifted cell count to build that limit — so `limit + bias` is the level's own width
    in pixels. That the $f0 is therefore the scrolled window's width is a reading, not a case.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (BRANCH_EXTENSION, JSR_ABS_L, RTS, add_w_dn_dn, addi_w_dn, addq_b_d16, andi_w_dn,
                  asr_w_imm_dn, branch, branch_over, branch_w_to, case_salt, clr_w_dn, cmp_w_dn_dn,
                  JMP_ABS_L, clr_b_d16, cmpi_b_dn, cmpi_b_ind, cmpi_w_d16, cmpi_w_dn, keyed_block,
                  lea_abs_l,
                  lea_indexed,
                  longword,
                  lsl_w_imm_dn, merge_bands, move_b_d16_dn, move_b_imm_d16, move_l_dn_dn,
                  move_w_abs_l_dn,
                  move_w_dn_dn, move_w_ind_dn, move_w_postinc_dn, movea_l_abs_l, moveq_0_dn, opcode,
                  mulu_w_dn_dn,
                  program_writes, s16, set_low_word, sub_w_dn_dn, subi_w_dn, subq_w_dn,
                  tst_w_abs_w, tst_w_dn, u16, word)
from layout import wb

import emu      # noqa: E402  (harness puts the kit's oracle on sys.path)
import loader   # noqa: E402

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
TILE_33 = wb("MAP_TILE_33")
TILE_33_FLAG = wb("TILE_33_FLAG")
TILE_33_MODE = wb("TILE_33_MODE")
TILE_33_STEP = wb("TILE_33_STEP")
TILE_33_RAISED = wb("TILE_33_FLAG_RAISED")
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
# The word the stamp's tile-set select reads is the SCENE DESCRIPTOR's kind word, and the value it
# tests for is the boss-defeat kind — one field and one value, named where src/scene.c names them
# (include/wonderboy.h, WB_SCENE_KIND) rather than a second time here.
RECORD_KIND = wb("SCENE_KIND")
KIND_BOSS_DEFEAT = wb("SCENE_KIND_BOSS_DEFEAT")
RECORD_CELL = wb("RECORD_10420_CELL")
STAMP_CELL_BIAS = wb("STAMP_CELL_BIAS")
STAMP_TILES_FIRST = wb("STAMP_TILES_FIRST")
STAMP_TILES_SECOND = wb("STAMP_TILES_SECOND")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
SCROLL_LIMIT_X = wb("BG_SCROLL_LIMIT_X")
LIMIT_BIAS = wb("BG_SCROLL_LIMIT_BIAS")

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
MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
LANDED_BIT = wb("ACTOR_FLAGS2_LANDED_BIT")
FALL_SPEED_MAX = wb("ACTOR_FALL_SPEED_MAX")
TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
RECORD_BYTES = wb("ACTOR_RECORD_BYTES")

WORD_LEN = 2
LONGWORD_LEN = 4
BYTE_MASK = 0xff
WORD_MASK = 0xffff

# --- register numbers, and the opcodes only this battery spells ------------------------------------
A0, A1, A2, A6 = 0, 1, 2, 6
D0, D1, D2, D3, D6, D7 = 0, 1, 2, 3, 6, 7

BNE_W, BEQ_W, BPL_W, BLT_W, BGE_W, BGT_W, BRA_W = (0x6600, 0x6700, 0x6a00, 0x6d00, 0x6c00, 0x6e00,
                                                   0x6000)
BLE_W = 0x6f00
BSET_IMM, BCLR_IMM, BTST_IMM = 0x08c0, 0x0880, 0x0800


def branch_s_back(condition, spanned_bytes):
    """A SHORT branch back over ``spanned_bytes`` — the two probes close their loops with these,
    and $1400 rejoins its unsupported arm from two places the same way."""
    displacement = -(spanned_bytes + BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a byte displacement"
    return opcode(condition | (displacement & BYTE_MASK))


def branch_w_back(condition, spanned_bytes):
    """The WORD form of the same jump. $1170's second loop-closing branch is the one place either
    probe needs it: its head is 130 bytes back, two further than a byte displacement reaches, so the
    assert is what says the wide form is the geometry's doing and not a transcription."""
    displacement = -(spanned_bytes + BRANCH_EXTENSION)
    assert displacement < -0x80, (
        f"{displacement} fits a byte displacement, which is the form the original would then use")
    return opcode(condition) + word(displacement)


def move_b_imm_dn(reg, value):
    return opcode(0x103c | (reg << 9)) + word(value)


def move_b_dn_dn(destination, source):
    return opcode(0x1000 | (destination << 9) | source)


def move_w_d16_ind(source, displacement, destination):
    return opcode(0x3080 | (destination << 9) | 0x28 | source) + word(displacement)


def move_w_abs_l_d16(addr, base, displacement):
    return opcode(0x3179 | (base << 9)) + longword(addr) + word(displacement)


def sub_w_d16_dn(reg, base, displacement):
    return opcode(0x9068 | (reg << 9) | base) + word(displacement)


def sub_w_dn_ind(reg, base):
    return opcode(0x9150 | (reg << 9) | base)


def add_w_d16_dn(reg, base, displacement):
    return opcode(0xd068 | (reg << 9) | base) + word(displacement)


def add_w_dn_ind(reg, base):
    return opcode(0xd150 | (reg << 9) | base)


def move_w_dn_ind(reg, base):
    return opcode(0x3080 | (base << 9) | reg)
    # ALSO IN test_player.py — second copy, which the rule allows. The two agree on the argument
    # ORDER (data register, then address register); this one called the data register `source`,
    # renamed to leaf.py's and that copy's `reg` so a third copy has one spelling to hoist.


def move_w_dn_d16(source, base, displacement):
    """`move.w Dn,d16(An)` — how $1334 stores the y it has just stepped."""
    return opcode(0x3140 | (base << 9) | source) + word(displacement)


def andi_w_d16(base, value, displacement):
    """`andi.w #imm,d16(An)` — $1492's landing arm masks the actor's own y with one of these."""
    return opcode(0x0268 | base) + word(value) + word(displacement)


def neg_w_dn(reg):
    # ALSO IN leaf.py (batch 39) and test_scroll.py. This copy stays because converting it is a
    # change to a battery batch 39 has no other reason to touch; ../STATUS.md's queue names it.
    return opcode(0x4440 | reg)


def ori_w_dn(reg, value):
    return opcode(0x0040 | reg) + word(value)


def subi_w_d16(base, value, displacement):
    return opcode(0x0468 | base) + word(value) + word(displacement)


def addq_w_dn(amount, reg):
    # ALSO IN leaf.py (batch 39). Same reason as `neg_w_dn` above, and the same queue entry.
    return opcode(0x5040 | ((amount & 7) << 9) | reg)


def addq_l_an(amount, reg):
    return opcode(0x5088 | ((amount & 7) << 9) | reg)


def cmp_w_d16_dn(reg, base, displacement):
    return opcode(0xb068 | (reg << 9) | base) + word(displacement)


def cmpi_b_indexed(base, index, value):
    """`cmpi.b #imm,0(An,Dn.w)` — how the ground test reaches a row up or down."""
    return opcode(0x0c30 | base) + word(value) + word(index << 12)


def bit_op_d16(op, bit, reg, displacement):
    return opcode(op | 0x28 | reg) + word(bit) + word(displacement)


def move_b_imm_ind(base, value):
    return opcode(0x10bc | (base << 9)) + word(value)


def move_b_imm_postinc(base, value):
    return opcode(0x10fc | (base << 9)) + word(value)


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


def _cell_lookup(column_reg, row_reg, stride_reg, product_reg):
    """The five instructions that turn a (column, row) pair into a cell pointer — the block $10a2
    inlines and $13c8 IS, which is why src/map.c has one `cell_pointer` helper rather than two.

    The two spellings differ in one thing only: which register the `mulu.w` accumulates into. $10a2
    loads the stride into d2 and multiplies its ROW register by it; $13c8 loads the stride into d3
    and multiplies THAT by the row. So the product register is one of the other two, and stating
    which is what makes both bodies come out of this one block.
    """
    assert product_reg in (row_reg, stride_reg), (
        "the `mulu.w` accumulates into the row register or the stride one, and nothing else")
    factor = row_reg if product_reg == stride_reg else stride_reg
    return (tst_w_abs_w(FLAG_A32)
            + branch(BEQ_W, lea_abs_l(A6, MAP_A32), branch(BRA_W, b""))
            + lea_abs_l(A6, MAP_A32) + branch(BRA_W, lea_abs_l(A6, MAP_DEFAULT))
            + lea_abs_l(A6, MAP_DEFAULT)
            + move_w_postinc_dn(stride_reg, A6) + mulu_w_dn_dn(product_reg, factor)
            + add_w_dn_dn(product_reg, column_reg)
            + lea_indexed(A6, product_reg, MAP_CELLS - WORD_LEN))


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
            + _cell_lookup(D0, D1, D2, D1))
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


def _ground_test_at():
    """$111a — the address $10a2's tail begins at, as the left probe's own entry plus everything in
    its body ABOVE that tail. $1170's two exits branch HERE, so their displacements come out of
    where the two bodies sit relative to one another rather than being transcribed."""
    return (leaf.entry_of("actor_step_left_against_map")
            + len(_step_left_entry()) - len(_ground_test()))


def _step_right_entry():
    """$1170's whole body — which ends in a `bra.w` INTO $10a2 rather than in an `rts`, and carries
    no `rts` anywhere."""
    entry = leaf.entry_of("actor_step_right_against_map")
    tail = _ground_test_at()

    prologue = move_b_imm_dn(D6, STEP_CLEAR)
    head = (moveq_0_dn(D0) + moveq_0_dn(D1)
            + move_w_ind_dn(D0, A0, ACTOR_X) + add_w_d16_dn(D0, A0, HALF_WIDTH)
            + add_w_dn_dn(D0, D7) + move_w_dn_dn(D3, D0) + asr_w_imm_dn(CELL_SHIFT, D0)
            + move_w_ind_dn(D1, A0, ACTOR_Y) + subq_w_dn(1, D1) + asr_w_imm_dn(CELL_SHIFT, D1)
            + _cell_lookup(D0, D1, D2, D1))

    # The clamp arm, in the two halves the `bge` sits between: the limit it builds, and the parking
    # it does when the probe is past that limit.
    limit = (tst_w_abs_w(FLAG_A32)
             + branch_over(BEQ_W, len(clr_w_dn(D0)) + BRANCH_W_LEN)
             + clr_w_dn(D0) + branch(BRA_W, move_w_abs_l_dn(D0, SCROLL_LIMIT_X))
             + move_w_abs_l_dn(D0, SCROLL_LIMIT_X)
             + addi_w_dn(D0, LIMIT_BIAS) + cmp_w_dn_dn(D0, D3))
    park = sub_w_d16_dn(D0, A0, HALF_WIDTH) + move_w_dn_ind(D0, A0)
    # Both exits are `move.b` plus a branch out of the body, so their length is known before their
    # displacements are — which is what lets the arms above be assembled at all.
    exit_len = len(move_b_imm_dn(D0, STEP_BLOCKED)) + BRANCH_W_LEN

    blocked = move_b_imm_dn(D6, STEP_BLOCKED) + subq_w_dn(1, D7)
    player_test = cmpi_w_d16(A0, ACTOR_TYPE_PLAYER, ACTOR_TYPE)
    clear_field = clr_b_d16(A0, FIELD_22)
    clamp_arm_len = (len(cmpi_b_ind(A6, TILE_BLOCK)) + BRANCH_W_LEN + len(limit) + BRANCH_W_LEN
                     + len(park) + BRANCH_W_LEN)
    # Both loop-closing branches jump back to `head`, i.e. past the entry's one leading instruction.
    to_head = len(head) + clamp_arm_len
    at_bne = len(blocked) + BRANCH_W_LEN + len(player_test)
    at_bra = at_bne + BRANCH_S_LEN + len(clear_field)
    retry = player_test + branch_s_back(BNE_W, to_head + at_bne) + clear_field
    blocked_arm = (blocked
                   + branch_over(BEQ_W, len(retry) + BRANCH_W_LEN + exit_len)
                   + retry
                   + branch_w_back(BRA_W, to_head + at_bra))

    clamp_arm = (cmpi_b_ind(A6, TILE_BLOCK)
                 + branch_over(BEQ_W, len(limit) + BRANCH_W_LEN + len(park) + BRANCH_W_LEN)
                 + limit
                 + branch_over(BGE_W, len(park) + BRANCH_W_LEN + len(blocked_arm) + exit_len)
                 + park
                 + branch_over(BRA_W, len(blocked_arm)))
    assert len(clamp_arm) == clamp_arm_len

    clamped_at = entry + len(prologue) + len(head) + len(clamp_arm) + len(blocked_arm)
    clamped = move_b_imm_dn(D0, STEP_BLOCKED)
    clamped += branch_w_to(BRA_W, clamped_at + len(clamped), tail)
    commit_at = clamped_at + len(clamped)
    commit = add_w_dn_ind(D7, A0) + move_b_dn_dn(D0, D6)
    commit += branch_w_to(BRA_W, commit_at + len(commit), tail)
    assert len(clamped) == exit_len and len(commit) == exit_len
    return prologue + head + clamp_arm + blocked_arm + clamped + commit


def _cell_from_actor_x_entry():
    """$13be, which ends WITHOUT an `rts`: its last instruction is followed by $13c8's first, and
    `test_the_prelude_falls_through_into_the_lookup` is what says so."""
    return (moveq_0_dn(D0) + move_l_dn_dn(D1, D0)
            + move_w_ind_dn(D0, A0, ACTOR_X) + sub_w_d16_dn(D0, A0, HALF_WIDTH))


def _cell_lookup_entry():
    return (move_w_dn_dn(D2, D0) + andi_w_dn(D2, CELL_MASK)
            + move_w_ind_dn(D1, A0, ACTOR_Y)
            + asr_w_imm_dn(CELL_SHIFT, D0) + asr_w_imm_dn(CELL_SHIFT, D1)
            + _cell_lookup(D0, D1, D3, D3)
            + move_w_ind_dn(D7, A0, HALF_WIDTH) + add_w_dn_dn(D7, D7) + RTS)


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


# The 32 bytes of actor_accelerate_fall, which sit INSIDE $1492's span. test_actor.py's
# `_accelerate_fall_entry` is the other spelling of them; this is the SECOND user of that
# encoding, so per the batch-7 rule it stays local here and STATUS.md registers the trigger — a
# THIRD would hoist it into leaf.py. The two spellings are independent assemblies of the same
# instructions and both are compared against the image, which is what makes the duplication earn
# its keep: `test_the_enclosed_routine_is_actor_accelerate_fall` below ties this copy to the other
# battery's ADDRESS and LENGTH, so the two cannot drift apart silently.
def _accelerate_fall_body():
    step = addq_b_d16(1, A0, SPEED)
    return (bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
            + bit_op_d16(BSET_IMM, FALLING_BIT, A0, ACTOR_FLAGS)
            + moveq_0_dn(D0) + move_b_d16_dn(D0, A0, SPEED)
            + cmpi_b_dn(D0, FALL_SPEED_MAX) + branch(BEQ_W, step) + step + RTS)


def _ground_tile_pair(after):
    """$1492's tile test, at all three of the sites it spells it: `cmpi.b #$1,(a6) / beq` then
    `cmpi.b #$2,(a6) / beq`, both aimed at the landing arm ``after`` bytes past the pair's end.

    THE PAIR is what makes this routine $1400's sibling rather than $1400 with a tile argument, so
    the pin builds it once and the three sites take it — a port that dropped the second `cmpi.b`
    would fail on the bytes as well as on a case."""
    second = cmpi_b_ind(A6, TILE_LEDGE) + branch_over(BEQ_W, after)
    first = cmpi_b_ind(A6, TILE_BLOCK) + branch_over(BEQ_W, after + len(second))
    return first + second


def _settle_tile_1_or_2_entry():
    """$1492's whole body — 130 bytes, of which the 32 in the middle are actor_accelerate_fall's."""
    fall = _accelerate_fall_body()
    landed = (andi_w_d16(A0, ~CELL_MASK & WORD_MASK, ACTOR_Y)
              + bit_op_d16(BSET_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BCLR_IMM, FALLING_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BCLR_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS)
              + clr_b_d16(A0, SPEED) + RTS)
    # The second pair sits directly above the enclosed routine, so its branches span exactly that.
    second_probe = addq_l_an(1, A6) + _ground_tile_pair(len(fall))
    subcell = (moveq_0_dn(D0) + move_w_dn_dn(D0, D7) + asr_w_imm_dn(1, D0) + neg_w_dn(D0)
               + andi_w_dn(D0, CELL_MASK) + cmp_w_dn_dn(D2, D0)
               + branch_over(BLT_W, len(second_probe)))
    step = addq_l_an(1, A6) + subi_w_dn(D7, CELL_PIXELS)
    span_test = cmpi_w_dn(D7, CELL_PIXELS)
    scan = (_ground_tile_pair(len(span_test) + BRANCH_W_LEN + len(step) + BRANCH_S_LEN
                              + len(subcell) + len(second_probe) + len(fall))
            + span_test + branch_over(BLT_W, len(step) + BRANCH_S_LEN) + step)
    scan += branch_s_back(BRA_W, len(scan))
    return scan + subcell + second_probe + fall + landed


def _fall_and_settle_entry():
    """$1334's whole body, which ends in a `bra.w` INTO actor_settle_on_platform and carries no
    `rts` past $1380.

    Assembled FORWARD rather than bottom-up like the others: five of its instructions are calls, and
    a call's displacement depends on where in the body it sits, so a pin aimed at the wrong callee
    (or built at the wrong offset) has to fail on the bytes."""
    entry = leaf.entry_of("actor_fall_and_settle")
    out = bytearray()

    def call(name):
        return leaf.bsr_w(entry + len(out), leaf.entry_of(name))

    def jump(name):
        return branch_w_to(BRA_W, entry + len(out), leaf.entry_of(name))

    raise_flag = leaf.MOVE_W_IMM_ABS_L + word(TILE_33_RAISED) + longword(TILE_33_FLAG)
    mode_test = leaf.tst_w_abs_l(TILE_33_MODE)
    clear_three = (leaf.clr_w_abs_l(TILE_33_MODE) + leaf.clr_w_abs_l(TILE_33_STEP)
                   + leaf.clr_w_abs_l(TILE_33_FLAG))
    # The head's own arm, from the `move.w #$ffff` down to the last `clr.w`: what the type test
    # branches over, and (less its `clr.w`s) what the tile test branches over.
    tile_33_arm = len(raise_flag) + len(mode_test) + BRANCH_W_LEN + len(RTS)
    step_y = (moveq_0_dn(D1) + move_w_ind_dn(D0, A0, ACTOR_Y) + move_b_d16_dn(D1, A0, SPEED)
              + add_w_dn_dn(D0, D1) + move_w_dn_d16(D0, A0, ACTOR_Y))
    landed_test = bit_op_d16(BTST_IMM, LANDED_BIT, A0, FLAGS2)
    crossed_test = andi_w_dn(D0, CELL_MASK) + cmp_w_dn_dn(D0, D1)
    # Both settle arms are a `bsr` plus a word branch, and the ground arm is two `bsr`s — lengths
    # the three branches below need before the calls themselves can be placed.
    call_len = len(leaf.bsr_w(0, 0))
    ground_arm = 2 * call_len
    fall_arm = call_len + BRANCH_W_LEN

    out += cmpi_w_d16(A0, ACTOR_TYPE_PLAYER, ACTOR_TYPE)
    out += branch_over(BNE_W, len(moveq_0_dn(D0)) + len(move_l_dn_dn(D1, D0))
                       + len(move_w_ind_dn(D0, A0, ACTOR_X)) + call_len
                       + len(cmpi_b_ind(A6, TILE_33)) + BRANCH_W_LEN
                       + tile_33_arm + len(clear_three))
    out += moveq_0_dn(D0) + move_l_dn_dn(D1, D0) + move_w_ind_dn(D0, A0, ACTOR_X)
    out += call("actor_map_cell_lookup")
    out += cmpi_b_ind(A6, TILE_33) + branch_over(BNE_W, tile_33_arm)
    out += raise_flag + mode_test + branch_over(BEQ_W, len(RTS) + len(clear_three)) + RTS
    out += clear_three
    out += bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS) + branch_over(BEQ_W, len(RTS)) + RTS
    out += step_y
    out += landed_test + branch_over(BNE_W, len(crossed_test) + BRANCH_W_LEN + fall_arm)
    out += crossed_test + branch_over(BLE_W, fall_arm)
    out += call("actor_accelerate_fall")
    out += branch_over(BRA_W, ground_arm)
    out += call("actor_map_cell_from_actor_x")
    out += call("actor_settle_on_tile_1_or_2")
    out += call("actor_map_cell_from_actor_x")
    out += jump("actor_settle_on_platform")
    return bytes(out)


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
            + cmpi_w_d16(A1, KIND_BOSS_DEFEAT, RECORD_KIND)
            + branch(BEQ_W, _stamp_arm(STAMP_TILES_FIRST))
            + _stamp_arm(STAMP_TILES_FIRST) + _stamp_arm(STAMP_TILES_SECOND))


ENTRY_BYTES = {
    "actor_step_left_against_map": _step_left_entry(),
    "actor_step_right_against_map": _step_right_entry(),
    "actor_map_cell_from_actor_x": _cell_from_actor_x_entry(),
    "actor_map_cell_lookup": _cell_lookup_entry(),
    "actor_settle_on_platform": _settle_entry(),
    "actor_settle_on_tile_1_or_2": _settle_tile_1_or_2_entry(),
    "actor_fall_and_settle": _fall_and_settle_entry(),
    "map_stamp_block": _stamp_entry(),
}
RECONSTRUCTED_ROUTINES = 8

# What the Ghidra function table does NOT count in a routine's size: another function's body, lying
# inside this one's span. There is exactly one, and it is why $1492's pin is longer than its scan
# size — see `test_the_enclosed_routine_is_actor_accelerate_fall`.
ENCLOSED_BYTES = {"actor_settle_on_tile_1_or_2": 32}


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("actor_step_left_against_map", 206),
    ("actor_step_right_against_map", 152),
    ("actor_map_cell_from_actor_x", 10),
    ("actor_map_cell_lookup", 56),
    ("actor_settle_on_platform", 146),
    ("actor_settle_on_tile_1_or_2", 98),
    ("actor_fall_and_settle", 138),
    ("map_stamp_block", 86),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The pins above would still pass on a PREFIX. These are the sizes the Ghidra function table
    records (../out/hw_scan.tsv), so a body one instruction short fails here — plus, for the one
    routine that has another's body inside its span, those bytes as well: 130 = 98 + 32."""
    enclosed = ENCLOSED_BYTES.get(name, 0)
    assert len(ENTRY_BYTES[name]) == size + enclosed, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records plus "
        f"the {enclosed} it encloses")


def test_the_enclosed_routine_is_actor_accelerate_fall():
    """$1492's span is $1492..$1513 and actor_accelerate_fall's 32 bytes sit INSIDE it — which is
    why the scan records 98 for a routine whose body is 130 bytes long. This is what says the
    enclosure is that routine and not some other 32 bytes: the enclosed block is at
    ../names.txt's own address for it, it is the length test_actor.py records, and the bytes this
    battery assembles for it are the bytes AT that address.

    Both of $1492's two ways in are pinned by the geometry above rather than asserted here: the
    `blt.w` at $14c0 branches over `second_probe` and lands on the block's first byte, and the
    second `beq.w` at $14d2 falls straight into it."""
    body = ENTRY_BYTES["actor_settle_on_tile_1_or_2"]
    fall = _accelerate_fall_body()
    entry = leaf.entry_of("actor_settle_on_tile_1_or_2")
    enclosed_at = leaf.entry_of("actor_accelerate_fall")

    assert len(fall) == ENCLOSED_BYTES["actor_settle_on_tile_1_or_2"]
    assert entry < enclosed_at < entry + len(body), (
        f"actor_accelerate_fall at {enclosed_at:#x} is not inside $1492's {entry:#x}..."
        f"{entry + len(body):#x} span at all")
    offset = enclosed_at - entry
    assert body[offset:offset + len(fall)] == fall, (
        f"the {len(fall)} bytes at offset {offset} of $1492's body are not the ones this battery "
        f"assembles for actor_accelerate_fall")
    assert bytes(harness.BASE_IMAGE[enclosed_at:enclosed_at + len(fall)]) == fall
    # ...and the enclosed routine's own `rts` is the LAST thing before $1492's landing arm, so the
    # two exits really are its rts and the landing arm's.
    assert body[offset + len(fall) - len(RTS):offset + len(fall)] == RTS


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
# ...and the y that puts an actor one pixel INSIDE that row. Cases that do not care about the row
# take this; `test_the_probe_row_is_the_pixel_above_the_actors_own_y` is the one that does.
DEFAULT_PROBE_Y = PROBE_ROW * CELL_PIXELS + 1
MARGIN = 0x20                       # ...and a margin either side, so an over-run is visible


def map_window(stride):
    """The bytes one map occupies at ``stride`` — public for map_pokes' reason."""
    return MAP_CELLS + stride * MAP_WINDOW_ROWS + MAP_WINDOW_COLUMNS + MARGIN


def _cell_of(base, stride, column, row):
    return base + MAP_CELLS + stride * row + column


ACTOR = TABLE_DEFAULT + 3 * RECORD_BYTES      # any record but the followed one or slot 8


def map_pokes(salt, a32_stride=A32_STRIDE, default_stride=DEFAULT_STRIDE):
    """Both maps seeded, their stride words set, and a margin below each.

    PUBLIC because test_behavior.py's three map-stepping leaves need the same seeded maps: a second
    copy of "what a collision map looks like" could disagree with src/map.c while both batteries
    stayed green. Same rule test_scene.py follows for test_stage.py's window model."""
    pokes = {}
    for base, stride in ((MAP_A32, a32_stride), (MAP_DEFAULT, default_stride)):
        window = map_window(stride)
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


def _word_write(addr, value):
    """One word store as a write set of its own — what a composed model folds into the pass's."""
    out = {}
    _put_word(out, addr, value)
    return out


def _over_high_half(entry, low):
    """A WORD write into a longword register: the low word is replaced and the caller's high half
    survives it. Kept under this battery's own name — it is what the probes DO to their fields —
    over leaf.py's spelling of machine.h's `set_low_word`, which is the operation itself."""
    return set_low_word(entry, low)


def _over_high_bytes(entry, low):
    """...and the same one size down, for the `move.b #$ff,d6` both probes open with: only d6's
    LOW BYTE is the outcome, and the caller's other three survive it (`set_low_byte`)."""
    return (entry & ~BYTE_MASK) | (low & BYTE_MASK)


# --- whole-image scans ------------------------------------------------------------------------------
# Every claim about how many callers a routine has, or how many sites touch a global, is a scan of
# the program's own bytes rather than a count taken off a disassembly listing.
BSR_HIGH_BYTE = 0x61
BRA_HIGH_BYTE = 0x60
BSR_LONG_DISPLACEMENT = 0xff        # the 68020 `bsr.l`/`bra.l` encoding; none in this image

# The two absolute forms a call site can take. `JSR_ABS_L` is leaf.py's — the scan below only ever
# compares against the opcode word, but a battery that BUILDS the instruction must get the same two
# bytes, so there is one definition of them.


def _relative_sites(program, targets, high_byte=BSR_HIGH_BYTE):
    """Every `bsr` site in ``program`` reaching one of ``targets``, in BOTH encodings — a short
    branch could reach $13be from 126 bytes either side, and a scan that looked only for the word
    form would report a caller count that is merely a lower bound. ``high_byte`` picks `bra`
    instead, which is how $1170's exits reach $10a2's tail."""
    sites = {target: [] for target in targets}
    for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN):
        instruction = int.from_bytes(program[at:at + WORD_LEN], "big")
        if instruction >> 8 != high_byte:
            continue
        short = instruction & BYTE_MASK
        if short == BSR_LONG_DISPLACEMENT:
            continue
        if short == 0:
            displacement = s16(int.from_bytes(program[at + WORD_LEN:at + LONGWORD_LEN], "big"))
        else:
            displacement = short - (BYTE_MASK + 1) if short & 0x80 else short
        target = at + WORD_LEN + displacement
        if target in sites:
            sites[target].append(at)
    return sites


def _absolute_sites(program, targets):
    """`jsr <abs>.l` and `jmp <abs>.l` sites reaching one of ``targets``. A `bsr` scan alone would
    put a floor under a caller count; this is what closes it."""
    sites = {target: [] for target in targets}
    for at in range(0, len(program) - 2 * LONGWORD_LEN, WORD_LEN):
        if int.from_bytes(program[at:at + WORD_LEN], "big") not in (JSR_ABS_L, JMP_ABS_L):
            continue
        target = int.from_bytes(program[at + WORD_LEN:at + WORD_LEN + LONGWORD_LEN], "big")
        if target in sites:
            sites[target].append(at)
    return sites


def _operand_sites(program, addr):
    """Every even offset at which ``addr``'s four bytes appear — an UPPER bound on the sites that
    name it, since a run of data could spell them by accident, and each case below then says which
    instruction is at the offsets it cares about. $83b2 is above $7fff, so the 68000's short
    absolute form cannot reach it and the long one is the whole story."""
    encoded = longword(addr)
    return [at for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN)
            if program[at:at + LONGWORD_LEN] == encoded]


# --- glue -------------------------------------------------------------------------------------------
# All three of the settle chain's routines HAND d7 BACK, because two behaviour handlers read a byte
# of it (src/behavior.c, map.h). The models below already state that register against the oracle —
# `_assert_the_span_comes_back` is what ties the reconstruction's own return value to the same
# number, so the C cannot drift from the model the oracle is checked against.
_SETTLE = leaf.register_glue("actor_settle_on_platform", [ctypes.c_uint32] * 4, ctypes.c_uint32)


def _assert_the_span_comes_back(info, regs, what):
    assert info["ret"] == regs["d7"], (
        f"{what}: the reconstruction returned {info['ret']:#010x} where the oracle left d7 = "
        f"{regs['d7']:#010x}")
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


def _model_ground(image, cell):
    """The tail at $111a: the WB_MAP_GROUND_*_BIT set it leaves in d1's low word, and the d7 it
    walked by to get there.

    ONE model because it is ONE piece of code — $1170's exits `bra.w` into these instructions — so
    both probes' models call it exactly as both reconstructions call `map_ground_under_cell`. The
    stride is WB_COLLISION_MAP_DEFAULT's whichever map the cell came out of: the asymmetry.
    """
    stride = u16(image, MAP_DEFAULT)

    def at(offset):
        return image[(cell + s16(offset)) & 0xffffffff]

    if image[cell] == TILE_BLOCK:
        walked = -stride & WORD_MASK                            # `neg.w d7`
        return (0 if at(walked) == TILE_BLOCK else GROUND_HEAD_BIT), walked
    if at(stride) in (TILE_BLOCK, TILE_LEDGE):
        return 0, stride
    walked = (stride + stride) & WORD_MASK                      # `add.w d7,d7`
    flags = GROUND_NEAR_BIT
    if at(walked) not in (TILE_BLOCK, TILE_LEDGE):
        flags |= GROUND_FAR_BIT
    return flags, walked


def _model_step_left(image, actor, step, a32):
    """{writes}, d0, d1 — the original's own arithmetic, in Python."""
    remaining = step & WORD_MASK
    outcome = STEP_CLEAR
    writes = {}
    map_base = MAP_A32 if a32 else MAP_DEFAULT

    while True:
        probe = (u16(image, actor + ACTOR_X) - u16(image, actor + HALF_WIDTH)
                 - remaining) & WORD_MASK
        column = _pixel_to_cell(probe) & WORD_MASK
        row = probe_row(u16(image, actor + ACTOR_Y)) & WORD_MASK
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

    flags, _walked = _model_ground(image, cell)

    d0 = (column & 0xff00) | outcome
    d1 = (product & 0xffff0000) | flags
    return writes, d0, d1


def _pixel_to_cell(pixels):
    """One pixel coordinate as the map cell it falls in — `asr.w #4`, the SIGNED shift both probes
    spell on both axes, in one place so the four spellings cannot disagree about it."""
    return s16(pixels) >> CELL_SHIFT


def probe_row(actor_y):
    """The ROW both probes take their cell from: `move.w 2(a0),d1 / subq.w #1,d1 / asr.w #4,d1`.
    The pixel ABOVE the actor's y, so a record standing exactly on a cell boundary probes the row it
    is standing IN rather than the one below — and a case's tiles are keyed to this rather than to
    `y asr.w #4`, which is a different row for every y that is a multiple of the cell."""
    return _pixel_to_cell((actor_y - 1) & WORD_MASK)


def probe_cell(actor_x, half_width, step, actor_y):
    """The COLUMN and ROW $10a2's first probe lands in — `(x - half_width - step) asr.w #4` and the
    row above. A case's tiles are keyed relative to this, because the step is part of the column:
    keying them off `x - half_width` alone plants them a cell away from where the routine actually
    looks, and the case then passes on bytes it did not mean to seed."""
    return _pixel_to_cell((actor_x - half_width - step) & WORD_MASK), probe_row(actor_y)


def right_probe_cell(actor_x, half_width, step, actor_y):
    """...and where $1170's lands: `(x + half_width + step) asr.w #4`, the actor's RIGHT edge a
    whole step out. Its own function rather than a direction flag on the one above — the pair of
    expressions is precisely what this batch is here to keep apart."""
    return _pixel_to_cell((actor_x + half_width + step) & WORD_MASK), probe_row(actor_y)


def _run_step_left(case, actor_x, half_width, step, tiles, a32=False, actor_type=0,
                   default_stride=DEFAULT_STRIDE, actor_y=None):
    """One step-left case. ``tiles`` is {(column offset, row offset): code} RELATIVE to the cell the
    first probe lands in, in the SELECTED map's own grid."""
    salt = case_salt(case)
    probe_y = DEFAULT_PROBE_Y if actor_y is None else actor_y
    pokes = map_pokes(salt, default_stride=default_stride)
    pokes[FLAG_A32] = word(0xffff if a32 else 0)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_X] = word(actor_x)
    pokes[ACTOR + ACTOR_Y] = word(probe_y)
    pokes[ACTOR + HALF_WIDTH] = word(half_width)
    pokes[ACTOR + ACTOR_TYPE] = word(actor_type)

    stride = A32_STRIDE if a32 else default_stride
    base = MAP_A32 if a32 else MAP_DEFAULT
    column, row = probe_cell(actor_x, half_width, step & WORD_MASK, probe_y)
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


# --- $1170: the rightward step ----------------------------------------------------------------------
# The mirror of $10a2, and what makes it a routine of its own rather than a parametrisation: its head
# ADDS the half-width and the step where the left one subtracts them, and its clear arm is a
# different mechanism entirely — a limit read out of memory, compared against the UNSHIFTED probe,
# with the actor parked so its right EDGE sits on that limit. What the two really do share is the
# TAIL: $1170 carries no `rts` at all and both of its exits `bra.w $111a`, into $10a2's ground test.
#
# Its retry costs 28 instructions at most (ten in the head, five for the map select and the cell,
# six for the lookup arithmetic and the block test, seven in the blocked arm including the
# player-only byte), counted off ../out/wonderboy_dis.txt — so the cap stays a cap.
STEP_RIGHT_INSN_PER_RETRY = 28
STEP_RIGHT_INSN_TAIL = 32

# Every case is written against this limit word unless it is about the clamp: the level's right edge
# is then far past any probe below, so the walk commits and the clamp arm is opt-in.
STEP_RIGHT_LIMIT_X = 0x400
# What a case may seed. d0 and d1 are allowed but pointless to expect back — the head clears both as
# LONGS (`moveq #$0,d0 / moveq #$0,d1`), which is what `test_the_head_clears_both_registers_as_longs`
# is about; d7 is the step and comes through the runner's own argument.
STEP_RIGHT_ENTRY_REGS = frozenset({"d0", "d1", "d2", "d3", "d6"})


def _model_step_right(image, actor, step, entry):
    """{writes} and EVERY register the original leaves, given the ones it is entered with.

    The oracle reports d0..d7 and a0..a6 now, so there is no reason to state two of them and guess
    at the rest: d0 and d1 are the results the reconstruction owes, and d2/d3/d6/d7/a6 are what the
    walk happens to leave behind — each a WORD or BYTE write over the caller's own bits, which is
    what the model says here.
    """
    remaining = step & WORD_MASK
    outcome = STEP_CLEAR
    writes = {}
    map_base = MAP_A32 if u16(image, FLAG_A32) else MAP_DEFAULT
    x_word = actor + ACTOR_X

    while True:
        probe = (u16(image, x_word) + u16(image, actor + HALF_WIDTH) + remaining) & WORD_MASK
        column = _pixel_to_cell(probe) & WORD_MASK
        row = probe_row(u16(image, actor + ACTOR_Y)) & WORD_MASK
        stride = u16(image, map_base)
        product = (stride * row) & 0xffffffff
        index = (product + column) & WORD_MASK
        cell = (map_base + MAP_CELLS + s16(index)) & 0xffffffff

        if image[cell] != TILE_BLOCK:
            # `clr.w d0` in the A32 mode: that mode has no limit word, only the bias.
            limit = ((0 if u16(image, FLAG_A32) else u16(image, SCROLL_LIMIT_X))
                     + LIMIT_BIAS) & WORD_MASK
            if s16(limit) >= s16(probe):            # `cmp.w d3,d0 / bge` — SIGNED, both operands
                reported, byte, commits = limit, outcome, True
                break
            reported = (limit - u16(image, actor + HALF_WIDTH)) & WORD_MASK
            _put_word(writes, x_word, reported)
            byte, commits = STEP_BLOCKED, False      # `move.b #$0,d0` — a LITERAL, not d6
            break
        outcome = STEP_BLOCKED
        remaining = (remaining - 1) & WORD_MASK
        if remaining == 0:
            reported, byte, commits = column, outcome, True
            break
        if u16(image, actor + ACTOR_TYPE) == ACTOR_TYPE_PLAYER:
            writes[actor + FIELD_22] = 0

    if commits:                                     # `add.w d7,(a0)`, of a step already run down
        _put_word(writes, x_word, (u16(image, x_word) + remaining) & WORD_MASK)
    flags, walked = _model_ground(image, cell)
    return writes, {
        "d0": (reported & 0xff00) | byte,
        "d1": (product & 0xffff0000) | flags,
        "d2": _over_high_half(entry.get("d2", 0), stride),
        "d3": _over_high_half(entry.get("d3", 0), probe),
        "d6": _over_high_bytes(entry.get("d6", 0), outcome),
        "d7": _over_high_half(step, walked),
        "a6": cell,
    }


def _assert_regs(info, expected, what):
    """Every register the model states, against the ORACLE's own — the reconstruction owes only
    d0 and d1, and stating the other five is what says so rather than assuming it."""
    for reg in sorted(expected):
        assert info["regs"][reg] == expected[reg], (
            f"{what}: the original left {reg}={info['regs'][reg]:#010x}, not the model's "
            f"{expected[reg]:#010x}")


_STEP_RIGHT_FN = leaf.bind("actor_step_right_against_map",
                           leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.c_uint32,
                                             ctypes.POINTER(ctypes.c_uint32)],
                           ctypes.c_uint32)


def _step_right_glue(actor, step, ground):
    return lambda _lib, image: _STEP_RIGHT_FN(image, actor, step, ctypes.byref(ground))


def _run_step_right(case, actor_x, half_width, step, tiles, a32=False, actor_type=0,
                    default_stride=DEFAULT_STRIDE, actor_y=None, limit_x=STEP_RIGHT_LIMIT_X,
                    entry=None):
    """One step-right case. ``tiles`` is {(column offset, row offset): code} RELATIVE to the cell
    the first probe lands in, in the SELECTED map's own grid.

    Returns the model's register dict, which has already been required to equal the ORACLE's seven
    registers — and, for the two the reconstruction owes, its returned d0 and its ground word too.
    """
    entry = dict(entry or {})
    assert set(entry) <= STEP_RIGHT_ENTRY_REGS, (
        f"{sorted(set(entry) - STEP_RIGHT_ENTRY_REGS)} is not a register a case may seed here")

    salt = case_salt(case)
    probe_y = DEFAULT_PROBE_Y if actor_y is None else actor_y
    pokes = map_pokes(salt, default_stride=default_stride)
    pokes[FLAG_A32] = word(0xffff if a32 else 0)
    pokes[SCROLL_LIMIT_X] = word(limit_x)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_X] = word(actor_x)
    pokes[ACTOR + ACTOR_Y] = word(probe_y)
    pokes[ACTOR + HALF_WIDTH] = word(half_width)
    pokes[ACTOR + ACTOR_TYPE] = word(actor_type)

    stride = A32_STRIDE if a32 else default_stride
    base = MAP_A32 if a32 else MAP_DEFAULT
    column, row = right_probe_cell(actor_x, half_width, step & WORD_MASK, probe_y)
    for (dcolumn, drow), code in tiles.items():
        pokes[_cell_of(base, stride, column + dcolumn, row + drow)] = bytes([code])

    image = harness.make_image(pokes)
    expected_writes, expected = _model_step_right(image, ACTOR, step, entry)

    ground = ctypes.c_uint32(0)
    what = f"actor_step_right_against_map {case}"
    info = leaf.run("actor_step_right_against_map", _step_right_glue(ACTOR, step, ground),
                    merge_bands(expected_writes), what,
                    regs=dict(entry, a0=ACTOR, d7=step, _pokes=pokes), poison=False,
                    max_insns=(STEP_RIGHT_INSN_PER_RETRY * ((step & WORD_MASK) + 1)
                               + STEP_RIGHT_INSN_TAIL))

    _assert_writes(info, expected_writes, what)
    _assert_regs(info, expected, what)
    assert info["ret"] == expected["d0"], (
        f"{what}: the reconstruction returned {info['ret']:#010x} against the original's "
        f"{expected['d0']:#010x}")
    assert ground.value == expected["d1"], (
        f"{what}: the reconstruction's ground word is {ground.value:#010x}, not "
        f"{expected['d1']:#010x}")
    return expected


# The same actor as the leftward cases, and the same tile keys: offsets from the cell the FIRST
# probe lands in, which `right_probe_cell` computes.
RIGHT_X = 0x200
RIGHT_HALF_WIDTH = 0x10
# ...and an x whose right edge is still inside the A32 mode's limit, which is the bias ALONE.
A32_INSIDE_LIMIT_X = LIMIT_BIAS - 2 * RIGHT_HALF_WIDTH


@pytest.mark.parametrize("case,step,tiles,expect_blocked", [
    # Nothing in the way, and the level's edge far off: the whole step is committed.
    ("clear", 8, {}, False),
    # The cell the first probe lands in is a block, and backing off leaves it in the cell BELOW it —
    # the probe shrinks as the step does, so the walk retreats leftward.
    ("blocked-then-clear", 0x11, {HERE: TILE_BLOCK}, True),
    # ...and a case where backing off has to cross a whole further cell.
    ("blocked-two-cells", 0x21, {HERE: TILE_BLOCK, (-1, 0): TILE_BLOCK}, True),
    # A zero step: the probe is the actor's own right edge, and the commit writes x unchanged.
    ("zero-step", 0, {}, False),
    # ...and a block the actor can never back out of, which runs the step down to an EXACT zero and
    # commits a move of nothing.
    ("blocked-everywhere", 4, {HERE: TILE_BLOCK}, True),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_rightward_step_stops_at_the_first_blocking_cell(case, step, tiles, expect_blocked):
    expected = _run_step_right(case, RIGHT_X, RIGHT_HALF_WIDTH, step, tiles)
    blocked = (expected["d0"] & BYTE_MASK) == STEP_BLOCKED
    assert blocked == expect_blocked, (
        f"{case}: the routine reported {'blocked' if blocked else 'clear'}, which is not what this "
        f"case is about")


def test_the_rightward_step_clears_the_players_own_byte_on_every_retry():
    """`cmpi.w #$1,4(a0) / bne.s $1174` at $11e8 — the same player-only clear $10a2 does, and the
    one case whose write set is larger than the x word."""
    expected = _run_step_right("player-retry", RIGHT_X, RIGHT_HALF_WIDTH, 0x11, {HERE: TILE_BLOCK},
                               actor_type=ACTOR_TYPE_PLAYER)
    assert expected["d0"] & BYTE_MASK == STEP_BLOCKED


def test_a_record_that_is_not_the_player_leaves_that_byte_alone_on_the_way_right():
    _run_step_right("other-retry", RIGHT_X, RIGHT_HALF_WIDTH, 0x11, {HERE: TILE_BLOCK},
                    actor_type=ACTOR_TYPE_PLAYER + 1)


# --- the clamp, which is the whole of what makes $1170 its own routine ------------------------------
# `move.w $83b2.l,d0 / addi.w #$f0,d0 / cmp.w d3,d0 / bge` at $11c4..$11d0. A limit SMALL enough that
# limit + bias falls short of the probe is what reaches the arm; STEP_RIGHT_LIMIT_X above never does.
CLAMPING_LIMIT_X = 0x100


def _parked_x(limit_x, half_width):
    """Where the clamp arm leaves the actor: `sub.w 14(a0),d0 / move.w d0,(a0)`, i.e. its right edge
    ON the limit rather than its centre."""
    return (limit_x + LIMIT_BIAS - half_width) & WORD_MASK


def test_the_clamp_parks_the_actors_right_edge_on_the_levels_own_edge():
    """The arm at $11d4: the actor is moved to the limit instead of by its step, and comes back
    WB_MAP_STEP_BLOCKED over the x it was parked at — not over a map column."""
    expected = _run_step_right("clamped", RIGHT_X, RIGHT_HALF_WIDTH, 8, {},
                               limit_x=CLAMPING_LIMIT_X)
    parked = _parked_x(CLAMPING_LIMIT_X, RIGHT_HALF_WIDTH)
    assert expected["d0"] == (parked & 0xff00) | STEP_BLOCKED, (
        f"d0 is {expected['d0']:#x}, not the parked x {parked:#x} under a blocked byte")


def test_the_clamps_own_byte_is_a_literal_and_not_the_walks_verdict():
    """$11f8 spells `move.b #$0,d0` where $1200 spells `move.b d6,d0`. This case's first probe was
    already CLEAR — d6 is still WB_MAP_STEP_CLEAR at the `rts`, which the register assert states —
    and d0's byte is zero all the same. A port that reported `outcome` here would pass every other
    case in this battery."""
    expected = _run_step_right("clamped-while-clear", RIGHT_X, RIGHT_HALF_WIDTH, 8, {},
                               limit_x=CLAMPING_LIMIT_X, entry={"d6": 0xabcdef00})
    assert expected["d6"] & BYTE_MASK == STEP_CLEAR, (
        "the walk had already decided BLOCKED here, so this case cannot tell the two apart")
    assert expected["d0"] & BYTE_MASK == STEP_BLOCKED


@pytest.mark.parametrize("case,a32,clamps", [("default-map", False, False), ("a32-map", True, True)],
                         ids=["default-map-reads-the-limit", "a32-map-has-no-limit-word"])
def test_only_the_default_mode_reads_the_scroll_limit_word(case, a32, clamps):
    """`tst.w $a32.w / beq $11c4` at $11b6 — the SECOND time this routine reads that flag. In the
    A32 mode the limit is `clr.w d0` plus the bias and the level's limit word is never fetched, so
    the same generous limit that lets the default mode commit stops the A32 mode dead. A port that
    read $83b2 in both modes fails the second of these."""
    expected = _run_step_right(f"limit-mode-{case}", RIGHT_X, RIGHT_HALF_WIDTH, 8, {}, a32=a32,
                               limit_x=STEP_RIGHT_LIMIT_X)
    clamped = (expected["d0"] & BYTE_MASK) == STEP_BLOCKED
    assert clamped == clamps, f"{case}: clamped={clamped}, which is not what this case is about"
    if clamps:
        assert expected["d0"] == (_parked_x(0, RIGHT_HALF_WIDTH) & 0xff00) | STEP_BLOCKED, (
            "the A32 arm parked the actor somewhere other than the bias alone")


# The probe is `x + half_width + step`, so these three x values put it exactly ON the limit, one
# pixel short of it and one pixel past it.
LIMIT_EDGE_X = CLAMPING_LIMIT_X + LIMIT_BIAS - RIGHT_HALF_WIDTH


@pytest.mark.parametrize("case,actor_x,clamps", [
    ("one-short-of-the-limit", LIMIT_EDGE_X - 1, False),
    ("exactly-on-the-limit", LIMIT_EDGE_X, False),
    ("one-past-the-limit", LIMIT_EDGE_X + 1, True),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_clamp_is_inclusive_of_the_limit_itself(case, actor_x, clamps):
    """`bge`, not `bgt`: a probe that lands exactly ON the limit still commits. The triple is what
    pins the comparison's direction AND its strictness — one arm each side of the boundary and the
    boundary itself."""
    expected = _run_step_right(f"limit-edge-{case}", actor_x, RIGHT_HALF_WIDTH, 0, {},
                               limit_x=CLAMPING_LIMIT_X)
    clamped = (expected["d0"] & BYTE_MASK) == STEP_BLOCKED
    assert clamped == clamps, f"{case}: clamped={clamped}, which is not what this case is about"


def test_the_limit_compare_is_signed():
    """`cmp.w d3,d0 / bge` reads both operands as SIGNED words, so a probe that wrapped past $7fff
    is BEHIND the limit rather than far beyond it and the move commits. An unsigned reading clamps
    here."""
    wrapping_x = 0x7ff8
    assert (wrapping_x + RIGHT_HALF_WIDTH) & 0x8000, "this case's probe does not wrap at all"
    expected = _run_step_right("probe-past-7fff", wrapping_x, RIGHT_HALF_WIDTH, 8, {},
                               limit_x=CLAMPING_LIMIT_X)
    assert expected["d0"] & BYTE_MASK == STEP_CLEAR, (
        "the wrapped probe was read as greater than the limit, so the compare was unsigned")


def test_the_bias_is_added_as_a_word_and_wraps():
    """`addi.w #$f0,d0` is a word add: a limit word near $ffff wraps to a small positive number
    instead of widening, and the compare then reads that. The model does the same."""
    _run_step_right("limit-wraps", RIGHT_X, RIGHT_HALF_WIDTH, 8, {},
                    limit_x=(-(LIMIT_BIAS // 2)) & WORD_MASK)


# --- what d0's low word carries, which differs per exit ---------------------------------------------
# Three paths, three different things under the same outcome byte. Each case picks geometry whose
# high byte is NONZERO and different from the other two, so a path that returned the wrong one fails.
FAR_X = 0x2000                          # a column above $ff, as $10a2's own case uses


def test_the_committed_exit_carries_the_limit_when_the_compare_sent_it_there():
    """$11d0's `bge` jumps to $1200 with d0 holding limit + bias — NOT the probe's column, which is
    what d0 held four instructions earlier. The two are different numbers here."""
    expected = _run_step_right("commit-carries-the-limit", RIGHT_X, RIGHT_HALF_WIDTH, 8, {})
    limit = STEP_RIGHT_LIMIT_X + LIMIT_BIAS
    column, _row = right_probe_cell(RIGHT_X, RIGHT_HALF_WIDTH, 8, DEFAULT_PROBE_Y)
    assert limit >> 8 not in (0, column >> 8), "this case cannot tell the limit from the column"
    assert expected["d0"] == (limit & 0xff00) | STEP_CLEAR


def test_the_committed_exit_carries_the_column_when_the_step_ran_out():
    """The other way into $1200, from $11e4's `beq`: d0 still holds the column the head shifted out,
    and its high byte comes back above the outcome byte."""
    expected = _run_step_right("commit-carries-the-column", FAR_X, RIGHT_HALF_WIDTH, 4,
                               {HERE: TILE_BLOCK}, limit_x=FAR_X)
    column, _row = right_probe_cell(FAR_X, RIGHT_HALF_WIDTH, 4, DEFAULT_PROBE_Y)
    assert column >> 8 != 0, "this case's column has no high byte, so it states nothing"
    assert expected["d0"] == ((column & 0xff00) | STEP_BLOCKED)


def test_the_ground_word_sits_over_the_row_products_high_half_on_the_way_right():
    """`clr.w d1` clears the low word and leaves the `mulu.w` product's high one, exactly as the
    leftward probe does — the same instruction, reached from the other body."""
    expected = _run_step_right("product-over-65535", RIGHT_X, RIGHT_HALF_WIDTH, 0, {},
                               default_stride=0x100, actor_y=0x4001)
    assert expected["d1"] >> 16 != 0, (
        "the row product's high half is zero here, so this case does not reach what it is about")


# --- the shared tail, entered from the RIGHT body ---------------------------------------------------
# `_model_ground` is one model for one piece of code, so these do not re-run all seven of $10a2's
# arms; they run one case per arm to say that $1170 arrives at it with the cell and the index the
# tail expects. The cell a walk stops on is never a block, so the block arm is reached the only way
# either routine allows: a step of 1 into a block, which retries once and commits at zero.
RIGHT_GROUND_CASES = [
    ("cell-is-a-block-with-air-above", 1, {HERE: TILE_BLOCK}, GROUND_HEAD_BIT),
    ("solid-ground-one-row-down", 0, {(0, 1): TILE_BLOCK}, 0),
    ("nothing-underneath", 0, {}, GROUND_NEAR_BIT | GROUND_FAR_BIT),
]


@pytest.mark.parametrize("case,step,tiles,flags", RIGHT_GROUND_CASES,
                         ids=[c[0] for c in RIGHT_GROUND_CASES])
def test_the_rightward_probe_reports_the_same_ground_flags(case, step, tiles, flags):
    expected = _run_step_right(f"right-{case}", RIGHT_X, RIGHT_HALF_WIDTH, step, dict(tiles))
    assert expected["d1"] & WORD_MASK == flags, (
        f"{case}: the tail reported {expected['d1'] & WORD_MASK:#x}, not the {flags:#x} this case "
        f"is about — a seeded neighbour is spelling a tile code by itself")


def test_the_rightward_probes_ground_test_walks_by_the_default_maps_stride_too():
    """THE ASYMMETRY, from the other body. $1170 looks its cell up in WB_COLLISION_MAP_A32 at that
    map's stride and then branches into `move.w $23494.l,d7` — WB_COLLISION_MAP_DEFAULT's word — so
    the blocks planted one and two A32 rows below the cell are not what the tail reads. A port that
    took the walked map's stride here answers GROUND_HEAD/0 instead."""
    assert A32_STRIDE != DEFAULT_STRIDE, "the two strides must differ for this case to mean anything"
    # Inside the A32 mode's own limit, so the walk COMMITS and the case is about the tail alone.
    expected = _run_step_right("right-a32-map-default-stride", A32_INSIDE_LIMIT_X,
                               RIGHT_HALF_WIDTH, 0, {(0, 1): TILE_BLOCK, (0, 2): TILE_BLOCK},
                               a32=True)
    assert expected["d0"] & BYTE_MASK == STEP_CLEAR, "the walk clamped, so this case moved the actor"
    assert (expected["d1"] & WORD_MASK) == GROUND_NEAR_BIT | GROUND_FAR_BIT, (
        f"the tail read d1={expected['d1'] & WORD_MASK:#x}, so it stepped by the map it walked "
        f"rather than by WB_COLLISION_MAP_DEFAULT's stride")


# --- the registers the walk leaves behind ------------------------------------------------------------

@pytest.mark.parametrize("high", [0x00000000, 0xdead0000], ids=lambda v: f"d7hi{v >> 16:#06x}")
def test_only_the_low_word_of_the_rightward_step_is_read(high):
    """`add.w d7,d0`, `subq.w #1,d7` and `add.w d7,(a0)` are all word operations, so a caller's
    rubbish above the step must not reach the walk — and must still be there at the `rts`, the
    tail's `move.w $23494.l,d7` being a word write as well."""
    _run_step_right(f"right-step-high-{high:#x}", RIGHT_X, RIGHT_HALF_WIDTH, high | 8, {})


def test_the_probe_row_is_the_pixel_above_the_actors_own_y():
    """`subq.w #1,d1` at $1188. Every other case in this file puts the actor one pixel INSIDE its
    row, where `y` and `y - 1` name the same cell and the instruction is invisible; this one stands
    it exactly ON a cell boundary, where the two differ by a whole row. It covers $10a2 as well —
    both probes take their row from `actor_probe_row`, which is the mutation sweep's finding."""
    on_boundary = PROBE_ROW * CELL_PIXELS
    column, row = right_probe_cell(RIGHT_X, RIGHT_HALF_WIDTH, 4, on_boundary)
    assert row == PROBE_ROW - 1, "this case's y does not straddle a cell boundary at all"

    expected = _run_step_right("row-on-a-cell-boundary", RIGHT_X, RIGHT_HALF_WIDTH, 4,
                               {HERE: TILE_BLOCK}, actor_y=on_boundary)
    assert expected["a6"] == _cell_of(MAP_DEFAULT, DEFAULT_STRIDE, column, row), (
        f"the cell is {expected['a6']:#x}, not row {row}'s — the probe took its row from y itself")
    assert expected["d0"] & BYTE_MASK == STEP_BLOCKED, (
        "the block this case seeds in that row was not found, so the walk looked somewhere else")


def test_the_head_clears_both_registers_as_longs():
    """`moveq #$0,d0 / moveq #$0,d1` at $1174/$1176 are LONG writes, so a caller's rubbish above d0
    and d1 does not come back — while the same rubbish above d2, d3 and d6 does, those being written
    a word or a byte at a time further down."""
    entry = {"d0": 0xdead0000, "d1": 0xbeef0000, "d2": 0xcafe0000, "d3": 0xf00d0000,
             "d6": 0x12345600}
    expected = _run_step_right("right-entry-high-halves", RIGHT_X, RIGHT_HALF_WIDTH, 8, {},
                               entry=entry)
    assert expected["d0"] >> 16 == 0 and expected["d1"] >> 16 == 0, (
        f"the head left d0={expected['d0']:#010x} d1={expected['d1']:#010x} over the caller's high "
        f"halves, so it wrote words rather than longs")
    for reg in ("d2", "d3"):
        assert expected[reg] >> 16 == entry[reg] >> 16, (
            f"{reg} came back {expected[reg]:#010x}, so its entry high half did not survive")
    assert expected["d6"] >> 8 == entry["d6"] >> 8, (
        f"d6 came back {expected['d6']:#010x}, so `move.b #$ff,d6` wrote more than a byte")


# --- what the two probes are to each other, and to the level's own edge ------------------------------
STEP_PROBE_CALLERS = 41
# How far a $1170 site can be from the nearest $10a2 one. Every site is inside this, which is what
# says the two are the arms of one direction test rather than two independent interfaces.
PAIRED_WITHIN_BYTES = 0x80
LIMIT_WRITE_SITE = 0xfb1c           # the one place WB_BG_SCROLL_LIMIT_X is written
LIMIT_COMPARE_SITE = 0x79d8         # ...and the scroll's own `cmp.w` against it


def test_both_probes_have_forty_one_callers_and_nothing_else_reaches_them():
    """A whole-image scan in all three encodings: 41 `bsr` sites reach $1170 and 41 reach $10a2, no
    `jsr`/`jmp` names either, and every rightward site sits within PAIRED_WITHIN_BYTES of a leftward
    one — the two arms of a direction test, which is why they are called the same number of times."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    right = leaf.entry_of("actor_step_right_against_map")
    left = leaf.entry_of("actor_step_left_against_map")

    sites = _relative_sites(program, (right, left))
    assert len(sites[right]) == len(sites[left]) == STEP_PROBE_CALLERS, (
        f"$1170 has {len(sites[right])} `bsr` callers and $10a2 {len(sites[left])}, not "
        f"{STEP_PROBE_CALLERS} each")
    absolute = _absolute_sites(program, (right, left))
    assert absolute == {right: [], left: []}, (
        f"a `jsr`/`jmp` names one of the probes as well: "
        f"{{k: [hex(a) for a in v] for k, v in absolute.items()}}")

    stray = [at for at in sites[right]
             if min(abs(at - other) for other in sites[left]) > PAIRED_WITHIN_BYTES]
    assert not stray, (
        f"{[hex(a) for a in stray]} call $1170 with no $10a2 site within "
        f"{PAIRED_WITHIN_BYTES:#x} bytes")


def test_the_rightward_probe_has_no_rts_and_branches_into_the_leftward_ones_tail():
    """$1170 does not return: both of its exits `bra.w $111a`, thirteen instructions inside $10a2.
    Three branches in the whole image reach that address — one from $10a2's own clear arm and these
    two — and the tail is therefore SHARED CODE, which is why `map_ground_under_cell` is one
    function and `_model_ground` one model."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    right = leaf.entry_of("actor_step_right_against_map")
    left = leaf.entry_of("actor_step_left_against_map")
    tail = _ground_test_at()

    assert left < tail < left + len(ENTRY_BYTES["actor_step_left_against_map"]), (
        f"the tail at {tail:#x} is not inside $10a2's own body")
    assert RTS not in ENTRY_BYTES["actor_step_right_against_map"], (
        "the rightward probe carries an `rts`, so it does not end in the other's tail after all")

    branches = _relative_sites(program, (tail,), high_byte=BRA_HIGH_BYTE)[tail]
    body = len(ENTRY_BYTES["actor_step_right_against_map"])
    from_right = [at for at in branches if right <= at < right + body]
    assert len(from_right) == 2 and len(branches) == 3, (
        f"{[hex(a) for a in branches]} branch to the tail, {[hex(a) for a in from_right]} of them "
        f"from $1170 — the reconstruction assumes two exits and one other entrance")


def test_the_clamps_bias_is_the_one_the_limit_word_was_built_with():
    """WB_BG_SCROLL_LIMIT_BIAS is not this routine's own number. $83b2 has exactly three operand
    sites: the scroll's `cmp.w` against it, the `move.w` at $11c4 this routine reads it with, and
    the ONE write, at $fb1c — which is preceded by `moveq #$0,d0 / move.w (a0)+,d0 / lsl.w #4,d0 /
    subi.w #$f0,d0`, i.e. a cell count turned into pixels with the SAME $f0 taken off it. So
    `limit + bias` here recovers the number the limit was made from."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    right = leaf.entry_of("actor_step_right_against_map")

    read_site = right + ENTRY_BYTES["actor_step_right_against_map"].index(
        move_w_abs_l_dn(D0, SCROLL_LIMIT_X)) + WORD_LEN
    sites = _operand_sites(program, SCROLL_LIMIT_X)
    assert sites == [read_site, LIMIT_COMPARE_SITE + WORD_LEN, LIMIT_WRITE_SITE + WORD_LEN], (
        f"{[hex(a) for a in sites]} spell $83b2, not the three operands this case names")

    setup = (moveq_0_dn(D0) + move_w_postinc_dn(D0, A0) + lsl_w_imm_dn(CELL_SHIFT, D0)
             + subi_w_dn(D0, LIMIT_BIAS) + leaf.MOVE_W_D0_ABS_L + longword(SCROLL_LIMIT_X))
    at = LIMIT_WRITE_SITE + len(leaf.MOVE_W_D0_ABS_L) + LONGWORD_LEN - len(setup)
    assert program[at:at + len(setup)] == setup, (
        f"the limit at {LIMIT_WRITE_SITE:#x} is not built by taking {LIMIT_BIAS:#x} off a shifted "
        f"cell count: {program[at:at + len(setup)].hex()}")


# --- $13be/$13c8: the cell lookup -----------------------------------------------------------------
# Both bodies are straight-line — four instructions and sixteen, no loop — so the cap is that count
# rather than a geometry, and a run that fell on into $1400 blows it instead of returning something
# plausible.
LOOKUP_INSN_CAP = 24

# Which map_cell_probe field carries which register, IN THE STRUCT'S OWN ORDER. Stated once: the
# ctypes mirror below is built from it, and every case asserts the ORACLE's register and the
# reconstruction's field against the same model entry — so a field wired to the wrong register
# cannot pass by being read the same wrong way twice.
PROBE_FIELD_BY_REG = {"a6": "cell", "d2": "sub_cell", "d3": "cell_index",
                      "d7": "span", "d0": "column", "d1": "row"}
# What a case may seed. a6 is left out: the `lea` at $13de/$13e8 overwrites it whatever it held, so
# seeding it would state nothing.
LOOKUP_ENTRY_REGS = frozenset(PROBE_FIELD_BY_REG) - {"a6"}


class MapCellProbe(ctypes.Structure):
    """include/map.h's `map_cell_probe` — the same fields in the same order, which is what lets a
    case hand the reconstruction its entry registers and read its six results back."""
    _fields_ = [(field, ctypes.c_uint32) for field in PROBE_FIELD_BY_REG.values()]


_LOOKUP_FNS = {name: leaf.bind(name, leaf.IMAGE_ARG + [ctypes.c_uint32,
                                                       ctypes.POINTER(MapCellProbe)])
               for name in ("actor_map_cell_from_actor_x", "actor_map_cell_lookup")}


def _lookup_glue(name, actor, probe):
    """The reconstruction's whole result is an in/out struct rather than a returned d0, so the case
    keeps the struct and reads it after the run — `leaf.register_glue` covers only a d0."""
    return lambda _lib, image: _LOOKUP_FNS[name](image, actor, ctypes.byref(probe))


def _model_cell_lookup(image, actor, entry):
    """The six registers $13c8 leaves, given the ones it is entered with."""
    pixel_x = entry.get("d0", 0) & WORD_MASK
    column = (s16(pixel_x) >> CELL_SHIFT) & WORD_MASK
    row = (s16(u16(image, actor + ACTOR_Y)) >> CELL_SHIFT) & WORD_MASK
    map_base = MAP_A32 if u16(image, FLAG_A32) else MAP_DEFAULT
    product = u16(image, map_base) * row            # `mulu.w` — UNSIGNED, and the whole 32 bits
    index = (product + column) & WORD_MASK          # `add.w` — the low word only
    return {
        "a6": (map_base + MAP_CELLS + s16(index)) & 0xffffffff,
        "d2": _over_high_half(entry.get("d2", 0), pixel_x & CELL_MASK),
        "d3": _over_high_half(product, index),
        "d7": _over_high_half(entry.get("d7", 0), 2 * u16(image, actor + HALF_WIDTH)),
        "d0": _over_high_half(entry.get("d0", 0), column),
        "d1": _over_high_half(entry.get("d1", 0), row),
    }


def _model_cell_from_actor_x(image, actor, entry):
    """$13be, which COMPOSES: it clears d0 and d1 as longs, computes the actor's left edge and then
    IS the lookup — the same composition src/map.c's two functions are."""
    left_edge = dict(entry)
    left_edge["d0"] = (u16(image, actor + ACTOR_X) - u16(image, actor + HALF_WIDTH)) & WORD_MASK
    left_edge["d1"] = 0
    return _model_cell_lookup(image, actor, left_edge)


_LOOKUP_MODELS = {"actor_map_cell_from_actor_x": _model_cell_from_actor_x,
                  "actor_map_cell_lookup": _model_cell_lookup}

LOOKUP_X = 0x200                        # mid-window, and a whole number of cells in
LOOKUP_HALF_WIDTH = 0x10
LOOKUP_Y = PROBE_ROW * CELL_PIXELS + 1  # inside PROBE_ROW, with rows above and below it


def _run_cell_lookup(name, case, entry=None, actor_x=LOOKUP_X, actor_y=LOOKUP_Y,
                     half_width=LOOKUP_HALF_WIDTH, a32=False, default_stride=DEFAULT_STRIDE):
    """One cell-lookup case, at either entry point.

    ``entry`` is the ENTRY register longs. $13c8 takes its pixel x in d0's LOW WORD and leaves every
    other register's high half untouched, so a case seeds both through this; $13be takes the pixel x
    from the record instead (``actor_x`` minus ``half_width``) and clears d0/d1 as longs.

    Returns the MODEL, which has already been required to equal the oracle's six registers and the
    reconstruction's six fields — so a case asserting on it is asserting on both.
    """
    entry = dict(entry or {})
    assert set(entry) <= LOOKUP_ENTRY_REGS, (
        f"{sorted(set(entry) - LOOKUP_ENTRY_REGS)} is not a register this routine reads or leaves")

    salt = case_salt(case)
    pokes = map_pokes(salt, default_stride=default_stride)
    pokes[FLAG_A32] = word(0xffff if a32 else 0)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_X] = word(actor_x)
    pokes[ACTOR + ACTOR_Y] = word(actor_y)
    pokes[ACTOR + HALF_WIDTH] = word(half_width)

    image = harness.make_image(pokes)
    expected = _LOOKUP_MODELS[name](image, ACTOR, entry)
    probe = MapCellProbe(**{PROBE_FIELD_BY_REG[reg]: value for reg, value in entry.items()})

    what = f"{name} {case}"
    # No `allowed` bands and no attribution pass: this routine STORES NOTHING, so there is not a
    # byte for the poison pass to invert and the write set below is required to be empty instead.
    info = leaf.run(name, _lookup_glue(name, ACTOR, probe), [], what,
                    regs=dict(entry, a0=ACTOR, _pokes=pokes), poison=False,
                    max_insns=LOOKUP_INSN_CAP)

    written = program_writes(info)
    assert not written, (
        f"{what}: the original wrote {sorted(hex(a) for a in written)} — it stores nothing, and "
        f"its whole surface is the six registers below")
    for reg, field in PROBE_FIELD_BY_REG.items():
        assert info["regs"][reg] == expected[reg], (
            f"{what}: the original left {reg}={info['regs'][reg]:#010x}, not the model's "
            f"{expected[reg]:#010x}")
        assert getattr(probe, field) == expected[reg], (
            f"{what}: the reconstruction's {field} is {getattr(probe, field):#010x}, not the "
            f"model's {expected[reg]:#010x} ({reg})")
    return expected


@pytest.mark.parametrize("a32", [False, True], ids=["default-map", "a32-map"])
def test_the_lookup_selects_the_map_the_mode_flag_names(a32):
    """`tst.w $a32.w / beq $13e8` at $13d6 picks WB_COLLISION_MAP_A32 when the flag is NONZERO and
    WB_COLLISION_MAP_DEFAULT when it is zero — the two `lea`s at $13de and $13e8. The two maps are
    seeded with DIFFERENT strides, so this states the pitch the row was multiplied by as well as
    the base the cell is measured from: neither map's answer is reachable from the other's."""
    assert A32_STRIDE != DEFAULT_STRIDE, "equal strides make the two maps indistinguishable here"
    expected = _run_cell_lookup("actor_map_cell_lookup", f"selected-map-{a32}",
                                entry={"d0": LOOKUP_X}, a32=a32)
    base, stride = (MAP_A32, A32_STRIDE) if a32 else (MAP_DEFAULT, DEFAULT_STRIDE)
    assert expected["a6"] == base + MAP_CELLS + stride * PROBE_ROW + (LOOKUP_X >> CELL_SHIFT), (
        f"the cell is {expected['a6']:#x}, which is not row {PROBE_ROW} of the map at {base:#x} at "
        f"its own stride of {stride:#x}")


def test_a_column_left_of_the_origin_is_negative():
    """`asr.w #4,d0` at $13d2 is an ARITHMETIC shift, so a pixel x left of the map's origin names
    column -1 and the cell lands one BELOW the map's first, not $fff cells along it."""
    expected = _run_cell_lookup("actor_map_cell_lookup", "negative-column",
                                entry={"d0": (-CELL_PIXELS) & WORD_MASK}, actor_y=0)
    assert expected["d0"] & WORD_MASK == WORD_MASK, (
        f"the column is {expected['d0'] & WORD_MASK:#x}, so the shift was not arithmetic")
    assert expected["a6"] == MAP_DEFAULT + MAP_CELLS - 1


def test_a_row_above_the_origin_is_negative_and_then_multiplied_UNSIGNED():
    """`asr.w #4,d1` at $13d4 is arithmetic too — but `mulu.w d1,d3` at $13f0 is UNSIGNED, so the
    negative row it produces is multiplied as $ffff rather than as -1. That is the pair of readings
    a `muls.w` would collapse."""
    expected = _run_cell_lookup("actor_map_cell_lookup", "negative-row",
                                entry={"d0": LOOKUP_X}, actor_y=(-CELL_PIXELS) & WORD_MASK)
    assert expected["d1"] & WORD_MASK == WORD_MASK, "the row shift was not arithmetic"
    assert expected["d3"] & ~WORD_MASK == (DEFAULT_STRIDE * WORD_MASK) & ~WORD_MASK != 0, (
        f"d3's high half is {expected['d3'] >> 16:#x}, not the "
        f"{(DEFAULT_STRIDE * WORD_MASK) >> 16:#x} an UNSIGNED multiply of row $ffff gives")


# A stride and a row whose product overflows sixteen bits, so d3's high half is load-bearing.
BIG_STRIDE = 0x1000
BIG_ROW = 0x1f


def test_the_row_product_is_a_longword_the_column_add_never_carries_into():
    """`mulu.w d1,d3` at $13f0 writes all 32 bits and the `add.w d0,d3` at $13f2 only the low word.
    So a product past $ffff comes back in d3's high half — the half $10a2's own ground word sits
    over — and a column that overflows the low word does NOT carry into it."""
    product = BIG_STRIDE * BIG_ROW
    assert product > WORD_MASK, "this case's product does not reach d3's high half at all"
    expected = _run_cell_lookup("actor_map_cell_lookup", "product-over-65535",
                                entry={"d0": (-CELL_PIXELS) & WORD_MASK},
                                actor_y=BIG_ROW * CELL_PIXELS, default_stride=BIG_STRIDE)
    assert expected["d3"] >> 16 == product >> 16, (
        f"d3's high half is {expected['d3'] >> 16:#x}, not the product's own {product >> 16:#x}")
    assert expected["d3"] != (product + WORD_MASK) & 0xffffffff, (
        "d3 is the whole 32-bit sum, so the column add carried into the product's high half")


# A stride and a row whose product alone reaches $8000, so the index the `lea` sign-extends is
# negative with no help from the column.
SIGNED_INDEX_STRIDE = 0x800
SIGNED_INDEX_ROW = 0x10


def test_a_cell_index_past_7fff_addresses_below_the_map():
    """`lea 2(a6,d3.w),a6` at $13f4 takes the index's LOW WORD SIGN-EXTENDED, and the `move.w (a6)+`
    above it has already stepped a6 past the stride word — which is where WB_COLLISION_MAP_CELLS
    comes from. An index of $8000 therefore addresses $8000 bytes BELOW the map, not above it."""
    expected = _run_cell_lookup("actor_map_cell_lookup", "index-past-7fff", entry={"d0": 0},
                                actor_y=SIGNED_INDEX_ROW * CELL_PIXELS,
                                default_stride=SIGNED_INDEX_STRIDE)
    index = expected["d3"] & WORD_MASK
    assert index == SIGNED_INDEX_STRIDE * SIGNED_INDEX_ROW >= 0x8000, (
        f"the index is {index:#x}, which does not reach the sign bit this case is about")
    assert expected["a6"] == MAP_DEFAULT + MAP_CELLS - (WORD_MASK + 1 - index), (
        f"the cell is {expected['a6']:#x}, so the index was zero-extended and the pointer ran far "
        f"above the map instead of below it")


# Rubbish above every register the routine writes a WORD of, each a different number so a case can
# tell them apart if one leaks into another.
ENTRY_HIGH_HALVES = {"d0": 0xdead0000, "d1": 0xbeef0000, "d2": 0xcafe0000, "d3": 0xf00d0000,
                     "d7": 0x12340000}


def test_every_word_write_leaves_the_callers_high_half_alone():
    """`move.w`, `andi.w`, `asr.w` and `add.w` all write a WORD of a longword register, so d0, d1,
    d2 and d7 come back with the CALLER's own high half over the routine's answer. d3 is the one
    that does not: `mulu.w` writes all 32 bits of it."""
    entry = dict(ENTRY_HIGH_HALVES, d0=ENTRY_HIGH_HALVES["d0"] | LOOKUP_X)
    expected = _run_cell_lookup("actor_map_cell_lookup", "entry-high-halves", entry=entry)
    for reg in ("d0", "d1", "d2", "d7"):
        assert expected[reg] >> 16 == entry[reg] >> 16 != 0, (
            f"{reg} came back {expected[reg]:#010x}, so its entry high half did not survive")
    assert expected["d3"] >> 16 == 0, (
        f"d3 came back {expected['d3']:#010x}, keeping a high half the `mulu.w` writes over — this "
        f"case's product is {DEFAULT_STRIDE * PROBE_ROW:#x}, which has none of its own")


@pytest.mark.parametrize("pixel_x", [0x000, 0x001, 0x00f, 0x210, 0x21b, (-1) & WORD_MASK],
                         ids=lambda v: f"x{v:#06x}")
def test_the_sub_cell_is_the_pixel_xs_own_low_nibble(pixel_x):
    """`move.w d0,d2 / andi.w #$f,d2` at $13c8/$13ca, taken BEFORE the shift at $13d2 — so it is the
    position within the cell of the x the caller handed over, negative x included."""
    expected = _run_cell_lookup("actor_map_cell_lookup", f"sub-cell-{pixel_x:#x}",
                                entry={"d0": pixel_x, "d2": ENTRY_HIGH_HALVES["d2"]})
    assert expected["d2"] == ENTRY_HIGH_HALVES["d2"] | (pixel_x & CELL_MASK)


@pytest.mark.parametrize("half_width", [0, 1, 0x10, 0x7fff, 0x9000], ids=lambda v: f"hw{v:#06x}")
def test_the_span_is_twice_the_half_width_as_a_word(half_width):
    """`move.w 14(a0),d7 / add.w d7,d7` at $13f8/$13fc — a WORD doubling of the footprint, so a
    half-width past $7fff wraps instead of widening into d7's high half."""
    expected = _run_cell_lookup("actor_map_cell_lookup", f"span-{half_width:#x}",
                                entry={"d0": LOOKUP_X, "d7": ENTRY_HIGH_HALVES["d7"]},
                                half_width=half_width)
    assert expected["d7"] == ENTRY_HIGH_HALVES["d7"] | ((2 * half_width) & WORD_MASK)


@pytest.mark.parametrize("case,actor_x,half_width", [
    ("inside-the-map", LOOKUP_X, LOOKUP_HALF_WIDTH),
    ("edge-on-a-cell-boundary", LOOKUP_X + LOOKUP_HALF_WIDTH, LOOKUP_HALF_WIDTH),
    # The edge goes past the origin, and then past $8000 the other way.
    ("edge-left-of-the-origin", 0x08, LOOKUP_HALF_WIDTH),
    ("edge-wraps-the-word", 0, 0x7fff),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_prelude_looks_the_actors_left_edge_up(case, actor_x, half_width):
    """`move.w (a0),d0 / sub.w 14(a0),d0` at $13c2/$13c4 — the left edge as a WORD subtraction that
    wraps, which is the whole of what $13be adds to the lookup."""
    expected = _run_cell_lookup("actor_map_cell_from_actor_x", f"left-edge-{case}",
                                actor_x=actor_x, half_width=half_width)
    left_edge = (actor_x - half_width) & WORD_MASK
    assert expected["d2"] == left_edge & CELL_MASK, (
        f"{case}: the sub-cell is {expected['d2']:#x}, not the left edge {left_edge:#x}'s own")
    assert expected["d0"] == (s16(left_edge) >> CELL_SHIFT) & WORD_MASK


def test_the_prelude_clears_both_registers_as_longs():
    """`moveq #$0,d0 / move.l d0,d1` at $13be/$13c0 are LONG writes, so a caller's rubbish above d0
    and d1 does not come back — while the same rubbish above d2 and d7 does, those being written a
    word at a time further down. It is exactly what a standalone $13c8 hands back that $13be is
    clearing, which is why the two entry points are one function with a prelude."""
    expected = _run_cell_lookup("actor_map_cell_from_actor_x", "prelude-clears-the-longs",
                                entry=dict(ENTRY_HIGH_HALVES))
    assert expected["d0"] >> 16 == 0 and expected["d1"] >> 16 == 0, (
        f"the prelude left d0={expected['d0']:#010x} d1={expected['d1']:#010x} over the caller's "
        f"high halves, so it wrote words rather than longs")
    for reg in ("d2", "d7"):
        assert expected[reg] >> 16 == ENTRY_HIGH_HALVES[reg] >> 16, (
            f"{reg} passes through the prelude untouched, so its high half must still survive")


def test_the_prelude_falls_through_into_the_lookup():
    """$13be has no `rts`: it ends exactly where $13c8 begins, which is the whole reason
    `actor_map_cell_from_actor_x` is written as a prelude that CALLS the lookup."""
    prelude = leaf.entry_of("actor_map_cell_from_actor_x")
    lookup = leaf.entry_of("actor_map_cell_lookup")
    assert prelude + len(ENTRY_BYTES["actor_map_cell_from_actor_x"]) == lookup, (
        f"the prelude at {prelude:#x} does not end at the lookup's {lookup:#x}")
    assert RTS not in ENTRY_BYTES["actor_map_cell_from_actor_x"], (
        "the prelude carries an `rts`, so it does not fall through and the two are separate "
        "routines after all")


# The `bsr` sites the lookup scan finds, all three inside $1334 — the un-ported tier above the map
# probes, which is what supplies the register arguments $1400 then reads.
PRELUDE_CALL_SITES = (0x13ae, 0x13b6)
LOOKUP_CALL_SITES = (0x1344,)


def test_the_pairs_only_callers_are_its_two_entry_conventions():
    """A whole-image scan: THREE `bsr` sites reach the pair, and which entry each takes is what says
    the pixel x is sometimes the caller's own. $13ae and $13b6 enter the PRELUDE, which computes the
    actor's left edge; $1344 enters the LOOKUP directly, and the instruction above it is
    `move.w (a0),d0` — the actor's x with no half-width taken off it."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    prelude = leaf.entry_of("actor_map_cell_from_actor_x")
    lookup = leaf.entry_of("actor_map_cell_lookup")

    sites = _relative_sites(program, (prelude, lookup))
    assert sites[prelude] == list(PRELUDE_CALL_SITES), (
        f"the prelude's callers are {[hex(a) for a in sites[prelude]]}, not "
        f"{[hex(a) for a in PRELUDE_CALL_SITES]}")
    assert sites[lookup] == list(LOOKUP_CALL_SITES), (
        f"the lookup's callers are {[hex(a) for a in sites[lookup]]}, not "
        f"{[hex(a) for a in LOOKUP_CALL_SITES]}")

    load_x = move_w_ind_dn(D0, A0, ACTOR_X)
    call = LOOKUP_CALL_SITES[0]
    at = call - len(load_x)
    assert program[at:call] == load_x, (
        f"the `bsr` at {call:#x} is preceded by {program[at:call].hex()}, not the "
        f"`move.w (a0),d0` this battery reads as its pixel x")


# --- $1400: the platform settle -------------------------------------------------------------------
# The scan steps one cell per WB_MAP_CELL_PIXELS of span; the cap is that geometry plus the band
# test and whichever arm runs.
SETTLE_INSN_PER_CELL = 8
SETTLE_INSN_TAIL = 48
SETTLE_COLUMN = 0x20            # the cell $13c8 would have handed over, mid-window


def _footprint_edge(remaining):
    """The four instructions BOTH settles spell before their sub-cell compare: `move.w d7,d0 /
    asr.w #1,d0 / neg.w d0 / andi.w #$f,d0`, over a `moveq #$0,d0` that cleared the whole long. One
    model because it is the same four instructions in both bodies, which is why src/map.c has one
    `footprint_reaches_next_cell` helper and two scans rather than the other way round."""
    return (-(s16(remaining) >> 1)) & CELL_MASK


def _pass_through(entry):
    """Every register the oracle reports, as the case seeded it.

    The models below start from this and overwrite what their routine writes, so a register NOTHING
    in the chain touches is stated as unchanged rather than left out — which is how d4, d5 and d6
    are covered at all."""
    return {reg: entry.get(reg, 0) for reg in emu.REPORTED_REGS}


def _model_settle(image, actor, cell, span, subcell, entry=None):
    """{writes} and every register $1400 leaves, given the ones it is entered with."""
    regs = _pass_through(dict(entry or {}))
    remaining = span & WORD_MASK
    cursor = cell
    while image[cursor] != TILE_PLATFORM and s16(remaining) >= CELL_PIXELS:
        cursor = (cursor + 1) & 0xffffffff
        remaining = (remaining - CELL_PIXELS) & WORD_MASK
    found = image[cursor] == TILE_PLATFORM
    if not found:
        # `moveq #$0,d0` clears the WHOLE long before the edge is built in its low word, so this is
        # the one path on which the caller's high half does NOT survive into d0.
        regs["d0"] = _footprint_edge(remaining)
        if s16(subcell & WORD_MASK) >= regs["d0"]:
            cursor = (cursor + 1) & 0xffffffff
            found = image[cursor] == TILE_PLATFORM
    regs["a6"] = cursor
    regs["d7"] = _over_high_half(span, remaining)

    writes = {}
    flags = image[actor + ACTOR_FLAGS]
    if found:
        actor_y = s16(u16(image, actor + ACTOR_Y))
        regs["d1"] = _over_high_half(regs["d1"], u16(image, actor + ACTOR_Y))
        top = s16(u16(image, PLATFORM_Y) - PLATFORM_Y_ABOVE)
        regs["d0"] = _over_high_half(regs["d0"], top)
        if not top > actor_y:
            regs["d0"] = _over_high_half(regs["d0"], top + PLATFORM_Y_BAND)
        if not top > actor_y and not s16(top + PLATFORM_Y_BAND) < actor_y:
            _put_word(writes, actor + ACTOR_Y,
                      u16(image, PLATFORM_Y) - PLATFORM_STAND_OFFSET)
            writes[actor + ACTOR_FLAGS] = ((flags | (1 << SUPPORTED_BIT))
                                           & ~(1 << FALLING_BIT) & ~(1 << LAUNCHED_BIT)) & BYTE_MASK
            writes[actor + FLAGS2] = image[actor + FLAGS2] | (1 << LANDED_BIT)
            writes[actor + SPEED] = 0
            return writes, regs

    if not flags & (1 << SUPPORTED_BIT):
        writes[actor + ACTOR_FLAGS] = flags | (1 << FALLING_BIT)
    writes[actor + FLAGS2] = image[actor + FLAGS2] & ~(1 << LANDED_BIT) & BYTE_MASK
    return writes, regs


def _run_settle(case, span, subcell, tiles, actor_y, platform_y, flags=0):
    salt = case_salt(case)
    pokes = map_pokes(salt)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_Y] = word(actor_y)
    pokes[ACTOR + ACTOR_FLAGS] = bytes([flags])
    pokes[PLATFORM_Y] = word(platform_y)

    cell = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE, SETTLE_COLUMN, PROBE_ROW)
    for column, code in tiles.items():
        pokes[cell + column] = bytes([code])

    image = harness.make_image(pokes)
    entry = {"a0": ACTOR, "a6": cell, "d7": span, "d2": subcell}
    expected, regs = _model_settle(image, ACTOR, cell, span, subcell, entry)

    what = f"actor_settle_on_platform {case}"
    info = leaf.run("actor_settle_on_platform", _SETTLE(ACTOR, cell, span, subcell),
                    merge_bands(expected), what, poison=False,
                    regs=dict(entry, _pokes=pokes),
                    max_insns=SETTLE_INSN_PER_CELL * (max(s16(span & WORD_MASK), 0) // CELL_PIXELS
                                                      + 1) + SETTLE_INSN_TAIL)
    _assert_writes(info, expected, what)
    _assert_regs(info, regs, what)
    _assert_the_span_comes_back(info, regs, what)
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


# --- $1492: the same footprint, settled onto a block or a ledge ------------------------------------
# $1400's sibling, and NOT a parametrisation of it: it accepts a PAIR of tile codes at each of its
# three test sites, it parks the actor by masking its own y rather than on WB_PLATFORM_Y, and its
# not-found arm is the WHOLE of actor_accelerate_fall — whose 32 bytes sit inside its own span and
# whose `rts` is one of its two exits.
#
# Its scan costs at most ten instructions per cell (two `cmpi.b`/`beq` pairs, the span test and the
# three-instruction step) plus the sub-cell test, the second pair and whichever arm runs.
TILE_SETTLE_INSN_PER_CELL = 10
TILE_SETTLE_INSN_TAIL = 32
# How far past the span's own cells a case seeds: the one more cell the sub-cell test may step onto,
# and a margin either side of that.
TILE_SETTLE_SCAN_MARGIN = 3
# A tile code none of the four tests in this file accept. The map window is seeded ADDRESS-KEYED, so
# a cell a scan walks over could spell $1, $2, $23 or $33 by itself and quietly turn a case into a
# different one; the cases a scan WALKS clear their whole run to this first and then poke the tiles
# they mean.
CLEAR_TILE = 0

_SETTLE_TILE = leaf.register_glue("actor_settle_on_tile_1_or_2", [ctypes.c_uint32] * 4,
                                  ctypes.c_uint32)


def _cell_is_ground(image, cell):
    """The PAIR $1492 accepts, at every one of its three test sites."""
    return image[cell] in (TILE_BLOCK, TILE_LEDGE)


def _model_accelerate_fall(image, actor):
    """$14d6, the 32 bytes inside $1492's own span, as ({writes}, d0). d0 is the PRE-increment
    speed byte over a `moveq`-cleared long, which is what both ways into it leave behind."""
    writes = {}
    flags = image[actor + ACTOR_FLAGS]
    writes[actor + ACTOR_FLAGS] = ((flags & ~(1 << SUPPORTED_BIT)) | (1 << FALLING_BIT)) & BYTE_MASK
    speed = image[actor + SPEED]
    if speed != FALL_SPEED_MAX:
        writes[actor + SPEED] = (speed + 1) & BYTE_MASK
    return writes, speed


def _model_settle_tile_1_or_2(image, actor, cell, span, subcell, entry=None):
    """{writes} and every register $1492 leaves, given the ones it is entered with."""
    regs = _pass_through(dict(entry or {}))
    remaining = span & WORD_MASK
    cursor = cell
    while not _cell_is_ground(image, cursor) and s16(remaining) >= CELL_PIXELS:
        cursor = (cursor + 1) & 0xffffffff
        remaining = (remaining - CELL_PIXELS) & WORD_MASK
    found = _cell_is_ground(image, cursor)
    if not found:
        regs["d0"] = _footprint_edge(remaining)         # `moveq #$0,d0` — the WHOLE long
        if s16(subcell & WORD_MASK) >= regs["d0"]:
            cursor = (cursor + 1) & 0xffffffff
            found = _cell_is_ground(image, cursor)
    regs["a6"] = cursor
    regs["d7"] = _over_high_half(span, remaining)

    if not found:
        writes, regs["d0"] = _model_accelerate_fall(image, actor)
        return writes, regs

    writes = {}
    _put_word(writes, actor + ACTOR_Y, u16(image, actor + ACTOR_Y) & ~CELL_MASK)
    writes[actor + ACTOR_FLAGS] = ((image[actor + ACTOR_FLAGS] | (1 << SUPPORTED_BIT))
                                   & ~(1 << FALLING_BIT) & ~(1 << LAUNCHED_BIT)) & BYTE_MASK
    writes[actor + SPEED] = 0
    return writes, regs


def _scan_cells(span):
    """How many cells of map a footprint scan of ``span`` pixels can read — its own geometry, not a
    round number: one cell per WB_MAP_CELL_PIXELS of a span the `blt` reads as SIGNED, plus the one
    the sub-cell test may step onto and a margin either side."""
    return max(s16(span & WORD_MASK), 0) // CELL_PIXELS + TILE_SETTLE_SCAN_MARGIN


def _run_settle_tile(case, span, subcell, tiles, actor_y=DEFAULT_PROBE_Y, flags=0, speed=0,
                     entry=None):
    """One $1492 case. ``tiles`` is {column offset: code} from the cell a6 names."""
    salt = case_salt(case)
    pokes = map_pokes(salt)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_Y] = word(actor_y)
    pokes[ACTOR + ACTOR_FLAGS] = bytes([flags])
    pokes[ACTOR + SPEED] = bytes([speed])

    cell = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE, SETTLE_COLUMN, PROBE_ROW)
    for column in range(_scan_cells(span)):
        pokes[cell + column] = bytes([CLEAR_TILE])
    for column, code in tiles.items():
        pokes[cell + column] = bytes([code])

    image = harness.make_image(pokes)
    seeded = dict(entry or {}, a0=ACTOR, a6=cell, d7=span, d2=subcell)
    expected, regs = _model_settle_tile_1_or_2(image, ACTOR, cell, span, subcell, seeded)

    what = f"actor_settle_on_tile_1_or_2 {case}"
    # No attribution pass: the routine READS the speed byte and the y word it also writes, so
    # inverting either feeds a different record back into the run — `_assert_writes` states the
    # write set exactly instead, which is this whole file's reason for `poison=False`.
    info = leaf.run("actor_settle_on_tile_1_or_2", _SETTLE_TILE(ACTOR, cell, span, subcell),
                    merge_bands(expected), what, poison=False, regs=dict(seeded, _pokes=pokes),
                    max_insns=(TILE_SETTLE_INSN_PER_CELL * (_scan_cells(span) + 1)
                               + TILE_SETTLE_INSN_TAIL))
    _assert_writes(info, expected, what)
    _assert_regs(info, regs, what)
    _assert_the_span_comes_back(info, regs, what)
    return expected, regs


def test_the_clear_tile_code_is_none_of_the_four_the_file_tests_for():
    assert CLEAR_TILE not in (TILE_BLOCK, TILE_LEDGE, TILE_PLATFORM, TILE_33)


@pytest.mark.parametrize("case,span,subcell,tiles", [
    ("under-the-first-cell-block", 0, 0, {0: TILE_BLOCK}),
    # The SECOND `cmpi.b` at every site, which a port carrying $1400's single test would fail.
    ("under-the-first-cell-ledge", 0, 0, {0: TILE_LEDGE}),
    ("one-cell-along", CELL_PIXELS, 0, {1: TILE_BLOCK}),
    ("one-cell-along-ledge", CELL_PIXELS, 0, {1: TILE_LEDGE}),
    ("two-cells-along", 2 * CELL_PIXELS, 0, {2: TILE_BLOCK}),
    # The leftover span puts the footprint's edge into one more cell only when d2 reaches it, and
    # that extra cell is tested with the pair as well.
    ("subcell-reaches-the-next", 2, CELL_MASK, {1: TILE_BLOCK}),
    ("subcell-reaches-the-next-ledge", 2, CELL_MASK, {1: TILE_LEDGE}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_ground_scan_finds_a_block_or_a_ledge_across_the_footprint(case, span, subcell, tiles):
    writes, _regs = _run_settle_tile(f"tile-settle-{case}", span, subcell, tiles)
    assert writes[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        f"{case}: the actor did not land, so this case is testing the other arm")


def test_the_platform_tile_is_not_one_this_scan_accepts():
    """$23 under the whole footprint, and the routine falls anyway. This is what says $1492 is not
    actor_settle_on_platform with a tile argument: the two accept disjoint sets of codes."""
    writes, _regs = _run_settle_tile("tile-settle-platform-is-not-ground", 2 * CELL_PIXELS, 0,
                                     {0: TILE_PLATFORM, 1: TILE_PLATFORM, 2: TILE_PLATFORM})
    assert not writes[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        "a $23 cell landed the actor, so this scan accepts the platform code after all")


def test_the_landing_arm_snaps_the_actor_to_its_own_cell_boundary():
    """`andi.w #$fff0,2(a0)` — the top of whichever cell the record is in, and NOT a platform word
    read out of memory. The y here is deliberately mid-cell, so the mask is visible."""
    inside_the_cell = PROBE_ROW * CELL_PIXELS + CELL_MASK
    writes, _regs = _run_settle_tile("tile-settle-y-snap", 0, 0, {0: TILE_BLOCK},
                                     actor_y=inside_the_cell)
    assert (int.from_bytes(bytes(writes[ACTOR + ACTOR_Y + i] for i in range(WORD_LEN)), "big")
            == PROBE_ROW * CELL_PIXELS), (
        "the landing arm did not mask the actor's y down to its cell boundary")


def test_the_landing_arm_leaves_the_second_flag_byte_alone():
    """$1400's landing raises WB_ACTOR_FLAGS2_LANDED_BIT and both of its other arms clear it. This
    one never touches 9(a0) at all — the write set says so, since it is stated exactly."""
    seeded_flags = (1 << FALLING_BIT) | (1 << LAUNCHED_BIT) | (1 << MOVING_BIT)
    writes, _regs = _run_settle_tile("tile-settle-flag-byte", 0, 0, {0: TILE_BLOCK},
                                     flags=seeded_flags, speed=5)
    assert ACTOR + FLAGS2 not in writes
    assert writes[ACTOR + ACTOR_FLAGS] == (1 << SUPPORTED_BIT) | (1 << MOVING_BIT), (
        "the landing arm did not clear exactly the falling and launched bits")
    assert writes[ACTOR + SPEED] == 0


@pytest.mark.parametrize("case,span,subcell,tiles", [
    # `blt.w $14d6` at $14c0: d2 short of the edge jumps STRAIGHT into the enclosed routine, past
    # the second pair of tile tests — so the block one cell along is never seen.
    ("blt-into-the-enclosed-routine", 2, 0, {1: TILE_BLOCK}),
    # ...and the other way in: the second pair runs, neither `beq` is taken, and the body falls
    # through $14d2 into the same 32 bytes.
    ("falls-through-into-the-enclosed-routine", 2, CELL_MASK, {}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_both_ways_into_the_enclosed_routine_accelerate_the_fall(case, span, subcell, tiles):
    """The two entrances to actor_accelerate_fall from inside $1492's own body. Both leave through
    its `rts` at $14f4, and both must produce that routine's whole effect."""
    writes, regs = _run_settle_tile(f"tile-settle-{case}", span, subcell, tiles,
                                    flags=1 << SUPPORTED_BIT, speed=3)
    assert writes[ACTOR + ACTOR_FLAGS] == 1 << FALLING_BIT, (
        f"{case}: the supported bit was not cleared and the falling one raised")
    assert writes[ACTOR + SPEED] == 4
    assert regs["d0"] == 3, "d0 does not carry the PRE-increment speed byte"


def test_the_enclosed_routine_stops_accelerating_on_the_terminal_speed():
    """`cmpi.b #$8,d0 / beq` — reached EXACTLY, so a record already at the maximum has its speed
    byte left out of the write set entirely."""
    writes, _regs = _run_settle_tile("tile-settle-terminal-speed", 0, 0, {}, speed=FALL_SPEED_MAX)
    assert ACTOR + SPEED not in writes, "the speed byte was written at the terminal speed"


def test_a_negative_span_never_enters_the_ground_scan():
    """`cmpi.w #$10,d7 / blt` is a SIGNED comparison of the operand here too, so a span with its top
    bit set leaves the scan on the cell it started at — and the sub-cell test then finds the ground
    one along. An unsigned reading walks 2049 cells first."""
    writes, _regs = _run_settle_tile("tile-settle-negative-span", 0x8010, CELL_MASK,
                                     {1: TILE_LEDGE})
    assert writes[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        "the actor did not land, so this case is not reaching the sub-cell arm")


def test_the_ground_scans_span_is_read_as_a_word():
    """`cmpi.w`/`subi.w` on d7 and `move.w d7,d0` in the sub-cell test: a caller's high half must
    not reach either, and must still be there in the d7 the routine leaves."""
    _run_settle_tile("tile-settle-span-high-half", 0xdead0000 | CELL_PIXELS, 0, {1: TILE_BLOCK})


def test_the_platform_scan_hands_back_the_callers_high_half_too():
    """$1400's half of the same claim, which the tile scan's case does not cover: the loop writes
    only d7's LOW word, so a caller's high half survives into the span the routine returns. The
    mutation sweep found it — `settle/span-high-half` survived on the tile settle's case alone.

    src/behavior.c's slots 3 and 6 are the two callers that read a BYTE of what comes back, so the
    high half reaching them is exactly what their `move.b #$2,d7` steps over."""
    _run_settle("settle-span-high-half", 0xdead0000 | CELL_PIXELS, 0, {1: TILE_PLATFORM},
                actor_y=PLATFORM, platform_y=PLATFORM)


def test_the_ground_scan_leaves_the_callers_high_halves_alone():
    """Every register the body writes a word or a byte of, seeded with rubbish above it: d0 is the
    exception (`moveq #$0,d0` clears the long), d7 keeps its high half, and d1/d3/d4/d5/d6 are never
    touched at all."""
    entry = {"d0": 0xdead0000, "d1": 0xbeef0000, "d3": 0xf00d0000, "d4": 0x11110000,
             "d5": 0x22220000, "d6": 0x33330000}
    span = 0xbeef0000 | 2
    _writes, regs = _run_settle_tile("tile-settle-entry-high-halves", span, 0, {}, entry=entry)
    assert regs["d0"] >> 16 == 0, (
        f"d0 came back {regs['d0']:#010x}, so the `moveq` did not clear the whole long")
    assert regs["d7"] >> 16 == span >> 16, "the span's own high half did not survive"


# The one `bsr` that reaches $1492, inside $1334's own body.
TILE_SETTLE_CALL_SITE = 0x13b2


def test_the_ground_scans_only_caller_is_the_fall_pass():
    """A whole-image scan in all three encodings: ONE `bsr` reaches $1492, from inside $1334, and
    the only other branch to it is its own scan closing its loop — which is what says the routine
    is not entered from anywhere but that one call, however deeply its body is entangled with
    actor_accelerate_fall's."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    entry = leaf.entry_of("actor_settle_on_tile_1_or_2")
    body = len(ENTRY_BYTES["actor_settle_on_tile_1_or_2"])
    fall = leaf.entry_of("actor_fall_and_settle")

    calls = _relative_sites(program, (entry,))[entry]
    assert calls == [TILE_SETTLE_CALL_SITE], (
        f"$1492's `bsr` callers are {[hex(a) for a in calls]}, not the one inside $1334")
    assert fall <= TILE_SETTLE_CALL_SITE < fall + len(ENTRY_BYTES["actor_fall_and_settle"]), (
        f"the call at {TILE_SETTLE_CALL_SITE:#x} is not inside $1334's body after all")
    assert _absolute_sites(program, (entry,))[entry] == [], "a `jsr`/`jmp` names $1492 as well"

    branches = _relative_sites(program, (entry,), high_byte=BRA_HIGH_BYTE)[entry]
    assert len(branches) == 1 and entry <= branches[0] < entry + body, (
        f"{[hex(a) for a in branches]} branch to $1492, and this battery reconstructs exactly one "
        f"— the scan's own loop-back, inside the body")


# --- $1334: the fall pass above all of them -------------------------------------------------------
# The tier the two settles hang off: it adds the record's own WB_ACTOR_SPEED to its y and then
# resolves what the record lands on. It has no `rts` on its main path — `bra.w $1400` — and its
# player-only head is the only thing in this file that reads WB_MAP_TILE_33 or writes the three
# WB_TILE_33_* words.
#
# Its cap is the two scans' own geometry (the span both walk is 2 * WB_ACTOR_HALF_WIDTH) plus a
# fixed part: its own two dozen instructions, three cell lookups and both settle tails.
FALL_INSN_FIXED = 24 + 3 * LOOKUP_INSN_CAP + SETTLE_INSN_TAIL + TILE_SETTLE_INSN_TAIL

_FALL = leaf.register_glue("actor_fall_and_settle", [ctypes.c_uint32] * 2, ctypes.c_uint32)


def _tile_33_cell(actor_x, actor_y):
    """Where $1344's lookup lands: the record's OWN x (`move.w (a0),d0` at $1342, with no
    half-width taken off it) and its y as it stands BEFORE the step, neither carrying the probes'
    `subq.w #1`. A case that keyed its head tile off `probe_cell` — the two step probes' expression
    — would plant it a column AND a row away from where this routine looks."""
    return _pixel_to_cell(actor_x & WORD_MASK), _pixel_to_cell(actor_y & WORD_MASK)


def _settle_cell(actor_x, half_width, moved_y):
    """...and where both `bsr $13be` sites land: the record's LEFT EDGE, and the y AFTER the step at
    $138e has moved it. $1492's landing arm may mask that y again between the two calls, but only
    within its own cell, so the two lookups name the same cell — which
    `test_the_second_lookup_starts_the_platform_scan_over` is what states."""
    return _pixel_to_cell((actor_x - half_width) & WORD_MASK), _pixel_to_cell(moved_y & WORD_MASK)


def _model_fall_and_settle(image, actor, entry=None):
    """{writes} and every register $1334 leaves.

    It COMPOSES: the models of $13c8, $13be, $1492, $1400 and $14d6 are the same ones the standalone
    cases above run, called in the order the body calls them and each handed the memory the ones
    before it left — which is what makes the two cell lookups take their row from the y this pass
    has just moved rather than from the seeded one.
    """
    current = bytearray(image)
    regs = _pass_through(dict(entry or {}))
    writes = {}

    def stage(sub):
        writes.update(sub)
        for addr, value in sub.items():
            current[addr] = value

    if u16(current, actor + ACTOR_TYPE) == ACTOR_TYPE_PLAYER:
        regs.update(_model_cell_lookup(current, actor,
                                       dict(regs, d0=u16(current, actor + ACTOR_X), d1=0)))
        if current[regs["a6"]] == TILE_33:
            stage(_word_write(TILE_33_FLAG, TILE_33_RAISED))
            if u16(current, TILE_33_MODE) != 0:
                return writes, regs                     # the `rts` at $1362
        else:
            for at in (TILE_33_MODE, TILE_33_STEP, TILE_33_FLAG):
                stage(_word_write(at, 0))

    if current[actor + ACTOR_FLAGS] & (1 << MOVING_BIT):
        return writes, regs                             # the `rts` at $1380

    speed = current[actor + SPEED]
    regs["d1"] = speed                                  # `moveq #$0,d1` — a LONG clear
    moved_y = (u16(current, actor + ACTOR_Y) + speed) & WORD_MASK
    regs["d0"] = _over_high_half(regs["d0"], moved_y)
    stage(_word_write(actor + ACTOR_Y, moved_y))

    if current[actor + FLAGS2] & (1 << LANDED_BIT) or s16(moved_y & CELL_MASK) <= s16(speed):
        regs.update(_model_cell_from_actor_x(current, actor, regs))
        sub, regs = _model_settle_tile_1_or_2(current, actor, regs["a6"], regs["d7"], regs["d2"],
                                              regs)
        stage(sub)
    else:
        sub, regs["d0"] = _model_accelerate_fall(current, actor)
        stage(sub)

    regs.update(_model_cell_from_actor_x(current, actor, regs))
    sub, regs = _model_settle(current, actor, regs["a6"], regs["d7"], regs["d2"], regs)
    stage(sub)
    return writes, regs


# The geometry every $1334 case is written against. The record's x is a whole number of cells in and
# its half-width one cell, so the head's column and the settles' differ by exactly one.
FALL_X = 0x200
FALL_HALF_WIDTH = CELL_PIXELS
FALL_Y = PROBE_ROW * CELL_PIXELS + 1


def _run_fall(case, tiles, head_tile=CLEAR_TILE, actor_x=FALL_X, half_width=FALL_HALF_WIDTH,
              actor_y=FALL_Y, speed=0, actor_type=ACTOR_TYPE_PLAYER, flags=0, flags2=0,
              mode=0, step_flag=0, flag_word=0, platform_y=PLATFORM, entry=None):
    """One $1334 case.

    ``tiles`` is {column offset: code} from the cell BOTH settle scans start at, which
    `_settle_cell` computes from the y the pass will have moved — not from the seeded one.
    ``head_tile`` is the single cell the player-only head reads, at `_tile_33_cell`.
    """
    salt = case_salt(case)
    pokes = map_pokes(salt)
    pokes[ACTOR - RECORD_BYTES] = keyed_block(ACTOR - RECORD_BYTES, 3 * RECORD_BYTES, salt)
    pokes[ACTOR + ACTOR_X] = word(actor_x)
    pokes[ACTOR + ACTOR_Y] = word(actor_y)
    pokes[ACTOR + HALF_WIDTH] = word(half_width)
    pokes[ACTOR + ACTOR_TYPE] = word(actor_type)
    pokes[ACTOR + ACTOR_FLAGS] = bytes([flags])
    pokes[ACTOR + FLAGS2] = bytes([flags2])
    pokes[ACTOR + SPEED] = bytes([speed])
    pokes[PLATFORM_Y] = word(platform_y)
    pokes[TILE_33_FLAG] = word(flag_word)
    pokes[TILE_33_MODE] = word(mode)
    pokes[TILE_33_STEP] = word(step_flag)

    span = 2 * half_width
    settle_at = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE,
                         *_settle_cell(actor_x, half_width, actor_y + speed))
    for column in range(_scan_cells(span)):
        pokes[settle_at + column] = bytes([CLEAR_TILE])
    for column, code in tiles.items():
        pokes[settle_at + column] = bytes([code])

    head_at = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE, *_tile_33_cell(actor_x, actor_y))
    assert head_at - settle_at not in tiles, (
        f"the head's cell {head_at:#x} is one this case also seeds through `tiles` — the two would "
        f"fight, and which of them the routine read would not be what the case says")
    pokes[head_at] = bytes([head_tile])

    image = harness.make_image(pokes)
    seeded = dict(entry or {}, a0=ACTOR)
    expected, regs = _model_fall_and_settle(image, ACTOR, seeded)

    what = f"actor_fall_and_settle {case}"
    info = leaf.run("actor_fall_and_settle", _FALL(ACTOR, seeded.get("d7", 0)),
                    merge_bands(expected), what,
                    poison=False, regs=dict(seeded, _pokes=pokes),
                    max_insns=(FALL_INSN_FIXED
                               + (SETTLE_INSN_PER_CELL + TILE_SETTLE_INSN_PER_CELL)
                               * (_scan_cells(span) + 1)))
    _assert_writes(info, expected, what)
    _assert_regs(info, regs, what)
    _assert_the_span_comes_back(info, regs, what)
    return expected, regs


def test_the_head_reads_the_cell_under_the_records_own_x():
    """`move.w (a0),d0 / bsr.w $13c8` at $1342 — the one site in the image that enters the lookup
    with the record's own x rather than its left edge, which is why the head's cell is a different
    column from the two settles'. The case seeds WB_MAP_TILE_33 at the head's cell alone."""
    head_column, head_row = _tile_33_cell(FALL_X, FALL_Y)
    settle_column, settle_row = _settle_cell(FALL_X, FALL_HALF_WIDTH, FALL_Y)
    assert (head_column, head_row) != (settle_column, settle_row), (
        "this case's geometry cannot tell the head's cell from the settles'")

    writes, _regs = _run_fall("fall-head-cell", {}, head_tile=TILE_33)
    assert leaf.read_int({"writes": writes}, TILE_33_FLAG, WORD_LEN) == TILE_33_RAISED, (
        "the head did not raise the flag, so it read some cell other than the record's own x")


def test_the_head_runs_for_the_player_record_only():
    """`cmpi.w #$1,4(a0) / bne` at $1334: a record of any other type skips the whole head, so the
    three WB_TILE_33_* words are not touched however its cell reads."""
    writes, _regs = _run_fall("fall-not-the-player", {}, head_tile=TILE_33,
                              actor_type=ACTOR_TYPE_PLAYER + 1)
    for at in (TILE_33_FLAG, TILE_33_MODE, TILE_33_STEP):
        assert at not in writes, f"{at:#x} was written for a record that is not the player"


def test_a_cell_that_is_not_the_tile_clears_all_three_words():
    """The arm at $1364: three `clr.w`s in the order WB_TILE_33_MODE, _STEP, _FLAG. Each is seeded
    NONZERO here, so a `clr.w` that went missing shows up as a write set one word short."""
    writes, _regs = _run_fall("fall-not-the-tile", {}, head_tile=TILE_33 + 1,
                              mode=0x1234, step_flag=0x5678, flag_word=TILE_33_RAISED)
    for at in (TILE_33_FLAG, TILE_33_MODE, TILE_33_STEP):
        assert leaf.read_int({"writes": writes}, at, WORD_LEN) == 0, f"{at:#x} was not cleared"


def test_the_mode_word_returns_the_pass_before_it_touches_the_record():
    """`tst.w $1516.l / beq` at $1358: on the tile AND with the mode word set, the routine returns
    at $1362 — the flag is raised and nothing else in the record moves at all, which no other exit
    does."""
    writes, _regs = _run_fall("fall-mode-set", {}, head_tile=TILE_33, mode=1, speed=3)
    assert set(writes) == {TILE_33_FLAG, TILE_33_FLAG + 1}, (
        f"the early exit wrote {sorted(hex(a) for a in writes)}, not the flag word alone")


def test_the_mode_word_is_only_consulted_on_the_tile():
    """The same mode word, off the tile: the $1364 arm clears it and the pass runs on. The pair with
    the case above is what says the `tst.w` is inside the tile's own arm."""
    writes, _regs = _run_fall("fall-mode-set-off-the-tile", {}, head_tile=CLEAR_TILE, mode=1,
                              speed=3)
    assert ACTOR + ACTOR_Y in writes, "the pass returned early off the tile as well"


def test_a_record_under_its_own_motion_is_left_alone():
    """`btst #0,8(a0) / beq` over the `rts` at $1380 — WB_ACTOR_FLAG_MOVING_BIT's one reader in this
    tier. The head has already run by then, so the three words ARE written and the record is not."""
    writes, _regs = _run_fall("fall-moving-bit", {}, head_tile=CLEAR_TILE,
                              flags=1 << MOVING_BIT, speed=3)
    assert TILE_33_FLAG in writes, "the head did not run before the moving-bit test"
    assert ACTOR + ACTOR_Y not in writes, "a record under its own motion had its y moved"


@pytest.mark.parametrize("speed", [0, 1, 8, 0xff], ids=lambda v: f"speed{v:#04x}")
def test_the_step_adds_the_speed_byte_to_the_y_word(speed):
    """`moveq #$0,d1 / move.b 11(a0),d1 / add.w d1,d0 / move.w d0,2(a0)`: the speed is a BYTE
    zero-extended into a cleared long, and the add is a WORD add of it — so even a speed of zero
    writes the y word back."""
    writes, _regs = _run_fall(f"fall-step-{speed:#x}", {}, speed=speed)
    moved = leaf.read_int({"writes": writes}, ACTOR + ACTOR_Y, WORD_LEN)
    assert moved == (FALL_Y + speed) & WORD_MASK, (
        "the y did not move by the speed byte alone — the record's neighbouring bytes are seeded "
        "address-keyed, so a word read would land somewhere else entirely")


# The `ble` at $13a2 compares the moved y's position within its cell against the step that produced
# it. These three y values put that position one short of the step, exactly on it, and one past.
FALL_STEP = 4


@pytest.mark.parametrize("case,sub_cell,scans_for_ground", [
    ("one-short-of-the-step", FALL_STEP - 1, True),
    ("exactly-the-step", FALL_STEP, True),
    ("one-past-the-step", FALL_STEP + 1, False),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_ground_scan_runs_only_when_the_step_crossed_a_cell(case, sub_cell, scans_for_ground):
    """`andi.w #$f,d0 / cmp.w d1,d0 / ble` — `ble`, not `blt`, so a moved y sitting EXACTLY the
    step's own distance into its cell still runs the ground scan. The triple pins the comparison's
    direction and its strictness at once.

    Each case seeds a block under the footprint: when the ground scan runs the record lands on it
    (supported, speed cleared), and when it does not the fall simply accelerates."""
    actor_y = PROBE_ROW * CELL_PIXELS + sub_cell - FALL_STEP
    writes, _regs = _run_fall(f"fall-crossed-{case}", {0: TILE_BLOCK}, actor_y=actor_y,
                              speed=FALL_STEP)
    landed = bool(writes[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT))
    assert landed == scans_for_ground, (
        f"{case}: landed={landed}, which is not what this case is about")
    # Both arms write the speed byte, so which VALUE they leave is what tells them apart: the
    # landing zeroes it and actor_accelerate_fall bumps it by one.
    assert writes[ACTOR + SPEED] == (0 if scans_for_ground else FALL_STEP + 1)


def test_the_landed_bit_runs_the_ground_scan_whatever_the_step_did():
    """`btst #1,9(a0) / bne $13ae` at $1392 jumps PAST the cell-crossing test, so a record already
    carrying WB_ACTOR_FLAGS2_LANDED_BIT scans for ground on a step that would otherwise only have
    accelerated. Its geometry is the third case above, the one that does not cross."""
    actor_y = PROBE_ROW * CELL_PIXELS + FALL_STEP + 1 - FALL_STEP
    writes, _regs = _run_fall("fall-landed-bit", {0: TILE_BLOCK}, actor_y=actor_y, speed=FALL_STEP,
                              flags2=1 << LANDED_BIT)
    assert writes[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        "the ground scan did not run, so the landed bit did not bypass the crossing test")


def test_the_accelerate_arm_still_runs_the_platform_scan():
    """`bsr.w $14d6 / bra.w $13b6`: the arm that does NOT scan for ground still falls into the
    second lookup and the platform settle. The case puts a platform under the footprint and inside
    the band, so the record lands on it having accelerated on the way."""
    actor_y = PLATFORM - PLATFORM_Y_ABOVE - FALL_STEP
    assert (actor_y + FALL_STEP) & CELL_MASK > FALL_STEP, (
        "this case's y crosses a cell, so it would take the ground arm instead")
    writes, _regs = _run_fall("fall-accelerate-then-platform", {0: TILE_PLATFORM}, actor_y=actor_y,
                              speed=FALL_STEP, flags=1 << SUPPORTED_BIT)
    assert writes[ACTOR + FLAGS2] & (1 << LANDED_BIT), (
        "the platform settle did not land the record, so this case never reached it")


def test_the_second_lookup_starts_the_platform_scan_over():
    """WHY $13be IS CALLED TWICE. $1492's scan CONSUMES a6 and d7 — it walks the cursor along and
    counts the span down — so a port that handed $1400 what $1492 left would start it two cells
    along with a span of nothing. This case puts the ground two cells into the footprint and the
    platform back at its FIRST cell: the ground scan walks to cell 2, and the platform settle finds
    $23 at cell 0 only because the second lookup put the cursor back."""
    writes, regs = _run_fall("fall-second-lookup", {0: TILE_PLATFORM, 2: TILE_BLOCK},
                             half_width=CELL_PIXELS, actor_y=PLATFORM - PLATFORM_Y_ABOVE,
                             speed=0)
    settle_at = _cell_of(MAP_DEFAULT, DEFAULT_STRIDE,
                         *_settle_cell(FALL_X, CELL_PIXELS, PLATFORM - PLATFORM_Y_ABOVE))
    assert regs["a6"] == settle_at, (
        f"the platform settle stopped at {regs['a6']:#x}, not the footprint's first cell "
        f"{settle_at:#x} — its scan did not start over")
    assert writes[ACTOR + FLAGS2] & (1 << LANDED_BIT), "the platform settle did not land the record"


def test_the_settle_cells_come_from_the_MOVED_y_and_survive_the_ground_arms_mask():
    """TWO claims about the row both `bsr $13be` sites read, and the case is keyed to neither the
    seeded y nor the actor's own edge.

    The row is `2(a0) asr.w #4` taken AFTER $138e has stored the step, so this case's seeded y and
    its moved y are in DIFFERENT rows and the block is in the moved one — a case keyed off the
    seeded y plants it a whole row above where the scan looks. And $1492's landing arm masks that y
    again between the two lookups, which cannot move the row because it only clears the low nibble:
    stated here as the arithmetic it is, with the mask itself pinned by the write it leaves.
    """
    speed = 6
    actor_y = PROBE_ROW * CELL_PIXELS - 1
    moved = (actor_y + speed) & WORD_MASK
    assert _pixel_to_cell(actor_y) != _pixel_to_cell(moved), (
        "this case's seeded y and moved y are in the same row, so it states nothing about which")
    assert moved & CELL_MASK != 0, "this case's moved y is already on a cell boundary"
    assert moved & CELL_MASK <= speed, "this case takes the accelerate arm, not the ground one"
    assert (_settle_cell(FALL_X, FALL_HALF_WIDTH, moved)
            == _settle_cell(FALL_X, FALL_HALF_WIDTH, moved & ~CELL_MASK)), (
        "masking the low nibble moved the row, so the two lookups would not agree on the cell")

    writes, _regs = _run_fall("fall-row-after-the-mask", {0: TILE_BLOCK}, actor_y=actor_y,
                              speed=speed)
    assert leaf.read_int({"writes": writes}, ACTOR + ACTOR_Y, WORD_LEN) == moved & ~CELL_MASK, (
        "the ground arm did not land the record on the moved row's own cell boundary")


def test_the_pass_leaves_the_callers_untouched_registers_alone():
    """d4, d5 and d6 are written by nothing in the whole chain — $13c8, $1492, $1400 and $14d6
    between them touch d0, d1, d2, d3, d7 and a6 and no other. Seeded with rubbish, they must come
    back unchanged, which `_assert_regs` requires of every case; this one exists to say the claim is
    deliberate."""
    entry = {"d4": 0x11112222, "d5": 0x33334444, "d6": 0x55556666, "a5": 0x77778888}
    _writes, regs = _run_fall("fall-untouched-registers", {0: TILE_BLOCK}, entry=entry)
    for reg, value in entry.items():
        assert regs[reg] == value


FALL_PASS_CALLERS = 46
FALL_PASS_OWN_RETURNS = 2


def test_the_fall_pass_has_forty_six_callers_and_no_other_entrance():
    """A whole-image scan in all three encodings. $1334 is called by `bsr` alone — no `jsr`, no
    `jmp`, and no `bra` into it either, which matters because the routine's own exits are branches
    out of it."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    entry = leaf.entry_of("actor_fall_and_settle")

    calls = _relative_sites(program, (entry,))[entry]
    assert len(calls) == FALL_PASS_CALLERS, (
        f"$1334 has {len(calls)} `bsr` callers, not {FALL_PASS_CALLERS}")
    assert _absolute_sites(program, (entry,))[entry] == [], "a `jsr`/`jmp` names $1334 as well"
    assert _relative_sites(program, (entry,), high_byte=BRA_HIGH_BYTE)[entry] == [], (
        "a `bra` enters $1334, so its callers are not all `bsr` sites")


def test_the_pass_ends_in_a_branch_into_the_platform_settle():
    """$1334 carries no `rts` after $1380: its last instruction is `bra.w $1400`, so
    actor_settle_on_platform's own `rts` returns to $1334's caller — which is why src/map.c writes
    the tail as a call followed by nothing."""
    body = ENTRY_BYTES["actor_fall_and_settle"]
    entry = leaf.entry_of("actor_fall_and_settle")
    tail = branch_w_to(BRA_W, entry + len(body) - BRANCH_W_LEN,
                       leaf.entry_of("actor_settle_on_platform"))
    assert body[-BRANCH_W_LEN:] == tail, (
        f"$1334 ends in {body[-BRANCH_W_LEN:].hex()}, not a `bra.w` into $1400")
    assert body.count(RTS) == FALL_PASS_OWN_RETURNS, (
        f"$1334 carries {body.count(RTS)} `rts`, not the {FALL_PASS_OWN_RETURNS} early exits it "
        f"has of its own")


# --- the three globals, and the tile code that raises them ----------------------------------------
# Every claim ../names.txt makes about them is this scan. A word-sized global can be named by a
# four-byte abs.l operand or a two-byte abs.w one (the 68000 sign-extends the short form, and all
# three lie below $8000, so both reach the same address) — so the scan runs BOTH encodings, and the
# short-form hits that are merely the tail half of a long-form operand are dropped.
TILE_33_SITES = {
    # {global: (long-form operand offsets, short-form ones)}. Each is the operand's own address, so
    # the instruction is the two bytes below a long one and the two below a short one.
    "flag": ([0xd86, 0x120a, 0x1354, 0x1372], [0x155e, 0x17a0, 0xff02]),
    "mode": ([0xd7a, 0xdb6, 0xdee, 0xfaa, 0x1016, 0x107e, 0x135a, 0x1366], [0x2090]),
    "step": ([0xda8, 0xde0, 0xe00, 0xe08, 0x136c], [0x20b0]),
}
# ...and the byte pairs elsewhere in the image that spell one of the three BY ACCIDENT. They are
# named here rather than filtered out by an address floor, because "it is past the code" would be a
# claim about where the code ends that nothing else in this project makes.
TILE_33_DATA_SPELLINGS = {"flag": [], "mode": [0x18a26],
                          "step": [0x1854e, 0x18556, 0x19a38, 0x19a9c]}

# How the 68000 spells an <abs>.w operand: effective-address mode 111, register 000. In a
# single-operand instruction that is the opcode word's low six bits; in a MOVE it is the
# DESTINATION field, bits 6..11, whose mode and register are stored the other way round.
ABS_W_EA = 0x38
MOVE_ABS_W_DEST = 0x07
MOVE_OPCODES = (1, 2, 3)                # move.b, move.l, move.w — the opcode word's top nibble


def _names_abs_w(program, at):
    """Whether the word below ``at`` is an instruction whose <abs>.w operand ``at`` is.

    This is what separates a real short-form reference from two bytes of graphics data that happen
    to spell the same number: every genuine site's opcode word carries the abs.w effective address
    and none of the accidental ones does.
    """
    instruction = int.from_bytes(program[at - WORD_LEN:at], "big")
    if instruction & 0x3f == ABS_W_EA:
        return True
    return instruction >> 12 in MOVE_OPCODES and (instruction >> 6) & 0x3f == MOVE_ABS_W_DEST


def _short_operand_sites(program, addr, long_sites):
    """Every even offset holding ``addr``'s two bytes that is not a long operand's tail half."""
    encoded = word(addr)
    return [at for at in range(WORD_LEN, len(program) - WORD_LEN, WORD_LEN)
            if program[at:at + WORD_LEN] == encoded and at - WORD_LEN not in long_sites]


@pytest.mark.parametrize("name,addr", [("flag", TILE_33_FLAG), ("mode", TILE_33_MODE),
                                       ("step", TILE_33_STEP)],
                         ids=["flag-1514", "mode-1516", "step-1518"])
def test_every_site_that_names_one_of_the_three_words(name, addr):
    """The ledger include/wonderboy.h records, as a scan rather than as a reading of the listing.

    The three sit immediately above $1492's last byte and below the routine at $151a, so they are
    three words of data inside the code — which is why an operand scan is the only way to find their
    readers at all. Both encodings are scanned: all three lie below $8000, so the 68000's short
    absolute form reaches them and a long-form-only scan would report a fraction of the sites.
    """
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    long_sites, short_sites = TILE_33_SITES[name]

    assert _operand_sites(program, addr) == long_sites, (
        f"{addr:#x}'s long-form operands are "
        f"{[hex(a) for a in _operand_sites(program, addr)]}, not {[hex(a) for a in long_sites]}")
    shorts = _short_operand_sites(program, addr, set(long_sites))
    operands = [at for at in shorts if _names_abs_w(program, at)]
    accidents = [at for at in shorts if not _names_abs_w(program, at)]
    assert operands == short_sites, (
        f"{addr:#x}'s short-form operands are {[hex(a) for a in operands]}, not "
        f"{[hex(a) for a in short_sites]}")
    assert accidents == TILE_33_DATA_SPELLINGS[name], (
        f"{[hex(a) for a in accidents]} spell {addr:#x} without being an operand, not "
        f"{[hex(a) for a in TILE_33_DATA_SPELLINGS[name]]}")


def test_the_fall_pass_holds_the_only_writers_of_the_three_words_this_battery_reaches():
    """Of the sites above, the ones inside $1334's own body are the four this file exercises: the
    `move.w #$ffff` at $1350 and the three `clr.w`s at $1364/$136a/$1370. Every other writer is in
    code no case here runs, which is what makes the ledger a scan and not an assumption."""
    entry = leaf.entry_of("actor_fall_and_settle")
    body = len(ENTRY_BYTES["actor_fall_and_settle"])
    inside = sorted(at for sites in TILE_33_SITES.values() for at in sites[0]
                    if entry <= at < entry + body)
    assert inside == [0x1354, 0x135a, 0x1366, 0x136c, 0x1372], (
        f"{[hex(a) for a in inside]} name one of the three words inside $1334")


def test_the_tile_code_is_compared_against_a_map_byte_in_exactly_two_places():
    """`cmpi.b #$33,(a6)` at $1348 and `cmpi.b #$33,d0` at $1554, the latter inside $151a on a byte
    it has just loaded from the same collision map. Nothing else in the image compares a cell
    against this code, which is the whole of what is known about what it means."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    encodings = (cmpi_b_ind(A6, TILE_33), cmpi_b_dn(D0, TILE_33))
    sites = sorted(at for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN)
                   for encoded in encodings if program[at:at + len(encoded)] == encoded)
    assert sites == list(TILE_33_COMPARE_SITES), (
        f"{[hex(a) for a in sites]} compare a map byte against {TILE_33:#x}")
    load_cell = move_w_ind_dn(D0, A0, ACTOR_X)          # `move.w (a0),d0` — the head's own pixel x
    at = TILE_33_COMPARE_SITES[0] - len(leaf.BSR_W) - WORD_LEN - len(load_cell)
    assert program[at:at + len(load_cell)] == load_cell


TILE_33_COMPARE_SITES = (0x1348, 0x1554)


# --- $1af0: the 2x2 stamp -------------------------------------------------------------------------
STAMP_INSN_CAP = 24
STAMP_RECORD = 0x30000          # plain RAM, well clear of both maps and the actor tables
STAMP_WINDOW_ROWS = 4


def _model_stamp(image):
    record = int.from_bytes(bytes(image[RECORD_PTR:RECORD_PTR + 4]), "big")
    cell = (u16(image, record + RECORD_CELL) + STAMP_CELL_BIAS) & WORD_MASK
    at = (MAP_ROW_STRIDE + s16(cell)) & 0xffffffff
    tile = (STAMP_TILES_SECOND
            if u16(image, record + RECORD_KIND) == KIND_BOSS_DEFEAT
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
        STAMP_RECORD + RECORD_KIND: word(variant),
    }
    image = harness.make_image(pokes)
    expected = _model_stamp(image)

    what = f"map_stamp_block {case}"
    info = leaf.run("map_stamp_block", _STAMP, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=STAMP_INSN_CAP)
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("variant,tile", [(0, STAMP_TILES_FIRST),
                                          (KIND_BOSS_DEFEAT, STAMP_TILES_SECOND)],
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
    info = _run_stamp("variant-high-half", 0, (KIND_BOSS_DEFEAT << 8)
                      | KIND_BOSS_DEFEAT)
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
        STAMP_RECORD + RECORD_KIND: word(0),
    }
    image = harness.make_image(pokes)
    expected = _model_stamp(image)
    what = "map_stamp_block row-step-negative"
    info = leaf.run("map_stamp_block", _STAMP, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=STAMP_INSN_CAP)
    _assert_writes(info, expected, what)
    assert min(expected) < MAP_ROW_STRIDE + STAMP_CELL_BIAS + DEFAULT_STRIDE * 2, (
        "the second row did not land above the first, so this case does not reach what it is about")
