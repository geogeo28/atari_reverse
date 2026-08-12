"""Differential test for src/behavior.c — the per-actor behaviour tier's foundation.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and bounds (or states exactly) the original's write set.

FOUR THINGS SHAPE THIS BATTERY.

  * THE PASS AND THE DISPATCHER WRITE NOTHING. `actor_behavior_pass` walks a table through a0 and
    `actor_dispatch_behavior` computes an address and jumps; between them they touch no image byte,
    so a byte-for-byte diff proves nothing about either. What pins them is the DISPATCH ROW: one
    case per table slot, all 62. For the 50 slots this port does not have, the C returns the address
    it would have transferred to and the oracle is stopped at that same address with a coverage
    witness that the `jmp (a1)` really fired; for the 12 it does, the run goes THROUGH the handler
    and the two cores are compared over the frame behind it. Either way the row pins the C's table
    entry by entry against ../names.txt AND against the image's own 62 longwords — and a slot that
    is ported later moves one row from the first kind to the second and nothing else.
  * THE PORTED SLOTS MAKE THE WALK RUNNABLE. Slots 0 and 58 hold the bare `rts` at $a36, so a table
    of type-0 records runs the whole pass to its own `rts` in both cores — which is the only way the
    free-marker skip, the end marker and the WB_STATE_FLAG_A34 arm can be driven. Every case that
    still wants a BOUNDARY names UNPORTED_TYPE or UNPORTED_SLOT rather than a bare number, and a
    case asserts both are still unported: batch 30 ported five slots such cases used to name, and a
    stale number would have turned a boundary case into a run-the-handler case without failing.
  * NOTHING IS SEEDED FROM A CONSTANT THE CODE ALSO USES. All three actor tables are zero in a fresh
    image, so every case fills them ADDRESS-KEYED with a record's margin either side: a walk that ran
    one record long or took the wrong stride lands on bytes that are wrong FOR WHERE THEY WERE
    WRITTEN rather than on zeros. The type word of every record a case walks is then poked
    explicitly, because a keyed byte would dispatch a slot the case did not choose.
  * SIX LEAVES CALL THE MAP PROBES, whose own write set test_map.py owns. Those cases BOUND the
    write set to the record and the probe's own band rather than stating it.

THE CURSOR STORE SLOTS 2, 3 AND 4 SKIP is not pinnable, and the sweep says so rather than this
paragraph merely claiming it. `bne.w $6bb8` jumps over the `move.b d0,18(a0)` below it — but the
value that store would have written is the wrap's own ZERO, and actor_defeat_and_score writes
WB_ACTOR_FIELD_18 = 0 itself before anything else. Both readings leave the same byte, so a mutant
that stores anyway SURVIVES (`gate/always-store-cursor`). It is reproduced because it is what the
bytes do, and recorded here because no case can hold it.

THE OTHER MUTANTS NOTHING HERE CAN CATCH, named so a later sweep does not chase them. All three are
REORDERINGS of two writes that neither reads, and the oracle's write ledger is address-keyed, so no
differential can separate any of them:
  * slot 6's `clr.b 31(a0)` against its `subq.b #1,30(a0)` — two independent bytes;
  * slot 56's actor_platform_release_blocked_rider against actor_platform_release_check — the first
    writes the rider's y, WB_ACTOR_PLATFORM_RIDDEN and the riding bit, the second reads the rider's
    x and three flag bits and writes the same two values, so neither reads what the other writes and
    their shared writes are the same constant;
  * `order/type52-free-writes` (batch 31) — the switch bit against the free marker in
    `switched_free_slot`, again two independent addresses.

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
                        TABLE_A32, _sfx_bytes, bit_op_d16, cmpi_w_ind, move_w_imm_ind)

BLE_W = 0x6f00
BGE_W = 0x6c00
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

# A SECOND unported slot, for the cases that need a boundary somewhere other than slot 1. Every case
# that wants "a handler this port does not have" names one of these two rather than a bare number —
# batch 30 ported five slots that such cases used to name, and a stale number would have turned a
# boundary case into a run-the-handler case without failing.
UNPORTED_SLOT = 7

# ...and two MORE, for the cases that want three different unported slots at once (one per alias
# band, one per walk boundary). Named for the same reason the two above are.
#
# WHY A BOUNDARY ROW MUST NOT USE UNPORTED_TYPE. `_walk_pokes` gives every FREE record that same
# type, so a walk case whose boundary slot is slot 1 cannot tell "stopped at the record I seeded"
# from "dispatched a free record instead of skipping it" — both report slot 1's address and write
# nothing. The walk rows therefore name these three and never UNPORTED_TYPE.
UNPORTED_MID = 38
UNPORTED_HIGH = 57


# --- the encodings only this battery spells -------------------------------------------------------
# NINE of these are now a THIRD copy and are due to move to leaf.py under its own rule ("an encoding
# moves there on its third"): `move_w_dn_d16` (test_actor.py, test_map.py), `movea_l_ind`
# (test_blit.py, test_scene.py), `addq_w_dn` (test_blit.py, test_map.py), `add_w_d16_dn`
# (test_blit.py, test_map.py), `neg_w_dn` (test_map.py, test_scroll.py), and batch 31's four —
# `clr_l_dn`, `jsr_ind`, `jsr_abs_w` and `cmp_b_imm_dn`. Hoisting them edits six other batteries, so
# ../STATUS.md registers the move rather than this batch making it; each is annotated ALSO IN below
# so the copies can be found from any of them. The rest are first or second copies, which the rule
# allows.
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


def clr_l_dn(reg):
    """`clr.l Dn` — the WHOLE register, which is what makes slot 61's d1 an argument and not a
    leftover: two bytes where `moveq #0` would have done, and the only long clear in this file."""
    return opcode(0x4280 | reg)
    # ALSO IN test_blit.py, test_hud.py (`_clr_l_dn`) — third copy, queued for leaf.py.


def move_b_ind_dn(reg, base):
    return opcode(0x1010 | (reg << 9) | base)


def cmp_b_imm_dn(reg, value):
    """`cmp.b #imm,Dn` — the CMP-with-immediate-source form ($b03c), not `cmpi.b` ($0c00). Both
    assemble a byte compare against a register and they are different instructions."""
    return opcode(0xb03c | (reg << 9)) + word(value & 0xff)
    # ALSO IN test_text.py, test_sound.py (`CMP_B_IMM_DN`) — third copy, queued for leaf.py.


def movea_l_imm(reg, value):
    return opcode(0x207c | (reg << 9)) + longword(value)
    # ALSO IN test_actor.py — second copy, which the rule allows.


def jsr_ind(reg):
    return opcode(0x4e90 | reg)
    # ALSO IN test_blit.py, test_scene.py — third copy, queued for leaf.py.


def jsr_abs_w(addr):
    """`jsr <abs>.w` — the SHORT absolute form, which is how slot 61 calls joy1_newly_pressed and
    how the copylock failure path calls slot 61 itself. A scan for the longword form misses both."""
    return opcode(0x4eb8) + word(addr)
    # ALSO IN test_actor.py, test_scene.py — third copy, queued for leaf.py.


def jmp_abs_l(addr):
    return opcode(0x4ef9) + longword(addr)


def neg_w_dn(reg):
    return opcode(0x4440 | reg)
    # ALSO IN test_map.py, test_scroll.py — third copy, queued for leaf.py.


def adda_w_dn(reg, base):
    return opcode(0xd0c0 | (base << 9) | reg)


def addq_w_ind(amount, base):
    return opcode(0x5050 | ((amount & 7) << 9) | base)
    # ALSO IN test_scene.py — second copy, which the rule allows.


def subq_w_ind(amount, base):
    return opcode(0x5150 | ((amount & 7) << 9) | base)


def addq_w_d16(amount, base, displacement):
    return opcode(0x5068 | ((amount & 7) << 9) | base) + word(displacement)


def subq_w_d16(amount, base, displacement):
    return opcode(0x5168 | ((amount & 7) << 9) | base) + word(displacement)


def tst_w_d16(base, displacement):
    return opcode(0x4a68 | base) + word(displacement)


def st_d16(base, displacement):
    """`st d16(An)` — the 68000's own "set true", i.e. the byte $ff."""
    return opcode(0x50e8 | base) + word(displacement)


def cmp_w_d16_dn(reg, base, displacement):
    return opcode(0xb068 | (reg << 9) | base) + word(displacement)


def move_w_indexed_d16(source, index, destination, displacement):
    """`move.w 0(As,Dn.w),d16(Ad)` — slot 6's death frame, which indexes and publishes in one."""
    return (opcode(0x3170 | (destination << 9) | source)
            + brief_extension_word(index) + word(displacement))


def move_l_ind_ind(source, destination):
    return opcode(0x2090 | (destination << 9) | source)


def move_l_imm_d16(base, value, displacement):
    return opcode(0x217c | (base << 9)) + longword(value) + word(displacement)


def move_l_imm_dn(reg, value):
    """`move.l #imm,Dn` — six bytes for a zero a `moveq` does in two, at $2840."""
    return opcode(0x203c | (reg << 9)) + longword(value)


def adda_l_imm(reg, value):
    return opcode(0xd1fc | (reg << 9)) + longword(value)


def cmpa_l_imm(reg, value):
    return opcode(0xb1fc | (reg << 9)) + longword(value)


def adda_l_dn(reg, base):
    return opcode(0xd1c0 | (base << 9) | reg)
    # ALSO IN test_actor.py, test_stage.py — THIRD copy, queued for leaf.py.


def mulu_w_dn(destination, source):
    return opcode(0xc0c0 | (destination << 9) | source)
    # ALSO IN test_map.py, test_stage.py — THIRD copy, queued for leaf.py.


def lsr_w_imm_dn(count, reg):
    return opcode(0xe048 | ((count & 7) << 9) | reg)


def cmpi_b_ind(base, value):
    return opcode(0x0c10 | base) + word(value & 0xff)


def cmpi_b_postinc(base, value):
    return opcode(0x0c18 | base) + word(value & 0xff)


def move_b_imm_dn(reg, value):
    """`move.b #imm,Dn` — the LOW BYTE alone, which is what slots 3 and 6 write their step into."""
    return opcode(0x103c | (reg << 9)) + word(value & 0xff)


def jsr_d16_an(reg, displacement):
    return opcode(0x4ea8 | reg) + word(displacement)
    # ALSO IN test_actor.py — second copy, which the rule allows.


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
    """`bra.s` aimed at a label: the pass closes its loop short where every other branch is long.
    One spelling of the displacement rule, in `_bcc_s`."""
    return _bcc_s(BRA_W, target)


def _bcc_s(condition, target):
    """`bcc.s` aimed at a label — `_bra_s` generalised when slot 61 turned out to close BOTH of its
    arms short, one on a `bpl` and one on a `bne`."""
    def build(at, labels):
        displacement = labels[target] - (at + leaf.BRANCH_EXTENSION)
        assert -0x80 <= displacement < 0x80 and displacement != 0, (
            f"{displacement} does not fit a `bcc.s` byte")
        return opcode(condition | (displacement & 0xff))

    return _Ref(2, build)


def _bsr(routine):
    return _Ref(4, lambda at, _labels: bsr_w(at, leaf.entry_of(routine)))


def _lea_pc_indexed(reg, index, target):
    """`lea d8(PC,Dn.w),An` aimed at an ADDRESS. The displacement counts from the EXTENSION WORD, so
    it comes out of the layout pass rather than being transcribed — a frame table named this way
    cannot drift when an instruction above it changes size."""
    return _Ref(4, lambda at, _labels: opcode(0x41fb | (reg << 9))
                + brief_extension_word(index, target - (at + WORD_BYTES)))


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


# --- the ten table slots, and the two routines they needed ------------------------------------------
# The five in the $2462..$2db1 band are ONE SHAPE with five bodies inside it, and these three pieces
# are the parts that really are the same instructions at every site. Everything else is spelt per
# slot, because "similar" is not "identical" and a shared spelling would hide the difference.
SPAWN_ANIM = "actor_spawn_anim_step"
HIT_BY_SHOT = "actor_hit_by_player_shot"
OVERLAP = "actor_followed_overlap_mask"
DAMAGE_FOLLOWED = "actor_damage_followed"
DAMAGE_TEMPLATE = "actor_damage_template_hitpoints"
DEFEAT = "actor_defeat_and_score"
FALL_AND_SETTLE = "actor_fall_and_settle"
HOP_ASCEND = "actor_hop_ascend_step"
HOP_OR_FLIP = "actor_hop_or_flip_side"
TOGGLE_SIDE = "actor_toggle_side_flag"
START_MOTION = "actor_start_motion_at_speed"
ALLOC_HIGH = "actor_alloc_slot_high"
SPRITE_FROM_6ED8 = "actor_sprite_from_6ed8"
PLATFORM_CARRY = "actor_platform_carry_followed"
PLATFORM_RELEASE = "actor_platform_release_check"
PLATFORM_BLOCKED = "actor_platform_release_blocked_rider"
STUN = "actor_stun_followed"

# The stub table and its trigger slot come from the battery that OWNS the sound module, not from a
# second copy here — test_actor.py's two damage paths import the same pair for the same reason.
from test_sound import STUB_TABLE_BASE as SND_STUB_TABLE, STUB_TRIGGER_OFFSET  # noqa: E402

SND_CHANNEL_A = wb("SND_CHANNEL_A")
STUN_SFX = wb("ACTOR_STUN_SFX")
STUN_STEPS_BASE = wb("ACTOR_STUN_STEPS_BASE")
EFFECT_STATE_BD68 = wb("EFFECT_STATE_BD68")
FIELD_29 = wb("ACTOR_FIELD_29")
FIELD_24 = wb("ACTOR_FIELD_24")
FIELD_31 = wb("ACTOR_FIELD_31")
TEMPLATE_SLOT = wb("ACTOR_TEMPLATE_SLOT")
ST_BYTE = wb("ACTOR_ST_BYTE")
# `move.b #$84,19(a0)`, the inline damage word slots 51, 52 and 53 all write
CONTACT_DAMAGE = wb("ACTOR_CONTACT_DAMAGE_INLINE")
FLAGS2_BIT_0 = wb("ACTOR_FLAGS2_BIT_0")
DEFEATED_BIT = wb("ACTOR_FLAGS2_DEFEATED_BIT")
DIRECTION_BIT = wb("ACTOR_FIELD_22_DIRECTION_BIT")
PLATFORM_STEP = wb("ACTOR_PLATFORM_STEP")
SINK_TICK = wb("ACTOR_PLATFORM_SINK_TICK")
ANIM32_MASK = wb("ACTOR_ANIM32_MASK")
COLLISION_MAP_DEFAULT = wb("COLLISION_MAP_DEFAULT")
COLLISION_MAP_CELLS = wb("COLLISION_MAP_CELLS")
MAP_CELL_SHIFT = wb("MAP_CELL_SHIFT")
TILE_BLOCK = wb("MAP_TILE_BLOCK")
TILE_LEDGE = wb("MAP_TILE_LEDGE")
A5, A6 = 5, 6


def _monster_prologue(dying_label):
    """The four instructions slots 2..6 open with: the spawn gate (a BRANCH into $698a, not a call)
    and the switch onto the death animation."""
    return [
        bit_op_d16(BTST_IMM, SPAWNED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(SPAWN_ANIM)),
        bit_op_d16(BTST_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _bcc(BNE_W, dying_label),
    ]


def _monster_contact(body_arm, walk_label):
    """`bsr $23b6 / tst.w d7 / bne` then `bsr $5c6e` and the two `btst`s over its mask. `body_arm`
    is what the slot does between bit 1 and the tail jump into $69fe — nothing for slots 2 and 4,
    a `bchg` of the side flag for 3, 5 and 6."""
    return [
        _bsr(HIT_BY_SHOT),
        tst_w_dn(D7),
        _bcc(BNE_W, "struck"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "point"),
        *body_arm,
        _bcc_abs(BRA_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        _lab("point"),
        btst_imm_dn(POINT_BIT, D0),
        _bcc(BEQ_W, walk_label),
    ]


def _monster_struck(extra=()):
    """`bset #0,9(a0) / clr.b 18(a0)` and the tail jump into $6b46, with slot 6's extra call in it."""
    return [
        _lab("struck"),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        clr_b_d16(A0, FIELD_18),
        *extra,
        _bcc_abs(BRA_W, leaf.entry_of(DAMAGE_TEMPLATE)),
    ]


def _cursor_into(reg):
    """`moveq #0,d0 / move.b 18(a0),d0 / lea 0(An,d0.w),An` — a byte cursor turned into a pointer."""
    return [moveq_0_dn(D0), move_b_d16_dn(D0, A0, FIELD_18), lea_indexed(reg, D0)]


def _type02_pieces():
    return [
        *_monster_prologue("dying"),
        *_monster_contact([], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        move_w_ind_dn(D0, A0),
        leaf.move_w_abs_l_dn(D1, FOLLOWED_DEFAULT),
        cmp_w_dn_dn(D1, D0),
        _bcc(BGT_W, "followed-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE02_WALK_LEFT")),
        bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BRA_W, "walk-anim"),
        _lab("followed-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE02_WALK_RIGHT")),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("walk-anim"),
        *_cursor_into(A1),
        # ...and these five ARE actor_advance_anim16's eighteen bytes, spelt inline.
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
        _lab("dying"),
        _bsr(FALL_AND_SETTLE),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "dead-right"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-left-frames"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE02_DEAD_STEP")),
        _bsr(STEP_LEFT),
        _lab("dead-left-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE02_DEAD_LEFT")),
        _bcc(BRA_W, "dead-anim"),
        _lab("dead-right"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-right-frames"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE02_DEAD_STEP")),
        _bsr(STEP_RIGHT),
        _lab("dead-right-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE02_DEAD_RIGHT")),
        _lab("dead-anim"),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, ANIM32_MASK),
        _bcc(BNE_W, "store"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BCLR_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab("store"),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
    ]


def _type03_pieces():
    return [
        *_monster_prologue("dying"),
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "reload"),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "facing"),
        _lab("reload"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE03_TURN_FRAMES"), FIELD_30),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("facing"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "walk-right"),
        # `move.b`, not `move.w`: the step's high byte is whatever the settle above left in d7.
        move_b_imm_dn(D7, wb("ACTOR_TYPE03_WALK_STEP")),
        _bsr(STEP_LEFT),
        _bsr(TOGGLE_SIDE),
        lea_abs_l(A1, wb("ACTOR_TYPE03_WALK_LEFT")),
        _bcc(BRA_W, "walk-anim"),
        _lab("walk-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE03_WALK_STEP")),
        _bsr(STEP_RIGHT),
        _bsr(TOGGLE_SIDE),
        lea_abs_l(A1, wb("ACTOR_TYPE03_WALK_RIGHT")),
        _lab("walk-anim"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
        _lab("dying"),
        _bsr(FALL_AND_SETTLE),
        leaf.movea_l_abs_l(A1, TABLE_SELECTED),
        adda_l_imm(A1, FOLLOWED_SLOT * RECORD_BYTES),
        move_w_ind_dn(D0, A1),
        cmp_w_ind_dn(D0, A0),
        _bcc(BGE_W, "retreat-left"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BRA_W, "retreat-right"),
        _lab("retreat-left"),
        bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "held-left"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE03_DEAD_STEP")),
        _bsr(STEP_LEFT),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, wb("ACTOR_TYPE03_DEAD_LEFT")),
        lea_indexed(A1, D0),
        _bcc(BRA_W, "dead-anim"),
        _lab("held-left"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, wb("ACTOR_TYPE03_HELD_LEFT")),
        lea_indexed(A1, D0),
        _bcc(BRA_W, "dead-anim"),
        _lab("retreat-right"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "held-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE03_DEAD_STEP")),
        _bsr(STEP_RIGHT),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, wb("ACTOR_TYPE03_DEAD_RIGHT")),
        lea_indexed(A1, D0),
        _bcc(BRA_W, "dead-anim"),
        _lab("held-right"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, wb("ACTOR_TYPE03_HELD_RIGHT")),
        lea_indexed(A1, D0),
        _lab("dead-anim"),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, ANIM16_MASK),
        _bcc(BNE_W, "store"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BCLR_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab("store"),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
    ]


def _type04_pieces():
    return [
        *_monster_prologue("dying"),
        *_monster_contact([], "chase"),
        *_monster_struck(),
        _lab("chase"),
        _bsr(SIDE_FLAG),
        move_w_imm_dn(D0, wb("ACTOR_CHASE_REACH")),
        _bsr(WITHIN),
        tst_w_dn(D0),
        _bcc(BMI_W, "hover"),
        move_w_ind_dn(D0, A0),
        cmp_w_ind_dn(D0, A1),
        _bcc(BEQ_W, "level"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "fly-right"),
        _bcc(BRA_W, "fly-left"),
        _lab("level"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "level-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE04_FLY_LEFT")),
        _bcc(BRA_W, "fly-anim"),
        _lab("level-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE04_FLY_RIGHT")),
        _bcc(BRA_W, "fly-anim"),
        _lab("fly-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE04_FLY_LEFT")),
        move_w_imm_dn(D7, wb("ACTOR_TYPE04_FLY_STEP")),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "fly-anim"),
        _lab("fly-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE04_FLY_RIGHT")),
        move_w_imm_dn(D7, wb("ACTOR_TYPE04_FLY_STEP")),
        _bsr(STEP_RIGHT),
        _lab("fly-anim"),
        move_l_imm_dn(D0, 0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM32_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _lab("hover"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_30),
        lea_abs_l(A1, wb("ACTOR_TYPE04_HOVER")),
        leaf.move_w_indexed_dn(D1, A1, D0),
        add_w_dn_d16(D1, A0, ACTOR_Y),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, wb("ACTOR_TYPE04_HOVER_MASK")),
        move_b_dn_d16(D0, A0, FIELD_30),
        RTS,
        _lab("dying"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "dead-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE04_DEAD_STEP")),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-left-frames"),
        _bsr(STEP_LEFT),
        _lab("dead-left-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE04_DEAD_LEFT")),
        _bcc(BRA_W, "dead-anim"),
        _lab("dead-right"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-right-frames"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE04_DEAD_STEP")),
        _bsr(STEP_RIGHT),
        _lab("dead-right-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE04_DEAD_RIGHT")),
        _lab("dead-anim"),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, ANIM32_MASK),
        _bcc(BNE_W, "store"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BCLR_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab("store"),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
    ]


def _type05_pieces():
    return [
        *_monster_prologue("dying"),
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "hop"),
        *_monster_struck(),
        _lab("hop"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "hop-left"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE05_HOP_STEP")),
        _bsr(STEP_RIGHT),
        lea_abs_l(A1, wb("ACTOR_TYPE05_HOP_RIGHT")),
        _bsr(HOP_OR_FLIP),
        _bcc(BRA_W, "hop-anim"),
        _lab("hop-left"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE05_HOP_STEP")),
        _bsr(STEP_LEFT),
        lea_abs_l(A1, wb("ACTOR_TYPE05_HOP_LEFT")),
        _bsr(HOP_OR_FLIP),
        _lab("hop-anim"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM32_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
        _lab("dying"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(SIDE_FLAG),
        moveq_0_dn(D0),
        lea_abs_l(A1, wb("ACTOR_TYPE05_DEAD")),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "recoil"),
        # `btst`, not `bclr`: the defeated bit is NOT lowered on the way to $6bb8 here.
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        RTS,
        _lab("recoil"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "held"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE05_DEAD_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "recoil-left"),
        _bsr(STEP_RIGHT),
        RTS,
        _lab("recoil-left"),
        _bsr(STEP_LEFT),
        _lab("held"),
        RTS,
    ]


def _type06_pieces():
    return [
        *_monster_prologue("dying"),
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "live"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("live"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "armed"),
        clr_b_d16(A0, FIELD_31),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "walk"),
        _lab("armed"),
        tst_b_d16(A0, FIELD_31),
        _bcc(BNE_W, "airborne?"),
        move_b_d16_d16(A0, ACTOR_FLAGS, A0, FIELD_29),
        st_d16(A0, FIELD_31),
        move_w_imm_dn(D0, wb("ACTOR_CHASE_REACH")),
        _bsr(WITHIN),
        tst_w_dn(D0),
        _bcc(BMI_W, "restore"),
        _bsr(SIDE_FLAG),
        move_w_imm_dn(D0, wb("ACTOR_TYPE06_CHARGE_SPEED")),
        _bsr(START_MOTION),
        _lab("airborne?"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "throw"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "stand-left"),
        move_w_imm_d16(A0, wb("ACTOR_TYPE06_SPRITE_RIGHT"), ACTOR_SPRITE),
        RTS,
        _lab("stand-left"),
        move_w_imm_d16(A0, wb("ACTOR_TYPE06_SPRITE_LEFT"), ACTOR_SPRITE),
        RTS,
        _lab("throw"),
        _bsr(ALLOC_HIGH),
        cmpa_l_imm(A1, 0),
        _bcc(BEQ_W, "restore"),
        move_l_ind_ind(A0, A1),
        subq_w_d16(wb("ACTOR_TYPE06_SHOT_UP"), A1, ACTOR_Y),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "shot-behind"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE06_SHOT_AHEAD")),
        _bcc(BRA_W, "shot-place"),
        _lab("shot-behind"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE06_SHOT_BEHIND")),
        _lab("shot-place"),
        add_w_dn_ind(D0, A1),
        move_w_imm_d16(A1, wb("ACTOR_TYPE06_SHOT_TYPE"), ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, wb("ACTOR_TYPE06_SHOT_SIZE"), HALF_WIDTH),
        leaf.clr_w_d16(A1, FIELD_30),
        clr_b_d16(A1, FIELD_18),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS),
        _lab("restore"),
        move_b_d16_d16(A0, FIELD_29, A0, ACTOR_FLAGS),
        clr_b_d16(A0, FIELD_31),
        move_b_imm_d16(A0, wb("ACTOR_TYPE06_RELOAD"), FIELD_30),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("walk"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "walk-right"),
        move_b_imm_dn(D7, wb("ACTOR_TYPE06_WALK_STEP")),
        _bsr(STEP_LEFT),
        _bsr(TOGGLE_SIDE),
        _bcc(BRA_W, "walk-frames"),
        _lab("walk-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE06_WALK_STEP")),
        _bsr(STEP_RIGHT),
        _bsr(TOGGLE_SIDE),
        _lab("walk-frames"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "walk-left-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE06_WALK_RIGHT")),
        _bcc(BRA_W, "walk-anim"),
        _lab("walk-left-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE06_WALK_LEFT")),
        _lab("walk-anim"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM32_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
        _lab("dying"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "held"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE06_DEAD_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "recoil-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "dead-right-frames"),
        _lab("recoil-left"),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "dead-left-frames"),
        _lab("held"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "dead-right-frames"),
        _lab("dead-left-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE06_DEAD_LEFT")),
        _bcc(BRA_W, "dead-anim"),
        _lab("dead-right-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE06_DEAD_RIGHT")),
        _lab("dead-anim"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "out"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab("out"),
        RTS,
    ]


def _type50_pieces():
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        addq_w_ind(wb("ACTOR_TYPE50_STEP"), A0),
        _bcc(BRA_W, "frames"),
        _lab("left"),
        subq_w_ind(wb("ACTOR_TYPE50_STEP"), A0),
        _lab("frames"),
        # DEAD: the PC-relative `lea` two instructions on overwrites a1 before anything reads it.
        lea_abs_l(A1, wb("ACTOR_TYPE50_FRAMES")),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE50_FRAMES")),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, wb("ACTOR_TYPE50_MASK")),
        move_b_dn_d16(D0, A0, FIELD_18),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BNE_W, "out"),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type51_pieces():
    # THE HEAD IS SLOT 52's AND 53's, byte for byte: the label assembler carries both of the
    # differences the three bodies have (which arm the raised switch bit goes to, and the
    # displacements that follow from sitting at another address), so there is one spelling of it.
    return _switched_contact_pieces("falling") + [
        move_w_imm_d16(A0, wb("ACTOR_TYPE51_SPRITE"), ACTOR_SPRITE),
        move_w_imm_dn(D7, wb("ACTOR_TYPE51_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "blocked?"),
        _lab("left"),
        _bsr(STEP_LEFT),
        _lab("blocked?"),
        tst_b_dn(D0),
        _bcc(BNE_W, "end"),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        RTS,
        _lab("falling"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "end"),
        move_w_imm_ind(A0, FREE_MARKER),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _lab("end"),
        RTS,
    ]


def _stun_pieces():
    return [
        move_w_imm_dn(D0, STUN_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, SND_STUB_TABLE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        _bsr(FOLLOWED_RECORD),
        leaf.move_w_abs_l_dn(D0, EFFECT_STATE_BD68),
        leaf.add_w_dn_dn(D0, D0),
        move_w_imm_dn(D1, STUN_STEPS_BASE),
        sub_w_dn_dn(D1, D0),
        move_b_dn_d16(D1, A1, FIELD_29),
        clr_b_d16(A1, FIELD_22),
        RTS,
    ]


def _platform_blocked_pieces():
    return [
        lea_abs_l(A6, COLLISION_MAP_DEFAULT),
        move_w_ind_dn(D1, A6),
        move_w_ind_dn(D0, A1),
        lsr_w_imm_dn(MAP_CELL_SHIFT, D0),
        addq_w_dn(COLLISION_MAP_CELLS, D0),
        adda_w_dn(D0, A6),
        move_w_ind_dn(D0, A1, ACTOR_Y),
        lsr_w_imm_dn(MAP_CELL_SHIFT, D0),
        mulu_w_dn(D1, D0),
        adda_l_dn(D1, A6),
        cmpi_b_ind(A6, TILE_BLOCK),
        _bcc(BEQ_W, "blocked"),
        cmpi_b_postinc(A6, TILE_LEDGE),
        _bcc(BEQ_W, "blocked"),
        cmpi_b_ind(A6, TILE_BLOCK),
        _bcc(BEQ_W, "blocked"),
        cmpi_b_postinc(A6, TILE_LEDGE),
        _bcc(BNE_W, "out"),
        _lab("blocked"),
        subq_w_d16(PLATFORM_STEP, A1, ACTOR_Y),
        clr_w_abs_l(PLATFORM_RIDDEN),
        bit_op_d16(BCLR_IMM, RIDING_BIT, A0, FIELD_22),
        _lab("out"),
        RTS,
    ]


def _type54_pieces():
    return [
        _bsr(SPRITE_FROM_6ED8),
        bit_op_d16(BTST_IMM, DIRECTION_BIT, A0, FIELD_22),
        _bcc(BEQ_W, "down"),
        subq_w_d16(PLATFORM_STEP, A0, ACTOR_Y),
        _bcc(BRA_W, "ridden?"),
        _lab("down"),
        addq_w_d16(PLATFORM_STEP, A0, ACTOR_Y),
        _lab("ridden?"),
        tst_w_abs_l(PLATFORM_RIDDEN),
        _bcc(BNE_W, "carrying?"),
        _bsr(PLATFORM_CARRY),
        _bcc(BRA_W, "travel"),
        _lab("carrying?"),
        bit_op_d16(BTST_IMM, RIDING_BIT, A0, FIELD_22),
        _bcc(BEQ_W, "travel"),
        move_w_ind_dn(D0, A0, ACTOR_Y),
        subi_w_dn(D0, PLATFORM_TOP),
        move_w_dn_d16(D0, A1, ACTOR_Y),
        _bsr(PLATFORM_RELEASE),
        bit_op_d16(BTST_IMM, DIRECTION_BIT, A0, FIELD_22),
        _bcc(BNE_W, "travel"),
        _bsr(PLATFORM_BLOCKED),
        _lab("travel"),
        addq_w_d16(PLATFORM_STEP, A0, FIELD_24),
        move_w_ind_dn(D0, A0, FIELD_24),
        cmp_w_d16_dn(D0, A0, SIZE_SECOND),
        _bcc(BNE_W, "out"),
        leaf.clr_w_d16(A0, FIELD_24),
        bit_op_d16(BCHG_IMM, DIRECTION_BIT, A0, FIELD_22),
        _lab("out"),
        RTS,
    ]


# $6e70 — the travel tail inside slot 54's body, which slot 55 reaches by three `bra.w`s. Its
# address comes out of slot 54's own layout rather than being transcribed.
TYPE54_TRAVEL_AT = _place(leaf.entry_of("actor_behavior_type54"), _type54_pieces())["travel"]


def _type55_pieces():
    return [
        _bsr(SPRITE_FROM_6ED8),
        bit_op_d16(BTST_IMM, DIRECTION_BIT, A0, FIELD_22),
        _bcc(BEQ_W, "right"),
        subq_w_ind(PLATFORM_STEP, A0),
        _bcc(BRA_W, "ridden?"),
        _lab("right"),
        addq_w_ind(PLATFORM_STEP, A0),
        _lab("ridden?"),
        tst_w_abs_w(PLATFORM_RIDDEN),
        _bcc(BNE_W, "carrying?"),
        _bsr(PLATFORM_CARRY),
        _bcc_abs(BRA_W, TYPE54_TRAVEL_AT),
        _lab("carrying?"),
        bit_op_d16(BTST_IMM, RIDING_BIT, A0, FIELD_22),
        _bcc_abs(BEQ_W, TYPE54_TRAVEL_AT),
        bit_op_d16(BTST_IMM, DIRECTION_BIT, A0, FIELD_22),
        _bcc(BEQ_W, "rider-right"),
        subq_w_ind(PLATFORM_STEP, A1),
        _bcc(BRA_W, "release"),
        _lab("rider-right"),
        addq_w_ind(PLATFORM_STEP, A1),
        _lab("release"),
        _bsr(PLATFORM_RELEASE),
        _bcc_abs(BRA_W, TYPE54_TRAVEL_AT),
    ]


def _type56_pieces():
    return [
        _bsr(SPRITE_FROM_6ED8),
        tst_w_abs_w(PLATFORM_RIDDEN),
        _bcc(BEQ_W, "rise"),
        bit_op_d16(BTST_IMM, RIDING_BIT, A0, FIELD_22),
        _bcc(BEQ_W, "out"),
        addq_w_d16(PLATFORM_STEP, A1, ACTOR_Y),
        addq_w_d16(PLATFORM_STEP, A0, ACTOR_Y),
        addq_w_d16(SINK_TICK, A0, FIELD_24),
        _bsr(PLATFORM_BLOCKED),
        _bcc_abs(BRA_W, leaf.entry_of(PLATFORM_RELEASE)),
        _lab("rise"),
        tst_w_d16(A0, FIELD_24),
        _bcc(BEQ_W, "carry"),
        subq_w_d16(PLATFORM_STEP, A0, ACTOR_Y),
        subq_w_d16(SINK_TICK, A0, FIELD_24),
        _lab("carry"),
        _bsr(PLATFORM_CARRY),
        _lab("out"),
        RTS,
    ]


# --- batch 31: slot 51's two neighbours, the four rows above the platforms, and the player gate ---
A5, A7 = 5, 7

PLAYER_GATE = "player_gate_on_1516"
JOY_NEWLY_PRESSED = "joy1_newly_pressed"

TYPE52_FRAMES = wb("ACTOR_TYPE52_FRAMES")
TYPE52_MASK = wb("ACTOR_TYPE52_MASK")
TYPE53_SPRITE = wb("ACTOR_TYPE53_SPRITE")
TYPE53_STEP = wb("ACTOR_TYPE53_STEP")
TYPE53_ALIVE = wb("ACTOR_TYPE53_ALIVE")
TYPE53_ALIVE_SET = wb("ACTOR_TYPE53_ALIVE_SET")
SPRITE_NONE = wb("ACTOR_SPRITE_NONE")
TYPE60_BECOMES = wb("ACTOR_TYPE60_BECOMES")
STATE_WORD_6F9C = wb("STATE_WORD_6F9C")
TYPE61_ACTIVE = wb("ACTOR_TYPE61_ACTIVE")
TYPE61_ACTIVE_SET = wb("ACTOR_TYPE61_ACTIVE_SET")
TYPE61_MESSAGES = wb("ACTOR_TYPE61_MESSAGES")
TYPE61_MESSAGE_END = wb("ACTOR_TYPE61_MESSAGE_END")
TYPE61_FIRST_MESSAGE = wb("ACTOR_TYPE61_FIRST_MESSAGE")
TYPE61_SONG = wb("ACTOR_TYPE61_SONG")
TYPE61_FIRE_BIT = wb("ACTOR_TYPE61_FIRE_BIT")
TYPE59_RESPAWN_KIND = wb("ACTOR_TYPE59_RESPAWN_KIND")
TYPE59_MARK_BIT = wb("ACTOR_TYPE59_MARK_BIT")
TYPE08_MARK_BIT = wb("ACTOR_TYPE08_MARK_BIT")
BEHAVIOR_TYPE07 = wb("ACTOR_BEHAVIOR_TYPE07")
TABLE_A32_SET = wb("TABLE_A32_SET")
SPAWN_RESPAWN_KIND = wb("SPAWN_RESPAWN_KIND")
TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_BOX_ACTIVE = wb("TEXT_BOX_ACTIVE")
TILE_33_MODE = wb("TILE_33_MODE")
PLAYER_STEP_BODY = wb("PLAYER_STEP_BODY")
SHOW_DATA_DISK_PROMPT = wb("SHOW_DATA_DISK_PROMPT")
JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")
ST_MEMORY_TOP = wb("ST_MEMORY_TOP")


def _switched_contact_pieces(free_label):
    """The head slots 51, 52 and 53 share, spelt once here for the two that agree BYTE FOR BYTE
    (slot 51's differs — its switch arm goes to a FALL, so its `bne.w` aims elsewhere and its damage
    arm sits at a different displacement). ``free_label`` is what the raised switch bit means for
    the caller, which is the whole of what 52 and 53 disagree about with 51."""
    return [
        bit_op_d16(BTST_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _bcc(BNE_W, free_label),
        _bsr(OVERLAP),
        btst_imm_dn(STRIKE_BIT, D0),
        _bcc(BEQ_W, "body"),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _bcc_abs(BRA_W, leaf.entry_of(STUN)),
        _lab("body"),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "walk"),
        move_b_imm_d16(A0, CONTACT_DAMAGE, TEMPLATE_SLOT),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _bsr(DAMAGE_FOLLOWED),
        st_d16(A0, FIELD_30),
        RTS,
        _lab("walk"),
    ]


def _type52_pieces():
    return _switched_contact_pieces("free") + [
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        # THE STEP IS THE RECORD'S OWN COUNTDOWN BYTE, zero-extended — not an immediate, and not the
        # settle's leftover either: the `moveq` clears the whole register first.
        moveq_0_dn(D7),
        move_b_d16_dn(D7, A0, FIELD_30),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "frames"),
        _lab("left"),
        _bsr(STEP_LEFT),
        _lab("frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, TYPE52_FRAMES),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, TYPE52_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "out"),
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type53_pieces():
    return [move_w_imm_abs_l(TYPE53_ALIVE_SET, TYPE53_ALIVE)] + _switched_contact_pieces("free") + [
        _bsr(FALL_AND_SETTLE),
        _bsr(PLAYER_GATE),
        leaf.moveq(TYPE53_STEP, D7),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        add_w_dn_ind(D7, A0),
        _bcc(BRA_W, "sprite"),
        _lab("left"),
        sub_w_dn_ind(D7, A0),
        _lab("sprite"),
        move_w_imm_d16(A0, TYPE53_SPRITE, ACTOR_SPRITE),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "free"),
        subq_b_d16(1, A0, FIELD_30),
        RTS,
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        move_w_imm_ind(A0, FREE_MARKER),
        clr_w_abs_l(TYPE53_ALIVE),
        RTS,
    ]


def _player_gate_pieces():
    return [
        tst_w_abs_l(TILE_33_MODE),
        _bcc_abs(BEQ_W, PLAYER_STEP_BODY),
        RTS,
    ]


def _type60_pieces():
    return [
        move_w_imm_d16(A0, SPRITE_NONE, ACTOR_SPRITE),
        tst_w_abs_l(STATE_WORD_6F9C),
        _bcc(BEQ_W, "out"),
        clr_w_abs_l(STATE_WORD_6F9C),
        move_w_imm_d16(A0, TYPE60_BECOMES, ACTOR_TYPE),
        _lab("out"),
        RTS,
    ]


def _type61_pieces():
    return [
        leaf.tst_b_abs_l(TYPE61_ACTIVE),
        _bcc(BNE_W, "armed"),
        move_l_imm_dn(D0, TYPE61_SONG),
        clr_l_dn(D1),
        lea_abs_l(A5, SND_STUB_TABLE),
        jsr_ind(A5),
        move_b_imm_d16(A0, 0, FIELD_31),
        move_b_imm_dn(D0, TYPE61_FIRST_MESSAGE),
        _lab("post"),
        leaf.move_b_dn_abs_l(D0, TEXT_REQUEST),
        leaf.clr_b_abs_l(TEXT_LIFETIME_REQUEST),
        leaf.clr_b_abs_l(TEXT_BOX_ACTIVE),
        leaf.move_b_imm_abs_l(TYPE61_ACTIVE_SET, TYPE61_ACTIVE),
        _lab("out"),
        RTS,
        _lab("armed"),
        jsr_abs_w(leaf.entry_of(JOY_NEWLY_PRESSED)),
        tst_b_dn(D0),
        _bcc_s(BPL_W, "out"),
        addq_b_d16(1, A0, FIELD_31),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_31),
        lea_abs_l(A1, TYPE61_MESSAGES),
        lea_indexed(A1, D0),
        move_b_ind_dn(D0, A1),
        cmp_b_imm_dn(D0, TYPE61_MESSAGE_END),
        _bcc_s(BNE_W, "post"),
        leaf.clr_b_abs_l(TYPE61_ACTIVE),
        movea_l_imm(A7, ST_MEMORY_TOP),
        jmp_abs_l(SHOW_DATA_DISK_PROMPT),
    ]


def _type59_pieces():
    return [
        bit_op_d16(BSET_IMM, TYPE59_MARK_BIT, A0, FIELD_30),
        lea_abs_l(A1, TABLE_A32_SET),
        move_w_imm_d16(A1, TYPE59_RESPAWN_KIND, SPAWN_RESPAWN_KIND),
        _bcc_abs(BRA_W, BEHAVIOR_TYPE07),
    ]


def _type08_pieces():
    """SIX BYTES AND NO BRANCH: slot 8 runs into slot 7's body rather than jumping to it, which is
    what bounds it at exactly one instruction."""
    return [bit_op_d16(BSET_IMM, TYPE08_MARK_BIT, A0, FIELD_30)]


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
    "actor_stun_followed": _stun_pieces(),
    "actor_platform_release_blocked_rider": _platform_blocked_pieces(),
    "actor_behavior_type02": _type02_pieces(),
    "actor_behavior_type03": _type03_pieces(),
    "actor_behavior_type04": _type04_pieces(),
    "actor_behavior_type05": _type05_pieces(),
    "actor_behavior_type06": _type06_pieces(),
    "actor_behavior_type50": _type50_pieces(),
    "actor_behavior_type51": _type51_pieces(),
    "actor_behavior_type54": _type54_pieces(),
    "actor_behavior_type55": _type55_pieces(),
    "actor_behavior_type56": _type56_pieces(),
    "actor_behavior_type52": _type52_pieces(),
    "actor_behavior_type53": _type53_pieces(),
    "actor_behavior_type59": _type59_pieces(),
    "actor_behavior_type08": _type08_pieces(),
    "actor_behavior_type60": _type60_pieces(),
    "actor_behavior_type61": _type61_pieces(),
    "player_gate_on_1516": _player_gate_pieces(),
}
RECONSTRUCTED_ROUTINES = 39

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
    "actor_stun_followed": 44,          # $6796..$67c1, bounded by actor_set_side_flag's entry
    "actor_platform_release_blocked_rider": 76,   # $6e8c..$6ed7, then the $6ed8 sprite/band rows
    "actor_behavior_type02": 254,       # $2462..$255f, then 96 bytes of frame words
    "actor_behavior_type03": 374,       # $25c0..$2735, then 96
    "actor_behavior_type04": 342,       # $2796..$28eb, then 256 (four lists and the hover table)
    "actor_behavior_type05": 262,       # $29ec..$2af1, bounded by actor_start_motion_at_speed
    "actor_behavior_type06": 490,       # $2bc8..$2db1, then 96
    "actor_behavior_type50": 64,        # $5a6e..$5aad, then its own two frame words
    "actor_behavior_type51": 138,       # $5ab2..$5b3b, bounded by slot 52's entry
    "actor_behavior_type54": 112,       # $6e1c..$6e8b, bounded by the probe helper's entry
    "actor_behavior_type55": 74,        # $6ef4..$6f3d — no `rts` at all, three `bra.w`s into 54
    "actor_behavior_type56": 64,        # $6f3e..$6f7d, bounded by slot 60's entry
    "actor_behavior_type52": 152,       # $5b3c..$5bd3, then its own eight frame words
    "actor_behavior_type53": 136,       # $5be4..$5c6b, then the ALIVE word at $5c6c
    "actor_behavior_type60": 30,        # $6f7e..$6f9b, then WB_STATE_WORD_6F9C itself
    "actor_behavior_type61": 118,       # $6f9e..$7013, then the ACTIVE byte and the message table
    "actor_behavior_type59": 22,        # $7044..$7059, bounded by slot 8's entry
    "actor_behavior_type08": 6,         # $705a..$705f — one instruction, then slot 7's own entry
    "player_gate_on_1516": 12,          # $d78..$d83, bounded by player_apply_joystick's entry
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

# The slots this port HAS a reconstruction for; every other slot is the boundary. Keyed by the
# routine NAME rather than the slot number, exactly as src/behavior.c's list is keyed by the target
# address — so adding a handler is one row here and one row there and no case moves.
PORTED_TARGETS = ("actor_behavior_null",
                  "actor_behavior_type02", "actor_behavior_type03", "actor_behavior_type04",
                  "actor_behavior_type05", "actor_behavior_type06", "actor_behavior_type08",
                  "actor_behavior_type50", "actor_behavior_type51", "actor_behavior_type52",
                  "actor_behavior_type53", "actor_behavior_type54", "actor_behavior_type55",
                  "actor_behavior_type56", "actor_behavior_type59",
                  "actor_behavior_type60", "actor_behavior_type61")
PORTED_SLOTS = tuple(slot for slot, name in sorted(TABLE_TARGETS.items())
                     if name in PORTED_TARGETS)

# The two handlers that have NO arm which returns: both raise a bit of their own and then run into
# slot 7's body, so what they report is an address exactly as an unported slot does. Keyed by name
# for the same reason PORTED_TARGETS is — the slot is not what the dispatcher jumps through.
#
# The second element is the TRANSFER INSTRUCTION a checkpointed run must witness, or None. Slot 59
# has one — the `bra.w $7060` its pin ends with, whose address comes out of that pin — and slot 8
# has NONE AT ALL: its single instruction simply runs into slot 7's first byte, so there is no
# transfer to observe and the checkpoint is unambiguous only because the body holds no `rts` either.
ALWAYS_TRANSFER = {
    "actor_behavior_type59": (BEHAVIOR_TYPE07,
                              leaf.entry_of("actor_behavior_type59")
                              + len(_asm(leaf.entry_of("actor_behavior_type59"),
                                         _type59_pieces()[:-1]))),
    "actor_behavior_type08": (BEHAVIOR_TYPE07, None),
}


def test_no_handler_that_always_transfers_reports_a_PORTED_address():
    """What makes an address a boundary is that this port does not have it. Slots 59 and 8 hard-code
    WB_ACTOR_BEHAVIOR_TYPE07, so the batch that ports slot 7 must move them — and until it does,
    nothing else would fail: the dispatch rows and the prologue cases would all still pass while the
    walk stopped at a slot the port has."""
    ported = {leaf.entry_of(name) for name in PORTED_TARGETS}
    for name, (target, _witness) in ALWAYS_TRANSFER.items():
        assert target not in ported, (
            f"{name} reports {target:#x}, which is reconstructed now — it is no longer a boundary")


def test_the_unported_slots_the_cases_name_really_are_unported():
    """UNPORTED_TYPE and UNPORTED_SLOT are what every boundary case in this file steps over or stops
    at. If a later batch ports either, the cases below would quietly stop testing a boundary — so
    the two numbers are checked against the ported list rather than trusted."""
    for slot in (UNPORTED_TYPE, UNPORTED_SLOT, UNPORTED_MID, UNPORTED_HIGH):
        assert slot not in PORTED_SLOTS, (
            f"slot {slot} is reconstructed now — the boundary cases in this file need a new one")


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
        == [slot for slot, name in sorted(TABLE_TARGETS.items())
            if name == "actor_behavior_null"]


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
    slot, target_slot = 0, UNPORTED_SLOT
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


# --- what a PORTED handler is allowed to touch ------------------------------------------------------
# The band a handler's frame may write while it stays on its own arms: the three actor tables (one
# record's margin either side, as `_tier_pokes` seeds them) and the one global the platforms keep. A
# case that drives an arm reaching actor_damage_followed, actor_damage_template_hitpoints or
# actor_defeat_and_score widens it through `_foreign_band` below, which takes the addresses from
# test_actor.py's own models rather than re-listing them here.
#
# THIS LIST IS THE STRAY-WRITE BOUND, NOT THE DIFF SCOPE, so every address in it is one every case
# that uses it stops checking — which is why the globals are keyed by the handler that publishes
# them (`HANDLER_GLOBALS`, the same shape as `_quiet_record`) instead of being folded in here.
# WB_ACTOR_PLATFORM_RIDDEN is the one exception and stays shared: three handlers AND
# actor_platform_release_blocked_rider write it, and `BLOCKED_RIDER_BAND` below is this same list.
HANDLER_WRITE_BAND = [(TABLES_LO, TABLES_HI - TABLES_LO), (PLATFORM_RIDDEN, WORD_BYTES)]

# The global each of the four new handlers publishes, and nothing else in the tier writes.
HANDLER_GLOBALS = {
    "actor_behavior_type53": [(TYPE53_ALIVE, WORD_BYTES)],
    "actor_behavior_type59": [(TABLE_A32_SET + SPAWN_RESPAWN_KIND, WORD_BYTES)],
    "actor_behavior_type60": [(STATE_WORD_6F9C, WORD_BYTES)],
    "actor_behavior_type61": [(TYPE61_ACTIVE, 1), (TEXT_REQUEST, 1), (TEXT_BOX_ACTIVE, 1),
                              (TEXT_LIFETIME_REQUEST, 1)],
}


def _handler_band(name):
    """What `name`'s frame may write: the tier's records plus that handler's OWN globals."""
    return HANDLER_WRITE_BAND + HANDLER_GLOBALS.get(name, [])

# Upper bounds for the routines a handler calls whose bodies belong to other batteries, in
# instructions. The two map probes and the PRNG already have theirs above; these three are the
# damage pair and the defeat, and they are bounds rather than counts for the same reason.
FALL_AND_SETTLE_INSNS = 3 * MAP_PROBE_INSNS
DAMAGE_INSNS = 400
DEFEAT_INSNS = 600
# ...and the sound module's, which slot 61's opening frame reaches through stub +0. It comes from
# the battery that owns snd_play_song rather than being a number stated here.
from test_sound import PLAY_SONG_INSN_CAP   # noqa: E402

HANDLER_CALLEE_INSNS = (INSN_COUNT["actor_spawn_anim_step"]
                        + INSN_COUNT["actor_hit_by_player_shot"]
                        + INSN_COUNT["actor_followed_overlap_mask"]
                        + INSN_COUNT["actor_sprite_from_6ed8"]
                        + INSN_COUNT["actor_platform_carry_followed"]
                        + INSN_COUNT["actor_platform_release_check"]
                        + INSN_COUNT["actor_platform_release_blocked_rider"]
                        + INSN_COUNT["actor_hop_ascend_step"]
                        + INSN_COUNT["actor_stun_followed"]
                        + FALL_AND_SETTLE_INSNS + 2 * MAP_PROBE_INSNS
                        + SIDE_FLAG_INSNS + WITHIN_INSNS + DAMAGE_INSNS + DEFEAT_INSNS
                        + PLAY_SONG_INSN_CAP)


def _handler_cap(name):
    """A handler's instruction cap: its own pinned body plus one bound for every routine anything in
    this file can call. Derived from the pins, so a body that grows carries its cap with it."""
    return INSN_COUNT[name] + HANDLER_CALLEE_INSNS


# The five slots in the $2462..$2db1 band, in table order — the ones that share the spawn gate.
MONSTER_SLOTS = (2, 3, 4, 5, 6)
MONSTER_HANDLERS = tuple(f"actor_behavior_type{slot:02d}" for slot in MONSTER_SLOTS)


def _quiet_record(name, actor):
    """What a ported handler's record needs for the dispatch case to stay inside
    HANDLER_WRITE_BAND. Slots 2..6 open on the spawn gate, so raising WB_ACTOR_FLAGS2_SPAWNED_BIT
    makes the whole frame one animation step; slot 51 is put on its FALLING arm with a half-width
    small enough to bound the settle's own scan; the other four have no arm that leaves the band."""
    if name in MONSTER_HANDLERS:
        return {actor + FLAGS2: bytes([1 << SPAWNED_BIT])}
    if name == "actor_behavior_type51":
        return {actor + FLAGS2: bytes([1 << FLAGS2_BIT_0]), actor + HALF_WIDTH: word(4),
                actor + ACTOR_FLAGS: bytes([0])}
    # Slots 52 and 53 are quietest on their SWITCH arm, which frees the slot and runs nothing else;
    # slot 60 is quiet while WB_STATE_WORD_6F9C is clear (it publishes one sprite word); slot 61 is
    # quiet while its sequence is armed and the fire button has NOT just gone down, which is the one
    # arm of it that writes nothing at all and the one that does not reach the sound module.
    if name in ("actor_behavior_type52", "actor_behavior_type53"):
        return {actor + FLAGS2: bytes([1 << FLAGS2_BIT_0])}
    if name == "actor_behavior_type60":
        return {STATE_WORD_6F9C: word(0)}
    if name == "actor_behavior_type61":
        return {TYPE61_ACTIVE: bytes([TYPE61_ACTIVE_SET]),
                JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([0])}
    return {}


# --- $928: the dispatch, entry by entry -------------------------------------------------------------
@pytest.mark.parametrize("slot", range(BEHAVIOR_SLOTS), ids=lambda v: f"slot{v:02d}")
def test_the_dispatcher_transfers_to_the_slot_the_type_names(slot):
    """ONE CASE PER TABLE ENTRY, and it is the whole pin on src/behavior.c's BEHAVIOR_SLOTS array.

    For an UNPORTED slot the reconstruction returns the address it would have transferred to and the
    oracle is stopped at that same address — so the two agree on WHICH handler, with `cov_visited`
    on the `jmp (a1)` as the positive evidence that the transfer fired rather than the routine
    having returned. For a ported slot the run goes THROUGH the handler and the two cores are
    compared over the frame behind it.

    AND THERE IS NOW A THIRD KIND, which is behavior.h's handler boundary: slots 59 and 8 are
    reconstructed AND transfer, so the run is checkpointed at slot 7's entry like an unported one
    while the writes their prologues make are diffed like a ported one.
    """
    actor = _record(TABLE_DEFAULT, 3)
    what = f"actor_dispatch_behavior type {slot}"
    name = TABLE_TARGETS[slot]
    pokes = _tier_pokes(case_salt(what),
                        leaf.overlay({actor + ACTOR_TYPE: word(slot)}, _quiet_record(name, actor)))
    target = leaf.entry_of(name)
    regs = {"a0": actor, "_pokes": pokes}

    if slot not in PORTED_SLOTS:
        info = leaf.run_reaching(DISPATCHER, _DISPATCH(actor), [], what, DISPATCH_JMP_PC,
                                 regs=regs, stop_pc=target,
                                 max_insns=_cap(DISPATCHER,
                                                extra=INSN_COUNT["actor_behavior_null"]))
        assert info["ret"] == target, (
            f"{what}: the reconstruction reported {info['ret']:#x} against the table's {target:#x}")
        assert not program_writes(info), f"{what}: the dispatcher wrote memory, which it does not"
        return

    # A PORTED slot runs its whole handler here, which is what makes this case a differential over
    # the transfer AND the frame behind it. The seeding above puts each handler on its quietest arm,
    # so what it may write is BOUNDED by the tier's own band — the per-handler cases below are what
    # state a write set exactly.
    expected = ALWAYS_TRANSFER.get(name, (DISPATCH_RAN, None))[0]
    caps = dict(regs=regs, poison=False,
                max_insns=_cap(DISPATCHER, extra=_handler_cap(name)))
    if expected == DISPATCH_RAN:
        info = leaf.run(DISPATCHER, _DISPATCH(actor), _handler_band(name), what, **caps)
    else:
        info = leaf.run_reaching(DISPATCHER, _DISPATCH(actor), _handler_band(name), what,
                                 DISPATCH_JMP_PC, stop_pc=expected, **caps)
    assert info["ret"] == expected, (
        f"{what}: the reconstruction reported {info['ret']:#x} against the {expected:#x} this slot "
        f"leaves at")


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

    # The arms every ported slot is QUIETEST on, ALL re-applied per iteration: the spawn gate for
    # slots 2..6, the switch bit for 51..53, and slot 61's armed-with-no-edge state. Hoisting the
    # last three out of the loop would rest on "no quiet arm writes its own seed" — true today and
    # unchecked, and the failure would be silent, because both of slot 61's arms answer
    # WB_ACTOR_DISPATCH_RAN and this case asserts only the answer. A per-iteration byte store is
    # nothing next to the FFI call it precedes.
    quiet_flags2 = (1 << SPAWNED_BIT) | (1 << FLAGS2_BIT_0)

    for type_word in range(chunk * TYPES_PER_CHUNK, (chunk + 1) * TYPES_PER_CHUNK):
        buf[actor + ACTOR_TYPE] = type_word >> 8
        buf[actor + ACTOR_TYPE + 1] = type_word & 0xff
        buf[actor + FLAGS2] = quiet_flags2
        buf[TYPE61_ACTIVE] = TYPE61_ACTIVE_SET
        buf[JOY1_PREV] = buf[JOY1_CURRENT] = 0
        slot = _dispatched_slot(type_word)
        answer = dispatch(buf, actor)
        if slot is None:
            assert answer == DISPATCH_REFUSED, (
                f"type {type_word:#06x} answered {answer:#x}, not the refusal its offset earns")
            continue
        dispatched += 1
        expected = leaf.entry_of(TABLE_TARGETS[slot])
        if slot in PORTED_SLOTS:
            expected = ALWAYS_TRANSFER.get(TABLE_TARGETS[slot], (DISPATCH_RAN, None))[0]
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


@pytest.mark.parametrize("type_word,slot",
                         [(0x4000 + UNPORTED_SLOT, UNPORTED_SLOT),
                          (0x8000 + UNPORTED_MID, UNPORTED_MID),
                          (0xc000 + UNPORTED_HIGH, UNPORTED_HIGH)],
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
    slot = UNPORTED_SLOT
    record = _record(TABLE_DEFAULT, 0)
    pokes = _walk_pokes(case_salt(what), [slot], {record + ACTOR_X: word(0xffff)})
    target = leaf.entry_of(TABLE_TARGETS[slot])

    info = leaf.run_reaching("actor_behavior_pass", _PASS, [], what, DISPATCH_JMP_PC,
                             regs={"_pokes": pokes}, stop_pc=target,
                             max_insns=WALK_INSN_PER_RECORD * 2 + leaf.LEAF_INSN_CAP)
    assert info["ret"] == target, (
        f"{what}: the reconstruction reported {info['ret']:#x}, so it read the terminator as a "
        f"WORD and ended the walk")


@pytest.mark.parametrize("slot", [UNPORTED_SLOT, UNPORTED_MID, UNPORTED_HIGH],
                         ids=lambda v: f"handler{v:02d}")
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
    slot = UNPORTED_SLOT
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
        fields[_record(TABLE_DEFAULT, slot) + ACTOR_TYPE] = word(UNPORTED_SLOT)
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


# --- the ten handlers, arm by arm -------------------------------------------------------------------
# Every case below enters the handler at its own address with the record in a0, which is how the
# dispatcher reaches it. What each pins is the ARM: the differential compares the whole image
# either way, so the seeds are chosen to put the frame on one path and the assertions say which.
#
# EVERY HANDLER HANDS BACK A uint32_t, which is behavior.h's boundary: WB_ACTOR_DISPATCH_RAN when it
# ran to its own `rts`, or the address at which the original left code this port has.
_HANDLER_GLUE = {name: leaf.register_glue(name, [ctypes.c_uint32], ctypes.c_uint32)
                 for name in PORTED_TARGETS if name != "actor_behavior_null"}
_PLAYER_GATE = leaf.image_glue(PLAYER_GATE, ctypes.c_uint32)
_STUN = leaf.image_glue("actor_stun_followed")
_BLOCKED_RIDER = leaf.register_glue("actor_platform_release_blocked_rider", [ctypes.c_uint32] * 2)


def _run_handler(name, what, pokes, band=None, expect=DISPATCH_RAN, transfer=None, **kwargs):
    """One handler frame, entered where the `jmp (a1)` would land — and its ANSWER, checked.

    THE RETURN IS THE POINT OF THE NEW SIGNATURE and a memory diff cannot see it: a handler that
    reported a boundary where it really returned writes exactly the same bytes, and
    `actor_behavior_pass` would then stop the whole walk at a record it had in fact finished. So
    every case asserts it, and the boundary cases say which address they expect instead of
    WB_ACTOR_DISPATCH_RAN. `kwargs` reaches `leaf.run` (stop_pc, psg_seed) so a boundary case still
    enters the handler the way the dispatcher does rather than re-spelling the convention, and
    `transfer` names the instruction whose execution witnesses that the tail was really taken."""
    runner = leaf.run if transfer is None else (
        lambda *args, **kw: leaf.run_reaching(args[0], args[1], args[2], args[3], transfer, **kw))
    info = runner(name, _HANDLER_GLUE[name](ACTOR),
                  _handler_band(name) if band is None else band, what,
                  regs={"a0": ACTOR, "_pokes": pokes}, poison=False,
                  max_insns=_handler_cap(name), **kwargs)
    assert info["ret"] == expect, (
        f"{what}: the reconstruction reported {info['ret']:#x}, not the {expect:#x} this arm ends at")
    return info


def _monster_pokes(what, slot, fields=None):
    """A record of `slot`'s own type on ACTOR, with the geometry every arm reads stated: a small
    half-width (so a settle's footprint scan is bounded), a vertical extent, and a position clear of
    the followed record's. Everything else stays address-keyed."""
    base = {ACTOR + ACTOR_TYPE: word(slot),
            ACTOR + HALF_WIDTH: word(4), ACTOR + SIZE_SECOND: word(8),
            ACTOR + ACTOR_X: word(0x0100), ACTOR + ACTOR_Y: word(0x0080),
            ACTOR + ACTOR_FLAGS: bytes([0]), ACTOR + FLAGS2: bytes([0]),
            ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([0x10]),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0200),
            FOLLOWED_DEFAULT + ACTOR_Y: word(0x0080),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0x0100),
            FOLLOWED_DEFAULT + HALF_WIDTH: word(4),
            FOLLOWED_DEFAULT + SIZE_SECOND: word(8)}
    return _tier_pokes(case_salt(what), leaf.overlay(base, fields or {}))


# --- the spawn gate the five monster slots share ----------------------------------------------------
@pytest.mark.parametrize("slot", MONSTER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_a_spawning_record_plays_the_animation_and_nothing_else(slot):
    """`btst #2,9(a0) / bne.w $698a` — the first two instructions of all five. The whole frame is
    then one animation step, which is what makes the write set three bytes of the record."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} spawning"
    cursor = 4
    pokes = _monster_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << SPAWNED_BIT]),
                                        ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + FIELD_18: cursor + ANIM_FRAME_BYTES}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + cursor))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("slot", MONSTER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_spawn_gate_is_the_only_thing_bit_2_gates(slot):
    """The same seed with the bit down runs the rest of the frame instead — which is what says the
    case above is testing the gate and not the seed."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} not spawning"
    pokes = _monster_pokes(what, slot)

    info = _run_handler(name, what, pokes)
    assert program_writes(info), f"{what}: the frame wrote nothing at all, so no arm ran"


# --- slot 50: the drift -----------------------------------------------------------------------------
@pytest.mark.parametrize("side,step", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
def test_slot50_slides_eight_pixels_the_way_its_side_bit_points(side, step):
    what = f"actor_behavior_type50 side={side:#04x}"
    x, cursor, timer = 0x0100, 0, 0x10
    pokes = _monster_pokes(what, 50, {ACTOR + ACTOR_FLAGS: bytes([side]),
                                      ACTOR + FIELD_18: bytes([cursor]),
                                      ACTOR + FIELD_30: bytes([timer])})

    info = _run_handler("actor_behavior_type50", what, pokes)
    expected = {ACTOR + FIELD_18: cursor + ANIM_FRAME_BYTES, ACTOR + FIELD_30: timer - 1}
    _put(expected, ACTOR + ACTOR_X, x + step * wb("ACTOR_TYPE50_STEP"))
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(wb("ACTOR_TYPE50_FRAMES") + cursor))
    _assert_writes(info, expected, what)


def test_slot50_frees_its_own_slot_when_the_countdown_runs_out():
    """`subq.b #1,30(a0) / bne` — the free marker lands on the frame the byte reaches zero, and the
    x it overwrites is the one this same frame just stepped."""
    what = "actor_behavior_type50 countdown expiring"
    pokes = _monster_pokes(what, 50, {ACTOR + FIELD_30: bytes([1]),
                                      ACTOR + ACTOR_FLAGS: bytes([0])})

    info = _run_handler("actor_behavior_type50", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8 | written[ACTOR + ACTOR_X + 1]) == FREE_MARKER, (
        f"{what}: the record was not freed")
    assert written[ACTOR + FIELD_30] == 0


def test_slot50_wraps_its_cursor_over_two_frames_only():
    """`andi.w #$3` — a four-BYTE wrap over a two-word table, so the cursor only ever holds 0 or 2
    and the second word is the last one reachable."""
    seen = set()
    for cursor in (0, 2, 0xfe):
        what = f"actor_behavior_type50 cursor {cursor:#04x}"
        pokes = _monster_pokes(what, 50, {ACTOR + FIELD_18: bytes([cursor]),
                                          ACTOR + FIELD_30: bytes([0x10])})
        info = _run_handler("actor_behavior_type50", what, pokes)
        seen.add(program_writes(info)[ACTOR + FIELD_18])
    assert seen == {0, 2}, f"the cursor reached {sorted(seen)}, not just the table's two offsets"


# --- $6796: the stun --------------------------------------------------------------------------------
@pytest.mark.parametrize("state", [0, 1, 3, 0x8000], ids=lambda v: f"bd68={v:#06x}")
def test_the_stun_stamps_ten_minus_twice_the_state_word(state):
    """`move.w $bd68,d0 / add.w d0,d0 / move.w #$a,d1 / sub.w d0,d1` is 16-bit throughout and only
    the low BYTE of the difference is stored — so a state word above 5 wraps the count instead of
    going negative, which $8000 is here to drive."""
    what = f"actor_stun_followed bd68={state:#06x}"
    pokes = _tier_pokes(case_salt(what), {EFFECT_STATE_BD68: word(state),
                                          FOLLOWED_DEFAULT + FIELD_29: bytes([0x5a]),
                                          FOLLOWED_DEFAULT + FIELD_22: bytes([0x5a])})
    image = harness.make_image(pokes)
    expected = {FOLLOWED_DEFAULT + FIELD_29: (STUN_STEPS_BASE - 2 * state) & 0xff,
                FOLLOWED_DEFAULT + FIELD_22: 0}
    expected.update(_sfx_bytes(image, STUN_SFX, SND_CHANNEL_A))

    info = leaf.run("actor_stun_followed", _STUN, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=_cap(STUN) + FOLLOWED_INSNS + DAMAGE_INSNS)
    _assert_writes(info, expected, what)


def test_the_stun_writes_the_record_the_mode_flag_names():
    """`bsr $67e0` — it is followed_actor_record's a1 that is stamped, so the other table's record
    is the one written while WB_STATE_FLAG_A32 is up."""
    what = "actor_stun_followed over the a32 record"
    pokes = _tier_pokes(case_salt(what), {FLAG_A32: word(0xffff), EFFECT_STATE_BD68: word(0)})
    image = harness.make_image(pokes)
    expected = {FOLLOWED_A32 + FIELD_29: STUN_STEPS_BASE, FOLLOWED_A32 + FIELD_22: 0}
    expected.update(_sfx_bytes(image, STUN_SFX, SND_CHANNEL_A))

    info = leaf.run("actor_stun_followed", _STUN, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=_cap(STUN) + FOLLOWED_INSNS + DAMAGE_INSNS)
    _assert_writes(info, expected, what)


# --- $6e8c: the rider's own cell --------------------------------------------------------------------
# The maps come from the battery that owns them, so "what a collision map looks like" has one
# spelling — the rule test_behavior.py already follows for the record geometry.
from test_map import A32_STRIDE, DEFAULT_STRIDE, MAP_A32, map_pokes   # noqa: E402

RIDER = _record(TABLE_DEFAULT, 4)
RIDER_X, RIDER_Y = 0x0100, 0x0080


def _rider_cell(column_offset=0, base=None, stride=DEFAULT_STRIDE):
    """Where $6e8c's own arithmetic lands: `lsr.w #4` on each coordinate, plus the same
    WB_COLLISION_MAP_CELLS bias actor_map_cell_lookup applies.

    `base` and `stride` are parameters ONLY so the asymmetry case below can name the SAME cell on
    the other map: a case that seeded the a32 map at its own cell 0 would be seeding a cell this
    routine never reads on either map, and would pass however the map was chosen."""
    column = (RIDER_X >> MAP_CELL_SHIFT) + COLLISION_MAP_CELLS + column_offset
    return ((COLLISION_MAP_DEFAULT if base is None else base)
            + column + stride * (RIDER_Y >> MAP_CELL_SHIFT))


def _blocked_rider_pokes(what, tiles, riding=1 << RIDING_BIT):
    salt = case_salt(what)
    pokes = _tier_pokes(salt, {ACTOR + FIELD_22: bytes([riding]),
                               RIDER + ACTOR_X: word(RIDER_X), RIDER + ACTOR_Y: word(RIDER_Y),
                               PLATFORM_RIDDEN: word(1)})
    pokes.update(map_pokes(salt))
    for offset, tile in tiles.items():
        pokes[_rider_cell(offset)] = bytes([tile])
    return pokes


BLOCKED_RIDER_BAND = HANDLER_WRITE_BAND
BLOCKED_RIDER_CAP = 40


@pytest.mark.parametrize("tiles,blocked", [
    ({0: TILE_BLOCK, 1: 0}, True),
    ({0: TILE_LEDGE, 1: 0}, True),
    ({0: 0, 1: TILE_BLOCK}, True),
    ({0: 0, 1: TILE_LEDGE}, True),
    ({0: 0, 1: 0}, False),
    ({0: TILE_LEDGE + 1, 1: TILE_BLOCK - 1}, False),
], ids=["first-block", "first-ledge", "second-block", "second-ledge", "clear", "neither-code"])
def test_the_blocked_rider_check_reads_two_cells_and_only_two_codes(tiles, blocked):
    """Four `cmpi.b` in two post-increment pairs: the rider's own cell and the one beside it, each
    against WB_MAP_TILE_BLOCK and WB_MAP_TILE_LEDGE. Anything else leaves the ride alone."""
    what = f"actor_platform_release_blocked_rider tiles={tiles}"
    pokes = _blocked_rider_pokes(what, tiles)

    info = leaf.run("actor_platform_release_blocked_rider", _BLOCKED_RIDER(ACTOR, RIDER),
                    BLOCKED_RIDER_BAND, what,
                    regs={"a0": ACTOR, "a1": RIDER, "_pokes": pokes}, poison=False,
                    max_insns=BLOCKED_RIDER_CAP)
    expected = {}
    if blocked:
        _put(expected, RIDER + ACTOR_Y, RIDER_Y - PLATFORM_STEP)
        _put(expected, PLATFORM_RIDDEN, 0)
        expected[ACTOR + FIELD_22] = 0
    _assert_writes(info, expected, what)


def test_the_blocked_rider_check_probes_the_default_map_whatever_the_mode_flag_says():
    """`lea $23494.l,a6` with no test at all — the asymmetry $10a2's ground test has, in a second
    routine. With WB_STATE_FLAG_A32 up and the OTHER map holding the block, nothing happens."""
    what = "actor_platform_release_blocked_rider a32 up, block on the a32 map"
    pokes = _blocked_rider_pokes(what, {0: 0, 1: 0})
    pokes[FLAG_A32] = word(0xffff)
    # THE RIDER'S OWN CELL on the a32 map — its stride, not the default one's — so the only thing
    # separating a pass from a fail is WHICH map the routine read.
    for offset in (0, 1):
        pokes[_rider_cell(offset, base=MAP_A32, stride=A32_STRIDE)] = bytes([TILE_BLOCK])

    info = leaf.run("actor_platform_release_blocked_rider", _BLOCKED_RIDER(ACTOR, RIDER),
                    BLOCKED_RIDER_BAND, what,
                    regs={"a0": ACTOR, "a1": RIDER, "_pokes": pokes}, poison=False,
                    max_insns=BLOCKED_RIDER_CAP)
    assert not program_writes(info), f"{what}: it read the a32 map after all"


# --- slots 54, 55 and 56: the three moving platforms -------------------------------------------------
MOVER_ROW_INDEX = 1              # the middle of the three WB_ACTOR_SPRITE_TABLE_6ED8 rows
MOVER_ROW = wb("ACTOR_SPRITE_TABLE_6ED8") + MOVER_ROW_INDEX * wb("ACTOR_SPRITE_6ED8_STRIDE")
MOVER_X, MOVER_Y = 0x0100, 0x0080
MOVER_LIMIT = 0x20               # into WB_ACTOR_SIZE_SECOND: the travel the cursor is compared to


def _moving_platform_pokes(what, fields=None, ridden=0):
    """A platform on ACTOR with a real WB_ACTOR_SPRITE_TABLE_6ED8 row, and the followed record
    parked ON it — inside the row's band and at the ride height, so the catch and the release both
    have something to decide about."""
    band_left = _image_word(MOVER_ROW + BAND_LEFT)
    base = {ACTOR + HALF_WIDTH: word(MOVER_ROW_INDEX),
            ACTOR + SIZE_SECOND: word(MOVER_LIMIT),
            ACTOR + ACTOR_X: word(MOVER_X), ACTOR + ACTOR_Y: word(MOVER_Y),
            ACTOR + FIELD_22: bytes([0]), ACTOR + FIELD_24: word(0),
            FOLLOWED_DEFAULT + ACTOR_X: word(MOVER_X - band_left + 1),
            FOLLOWED_DEFAULT + ACTOR_Y: word(MOVER_Y - PLATFORM_TOP),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0]),
            FOLLOWED_DEFAULT + FLAGS2: bytes([0]),
            PLATFORM_RIDDEN: word(ridden)}
    salt = case_salt(what)
    pokes = _tier_pokes(salt, leaf.overlay(base, fields or {}))
    pokes.update(map_pokes(salt))
    return pokes


@pytest.mark.parametrize("name,axis", [("actor_behavior_type54", ACTOR_Y),
                                       ("actor_behavior_type55", ACTOR_X)],
                         ids=["type54-vertical", "type55-horizontal"])
@pytest.mark.parametrize("direction", [0, 1 << DIRECTION_BIT], ids=["forward", "back"])
def test_the_travelling_platforms_step_two_pixels_on_their_own_axis(name, axis, direction):
    """Slot 54 moves on the y word and slot 55 on the x, both by WB_ACTOR_PLATFORM_STEP and both on
    bit 0 of 22(a0) — which is the whole of the difference between the two bodies."""
    what = f"{name} direction={direction:#04x}"
    pokes = _moving_platform_pokes(what, {ACTOR + FIELD_22: bytes([direction])})

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    start = MOVER_Y if axis == ACTOR_Y else MOVER_X
    moved = start - PLATFORM_STEP if direction else start + PLATFORM_STEP
    assert (written[ACTOR + axis] << 8 | written[ACTOR + axis + 1]) == moved, (
        f"{what}: the platform is at {written[ACTOR + axis]:#04x}.., not {moved:#06x}")


@pytest.mark.parametrize("name", ["actor_behavior_type54", "actor_behavior_type55"],
                         ids=["type54", "type55"])
def test_the_travelling_platforms_turn_on_equality_with_their_limit(name):
    """`cmp.w 16(a0),d0 / bne` — the turn is on EQUALITY, so the cursor is zeroed and the direction
    bit flipped only on the frame the step lands exactly on the limit."""
    what = f"{name} reaching its limit"
    pokes = _moving_platform_pokes(what, {ACTOR + FIELD_24: word(MOVER_LIMIT - PLATFORM_STEP)})

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + FIELD_24] << 8 | written[ACTOR + FIELD_24 + 1]) == 0
    assert written[ACTOR + FIELD_22] & (1 << DIRECTION_BIT), f"{what}: the direction did not flip"


@pytest.mark.parametrize("name", ["actor_behavior_type54", "actor_behavior_type55"],
                         ids=["type54", "type55"])
def test_a_limit_the_step_cannot_land_on_is_never_reached(name):
    """The other half of that `bne`: an ODD limit is stepped straight past, and the platform travels
    on until the word wraps. The case drives ONE frame and shows the cursor going by it."""
    what = f"{name} odd limit"
    odd = MOVER_LIMIT + 1
    pokes = _moving_platform_pokes(what, {ACTOR + SIZE_SECOND: word(odd),
                                   ACTOR + FIELD_24: word(odd - 1)})

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + FIELD_24] << 8 | written[ACTOR + FIELD_24 + 1]) == odd + 1, (
        f"{what}: the cursor stopped instead of stepping past an unreachable limit")


def test_slot54_snaps_the_rider_to_its_own_top_every_ridden_frame():
    """The write $6d70 would have made once, made again every frame — which is what carries the
    record with the platform rather than leaving it where it landed."""
    what = "actor_behavior_type54 carrying"
    pokes = _moving_platform_pokes(what, {ACTOR + FIELD_22: bytes([1 << RIDING_BIT])}, ridden=1)

    info = _run_handler("actor_behavior_type54", what, pokes)
    written = program_writes(info)
    top = (MOVER_Y + PLATFORM_STEP - PLATFORM_TOP) & 0xffff
    assert (written[FOLLOWED_DEFAULT + ACTOR_Y] << 8
            | written[FOLLOWED_DEFAULT + ACTOR_Y + 1]) == top, (
        f"{what}: the rider was not snapped to the platform's new top")


def test_slot55_carries_the_rider_sideways_by_its_own_step():
    """Slot 55's counterpart, and the one place the two bodies really differ inside the ridden arm:
    54 snaps a y it computes, 55 ADDS the same two pixels to the rider's x."""
    what = "actor_behavior_type55 carrying"
    pokes = _moving_platform_pokes(what, {ACTOR + FIELD_22: bytes([1 << RIDING_BIT])}, ridden=1)
    rider_x = _image_word(MOVER_ROW + BAND_LEFT)

    info = _run_handler("actor_behavior_type55", what, pokes)
    written = program_writes(info)
    expected = (MOVER_X - rider_x + 1 + PLATFORM_STEP) & 0xffff
    assert (written[FOLLOWED_DEFAULT + ACTOR_X] << 8
            | written[FOLLOWED_DEFAULT + ACTOR_X + 1]) == expected


def test_slot56_sinks_while_it_is_ridden_and_rises_when_it_is_not():
    """No direction bit and no limit: 24(a0) counts UP by one per ridden frame and back down per
    free one, and the platform moves WB_ACTOR_PLATFORM_STEP either way."""
    sunk = 3
    ridden = _moving_platform_pokes("actor_behavior_type56 sinking",
                             {ACTOR + FIELD_22: bytes([1 << RIDING_BIT]),
                              ACTOR + FIELD_24: word(sunk)}, ridden=1)
    info = _run_handler("actor_behavior_type56", "actor_behavior_type56 sinking", ridden)
    written = program_writes(info)
    assert (written[ACTOR + FIELD_24] << 8 | written[ACTOR + FIELD_24 + 1]) == sunk + 1
    assert (written[ACTOR + ACTOR_Y] << 8
            | written[ACTOR + ACTOR_Y + 1]) == MOVER_Y + PLATFORM_STEP

    free = _moving_platform_pokes("actor_behavior_type56 rising", {ACTOR + FIELD_24: word(sunk)})
    info = _run_handler("actor_behavior_type56", "actor_behavior_type56 rising", free)
    written = program_writes(info)
    assert (written[ACTOR + FIELD_24] << 8 | written[ACTOR + FIELD_24 + 1]) == sunk - 1
    assert (written[ACTOR + ACTOR_Y] << 8
            | written[ACTOR + ACTOR_Y + 1]) == MOVER_Y - PLATFORM_STEP


def test_slot56_at_rest_only_offers_the_catch():
    """`tst.w 24(a0) / beq` — a platform that has not sunk does not rise, so the frame is one call
    to actor_platform_carry_followed and nothing else."""
    what = "actor_behavior_type56 at rest"
    pokes = _moving_platform_pokes(what, {ACTOR + FIELD_24: word(0)})

    info = _run_handler("actor_behavior_type56", what, pokes)
    written = program_writes(info)
    assert ACTOR + FIELD_24 not in written, f"{what}: the cursor moved with nothing to unwind"


# --- slot 51: the one-way switch ---------------------------------------------------------------------
# Its three raising arms and its falling one. The overlap mask is driven through the FOLLOWED
# record's own sprite and position, which is test_behavior.py's model of $5c6e above.
TYPE51_SPRITE = wb("ACTOR_TYPE51_SPRITE")


# The ground every walking case stands on: the record sits at STAND_Y, whose row is SOLID, while the
# row the two probes read (`(y - 1) asr.w #4`, one above it) is CLEAR. That is what separates the
# three things a keyed map would tangle together — the settle LANDS (so the record keeps
# WB_ACTOR_FLAG_SUPPORTED_BIT), the step is NOT blocked, and the rows below are solid so neither
# actor_toggle_side_flag nor actor_hop_or_flip_side reacts to a drop.
STAND_Y = 0x0080
STAND_ROW = STAND_Y >> MAP_CELL_SHIFT
# The level's right edge, seeded WIDE. actor_step_right_against_map clamps at
# WB_BG_SCROLL_LIMIT_X + WB_BG_SCROLL_LIMIT_BIAS and reports the clamp as BLOCKED, so a record left
# on a zero limit word is "blocked" wherever it stands — which is not the thing any case below is
# about.
SCROLL_LIMIT_X = wb("BG_SCROLL_LIMIT_X")
WIDE_LEVEL = 0x0800
# A row is DEFAULT_STRIDE bytes and no wider: a loop past that runs into the NEXT row's
# cells and quietly unpicks the row above it, which is how this seeding was first wrong.
GROUND_COLUMNS = DEFAULT_STRIDE


def _stand_on_ground(pokes, rows=3):
    for row in range(STAND_ROW, STAND_ROW + rows):
        for column in range(GROUND_COLUMNS):
            pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
                  + DEFAULT_STRIDE * row] = bytes([TILE_BLOCK])
    for column in range(GROUND_COLUMNS):
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 1)] = bytes([0])
    return pokes


def _clear_ground(pokes, rows=6):
    """...and the same window with NOTHING in it, for the cases about a record that does not land."""
    for row in range(STAND_ROW - 1, STAND_ROW + rows):
        for column in range(GROUND_COLUMNS):
            pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
                  + DEFAULT_STRIDE * row] = bytes([0])
    return pokes


def _type51_pokes(what, fields=None, ground=True):
    """A slot-51 record clear of the followed one, with the map seeded so a step can be taken or
    refused by a tile the case chooses."""
    salt = case_salt(what)
    base = {ACTOR + ACTOR_TYPE: word(51), ACTOR + HALF_WIDTH: word(4),
            ACTOR + SIZE_SECOND: word(8), ACTOR + ACTOR_X: word(0x0100),
            ACTOR + ACTOR_Y: word(STAND_Y), ACTOR + ACTOR_FLAGS: bytes([0]),
            ACTOR + FLAGS2: bytes([0]), ACTOR + SPEED: bytes([0]),
            # Far away and on a sprite no arm of $5c6e runs for, so the mask comes back zero.
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0600), FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0), FOLLOWED_DEFAULT + HALF_WIDTH: word(4),
            FOLLOWED_DEFAULT + SIZE_SECOND: word(8), FOLLOWED_DEFAULT + FLAGS2: bytes([0]),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0]),
            SCROLL_LIMIT_X: word(WIDE_LEVEL)}
    pokes = _tier_pokes(salt, leaf.overlay(base, fields or {}))
    pokes.update(map_pokes(salt))
    return _stand_on_ground(pokes) if ground else _clear_ground(pokes)


def test_slot51_walks_until_the_map_stops_it():
    """A clear step leaves bit 0 of 9(a0) DOWN and publishes WB_ACTOR_TYPE51_SPRITE; the byte
    `tst.b d0` reads is the probe's outcome, and only a BLOCKED one raises the bit."""
    what = "actor_behavior_type51 walking"
    pokes = _type51_pokes(what)

    info = _run_handler("actor_behavior_type51", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_SPRITE] << 8
            | written[ACTOR + ACTOR_SPRITE + 1]) == TYPE51_SPRITE
    assert ACTOR + FLAGS2 not in written, f"{what}: the switch was thrown by an unblocked step"


def test_slot51_throws_its_switch_on_a_blocked_step():
    """The tile the probe refuses to walk into, one cell ahead of the record's right edge."""
    what = "actor_behavior_type51 blocked"
    pokes = _type51_pokes(what)
    for column in range(GROUND_COLUMNS):
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 1)] = bytes([TILE_BLOCK])

    info = _run_handler("actor_behavior_type51", what, pokes)
    assert program_writes(info)[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: a blocked step did not raise bit 0")


def test_slot51_writes_its_own_inline_damage_word_before_it_hurts_the_player():
    """The BODY arm, and the write no other case reaches: `move.b #$84,19(a0)` stamps an INLINE
    damage word over the record's own WB_ACTOR_TEMPLATE_SLOT — sign bit set, so actor_damage_followed
    reads the cost out of its low seven bits instead of indexing the template table.

    The followed record carries WB_ACTOR_FLAGS2_INVULNERABLE_BIT, which is the one state that makes
    that routine return having written NOTHING — so the write set here is slot 51's own three bytes
    and the damage path's own battery keeps its arithmetic. (The sweep found this hole:
    `constant/type51-damage` survived without it.)
    """
    what = "actor_behavior_type51 body overlap"
    x, y = 0x0100, STAND_Y
    pokes = _type51_pokes(what, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        ACTOR + TEMPLATE_SLOT: bytes([0]),
        # Both footprints on the same point, and a sprite outside the strike and point bands so the
        # mask comes back with bit 1 alone.
        FOLLOWED_DEFAULT + ACTOR_X: word(x), FOLLOWED_DEFAULT + ACTOR_Y: word(y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0),
        FOLLOWED_DEFAULT + FLAGS2: bytes([1 << INVULNERABLE_BIT])})

    info = _run_handler("actor_behavior_type51", what, pokes)
    expected = {ACTOR + TEMPLATE_SLOT: CONTACT_DAMAGE,
                ACTOR + FLAGS2: 1 << FLAGS2_BIT_0,
                ACTOR + FIELD_30: ST_BYTE}
    _assert_writes(info, expected, what)


def test_slot51_frees_its_slot_the_frame_it_is_supported_again():
    """The falling arm: actor_fall_and_settle, actor_hop_ascend_step, and — with bit 2 of 8(a0) up
    — the free marker and bit 0 back down. The bit is read AFTER the settle, so a landing this same
    frame is what ends the record."""
    what = "actor_behavior_type51 landing"
    pokes = _type51_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                 ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type51", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8 | written[ACTOR + ACTOR_X + 1]) == FREE_MARKER
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0)


def test_slot51_that_is_still_falling_keeps_its_slot():
    """The other side of that `beq`: an unsupported record is left to fall, and the x word it would
    have been freed with is untouched."""
    what = "actor_behavior_type51 still falling"
    pokes = _type51_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                 ACTOR + ACTOR_FLAGS: bytes([1 << FALLING_BIT])}, ground=False)

    info = _run_handler("actor_behavior_type51", what, pokes)
    assert ACTOR + ACTOR_X not in program_writes(info), f"{what}: the slot was freed mid-air"


# --- slots 2..6: the live arms -----------------------------------------------------------------------
def _walk_pokes_for(what, slot, fields=None, ground=True):
    """A monster of `slot`'s type on ACTOR, out of every contact test's reach: no flash timer, no
    shot in the high pool (the tables are keyed but every record's x is a free marker here), and a
    followed record whose sprite runs none of $5c6e's three arms."""
    salt = case_salt(what)
    base = {ACTOR + ACTOR_TYPE: word(slot), ACTOR + HALF_WIDTH: word(4),
            ACTOR + SIZE_SECOND: word(8), ACTOR + ACTOR_X: word(0x0100),
            ACTOR + ACTOR_Y: word(STAND_Y), ACTOR + ACTOR_FLAGS: bytes([0]),
            ACTOR + FLAGS2: bytes([0]), ACTOR + FIELD_18: bytes([0]),
            ACTOR + FIELD_30: bytes([0x10]), ACTOR + FIELD_31: bytes([0]),
            ACTOR + SPEED: bytes([0]),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0600), FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0x0100),
            FOLLOWED_DEFAULT + HALF_WIDTH: word(4), FOLLOWED_DEFAULT + SIZE_SECOND: word(8),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0]), FOLLOWED_DEFAULT + FLAGS2: bytes([0])}
    for high in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        base[_record(TABLE_DEFAULT, high) + ACTOR_X] = word(FREE_MARKER)
    base[SCROLL_LIMIT_X] = word(WIDE_LEVEL)
    pokes = _tier_pokes(salt, leaf.overlay(base, fields or {}))
    pokes.update(map_pokes(salt))
    return _stand_on_ground(pokes) if ground else _clear_ground(pokes)


@pytest.mark.parametrize("followed_x,side,frames", [
    (0x0600, 0, "ACTOR_TYPE02_WALK_RIGHT"),
    (0x0010, 1 << SIDE_BIT, "ACTOR_TYPE02_WALK_LEFT"),
], ids=["followed-right", "followed-left"])
def test_slot02_faces_the_default_record_and_takes_no_step(followed_x, side, frames):
    """`move.w $9aec.l,d1` — the followed record's x read ABSOLUTE, so the facing follows the
    DEFAULT record. And the live arm moves nothing: only actor_fall_and_settle can, and the record
    here is already supported."""
    what = f"actor_behavior_type02 followed at {followed_x:#06x}"
    pokes = _walk_pokes_for(what, 2, {FOLLOWED_DEFAULT + ACTOR_X: word(followed_x),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type02", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT) == side, (
        f"{what}: the side flag is not what the absolute read of $9aec gives")
    assert (written[ACTOR + ACTOR_SPRITE] << 8
            | written[ACTOR + ACTOR_SPRITE + 1]) == _image_word(wb(frames))
    assert ACTOR + ACTOR_X not in written, f"{what}: the live arm stepped, which it does not"


def test_slot02_faces_the_default_record_even_while_the_mode_flag_names_the_other():
    """The correction as a case: WB_STATE_FLAG_A32 up, the two followed records on OPPOSITE sides,
    and the facing follows the default one — where actor_set_side_flag would follow the other."""
    what = "actor_behavior_type02 a32 up"
    pokes = _walk_pokes_for(what, 2, {FLAG_A32: word(0xffff),
                                      FOLLOWED_DEFAULT + ACTOR_X: word(0x0010),
                                      FOLLOWED_A32 + ACTOR_X: word(0x0600),
                                      FOLLOWED_A32 + ACTOR_Y: word(0x0600),
                                      FOLLOWED_A32 + ACTOR_SPRITE: word(0x0100),
                                      FOLLOWED_A32 + HALF_WIDTH: word(4),
                                      FOLLOWED_A32 + SIZE_SECOND: word(8),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type02", what, pokes)
    assert program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: it followed the a32 record, so the absolute read was not reproduced")


def test_slot03_turns_when_its_countdown_runs_out():
    """30(a0) at zero reloads WB_ACTOR_TYPE03_TURN_FRAMES and `bchg`es the side flag — the first of
    the two ways this monster turns round."""
    what = "actor_behavior_type03 turning"
    pokes = _walk_pokes_for(what, 3, {ACTOR + FIELD_30: bytes([0]),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type03", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_30] == wb("ACTOR_TYPE03_TURN_FRAMES")
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: the side flag did not flip"


@pytest.mark.parametrize("sprite", [0x0100, 0x0007], ids=["sprite-0100", "sprite-0007"])
def test_slot03s_left_step_carries_the_settles_leftover_high_byte(sprite):
    """THE `move.b #$2,d7` ASYMMETRY, as a case, and the reason map.h now hands d7 back.

    On the LEFT arm the step is written into d7's low BYTE alone. Reaching that instruction, d7
    holds what actor_fall_and_settle left — and with WB_ACTOR_FLAG_MOVING_BIT up that routine
    returns at $1380 without touching the register, so what is in it is $5c6e's `move.w 6(a1),d7`,
    the FOLLOWED RECORD'S SPRITE ID, over the long $23b6's `moveq #0,d7` cleared. The step is
    therefore `(sprite & $ff00) | 2`: two pixels for a sprite below $100 and 258 for one above it,
    from the same instruction. The RIGHT arm spells `move.w` and always steps two.
    """
    what = f"actor_behavior_type03 left step, followed sprite {sprite:#06x}"
    x = 0x0100
    pokes = _walk_pokes_for(what, 3, {
        ACTOR + ACTOR_X: word(x),
        ACTOR + ACTOR_FLAGS: bytes([(1 << SIDE_BIT) | (1 << MOVING_BIT)]),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(sprite)})

    info = _run_handler("actor_behavior_type03", what, pokes)
    written = program_writes(info)
    stepped = (written[ACTOR + ACTOR_X] << 8) | written[ACTOR + ACTOR_X + 1]
    step = (sprite & 0xff00) | wb("ACTOR_TYPE03_WALK_STEP")
    half_width = 4
    # $10a2 parks x at 14(a0) when the probe `x - 14(a0) - d7` goes NEGATIVE, so a 258-pixel step
    # from here does not land 258 pixels along — it lands on the level's own left edge.
    expected = half_width if x - half_width - step < 0 else x - step
    assert stepped == expected, (
        f"{what}: the record stepped to {stepped:#06x}, not the {expected:#06x} a byte-wide "
        f"`move.b` over the settle's leftover d7 gives")


def test_slot03s_right_step_is_two_pixels_whatever_the_settle_left():
    """The control for the case above: the same seed on the other arm, where `move.w` replaces the
    whole low word, so the sprite id cannot reach the step."""
    what = "actor_behavior_type03 right step"
    x = 0x0100
    pokes = _walk_pokes_for(what, 3, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0x0100)})

    info = _run_handler("actor_behavior_type03", what, pokes)
    written = program_writes(info)
    stepped = (written[ACTOR + ACTOR_X] << 8) | written[ACTOR + ACTOR_X + 1]
    assert stepped == x + wb("ACTOR_TYPE03_WALK_STEP")


# 0x1e is the cursor that SEPARATES WB_ACTOR_TYPE04_HOVER_MASK from the sixteen-word one:
# every smaller offset steps the same under both, and 0x7e wraps to 0 under both. The sweep
# found it — `constant/type04-hover-mask` survived a table of 0, 2 and 0x7e.
@pytest.mark.parametrize("cursor", [0, 2, 0x1e, 0x7e], ids=lambda v: f"cursor{v:#04x}")
def test_slot04_hovers_on_its_own_delta_table(cursor):
    """30(a0) indexes 64 SIGNED words straight into 2(a0), and `andi.b #$7f` wraps over the whole
    table — so the last word steps the cursor back to zero."""
    what = f"actor_behavior_type04 hover cursor {cursor:#04x}"
    y = STAND_Y
    pokes = _walk_pokes_for(what, 4, {ACTOR + FIELD_30: bytes([cursor]),
                                      ACTOR + ACTOR_Y: word(y)})

    info = _run_handler("actor_behavior_type04", what, pokes)
    written = program_writes(info)
    delta = _image_word(wb("ACTOR_TYPE04_HOVER") + cursor)
    assert (written[ACTOR + ACTOR_Y] << 8 | written[ACTOR + ACTOR_Y + 1]) == (y + delta) & 0xffff
    assert written[ACTOR + FIELD_30] == (cursor + ANIM_FRAME_BYTES) & wb("ACTOR_TYPE04_HOVER_MASK")


def test_slot04_out_of_reach_hovers_and_nothing_else():
    """`bsr $67f8 / tst.w d0 / bmi` — beyond WB_ACTOR_CHASE_REACH the whole chase, including its
    animation, is skipped, and the frame is the hover alone."""
    what = "actor_behavior_type04 out of reach"
    pokes = _walk_pokes_for(what, 4)

    info = _run_handler("actor_behavior_type04", what, pokes)
    written = program_writes(info)
    assert ACTOR + FIELD_18 not in written, f"{what}: the chase animation ran out of reach"
    assert ACTOR + ACTOR_Y in written, f"{what}: the hover did not run"


def test_slot04_level_with_the_followed_record_animates_without_stepping():
    """`cmp.w (a1),d0 / beq` — equal x words skip the two probe calls but not the frame list."""
    what = "actor_behavior_type04 level"
    x = 0x0100
    pokes = _walk_pokes_for(what, 4, {FOLLOWED_DEFAULT + ACTOR_X: word(x),
                                      FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600),
                                      ACTOR + ACTOR_X: word(x)})

    info = _run_handler("actor_behavior_type04", what, pokes)
    written = program_writes(info)
    assert ACTOR + FIELD_18 in written, f"{what}: the chase animation did not run"
    assert ACTOR + ACTOR_X not in written, f"{what}: it stepped while already level"


def test_slot05_hops_when_the_ground_says_to():
    """actor_hop_or_flip_side over the step's two results: a blocked step onto a cell with a clear
    one above it launches the record at WB_ACTOR_HOP_SPEED instead of turning it round."""
    what = "actor_behavior_type05 hopping"
    pokes = _walk_pokes_for(what, 5, {ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})
    # A block in the PROBE's row with a clear cell above it: `btst #0,d1`'s step-up.
    for column in range(GROUND_COLUMNS):
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 1)] = bytes([TILE_BLOCK])
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 2)] = bytes([0])

    info = _run_handler("actor_behavior_type05", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + SPEED] == wb("ACTOR_HOP_SPEED"), (
        f"{what}: the record was not launched — 11(a0) is {written.get(ACTOR + SPEED)}")


def test_slot06_counts_its_reload_down_and_walks():
    """30(a0) nonzero clears 31(a0), ticks the countdown and goes straight to the walk — no reach
    test, no charge, no throw."""
    what = "actor_behavior_type06 reloading"
    pokes = _walk_pokes_for(what, 6, {ACTOR + FIELD_30: bytes([5]),
                                      ACTOR + FIELD_31: bytes([0xff]),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type06", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_30] == 4 and written[ACTOR + FIELD_31] == 0
    assert ACTOR + FIELD_29 not in written, f"{what}: it saved its flag byte on a reloading frame"


def test_slot06_out_of_reach_restores_the_flag_byte_it_saved():
    """`move.b 8(a0),29(a0)` then, on the out-of-reach arm, `move.b 29(a0),8(a0)` — so the save is
    visible in 29(a0) and the flag byte comes back to what it was, bar the `bchg` at the end."""
    what = "actor_behavior_type06 out of reach"
    flags = 1 << SUPPORTED_BIT
    pokes = _walk_pokes_for(what, 6, {ACTOR + FIELD_30: bytes([0]),
                                      ACTOR + FIELD_31: bytes([0]),
                                      ACTOR + ACTOR_FLAGS: bytes([flags])})

    info = _run_handler("actor_behavior_type06", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_31] == 0 and written[ACTOR + FIELD_30] == wb("ACTOR_TYPE06_RELOAD")
    # The ROUND TRIP, not the seeded byte: actor_fall_and_settle runs BEFORE the save, so what is
    # saved is the flag byte as that routine left it — and what comes back is that byte with the
    # `bchg` at the foot of the restore applied.
    assert written[ACTOR + ACTOR_FLAGS] == written[ACTOR + FIELD_29] ^ (1 << SIDE_BIT), (
        f"{what}: 8(a0) came back {written[ACTOR + ACTOR_FLAGS]:#04x} against the saved "
        f"{written[ACTOR + FIELD_29]:#04x}")


def test_slot06_that_is_not_supported_holds_a_standing_frame_and_returns():
    """The arm with NO restore in it: `btst #2,8(a0) / beq` publishes one of two sprites and ends
    the frame, so whatever actor_start_motion_at_speed wrote to 8(a0) stays written."""
    what = "actor_behavior_type06 airborne"
    pokes = _walk_pokes_for(what, 6, {ACTOR + FIELD_30: bytes([0]),
                                      ACTOR + FIELD_31: bytes([0xff]),
                                      ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type06", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_SPRITE] << 8
            | written[ACTOR + ACTOR_SPRITE + 1]) == wb("ACTOR_TYPE06_SPRITE_RIGHT")
    assert ACTOR + FIELD_18 not in written, f"{what}: the walk ran on the standing arm"


def test_slot06_throws_a_shot_into_the_high_pool():
    """The spawn: actor_alloc_slot_high's record filled from the thrower's own longword, offset
    WB_ACTOR_TYPE06_SHOT_AHEAD and up WB_ACTOR_TYPE06_SHOT_UP, stamped with the shot type and the
    packed WB_ACTOR_TYPE06_SHOT_SIZE."""
    what = "actor_behavior_type06 throwing"
    x, y = 0x0100, STAND_Y
    pokes = _walk_pokes_for(what, 6, {ACTOR + FIELD_30: bytes([0]),
                                      ACTOR + FIELD_31: bytes([0xff]),
                                      ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type06", what, pokes)
    written = program_writes(info)
    shot = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST)
    assert (written[shot + ACTOR_X] << 8
            | written[shot + ACTOR_X + 1]) == x + wb("ACTOR_TYPE06_SHOT_AHEAD")
    assert (written[shot + ACTOR_Y] << 8
            | written[shot + ACTOR_Y + 1]) == y - wb("ACTOR_TYPE06_SHOT_UP")
    assert (written[shot + ACTOR_TYPE] << 8
            | written[shot + ACTOR_TYPE + 1]) == wb("ACTOR_TYPE06_SHOT_TYPE")
    assert (written[shot + HALF_WIDTH] << 8 | written[shot + HALF_WIDTH + 1]) \
        == wb("ACTOR_TYPE06_SHOT_SIZE") >> 16


def test_slot06_with_the_high_pool_full_throws_nothing_and_still_restores():
    """`cmpa.l #$0,a1 / beq` — a failed allocation joins the out-of-reach arm at the restore, which
    is the third entrance to it."""
    what = "actor_behavior_type06 pool full"
    occupied = {_record(TABLE_DEFAULT, high) + ACTOR_X: word(0x1234)
                for high in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS)}
    pokes = _walk_pokes_for(what, 6, {**occupied,
                                      ACTOR + FIELD_30: bytes([0]),
                                      ACTOR + FIELD_31: bytes([0xff]),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type06", what, pokes)
    written = program_writes(info)
    shot = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST)
    assert shot + ACTOR_TYPE not in written, f"{what}: a shot was written into an occupied record"
    assert written[ACTOR + FIELD_30] == wb("ACTOR_TYPE06_RELOAD")


# --- the arms the mutation sweep found unreached ------------------------------------------------------
# Eight rows that exist because a mutant survived without them. Each names the mutant it closes, so a
# later reader can tell a case written for coverage from one written for a claim.
def test_slot02_recoils_while_it_dies():
    """`constant/type02-dead-step`: the death animation's own step, which no live-arm case reaches.
    Bit 3 of 8(a0) SET recoils RIGHT — the opposite arm to $2f22's, since the bit says the followed
    record is to the LEFT."""
    what = "actor_behavior_type02 dying and recoiling"
    x = 0x0100
    pokes = _walk_pokes_for(what, 2, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                      ACTOR + ACTOR_FLAGS: bytes([(1 << SIDE_BIT)
                                                                  | (1 << SUPPORTED_BIT)]),
                                      ACTOR + ACTOR_X: word(x), ACTOR + FIELD_18: bytes([2])})

    info = _run_handler("actor_behavior_type02", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8
            | written[ACTOR + ACTOR_X + 1]) == x + wb("ACTOR_TYPE02_DEAD_STEP")
    assert (written[ACTOR + ACTOR_SPRITE] << 8 | written[ACTOR + ACTOR_SPRITE + 1]) \
        == _image_word(wb("ACTOR_TYPE02_DEAD_RIGHT") + 2)


def test_a_defeated_slot02_stands_still_while_it_dies():
    """The other side of that arm: with bit 3 of 9(a0) up the recoil is skipped entirely, so the
    animation plays on a record that does not move."""
    what = "actor_behavior_type02 dying, already defeated"
    pokes = _walk_pokes_for(what, 2, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + ACTOR_FLAGS: bytes([(1 << SIDE_BIT) | (1 << SUPPORTED_BIT)]),
        ACTOR + FIELD_18: bytes([2])})

    info = _run_handler("actor_behavior_type02", what, pokes)
    assert ACTOR + ACTOR_X not in program_writes(info), f"{what}: a defeated record recoiled"


def test_slot02_faces_the_record_it_is_LEVEL_with_by_the_inclusive_arm():
    """`branch/type02-facing`: `cmp.w d0,d1 / bgt` is STRICT, so equal x words take the OTHER arm —
    the one that raises WB_ACTOR_FLAG_SIDE_BIT — where a `bge` would clear it."""
    what = "actor_behavior_type02 level with the followed record"
    x = 0x0100
    pokes = _walk_pokes_for(what, 2, {ACTOR + ACTOR_X: word(x),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                      FOLLOWED_DEFAULT + ACTOR_X: word(x),
                                      FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600)})

    info = _run_handler("actor_behavior_type02", what, pokes)
    assert program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: an equal x cleared the side flag, so the compare was read as inclusive")


def test_the_body_bit_is_answered_before_the_point_bit():
    """`branch/contact-order`: with BOTH bits of $5c6e's mask up, the handler damages the followed
    record and does NOT enter its own hit animation — the order the two `btst`s are written in."""
    what = "actor_behavior_type02 body and point together"
    x, y = 0x0100, STAND_Y
    pokes = _walk_pokes_for(what, 2, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        ACTOR + HALF_WIDTH: word(0x40), ACTOR + SIZE_SECOND: word(0x40),
        # Sprite WB_FOLLOWED_SPRITE_POINT_LO runs the POINT test, and the box above is wide enough
        # to hold both that point and the followed record's own footprint.
        FOLLOWED_DEFAULT + ACTOR_X: word(x), FOLLOWED_DEFAULT + ACTOR_Y: word(y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(POINT_LO),
        FOLLOWED_DEFAULT + FLAGS2: bytes([1 << INVULNERABLE_BIT])})

    info = _run_handler("actor_behavior_type02", what, pokes)
    written = program_writes(info)
    assert ACTOR + FLAGS2 not in written, (
        f"{what}: the record entered its own hit animation, so the point bit was read first")


def test_slot03_retreats_from_a_record_it_is_LEVEL_with():
    """`boundary/type03-retreat` and `index/type03-followed` together: the death arm's compare is
    `cmp.w (a0),d0 / bge`, INCLUSIVE, and the record it compares against is the PUBLISHED table's
    followed slot rather than either absolute one."""
    what = "actor_behavior_type03 dying, level with the followed record"
    x = 0x0100
    followed = _record(TABLE_DEFAULT, FOLLOWED_SLOT)
    pokes = _walk_pokes_for(what, 3, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                      ACTOR + ACTOR_X: word(x),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                      ACTOR + FIELD_18: bytes([2]),
                                      followed + ACTOR_X: word(x)})

    info = _run_handler("actor_behavior_type03", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: an equal x took the other arm, so the compare was read as strict")
    assert (written[ACTOR + ACTOR_X] << 8
            | written[ACTOR + ACTOR_X + 1]) == x - wb("ACTOR_TYPE03_DEAD_STEP")
    assert (written[ACTOR + ACTOR_SPRITE] << 8 | written[ACTOR + ACTOR_SPRITE + 1]) \
        == _image_word(wb("ACTOR_TYPE03_DEAD_LEFT") + 2)


def _ridden_platform_pokes(what, direction, rider_flags=0, blocked=False):
    """A platform carrying the followed record, with the ride already established: the global word
    up, the record's own riding bit up, and the rider inside the band."""
    band_left = _image_word(MOVER_ROW + BAND_LEFT)
    pokes = _moving_platform_pokes(what, {
        ACTOR + FIELD_22: bytes([(1 << RIDING_BIT) | direction]),
        FOLLOWED_DEFAULT + ACTOR_X: word(MOVER_X - band_left + 1),
        FOLLOWED_DEFAULT + ACTOR_Y: word(MOVER_Y - PLATFORM_TOP),
        FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([rider_flags])}, ridden=1)
    if blocked:
        rider_x = MOVER_X - band_left + 1
        rider_y = (MOVER_Y - PLATFORM_TOP + PLATFORM_STEP) & 0xffff
        cell = (COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS
                + ((rider_x >> MAP_CELL_SHIFT) + DEFAULT_STRIDE * (rider_y >> MAP_CELL_SHIFT)))
        pokes[cell] = bytes([TILE_BLOCK])
        pokes[cell + 1] = bytes([TILE_BLOCK])
    return pokes


def test_slot54_checks_the_riders_cell_only_on_its_DOWNWARD_frames():
    """`branch/type54-direction`: the `btst #0,22(a0) / bne` in front of the call. Travelling BACK
    (up) the rider's cell is never read, so a solid one under it changes nothing."""
    for direction, expect_release in ((0, True), (1 << DIRECTION_BIT, False)):
        what = f"actor_behavior_type54 blocked rider, direction={direction:#04x}"
        pokes = _ridden_platform_pokes(what, direction, blocked=True)
        info = _run_handler("actor_behavior_type54", what, pokes)
        written = program_writes(info)
        released = (PLATFORM_RIDDEN in written
                    and (written[PLATFORM_RIDDEN] << 8 | written[PLATFORM_RIDDEN + 1]) == 0)
        assert released == expect_release, (
            f"{what}: the ride {'was not' if expect_release else 'was'} ended, against the "
            f"direction bit's own gate")


def test_slot54_lets_a_rider_under_its_own_power_go():
    """`order/type54-snap`: the release check really runs on the ridden arm — a rider with
    WB_ACTOR_FLAG_MOVING_BIT up loses the ride even though it is still inside the band."""
    what = "actor_behavior_type54 rider moving under its own power"
    pokes = _ridden_platform_pokes(what, 0, rider_flags=1 << MOVING_BIT)

    info = _run_handler("actor_behavior_type54", what, pokes)
    written = program_writes(info)
    assert (written[PLATFORM_RIDDEN] << 8 | written[PLATFORM_RIDDEN + 1]) == 0, (
        f"{what}: the release check did not run")
    assert not written[ACTOR + FIELD_22] & (1 << RIDING_BIT)


# --- the death WRAP, the defeat transfer and the STRUCK arm -------------------------------------------
# The three exits the cases above stop short of. Each of them leaves the behaviour tier: the wrap
# hands the record to actor_defeat_and_score and the struck arm to actor_damage_template_hitpoints,
# and both of those write across the HUD, the sound module, the text request and the template table.
#
# THEIR WRITE SETS ARE BOUNDED, NOT STATED, and this is the one place in the file that is true of
# something other than a map probe: modelling either routine here would be a second copy of
# test_actor.py's model, which is the copy that could disagree while both batteries stayed green.
# What pins the VALUES is the differential itself — leaf.run compares the whole image either way —
# and what this band adds is "and nothing outside these".
from test_actor import (BCD_SCORE, EFFECT_RECORD_LIST, METER_VALUE, SLOT_BBC0,   # noqa: E402
                        SPAWN_HITPOINTS, SPAWN_RECORD_BYTES, SPAWN_TYPE, TABLE_PTR,
                        TEMPLATE_SLOTS, TEMPLATE_TABLE, TEXT_REQUEST, _model_damage_template,
                        _model_defeat, _template_band)
from test_actor import DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B                    # noqa: E402

# THE ONE SPAWN TYPE THESE CASES MAY USE. `lsl.w #2,d2` inside actor_defeat_and_score leaves the X
# flag holding the type's bit 14, and bcd_add_score_bd70 folds the caller's X into its lowest digit
# pair — an entry state the oracle cannot be given, which actor.h registers and test_actor.py's own
# defeat cases refuse. A keyed template word would carry that bit at random, so every template in
# the band below is seeded with a type that does not.
SAFE_SPAWN_TYPE = 4
TEMPLATE_POOL = 0x40

TEMPLATE_BAND_BYTES = TEMPLATE_SLOTS * SPAWN_RECORD_BYTES


def _foreign_band(image, own, model):
    """The addresses a foreign tail may write, taken from test_actor.py's OWN models rather than
    listed here — a hand-written list of regions would be the second copy that could disagree with
    the battery owning them while both stayed green.

    ``own`` is what the handler itself writes BEFORE the tail jump, applied to a copy first so the
    model reads the image the routine it models really would (the `bset #0,9(a0)` is one of that
    routine's inputs). ``model`` names the tail: the damage path composes with the SFX trigger's
    write set, the defeat composes its own.
    """
    after = bytearray(image)
    for addr, value in own.items():
        after[addr] = value
    named = dict(own)
    if model == "damage-template":
        named.update(_model_damage_template(after, ACTOR)[2])
        named.update(_sfx_bytes(after, DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B))
    else:
        named.update(_model_defeat(after, ACTOR)[2])
    return merge_bands(named) + HANDLER_WRITE_BAND


def _band_slot_pokes(what, slot, fields=None, ground=True):
    """`_walk_pokes_for` plus the TEMPLATE environment the two damage paths and the defeat read:
    a table of eight records with a hit-point pool, the published pointer to it, and the two HUD
    charge slots emptied so neither path spends one (which keeps the arms this case is about the
    only thing moving)."""
    salt = case_salt(what)
    pokes = _walk_pokes_for(what, slot, fields, ground=ground)
    _template_band(salt, TEMPLATE_TABLE, TEMPLATE_SLOTS, pokes)
    pokes[TABLE_PTR] = longword(TEMPLATE_TABLE)
    # EVERY template of the band, not just the one the slot byte names: the two damage paths and the
    # defeat index it three different ways, so seeding one record would leave a wrongly-indexed port
    # reading keyed noise instead of a number the case chose. test_actor.py's own seeding says so.
    for template in range(TEMPLATE_SLOTS):
        record = TEMPLATE_TABLE + template * SPAWN_RECORD_BYTES
        pokes[record + SPAWN_TYPE] = word(SAFE_SPAWN_TYPE)
        pokes[record + SPAWN_HITPOINTS] = word(TEMPLATE_POOL)
    pokes[SLOT_BBC0] = word(0)
    pokes[wb("HUD_SLOT_BBBE")] = word(0)
    pokes[EFFECT_RECORD_LIST] = word(0)
    pokes[BCD_SCORE] = longword(0)
    return pokes


def _run_band_handler(slot, what, pokes, model):
    """One band-slot frame whose arm leaves the tier. ``own`` is the two writes the STRUCK arm makes
    before its tail jump; the wrap reaches actor_defeat_and_score with the record as it stands."""
    image = harness.make_image(pokes)
    own = ({ACTOR + FLAGS2: image[ACTOR + FLAGS2] | (1 << FLAGS2_BIT_0), ACTOR + FIELD_18: 0}
           if model == "damage-template" else {})
    return _run_handler(f"actor_behavior_type{slot:02d}", what, pokes,
                        band=_foreign_band(image, own, model))


# The cursor that sits on a table's LAST frame, so one more step wraps it to zero. Derived from the
# mask rather than stated, which is what keeps it right if a table's size is ever re-read.
LAST_FRAME = {ANIM16_MASK: ANIM16_MASK - 1, ANIM32_MASK: ANIM32_MASK - 1}
BAND_DEATH_MASK = {2: ANIM32_MASK, 3: ANIM16_MASK, 4: ANIM32_MASK, 5: ANIM16_MASK, 6: ANIM16_MASK}


@pytest.mark.parametrize("slot", MONSTER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_a_death_animation_that_wraps_without_the_defeated_bit_comes_back_to_life(slot):
    """The WRAP, on the arm that does NOT transfer: bit 0 of 9(a0) goes down and the record returns
    to its live handler next frame. Nothing outside the actor tables is written, which is what says
    actor_defeat_and_score did not run."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} death animation wrapping, not defeated"
    cursor = LAST_FRAME[BAND_DEATH_MASK[slot]]
    pokes = _band_slot_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                          ACTOR + FIELD_18: bytes([cursor]),
                                          ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the record is still in its death animation after the wrap")
    assert all(addr < TEMPLATE_TABLE for addr in written), (
        f"{what}: something outside the actor tables was written, so the defeat ran")


@pytest.mark.parametrize("slot", MONSTER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_a_death_animation_that_wraps_ON_the_defeated_bit_transfers_to_the_defeat(slot):
    """...and the arm that DOES. `bne.w $6bb8` is a tail jump, so actor_defeat_and_score's own `rts`
    returns to the handler's caller.

    AND THE SKIPPED STORE IS NOT OBSERVABLE HERE, which is worth saying rather than asserting: for
    slots 2, 3 and 4 the transfer jumps over the `move.b d0,18(a0)` below it, but the value that
    store would have written is the wrap's own ZERO and actor_defeat_and_score writes
    WB_ACTOR_FIELD_18 = 0 itself. Both readings leave the same byte, so no differential can separate
    them on this frame — ../STATUS.md carries it. What IS checked is that the defeat ran at all."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} death animation wrapping, defeated"
    cursor = LAST_FRAME[BAND_DEATH_MASK[slot]]
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + FIELD_18: bytes([cursor]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template was not touched, so the transfer into actor_defeat_and_score never "
        f"happened")
    # WHICH of the defeat's two exits it takes is that routine's own decision (the kill count
    # against the template's limit) and test_actor.py's cases own it. What this adds is the WRAP
    # itself: the cursor came back to zero, which is the frame the transfer hangs off.
    assert written[ACTOR + FIELD_18] == 0, (
        f"{what}: the cursor is {written[ACTOR + FIELD_18]:#04x}, so the animation did not wrap")


@pytest.mark.parametrize("slot", MONSTER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_struck_arm_enters_the_hit_animation_and_spends_the_templates_pool(slot):
    """The MONSTER_STRUCK arm, driven through $23b6's FLASH path: WB_FLASH_TIMER running with the
    followed record inside WB_ACTOR_FLASH_REACH is a hit with no projectile at all. The handler then
    raises bit 0 of 9(a0), zeroes the cursor and tail-jumps into actor_damage_template_hitpoints."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} struck by the flash"
    x = 0x0100
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_18: bytes([4]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        FLASH_TIMER: word(1), FOLLOWED_DEFAULT + ACTOR_X: word(x)})

    info = _run_band_handler(slot, what, pokes, "damage-template")
    written = program_writes(info)
    assert written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), f"{what}: the hit animation was not entered"
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the animation cursor was not zeroed"
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template's pool was not spent, so the tail jump never happened")


def test_slot06_faces_the_followed_record_before_it_takes_the_hit():
    """The one instruction slot 6 has in its struck arm that the other four do not: `bsr $67c2`
    between the two writes and the tail jump. Seeded with the followed record to the actor's LEFT,
    so the flag the call raises is a change the case can see."""
    what = "actor_behavior_type06 struck, facing first"
    x = 0x0100
    pokes = _band_slot_pokes(what, 6, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        FLASH_TIMER: word(1), FOLLOWED_DEFAULT + ACTOR_X: word(x - 1)})

    info = _run_band_handler(6, what, pokes, "damage-template")
    assert program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side flag was not raised, so actor_set_side_flag did not run")


# --- batch 31: slots 52 and 53, the gate below them, and the four rows above the platforms --------
# THE HEAD IS SHARED WITH SLOT 51 and the tails are not, so the contact arms are driven for BOTH new
# slots (the entry pin already says the two heads are the same bytes; these say the two cores agree
# about what they DO) and each slot's own move gets its own cases.
SWITCHED_SLOTS = (52, 53)
SWITCHED_HANDLERS = {52: "actor_behavior_type52", 53: "actor_behavior_type53"}


def _switched_pokes(what, slot, fields=None, ground=True):
    """A slot-52 or slot-53 record, seeded exactly as `_type51_pokes` seeds slot 51's — same
    geometry, same out-of-reach followed record, same map — so the three heads are compared on the
    same inputs rather than on three different ones."""
    return _type51_pokes(what, leaf.overlay({ACTOR + ACTOR_TYPE: word(slot)}, fields or {}),
                         ground=ground)


@pytest.mark.parametrize("slot", SWITCHED_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_switch_arm_frees_the_slot_outright(slot):
    """WHERE 52 AND 53 PART FROM 51. All three open `btst #0,9(a0) / bne.w`, but slot 51's branch
    lands on a FALL and these two land on the exit — so a record that raised the bit last frame
    gives its slot back with nothing else run at all. Slot 53 also lowers its live word here."""
    name = SWITCHED_HANDLERS[slot]
    what = f"{name} switch already up"
    pokes = _switched_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + FLAGS2: 0, ACTOR + ACTOR_X: FREE_MARKER >> 8,
                ACTOR + ACTOR_X + 1: FREE_MARKER & 0xff}
    if slot == 53:
        # ...and it was RAISED first, on the handler's own first instruction, so both writes land.
        _put(expected, TYPE53_ALIVE, 0)
    _assert_writes(info, expected, what)


STRIKE_ACTOR_X, STRIKE_ACTOR_Y = 0x0100, STAND_Y


def _strike_geometry():
    """Where a record has to stand for bit 0 of the overlap mask: inside the small box in FRONT of
    the followed record, which is WB_ACTOR_STRIKE_BOX_NEAR..FAR ahead of it and
    WB_ACTOR_STRIKE_BOX_TOP above. Standing ON the followed record reaches bit 1 and not bit 0,
    which is what the assertion in each case guards."""
    return {ACTOR + ACTOR_X: word(STRIKE_ACTOR_X), ACTOR + ACTOR_Y: word(STRIKE_ACTOR_Y),
            FOLLOWED_DEFAULT + ACTOR_X: word(STRIKE_ACTOR_X - STRIKE_BOX_NEAR + 1),
            FOLLOWED_DEFAULT + ACTOR_Y: word(STRIKE_ACTOR_Y + STRIKE_BOX_TOP - 4),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(STRIKE_LO),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0])}


@pytest.mark.parametrize("slot", SWITCHED_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_switch_arm_is_reached_by_a_STRIKE_and_stuns(slot):
    """Bit 0 of the overlap mask: the switch goes up and the frame tail-jumps into
    actor_stun_followed, so the write set is the record's flag byte plus the stun's own."""
    name = SWITCHED_HANDLERS[slot]
    what = f"{name} strike"
    pokes = _switched_pokes(what, slot, _strike_geometry())
    image = harness.make_image(pokes)
    assert _model_overlap_mask(image, ACTOR, FOLLOWED_DEFAULT) & (1 << STRIKE_BIT), (
        f"{what}: the seed does not reach bit 0, so this case would drive the body arm instead")
    band = _handler_band(name) + merge_bands(_sfx_bytes(image, STUN_SFX, SND_CHANNEL_A))

    info = _run_handler(name, what, pokes, band=band)
    written = program_writes(info)
    assert written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), f"{what}: the switch was not thrown"
    assert FOLLOWED_DEFAULT + FIELD_29 in written, f"{what}: the stun's step count was not stamped"
    assert written[FOLLOWED_DEFAULT + FIELD_22] == 0, f"{what}: the stun did not clear 22(a1)"


@pytest.mark.parametrize("slot", SWITCHED_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_switch_arm_is_reached_by_a_BODY_overlap_and_spends_the_inline_damage(slot):
    """Bit 1: the same three writes slot 51 makes — the inline damage word over the record's own
    WB_ACTOR_TEMPLATE_SLOT, the switch, and WB_ACTOR_ST_BYTE into the countdown. The followed
    record is INVULNERABLE, so actor_damage_followed returns having written nothing and the write
    set here is the handler's alone."""
    name = SWITCHED_HANDLERS[slot]
    what = f"{name} body overlap"
    x, y = 0x0100, STAND_Y
    pokes = _switched_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y), ACTOR + TEMPLATE_SLOT: bytes([0]),
        FOLLOWED_DEFAULT + ACTOR_X: word(x), FOLLOWED_DEFAULT + ACTOR_Y: word(y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0),
        FOLLOWED_DEFAULT + FLAGS2: bytes([1 << INVULNERABLE_BIT])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + TEMPLATE_SLOT: CONTACT_DAMAGE, ACTOR + FLAGS2: 1 << FLAGS2_BIT_0,
                ACTOR + FIELD_30: ST_BYTE}
    if slot == 53:
        _put(expected, TYPE53_ALIVE, TYPE53_ALIVE_SET)
    _assert_writes(info, expected, what)


# --- slot 52's own frame -------------------------------------------------------------------------
@pytest.mark.parametrize("step", [1, 4, 0x7f], ids=lambda v: f"step{v:#04x}")
def test_slot52_walks_by_its_own_countdown_BYTE_and_not_a_constant(step):
    """`moveq #0,d7 / move.b 30(a0),d7` — the step is WB_ACTOR_FIELD_30, so the same byte the damage
    arm stamps WB_ACTOR_ST_BYTE into is what a live record walks by. A handler that spelt a constant
    here would move the same distance for every seed."""
    what = f"actor_behavior_type52 walking {step} px"
    x = 0x0100
    pokes = _switched_pokes(what, 52, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([step]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type52", what, pokes)
    written = program_writes(info)
    moved = (written[ACTOR + ACTOR_X] << 8) | written[ACTOR + ACTOR_X + 1]
    assert moved == x + step, f"{what}: the record moved to {moved:#06x}, not {x + step:#06x}"


def test_slot52_discards_the_probes_blocked_answer():
    """Nothing follows the `bsr` — no `tst.b d0` — so a wall only stops this record by refusing to
    move it. The switch stays DOWN where slot 51's would have gone up on the same map."""
    what = "actor_behavior_type52 blocked"
    pokes = _switched_pokes(what, 52, {ACTOR + FIELD_30: bytes([4]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)
    for column in range(GROUND_COLUMNS):
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 1)] = bytes([TILE_BLOCK])

    info = _run_handler("actor_behavior_type52", what, pokes)
    assert not program_writes(info).get(ACTOR + FLAGS2, 0) & (1 << FLAGS2_BIT_0), (
        f"{what}: a blocked step threw the switch, which is slot 51's behaviour and not this one's")


@pytest.mark.parametrize("speed", [6, 1], ids=["mid-hop", "last-frame-of-the-hop"])
def test_slot52_hops_and_the_two_calls_keep_their_ORDER(speed):
    """THE ORDER OF `bsr $1334 / bsr $501a`, which took two sweep rounds to pin.

    The two are MUTUALLY EXCLUSIVE on one bit — actor_fall_and_settle returns at once while
    WB_ACTOR_FLAG_MOVING_BIT is up and actor_hop_ascend_step returns at once while it is down — so
    on almost every frame the order really is free, which is why the first `order/type52-settle-
    after-step` mutant survived a case that merely raised the bit. The frame that separates them is
    the LAST one of a hop: the ascent CLEARS the bit when the speed runs out, so a settle placed
    after it would find the record newly still and fall it. `speed=1` is that frame."""
    what = f"actor_behavior_type52 hopping at speed {speed}"
    pokes = _switched_pokes(what, 52, {ACTOR + FIELD_30: bytes([2]),
                                       ACTOR + SPEED: bytes([speed]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                            ground=False)

    info = _run_handler("actor_behavior_type52", what, pokes)
    written = program_writes(info)
    assert ACTOR + ACTOR_Y in written, f"{what}: neither the settle nor the ascent moved the record"
    if speed == 1:
        assert not written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT), (
            f"{what}: the hop did not end, so this row does not separate the two orders")
        assert written[ACTOR + SPEED] == 1, f"{what}: the ended hop did not reload the speed"
    else:
        assert written[ACTOR + SPEED] == speed - 1, (
            f"{what}: the ascent did not step the speed, so the hop never ran")


def test_slot52_frees_itself_the_frame_it_is_SUPPORTED():
    """The tail `btst #2,8(a0)` — read AFTER the settle, so a record that has just landed gives its
    slot back on the same frame, which is the opposite sense to slot 51's falling arm."""
    what = "actor_behavior_type52 landing"
    pokes = _switched_pokes(what, 52, {ACTOR + FIELD_30: bytes([2]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_handler("actor_behavior_type52", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8 | written[ACTOR + ACTOR_X + 1]) == FREE_MARKER
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0)


# The cursor values that separate an EIGHT-word table from every other stride in this file: the two
# ends, the byte before the wrap, the byte at it, and two that leave the table entirely (the read is
# unmasked — `andi.w #$f` runs AFTER it).
TYPE52_CURSORS = [0, 1, 2, TYPE52_MASK - 1, TYPE52_MASK + 1, 0x20, 0xfe]


@pytest.mark.parametrize("cursor", TYPE52_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot52_publishes_the_frame_its_cursor_names_and_then_wraps(cursor):
    """The frame comes out of the IMAGE, so a case that transcribed the eight words would pass on
    its own transcription — and the cursor is read BEFORE the mask, which is what the two rows past
    the table are here to say."""
    what = f"actor_behavior_type52 cursor {cursor:#04x}"
    pokes = _switched_pokes(what, 52, {ACTOR + FIELD_18: bytes([cursor]),
                                       ACTOR + FIELD_30: bytes([2]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type52", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & TYPE52_MASK
    assert (written[ACTOR + ACTOR_SPRITE] << 8 | written[ACTOR + ACTOR_SPRITE + 1]) \
        == _image_word(TYPE52_FRAMES + cursor)


# --- slot 53's own frame -------------------------------------------------------------------------
# WB_TILE_33_MODE is what decides whether the frame reaches its own tail at all: `bsr $d78` returns
# at once while it is SET and enters WB_PLAYER_STEP_BODY while it is clear.
TILE_33_MODE_SET = 0xffff


@pytest.mark.parametrize("side,delta", [(0, TYPE53_STEP), (1 << SIDE_BIT, -TYPE53_STEP)],
                         ids=["right", "left"])
def test_slot53_slides_a_fixed_step_and_counts_its_timer_down(side, delta):
    """`moveq #$8,d7` and `add.w d7,(a0)` / `sub.w d7,(a0)` — a step that is the same eight pixels
    whatever the record holds, which is where it differs from slot 52 above."""
    what = f"actor_behavior_type53 sliding side={side:#04x}"
    x, timer = 0x0100, 5
    pokes = _switched_pokes(what, 53, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + ACTOR_FLAGS: bytes([side]),
                                       TILE_33_MODE: word(TILE_33_MODE_SET)})

    info = _run_handler("actor_behavior_type53", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8 | written[ACTOR + ACTOR_X + 1]) == (x + delta) & 0xffff
    assert (written[ACTOR + ACTOR_SPRITE] << 8 | written[ACTOR + ACTOR_SPRITE + 1]) == TYPE53_SPRITE
    assert written[ACTOR + FIELD_30] == timer - 1
    assert written[TYPE53_ALIVE] << 8 | written[TYPE53_ALIVE + 1] == TYPE53_ALIVE_SET


def test_slot53_frees_itself_and_lowers_its_live_word_when_the_timer_runs_out():
    """`tst.b 30(a0) / beq` — the countdown is tested BEFORE it is decremented, so zero is the end
    and not $ff. The exit is the same three writes the switch arm makes."""
    what = "actor_behavior_type53 timer expired"
    pokes = _switched_pokes(what, 53, {ACTOR + FIELD_30: bytes([0]),
                                       TILE_33_MODE: word(TILE_33_MODE_SET)})

    info = _run_handler("actor_behavior_type53", what, pokes)
    written = program_writes(info)
    assert (written[ACTOR + ACTOR_X] << 8 | written[ACTOR + ACTOR_X + 1]) == FREE_MARKER
    assert written[TYPE53_ALIVE] << 8 | written[TYPE53_ALIVE + 1] == 0
    assert ACTOR + FIELD_30 not in written, f"{what}: the countdown was stepped past zero"


def test_slot53_raises_its_live_word_before_anything_else_it_does():
    """`move.w #$ffff,$5c6c.l` is the handler's FIRST instruction, so the word is up on every arm —
    including the one that returns immediately. Driven on the strike arm, which never reaches the
    tail that would lower it."""
    name = "actor_behavior_type53"
    what = f"{name} live word on the strike arm"
    pokes = _switched_pokes(what, 53, _strike_geometry())
    image = harness.make_image(pokes)
    band = _handler_band(name) + merge_bands(_sfx_bytes(image, STUN_SFX, SND_CHANNEL_A))

    info = _run_handler(name, what, pokes, band=band)
    written = program_writes(info)
    assert written[TYPE53_ALIVE] << 8 | written[TYPE53_ALIVE + 1] == TYPE53_ALIVE_SET


def _operand_sites(pattern):
    """Every offset in the loaded image holding ``pattern``. A word address appears whole in a
    short-form operand and as the LOW HALF of a long one, so one two-byte scan finds both."""
    image, sites, at = bytes(harness.BASE_IMAGE), [], 0
    while True:
        at = image.find(pattern, at)
        if at < 0:
            return sites
        sites.append(at)
        at += 1


# (name, address, how many operand sites the image holds, how many of them are the handler's own).
# EACH OF THESE IS A LOAD-BEARING CLAIM: slot 60's whole retype story is "nothing else lowers
# WB_STATE_WORD_6F9C", and slot 61's is "the sequence's state is entirely its own". They are scanned
# rather than asserted from ../names.txt so a rebuilt image is checked rather than a comment.
PUBLISHED_WORDS = [
    ("actor_behavior_type53", TYPE53_ALIVE, 3, 2),
    ("actor_behavior_type60", STATE_WORD_6F9C, 3, 2),
    ("actor_behavior_type61", TYPE61_ACTIVE, 3, 3),
    ("actor_behavior_type61", TYPE61_MESSAGES, 1, 1),
]


@pytest.mark.parametrize("name,addr,total,own", PUBLISHED_WORDS,
                         ids=[f"{a:#06x}" for _n, a, _t, _o in PUBLISHED_WORDS])
def test_each_word_these_handlers_publish_has_the_operand_sites_its_plate_claims(name, addr, total,
                                                                                own):
    sites = _operand_sites(addr.to_bytes(WORD_BYTES, "big"))
    entry, size = leaf.entry_of(name), BODY_SIZES[name]
    inside = [at for at in sites if entry <= at < entry + size]
    assert len(sites) == total, (
        f"the image holds {len(sites)} operand sites for {addr:#x}, not {total}: "
        f"{[hex(at) for at in sites]}")
    assert len(inside) == own, f"{name} spells {addr:#x} {len(inside)} times, not {own}"


# --- $d78: the gate, and the boundary it puts inside slot 53's frame ------------------------------
def _player_gate_beq():
    """The gate's `beq.w`, whose address comes out of the pin. It executes on BOTH arms, so on its
    own it witnesses only that the gate ran — what says the branch was TAKEN is the write set of the
    case that uses it, which holds nothing the handler writes below the call."""
    entry = leaf.entry_of(PLAYER_GATE)
    return entry + len(_asm(entry, _player_gate_pieces()[:1]))


def test_the_player_gate_returns_while_tile_33_mode_is_set():
    """The arm that writes nothing at all: `tst.w $1516 / beq` not taken, then `rts`."""
    what = "player_gate_on_1516 with the mode set"
    pokes = _tier_pokes(case_salt(what), {TILE_33_MODE: word(TILE_33_MODE_SET)})

    info = leaf.run(PLAYER_GATE, _PLAYER_GATE, [], what, regs={"_pokes": pokes},
                    max_insns=_cap(PLAYER_GATE))
    assert info["ret"] == DISPATCH_RAN
    assert not program_writes(info), f"{what}: the gate wrote memory, which it does not"


def test_the_player_gate_leaves_for_the_player_body_while_the_mode_is_clear():
    """The other arm is a BRANCH into code this port does not have, so it is a boundary and not a
    result. The witness is `run_reaching`'s: the `beq.w` at the gate's own second instruction really
    executed, which its address comes out of the pin for."""
    what = "player_gate_on_1516 with the mode clear"
    pokes = _tier_pokes(case_salt(what), {TILE_33_MODE: word(0)})
    info = leaf.run_reaching(PLAYER_GATE, _PLAYER_GATE, [], what, _player_gate_beq(),
                             regs={"_pokes": pokes}, stop_pc=PLAYER_STEP_BODY,
                             max_insns=_cap(PLAYER_GATE))
    assert info["ret"] == PLAYER_STEP_BODY
    assert not program_writes(info), f"{what}: the gate wrote memory before the boundary"


def test_slot53_stops_at_the_player_gate_while_tile_33_mode_is_clear():
    """THE BOUNDARY INSIDE A HANDLER'S FRAME, which is what behavior.h's `uint32_t` return is for.
    The step, the sprite and the countdown are all BELOW the `bsr $d78`, so what says the port
    stopped in the right place is that none of them was written: the live word alone moved."""
    what = "actor_behavior_type53 stopped at the player gate"
    pokes = _switched_pokes(what, 53, {ACTOR + FIELD_30: bytes([5]), TILE_33_MODE: word(0)})

    info = _run_handler("actor_behavior_type53", what, pokes, expect=PLAYER_STEP_BODY,
                        stop_pc=PLAYER_STEP_BODY, transfer=_player_gate_beq())
    written = program_writes(info)
    assert written[TYPE53_ALIVE] << 8 | written[TYPE53_ALIVE + 1] == TYPE53_ALIVE_SET
    for field in (ACTOR_X, ACTOR_SPRITE, FIELD_30):
        assert ACTOR + field not in written, (
            f"{what}: {field} was written, so the frame ran on past the gate")


# --- slot 60 ($6f7e): the record that becomes a moving platform -----------------------------------
def _type60_pokes(what, state_word, fields=None):
    base = {ACTOR + ACTOR_TYPE: word(60), ACTOR + ACTOR_SPRITE: word(0),
            ACTOR + ACTOR_Y: word(STAND_Y), STATE_WORD_6F9C: word(state_word)}
    return _tier_pokes(case_salt(what), leaf.overlay(base, fields or {}))


def test_slot60_publishes_no_sprite_and_waits():
    """Thirty bytes of which the first six run every frame: WB_ACTOR_SPRITE_NONE, so a waiting
    record is invisible, and then one `tst.w` that finds nothing."""
    what = "actor_behavior_type60 waiting"
    info = _run_handler("actor_behavior_type60", what, _type60_pokes(what, 0))

    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE, SPRITE_NONE)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("state_word", [1, 0x8000, 0xffff], ids=lambda v: f"state{v:#06x}")
def test_slot60_consumes_the_state_word_and_RETYPES_itself(state_word):
    """`tst.w / beq` — any nonzero word fires it, negative or not. It then CLEARS the word (this is
    its only writer besides set_state_6f9c_ffff) and stamps WB_ACTOR_TYPE60_BECOMES into 4(a0),
    which is WB_ACTOR_TYPE: the record's next dispatch is a different handler."""
    what = f"actor_behavior_type60 consuming {state_word:#06x}"
    info = _run_handler("actor_behavior_type60", what, _type60_pokes(what, state_word))

    expected = {}
    _put(expected, ACTOR + ACTOR_SPRITE, SPRITE_NONE)
    _put(expected, STATE_WORD_6F9C, 0)
    _put(expected, ACTOR + ACTOR_TYPE, TYPE60_BECOMES)
    _assert_writes(info, expected, what)


def test_the_type_slot_60_writes_is_the_VERTICAL_PLATFORMS_own_slot():
    """WHAT THE $36 SELECTS, closed against the image's own table rather than against a comment: the
    entry WB_ACTOR_TYPE60_BECOMES indexes is actor_behavior_type54's."""
    assert _image_slot(TYPE60_BECOMES) == leaf.entry_of("actor_behavior_type54")


# --- slot 61 ($6f9e): the four-message sequence ---------------------------------------------------
from test_sound import (PLAY_SONG_MIXER, PSG_REG_MIXER, model_play_song,   # noqa: E402
                        write_bands)

FIRE = 1 << TYPE61_FIRE_BIT

# The table as the IMAGE holds it, bounded ABOVE by the next routine's entry (one padding byte
# sits between) rather than by a length this file states — so the terminator's index is measured.
TYPE61_MESSAGE_PAD = 1
TYPE61_MESSAGE_BYTES = bytes(harness.BASE_IMAGE[
    TYPE61_MESSAGES:leaf.entry_of("actor_face_followed_reset_22") - TYPE61_MESSAGE_PAD])


def _type61_pokes(what, active, cursor=0, joy_prev=0, joy_current=0, fields=None):
    """A slot-61 record with the sequence's two inputs stated: the active byte and the joystick
    pipeline the rising-edge test reads (joy1_newly_pressed diffs $8b3 against $8cf)."""
    # THE THREE TEXT GLOBALS ARE SEEDED NONZERO. All three are zero in a fresh image, so a `clr.b`
    # over one writes the value that was already there and DROPPING it changes nothing a diff can
    # see — the sweep's `store/type61-lifetime` survived exactly that way.
    base = {ACTOR + ACTOR_TYPE: word(61), ACTOR + FIELD_31: bytes([cursor]),
            TYPE61_ACTIVE: bytes([active]),
            JOY1_PREV: bytes([joy_prev]), JOY1_CURRENT: bytes([joy_current]),
            TEXT_REQUEST: bytes([0x5a]), TEXT_BOX_ACTIVE: bytes([0x5a]),
            TEXT_LIFETIME_REQUEST: bytes([0x5a])}
    return _tier_pokes(case_salt(what), leaf.overlay(base, fields or {}))


def test_slot61_opening_frame_starts_the_song_and_posts_the_first_message():
    """THE ARM THAT REACHES THE SOUND MODULE. `move.l #$e,d0 / clr.l d1 / lea $17adc.l,a5 / jsr
    (a5)` is stub +0, so what the frame writes is snd_play_song's whole write set — taken from the
    battery that OWNS it — plus this handler's own five bytes."""
    what = "actor_behavior_type61 opening frame"
    pokes = _type61_pokes(what, active=0, cursor=0x5a)
    image = harness.make_image(pokes)

    expected = model_play_song(image, TYPE61_SONG)
    expected[ACTOR + FIELD_31] = bytes([0])
    expected[TEXT_REQUEST] = bytes([TYPE61_FIRST_MESSAGE])
    expected[TEXT_LIFETIME_REQUEST] = bytes([0])
    expected[TEXT_BOX_ACTIVE] = bytes([0])
    expected[TYPE61_ACTIVE] = bytes([TYPE61_ACTIVE_SET])

    info = _run_handler("actor_behavior_type61", what, pokes, band=write_bands(expected),
                        psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    leaf.assert_written_is(info, expected, what)


@pytest.mark.parametrize("prev,current", [(0, 0), (FIRE, FIRE), (FIRE, 0), (0, 1)],
                         ids=["idle", "held", "released", "other-bit"])
def test_slot61_waits_for_a_rising_FIRE_edge_and_writes_nothing_meanwhile(prev, current):
    """`jsr $682.w / tst.b d0 / bpl` — only the byte's SIGN bit holds the frame, and only on the
    frame it goes down. A button HELD from last frame is not an edge, and no other joystick bit
    reaches the test at all."""
    what = f"actor_behavior_type61 armed, joy {prev:#04x}->{current:#04x}"
    pokes = _type61_pokes(what, active=TYPE61_ACTIVE_SET, cursor=1,
                          joy_prev=prev, joy_current=current)

    info = _run_handler("actor_behavior_type61", what, pokes)
    assert not program_writes(info), f"{what}: the frame advanced without an edge"


@pytest.mark.parametrize("cursor", [0, 1, 2], ids=lambda v: f"cursor{v}")
def test_slot61_posts_one_message_per_press_out_of_its_own_table(cursor):
    """The cursor is PRE-INCREMENTED, so entry 0 of WB_ACTOR_TYPE61_MESSAGES is never read and the
    first press posts entry 1. The message comes out of the image, not out of this case."""
    what = f"actor_behavior_type61 press at cursor {cursor}"
    pokes = _type61_pokes(what, active=TYPE61_ACTIVE_SET, cursor=cursor, joy_current=FIRE)

    info = _run_handler("actor_behavior_type61", what, pokes)
    message = harness.BASE_IMAGE[TYPE61_MESSAGES + cursor + 1]
    expected = {ACTOR + FIELD_31: cursor + 1, TEXT_REQUEST: message,
                TEXT_LIFETIME_REQUEST: 0, TEXT_BOX_ACTIVE: 0,
                TYPE61_ACTIVE: TYPE61_ACTIVE_SET}
    _assert_writes(info, expected, what)


def test_slot61_leaves_for_the_data_disk_prompt_on_its_terminator():
    """THE HANDLER'S OWN BOUNDARY. The press that reads WB_ACTOR_TYPE61_MESSAGE_END clears the
    active byte and `jmp`s to show_data_disk_prompt with a7 thrown away — a restart, never a
    return. The witness is that `jmp` itself, whose address comes out of the pin."""
    what = "actor_behavior_type61 terminator"
    cursor = len(TYPE61_MESSAGE_BYTES) - 2
    pokes = _type61_pokes(what, active=TYPE61_ACTIVE_SET, cursor=cursor, joy_current=FIRE)
    jmp_pc = leaf.entry_of("actor_behavior_type61") + BODY_SIZES["actor_behavior_type61"] \
        - len(jmp_abs_l(0))

    info = _run_handler("actor_behavior_type61", what, pokes, transfer=jmp_pc,
                        expect=SHOW_DATA_DISK_PROMPT, stop_pc=SHOW_DATA_DISK_PROMPT)
    _assert_writes(info, {ACTOR + FIELD_31: cursor + 1, TYPE61_ACTIVE: 0}, what)


def test_slot61_reads_PAST_its_own_table_for_a_stale_cursor():
    """NOTHING MASKS THE CURSOR: `moveq #0,d0 / move.b 31(a0),d0 / lea 0(a1,d0.w),a1` reads
    WB_ACTOR_TYPE61_MESSAGES + 0..255, so a record entered with a cursor the opening frame did not
    write posts whatever byte of the code image it lands on. The game's own flow cannot reach this
    — the opening frame writes 0 — and the window stays inside the image, which is why it is a
    quiet wrong answer rather than a crash."""
    what = "actor_behavior_type61 stale cursor"
    cursor = 0x40
    pokes = _type61_pokes(what, active=TYPE61_ACTIVE_SET, cursor=cursor, joy_current=FIRE)

    info = _run_handler("actor_behavior_type61", what, pokes)
    assert program_writes(info)[TEXT_REQUEST] == harness.BASE_IMAGE[TYPE61_MESSAGES + cursor + 1]


def test_the_message_table_is_four_ids_and_a_terminator():
    """The four highest WB_TEXT_REQUEST ids in the game, in order, and $ff. It is bounded below by
    slot 61's last instruction plus the active byte and above by actor_face_followed_reset_22."""
    assert TYPE61_MESSAGE_BYTES[-1] == TYPE61_MESSAGE_END
    ids = TYPE61_MESSAGE_BYTES[:-1]
    assert ids[0] == TYPE61_FIRST_MESSAGE
    assert list(ids) == list(range(TYPE61_FIRST_MESSAGE, TYPE61_FIRST_MESSAGE + len(ids)))
    assert len(TYPE61_MESSAGE_BYTES) == len(ids) + 1


COPYLOCK_FAILURE_CALL = 0xf56e


def jmp_abs_w(addr):
    return opcode(0x4ef8) + word(addr)


# The four ways the image could name a handler outside the dispatcher: `jsr`/`jmp`, short and long.
# THE SHORT FORMS ARE THE POINT — the longword-only scan that produced ../names.txt's plates is what
# missed the one real caller.
CALL_ENCODINGS = (jsr_abs_w, jmp_abs_w, leaf.jsr_abs_l, jmp_abs_l)


def test_exactly_one_table_slot_is_also_reached_by_a_CALL_and_it_is_slot_61():
    """THE PLATE CORRECTION, as a scan over ALL SIXTY-TWO slots rather than the one it was found on.

    ../names.txt says of every slot that it is "reached ONLY through actor_dispatch_behavior's
    `jmp (a1)`, never by a call". That is false for exactly one — the copylock failure path's
    `jsr $6f9e.w` — and it is what says what slot 61's four messages are for. Scanning all four
    encodings against all 62 targets is what stops the next batch inheriting the sentence unverified.
    """
    calls = {}
    for slot in range(BEHAVIOR_SLOTS):
        target = _image_slot(slot)
        # Every entry is inside the short form's reach, which is what makes all four encodings
        # meaningful; a target above it would alias under `word()`'s mask rather than fail.
        assert target <= 0xffff, f"slot {slot}'s target {target:#x} is outside the short form"
        for encode in CALL_ENCODINGS:
            for at in _operand_sites(encode(target)):
                calls[at] = (slot, target)

    assert sorted(calls) == [COPYLOCK_FAILURE_CALL], (
        f"the image calls table targets at {[hex(at) for at in sorted(calls)]}")
    assert calls[COPYLOCK_FAILURE_CALL] == (61, leaf.entry_of("actor_behavior_type61"))


# --- slots 59 and 8 ($7044, $705a): the two prologues that run into slot 7 ------------------------
TYPE59_TEMPLATE_FIELD = TABLE_A32_SET + SPAWN_RESPAWN_KIND


def _prologue_pokes(what, slot, field_30=0):
    return _tier_pokes(case_salt(what), {ACTOR + ACTOR_TYPE: word(slot),
                                         ACTOR + FIELD_30: bytes([field_30]),
                                         TYPE59_TEMPLATE_FIELD: word(0)})


def _run_prologue(name, what, pokes):
    """THE STOP IS THE WHOLE POINT and there is no `run_reaching` witness for slot 8: it has no
    transfer instruction at all, it simply runs into slot 7's first byte. Neither prologue holds an
    `rts`, so the oracle's only other stop is unreachable and the checkpoint is unambiguous.

    The expected answer AND the witness both come out of ALWAYS_TRANSFER rather than being spelt
    again, so the table the dispatch row reads and the value the handler returns are pinned against
    each other."""
    target, transfer = ALWAYS_TRANSFER[name]
    return _run_handler(name, what, pokes, expect=target, stop_pc=target, transfer=transfer)


@pytest.mark.parametrize("field_30", [0, 1 << TYPE08_MARK_BIT, 0xff],
                         ids=lambda v: f"field30={v:#04x}")
def test_slot59_marks_the_record_and_arms_the_A32_templates_first_respawn(field_30):
    """Twenty-two bytes: `bset #2,30(a0)`, then WB_ACTOR_TYPE59_RESPAWN_KIND into
    WB_TABLE_A32_SET's first template — addressed by a bare `lea`, so it lands on the A32 table
    whichever one WB_TABLE_PTR_21E8C currently names — and then slot 7's body."""
    what = f"actor_behavior_type59 over {field_30:#04x}"
    info = _run_prologue("actor_behavior_type59", what,
                         _prologue_pokes(what, 59, field_30))
    expected = {ACTOR + FIELD_30: field_30 | (1 << TYPE59_MARK_BIT)}
    _put(expected, TYPE59_TEMPLATE_FIELD, TYPE59_RESPAWN_KIND)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("field_30", [0, 1 << TYPE59_MARK_BIT, 0xff],
                         ids=lambda v: f"field30={v:#04x}")
def test_slot08_marks_the_record_and_nothing_else(field_30):
    """SIX BYTES AND ONE INSTRUCTION — the shortest reconstructed routine in this project. It raises
    its own bit and falls into the same body slot 59 branches to, which is what makes the two bits
    of WB_ACTOR_FIELD_30 the way one shared handler knows which entry was dispatched."""
    what = f"actor_behavior_type08 over {field_30:#04x}"
    info = _run_prologue("actor_behavior_type08", what,
                         _prologue_pokes(what, 8, field_30))
    _assert_writes(info, {ACTOR + FIELD_30: field_30 | (1 << TYPE08_MARK_BIT)}, what)


def test_the_two_prologues_and_slot_7_are_three_table_entries_for_one_body():
    """What the boundary is BOUNDING: slots 59, 8 and 7 are three distinct table entries whose code
    is contiguous and ends in one body. Their addresses come out of the image's own table."""
    assert _image_slot(59) + BODY_SIZES["actor_behavior_type59"] == _image_slot(8)
    assert _image_slot(8) + BODY_SIZES["actor_behavior_type08"] == _image_slot(7)
    assert _image_slot(7) == BEHAVIOR_TYPE07
