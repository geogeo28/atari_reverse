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
import loader
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, addi_w_dn, addq_b_d16, andi_w_dn, bcd_expected,
                  branch_w_to, brief_extension_word, bsr_w, btst_imm_dn, case_salt, clr_b_d16,
                  clr_w_abs_l, clr_w_dn, cmp_w_dn_dn, cmp_w_imm_dn, cmpi_w_d16, keyed_block,
                  lea_abs_l, lea_d16, lea_indexed, longword, lsl_w_imm_dn, merge_bands,
                  move_b_d16_dn, move_b_imm_d16, move_w_dn_dn, move_w_imm_abs_l, move_w_imm_dn,
                  move_w_ind_dn, move_w_postinc_dn, moveq_0_dn, opcode, program_writes, s16,
                  sub_w_dn_d16, sub_w_dn_dn, subi_w_dn, subq_w_dn, tst_b_d16, tst_w_abs_l,
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
# Batch 32 ported slot 7, which this used to name, batch 35 ported slot 9, which replaced it,
# batch 36 ported slot 14, which replaced that, and batch 37 ported slot 20 — for the same reason
# the constant exists at all. With the monster family whole, the only rows left are the player's
# (slot 1, which UNPORTED_TYPE already names), 38..46 and 57.
UNPORTED_SLOT = 39

# ...and two MORE, for the cases that want three different unported slots at once (one per alias
# band, one per walk boundary). Named for the same reason the two above are.
#
# WHY A BOUNDARY ROW MUST NOT USE UNPORTED_TYPE. `_walk_pokes` gives every FREE record that same
# type, so a walk case whose boundary slot is slot 1 cannot tell "stopped at the record I seeded"
# from "dispatched a free record instead of skipping it" — both report slot 1's address and write
# nothing. The walk rows therefore name these three and never UNPORTED_TYPE.
UNPORTED_MID = 40
UNPORTED_HIGH = 57


# --- the encodings only this battery spells -------------------------------------------------------
# TWELVE of these are now a THIRD copy and are due to move to leaf.py under its own rule ("an
# encoding moves there on its third") — batch 33 adding `move_w_dn_abs_l`, `cmp_w_abs_l_dn` and
# `addq_b_dn` to the list, each annotated ALSO IN beside its own definition below: `move_w_dn_d16` (test_actor.py, test_map.py), `movea_l_ind`
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


def movea_l_an(destination, source):
    """`movea.l An,Ad` — slot 21 keeps the followed record in a2 across its allocation, which is the
    one place in this tier an address register is copied to another."""
    return opcode(0x2048 | (destination << 9) | source)


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


def lsl_l_imm_dn(count, reg):
    """`lsl.l #n,Dn` — slot 38 scales a zero-extended KIND byte by sixteen with one."""
    return opcode(0xe188 | ((count & 7) << 9) | reg)
    # ALSO IN test_actor.py, test_stage.py — third copy, queued for leaf.py.


def rol_l_imm_dn(count, reg):
    """`rol.l #n,Dn` — how $6938 walks a packed-BCD longword one nibble at a time. Not `lsl`: the
    nibble that leaves the top comes back at the bottom, which is what makes the digit order
    cyclic."""
    return opcode(0xe198 | ((count & 7) << 9) | reg)


def move_l_dn_dn(destination, source):
    return opcode(0x2000 | (destination << 9) | source)


def move_l_d16_dn(reg, base, displacement):
    """`move.l d16(An),Dn` — the SCORE longword out of an actor_kind_table row."""
    return opcode(0x2028 | (reg << 9) | base) + word(displacement)


def andi_l_dn(reg, value):
    """`andi.l #imm,Dn` — a LONGWORD mask where every other mask in this file is a word one."""
    return opcode(0x0280 | reg) + longword(value)


def move_b_imm_postinc(base, value):
    return opcode(0x10fc | (base << 9)) + word(value & 0xff)


def move_b_dn_postinc(base, reg):
    """`move.b Dn,(An)+` — the digit store $6938 walks its five characters out with."""
    return opcode(0x10c0 | (base << 9) | reg)


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


def jmp_d16_an(reg, displacement):
    """`jmp d16(An)` — $6786's TAIL into the sound stub table, where actor_stun_followed twelve
    bytes later spells the same slot as a `jsr`."""
    return opcode(0x4ee8 | reg) + word(displacement)


def jsr_d16_an(reg, displacement):
    return opcode(0x4ea8 | reg) + word(displacement)
    # ALSO IN test_actor.py — second copy, which the rule allows.


def sub_w_ind_dn(reg, base):
    """`sub.w (An),Dn` — the swoop's own x difference, taken straight out of the followed record."""
    return opcode(0x9050 | (reg << 9) | base)


def suba_l_imm(reg, value):
    """`suba.l #imm,An` — how the swoop turns a path ADDRESS into the offset it stores."""
    return opcode(0x91fc | (reg << 9)) + longword(value)


def move_w_an_d16(source, base, displacement):
    """`move.w An,d16(Ad)` — an ADDRESS register's low word stored into a record field, which is
    what makes WB_ACTOR_FIELD_24 an offset rather than a pointer."""
    return opcode(0x3148 | (base << 9) | source) + word(displacement)
    # First copy anywhere: no other battery has an address register STORED into a record field.


def move_w_d16_d16(source, source_displacement, destination, destination_displacement):
    """`move.w d16(As),d16(Ad)` — $731a's `move.w 2(a0),26(a0)`, the launch y saved."""
    # ALSO IN test_hud.py, test_scroll.py — third copy, queued for leaf.py.
    return (opcode(0x3168 | (destination << 9) | source)
            + word(source_displacement) + word(destination_displacement))


def movea_l_indexed(destination, source, index):
    """`movea.l 0(As,Dn.w),Ad` — the fetch BOTH of this file's jump tables are read with."""
    return opcode(0x2070 | (destination << 9) | source) + brief_extension_word(index)
    # ALSO IN test_blit.py, test_scene.py (each hand-rolling `index << 12` where this calls
    # `brief_extension_word`) — third copy, and the FIRST candidate for the leaf.py promotion
    # because the other two spell the extension word themselves.


def andi_b_d16(base, value, displacement):
    """`andi.b #imm,d16(An)` — a mask applied IN MEMORY, so the flags come from the ALU result and
    the masked byte is stored. Slot 7 spells both of its spawn cadences this way."""
    return opcode(0x0228 | base) + word(value & 0xff) + word(displacement)
    # Second copy of the SHAPE `andi_b_dn` above has, over memory rather than a register; the rule
    # counts spellings per battery, so this is a first here.


def subi_w_d16(base, value, displacement):
    """`subi.w #imm,d16(An)` — the dropper's `subi.w #$20,2(a1)`."""
    return opcode(0x0468 | base) + word(value) + word(displacement)
    # ALSO IN test_scroll.py, test_stage.py — third copy, queued for leaf.py.


def move_l_postinc_d16(source, destination, displacement):
    """`move.l (As)+,d16(Ad)` — the velocity longword the burst walks its table with."""
    return opcode(0x2158 | (destination << 9) | source) + word(displacement)


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
        *_launch_inline_pieces(TIMER30_SPEED),
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
FIELD_21 = wb("ACTOR_FIELD_21")
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
# Slot 21 hands $6528 four coordinates in d0..d3 and its row in d4; D0..D2 and D7 come from
# test_actor.py with the rest of the record model, and these two have had no caller until now.
D3, D4 = 3, 4


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


REQUEST9_SFX = wb("ACTOR_REQUEST9_SFX")
SOUND_REQUEST_9 = "sound_request_9"


def _sound_request_9_pieces():
    return [
        move_w_imm_dn(D0, REQUEST9_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, SND_STUB_TABLE),
        jmp_d16_an(A1, STUB_TRIGGER_OFFSET),
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


def _bonus_digits_pieces():
    """$6938 — the LEA is into a6 and the count is FIVE, both of which the old plate had wrong.

    Two loops that share nothing but the counter: the blanking one decrements without testing (so
    only a nonzero nibble ends it) and the digit one tests after decrementing (so a counter that
    started at zero wraps). Both closing branches are SHORT where every other branch here is long.
    """
    return [
        leaf.lea_abs_l(A6, BONUS_DIGITS_AT),
        leaf.swap_dn(D0),
        move_w_imm_dn(D7, BONUS_DIGIT_COUNT),
        _lab("blank"),
        move_l_dn_dn(D1, D0),
        andi_l_dn(D1, BCD_DIGIT_MASK),
        leaf.tst_w_dn(D1),
        _bcc(BNE_W, "digit"),
        move_b_imm_postinc(A6, DIGIT_BLANK),
        leaf.subi_w_dn(D7, 1),
        rol_l_imm_dn(BCD_DIGIT_BITS, D0),
        _bra_s("blank"),
        _lab("digit"),
        move_l_dn_dn(D1, D0),
        andi_l_dn(D1, BCD_DIGIT_MASK),
        addi_b_dn(D1, DIGIT_ZERO),
        move_b_dn_postinc(A6, D1),
        leaf.subi_w_dn(D7, 1),
        _bcc(BEQ_W, "post"),
        rol_l_imm_dn(BCD_DIGIT_BITS, D0),
        _bra_s("digit"),
        _lab("post"),
        leaf.move_b_imm_abs_l(MESSAGE_BONUS_POINTS, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        RTS,
    ]


def _type38_pieces():
    """$5408 — 236 bytes, and no table of its own.

    The SFX request is spelt INLINE here (`jsr 56(a1)` where `sound_request_9` has a `jmp`), so this
    handler is not one of that routine's five callers and the pin says so by assembling the four
    instructions rather than a `bsr`. Its gold arm is `hud_award_gold_from_descriptor`'s five calls
    with WB_STAGE_NUMBER above them and a `bra.w` into the defeat below them.
    """
    return [
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "wait"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "wait"),
        move_w_imm_dn(D0, REQUEST9_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, SND_STUB_TABLE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, KIND),
        cmpi_b_d16(A0, PICKUP_KIND_FIRST, KIND),
        _bcc(BGE_W, "kind"),
        leaf.move_w_abs_l_dn(D0, STAGE_NUMBER),
        _bsr(BCD_RANDOM),
        _bsr(ADD_COUNTER),
        _bsr(GOLD_DIGITS),
        move_l_imm_dn(D0, COLLECT_SCORE),
        _bsr(ADD_SCORE),
        leaf.move_b_imm_abs_l(MESSAGE_GOLD_GET, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        _bcc_abs(BRA_W, leaf.entry_of(DEFEAT)),
        _lab("kind"),
        lea_abs_l(A1, KIND_TABLE),
        lsl_l_imm_dn(KIND_RECORD_SHIFT, D0),
        leaf.lea_indexed(A1, D0),
        move_l_d16_dn(D0, A1, KIND_SCORE),
        _bcc(BEQ_W, "effect"),
        _bsr(ADD_SCORE),
        _bsr(BONUS_DIGITS),
        _lab("effect"),
        move_w_ind_dn(D0, A1, KIND_PICKUP_EFFECT),
        lea_abs_l(A1, PICKUP_EFFECT_TABLE),
        leaf.add_w_dn_dn(D0, D0),
        leaf.add_w_dn_dn(D0, D0),
        movea_l_indexed(A1, A1, D0),
        jsr_ind(A1),
        _bcc_abs(BRA_W, leaf.entry_of(DEFEAT)),
        _lab("wait"),
        cmpi_b_d16(A0, PICKUP_KIND_FIRST, KIND),
        _bcc(BLT_W, "gold-wait"),
        tst_w_abs_w(FLAG_A32),
        _bcc(BEQ_W, "tick"),
        move_b_imm_d16(A0, TYPE38_FLASH, FIELD_12),
        _bcc(BRA_W, "tick"),
        _lab("gold-wait"),
        tst_b_d16(A0, KIND),
        _bcc(BNE_W, "sprite"),
        _bsr(RELAUNCH_5160),
        _bcc(BRA_W, "tick"),
        _lab("sprite"),
        _bsr(SELECT_SPRITE),
        _lab("tick"),
        subq_b_d16(1, A0, FIELD_12),
        _bcc(BNE_W, "out"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        move_b_imm_d16(A0, TYPE38_FIELD_12_RELOAD, FIELD_12),
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


# --- batch 32: the rest of the $5a band ($5928, $5972, $59d0) -------------------------------------
ADVANCE_ANIM16 = "actor_advance_anim16"

TYPE47_FRAMES = wb("ACTOR_TYPE47_FRAMES")
TYPE48_FRAMES = wb("ACTOR_TYPE48_FRAMES")
TYPE48_MASK = wb("ACTOR_TYPE48_MASK")
TYPE48_STEP = wb("ACTOR_TYPE48_STEP")
TYPE49_FRAMES_PHASE1 = wb("ACTOR_TYPE49_FRAMES_PHASE1")
TYPE49_FRAMES_PHASE2 = wb("ACTOR_TYPE49_FRAMES_PHASE2")
TYPE49_STEP = wb("ACTOR_TYPE49_STEP")


def _type47_pieces():
    """The only handler in the band whose table is reached ABSOLUTE and then indexed in a second
    instruction (`lea $5952.l,a1 / lea 0(a1,d0.w),a1`) rather than by one `lea d8(PC,Dn.w)`."""
    return [
        lea_abs_l(A1, TYPE47_FRAMES),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM32_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "out"),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _walk_prologue_pieces(step, faced_label):
    """The forty-two bytes slots 48 and 49 open with, spelt once here because the image spells them
    twice: the settle, the ascent, and actor_step_facing's own body inline. ``faced_label`` is where
    the `bne` past the `bchg` lands, which is the only thing the two copies disagree about."""
    return [
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        move_w_imm_dn(D7, step),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "blocked?"),
        _lab("left"),
        _bsr(STEP_LEFT),
        _lab("blocked?"),
        tst_b_dn(D0),
        _bcc(BNE_W, faced_label),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab(faced_label),
    ]


def _type48_pieces():
    """That walk, then slot 50's tail: the same nine instructions over a FOUR-word table and the
    same `subq.b #1,30(a0)` ending."""
    return _walk_prologue_pieces(TYPE48_STEP, "frames") + [
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, TYPE48_FRAMES),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, TYPE48_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BNE_W, "out"),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type49_pieces():
    """The same walk, then the TWO-PHASE animation: one cursor read before the phase test, two
    tables, and the two `bsr $5a3c` sites actor_advance_anim16's own plate names."""
    return _walk_prologue_pieces(TYPE49_STEP, "cursor") + [
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        tst_b_d16(A0, FIELD_31),
        _bcc(BEQ_W, "phase-one"),
        _lea_pc_indexed(A1, D0, TYPE49_FRAMES_PHASE2),
        _bsr(ADVANCE_ANIM16),
        tst_b_dn(D0),
        _bcc(BEQ_W, "free"),
        RTS,
        _lab("phase-one"),
        _lea_pc_indexed(A1, D0, TYPE49_FRAMES_PHASE1),
        _bsr(ADVANCE_ANIM16),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BNE_W, "out"),
        st_d16(A0, FIELD_31),
        RTS,
        _lab("free"),
        clr_b_d16(A0, FIELD_31),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


# --- batch 32 phase 2: the SWOOP tier ($72c2..$73cd) and slot 7's body ($7060) --------------------
SWOOP_STATE0 = "actor_swoop_state0_acquire"
SWOOP_STATE1 = "actor_swoop_state1_run_path"
SWOOP_STATE2 = "actor_swoop_state2_home_x"
SWOOP_STATE3 = "actor_swoop_state3_descend"
TYPE07 = "actor_behavior_type07"
FACE_FOLLOWED = "actor_face_followed_reset_22"

FIELD_23 = wb("ACTOR_FIELD_23")
FIELD_26 = wb("ACTOR_FIELD_26")
SWOOP_STATE_TABLE = wb("ACTOR_SWOOP_STATE_TABLE")
SWOOP_STATE_ENTRY = wb("ACTOR_SWOOP_STATE_ENTRY")
SWOOP_PATH_TABLE = wb("ACTOR_SWOOP_PATH_TABLE")
SWOOP_PATHS = wb("ACTOR_SWOOP_PATHS")
SWOOP_PATH_FAR = wb("ACTOR_SWOOP_PATH_FAR")
SWOOP_PATH_ENTRY = wb("ACTOR_SWOOP_PATH_ENTRY")
SWOOP_PATH_DY = wb("ACTOR_SWOOP_PATH_DY")
SWOOP_PATH_STEP = wb("ACTOR_SWOOP_PATH_STEP")
SWOOP_X_REACH = wb("ACTOR_SWOOP_X_REACH")
SWOOP_Y_NEAR = wb("ACTOR_SWOOP_Y_NEAR")
SWOOP_Y_FLOOR = wb("ACTOR_SWOOP_Y_FLOOR")
SWOOP_Y_SHIFT = wb("ACTOR_SWOOP_Y_SHIFT")
SWOOP_HOME_STEP = wb("ACTOR_SWOOP_HOME_STEP")
SWOOP_DESCEND_STEP = wb("ACTOR_SWOOP_DESCEND_STEP")
SWOOP_RISE = wb("ACTOR_SWOOP_RISE")
SWOOP_ACQUIRE = wb("ACTOR_SWOOP_ACQUIRE")
SWOOP_RUN_PATH = wb("ACTOR_SWOOP_RUN_PATH")
SWOOP_HOME_X = wb("ACTOR_SWOOP_HOME_X")
SWOOP_DESCEND = wb("ACTOR_SWOOP_DESCEND")

TYPE07_SPRITE_LEFT = wb("ACTOR_TYPE07_SPRITE_LEFT")
TYPE07_SPRITE_RIGHT = wb("ACTOR_TYPE07_SPRITE_RIGHT")
TYPE07_FRAME_COUNT = wb("ACTOR_TYPE07_FRAME_COUNT")
TYPE07_FRAMES_LEFT = wb("ACTOR_TYPE07_FRAMES_LEFT")
TYPE07_FRAMES_RIGHT = wb("ACTOR_TYPE07_FRAMES_RIGHT")
TYPE07_FRAMES_MARKED_LEFT = wb("ACTOR_TYPE07_FRAMES_MARKED_LEFT")
TYPE07_FRAMES_MARKED_RIGHT = wb("ACTOR_TYPE07_FRAMES_MARKED_RIGHT")
TYPE07_FRAMES_UNREFERENCED = wb("ACTOR_TYPE07_FRAMES_UNREFERENCED")
TYPE07_BURST_MASK = wb("ACTOR_TYPE07_BURST_MASK")
TYPE07_BURST_LAST = wb("ACTOR_TYPE07_BURST_LAST")
TYPE07_BURST_LEFT = wb("ACTOR_TYPE07_BURST_LEFT")
TYPE07_BURST_RIGHT = wb("ACTOR_TYPE07_BURST_RIGHT")
TYPE07_BURST_ENTRY = wb("ACTOR_TYPE07_BURST_ENTRY")
TYPE07_BURST_SPRITE = wb("ACTOR_TYPE07_BURST_SPRITE")
TYPE07_DROP_MASK = wb("ACTOR_TYPE07_DROP_MASK")
TYPE07_DROP_SPRITE = wb("ACTOR_TYPE07_DROP_SPRITE")
TYPE07_DROP_RISE = wb("ACTOR_TYPE07_DROP_RISE")
TYPE07_DROP_VELOCITY = wb("ACTOR_TYPE07_DROP_VELOCITY")
TYPE07_DROP_FIELD_26 = wb("ACTOR_TYPE07_DROP_FIELD_26")
TYPE07_SHOT_TYPE = wb("ACTOR_TYPE07_SHOT_TYPE")
TYPE07_SHOT_SIZE = wb("ACTOR_TYPE07_SHOT_SIZE")
ALLOC_NONE = wb("ACTOR_ALLOC_NONE")


def _swoop_state0_pieces():
    """$72c2 — three gates and four writes. `cmp.w #$ffc0` and `cmp.w #$40` are the same window
    either side of zero; the `bmi` after `subq.w #8` is what keeps the shift's index inside the
    four-entry table."""
    return [
        _bsr(SIDE_FLAG),
        _bsr(FOLLOWED_RECORD),
        move_w_ind_dn(D0, A0),
        sub_w_ind_dn(D0, A1),
        cmp_w_imm_dn(D0, -SWOOP_X_REACH & 0xffff),
        _bcc(BLT_W, "out"),
        cmp_w_imm_dn(D0, SWOOP_X_REACH),
        _bcc(BGT_W, "out"),
        move_w_ind_dn(D0, A1, ACTOR_Y),
        sub_w_d16_dn(D0, A0, ACTOR_Y),
        _bcc(BMI_W, "out"),
        cmp_w_imm_dn(D0, SWOOP_Y_NEAR),
        _bcc(BLE_W, "table"),
        movea_l_imm(A1, SWOOP_PATH_FAR),
        _bcc(BRA_W, "commit"),
        _lab("table"),
        subq_w_dn(SWOOP_Y_FLOOR, D0),
        _bcc(BMI_W, "out"),
        lea_abs_l(A1, SWOOP_PATH_TABLE),
        lsr_w_imm_dn(SWOOP_Y_SHIFT, D0),
        lsl_w_imm_dn(2, D0),
        movea_l_indexed(A1, A1, D0),
        _lab("commit"),
        suba_l_imm(A1, SWOOP_PATHS),
        move_w_an_d16(A1, A0, FIELD_24),
        move_w_d16_d16(A0, ACTOR_Y, A0, FIELD_26),
        move_b_imm_d16(A0, SWOOP_RUN_PATH, FIELD_22),
        _lab("out"),
        RTS,
    ]


def _swoop_state1_pieces():
    """$7328 — one word PAIR a frame. The sentinel arm does NOT write the cursor back, which is why
    the two `move.w a1,24(a0)` sites are one instruction rather than a shared exit."""
    return [
        move_w_ind_dn(D1, A0, FIELD_24),
        lea_abs_l(A1, SWOOP_PATHS),
        adda_w_dn(D1, A1),
        move_w_postinc_dn(D0, A1),
        _bcc(BMI_W, "end"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "right"),
        sub_w_dn_ind(D0, A0),
        _bcc(BRA_W, "dy"),
        _lab("right"),
        add_w_dn_ind(D0, A0),
        _lab("dy"),
        move_w_postinc_dn(D0, A1),
        add_w_dn_d16(D0, A0, ACTOR_Y),
        suba_l_imm(A1, SWOOP_PATHS),
        move_w_an_d16(A1, A0, FIELD_24),
        RTS,
        _lab("end"),
        move_b_imm_d16(A0, SWOOP_HOME_X, FIELD_22),
        RTS,
    ]


def _swoop_state2_pieces():
    """$7366 — and the TWO `bchg`s, which are what this pin is for: no differential can separate a
    no-op pair from nothing, so the bytes are the only surface they have."""
    return [
        _bsr(FOLLOWED_RECORD),
        move_w_ind_dn(D0, A1),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "right"),
        subq_w_ind(SWOOP_HOME_STEP, A0),
        cmp_w_ind_dn(D0, A0),
        _bcc(BGE_W, "arrived"),
        RTS,
        _lab("right"),
        addq_w_ind(SWOOP_HOME_STEP, A0),
        cmp_w_ind_dn(D0, A0),
        _bcc(BLE_W, "arrived"),
        RTS,
        _lab("arrived"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, SWOOP_DESCEND, FIELD_22),
        RTS,
    ]


def _swoop_state3_pieces():
    """$739e — the machine's only map probe, and its answer is discarded: nothing follows the
    `bsr`, exactly as slot 52's step does."""
    return [
        move_w_imm_dn(D7, SWOOP_DESCEND_STEP),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "right"),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "rise"),
        _lab("right"),
        _bsr(STEP_RIGHT),
        _lab("rise"),
        subq_w_d16(SWOOP_RISE, A0, ACTOR_Y),
        move_w_ind_dn(D0, A0, FIELD_26),
        cmp_w_d16_dn(D0, A0, ACTOR_Y),
        _bcc(BLT_W, "out"),
        clr_b_d16(A0, FIELD_22),
        _lab("out"),
        RTS,
    ]


def _type07_pieces():
    """$7060 — 424 bytes, and the two `bsr.s $701c` are the only SHORT calls in the behaviour tier
    outside $6840's. The frame-list choice is two overlapping writes of a1, spelt in that order."""
    return [
        bit_op_d16(BTST_IMM, SPAWNED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(SPAWN_ANIM)),
        _bsr(HIT_BY_SHOT),
        tst_w_dn(D7),
        _bcc(BNE_W, "damage"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "point?"),
        _bsr_s(FACE_FOLLOWED),
        _bcc_abs(BRA_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        _lab("point?"),
        btst_imm_dn(POINT_BIT, D0),
        _bcc(BEQ_W, "sprite"),
        _lab("damage"),
        _bsr_s(FACE_FOLLOWED),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        clr_b_d16(A0, FIELD_18),
        _bsr(DAMAGE_TEMPLATE),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab("sprite"),
        bit_op_d16(BTST_IMM, TYPE59_MARK_BIT, A0, FIELD_30),
        _bcc(BEQ_W, "animate"),
        move_w_imm_d16(A0, TYPE07_SPRITE_LEFT, ACTOR_SPRITE),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "state"),
        move_w_imm_d16(A0, TYPE07_SPRITE_RIGHT, ACTOR_SPRITE),
        _bcc(BRA_W, "state"),
        _lab("animate"),
        addq_b_d16(1, A0, FIELD_23),
        cmpi_b_d16(A0, TYPE07_FRAME_COUNT, FIELD_23),
        _bcc(BLT_W, "cursor"),
        clr_b_d16(A0, FIELD_23),
        _lab("cursor"),
        clr_w_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_23),
        lsl_w_imm_dn(1, D0),
        lea_abs_l(A1, TYPE07_FRAMES_LEFT),
        bit_op_d16(BTST_IMM, TYPE08_MARK_BIT, A0, FIELD_30),
        _bcc(BEQ_W, "side?"),
        lea_abs_l(A1, TYPE07_FRAMES_MARKED_LEFT),
        _lab("side?"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "publish"),
        lea_abs_l(A1, TYPE07_FRAMES_RIGHT),
        bit_op_d16(BTST_IMM, TYPE08_MARK_BIT, A0, FIELD_30),
        _bcc(BEQ_W, "publish"),
        lea_abs_l(A1, TYPE07_FRAMES_MARKED_RIGHT),
        _lab("publish"),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        _lab("state"),
        clr_w_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_22),
        lsl_w_imm_dn(2, D0),
        lea_abs_l(A1, SWOOP_STATE_TABLE),
        movea_l_indexed(A1, A1, D0),
        jsr_ind(A1),
        bit_op_d16(BTST_IMM, TYPE08_MARK_BIT, A0, FIELD_30),
        _bcc(BEQ_W, "dropper?"),
        addq_b_d16(1, A0, FIELD_31),
        tst_b_d16(A0, FIELD_22),
        _bcc(BNE_W, "dropper?"),
        andi_b_d16(A0, TYPE07_BURST_MASK, FIELD_31),
        _bcc(BNE_W, "dropper?"),
        move_w_imm_dn(D1, TYPE07_BURST_LAST),
        lea_abs_l(A2, TYPE07_BURST_LEFT),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "burst"),
        lea_abs_l(A2, TYPE07_BURST_RIGHT),
        _lab("burst"),
        _bsr(ALLOC_HIGH),
        cmpa_l_imm(A1, ALLOC_NONE),
        _bcc(BEQ_W, "out"),
        move_l_ind_ind(A0, A1),
        move_w_imm_d16(A1, TYPE07_SHOT_TYPE, ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, TYPE07_SHOT_SIZE, HALF_WIDTH),
        move_w_imm_d16(A1, TYPE07_BURST_SPRITE, ACTOR_SPRITE),
        move_l_postinc_d16(A2, A1, FIELD_24),
        dbf_to(D1, "burst"),
        _lab("dropper?"),
        bit_op_d16(BTST_IMM, TYPE59_MARK_BIT, A0, FIELD_30),
        _bcc(BEQ_W, "out"),
        _bsr(ALLOC_HIGH),
        cmpa_l_imm(A1, ALLOC_NONE),
        _bcc(BEQ_W, "out"),
        addq_b_d16(1, A0, FIELD_31),
        andi_b_d16(A0, TYPE07_DROP_MASK, FIELD_31),
        _bcc(BNE_W, "out"),
        move_l_ind_ind(A0, A1),
        subi_w_d16(A1, TYPE07_DROP_RISE, ACTOR_Y),
        move_w_imm_d16(A1, TYPE07_SHOT_TYPE, ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, TYPE07_SHOT_SIZE, HALF_WIDTH),
        move_w_imm_d16(A1, TYPE07_DROP_SPRITE, ACTOR_SPRITE),
        move_w_imm_d16(A1, TYPE07_DROP_VELOCITY, FIELD_24),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "out"),
        move_w_imm_d16(A1, TYPE07_DROP_FIELD_26, FIELD_26),
        _lab("out"),
        RTS,
    ]


# --- batch 33: the collectables (slots 28, 30, 31) and the payout cluster at $517a ----------------
BCD_RANDOM = "bcd_add_random_1_to_4"
GOLD_DIGITS = "text_write_gold_digits_a2ac"
AWARD = "hud_award_gold_from_descriptor"
SELECT_SPRITE = "actor_select_sprite_by_flag"
ADD_COUNTER = "bcd_add_counter_bd6e"
ADD_SCORE = "bcd_add_score_bd70"
RELAUNCH_5160 = "actor_relaunch_and_anim_5160"

FIELD_12 = wb("ACTOR_FIELD_12")
FLICKER_BIT = wb("ACTOR_FLAG_FLICKER_BIT")
FRAME_TOGGLE = wb("FRAME_TOGGLE")
METER_VALUE = wb("HUD_METER_VALUE")
METER_MAX = wb("HUD_METER_MAX")
BCD_COUNTER = wb("BCD_COUNTER")
BCD_COUNTER_LEN = wb("BCD_COUNTER_LEN")
BCD_SCORE = wb("BCD_SCORE")
BCD_SCORE_LEN = wb("BCD_SCORE_LEN")
BCD_ADDEND = wb("BCD_ADDEND")
COLLECT_SCORE = wb("ACTOR_COLLECT_SCORE")
FLICKER_AT_FIELD_12 = wb("ACTOR_FLICKER_AT_FIELD_12")
TYPE28_GOLD = wb("ACTOR_TYPE28_GOLD")
TYPE28_FIELD_12_RELOAD = wb("ACTOR_TYPE28_FIELD_12_RELOAD")
TYPE30_COLLECT_MIN = wb("ACTOR_TYPE30_COLLECT_MIN")
TYPE30_METER_STEP = wb("ACTOR_TYPE30_METER_STEP")
TYPE30_CURSOR = wb("ACTOR_TYPE30_CURSOR")
# ...and slot 17's PAIR of them, the tier's only other global cursors, named here beside slot 30's
# so `HANDLER_GLOBALS` below can key on all three.
TYPE17_DX_CURSOR = wb("ACTOR_TYPE17_DX_CURSOR")
TYPE17_DY_CURSOR = wb("ACTOR_TYPE17_DY_CURSOR")
TYPE30_DRIFT = wb("ACTOR_TYPE30_DRIFT")
TYPE30_DRIFT_MASK = wb("ACTOR_TYPE30_DRIFT_MASK")
TYPE30_DRIFT_STRIDE = wb("ACTOR_TYPE30_DRIFT_STRIDE")
RECORD_PTR_10424 = wb("RECORD_PTR_10424")
SCENE_GOLD_AWARD = wb("SCENE_GOLD_AWARD")
BCD_RANDOM_MASK = wb("BCD_RANDOM_MASK")
GOLD_DIGITS_AT = wb("TEXT_GOLD_DIGITS")
MESSAGE_GOLD_GET = wb("TEXT_MESSAGE_GOLD_GET")
BCD_DIGIT_MASK = wb("BCD_DIGIT_MASK")
BCD_DIGIT_BITS = wb("BCD_DIGIT_BITS")
DIGIT_ZERO = wb("TEXT_DIGIT_ZERO")
DIGIT_BLANK = wb("TEXT_DIGIT_BLANK")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")

# --- batch 38: slot 38 and the pickup tier ---------------------------------------------------------
A6 = 6
KIND = wb("ACTOR_KIND")
KIND_TABLE = wb("ACTOR_KIND_TABLE")
KIND_RECORD_BYTES = wb("ACTOR_KIND_RECORD_BYTES")
KIND_RECORD_SHIFT = wb("ACTOR_KIND_RECORD_SHIFT")
KIND_TABLE_ROWS = wb("ACTOR_KIND_TABLE_ROWS")
KIND_SCORE = wb("ACTOR_KIND_SCORE")
KIND_PICKUP_EFFECT = wb("ACTOR_KIND_PICKUP_EFFECT")
PICKUP_KIND_FIRST = wb("ACTOR_PICKUP_KIND_FIRST")
PANEL_FRAME_DELAY = wb("PANEL_FRAME_DELAY")
PANEL_FRAME_DELAY_INIT = wb("PANEL_FRAME_DELAY_INIT")
PICKUP_METER_STEP = wb("PICKUP_METER_STEP")
TEXT_REQUEST_NONE = wb("TEXT_REQUEST_NONE")
PICKUP_EFFECT_TABLE = wb("PICKUP_EFFECT_TABLE")
PICKUP_EFFECT_ENTRY = wb("PICKUP_EFFECT_ENTRY")
PICKUP_EFFECT_ENTRIES = wb("PICKUP_EFFECT_ENTRIES")
TYPE38_FLASH = wb("ACTOR_TYPE38_FLASH")
TYPE38_FIELD_12_RELOAD = wb("ACTOR_TYPE38_FIELD_12_RELOAD")
STAGE_NUMBER = wb("STAGE_NUMBER")
BONUS_DIGITS_AT = wb("TEXT_BONUS_DIGITS")
BONUS_DIGIT_COUNT = wb("TEXT_BONUS_DIGIT_COUNT")
MESSAGE_BONUS_POINTS = wb("TEXT_MESSAGE_BONUS_POINTS")
BONUS_DIGITS = "text_post_bonus_points_a4be"
TYPE38 = "actor_behavior_type38_pickup"
DISPATCH_PICKUP_REFUSED = wb("ACTOR_DISPATCH_PICKUP_REFUSED")

# --- batch 34: slots 32..37, the rest of the $4e38..$5407 band -------------------------------------
FIELD_10 = wb("ACTOR_FIELD_10")
TYPE32_WALKING = wb("ACTOR_TYPE32_WALKING")
TYPE32_HOPS_SPENT = wb("ACTOR_TYPE32_HOPS_SPENT")
TYPE32_LATCH_SET = wb("ACTOR_TYPE32_LATCH_SET")
TYPE32_CURSOR = wb("ACTOR_TYPE32_CURSOR")
TYPE32_WALK_STEP = wb("ACTOR_TYPE32_WALK_STEP")
PANEL_FRAME_REWIND = wb("PANEL_FRAME_REWIND")
PANEL_FRAME_REWIND_SET = wb("PANEL_FRAME_REWIND_SET")
PANEL_FRAME_HOLD = wb("PANEL_FRAME_HOLD")
PANEL_FRAME_HOLD_SET = wb("PANEL_FRAME_HOLD_SET")
TYPE34_ITEM1_X = wb("ACTOR_TYPE34_ITEM1_X")
TYPE34_MIDDLE_X = wb("ACTOR_TYPE34_MIDDLE_X")
TYPE34_ITEM2_X = wb("ACTOR_TYPE34_ITEM2_X")
TYPE34_MIDDLE_Y = wb("ACTOR_TYPE34_MIDDLE_Y")
TYPE34_ITEM_Y = wb("ACTOR_TYPE34_ITEM_Y")
JOY1_LEFT_BIT = wb("JOY1_LEFT_BIT")
JOY1_RIGHT_BIT = wb("JOY1_RIGHT_BIT")
JOY1_FIRE_BIT = wb("JOY1_FIRE_BIT")
SHOP_RECORD_PTR = wb("SHOP_RECORD_PTR")
SHOP_ITEM1_CURSOR_MSG = wb("SHOP_ITEM1_CURSOR_MSG")
SHOP_ITEM2_CURSOR_MSG = wb("SHOP_ITEM2_CURSOR_MSG")
SHOP_REQUEST = wb("SHOP_REQUEST")
SHOP_REQUEST_ITEM1 = wb("SHOP_REQUEST_ITEM1")
SHOP_REQUEST_ITEM2 = wb("SHOP_REQUEST_ITEM2")
SHOP_REQUEST_FAREWELL = wb("SHOP_REQUEST_FAREWELL")
SCENE_MESSAGE_PENDING = wb("SCENE_MESSAGE_PENDING")
SCENE_ACK_WAIT = wb("SCENE_ACK_WAIT")
TEXT_REQUEST_DISMISS = wb("TEXT_REQUEST_DISMISS")
EVENT_ANIM_CURSOR = wb("ACTOR_EVENT_ANIM_CURSOR")
EVENT_ANIM_FRAMES = wb("ACTOR_EVENT_ANIM_FRAMES")
EVENT_ANIM_MASK = wb("ACTOR_EVENT_ANIM_MASK")
EVENT_ANIM_DONE_B12 = wb("EVENT_ANIM_DONE_B12")
EVENT_ANIM_DONE_B16 = wb("EVENT_ANIM_DONE_B16")
EVENT_DONE_SET = wb("EVENT_DONE_SET")
TYPE37_RISE = wb("ACTOR_TYPE37_RISE")
SCENE_VARIANT = wb("SCENE_VARIANT")
SCENE_MESSAGE_PENDING_SET = wb("SCENE_MESSAGE_PENDING_SET")
RECORD_PTR_10420 = wb("RECORD_PTR_10420")
JOY_INPUT = "joy1_newly_pressed"

# Slot 37's geometry, as a y it starts at and a y it has to reach. The two are far enough apart that
# one frame cannot close the gap, which is what makes "it rose one pixel" and "it arrived" different
# answers; a case that wants the ARRIVAL seeds the record at the target instead.
TYPE37_START_Y = 0x0180
TYPE37_TARGET_Y = 0x0100


# The encodings only this section spells. `abcd_dn_dn` is the reason batch 33 exists in the shape it
# does: out/wonderboy_dis.txt prints $51d4's `c101` as `and.b d0,d1`, and it is an `abcd`.
def abcd_dn_dn(destination, source):
    """`abcd Dy,Dx` — opmode 100 over ea mode 000, which is the encoding an AND cannot have (a byte
    AND with a REGISTER destination would have to write a data register through the `<ea>` half).
    ../names.txt records the same disassembler bug for $b562's `c308`."""
    return opcode(0xc100 | (destination << 9) | source)


def add_b_dn_dn(destination, source):
    return opcode(0xd000 | (destination << 9) | source)


def addq_b_dn(amount, reg):
    return opcode(0x5000 | ((amount & 7) << 9) | reg)
    # ALSO IN test_actor.py — third copy of the ENCODING (test_text.py spells the LONG form off the
    # same base), queued for leaf.py.


def ror_w_imm_dn(count, reg):
    """`ror.w #n,Dn` — a WORD rotate, so the units nibble goes out of the bottom and in at the top
    and the tens nibble lands where the mask below can reach it."""
    return opcode(0xe058 | ((count & 7) << 9) | reg)


def tst_b_abs_w(addr):
    """`tst.b <abs>.w` — the SHORT absolute form, and a BYTE test on a WORD flag: it reads
    WB_FRAME_TOGGLE's high half, which is $00 or $ff and never anything between."""
    return opcode(0x4a38) + word(addr)
    # ALSO IN test_actor.py — second copy, which the rule allows.


def cmp_w_abs_l_dn(reg, addr):
    return opcode(0xb079 | (reg << 9)) + longword(addr)
    # ALSO IN test_stage.py, and as a bare opcode in test_scroll.py (`CMP_W_ABS_L_D0`) and
    # test_scene.py — third copy, queued for leaf.py.


def move_w_dn_abs_l(reg, addr):
    return opcode(0x33c0 | reg) + longword(addr)
    # ALSO IN test_scroll.py, test_stage.py — third copy, queued for leaf.py, and the one whose home
    # already exists: leaf.py owns both mirrors (`move_w_abs_l_dn`, `move_b_dn_abs_l`).


def move_w_dn_abs_w(reg, addr):
    """`move.w Dn,<abs>.w` — the SHORT mirror of `move_w_dn_abs_l` above, and the whole of what
    separates slot 36's cursor store from slot 35's: the two write the same address in the two
    absolute forms, so a scan for one encoding finds only half of the four sites."""
    return opcode(0x31c0 | reg) + word(addr)


def move_l_imm_ind(reg, value):
    """`move.l #imm,(An)` — how slot 34 plants a menu position over WB_ACTOR_X and WB_ACTOR_Y as
    ONE write. First copy anywhere: no other battery has a LONGWORD immediate stored through a bare
    address register."""
    return opcode(0x20bc | (reg << 9)) + longword(value)


def move_w_abs_l_abs_l(source, destination):
    """`move.w <abs>.l,<abs>.l` — TEN bytes, and the only instruction in the tier that moves a word
    between two fixed addresses without a register in between."""
    return opcode(0x33f9) + longword(source) + longword(destination)


def _gold_digits_pieces():
    """$51d8 — units, then tens, and the tens arm is the one that branches."""
    return [
        move_w_dn_dn(D1, D0),
        andi_w_dn(D1, BCD_DIGIT_MASK),
        addi_b_dn(D1, DIGIT_ZERO),
        leaf.move_b_dn_abs_l(D1, GOLD_DIGITS_AT + 1),
        ror_w_imm_dn(BCD_DIGIT_BITS, D0),
        andi_w_dn(D0, BCD_DIGIT_MASK),
        _bcc(BNE_W, "digit"),
        leaf.move_b_imm_abs_l(DIGIT_BLANK, GOLD_DIGITS_AT),
        RTS,
        _lab("digit"),
        addi_b_dn(D0, DIGIT_ZERO),
        leaf.move_b_dn_abs_l(D0, GOLD_DIGITS_AT),
        RTS,
    ]


def _bcd_random_pieces():
    """$51ac — four byte reads in a FIXED order (the two hardware ones first), the mask, the step
    that guarantees X = 0, and the `abcd` that makes d0 the result."""
    return [
        moveq_0_dn(D1),
        leaf.move_b_abs_l_dn(D2, leaf.VIDEO_COUNTER_LOW),
        add_b_dn_dn(D1, D2),
        leaf.move_b_abs_l_dn(D2, leaf.VIDEO_COUNTER_MID),
        add_b_dn_dn(D1, D2),
        leaf.move_b_abs_l_dn(D2, FOLLOWED_DEFAULT),
        add_b_dn_dn(D1, D2),
        leaf.move_b_abs_l_dn(D2, FOLLOWED_DEFAULT + 1),
        add_b_dn_dn(D1, D2),
        andi_b_dn(D1, BCD_RANDOM_MASK),
        addq_b_dn(1, D1),
        abcd_dn_dn(D0, D1),
        RTS,
    ]


def _award_pieces():
    """$517a — the payout, and every `bsr` displacement in it comes out of ../names.txt."""
    return [
        leaf.movea_l_abs_l(A1, RECORD_PTR_10424),
        move_w_ind_dn(D0, A1, SCENE_GOLD_AWARD),
        _bsr(BCD_RANDOM),
        _bsr(ADD_COUNTER),
        _bsr(GOLD_DIGITS),
        move_l_imm_dn(D0, COLLECT_SCORE),
        _bsr(ADD_SCORE),
        leaf.move_b_imm_abs_l(MESSAGE_GOLD_GET, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        RTS,
    ]


def _type28_pieces():
    return [
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "wait"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "wait"),
        _bsr(SOUND_REQUEST_9),
        move_w_imm_ind(A0, FREE_MARKER),
        move_w_imm_dn(D0, TYPE28_GOLD),
        _bsr(ADD_COUNTER),
        move_l_imm_dn(D0, COLLECT_SCORE),
        _bsr(ADD_SCORE),
        _bcc(BRA_W, "out"),
        _lab("wait"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(RELAUNCH_5160),
        # `moveq #0,d7` first: the step is the WHOLE of d7 and carries nothing of the settle's.
        moveq_0_dn(D7),
        move_b_d16_dn(D7, A0, FIELD_31),
        _bcc(BEQ_W, "countdown"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "blocked?"),
        _lab("left"),
        _bsr(STEP_LEFT),
        _lab("blocked?"),
        # THE WORD TEST. Every other blocked-step test in this file is `tst_b_dn`.
        tst_w_dn(D0),
        _bcc(BNE_W, "step-done"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("step-done"),
        subq_b_d16(1, A0, FIELD_31),
        _lab("countdown"),
        subq_b_d16(1, A0, FIELD_12),
        _bcc(BNE_W, "out"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "free"),
        move_b_imm_d16(A0, TYPE28_FIELD_12_RELOAD, FIELD_12),
        RTS,
        _lab("free"),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type30_pieces():
    return [
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "wait"),
        cmpi_b_d16(A0, TYPE30_COLLECT_MIN, FIELD_30),
        _bcc(BLT_W, "wait"),
        _bsr(SOUND_REQUEST_9),
        leaf.move_w_abs_l_dn(D0, METER_VALUE),
        addq_w_dn(TYPE30_METER_STEP, D0),
        cmp_w_abs_l_dn(D0, METER_MAX),
        # The sum is DISCARDED on this arm: `blt` leaves d0 unstored.
        _bcc(BLT_W, "free"),
        move_w_abs_l_abs_l(METER_MAX, METER_VALUE),
        _bcc(BRA_W, "free"),
        _lab("wait"),
        addq_b_d16(1, A0, FIELD_30),
        tst_b_abs_w(FRAME_TOGGLE),
        _bcc(BEQ_W, "drift"),
        subq_w_d16(1, A0, ACTOR_Y),
        _lab("drift"),
        leaf.move_w_abs_l_dn(D0, TYPE30_CURSOR),
        _lea_pc_indexed(A1, D0, TYPE30_DRIFT),
        move_w_ind_dn(D1, A1),
        add_w_dn_ind(D1, A0),
        addq_w_dn(TYPE30_DRIFT_STRIDE, D0),
        andi_w_dn(D0, TYPE30_DRIFT_MASK),
        move_w_dn_abs_l(D0, TYPE30_CURSOR),
        cmpi_w_d16(A0, FLICKER_AT_FIELD_12, FIELD_12),
        _bcc(BNE_W, "tick"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _lab("tick"),
        subq_w_d16(1, A0, FIELD_12),
        _bcc(BNE_W, "out"),
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        clr_w_abs_l(TYPE30_CURSOR),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type31_pieces():
    """SEVENTY-EIGHT bytes with TWO exits. The body ends in its own `rts` at $4fe8 — which is why
    the last piece here is `RTS` — and the LIVE-countdown arm leaves through the `bne.w $4fea` four
    instructions above it, into actor_select_sprite_by_flag, whose 48 bytes are pinned as a routine
    of their own. It is that routine's ENTRY that bounds this one at 78 bytes."""
    return [
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        cmpi_w_d16(A0, FLICKER_AT_FIELD_12, FIELD_12),
        _bcc(BNE_W, "collect?"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _lab("collect?"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "tick"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "tick"),
        _bsr(SOUND_REQUEST_9),
        _bsr(AWARD),
        _bcc(BRA_W, "free"),
        _lab("tick"),
        subq_w_d16(1, A0, FIELD_12),
        _bcc_abs(BNE_W, leaf.entry_of(SELECT_SPRITE)),
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        move_w_imm_ind(A0, FREE_MARKER),
        RTS,
    ]


# --- batch 34: slots 32..37 --------------------------------------------------------------------
def _type32_pieces():
    """278 bytes. The `bsr.s` on the second line is the whole reason `_bsr_s` exists in this file
    and it is not cosmetic: $501a's thirty-six callers spell it long everywhere else, and only this
    one is close enough to reach short."""
    return [
        _bsr(FALL_AND_SETTLE),
        _bsr_s(HOP_ASCEND),
        leaf.tst_b_abs_l(TYPE32_WALKING),
        _bcc(BNE_W, "contact"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "hop"),
        _lab("contact"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "hop"),
        _bsr(SOUND_REQUEST_9),
        _bsr(AWARD),
        _bcc(BRA_W, "free"),
        _lab("hop"),
        leaf.tst_b_abs_l(TYPE32_HOPS_SPENT),
        _bcc(BNE_W, "walk?"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "walk?"),
        leaf.st_abs_l(TYPE32_WALKING),
        subq_b_d16(1, A0, FIELD_10),
        _bcc(BNE_W, "launch"),
        leaf.st_abs_l(TYPE32_HOPS_SPENT),
        _bcc(BRA_W, "walk?"),
        _lab("launch"),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        # The speed is RE-READ out of the field the `subq.b` above stored, not reused from d0.
        move_b_d16_dn(D0, A0, FIELD_10),
        move_b_dn_d16(D0, A0, SPEED),
        _lab("walk?"),
        leaf.tst_b_abs_l(TYPE32_WALKING),
        _bcc(BEQ_W, "age"),
        # actor_step_facing's own body, inline — and a `move.w` of the step in BOTH arms, so d7's
        # high half never reaches the probes.
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "right"),
        move_w_imm_dn(D7, TYPE32_WALK_STEP),
        _bsr(STEP_LEFT),
        tst_b_dn(D0),
        _bcc(BNE_W, "age"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BRA_W, "age"),
        _lab("right"),
        move_w_imm_dn(D7, TYPE32_WALK_STEP),
        _bsr(STEP_RIGHT),
        tst_b_dn(D0),
        _bcc(BNE_W, "age"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("age"),
        cmpi_w_d16(A0, FLICKER_AT_FIELD_12, FIELD_12),
        _bcc(BNE_W, "tick"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _lab("tick"),
        subq_w_d16(1, A0, FIELD_12),
        _bcc(BNE_W, "anim"),
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        # A WORD clear over the two latch BYTES, then a `clr.b` over the second of them again.
        clr_w_abs_l(TYPE32_WALKING),
        leaf.clr_b_abs_l(TYPE32_HOPS_SPENT),
        move_w_imm_ind(A0, FREE_MARKER),
        _bcc(BRA_W, "out"),
        _lab("anim"),
        leaf.move_w_abs_l_dn(D0, TYPE32_CURSOR),
        lea_abs_l(A1, ANIM_5160_FRAMES),
        lea_indexed(A1, D0),
        # ...and NOT the post-increment $6872 publishes with, which is why the sentinel below is
        # read at 2(a1) here and at (a1) there — the same word, two spellings.
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        cmpi_w_d16(A1, ANIM_5160_END, ANIM_FRAME_BYTES),
        _bcc(BNE_W, "store"),
        clr_w_dn(D0),
        _lab("store"),
        move_w_dn_abs_l(D0, TYPE32_CURSOR),
        _lab("out"),
        RTS,
    ]


def _type33_pieces():
    return [
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "wait"),
        _bsr(SOUND_REQUEST_9),
        move_w_imm_abs_l(PANEL_FRAME_REWIND_SET, PANEL_FRAME_REWIND),
        move_w_imm_abs_l(PANEL_FRAME_HOLD_SET, PANEL_FRAME_HOLD),
        move_l_imm_dn(D0, COLLECT_SCORE),
        _bsr(ADD_SCORE),
        _bcc(BRA_W, "free"),
        _lab("wait"),
        cmpi_w_d16(A0, FLICKER_AT_FIELD_12, FIELD_12),
        _bcc(BNE_W, "tick"),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        _lab("tick"),
        subq_w_d16(1, A0, FIELD_12),
        _bcc(BNE_W, "out"),
        _lab("free"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        move_w_imm_ind(A0, FREE_MARKER),
        _lab("out"),
        RTS,
    ]


def _type34_position(x, y):
    """The longword one arm plants over WB_ACTOR_X and WB_ACTOR_Y together, composed from the same
    two constants the `cmpi.w`s read rather than transcribed as a literal."""
    return move_l_imm_ind(A0, (x << 16) | y)


def _type34_pieces():
    """220 bytes and SEVEN `rts`, one per arm — the two gates and the three direction bits each
    leave by their own."""
    return [
        tst_w_abs_l(SCENE_MESSAGE_PENDING),
        _bcc(BNE_W, "out"),
        tst_w_abs_l(SCENE_ACK_WAIT),
        _bcc(BNE_W, "out"),
        _bsr(JOY_INPUT),
        btst_imm_dn(JOY1_LEFT_BIT, D0),
        _bcc(BNE_W, "left"),
        btst_imm_dn(JOY1_RIGHT_BIT, D0),
        _bcc(BNE_W, "right"),
        btst_imm_dn(JOY1_FIRE_BIT, D0),
        _bcc(BNE_W, "fire"),
        RTS,
        _lab("left"),
        cmpi_w_ind(A0, TYPE34_ITEM2_X),
        _bcc(BEQ_W, "middle"),
        cmpi_w_ind(A0, TYPE34_MIDDLE_X),
        _bcc(BEQ_W, "item1"),
        RTS,
        _lab("right"),
        cmpi_w_ind(A0, TYPE34_ITEM1_X),
        _bcc(BEQ_W, "middle"),
        cmpi_w_ind(A0, TYPE34_MIDDLE_X),
        _bcc(BEQ_W, "item2"),
        RTS,
        _lab("middle"),
        # The dismiss alone: no lifetime is posted beside it, where both item arms post one.
        leaf.move_b_imm_abs_l(TEXT_REQUEST_DISMISS, TEXT_REQUEST),
        _type34_position(TYPE34_MIDDLE_X, TYPE34_MIDDLE_Y),
        RTS,
        _lab("item2"),
        leaf.movea_l_abs_l(A1, SHOP_RECORD_PTR),
        move_w_ind_dn(D0, A1, SHOP_ITEM2_CURSOR_MSG),
        leaf.move_b_dn_abs_l(D0, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        _type34_position(TYPE34_ITEM2_X, TYPE34_ITEM_Y),
        RTS,
        _lab("item1"),
        leaf.movea_l_abs_l(A1, SHOP_RECORD_PTR),
        move_w_ind_dn(D0, A1, SHOP_ITEM1_CURSOR_MSG),
        leaf.move_b_dn_abs_l(D0, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        _type34_position(TYPE34_ITEM1_X, TYPE34_ITEM_Y),
        RTS,
        _lab("fire"),
        cmpi_w_ind(A0, TYPE34_ITEM1_X),
        _bcc(BNE_W, "fire2"),
        move_w_imm_abs_l(SHOP_REQUEST_ITEM1, SHOP_REQUEST),
        RTS,
        _lab("fire2"),
        cmpi_w_ind(A0, TYPE34_ITEM2_X),
        _bcc(BNE_W, "fire3"),
        move_w_imm_abs_l(SHOP_REQUEST_ITEM2, SHOP_REQUEST),
        RTS,
        _lab("fire3"),
        cmpi_w_ind(A0, TYPE34_MIDDLE_X),
        _bcc(BNE_W, "out"),
        move_w_imm_abs_l(SHOP_REQUEST_FAREWELL, SHOP_REQUEST),
        _lab("out"),
        RTS,
    ]


def _event_anim_pieces(cursor_lea, cursor_store):
    """The six instructions slots 35 and 36 share, with the two absolute FORMS the caller supplies —
    long in slot 35 and short in slot 36. One pin taken twice rather than two transcriptions, which
    is `_face_and_step_pieces`'s shape."""
    return [
        cursor_lea,
        move_w_postinc_dn(D0, A1),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        addq_w_dn(ANIM_FRAME_BYTES, D0),
        andi_w_dn(D0, EVENT_ANIM_MASK),
        cursor_store,
        _bcc(BNE_W, "out"),
    ]


def _type35_pieces():
    return [
        *_event_anim_pieces(lea_abs_l(A1, EVENT_ANIM_CURSOR),
                            move_w_dn_abs_l(D0, EVENT_ANIM_CURSOR)),
        leaf.move_w_imm_abs_w(EVENT_DONE_SET, EVENT_ANIM_DONE_B12),
        _lab("out"),
        RTS,
    ]


def _type36_pieces():
    return [
        *_event_anim_pieces(lea_abs_w(A1, EVENT_ANIM_CURSOR),
                            move_w_dn_abs_w(D0, EVENT_ANIM_CURSOR)),
        leaf.move_w_imm_abs_w(EVENT_DONE_SET, EVENT_ANIM_DONE_B16),
        # ...and the one instruction slot 35 does not have: the record RETYPES itself to slot 0.
        leaf.clr_w_d16(A0, ACTOR_TYPE),
        _lab("out"),
        RTS,
    ]


def _type37_pieces():
    return [
        leaf.movea_l_abs_l(A1, RECORD_PTR_10420),
        move_w_ind_dn(D0, A1, SCENE_VARIANT),
        subi_w_dn(D0, TYPE37_RISE),
        cmp_w_d16_dn(D0, A0, ACTOR_Y),
        _bcc(BEQ_W, "arrived"),
        subq_w_d16(1, A0, ACTOR_Y),
        _bcc(BRA_W, "out"),
        _lab("arrived"),
        leaf.move_w_imm_abs_w(EVENT_DONE_SET, EVENT_ANIM_DONE_B16),
        _lab("out"),
        RTS,
    ]


# --- batch 35: the monster-prologue family, dispatch rows 9..13 ------------------------------------
# The same three openings slots 2..6 have, and five middles that share nothing but their shape. Each
# pin below runs to the handler's own last `rts`; BODY_SIZES states where that is.
RANDOM_HOP = "actor_random_facing_hop"
STEP_FACING = "actor_step_facing"
FACE_TOWARD = "actor_face_and_step_toward"
FACE_AWAY4 = "actor_face_and_step_away4"
TICK_TIMER30 = "actor_tick_timer30"
ANIM_LIST = "actor_anim_step_facing_list"
TOWARD = "actor_step_toward_followed"

RANDOM_HOP_RNG_BIT = wb("ACTOR_RANDOM_HOP_RNG_BIT")
RANDOM_HOP_SPEED = wb("ACTOR_RANDOM_HOP_SPEED")


def _launch_inline_pieces(speed):
    """`bset #0 / bset #1 / bclr #2` of the flag byte and the speed as a LITERAL — the four writes
    src/behavior.c calls `launch_at_inline_speed`, spelt at four sites in this band."""
    return [
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, speed, SPEED),
    ]


def _memory_cursor_pieces(offset, mask):
    """`addq.b #2,d16(a0) / andi.b #mask,d16(a0)` — the cursor stepped as TWO read-modify-writes on
    memory, which is what separates slots 10 and 13's cursors from every other one in the tier."""
    return [addq_b_d16(ANIM_FRAME_BYTES, A0, offset), andi_b_d16(A0, mask, offset)]


def _random_hop_pieces():
    return [
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "airborne"),
        _bsr(RNG_NEXT),
        btst_imm_dn(RANDOM_HOP_RNG_BIT, D0),
        _bcc(BNE_W, "face-right"),
        bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BRA_W, "launch"),
        _lab("face-right"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("launch"),
        *_launch_inline_pieces(RANDOM_HOP_SPEED),
        _lab("airborne"),
        RTS,
    ]


def _list_pair_pieces(list_pair):
    """`lea $pair.l,a1 / bsr $3006` — how slots 9 and 12 publish, where the other three index a word
    table themselves."""
    return [lea_abs_l(A1, list_pair), _bsr(ANIM_LIST)]


def _hurt_tail_pieces(done_label):
    """`bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8` — the four bytes of tail four of the five hurt
    animations end on. The defeated bit is TESTED, not cleared."""
    return [
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        _lab(done_label),
        RTS,
    ]


def _type09_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        move_w_imm_dn(D7, wb("ACTOR_TYPE09_WALK_STEP")),
        _bsr(STEP_FACING),
        _bsr(RANDOM_HOP),
        *_list_pair_pieces(wb("ACTOR_TYPE09_WALK_LISTS")),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(PLAYER_GATE),
        _bsr(FACE_AWAY4),
        *_list_pair_pieces(wb("ACTOR_TYPE09_HURT_LISTS")),
        # The cursor RE-READ out of memory after $3006 stored it, which is what the wrap is read off.
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type10_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "fly"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("fly"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_31),
        lea_abs_l(A1, wb("ACTOR_TYPE10_HOVER")),
        lea_indexed(A1, D0),
        move_w_ind_dn(D1, A1),
        add_w_dn_d16(D1, A0, ACTOR_Y),
        *_memory_cursor_pieces(FIELD_31, wb("ACTOR_TYPE10_HOVER_MASK")),
        _bcc(BNE_W, "drift"),
        _bsr(FOLLOWED_RECORD),
        move_w_imm_dn(D0, wb("ACTOR_TYPE10_CLOSE_STEP")),
        move_w_ind_dn(D1, A0, ACTOR_Y),
        cmp_w_d16_dn(D1, A1, ACTOR_Y),
        _bcc(BLT_W, "close"),
        neg_w_dn(D0),
        _lab("close"),
        add_w_dn_d16(D0, A0, ACTOR_Y),
        _lab("drift"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "drift-left"),
        addq_w_ind(wb("ACTOR_TYPE10_DRIFT_STEP"), A0),
        _bcc(BRA_W, "timer"),
        _lab("drift-left"),
        subq_w_ind(wb("ACTOR_TYPE10_DRIFT_STEP"), A0),
        _lab("timer"),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "turn"),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "anim"),
        _lab("turn"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, wb("ACTOR_TYPE10_TURN_FRAMES"), FIELD_30),
        move_w_imm_dn(D7, wb("ACTOR_TYPE10_HOME_STEP")),
        _bsr(TOWARD),
        _lab("anim"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "anim-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE10_WALK_RIGHT")),
        _bcc(BRA_W, "publish"),
        _lab("anim-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE10_WALK_LEFT")),
        _lab("publish"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        *_memory_cursor_pieces(FIELD_18, ANIM16_MASK),
        RTS,
        _lab("hurt"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "hurt-anim"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE10_HURT_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "hurt-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "hurt-anim"),
        _lab("hurt-left"),
        _bsr(STEP_LEFT),
        _lab("hurt-anim"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "hurt-left-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE10_HURT_RIGHT")),
        _bcc(BRA_W, "hurt-publish"),
        _lab("hurt-left-frames"),
        lea_abs_l(A1, wb("ACTOR_TYPE10_HURT_LEFT")),
        _lab("hurt-publish"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type11_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "decide"),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "step"),
        _lab("decide"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE11_RELOAD"), FIELD_30),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "decided"),
        _bsr(RNG_NEXT),
        btst_imm_dn(wb("ACTOR_TYPE11_FACE_RNG_BIT"), D0),
        _bcc(BEQ_W, "face-right"),
        bit_op_d16(BSET_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BRA_W, "hop-test"),
        _lab("face-right"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("hop-test"),
        btst_imm_dn(wb("ACTOR_TYPE11_HOP_RNG_BIT"), D0),
        _bcc(BNE_W, "decided"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE11_HOP_SPEED")),
        _bcc_abs(BRA_W, leaf.entry_of(START_MOTION)),
        _lab("decided"),
        RTS,
        # $32b2..$32db is actor_step_facing's body inline, with the step spelt in EACH arm.
        _lab("step"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "step-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE11_WALK_STEP")),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "turn-test"),
        _lab("step-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE11_WALK_STEP")),
        _bsr(STEP_RIGHT),
        _lab("turn-test"),
        tst_b_dn(D0),
        _bcc(BNE_W, "walk-anim"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("walk-anim"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "walk-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE11_WALK_RIGHT")),
        _bcc(BRA_W, "walk-publish"),
        _lab("walk-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE11_WALK_LEFT")),
        _lab("walk-publish"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        RTS,
        _lab("hurt"),
        # The `moveq` is BEFORE the table select here, so one clear serves both arms.
        moveq_0_dn(D0),
        bit_op_d16(BTST_IMM, wb("ACTOR_TYPE11_HURT_BIT"), A0, FIELD_30),
        _bcc(BNE_W, "hurt-marked"),
        lea_abs_l(A1, wb("ACTOR_TYPE11_HURT_PLAIN")),
        _bcc(BRA_W, "hurt-publish"),
        _lab("hurt-marked"),
        lea_abs_l(A1, wb("ACTOR_TYPE11_HURT_MARKED")),
        _lab("hurt-publish"),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM16_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type12_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        move_w_imm_dn(D7, wb("ACTOR_TYPE12_WALK_STEP")),
        _bsr(FACE_TOWARD),
        _bsr(TICK_TIMER30),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "ground"),
        *_list_pair_pieces(wb("ACTOR_TYPE12_AIR_LISTS")),
        RTS,
        _lab("ground"),
        *_list_pair_pieces(wb("ACTOR_TYPE12_GROUND_LISTS")),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(PLAYER_GATE),
        _bsr(FACE_AWAY4),
        *_list_pair_pieces(wb("ACTOR_TYPE12_HURT_LISTS")),
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type13_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "hop"),
        *_monster_struck(),
        _lab("hop"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "hop-anim"),
        *_launch_inline_pieces(wb("ACTOR_TYPE13_HOP_SPEED")),
        _lab("hop-anim"),
        lea_abs_l(A1, wb("ACTOR_TYPE13_FRAMES")),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        *_memory_cursor_pieces(FIELD_18, ANIM16_MASK),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BNE_W, "throe"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE13_DEATH_FRAMES"), FIELD_31),
        st_d16(A0, FIELD_30),
        *_launch_inline_pieces(wb("ACTOR_TYPE13_DEATH_SPEED")),
        _bsr(SIDE_FLAG),
        _lab("throe"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE13_HURT_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "throe-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "throe-frame"),
        _lab("throe-left"),
        _bsr(STEP_LEFT),
        _lab("throe-frame"),
        move_w_imm_d16(A0, wb("ACTOR_TYPE13_HURT_SPRITE"), ACTOR_SPRITE),
        subq_b_d16(1, A0, FIELD_31),
        _bcc(BNE_W, "alive"),
        clr_b_d16(A0, FIELD_30),
        # The ONE unconditional transfer into the defeat in the whole family.
        _bcc_abs(BRA_W, leaf.entry_of(DEFEAT)),
        _lab("alive"),
        RTS,
    ]


TURN_LAUNCH = "actor_turn_and_launch"


def subi_b_dn(reg, value):
    return opcode(0x0400 | reg) + word(value & 0xff)
    # ALSO IN test_text.py — second copy, which the rule allows.


def _index_and_publish_pieces(mask, indexed=False):
    """`move.b 18(a0),d0 / lea 0(a1,d0.w),a1 / move.w (a1),6(a0) / addi.b #2,d0 / andi.b #mask,d0 /
    move.b d0,18(a0)` — publish on the RAW cursor and store the MASKED step, in the one register.
    Nine of batch 36's eleven frame reads spell it, and slot 18's hurt arm folds the `lea` and the
    `move.w` into one `move.w 0(a1,d0.w),6(a0)` instead, which `indexed` selects."""
    fetch = ([move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE)] if indexed
             else [lea_indexed(A1, D0), move_w_ind_d16(A1, A0, ACTOR_SPRITE)])
    return [
        move_b_d16_dn(D0, A0, FIELD_18),
        *fetch,
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, mask),
        move_b_dn_d16(D0, A0, FIELD_18),
    ]


def _table_by_facing_pieces(left, right, label):
    """`btst #3,8(a0) / bne / lea right / bra / lea left` — the frame-table select, and the branch
    polarity is the SAME at all eight of this batch's sites: the SET arm is the LEFT table."""
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, f"{label}-left"),
        lea_abs_l(A1, right),
        _bcc(BRA_W, f"{label}-publish"),
        _lab(f"{label}-left"),
        lea_abs_l(A1, left),
        _lab(f"{label}-publish"),
    ]


def _alloc_pieces(full_label):
    """`bsr $1b8e / cmpa.l #$0,a1 / beq <full>` — the allocation and the refusal branch every
    spawner in this batch opens with. Where a full pool GOES differs per slot, so it is a label."""
    return [_bsr(ALLOC_HIGH), cmpa_l_imm(A1, 0), _bcc(BEQ_W, full_label)]


def _companion_pieces(type_word, full_label):
    """The WHOLE spawn slots 16 and 18 share: the x/y longword, a type, the parent's flag byte, the
    speed, the size longword and the two cursors. The only difference between the two is the type."""
    return [
        *_alloc_pieces(full_label),
        move_l_ind_ind(A0, A1),
        move_w_imm_d16(A1, type_word, ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_b_imm_d16(A1, wb("ACTOR_MINION_SPEED"), SPEED),
        move_l_imm_d16(A1, wb("ACTOR_MINION_SIZE"), HALF_WIDTH),
        leaf.clr_w_d16(A1, FIELD_30),
        clr_b_d16(A1, FIELD_18),
        RTS,
    ]


def _type14_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "turn"),
        subq_b_d16(1, A0, FIELD_30),
        tst_b_d16(A0, FIELD_31),
        _bcc(BEQ_W, "drop"),
        subq_b_d16(1, A0, FIELD_31),
        _bcc(BRA_W, "step"),
        _lab("drop"),
        *_alloc_pieces("done"),
        move_l_ind_ind(A0, A1),
        move_w_imm_d16(A1, wb("ACTOR_TYPE14_MINION_TYPE"), ACTOR_TYPE),
        move_l_imm_d16(A1, wb("ACTOR_MINION_SIZE"), HALF_WIDTH),
        move_b_imm_d16(A1, wb("ACTOR_TYPE14_MINION_TIMER"), FIELD_30),
        clr_b_d16(A1, FIELD_31),
        clr_b_d16(A1, FIELD_18),
        # BELOW the failed-allocation branch, so a full pool leaves the gap byte at zero.
        move_b_imm_d16(A0, wb("ACTOR_TYPE14_SPAWN_GAP"), FIELD_31),
        RTS,
        _lab("turn"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, wb("ACTOR_TYPE14_TURN_FRAMES"), FIELD_30),
        RTS,
        _lab("step"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "step-right"),
        # `move.b` — the LOW BYTE alone, over whatever actor_fall_and_settle left in d7.
        move_b_imm_dn(D7, wb("ACTOR_TYPE14_WALK_STEP")),
        _bsr(STEP_LEFT),
        _bsr(TOGGLE_SIDE),
        _bcc(BRA_W, "walk-anim"),
        _lab("step-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE14_WALK_STEP")),
        _bsr(STEP_RIGHT),
        _bsr(TOGGLE_SIDE),
        _lab("walk-anim"),
        *_table_by_facing_pieces(wb("ACTOR_TYPE14_WALK_LEFT"), wb("ACTOR_TYPE14_WALK_RIGHT"),
                                 "walk"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM32_MASK),
        RTS,
        _lab("hurt"),
        # The `lea` sits between the `moveq` and the cursor read here — ONE table for both facings.
        moveq_0_dn(D0),
        lea_abs_l(A1, wb("ACTOR_TYPE14_HURT")),
        *_index_and_publish_pieces(ANIM16_MASK),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _defeat_first_tail_pieces(done_label):
    """`btst #3,9(a0) / bne.w $6bb8 / bclr #0,9(a0)` — slots 15 and 16 read the two marks in the
    OTHER order from `_hurt_tail_pieces`: a record that transfers keeps BOTH."""
    return [
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc_abs(BNE_W, leaf.entry_of(DEFEAT)),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        _lab(done_label),
        RTS,
    ]


def _type15_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "step-left"),
        # `move.w` in BOTH arms, so the settle's register cannot reach the step.
        move_w_imm_dn(D7, wb("ACTOR_TYPE15_WALK_STEP")),
        _bsr(STEP_RIGHT),
        lea_abs_l(A1, wb("ACTOR_TYPE15_WALK_RIGHT")),
        _bsr(TURN_LAUNCH),
        _bcc(BRA_W, "walk-publish"),
        _lab("step-left"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE15_WALK_STEP")),
        _bsr(STEP_LEFT),
        lea_abs_l(A1, wb("ACTOR_TYPE15_WALK_LEFT")),
        _bsr(TURN_LAUNCH),
        _lab("walk-publish"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        # The walk arm steps its cursor IN MEMORY; the hurt arm below does it in d0.
        *_memory_cursor_pieces(FIELD_18, ANIM16_MASK),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        moveq_0_dn(D0),
        *_table_by_facing_pieces(wb("ACTOR_TYPE15_HURT_LEFT"), wb("ACTOR_TYPE15_HURT_RIGHT"),
                                 "hurt"),
        *_index_and_publish_pieces(ANIM32_MASK),
        _bcc(BNE_W, "done"),
        *_defeat_first_tail_pieces("done"),
    ]


def _type16_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(SIDE_FLAG),
        *_table_by_facing_pieces(wb("ACTOR_TYPE16_WALK_LEFT"), wb("ACTOR_TYPE16_WALK_RIGHT"),
                                 "walk"),
        *_cursor_into(A1),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        *_memory_cursor_pieces(FIELD_18, ANIM16_MASK),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "launch"),
        subq_b_d16(1, A0, FIELD_30),
        RTS,
        _lab("launch"),
        # `bclr` is the TEST and the write: the branch reads the bit as it WAS.
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "done"),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, wb("ACTOR_TYPE16_HOP_SPEED"), SPEED),
        move_b_imm_d16(A0, wb("ACTOR_TYPE16_RELOAD"), FIELD_30),
        *_companion_pieces(wb("ACTOR_TYPE16_MINION_TYPE"), "done"),
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        moveq_0_dn(D0),
        *_table_by_facing_pieces(wb("ACTOR_TYPE16_HURT_LEFT"), wb("ACTOR_TYPE16_HURT_RIGHT"),
                                 "hurt"),
        *_index_and_publish_pieces(ANIM32_MASK),
        _bcc(BNE_W, "done"),
        *_defeat_first_tail_pieces("done"),
    ]


def _type17_drift_pieces(field, cursor_at, table, mask, add_piece):
    """`move.w $cursor.l,d0 / lea $table.l,a1 / lea 0(a1,d0.w),a1 / move.w (a1)+,d1 /
    add.w d1,<field> / addi.w #2,d0 / andi.w #mask,d0 / move.w d0,$cursor.l` — one axis of the
    drift, and the cursor is a GLOBAL word rather than a record byte."""
    return [
        leaf.move_w_abs_l_dn(D0, cursor_at),
        lea_abs_l(A1, table),
        lea_indexed(A1, D0),
        move_w_postinc_dn(D1, A1),
        add_piece,
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, mask),
        move_w_dn_abs_l(D0, cursor_at),
    ]


def _type17_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "drift"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("drift"),
        _bsr(SIDE_FLAG),
        *_list_pair_pieces(wb("ACTOR_TYPE17_LIVE_LISTS")),
        *_type17_drift_pieces(ACTOR_X, wb("ACTOR_TYPE17_DX_CURSOR"), wb("ACTOR_TYPE17_DX"),
                              wb("ACTOR_TYPE17_DX_MASK"), add_w_dn_ind(D1, A0)),
        *_type17_drift_pieces(ACTOR_Y, wb("ACTOR_TYPE17_DY_CURSOR"), wb("ACTOR_TYPE17_DY"),
                              wb("ACTOR_TYPE17_DY_MASK"), add_w_dn_d16(D1, A0, ACTOR_Y)),
        # The seeding fires on the frame the Y cursor WRAPS, and nothing else reads that branch.
        _bcc(BNE_W, "drifted"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE17_SEED_DBF_COUNT")),
        move_w_imm_dn(D6, wb("ACTOR_TYPE17_SEED_FIRST")),
        _bsr(RNG_NEXT),
        andi_w_dn(D0, wb("ACTOR_TYPE17_SEED_ODDS_MASK")),
        _bcc(BNE_W, "drifted"),
        # The `dbf` closes back onto the ALLOCATION, so five separate records are taken and the
        # first refusal ends the whole burst.
        _lab("seed"),
        *_alloc_pieces("drifted"),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_b_dn_d16(D6, A1, FIELD_30),
        subi_b_dn(D6, 1),
        move_l_ind_ind(A0, A1),
        move_l_imm_d16(A1, wb("ACTOR_TYPE17_SEED_SIZE"), HALF_WIDTH),
        move_w_imm_d16(A1, wb("ACTOR_TYPE17_SEED_TYPE"), ACTOR_TYPE),
        bit_op_d16(BSET_IMM, MOVING_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS),
        move_b_imm_d16(A1, wb("ACTOR_TYPE17_SEED_SPEED"), SPEED),
        dbf_to(D7, "seed"),
        _lab("drifted"),
        RTS,
        _lab("hurt"),
        *_list_pair_pieces(wb("ACTOR_TYPE17_HURT_LISTS")),
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type18_pieces():
    return [
        *_monster_prologue("hurt"),
        # The body arm FLIPS the facing, and `bsr $67c2` sits on the POINT arm alone.
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "walk"),
        _bsr(SIDE_FLAG),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "charge-test"),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "step"),
        _lab("charge-test"),
        tst_b_d16(A0, FIELD_31),
        _bcc(BNE_W, "landing"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE18_CHARGING"), FIELD_31),
        move_b_d16_d16(A0, ACTOR_FLAGS, A0, FIELD_29),
        _bsr(SIDE_FLAG),
        move_w_imm_dn(D0, wb("ACTOR_TYPE18_HOP_SPEED")),
        _bsr(START_MOTION),
        *_companion_pieces(wb("ACTOR_TYPE18_MINION_TYPE"), "done"),
        _lab("landing"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "walk-anim"),
        move_b_d16_d16(A0, FIELD_29, A0, ACTOR_FLAGS),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, wb("ACTOR_TYPE18_TURN_FRAMES"), FIELD_30),
        clr_b_d16(A0, FIELD_31),
        RTS,
        _lab("step"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "step-right"),
        move_b_imm_dn(D7, wb("ACTOR_TYPE18_WALK_STEP")),
        _bsr(STEP_LEFT),
        _bsr(TOGGLE_SIDE),
        _bcc(BRA_W, "walk-anim"),
        _lab("step-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE18_WALK_STEP")),
        _bsr(STEP_RIGHT),
        _bsr(TOGGLE_SIDE),
        _lab("walk-anim"),
        *_table_by_facing_pieces(wb("ACTOR_TYPE18_WALK_LEFT"), wb("ACTOR_TYPE18_WALK_RIGHT"),
                                 "walk"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM32_MASK),
        RTS,
        # THE HURT ARM'S TABLE SELECT IS THE RETREAT'S OWN BRANCH: the undefeated arm steps away and
        # falls into the list its `btst` already chose; only the defeated arm tests the bit again.
        _lab("hurt"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "hurt-marked"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE18_HURT_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "retreat-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "hurt-left"),
        _lab("retreat-left"),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "hurt-right"),
        _lab("hurt-marked"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "hurt-left"),
        _lab("hurt-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE18_HURT_RIGHT")),
        _bcc(BRA_W, "hurt-publish"),
        _lab("hurt-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE18_HURT_LEFT")),
        _lab("hurt-publish"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM16_MASK, indexed=True),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type19_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "glide-test"),
        _bsr(SIDE_FLAG),
        *_monster_struck(),
        _lab("glide-test"),
        tst_b_d16(A0, FIELD_31),
        _bcc(BNE_W, "attack"),
        move_w_imm_d16(A0, wb("ACTOR_TYPE19_GLIDE_SPRITE"), ACTOR_SPRITE),
        move_w_imm_d16(A0, wb("ACTOR_TYPE19_GLIDE_HEIGHT"), SIZE_SECOND),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_30),
        lea_abs_l(A1, wb("ACTOR_TYPE19_DRIFT")),
        lea_indexed(A1, D0),
        move_w_ind_dn(D1, A1),
        add_w_dn_ind(D1, A0),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, wb("ACTOR_TYPE19_DRIFT_MASK")),
        move_b_dn_d16(D0, A0, FIELD_30),
        _bcc(BNE_W, "done"),
        st_d16(A0, FIELD_31),
        RTS,
        _lab("attack"),
        move_w_imm_d16(A0, wb("ACTOR_TYPE19_ATTACK_HEIGHT"), SIZE_SECOND),
        _bsr(SIDE_FLAG),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "frames-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE19_FRAMES_RIGHT")),
        _bcc(BRA_W, "cursor"),
        _lab("frames-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE19_FRAMES_LEFT")),
        _lab("cursor"),
        moveq_0_dn(D7),
        move_b_d16_dn(D7, A0, FIELD_18),
        cmp_w_imm_dn(D7, wb("ACTOR_TYPE19_SHOT_CURSOR")),
        _bcc(BNE_W, "attack-publish"),
        # AND THE ALLOCATION OVERWRITES a1 — the very register the frame table was `lea`d into.
        *_alloc_pieces("attack-publish"),
        move_l_ind_ind(A0, A1),
        subq_w_d16(wb("ACTOR_TYPE19_SHOT_RISE"), A1, ACTOR_Y),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "shot-left"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE19_SHOT_DX_RIGHT")),
        _bcc(BRA_W, "shot-x"),
        _lab("shot-left"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE19_SHOT_DX_LEFT")),
        _lab("shot-x"),
        add_w_dn_ind(D0, A1),
        move_w_imm_d16(A1, wb("ACTOR_TYPE19_SHOT_TYPE"), ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, wb("ACTOR_TYPE19_SHOT_SIZE"), HALF_WIDTH),
        leaf.clr_w_d16(A1, FIELD_30),
        clr_b_d16(A1, FIELD_18),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS),
        _lab("attack-publish"),
        lea_indexed(A1, D7),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D7, ANIM_FRAME_BYTES),
        andi_b_dn(D7, wb("ACTOR_TYPE19_FRAME_MASK")),
        move_b_dn_d16(D7, A0, FIELD_18),
        _bcc(BNE_W, "done"),
        clr_b_d16(A0, FIELD_31),
        RTS,
        _lab("hurt"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "death"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        RTS,
        _lab("death"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        lea_abs_l(A1, wb("ACTOR_TYPE19_DEATH")),
        lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, ANIM32_MASK),
        move_b_dn_d16(D0, A0, FIELD_18),
        _bcc(BNE_W, "done"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        # The family's SECOND unconditional transfer into the defeat, after slot 13's.
        _bcc_abs(BRA_W, leaf.entry_of(DEFEAT)),
        _lab("done"),
        RTS,
    ]



AIM_VELOCITY = "actor_aim_velocity"
BCD_SUB_COUNTER = "bcd_sub_counter_bd6e"
# Slot 25's hurt wrap branches to SLOT 18's `rts`, so the address is DERIVED rather than
# transcribed: slot 18's body is bounded above by its own first frame table, and its last two bytes
# are that `rts`. A body that moved would carry this with it instead of silently missing.
TYPE18_RTS = wb("ACTOR_TYPE18_WALK_LEFT") - len(RTS)

# --- batch 37's eight, and the four shapes they share ---------------------------------------------
# THE BODY ARM COMES IN A SECOND ENCODING. Slots 20 and 27 spell it as ONE `bne.w $69fe` where every
# other handler in the family spells `beq <point> / <body arm> / bra.w $69fe`; the two are the same
# mapping and different bytes, so the pin has to know which.
def _monster_contact_direct(walk_label):
    return [
        _bsr(HIT_BY_SHOT),
        tst_w_dn(D7),
        _bcc(BNE_W, "struck"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc_abs(BNE_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        btst_imm_dn(POINT_BIT, D0),
        _bcc(BEQ_W, walk_label),
    ]


def _retreat_pieces(step, label):
    """`btst #3,8(a0) / beq / bsr $1170 / bra / bsr $10a2` — the step AWAY four handlers in this
    block spell, with the SET arm walking right. The two arms JOIN on `label`."""
    return [
        move_w_imm_dn(D7, step),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, f"{label}-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, label),
        _lab(f"{label}-left"),
        _bsr(STEP_LEFT),
    ]


def _hopper_pieces(walk_left, walk_right, hurt_left, hurt_right, air_left, air_right):
    """SLOTS 20 AND 27, whose 378 bytes are the same instructions twice. Only the six operands
    below differ, which is why one builder pins both — and a case asserts the two really are equal
    once the operands are substituted."""
    return [
        *_monster_prologue("hurt"),
        *_monster_contact_direct("walk"),
        _bsr(SIDE_FLAG),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "step"),
        _bsr(SIDE_FLAG),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BPL_W, "step"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE20_HOP_RELOAD"), FIELD_30),
        _bsr(RNG_NEXT),
        btst_imm_dn(wb("ACTOR_TYPE20_HOP_RNG_BIT"), D0),
        _bcc(BNE_W, "step"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE20_HOP_SPEED")),
        _bcc_abs(BRA_W, leaf.entry_of(START_MOTION)),
        _lab("step"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE20_WALK_STEP")),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "step-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "turn-test"),
        _lab("step-left"),
        _bsr(STEP_LEFT),
        _lab("turn-test"),
        # `tst.w d0` — the WORD test, which only slot 28 spells anywhere else in the tier.
        tst_w_dn(D0),
        _bcc(BNE_W, "anim"),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _lab("anim"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "airborne"),
        moveq_0_dn(D0),
        *_table_by_facing_pieces(walk_left, walk_right, "walk"),
        *_index_and_publish_pieces(ANIM16_MASK),
        RTS,
        _lab("airborne"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "air-left"),
        move_w_imm_d16(A0, air_right, ACTOR_SPRITE),
        RTS,
        _lab("air-left"),
        move_w_imm_d16(A0, air_left, ACTOR_SPRITE),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(SIDE_FLAG),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "hurt-anim"),
        *_retreat_pieces(wb("ACTOR_TYPE20_HURT_STEP"), "hurt-anim"),
        _lab("hurt-anim"),
        *_table_by_facing_pieces(hurt_left, hurt_right, "hurt"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM32_MASK),
        _bcc(BNE_W, "done"),
        # `st 30(a0)` ABOVE the two mark instructions: the recovered record's next live frame finds
        # its countdown already negative.
        st_d16(A0, FIELD_30),
        *_hurt_tail_pieces("done"),
    ]


def _type20_pieces():
    return _hopper_pieces(wb("ACTOR_TYPE20_WALK_LEFT"), wb("ACTOR_TYPE20_WALK_RIGHT"),
                          wb("ACTOR_TYPE20_HURT_LEFT"), wb("ACTOR_TYPE20_HURT_RIGHT"),
                          wb("ACTOR_TYPE20_AIR_LEFT"), wb("ACTOR_TYPE20_AIR_RIGHT"))


def _type27_pieces():
    return _hopper_pieces(wb("ACTOR_TYPE27_WALK_LEFT"), wb("ACTOR_TYPE27_WALK_RIGHT"),
                          wb("ACTOR_TYPE27_HURT_LEFT"), wb("ACTOR_TYPE27_HURT_RIGHT"),
                          wb("ACTOR_TYPE27_AIR_LEFT"), wb("ACTOR_TYPE27_AIR_RIGHT"))


def _type21_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "idle"),
        _bsr(SIDE_FLAG),
        *_monster_struck(),
        _lab("idle"),
        _bsr(SIDE_FLAG),
        tst_b_d16(A0, FIELD_30),
        _bcc(BNE_W, "aim"),
        *_table_by_facing_pieces(wb("ACTOR_TYPE21_WALK_LEFT"), wb("ACTOR_TYPE21_WALK_RIGHT"),
                                 "walk"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM32_MASK),
        _bcc(BNE_W, "done"),
        st_d16(A0, FIELD_30),
        RTS,
        _lab("aim"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE21_REACH")),
        _bsr(WITHIN),
        tst_w_dn(D0),
        _bcc(BMI_W, "done"),
        _bsr(RNG_NEXT),
        andi_w_dn(D0, wb("ACTOR_TYPE21_SHOT_ODDS_MASK")),
        _bcc(BNE_W, "done"),
        _bsr(FOLLOWED_RECORD),
        movea_l_an(A2, A1),
        # CLEARED ABOVE THE ALLOCATION, so a refused shot still puts the record back in its idle
        # half — where slot 14's refused drop leaves its own gap byte standing.
        clr_b_d16(A0, FIELD_30),
        *_alloc_pieces("done"),
        move_l_ind_ind(A0, A1),
        subq_w_d16(wb("ACTOR_TYPE21_SHOT_RISE"), A1, ACTOR_Y),
        move_w_imm_d16(A1, wb("ACTOR_TYPE21_SHOT_TYPE"), ACTOR_TYPE),
        move_b_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, wb("ACTOR_TYPE21_SHOT_SIZE"), HALF_WIDTH),
        move_w_ind_dn(D0, A0),
        move_w_ind_dn(D1, A0, ACTOR_Y),
        move_w_ind_dn(D2, A2),
        move_w_ind_dn(D3, A2, ACTOR_Y),
        move_w_imm_dn(D4, wb("ACTOR_TYPE21_AIM_ROW")),
        _bsr(AIM_VELOCITY),
        move_b_dn_d16(D0, A1, FIELD_30),
        # `clr.w d1` OVERWRITES the dy the table returned when the two records are level.
        move_w_ind_dn(D7, A0, ACTOR_Y),
        cmp_w_d16_dn(D7, A2, ACTOR_Y),
        _bcc(BNE_W, "store-dy"),
        clr_w_dn(D1),
        _lab("store-dy"),
        move_b_dn_d16(D1, A1, FIELD_31),
        move_b_imm_d16(A1, wb("ACTOR_TYPE21_SHOT_LIFE"), FIELD_29),
        clr_b_d16(A1, FIELD_18),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS),
        RTS,
        _lab("hurt"),
        moveq_0_dn(D0),
        *_table_by_facing_pieces(wb("ACTOR_TYPE21_HURT_LEFT"), wb("ACTOR_TYPE21_HURT_RIGHT"),
                                 "hurt"),
        *_index_and_publish_pieces(ANIM16_MASK),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type22_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "launch-test"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("launch-test"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(SIDE_FLAG),
        tst_b_d16(A0, FIELD_30),
        _bcc(BNE_W, "tick"),
        # `bclr #2,8(a0) / beq` is the TEST AND THE WRITE, so an airborne record stores its flag
        # byte unchanged and then falls into the `subq`, which wraps the countdown to $ff.
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "tick"),
        move_b_imm_d16(A0, wb("ACTOR_TYPE22_RELOAD"), FIELD_30),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, wb("ACTOR_TYPE22_LAUNCH_SPEED"), SPEED),
        _bcc(BRA_W, "anim"),
        _lab("tick"),
        subq_b_d16(1, A0, FIELD_30),
        _lab("anim"),
        *_list_pair_pieces(wb("ACTOR_TYPE22_LIVE_LISTS")),
        tst_w_abs_l(wb("ACTOR_TYPE53_ALIVE")),
        _bcc(BNE_W, "done"),
        _bsr(RNG_NEXT),
        andi_b_dn(D0, wb("ACTOR_TYPE22_SEED_ODDS_MASK")),
        _bcc(BNE_W, "done"),
        *_alloc_pieces("done"),
        move_l_ind_ind(A0, A1),
        subi_w_d16(A1, wb("ACTOR_TYPE22_MINION_RISE"), ACTOR_Y),
        move_w_imm_d16(A1, wb("ACTOR_TYPE22_MINION_TYPE"), ACTOR_TYPE),
        # `move.w 8(a0),8(a1)` — a WORD, so WB_ACTOR_FLAGS2 crosses with the flag byte.
        move_w_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_b_imm_d16(A1, wb("ACTOR_TYPE22_MINION_TIMER"), FIELD_30),
        move_l_imm_d16(A1, wb("ACTOR_TYPE22_MINION_SIZE"), HALF_WIDTH),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(PLAYER_GATE),
        _bsr(FACE_AWAY4),
        *_list_pair_pieces(wb("ACTOR_TYPE22_HURT_LISTS")),
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _type23_pieces():
    """SLOT 4's BODY with a different contact arm — and one branch that LEAVES for slot 4's own
    publish, which is what makes this handler's extent not the whole of what it runs."""
    return [
        *_monster_prologue("hurt"),
        _bsr(HIT_BY_SHOT),
        tst_w_dn(D7),
        _bcc(BNE_W, "struck"),
        _bsr(OVERLAP),
        btst_imm_dn(BODY_BIT, D0),
        _bcc(BEQ_W, "point"),
        # THE THEFT, and its two refusals both fall into the damage the ordinary body arm does.
        _bsr(FOLLOWED_RECORD),
        bit_op_d16(BTST_IMM, FLICKER_BIT, A1, ACTOR_FLAGS),
        _bcc_abs(BNE_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        tst_w_abs_l(BCD_COUNTER),
        _bcc_abs(BEQ_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        leaf.cmpi_w_abs_l(wb("ACTOR_TYPE23_STEAL_MAX"), BCD_COUNTER),
        _bcc(BGT_W, "charge"),
        clr_w_abs_l(BCD_COUNTER),
        _bcc(BRA_W, "loot"),
        _lab("charge"),
        move_w_imm_dn(D0, wb("ACTOR_TYPE23_STEAL_MAX")),
        _bsr(BCD_SUB_COUNTER),
        _lab("loot"),
        *_alloc_pieces("stun"),
        move_l_ind_ind(A0, A1),
        move_w_imm_d16(A1, wb("ACTOR_TYPE23_LOOT_TYPE"), ACTOR_TYPE),
        move_b_imm_d16(A1, wb("ACTOR_TYPE23_LOOT_TIMER"), FIELD_30),
        clr_b_d16(A1, FIELD_18),
        # BELOW the refusal branch: on a full pool a1 is 0 and this lands at address FIELD_21.
        _lab("stun"),
        move_b_imm_d16(A1, wb("ACTOR_TYPE23_STUN_FRAMES"), FIELD_21),
        _bcc_abs(BRA_W, leaf.entry_of(DAMAGE_FOLLOWED)),
        _lab("point"),
        btst_imm_dn(POINT_BIT, D0),
        _bcc(BEQ_W, "chase"),
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
        lea_abs_l(A1, wb("ACTOR_TYPE23_FLY_LEFT")),
        _bcc(BRA_W, "fly-anim"),
        _lab("level-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE23_FLY_RIGHT")),
        # THE ONE BRANCH THAT LEAVES: slot 4's publish-and-hover tail, not this handler's copy.
        _bcc_abs(BRA_W, wb("ACTOR_TYPE04_FLY_PUBLISH")),
        _lab("fly-left"),
        lea_abs_l(A1, wb("ACTOR_TYPE23_FLY_LEFT")),
        move_w_imm_dn(D7, wb("ACTOR_TYPE23_FLY_STEP")),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "fly-anim"),
        _lab("fly-right"),
        lea_abs_l(A1, wb("ACTOR_TYPE23_FLY_RIGHT")),
        move_w_imm_dn(D7, wb("ACTOR_TYPE23_FLY_STEP")),
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
        # SLOT 4's HOVER TABLE, through the SHORT absolute encoding where slot 4 uses the long one.
        lea_abs_w(A1, wb("ACTOR_TYPE04_HOVER")),
        leaf.move_w_indexed_dn(D1, A1, D0),
        add_w_dn_d16(D1, A0, ACTOR_Y),
        addi_b_dn(D0, ANIM_FRAME_BYTES),
        andi_b_dn(D0, wb("ACTOR_TYPE04_HOVER_MASK")),
        move_b_dn_d16(D0, A0, FIELD_30),
        RTS,
        _lab("hurt"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "dead-right"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE23_DEAD_STEP")),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-left-frames"),
        _bsr(STEP_LEFT),
        _lab("dead-left-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE23_DEAD_LEFT")),
        _bcc(BRA_W, "dead-anim"),
        _lab("dead-right"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "dead-right-frames"),
        move_w_imm_dn(D7, wb("ACTOR_TYPE23_DEAD_STEP")),
        _bsr(STEP_RIGHT),
        _lab("dead-right-frames"),
        moveq_0_dn(D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        _lea_pc_indexed(A1, D0, wb("ACTOR_TYPE23_DEAD_RIGHT")),
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


def _type24_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        _bsr(SIDE_FLAG),
        move_w_imm_dn(D7, wb("ACTOR_TYPE24_WALK_STEP")),
        _bsr(STEP_FACING),
        *_list_pair_pieces(wb("ACTOR_TYPE24_LIVE_LISTS")),
        # THE TAIL IS SLOT 17's: this is where the handler's own bytes end.
        _bcc_abs(BRA_W, wb("ACTOR_TYPE17_SEED_BURST")),
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        *_list_pair_pieces(wb("ACTOR_TYPE24_HURT_LISTS")),
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
    ]


def _charger_pieces(walk_left, walk_right, hurt_left, hurt_right, charging, hop_speed,
                    turn_frames, minion_type, walk_step, hurt_step, wrap_branch):
    """SLOTS 18 AND 25, whose 424 bytes are the same instructions twice. `wrap_branch` is the one
    structural difference: slot 18 skips to its own `rts` and slot 25 branches to SLOT 18's."""
    return [
        *_monster_prologue("hurt"),
        # The body arm FLIPS the facing, and `bsr $67c2` sits on the POINT arm alone.
        *_monster_contact([bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)], "walk"),
        _bsr(SIDE_FLAG),
        *_monster_struck(),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        tst_b_d16(A0, FIELD_30),
        _bcc(BEQ_W, "charge-test"),
        subq_b_d16(1, A0, FIELD_30),
        _bcc(BRA_W, "step"),
        _lab("charge-test"),
        tst_b_d16(A0, FIELD_31),
        _bcc(BNE_W, "landing"),
        move_b_imm_d16(A0, charging, FIELD_31),
        move_b_d16_d16(A0, ACTOR_FLAGS, A0, FIELD_29),
        _bsr(SIDE_FLAG),
        move_w_imm_dn(D0, hop_speed),
        _bsr(START_MOTION),
        *_companion_pieces(minion_type, "done"),
        _lab("landing"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "walk-anim"),
        move_b_d16_d16(A0, FIELD_29, A0, ACTOR_FLAGS),
        bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, turn_frames, FIELD_30),
        clr_b_d16(A0, FIELD_31),
        RTS,
        _lab("step"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "step-right"),
        move_b_imm_dn(D7, walk_step),
        _bsr(STEP_LEFT),
        _bsr(TOGGLE_SIDE),
        _bcc(BRA_W, "walk-anim"),
        _lab("step-right"),
        move_w_imm_dn(D7, walk_step),
        _bsr(STEP_RIGHT),
        _bsr(TOGGLE_SIDE),
        _lab("walk-anim"),
        *_table_by_facing_pieces(walk_left, walk_right, "walk"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM32_MASK),
        RTS,
        # THE HURT ARM'S TABLE SELECT IS THE RETREAT'S OWN BRANCH: the undefeated arm steps away and
        # falls into the list its `btst` already chose; only the defeated arm tests the bit again.
        _lab("hurt"),
        bit_op_d16(BTST_IMM, DEFEATED_BIT, A0, FLAGS2),
        _bcc(BNE_W, "hurt-marked"),
        move_w_imm_dn(D7, hurt_step),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "retreat-left"),
        _bsr(STEP_RIGHT),
        _bcc(BRA_W, "hurt-left"),
        _lab("retreat-left"),
        _bsr(STEP_LEFT),
        _bcc(BRA_W, "hurt-right"),
        _lab("hurt-marked"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        _bcc(BNE_W, "hurt-left"),
        _lab("hurt-right"),
        lea_abs_l(A1, hurt_right),
        _bcc(BRA_W, "hurt-publish"),
        _lab("hurt-left"),
        lea_abs_l(A1, hurt_left),
        _lab("hurt-publish"),
        moveq_0_dn(D0),
        *_index_and_publish_pieces(ANIM16_MASK, indexed=True),
        wrap_branch,
        *_hurt_tail_pieces("done"),
    ]


def _type18_pieces():
    return _charger_pieces(wb("ACTOR_TYPE18_WALK_LEFT"), wb("ACTOR_TYPE18_WALK_RIGHT"),
                           wb("ACTOR_TYPE18_HURT_LEFT"), wb("ACTOR_TYPE18_HURT_RIGHT"),
                           wb("ACTOR_TYPE18_CHARGING"), wb("ACTOR_TYPE18_HOP_SPEED"),
                           wb("ACTOR_TYPE18_TURN_FRAMES"), wb("ACTOR_TYPE18_MINION_TYPE"),
                           wb("ACTOR_TYPE18_WALK_STEP"), wb("ACTOR_TYPE18_HURT_STEP"),
                           _bcc(BNE_W, "done"))


def _type25_pieces():
    return _charger_pieces(wb("ACTOR_TYPE25_WALK_LEFT"), wb("ACTOR_TYPE25_WALK_RIGHT"),
                           wb("ACTOR_TYPE25_HURT_LEFT"), wb("ACTOR_TYPE25_HURT_RIGHT"),
                           wb("ACTOR_TYPE25_CHARGING"), wb("ACTOR_TYPE25_HOP_SPEED"),
                           wb("ACTOR_TYPE25_TURN_FRAMES"), wb("ACTOR_TYPE25_MINION_TYPE"),
                           wb("ACTOR_TYPE25_WALK_STEP"), wb("ACTOR_TYPE25_HURT_STEP"),
                           _bcc_abs(BNE_W, TYPE18_RTS))


def _type26_pieces():
    return [
        *_monster_prologue("hurt"),
        *_monster_contact([], "walk"),
        *_monster_struck([_bsr(SIDE_FLAG)]),
        _lab("walk"),
        _bsr(FALL_AND_SETTLE),
        _bsr(HOP_ASCEND),
        move_w_imm_dn(D7, wb("ACTOR_TYPE26_STEP")),
        _bsr(FACE_TOWARD),
        _bsr(TICK_TIMER30),
        # The MOVING bit, read AFTER the tick that can raise it — where slot 12 reads SUPPORTED.
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        _bcc(BEQ_W, "still"),
        *_alloc_pieces("moving"),
        move_l_ind_ind(A0, A1),
        subi_w_d16(A1, wb("ACTOR_TYPE26_SHOT_RISE"), ACTOR_Y),
        move_w_imm_d16(A1, wb("ACTOR_TYPE26_SHOT_TYPE"), ACTOR_TYPE),
        move_w_d16_d16(A0, ACTOR_FLAGS, A1, ACTOR_FLAGS),
        move_l_imm_d16(A1, wb("ACTOR_TYPE26_SHOT_SIZE"), HALF_WIDTH),
        _lab("moving"),
        *_list_pair_pieces(wb("ACTOR_TYPE26_MOVING_LISTS")),
        RTS,
        _lab("still"),
        *_list_pair_pieces(wb("ACTOR_TYPE26_STILL_LISTS")),
        RTS,
        _lab("hurt"),
        _bsr(FALL_AND_SETTLE),
        _bsr(PLAYER_GATE),
        _bsr(FACE_AWAY4),
        *_list_pair_pieces(wb("ACTOR_TYPE26_HURT_LISTS")),
        tst_b_d16(A0, FIELD_18),
        _bcc(BNE_W, "done"),
        *_hurt_tail_pieces("done"),
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
    "sound_request_9": _sound_request_9_pieces(),
    "actor_stun_followed": _stun_pieces(),
    "actor_behavior_type29": [RTS],
    "actor_platform_release_blocked_rider": _platform_blocked_pieces(),
    "actor_behavior_type02": _type02_pieces(),
    "actor_behavior_type03": _type03_pieces(),
    "actor_behavior_type04": _type04_pieces(),
    "actor_behavior_type05": _type05_pieces(),
    "actor_behavior_type06": _type06_pieces(),
    "actor_swoop_state0_acquire": _swoop_state0_pieces(),
    "actor_swoop_state1_run_path": _swoop_state1_pieces(),
    "actor_swoop_state2_home_x": _swoop_state2_pieces(),
    "actor_swoop_state3_descend": _swoop_state3_pieces(),
    "actor_behavior_type07": _type07_pieces(),
    "actor_behavior_type47": _type47_pieces(),
    "actor_behavior_type48": _type48_pieces(),
    "actor_behavior_type49": _type49_pieces(),
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
    "actor_behavior_type28": _type28_pieces(),
    "actor_behavior_type30": _type30_pieces(),
    "actor_behavior_type31": _type31_pieces(),
    "hud_award_gold_from_descriptor": _award_pieces(),
    "bcd_add_random_1_to_4": _bcd_random_pieces(),
    "text_write_gold_digits_a2ac": _gold_digits_pieces(),
    "actor_behavior_type32": _type32_pieces(),
    "actor_behavior_type33": _type33_pieces(),
    "actor_behavior_type34": _type34_pieces(),
    "actor_behavior_type35": _type35_pieces(),
    "actor_behavior_type36": _type36_pieces(),
    "actor_behavior_type37": _type37_pieces(),
    "actor_behavior_type38_pickup": _type38_pieces(),
    "text_post_bonus_points_a4be": _bonus_digits_pieces(),
    "actor_random_facing_hop": _random_hop_pieces(),
    "actor_behavior_type09": _type09_pieces(),
    "actor_behavior_type10": _type10_pieces(),
    "actor_behavior_type11": _type11_pieces(),
    "actor_behavior_type12": _type12_pieces(),
    "actor_behavior_type13": _type13_pieces(),
    "actor_behavior_type14": _type14_pieces(),
    "actor_behavior_type15": _type15_pieces(),
    "actor_behavior_type16": _type16_pieces(),
    "actor_behavior_type17": _type17_pieces(),
    "actor_behavior_type18": _type18_pieces(),
    "actor_behavior_type19": _type19_pieces(),
    "actor_behavior_type20": _type20_pieces(),
    "actor_behavior_type21": _type21_pieces(),
    "actor_behavior_type22": _type22_pieces(),
    "actor_behavior_type23": _type23_pieces(),
    "actor_behavior_type24": _type24_pieces(),
    "actor_behavior_type25": _type25_pieces(),
    "actor_behavior_type26": _type26_pieces(),
    "actor_behavior_type27": _type27_pieces(),
}
RECONSTRUCTED_ROUTINES = 83

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
    "sound_request_9": 16,              # $6786..$6795, bounded by the stun's own entry
    "actor_stun_followed": 44,          # $6796..$67c1, bounded by actor_set_side_flag's entry
    "actor_behavior_type29": 2,         # $4ec8..$4ec9 — the `rts` between slots 28 and 30
    "actor_platform_release_blocked_rider": 76,   # $6e8c..$6ed7, then the $6ed8 sprite/band rows
    "actor_behavior_type02": 254,       # $2462..$255f, then 96 bytes of frame words
    "actor_behavior_type03": 374,       # $25c0..$2735, then 96
    "actor_behavior_type04": 342,       # $2796..$28eb, then 256 (four lists and the hover table)
    "actor_behavior_type05": 262,       # $29ec..$2af1, bounded by actor_start_motion_at_speed
    "actor_behavior_type06": 490,       # $2bc8..$2db1, then 96
    "actor_swoop_state0_acquire": 102,  # $72c2..$7327, bounded by state 1's entry
    "actor_swoop_state1_run_path": 62,  # $7328..$7365
    "actor_swoop_state2_home_x": 56,    # $7366..$739d
    "actor_swoop_state3_descend": 48,   # $739e..$73cd, then actor_swoop_path_table
    "actor_behavior_type07": 424,       # $7060..$7207, then the two velocity tables at $7208
    "actor_behavior_type47": 42,        # $5928..$5951, then its own sixteen frame words
    "actor_behavior_type48": 86,        # $5972..$59c7, then its own four
    "actor_behavior_type49": 108,       # $59d0..$5a3b, bounded by actor_advance_anim16's entry —
                                        # the eighteen bytes at $5a3c are that routine's, not this
                                        # handler's, and its two frame tables sit above them
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
    "actor_behavior_type28": 144,       # $4e38..$4ec7, bounded by slot 29's bare `rts`
    "actor_behavior_type30": 142,       # $4eca..$4f57, then a $0000 pad, its global cursor at
                                        # $4f5a and its 32-word drift table at $4f5c
    "actor_behavior_type31": 78,        # $4f9c..$4fe9 — NOT 146: the `bne.w $4fea` at the end
                                        # is a branch OUT of the body, into the 48 bytes
                                        # actor_select_sprite_by_flag already owns above it
    "hud_award_gold_from_descriptor": 50,    # $517a..$51ab
    "bcd_add_random_1_to_4": 44,             # $51ac..$51d7
    "text_write_gold_digits_a2ac": 48,       # $51d8..$5207, bounded by slot 33's entry
    "actor_behavior_type32": 278,       # $5046..$515b, bounded by its own three globals
    "actor_behavior_type33": 82,        # $5208..$5259, bounded by slot 34's entry
    "actor_behavior_type34": 220,       # $525a..$5335, bounded by slot 35's entry
    "actor_behavior_type35": 38,        # $5336..$535b — NOT the $5336..$53bb a scan running to the
                                        # next `rts` gives it: $535c is its own cursor, $535e its
                                        # sixteen frame words, $537e the 32-byte record template
                                        # scene_copy_record_fields is handed, and $539e that
                                        # routine's own entry
    "actor_behavior_type36": 38,        # $53bc..$53e1, bounded by slot 37's entry
    "actor_behavior_type37": 38,        # $53e2..$5407, bounded by slot 38's entry
    # Batch 38. The plate figure again, verified here: a difference of dispatch
    # entries gives 236 and the code is 236 — the only row in the tier so far whose
    # extent has NO data in it, because this handler ships no frame table.
    "actor_behavior_type38_pickup": 236,  # $5408..$54f3, bounded by slot 39's entry
    "text_post_bonus_points_a4be": 82,    # $6938..$6989, bounded by the spawn
                                          # animation's entry — NOT 84: the plate
                                          # that called this a six-digit unpack was
                                          # wrong about the count as well
    "actor_random_facing_hop": 64,      # $2f46..$2f85, bounded by actor_tick_timer30's entry
    "actor_behavior_type09": 152,       # $2e12..$2ea9 — NOT the 552 to slot 10's entry: $2eaa is
                                        # its two list PAIRS and $2eba..$2f21 the four lists, and
                                        # $2f22..$3039 above them is SIX shared leaves, five of
                                        # them ported before this batch
    "actor_behavior_type10": 350,       # $303a..$3197, then four 8-word lists and the 32-word
                                        # hover table at $31d8
    "actor_behavior_type11": 324,       # $3218..$335b, then four 8-word lists — and the two 16-byte
                                        # blocks at $338c and $33ac (32 bytes) that repeat two of
                                        # them: no operand site anywhere, but REACHABLE through the
                                        # live table's own `lea` on an over-mask cursor
    "actor_behavior_type12": 174,       # $33bc..$3469, then three list pairs and their six lists
    "actor_behavior_type13": 246,       # $34d2..$35c7, then its own eight frame words — and NO
                                        # padding above them, which is why its over-read lands in
                                        # slot 14's code where slot 11's lands on a copy
    # Batch 36. EVERY ONE OF THESE SIX WAS TAKEN FROM ITS ../names.txt PLATE ("decoded code runs
    # $x..$y") AND THEN VERIFIED HERE, which is batch 35's own instruction: a difference of dispatch
    # entries gives 396/330/408/574/520/652 and the code is 316/234/312/290/424/364. What the gaps
    # hold is this batch's tables, and every byte of every gap is accounted for below.
    "actor_behavior_type14": 316,       # $35d8..$3713, then 32+32 walk words and 16 hurt ones
    "actor_behavior_type15": 234,       # $3764..$384d, then 16+16 walk and 32+32 hurt
    "actor_behavior_type16": 312,       # $38ae..$39e5, then 16+16 walk and 32+32 hurt
    "actor_behavior_type17": 290,       # $3a46..$3b67, then two list PAIRS, their four lists, the
                                        # two GLOBAL cursors at $3bc0/$3bc2 and the 128+64 bytes of
                                        # drift table above them
    "actor_behavior_type18": 424,       # $3c84..$3e2b, then 32+32 walk and 16+16 hurt
    "actor_behavior_type19": 364,       # $3e8c..$3ff7, then 128 bytes of drift, 64+64 of frames
                                        # and 32 of death — ending exactly at slot 20's entry
    # Batch 37, and again every figure came from its ../names.txt plate first: a difference of
    # dispatch entries gives 474/458/352/560/202/520/320/474 and the code is
    # 378/362/264/432/150/424/216/378. Slots 20 and 27 are the SAME 378 bytes twice.
    "actor_behavior_type20": 378,       # $4118..$4291, then 16+16 walk words and 32+32 hurt
    "actor_behavior_type21": 362,       # $42f2..$445b, then 32+32 walk and 16+16 hurt
    "actor_behavior_type22": 264,       # $44bc..$45c3, then two list PAIRS and their four lists
    "actor_behavior_type23": 432,       # $461c..$47cb, then 32+32 dead words and 32+32 fly ones —
                                        # and NO hover table of its own: it reads slot 4's
    "actor_behavior_type24": 150,       # $484c..$48e1, then two PAIRS and their two lists
    "actor_behavior_type25": 424,       # $4916..$4abd, then 32+32 walk and 16+16 hurt
    "actor_behavior_type26": 216,       # $4b1e..$4bf5, then three PAIRS and their six lists
    "actor_behavior_type27": 378,       # $4c5e..$4dd7, then 16+16 walk and 32+32 hurt, ending
                                        # exactly at slot 28's entry
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
# Slot 29's row holds a bare `rts` at an address of its own, so src/behavior.c maps it to
# actor_behavior_null's body: there is no `actor_behavior_type29` symbol to bind glue to, exactly as
# there is none for the null rows. NO_GLUE_TARGETS is what both facts are keyed on.
NO_GLUE_TARGETS = ("actor_behavior_null", "actor_behavior_type29")

PORTED_TARGETS = ("actor_behavior_null", "actor_behavior_type29",
                  "actor_behavior_type02", "actor_behavior_type03", "actor_behavior_type04",
                  "actor_behavior_type05", "actor_behavior_type06", "actor_behavior_type08",
                  "actor_behavior_type07",
                  "actor_behavior_type09", "actor_behavior_type10", "actor_behavior_type11",
                  "actor_behavior_type12", "actor_behavior_type13",
                  "actor_behavior_type14", "actor_behavior_type15", "actor_behavior_type16",
                  "actor_behavior_type17", "actor_behavior_type18", "actor_behavior_type19",
                  "actor_behavior_type20", "actor_behavior_type21", "actor_behavior_type22",
                  "actor_behavior_type23", "actor_behavior_type24", "actor_behavior_type25",
                  "actor_behavior_type26", "actor_behavior_type27",
                  "actor_behavior_type47", "actor_behavior_type48", "actor_behavior_type49",
                  "actor_behavior_type50", "actor_behavior_type51", "actor_behavior_type52",
                  "actor_behavior_type53", "actor_behavior_type54", "actor_behavior_type55",
                  "actor_behavior_type56", "actor_behavior_type59",
                  "actor_behavior_type60", "actor_behavior_type61",
                  "actor_behavior_type28", "actor_behavior_type30",
                  "actor_behavior_type31", "actor_behavior_type32",
                  "actor_behavior_type33", "actor_behavior_type34",
                  "actor_behavior_type35", "actor_behavior_type36",
                  "actor_behavior_type37", "actor_behavior_type38_pickup")
PORTED_SLOTS = tuple(slot for slot, name in sorted(TABLE_TARGETS.items())
                     if name in PORTED_TARGETS)

# HOW MANY ROWS ARE LIVE, as a number a test holds rather than as prose. It has drifted TWICE — the
# README said twenty-two while ../STATUS.md said twenty-three for the whole of batch 32, and neither
# was checked against anything. Every place that states it in words is listed here, so the next
# batch to add a row fails this file instead of a reviewer:
#   * ../STATUS.md's headline ("N of the table's 62 rows are live") and its batch section
#   * ../README.md's src/behavior.c entry and its test/test_behavior.py entry
PORTED_SLOT_COUNT = 52


def test_the_live_row_count_the_docs_state_is_the_one_the_table_has():
    assert len(PORTED_SLOTS) == PORTED_SLOT_COUNT, (
        f"{len(PORTED_SLOTS)} rows are reconstructed, not the {PORTED_SLOT_COUNT} the prose says — "
        f"update PORTED_SLOT_COUNT and the surfaces named beside it")

# THE LAST TWO ALWAYS-TRANSFER HANDLERS ARE GONE (batch 32). Through batch 31 slots 59 and 8 held
# no `rts` at all — each raised a bit and ran into slot 7's body, so what each REPORTED was an
# address, and this file carried a checkpoint table (`ALWAYS_TRANSFER`) to drive them. Slot 7 is
# reconstructed now, both run straight on, and every ported row answers WB_ACTOR_DISPATCH_RAN —
# which the 62 dispatch rows below are what assert. Nothing here needs a second statement of it.
def test_the_header_and_the_image_agree_about_slot_7s_entry():
    """WB_ACTOR_BEHAVIOR_TYPE07 is spelt in wonderboy.h AND named in ../names.txt AND held in the
    image's own table; the three are pinned against each other here because two of them are what
    slots 59 and 8 used to REPORT, and a drift would now be silent."""
    assert BEHAVIOR_TYPE07 == leaf.entry_of("actor_behavior_type07") == _image_slot(7)


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
    # Slot 30's animation cursor is a GLOBAL, so it is written on every waiting frame — which is
    # what puts it here rather than in the record band every other handler's cursor lives in.
    "actor_behavior_type30": [(TYPE30_CURSOR, WORD_BYTES)],
    # ...and slot 32 has THREE of them, the two latch bytes as one word and the cursor beside it.
    "actor_behavior_type32": [(TYPE32_WALKING, WORD_BYTES), (TYPE32_CURSOR, WORD_BYTES)],
    # Slots 35 and 36 share ONE cursor and raise one flag each; slot 37 raises slot 36's.
    "actor_behavior_type35": [(EVENT_ANIM_CURSOR, WORD_BYTES),
                              (EVENT_ANIM_DONE_B12, WORD_BYTES)],
    "actor_behavior_type36": [(EVENT_ANIM_CURSOR, WORD_BYTES),
                              (EVENT_ANIM_DONE_B16, WORD_BYTES)],
    "actor_behavior_type37": [(EVENT_ANIM_DONE_B16, WORD_BYTES)],
    # Slot 17's two DRIFT cursors are globals, so both are written on every live frame — the shape
    # slot 30's cursor has, one axis over.
    "actor_behavior_type17": [(TYPE17_DX_CURSOR, WORD_BYTES), (TYPE17_DY_CURSOR, WORD_BYTES)],
    # Slot 34 writes no record field at all on three of its five arms — what it publishes is the
    # message pair and the shop's request word.
    "actor_behavior_type34": [(TEXT_REQUEST, 1), (TEXT_LIFETIME_REQUEST, WORD_BYTES),
                              (SHOP_REQUEST, WORD_BYTES)],
}

# ...and what the PAYOUT writes is deliberately NOT a row here. Only slot 31's collect arm reaches
# it, and the band those cases pass to `leaf.run` is `merge_bands(_model_award(...))` — derived from
# the model that also states the VALUES, so a band and a model cannot drift apart.


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
from test_sound import PLAY_SONG_INSN_CAP, STUB_INSN_CAP   # noqa: E402

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

# ...and what only slot 7's three rows add, kept OFF the shared bound so every other handler's cap
# stays as tight as its own callees make it. The allocator's body is test_actor.py's and this is an
# upper bound on one call; the burst makes BURST_ALLOCS of them in a `dbf` loop and the dropper one.
ALLOC_INSNS = 200
BURST_ALLOCS = TYPE07_BURST_LAST + 1
DROPPER_ALLOCS = 1
SWOOP_INSNS = sum(INSN_COUNT[name] for name in ("actor_swoop_state0_acquire",
                                                "actor_swoop_state1_run_path",
                                                "actor_swoop_state2_home_x",
                                                "actor_swoop_state3_descend"))
# ONE map probe, not two: only state 3 takes one, and it takes one per frame.
SLOT07_CALLEE_INSNS = (INSN_COUNT["actor_face_followed_reset_22"]
                       + SWOOP_INSNS + MAP_PROBE_INSNS + FOLLOWED_INSNS
                       + (BURST_ALLOCS + DROPPER_ALLOCS) * ALLOC_INSNS)


# ...and what the MONSTER-PROLOGUE family's own leaves add, kept off the shared bound for the same
# reason slot 7's are. Every term is a routine one of slots 9..13 calls that no earlier handler did;
# `rng_next` is reached three different ways (slot 9 through actor_random_facing_hop, slot 11
# directly, slot 12 through actor_tick_timer30) but never twice in one frame.
START_MOTION_INSNS = 5      # $2af2, 24 bytes — three bit writes, the speed store and the `rts`
FAMILY35_CALLEE_INSNS = (INSN_COUNT["actor_step_facing"]
                         + INSN_COUNT["actor_random_facing_hop"]
                         + INSN_COUNT["actor_tick_timer30"]
                         + INSN_COUNT["actor_face_and_step_toward"]
                         + INSN_COUNT["actor_face_and_step_away4"]
                         + INSN_COUNT["actor_anim_step_facing_list"]
                         + INSN_COUNT["actor_step_toward_followed"]
                         + INSN_COUNT["player_gate_on_1516"]
                         + START_MOTION_INSNS + RNG_INSNS + SIDE_FLAG_INSNS + FOLLOWED_INSNS
                         # ONE more probe than the shared bound's two: slot 9's walk takes
                         # actor_step_facing's on top of its own arms'.
                         + MAP_PROBE_INSNS)

# ...and batch 36's, which are the first handlers in this family to ALLOCATE. Slot 17 makes
# WB_ACTOR_TYPE17_SEED_DBF_COUNT + 1 of them in a `dbf` loop and the other four spawners one each, so the
# bound is the burst's; `rng_next` is reached only through slot 17's own draw.
TYPE17_SEEDS = wb("ACTOR_TYPE17_SEED_DBF_COUNT") + 1
TOGGLE_SIDE_INSNS = 6       # $2b82, 12 bytes plus the eight-byte tail it falls into
TURN_LAUNCH_INSNS = 15      # $2b8e, 58 bytes
FAMILY36_CALLEE_INSNS = (INSN_COUNT["actor_anim_step_facing_list"]
                         + TOGGLE_SIDE_INSNS + TURN_LAUNCH_INSNS
                         + START_MOTION_INSNS + RNG_INSNS + SIDE_FLAG_INSNS
                         + TYPE17_SEEDS * ALLOC_INSNS)

# ...and batch 37's, which is the WIDEST bound in the file because slot 24 runs slot 17's whole
# seeding burst on top of its own callees and slot 23 reaches the BCD subtract. Every term is a
# routine one of slots 20..27 can call: the four leaves the family already had, the aim table, and
# the burst's allocations.
AIM_VELOCITY_INSNS = 38     # $6528, 94 bytes — a leaf with no entry pin of its own (see
                            # ../STATUS.md): its shifts and flag reads need eight encoders no
                            # other body in this file spells, and what pins it is the
                            # differential over slot 21's aimed shot rather than a transcription
BCD_SUB_COUNTER_INSNS = 32   # $b582, whose own body test_hud.py pins
FAMILY37_CALLEE_INSNS = (FAMILY36_CALLEE_INSNS
                         + INSN_COUNT["actor_step_facing"]
                         + INSN_COUNT["actor_tick_timer30"]
                         + INSN_COUNT["actor_face_and_step_toward"]
                         + INSN_COUNT["actor_face_and_step_away4"]
                         + INSN_COUNT["player_gate_on_1516"]
                         + AIM_VELOCITY_INSNS + BCD_SUB_COUNTER_INSNS + FOLLOWED_INSNS)


def _handler_cap(name):
    """A handler's instruction cap: its own pinned body plus one bound for every routine anything in
    this file can call. Derived from the pins, so a body that grows carries its cap with it."""
    return INSN_COUNT[name] + HANDLER_CALLEE_INSNS + HANDLER_EXTRA_INSNS.get(name, 0)


# The five slots in the $2462..$2db1 band, in table order — the ones that share the spawn gate.
MONSTER_SLOTS = (2, 3, 4, 5, 6)
MONSTER_HANDLERS = tuple(f"actor_behavior_type{slot:02d}" for slot in MONSTER_SLOTS)

# ...and batch 35's five, which share that band's WHOLE grammar and not merely the gate: the same
# prologue, the same contact enum and the same hurt tail. Kept as a second list rather than folded
# into MONSTER_SLOTS because the cases above state the $2462 band's own frame tables and death
# masks, which these five do not have.
FAMILY35_SLOTS = (9, 10, 11, 12, 13)
FAMILY35_HANDLERS = tuple(f"actor_behavior_type{slot:02d}" for slot in FAMILY35_SLOTS)

# ...and batch 36's six, which are the same family one block on. They are a THIRD list because what
# they add is their own: five of them SPAWN (so their cap carries the allocator), slot 17 publishes
# two globals, and the hurt tail comes in three orders across the six rather than one.
FAMILY36_SLOTS = (14, 15, 16, 17, 18, 19)
FAMILY36_HANDLERS = tuple(f"actor_behavior_type{slot:02d}" for slot in FAMILY36_SLOTS)

# ...and batch 37's eight, which CLOSE the family. A FOURTH list because five of the eight are
# parametrisations of bodies this port already had (20 == 27, 23 == slot 4's, 25 == slot 18's,
# 22 and 26 share slot 9's gated hurt arm) and the three cases below that turn on that are keyed on
# this tuple rather than on the earlier ones.
FAMILY37_SLOTS = (20, 21, 22, 23, 24, 25, 26, 27)
FAMILY37_HANDLERS = tuple(f"actor_behavior_type{slot:02d}" for slot in FAMILY37_SLOTS)
# The two whose HURT arm calls $d78 and therefore reports WB_PLAYER_STEP_BODY while
# WB_TILE_33_MODE is clear; the other three run that arm to their own `rts`.
FAMILY35_BOUNDED = (9, 12)
# ...and batch 37's two, which reach it through the very same `gated_hurt_frame`.
FAMILY37_BOUNDED = (22, 26)

# ...and the three table rows that share slot 7's body, which opens with the same gate. Slot 59's
# prologue writes one global on top of it (HANDLER_GLOBALS), and slot 8's writes nothing extra.
SLOT07_HANDLERS = ("actor_behavior_type07", "actor_behavior_type08", "actor_behavior_type59")

# Every handler whose quietest arm is the spawn animation — the three families that open on
# `btst #2,9(a0)`. Named because `_quiet_record` below is not the only thing that will want it.
SPAWN_GATE_HANDLERS = (MONSTER_HANDLERS + SLOT07_HANDLERS + FAMILY35_HANDLERS
                       + FAMILY36_HANDLERS + FAMILY37_HANDLERS)

# What each handler adds to the shared bound, keyed by NAME — the shape `_handler_band` above
# already uses, rather than an `if` chain that grows a branch per family. A slot absent from the dict
# is bounded by HANDLER_CALLEE_INSNS alone.
# ...and batch 38's, which is the first handler whose frame reaches the packed-BCD accumulators AND
# a second dispatch. Every term is a routine slot 38 can call that no earlier handler did; the two
# digit routines are the only ones here that LOOP, and the bonus one's bound is its own pinned body
# plus eight instructions per character it can draw.
BCD_ADD_INSNS = 32          # $b562/$b5a2, whose bodies test_hud.py pins — BCD_SUB_COUNTER_INSNS's
                            # sibling, and an upper bound on one call for the same reason
PICKUP_EFFECT_INSNS = 20    # the longest of the fourteen: `pickup_effect_vanish_followed`, whose
                            # own call to followed_actor_record is FOLLOWED_INSNS of it
BONUS_DIGIT_LOOP_INSNS = 8  # the longer of $6938's two loop bodies, per character drawn
PICKUP_CALLEE_INSNS = (INSN_COUNT["bcd_add_random_1_to_4"]
                       + INSN_COUNT["text_write_gold_digits_a2ac"]
                       + INSN_COUNT["text_post_bonus_points_a4be"]
                       + BONUS_DIGIT_COUNT * BONUS_DIGIT_LOOP_INSNS
                       + 3 * BCD_ADD_INSNS + RNG_INSNS + PICKUP_EFFECT_INSNS)

HANDLER_EXTRA_INSNS = {name: SLOT07_CALLEE_INSNS for name in SLOT07_HANDLERS}
HANDLER_EXTRA_INSNS.update({name: FAMILY35_CALLEE_INSNS for name in FAMILY35_HANDLERS})
HANDLER_EXTRA_INSNS.update({name: FAMILY36_CALLEE_INSNS for name in FAMILY36_HANDLERS})
HANDLER_EXTRA_INSNS.update({name: FAMILY37_CALLEE_INSNS for name in FAMILY37_HANDLERS})
HANDLER_EXTRA_INSNS[TYPE38] = PICKUP_CALLEE_INSNS


def _quiet_record(name, actor):
    """What a ported handler's record needs for the dispatch case to stay inside
    HANDLER_WRITE_BAND. NINETEEN slots open on the spawn gate (SPAWN_GATE_HANDLERS), so raising
    WB_ACTOR_FLAGS2_SPAWNED_BIT makes the whole frame one animation step; slot 51 is put on its
    FALLING arm with a half-width small enough to bound the settle's own scan; the rest are quietest
    one arm at a time and each says which below."""
    if name in SPAWN_GATE_HANDLERS:
        return {actor + FLAGS2: bytes([1 << SPAWNED_BIT])}
    if name == "actor_behavior_type51":
        return {actor + FLAGS2: bytes([1 << FLAGS2_BIT_0]), actor + HALF_WIDTH: word(4),
                actor + ACTOR_FLAGS: bytes([0])}
    # Slots 48 and 49 have NO arm that skips actor_fall_and_settle, so they get the half-width that
    # bounds its footprint scan rather than an arm; slot 47 has no map, no ground and no callee at
    # all, so nothing it can do leaves the record it was handed.
    if name in ("actor_behavior_type48", "actor_behavior_type49"):
        return {actor + HALF_WIDTH: word(4), actor + ACTOR_FLAGS: bytes([0])}
    # Slots 52 and 53 are quietest on their SWITCH arm, which frees the slot and runs nothing else;
    # slot 60 is quiet while WB_STATE_WORD_6F9C is clear (it publishes one sprite word); slot 61 is
    # quiet while its sequence is armed and the fire button has NOT just gone down, which is the one
    # arm of it that writes nothing at all and the one that does not reach the sound module.
    if name in ("actor_behavior_type52", "actor_behavior_type53"):
        return {actor + FLAGS2: bytes([1 << FLAGS2_BIT_0])}
    if name == "actor_behavior_type60":
        return {STATE_WORD_6F9C: word(0)}
    # The three collectables are quietest with their COLLECT arm shut, and each shuts it a different
    # way: slots 28 and 31 on WB_ACTOR_FLAG_MOVING_BIT being UP (a record mid-hop cannot be picked
    # up) and slot 30 on its own count-up byte being below WB_ACTOR_TYPE30_COLLECT_MIN. Slots 28 and
    # 31 also get the half-width that bounds actor_fall_and_settle's footprint scan, and slot 28 a
    # zero WB_ACTOR_FIELD_31 so its map step is skipped rather than driven off a keyed byte.
    # Slot 38 shuts its collect arm the same way and states its countdown as well, since a keyed
    # byte reaching zero would take the record into actor_defeat_and_score instead of the frame.
    if name in ("actor_behavior_type28", "actor_behavior_type31", TYPE38):
        quiet = {actor + ACTOR_FLAGS: bytes([1 << MOVING_BIT]), actor + HALF_WIDTH: word(4)}
        if name == "actor_behavior_type28":
            quiet[actor + FIELD_31] = bytes([0])
        if name == TYPE38:
            quiet[actor + FIELD_12] = bytes([COLLECT_FIELD_12_IDLE & 0xff])
        return quiet
    if name == "actor_behavior_type30":
        return {actor + FIELD_30: bytes([0])}
    # Slot 32 shuts its collect arm the way slots 28 and 31 do AND with its own latch down — the
    # contact test runs on `walking OR not moving`, so both halves are needed — and its hop machine
    # is shut by the second latch, which leaves the frame the settle, the ascent and one animation
    # frame. Its countdown is stated so a keyed word cannot expire the record instead.
    if name == "actor_behavior_type32":
        return {actor + ACTOR_FLAGS: bytes([1 << MOVING_BIT]), actor + HALF_WIDTH: word(4),
                actor + FIELD_12: word(COLLECT_FIELD_12_IDLE),
                TYPE32_WALKING: bytes([0]), TYPE32_HOPS_SPENT: bytes([TYPE32_LATCH_SET]),
                TYPE32_CURSOR: word(0)}
    # Slot 33 has NO gate on its contact test, so the only way to shut it is the geometry: the
    # tier's own out-of-reach seed, taken from `_type51_pokes` rather than restated.
    if name == "actor_behavior_type33":
        return leaf.overlay(_out_of_reach_geometry(actor),
                            {actor + FIELD_12: word(COLLECT_FIELD_12_IDLE)})
    # Slot 34 is quietest while the driver is talking: the two gate words end the frame before the
    # joystick is read, so it writes nothing at all.
    if name == "actor_behavior_type34":
        return {SCENE_MESSAGE_PENDING: word(SCENE_MESSAGE_PENDING_SET)}
    # Slots 35 and 36 always publish a frame and step their shared cursor; a cursor that does not
    # WRAP is what keeps the flag (and slot 36's retype) out of the frame.
    if name in ("actor_behavior_type35", "actor_behavior_type36"):
        return {EVENT_ANIM_CURSOR: word(0)}
    # Slot 37 is quietest while it is still rising, which is a fact about the descriptor rather than
    # the record: the target is a word the case has to place somewhere it can state.
    if name == "actor_behavior_type37":
        return {actor + ACTOR_Y: word(TYPE37_START_Y),
                RECORD_PTR_10420: longword(DESCRIPTOR_AT),
                DESCRIPTOR_AT + SCENE_VARIANT: word(TYPE37_TARGET_Y + TYPE37_RISE)}
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

    THERE IS NO THIRD KIND ANY MORE. Batch 31 had one — slots 59 and 8 were reconstructed AND
    transferred, so their rows were checkpointed at slot 7's entry while their writes were diffed —
    and batch 32's slot 7 retired it: both now run through the shared body like any other row.
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
    expected = DISPATCH_RAN
    info = leaf.run(DISPATCHER, _DISPATCH(actor), _handler_band(name), what,
                    regs=regs, poison=False,
                    max_insns=_cap(DISPATCHER, extra=_handler_cap(name)))
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


def _image_half_width(pokes):
    """The record's own WB_ACTOR_HALF_WIDTH, which is where $10a2 parks an x whose probe went
    negative — read out of the seed rather than restated."""
    return int.from_bytes(harness.make_image(pokes)[ACTOR + HALF_WIDTH:
                                                    ACTOR + HALF_WIDTH + WORD_BYTES], "big")


def _written_word(written, record, offset=0):
    """The WORD a write ledger holds at `record + offset` — `_put`'s reader, and one spelling for
    what a case would otherwise inline as `written[a] << 8 | written[a + 1]`."""
    return written[record + offset] << 8 | written[record + offset + 1]


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
from test_rng import FRAME_TICK, model_rng                     # noqa: E402

# The generator's word is the frame tick plus its three counters (the entropy byte is a MODELED
# hardware read, and these cases declare it as `hw_declared()`'s 0 — see the note at the run below),
# so the tick is the ONE input a case can steer the relaunch's `btst #2` with.
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

    # `hw_declared()` because this routine reaches rng_next, whose entropy term is a MODELED
    # hardware byte since batch 33 — an undeclared read of it refuses the differential.
    info = leaf.run("actor_tick_timer30", _TICK_TIMER30(ACTOR), merge_bands(expected), what,
                    hw_seed=leaf.hw_declared(),
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
                 for name in PORTED_TARGETS if name not in NO_GLUE_TARGETS}
_PLAYER_GATE = leaf.image_glue(PLAYER_GATE, ctypes.c_uint32)
_STUN = leaf.image_glue("actor_stun_followed")
_SOUND_REQUEST_9 = leaf.image_glue(SOUND_REQUEST_9)
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


# --- $6786: the band's own sound request ------------------------------------------------------------
def test_sound_request_9_is_the_stuns_opening_one_request_higher():
    """FOUR INSTRUCTIONS AND ONE OBSERVABLE: the SFX the stub writes. It takes no record and reads
    no image state, so the whole of its behaviour is the write set — which is also what separates
    it from actor_stun_followed twelve bytes later, whose request is WB_ACTOR_STUN_SFX."""
    what = "sound_request_9"
    pokes = _tier_pokes(case_salt(what), {})
    image = harness.make_image(pokes)
    expected = _sfx_bytes(image, REQUEST9_SFX, SND_CHANNEL_A)
    assert expected != _sfx_bytes(image, STUN_SFX, SND_CHANNEL_A), (
        "requests 8 and 9 write the same bytes, so this case cannot tell them apart")

    # STUB_INSN_CAP, from the battery that owns the stub, and not the damage path's 400: a cap two
    # orders of magnitude over a four-instruction body can never fire.
    info = leaf.run(SOUND_REQUEST_9, _SOUND_REQUEST_9, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=_cap(SOUND_REQUEST_9) + STUB_INSN_CAP)
    _assert_writes(info, expected, what)


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


def _block_the_walk(pokes, row=None):
    """One MAP ROW filled with WB_MAP_TILE_BLOCK — by default the row the two step probes read,
    which is `(y - 1) asr.w #4`, one above the record's own. Four cases spelt this loop before it
    was one helper, and a fifth (the ground below) fills a run of rows the same way."""
    for column in range(GROUND_COLUMNS):
        pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
              + DEFAULT_STRIDE * (STAND_ROW - 1 if row is None else row)] = bytes([TILE_BLOCK])
    return pokes


def _clear_ground(pokes, rows=6):
    """...and the same window with NOTHING in it, for the cases about a record that does not land."""
    for row in range(STAND_ROW - 1, STAND_ROW + rows):
        for column in range(GROUND_COLUMNS):
            pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS + column
                  + DEFAULT_STRIDE * row] = bytes([0])
    return pokes


def _out_of_reach_geometry(actor):
    """The two boxes $5c6e compares, seeded so its mask comes back ZERO: a small footprint on each,
    the two records far apart, and a followed SPRITE outside both of the gated bands.

    It is a helper rather than a dict inside `_type51_pokes` because slot 33's frame has NO gate on
    its contact test — the geometry is the only thing that can shut it — so the tier's dispatch row
    for that slot needs the same premise the band's own seed rests on, stated once."""
    return {actor + HALF_WIDTH: word(4), actor + SIZE_SECOND: word(8),
            actor + ACTOR_X: word(0x0100), actor + ACTOR_Y: word(STAND_Y),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0600), FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0), FOLLOWED_DEFAULT + HALF_WIDTH: word(4),
            FOLLOWED_DEFAULT + SIZE_SECOND: word(8), FOLLOWED_DEFAULT + FLAGS2: bytes([0]),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0])}


def _type51_pokes(what, fields=None, ground=True):
    """A slot-51 record clear of the followed one, with the map seeded so a step can be taken or
    refused by a tile the case chooses."""
    salt = case_salt(what)
    base = leaf.overlay(_out_of_reach_geometry(ACTOR),
                        {ACTOR + ACTOR_TYPE: word(51), ACTOR + ACTOR_FLAGS: bytes([0]),
                         ACTOR + FLAGS2: bytes([0]), ACTOR + SPEED: bytes([0]),
                         SCROLL_LIMIT_X: word(WIDE_LEVEL)})
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
    _block_the_walk(pokes)

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
    _block_the_walk(pokes)
    for column in range(GROUND_COLUMNS):
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
from test_actor import (EFFECT_RECORD_LIST, SLOT_BBC0,                           # noqa: E402
                        SPAWN_HITPOINTS, SPAWN_RECORD_BYTES, SPAWN_TYPE, TABLE_PTR,
                        TEMPLATE_SLOTS, TEMPLATE_TABLE, TEXT_REQUEST, _model_damage_followed,
                        _model_damage_template, _model_defeat, _template_band)
from test_actor import DAMAGE_FOLLOWED_SFX, DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B   # noqa: E402

# THE ONE SPAWN TYPE THESE CASES USE. `lsl.w #2,d2` inside actor_defeat_and_score leaves the X flag
# holding the type's bit 14, and bcd_add_score_bd70 folds it into the score's lowest digit — which
# src/actor.c THREADS since batch 33 phase B, so it is no longer a reason to refuse a type, only a
# reason to CHOOSE one here: a keyed template word would carry that bit at random and these cases
# are not about the score. test_actor.py's SCORE_EXTEND_TYPES drives the bit deliberately instead.
SAFE_SPAWN_TYPE = 4
TEMPLATE_POOL = 0x40

TEMPLATE_BAND_BYTES = TEMPLATE_SLOTS * SPAWN_RECORD_BYTES


def _foreign_band(image, own, model):
    """The addresses a foreign tail may write, taken from test_actor.py's OWN models rather than
    listed here — a hand-written list of regions would be the second copy that could disagree with
    the battery owning them while both stayed green.

    ``own`` is what the handler itself writes BEFORE the tail jump, applied to a copy first so the
    model reads the image the routine it models really would (the `bset #0,9(a0)` is one of that
    routine's inputs). ``model`` names the tail: the two damage paths compose with their SFX
    trigger's write set, the defeat composes its own.
    """
    after = bytearray(image)
    for addr, value in own.items():
        after[addr] = value
    named = dict(own)
    if model == "damage-template":
        named.update(_model_damage_template(after, ACTOR)[2])
        named.update(_sfx_bytes(after, DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B))
    elif model == "damage-followed":
        followed = _model_damage_followed(after, ACTOR)[1]
        named.update(followed)
        if followed:            # the invulnerable arm never reaches the trigger either
            named.update(_sfx_bytes(after, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A))
    else:
        named.update(_model_defeat(after, ACTOR)[2])
    return merge_bands(named) + HANDLER_WRITE_BAND


def _template_environment(salt, pokes):
    """The TEMPLATE environment the two damage paths and the defeat read: a table of eight records
    with a hit-point pool, the published pointer to it, and the two HUD charge slots emptied so
    neither path spends one (which keeps the arms a case is about the only thing moving)."""
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


def _band_slot_pokes(what, slot, fields=None, ground=True):
    """`_walk_pokes_for` under that environment — the seed every case whose arm leaves the tier
    uses."""
    return _template_environment(case_salt(what),
                                 _walk_pokes_for(what, slot, fields, ground=ground))


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


def _band5a_pokes(what, slot, fields=None, ground=True):
    """A record of any $5a-band slot, seeded exactly as `_type51_pokes` seeds slot 51's — same
    geometry, same out-of-reach followed record, same map — so the band's heads are compared on the
    same inputs rather than on five different ones. The TYPE word is what each slot overrides, and
    it is not cosmetic: actor_fall_and_settle has a player-only head that reads it."""
    return _type51_pokes(what, leaf.overlay({ACTOR + ACTOR_TYPE: word(slot)}, fields or {}),
                         ground=ground)


@pytest.mark.parametrize("slot", SWITCHED_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_switch_arm_frees_the_slot_outright(slot):
    """WHERE 52 AND 53 PART FROM 51. All three open `btst #0,9(a0) / bne.w`, but slot 51's branch
    lands on a FALL and these two land on the exit — so a record that raised the bit last frame
    gives its slot back with nothing else run at all. Slot 53 also lowers its live word here."""
    name = SWITCHED_HANDLERS[slot]
    what = f"{name} switch already up"
    pokes = _band5a_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0])})

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
    pokes = _band5a_pokes(what, slot, _strike_geometry())
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
    pokes = _band5a_pokes(what, slot, {
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
    pokes = _band5a_pokes(what, 52, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([step]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type52", what, pokes)
    written = program_writes(info)
    moved = (written[ACTOR + ACTOR_X] << 8) | written[ACTOR + ACTOR_X + 1]
    assert moved == x + step, f"{what}: the record moved to {moved:#06x}, not {x + step:#06x}"


def test_slot52_discards_the_probes_blocked_answer():
    """Nothing follows the `bsr` — no `tst.b d0` — so a wall only stops this record by refusing to
    move it. The switch stays DOWN where slot 51's would have gone up on the same map."""
    what = "actor_behavior_type52 blocked"
    pokes = _band5a_pokes(what, 52, {ACTOR + FIELD_30: bytes([4]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)
    _block_the_walk(pokes)

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
    pokes = _band5a_pokes(what, 52, {ACTOR + FIELD_30: bytes([2]),
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
    pokes = _band5a_pokes(what, 52, {ACTOR + FIELD_30: bytes([2]),
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
    pokes = _band5a_pokes(what, 52, {ACTOR + FIELD_18: bytes([cursor]),
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
    pokes = _band5a_pokes(what, 53, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]),
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
    pokes = _band5a_pokes(what, 53, {ACTOR + FIELD_30: bytes([0]),
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
    pokes = _band5a_pokes(what, 53, _strike_geometry())
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
    pokes = _band5a_pokes(what, 53, {ACTOR + FIELD_30: bytes([5]), TILE_33_MODE: word(0)})

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


# The cursor every prologue case seeds, and the SPAWN GATE is what keeps these cases about the
# prologue: with WB_ACTOR_FLAGS2_SPAWNED_BIT up, slot 7's body is one animation step, so the write
# set is the prologue's own plus actor_spawn_anim_step's three bytes and nothing else.
PROLOGUE_CURSOR = 4


def _prologue_pokes(what, slot, field_30=0):
    return _tier_pokes(case_salt(what), {ACTOR + ACTOR_TYPE: word(slot),
                                         ACTOR + FIELD_30: bytes([field_30]),
                                         ACTOR + FLAGS2: bytes([1 << SPAWNED_BIT]),
                                         ACTOR + FIELD_18: bytes([PROLOGUE_CURSOR]),
                                         TYPE59_TEMPLATE_FIELD: word(0)})


def _spawn_gate_writes(also=None):
    """What slot 7's body adds to a prologue's own writes on the gated frame, plus whatever that
    prologue wrote itself. The map is BYTE-VALUED, which is why it is merged here rather than
    through `leaf.overlay` (that one flattens byte strings for the poke layers)."""
    expected = {ACTOR + FIELD_18: PROLOGUE_CURSOR + ANIM_FRAME_BYTES}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + PROLOGUE_CURSOR))
    expected.update(also or {})
    return expected


@pytest.mark.parametrize("field_30", [0, 1 << TYPE08_MARK_BIT, 0xff],
                         ids=lambda v: f"field30={v:#04x}")
def test_slot59_marks_the_record_and_arms_the_A32_templates_first_respawn(field_30):
    """Twenty-two bytes: `bset #2,30(a0)`, then WB_ACTOR_TYPE59_RESPAWN_KIND into
    WB_TABLE_A32_SET's first template — addressed by a bare `lea`, so it lands on the A32 table
    whichever one WB_TABLE_PTR_21E8C currently names — and then, since batch 32, slot 7's body
    rather than a boundary. The `bra.w $7060` is now a join and not a stop."""
    what = f"actor_behavior_type59 over {field_30:#04x}"
    info = _run_handler("actor_behavior_type59", what, _prologue_pokes(what, 59, field_30))
    expected = _spawn_gate_writes(also={ACTOR + FIELD_30: field_30 | (1 << TYPE59_MARK_BIT)})
    _put(expected, TYPE59_TEMPLATE_FIELD, TYPE59_RESPAWN_KIND)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("field_30", [0, 1 << TYPE59_MARK_BIT, 0xff],
                         ids=lambda v: f"field30={v:#04x}")
def test_slot08_marks_the_record_and_falls_into_the_shared_body(field_30):
    """SIX BYTES AND ONE INSTRUCTION — the shortest reconstructed routine in this project. It raises
    its own bit and RUNS INTO the same body slot 59 branches to, which is what makes the two bits of
    WB_ACTOR_FIELD_30 the way one shared handler knows which entry was dispatched."""
    what = f"actor_behavior_type08 over {field_30:#04x}"
    info = _run_handler("actor_behavior_type08", what, _prologue_pokes(what, 8, field_30))
    _assert_writes(info,
                   _spawn_gate_writes(also={ACTOR + FIELD_30: field_30 | (1 << TYPE08_MARK_BIT)}),
                   what)


def test_slot07s_own_row_raises_NEITHER_mark_bit():
    """The third entrance, and the control for the two above: entered directly, the body writes no
    WB_ACTOR_FIELD_30 at all — so the bits really are the prologues' and not the body's."""
    what = "actor_behavior_type07 own row"
    info = _run_handler("actor_behavior_type07", what, _prologue_pokes(what, 7))
    _assert_writes(info, _spawn_gate_writes(), what)


def test_the_two_prologues_and_slot_7_are_three_table_entries_for_one_body():
    """Slots 59, 8 and 7 are three distinct table entries whose code is CONTIGUOUS and ends in one
    body. Their addresses come out of the image's own table."""
    assert _image_slot(59) + BODY_SIZES["actor_behavior_type59"] == _image_slot(8)
    assert _image_slot(8) + BODY_SIZES["actor_behavior_type08"] == _image_slot(7)
    assert _image_slot(7) == BEHAVIOR_TYPE07


# --- slots 47, 48 and 49: the rest of the $5a band ------------------------------------------------
# The band's own grammar, as three endings. Slot 47 ends on its CURSOR, slot 48 on its COUNTDOWN and
# slot 49 on the cursor of its SECOND table — so a handler that borrowed a neighbour's ending would
# free the wrong record on the wrong frame, and the cases below are paired to say which.
BAND_WALK_SLOTS = (48, 49)
BAND_WALK_HANDLERS = {48: "actor_behavior_type48", 49: "actor_behavior_type49"}
BAND_WALK_STEP = {48: TYPE48_STEP, 49: TYPE49_STEP}


# --- slot 47 ($5928): pure animation ---------------------------------------------------------------
# The cursors that separate a SIXTEEN-word table from every other stride in this file: the two ends,
# the offset where a $f mask would have wrapped and a $1f one does not, the byte at the wrap, and two
# that leave the table entirely (the read is unmasked — `andi.b #$1f` runs after it).
TYPE47_CURSORS = [0, 2, 0x0e, 0x1c, 0x20, 0xfc]
TYPE47_WRAP_CURSORS = [0x1e, 0xfe]


@pytest.mark.parametrize("cursor", TYPE47_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot47_publishes_one_frame_and_touches_nothing_else(cursor):
    """FORTY-TWO BYTES AND TWO WRITES. There is no settle, no probe, no step and no countdown here,
    which is what the EXACT write set says: a handler that had borrowed slot 48's `subq.b #1,30(a0)`
    would write a third byte and fail on the set rather than on a value."""
    what = f"actor_behavior_type47 cursor {cursor:#04x}"
    pokes = _monster_pokes(what, 47, {ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler("actor_behavior_type47", what, pokes)
    expected = {ACTOR + FIELD_18: (cursor + ANIM_FRAME_BYTES) & ANIM32_MASK}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(TYPE47_FRAMES + cursor))
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("cursor", TYPE47_WRAP_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot47_frees_its_slot_the_frame_its_cursor_WRAPS(cursor):
    """`move.b d0,18(a0) / bne` reads the flags of the STORE, so what ends this record is the cursor
    reaching zero and not a timer — the one handler in the band whose life is a fixed sixteen frames
    however its countdown byte is seeded. The sixteenth word is still published on that frame."""
    what = f"actor_behavior_type47 wrapping at {cursor:#04x}"
    pokes = _monster_pokes(what, 47, {ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler("actor_behavior_type47", what, pokes)
    expected = {ACTOR + FIELD_18: 0}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(TYPE47_FRAMES + cursor))
    _put(expected, ACTOR + ACTOR_X, FREE_MARKER)
    _assert_writes(info, expected, what)


# --- the walk slots 48 and 49 share ----------------------------------------------------------------
@pytest.mark.parametrize("slot", BAND_WALK_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("side,direction", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
def test_the_band_walk_steps_the_way_the_side_bit_points(slot, side, direction):
    """`move.w #$3,d7` and the `btst #3,8(a0)` under it. The step is a CONSTANT here where slot 52's
    is its own countdown byte, and it sits after the settle so only d7's low word is replaced — which
    the probes are the ones that read (map.h)."""
    name = BAND_WALK_HANDLERS[slot]
    what = f"{name} walking side={side:#04x}"
    x, step = 0x0100, BAND_WALK_STEP[slot]
    pokes = _band5a_pokes(what, slot, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_18: bytes([0]),
                                       ACTOR + FIELD_30: bytes([5]), ACTOR + FIELD_31: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([side])}, ground=False)

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    moved = (written[ACTOR + ACTOR_X] << 8) | written[ACTOR + ACTOR_X + 1]
    assert moved == x + direction * step, (
        f"{what}: the record moved to {moved:#06x}, not the {x + direction * step:#06x} a "
        f"{step}-pixel step gives")
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT) == side, (
        f"{what}: an UNBLOCKED step flipped the side bit")


@pytest.mark.parametrize("slot", BAND_WALK_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("side", [0, 1 << SIDE_BIT], ids=["right", "left"])
def test_the_band_walk_TURNS_ROUND_on_a_blocked_step(slot, side):
    """`tst.b d0 / bne / bchg #3,8(a0)` — actor_step_facing's own ending, inline. Where slot 51
    `bset`s a switch on a blocked step and slot 52 discards the answer entirely, these two flip the
    side bit and walk back the other way, so a wall turns the record rather than ending it."""
    name = BAND_WALK_HANDLERS[slot]
    what = f"{name} blocked side={side:#04x}"
    pokes = _band5a_pokes(what, slot, {ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([5]),
                                       ACTOR + FIELD_31: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([side])}, ground=False)
    _block_the_walk(pokes)

    info = _run_handler(name, what, pokes)
    turned = program_writes(info)[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)
    assert turned != side, f"{what}: a blocked step did not flip the side bit"


@pytest.mark.parametrize("slot", BAND_WALK_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("speed", [6, 1], ids=["mid-hop", "last-frame-of-the-hop"])
def test_the_band_walk_keeps_the_SETTLE_before_the_ascent(slot, speed):
    """The order of `bsr $1334 / bsr $501a`, driven the way slot 52's case drives it: the two are
    mutually exclusive on WB_ACTOR_FLAG_MOVING_BIT, so only the LAST frame of a hop — where the
    ascent clears the bit — separates the two orders. `speed=1` is that frame."""
    name = BAND_WALK_HANDLERS[slot]
    what = f"{name} hopping at speed {speed}"
    pokes = _band5a_pokes(what, slot, {ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([5]),
                                       ACTOR + FIELD_31: bytes([0]), ACTOR + SPEED: bytes([speed]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                          ground=False)

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert ACTOR + ACTOR_Y in written, f"{what}: neither the settle nor the ascent moved the record"
    if speed == 1:
        assert not written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT), (
            f"{what}: the hop did not end, so this row does not separate the two orders")
        assert written[ACTOR + SPEED] == 1, f"{what}: the ended hop did not reload the speed"
    else:
        assert written[ACTOR + SPEED] == speed - 1, (
            f"{what}: the ascent did not step the speed, so the hop never ran")


# --- slot 48 ($5972): four frames over a countdown -------------------------------------------------
# The two ends of a FOUR-word table, the byte at its wrap, an offset where a $f mask would not have
# wrapped and a $7 one does, and one that leaves the table (the read is unmasked).
TYPE48_CURSORS = [0, 2, 4, 6, 8, 0xfe]


@pytest.mark.parametrize("cursor", TYPE48_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot48_publishes_the_frame_its_cursor_names_and_wraps_over_four(cursor):
    """The frame comes out of the IMAGE, so a case that transcribed the four words would pass on its
    own transcription — and the cursor is read BEFORE `andi.b #$7`, which is what the row past the
    table is here to say."""
    what = f"actor_behavior_type48 cursor {cursor:#04x}"
    pokes = _band5a_pokes(what, 48, {ACTOR + FIELD_18: bytes([cursor]),
                                     ACTOR + FIELD_30: bytes([5]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type48", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & TYPE48_MASK
    assert _written_word(written, ACTOR, ACTOR_SPRITE) \
        == _image_word(TYPE48_FRAMES + cursor)


def test_slot48_frees_its_slot_when_its_COUNTDOWN_runs_out():
    """`subq.b #1,30(a0) / bne` — the free marker lands on the frame the byte reaches zero, over the
    x word this same frame's step just moved."""
    what = "actor_behavior_type48 countdown expiring"
    pokes = _band5a_pokes(what, 48, {ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([1]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type48", what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER, (
        f"{what}: the record was not freed")
    assert written[ACTOR + FIELD_30] == 0


def test_slot48_does_NOT_free_itself_when_its_cursor_wraps():
    """The control that separates slot 48's ending from slot 47's: the same wrap that ends a type-47
    record leaves a type-48 one alive, because the `bne` here reads the COUNTDOWN's flags and not
    the cursor store's."""
    what = "actor_behavior_type48 cursor wrapping with the countdown alive"
    pokes = _band5a_pokes(what, 48, {ACTOR + FIELD_18: bytes([TYPE48_MASK - 1]),
                                     ACTOR + FIELD_30: bytes([5]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type48", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the cursor did not wrap, so nothing is tested"
    assert _written_word(written, ACTOR, ACTOR_X) != FREE_MARKER, (
        f"{what}: the slot was freed on the cursor, which is slot 47's ending and not this one's")


# --- slot 49 ($59d0): two tables over one cursor ---------------------------------------------------
# The same five offsets against an EIGHT-word table: the two ends, the byte at the wrap, the one past
# it, and one that leaves the table entirely.
TYPE49_CURSORS = [0, 2, 0x0e, 0x10, 0xfe]


@pytest.mark.parametrize("cursor", TYPE49_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot49_phase_one_plays_its_first_table_and_counts_down(cursor):
    """WB_ACTOR_FIELD_31 CLEAR: the frame comes from WB_ACTOR_TYPE49_FRAMES_PHASE1 and the countdown
    moves. The cursor is read ONCE, before the phase is tested, so it is the same offset either
    phase would have used."""
    what = f"actor_behavior_type49 phase one, cursor {cursor:#04x}"
    timer = 5
    pokes = _band5a_pokes(what, 49, {ACTOR + FIELD_18: bytes([cursor]),
                                     ACTOR + FIELD_30: bytes([timer]),
                                     ACTOR + FIELD_31: bytes([0]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type49", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & ANIM16_MASK
    assert _written_word(written, ACTOR, ACTOR_SPRITE) \
        == _image_word(TYPE49_FRAMES_PHASE1 + cursor)
    assert written[ACTOR + FIELD_30] == timer - 1
    assert ACTOR + FIELD_31 not in written, f"{what}: the phase byte moved with the timer alive"


def test_slot49_raises_its_phase_byte_when_the_countdown_runs_out_and_keeps_its_slot():
    """`st 31(a0)` — phase one's ONLY ending, and it is not a free: a type-49 record that has run its
    timer out is still in its slot, now playing the other table."""
    what = "actor_behavior_type49 phase one expiring"
    pokes = _band5a_pokes(what, 49, {ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([1]),
                                     ACTOR + FIELD_31: bytes([0]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type49", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_30] == 0
    assert written[ACTOR + FIELD_31] == ST_BYTE, f"{what}: the phase byte was not set"
    assert _written_word(written, ACTOR, ACTOR_X) != FREE_MARKER, (
        f"{what}: phase one freed the slot, which only phase two does")


# TYPE49_CURSORS minus the two that WRAP — the case below is the one that must not end the record,
# and a wrapping cursor is the next case's subject rather than this one's.
TYPE49_PHASE_TWO_CURSORS = [0, 2, 0x0c, 0x10, 0xfc]


@pytest.mark.parametrize("cursor", TYPE49_PHASE_TWO_CURSORS, ids=lambda v: f"cursor{v:#04x}")
def test_slot49_phase_two_plays_its_other_table_and_ignores_the_countdown(cursor):
    """WB_ACTOR_FIELD_31 SET: the frame comes from WB_ACTOR_TYPE49_FRAMES_PHASE2 and `subq.b #1,30(a0)`
    is on the arm this one branched past — so the countdown byte is not written at all, which is
    what separates the two phases beyond the table address."""
    what = f"actor_behavior_type49 phase two, cursor {cursor:#04x}"
    pokes = _band5a_pokes(what, 49, {ACTOR + FIELD_18: bytes([cursor]),
                                     ACTOR + FIELD_30: bytes([5]),
                                     ACTOR + FIELD_31: bytes([ST_BYTE]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type49", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & ANIM16_MASK
    assert _written_word(written, ACTOR, ACTOR_SPRITE) \
        == _image_word(TYPE49_FRAMES_PHASE2 + cursor)
    assert ACTOR + FIELD_30 not in written, f"{what}: phase two stepped the countdown"
    assert ACTOR + FIELD_31 not in written, f"{what}: the phase byte moved before the wrap"


@pytest.mark.parametrize("cursor", [0x0e, 0xfe], ids=lambda v: f"cursor{v:#04x}")
def test_slot49_phase_two_frees_the_slot_when_the_returned_cursor_wraps(cursor):
    """`bsr $5a3c / tst.b d0 / beq` — the cursor actor_advance_anim16 hands BACK, in d0's low byte
    alone, is what ends the record: the phase byte goes down and the free marker goes over the x."""
    what = f"actor_behavior_type49 phase two wrapping at {cursor:#04x}"
    pokes = _band5a_pokes(what, 49, {ACTOR + FIELD_18: bytes([cursor]),
                                     ACTOR + FIELD_30: bytes([5]),
                                     ACTOR + FIELD_31: bytes([ST_BYTE]),
                                     ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    info = _run_handler("actor_behavior_type49", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == 0
    assert written[ACTOR + FIELD_31] == 0, f"{what}: the phase byte was not lowered"
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER, (
        f"{what}: the record was not freed")


# --- the SWOOP tier ($72c2..$73cd) and slot 7's body ($7060) --------------------------------------
_SWOOP_GLUE = {name: leaf.register_glue(name, [ctypes.c_uint32])
               for name in (SWOOP_STATE0, SWOOP_STATE1, SWOOP_STATE2, SWOOP_STATE3)}

# What each state calls, per state rather than as one bound over all four: state 0 faces the
# followed record AND fetches it, state 2 only fetches it, state 1 calls nothing at all, and state 3
# takes exactly ONE map probe a frame.
_SWOOP_CALLEE_INSNS = {
    SWOOP_STATE0: SIDE_FLAG_INSNS + FOLLOWED_INSNS,
    SWOOP_STATE1: 0,
    SWOOP_STATE2: FOLLOWED_INSNS,
    SWOOP_STATE3: MAP_PROBE_INSNS,
}


def _image_long(addr):
    return int.from_bytes(harness.BASE_IMAGE[addr:addr + LONGWORD_BYTES], "big")


def _swoop_pokes(what, fields=None, ground=True):
    """A slot-7 record on the same seed the $5a band uses, so the two tiers are driven over one
    geometry. The TYPE word matters here for the same reason it does there — actor_fall_and_settle
    is not called, but actor_swoop_state3_descend's probes read the record's own footprint."""
    return _band5a_pokes(what, 7, fields, ground=ground)


def _run_swoop(name, what, pokes, band=None):
    info = leaf.run(name, _SWOOP_GLUE[name](ACTOR), band or HANDLER_WRITE_BAND, what,
                    regs={"a0": ACTOR, "_pokes": pokes}, poison=False,
                    max_insns=_cap(name, extra=_SWOOP_CALLEE_INSNS[name]))
    return program_writes(info)


# --- state 0 ($72c2): the acquire ------------------------------------------------------------------
SWOOP_ACTOR_X, SWOOP_ACTOR_Y = 0x0200, 0x0080


def _acquire_pokes(what, gap, drop):
    """The record at a fixed point and the followed one placed to give exactly `gap` and `drop`:
    `gap` is `(a0) - (a1)` and `drop` is `2(a1) - 2(a0)`, which is the order the two subtractions
    are written in."""
    return _swoop_pokes(what, {ACTOR + ACTOR_X: word(SWOOP_ACTOR_X),
                               ACTOR + ACTOR_Y: word(SWOOP_ACTOR_Y),
                               ACTOR + FIELD_22: bytes([SWOOP_ACQUIRE]),
                               FOLLOWED_DEFAULT + ACTOR_X: word((SWOOP_ACTOR_X - gap) & 0xffff),
                               FOLLOWED_DEFAULT + ACTOR_Y: word((SWOOP_ACTOR_Y + drop) & 0xffff)})


def _path_offset_for(drop):
    """What WB_ACTOR_FIELD_24 should hold for a drop inside the near window: the table's own
    longword turned into an offset, taken from the IMAGE rather than transcribed."""
    index = (drop - SWOOP_Y_FLOOR) >> SWOOP_Y_SHIFT
    return (_image_long(SWOOP_PATH_TABLE + index * SWOOP_PATH_ENTRY) - SWOOP_PATHS) & 0xffff


# The two ends of each of the four 16-pixel bands, so every path is picked twice and a shift that
# was off by one lands on a neighbour rather than staying inside the same band.
ACQUIRE_DROPS = [8, 23, 24, 39, 40, 55, 56, 64]


@pytest.mark.parametrize("drop", ACQUIRE_DROPS, ids=lambda v: f"drop{v}")
def test_swoop_state0_picks_the_path_its_drop_names(drop):
    """`subq.w #8,d0 / lsr.w #4 / lsl.w #2` — sixteen pixels of drop per path over four paths, and
    the offset stored is the table's longword MINUS WB_ACTOR_SWOOP_PATHS, not the address."""
    what = f"actor_swoop_state0_acquire drop {drop}"
    written = _run_swoop(SWOOP_STATE0, what, _acquire_pokes(what, 0, drop))

    assert _written_word(written, ACTOR, FIELD_24) \
        == _path_offset_for(drop), f"{what}: the wrong path was committed"
    assert _written_word(written, ACTOR, FIELD_26) == SWOOP_ACTOR_Y
    assert written[ACTOR + FIELD_22] == SWOOP_RUN_PATH


@pytest.mark.parametrize("drop", [SWOOP_Y_NEAR + 1, 0x100], ids=lambda v: f"drop{v}")
def test_swoop_state0_takes_the_FIXED_path_past_its_near_window(drop):
    """`cmp.w #$40,d0 / ble` — a drop past the window skips the table entirely and takes
    WB_ACTOR_SWOOP_PATH_FAR, which is where the `subq`/`lsr` pair would otherwise index past four
    entries."""
    what = f"actor_swoop_state0_acquire far drop {drop}"
    written = _run_swoop(SWOOP_STATE0, what, _acquire_pokes(what, 0, drop))

    assert _written_word(written, ACTOR, FIELD_24) \
        == (SWOOP_PATH_FAR - SWOOP_PATHS) & 0xffff
    assert written[ACTOR + FIELD_22] == SWOOP_RUN_PATH


@pytest.mark.parametrize("gap,drop", [
    (-SWOOP_X_REACH - 1, 32), (SWOOP_X_REACH + 1, 32),   # outside the window, either side
    (0, -1), (0, -0x100),                                # the followed record ABOVE: `bmi`
    (0, 0), (0, SWOOP_Y_FLOOR - 1),                      # under the floor: the second `bmi`
], ids=["gap-under", "gap-over", "above-1", "above-256", "drop-0", "drop-7"])
def test_swoop_state0_refuses_and_commits_nothing(gap, drop):
    """Three gates and one answer: the record is left in state 0 with no path and no launch y. Only
    actor_set_side_flag's own byte may have moved, which is why this is not an exact write set."""
    what = f"actor_swoop_state0_acquire refusing gap={gap} drop={drop}"
    written = _run_swoop(SWOOP_STATE0, what, _acquire_pokes(what, gap, drop))

    for field in (FIELD_22, FIELD_24, FIELD_26):
        assert ACTOR + field not in written, f"{what}: {field}(a0) was written by a refused acquire"


@pytest.mark.parametrize("gap", [-SWOOP_X_REACH, SWOOP_X_REACH], ids=["gap-lo", "gap-hi"])
def test_swoop_state0_accepts_both_ends_of_its_x_window(gap):
    """`blt` and `bgt` are STRICT, so the window's two edges are inside it — the control for the
    two rejected rows one pixel further out."""
    what = f"actor_swoop_state0_acquire edge gap={gap}"
    written = _run_swoop(SWOOP_STATE0, what, _acquire_pokes(what, gap, 32))
    assert written[ACTOR + FIELD_22] == SWOOP_RUN_PATH


# --- state 1 ($7328): the path walk ----------------------------------------------------------------
@pytest.mark.parametrize("side,direction", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
@pytest.mark.parametrize("cursor", [0, SWOOP_PATH_STEP, (SWOOP_PATH_FAR - SWOOP_PATHS) & 0xffff],
                         ids=["path0-first", "path0-second", "far-path-first"])
def test_swoop_state1_walks_one_word_pair_a_frame(side, direction, cursor):
    """dx the way WB_ACTOR_FLAG_SIDE_BIT points and dy always DOWN, both read out of the image, and
    the cursor advanced by one pair. A case that transcribed the paths would pass on itself."""
    what = f"actor_swoop_state1_run_path cursor {cursor:#06x} side={side:#04x}"
    x, y = 0x0200, 0x0080
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                ACTOR + FIELD_24: word(cursor),
                                ACTOR + ACTOR_FLAGS: bytes([side])})
    dx = _image_word(SWOOP_PATHS + cursor)
    dy = _image_word(SWOOP_PATHS + cursor + SWOOP_PATH_DY)

    written = _run_swoop(SWOOP_STATE1, what, pokes)
    assert _written_word(written, ACTOR, ACTOR_X) \
        == (x + direction * dx) & 0xffff
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + dy) & 0xffff
    assert _written_word(written, ACTOR, FIELD_24) \
        == cursor + SWOOP_PATH_STEP
    assert ACTOR + FIELD_22 not in written, f"{what}: the state moved mid-path"


# Every path's own sentinel, found by walking the image from each table entry rather than by
# transcribing four offsets — so a path that grew would move this case with it.
def _sentinel_offsets():
    starts = [_image_long(SWOOP_PATH_TABLE + i * SWOOP_PATH_ENTRY) for i in range(4)]
    offsets = []
    for start in starts + [SWOOP_PATH_FAR]:
        at = start
        while _image_word(at) < 0x8000:
            at += SWOOP_PATH_STEP
        offsets.append(at - SWOOP_PATHS)
    return offsets


@pytest.mark.parametrize("cursor", _sentinel_offsets(), ids=lambda v: f"sentinel{v:#06x}")
def test_swoop_state1_ends_the_path_on_its_sentinel(cursor):
    """A NEGATIVE first word is the end, and that arm writes ONE byte: the cursor is not advanced
    and neither coordinate moves, so a record leaves state 1 holding the sentinel's own offset."""
    what = f"actor_swoop_state1_run_path sentinel {cursor:#06x}"
    pokes = _swoop_pokes(what, {ACTOR + FIELD_24: word(cursor),
                                ACTOR + ACTOR_FLAGS: bytes([0])})

    written = _run_swoop(SWOOP_STATE1, what, pokes)
    assert set(written) == {ACTOR + FIELD_22}, (
        f"{what}: the sentinel arm wrote {sorted(hex(a) for a in written)}")
    assert written[ACTOR + FIELD_22] == SWOOP_HOME_X


# --- state 2 ($7366): closing the last of the gap ---------------------------------------------------
@pytest.mark.parametrize("side,direction", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
def test_swoop_state2_closes_the_gap_four_pixels_a_frame(side, direction):
    """WB_ACTOR_SWOOP_HOME_STEP pixels, and the record stays in state 2 while the target is still
    past it."""
    what = f"actor_swoop_state2_home_x stepping side={side:#04x}"
    x = 0x0200
    target = x + direction * 0x40
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_FLAGS: bytes([side]),
                                FOLLOWED_DEFAULT + ACTOR_X: word(target)})

    written = _run_swoop(SWOOP_STATE2, what, pokes)
    assert _written_word(written, ACTOR, ACTOR_X) \
        == (x + direction * SWOOP_HOME_STEP) & 0xffff
    assert ACTOR + FIELD_22 not in written, f"{what}: it arrived with the gap still open"


@pytest.mark.parametrize("side,direction", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
@pytest.mark.parametrize("overshoot", [0, 1], ids=["exactly-on", "past"])
def test_swoop_state2_arrives_and_flips_its_facing_TWICE(side, direction, overshoot):
    """`bge` after the left step and `ble` after the right one, both INCLUSIVE — landing exactly on
    the target arrives. The two `bchg #3,8(a0)` then leave the byte as they found it, so
    WB_ACTOR_FLAGS is in the write set with the value it started with and nothing else says the pair
    ran (no differential can: the mutant that drops both is EQUIVALENT)."""
    what = f"actor_swoop_state2_home_x arriving side={side:#04x} overshoot={overshoot}"
    x = 0x0200
    target = x + direction * (SWOOP_HOME_STEP - overshoot)
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_FLAGS: bytes([side]),
                                FOLLOWED_DEFAULT + ACTOR_X: word(target)})

    written = _run_swoop(SWOOP_STATE2, what, pokes)
    assert written[ACTOR + FIELD_22] == SWOOP_DESCEND, f"{what}: it did not arrive"
    assert written[ACTOR + ACTOR_FLAGS] == side, (
        f"{what}: the two `bchg`s did not cancel — the facing came out {written[ACTOR + ACTOR_FLAGS]:#04x}")


# --- state 3 ($739e): the climb back ----------------------------------------------------------------
@pytest.mark.parametrize("side,direction", [(0, +1), (1 << SIDE_BIT, -1)], ids=["right", "left"])
def test_swoop_state3_steps_sideways_and_rises(side, direction):
    """Two pixels along and two up a frame, and the map probe's blocked answer is DISCARDED — the
    record here has clear ground either side, so both arms move."""
    what = f"actor_swoop_state3_descend side={side:#04x}"
    x, y = 0x0200, 0x0080
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                ACTOR + FIELD_26: word(y - 0x40),
                                ACTOR + ACTOR_FLAGS: bytes([side])}, ground=False)

    written = _run_swoop(SWOOP_STATE3, what, pokes)
    assert _written_word(written, ACTOR, ACTOR_X) \
        == (x + direction * SWOOP_DESCEND_STEP) & 0xffff
    assert _written_word(written, ACTOR, ACTOR_Y) == y - SWOOP_RISE
    assert ACTOR + FIELD_22 not in written, f"{what}: it finished below its launch height"


@pytest.mark.parametrize("launch_delta", [0, 1, 0x40], ids=["exactly-on", "one-past", "well-past"])
def test_swoop_state3_returns_to_state_0_at_its_launch_height(launch_delta):
    """`move.w 26(a0),d0 / cmp.w 2(a0),d0 / blt` — the comparison is against the y AFTER the rise
    and it is NOT strict, so a record that lands exactly on its launch y ends the swoop."""
    what = f"actor_swoop_state3_descend home + {launch_delta}"
    y = 0x0080
    launch = y - SWOOP_RISE + launch_delta
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_Y: word(y), ACTOR + FIELD_26: word(launch),
                                ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    written = _run_swoop(SWOOP_STATE3, what, pokes)
    assert written[ACTOR + FIELD_22] == SWOOP_ACQUIRE, f"{what}: the swoop did not end"


# --- slot 7's body ($7060) --------------------------------------------------------------------------
# A state byte whose handler writes NOTHING, so a case about the sprite or a spawner is not also a
# case about the swoop: state 0 with the followed record far outside its window.
def _slot07_pokes(what, fields=None, free_high=ALLOC_HIGH_SLOTS, ground=False):
    base = {ACTOR + FIELD_22: bytes([SWOOP_ACQUIRE]), ACTOR + FIELD_23: bytes([0]),
            ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([0]),
            ACTOR + ACTOR_X: word(SWOOP_ACTOR_X), ACTOR + ACTOR_Y: word(SWOOP_ACTOR_Y),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0600), FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600)}
    # The high pool, record by record: free ones can be allocated, occupied ones cannot.
    for index in range(ALLOC_HIGH_SLOTS):
        record = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST + index)
        base[record + ACTOR_X] = word(FREE_MARKER if index < free_high else OCCUPIED_X)
    return _swoop_pokes(what, leaf.overlay(base, fields or {}), ground=ground)


@pytest.mark.parametrize("side,marked,frames", [
    (1 << SIDE_BIT, 0, "ACTOR_TYPE07_FRAMES_LEFT"),
    (0, 0, "ACTOR_TYPE07_FRAMES_RIGHT"),
    (1 << SIDE_BIT, 1 << TYPE08_MARK_BIT, "ACTOR_TYPE07_FRAMES_MARKED_LEFT"),
    (0, 1 << TYPE08_MARK_BIT, "ACTOR_TYPE07_FRAMES_MARKED_RIGHT"),
], ids=["left", "right", "left-marked", "right-marked"])
def test_slot07_picks_its_frame_list_from_the_side_bit_and_slot_8s_mark(side, marked, frames):
    """TWO OVERLAPPING WRITES OF a1, not a four-way test: $74a0 goes in, the mark bit replaces it
    with $74ee, and then the side bit decides whether either stands. The SET side bit is the one
    that keeps them, which is the polarity a plate reading "neither/side" would have inverted."""
    what = f"actor_behavior_type07 frames side={side:#04x} mark={marked:#04x}"
    cursor = 3
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([side]),
                                 ACTOR + FIELD_30: bytes([marked]),
                                 ACTOR + FIELD_23: bytes([cursor])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_23] == cursor + 1
    assert _written_word(written, ACTOR, ACTOR_SPRITE) \
        == _image_word(wb(frames) + (cursor + 1) * ANIM_FRAME_BYTES)


@pytest.mark.parametrize("side,sprite", [(1 << SIDE_BIT, TYPE07_SPRITE_LEFT),
                                         (0, TYPE07_SPRITE_RIGHT)], ids=["left", "right"])
def test_slot07_marked_by_slot59_holds_a_CONSTANT_frame(side, sprite):
    """`btst #2,30(a0)` — a record that came in through slot 59's row does not animate at all: one
    of two immediates, and WB_ACTOR_FIELD_23 is not touched. The write to $21 happens first and the
    clear-side arm overwrites it, so both land in the same ledger entry."""
    what = f"actor_behavior_type07 marked sprite side={side:#04x}"
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([side]),
                                 ACTOR + FIELD_30: bytes([1 << TYPE59_MARK_BIT]),
                                 ACTOR + FIELD_23: bytes([5])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == sprite
    assert ACTOR + FIELD_23 not in written, f"{what}: a marked record stepped its frame cursor"


@pytest.mark.parametrize("cursor", [0, TYPE07_FRAME_COUNT - 2, TYPE07_FRAME_COUNT - 1,
                                    TYPE07_FRAME_COUNT, 0x7f, 0x80, 0xff],
                         ids=lambda v: f"cursor{v:#04x}")
def test_slot07_wraps_its_frame_cursor_with_a_SIGNED_compare(cursor):
    """`addq.b #1,23(a0) / cmpi.b #$c,23(a0) / blt` — signed, so $80..$ff are NEGATIVE and pass the
    test unwrapped, and `lsl.w #1` then reaches a word past the twelve. The game's own flow cannot
    produce one (the spawn clears the byte), which is what makes those rows the honest bound rather
    than a claim that the wrap is total."""
    what = f"actor_behavior_type07 cursor {cursor:#04x}"
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                 ACTOR + FIELD_23: bytes([cursor])})
    stepped = (cursor + 1) & 0xff
    expected = 0 if s16((stepped ^ 0x80) - 0x80) >= TYPE07_FRAME_COUNT else stepped

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_23] == expected
    assert _written_word(written, ACTOR, ACTOR_SPRITE) \
        == _image_word(TYPE07_FRAMES_LEFT + expected * ANIM_FRAME_BYTES)


@pytest.mark.parametrize("state", [SWOOP_ACQUIRE, SWOOP_RUN_PATH, SWOOP_HOME_X, SWOOP_DESCEND],
                         ids=lambda v: f"state{v}")
def test_slot07_runs_the_swoop_state_its_byte_names(state):
    """One case per table entry, and what each asserts is the state's OWN signature write: the
    acquire commits a path, the walk moves both coordinates, the homing moves x alone and the climb
    moves y. The target is FETCHED out of the image, so a poked table would be followed."""
    what = f"actor_behavior_type07 state {state}"
    y = SWOOP_ACTOR_Y
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_22: bytes([state]),
                                 ACTOR + FIELD_24: word(0), ACTOR + FIELD_26: word(y - 0x40),
                                 FOLLOWED_DEFAULT + ACTOR_X: word(SWOOP_ACTOR_X),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(y + 32)})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    if state == SWOOP_ACQUIRE:
        assert written[ACTOR + FIELD_22] == SWOOP_RUN_PATH
    elif state == SWOOP_RUN_PATH:
        assert ACTOR + ACTOR_X in written and ACTOR + ACTOR_Y in written
    elif state == SWOOP_HOME_X:
        assert ACTOR + ACTOR_X in written and ACTOR + ACTOR_Y not in written
    else:
        assert _written_word(written, ACTOR, ACTOR_Y) == y - SWOOP_RISE


def test_slot07_reports_the_address_a_state_byte_past_the_table_names():
    """ALL 256 STATE BYTES against the reconstruction alone, which is the only surface the unbounded
    `jsr (a1)` has — the original would call arbitrary data, so no differential can drive one.

    `move.b 22(a0),d0 / lsl.w #2 / movea.l 0(a1,d0.w),a1` reaches $7490 + 0..1020 with no bound at
    all; the four states are the only longwords in that span this port has, and every other byte is
    reported as the address the original would have entered."""
    ported = {leaf.entry_of(name) for name in (SWOOP_STATE0, SWOOP_STATE1, SWOOP_STATE2,
                                               SWOOP_STATE3)}
    what = "actor_behavior_type07 state enumeration"
    image = harness.make_image(_slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                                    ACTOR + FIELD_30: bytes([MARK_BOTH]),
                                                    ACTOR + FIELD_31: bytes([TYPE07_BURST_MASK])}))
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(bytearray(image))
    handler = leaf.bind(TYPE07, [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32], ctypes.c_uint32)
    ran = 0

    # No oracle runs inside this loop — 256 FFI calls, under 5 ms — so the `chunk` shard the type
    # enumeration above needs does not apply here.
    for state in range(0x100):
        buf[ACTOR + FIELD_22] = state
        buf[ACTOR + FIELD_31] = TYPE07_BURST_MASK
        before = bytes(buf[TABLES_LO:TABLES_HI])
        target = _image_long(SWOOP_STATE_TABLE + state * SWOOP_STATE_ENTRY)
        answer = handler(buf, ACTOR)
        if target in ported:
            ran += 1
            assert answer == DISPATCH_RAN, (
                f"state {state} names {target:#x}, which is reconstructed, but answered {answer:#x}")
            continue
        assert answer == target, (
            f"state {state} answered {answer:#x} against the {target:#x} its longword holds")
        # AND THE FRAME STOPPED, which the answer alone cannot say: the longword at $7594 (state
        # byte 65) is $00000000, and that is WB_ACTOR_DISPATCH_RAN's own value. The seed above arms
        # BOTH spawners with their cadences met, so a port that read a fetched 0 as "it ran" fires
        # five shots and a dropper into the tables and this comparison catches it.
        assert bytes(buf[TABLES_LO:TABLES_HI]) == before, (
            f"state {state} reported the boundary {target:#x} and then went on writing")
    assert ran == len(ported), f"{ran} state bytes reached a reconstructed handler, not 4"


def test_the_state_table_span_really_holds_a_zero_longword():
    """The premise of the assertion above, taken from the IMAGE rather than asserted in prose: some
    state byte in 0..255 lands on a longword of 0, so WB_ACTOR_DISPATCH_RAN and a boundary address
    genuinely collide and the reconstruction cannot answer with one `uint32_t`."""
    zeros = [state for state in range(0x100)
             if _image_long(SWOOP_STATE_TABLE + state * SWOOP_STATE_ENTRY) == DISPATCH_RAN]
    assert zeros, "no state byte reaches a zero longword — the out-of-band answer is unmotivated"


# --- slot 7's two spawners --------------------------------------------------------------------------
def _high_record(index):
    return _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST + index)


# THE STATE RUNS BEFORE BOTH SPAWNERS, and state 0 is the one that rewrites WB_ACTOR_FLAG_SIDE_BIT
# (actor_set_side_flag). Every arm below reads that bit AFTER the state — the velocity table, the
# flag byte each shot copies and the dropper's 26(a1) — so a spawner case cannot simply seed the
# facing: it places the followed record on the side that PRODUCES it. Far enough out that state 0
# still refuses, which is what leaves 22(a0) at zero for the burst's own `tst.b`.
MARK_BOTH = (1 << TYPE08_MARK_BIT) | (1 << TYPE59_MARK_BIT)
SLOT07_FOLLOWED_LEFT = SWOOP_ACTOR_X - 0x200
SLOT07_FOLLOWED_RIGHT = SWOOP_ACTOR_X + 0x200


def _slot07_spawn_pokes(what, side, fields, free_high=ALLOC_HIGH_SLOTS):
    followed = SLOT07_FOLLOWED_LEFT if side else SLOT07_FOLLOWED_RIGHT
    return _slot07_pokes(what,
                         leaf.overlay({ACTOR + ACTOR_FLAGS: bytes([side]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(followed),
                                       FOLLOWED_DEFAULT + ACTOR_Y: word(0x0600)}, fields),
                         free_high=free_high)




@pytest.mark.parametrize("side,velocities", [(1 << SIDE_BIT, TYPE07_BURST_LEFT),
                                             (0, TYPE07_BURST_RIGHT)], ids=["left", "right"])
def test_slot07_burst_fires_five_mirrored_shots(side, velocities):
    """`move.w #$4,d1 / dbf` with the `bsr $1b8e` INSIDE the loop, so five separate records are
    taken; only a2 carries across an iteration. The velocity longwords come out of the image, and
    which table is read is the side bit's — a case that read the other one would see the same five
    dy words and mirrored dx."""
    what = f"actor_behavior_type07 burst side={side:#04x}"
    pokes = _slot07_spawn_pokes(what, side, {ACTOR + FIELD_30: bytes([1 << TYPE08_MARK_BIT]),
                                             ACTOR + FIELD_31: bytes([TYPE07_BURST_MASK])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_31] == 0, f"{what}: the cadence byte did not wrap"
    assert written[ACTOR + ACTOR_FLAGS] == side, (
        f"{what}: the state left the facing at {written[ACTOR + ACTOR_FLAGS]:#04x}, so the "
        f"velocity table this case names is not the one the burst read")
    for index in range(TYPE07_BURST_LAST + 1):
        shot = _high_record(index)
        assert _written_word(written, shot, ACTOR_X) == SWOOP_ACTOR_X
        assert _written_word(written, shot, ACTOR_Y) == SWOOP_ACTOR_Y
        assert _written_word(written, shot, ACTOR_TYPE) == TYPE07_SHOT_TYPE
        assert written[shot + ACTOR_FLAGS] == side
        assert _written_word(written, shot, ACTOR_SPRITE) == TYPE07_BURST_SPRITE
        assert _written_word(written, shot, HALF_WIDTH) == TYPE07_SHOT_SIZE >> 16
        assert _written_word(written, shot, SIZE_SECOND) == TYPE07_SHOT_SIZE & 0xffff
        velocity = _image_long(velocities + index * TYPE07_BURST_ENTRY)
        assert _written_word(written, shot, FIELD_24) == velocity >> 16
        assert _written_word(written, shot, FIELD_26) == velocity & 0xffff


# WB_ACTOR_TYPE07_DROP_MASK is a SUBSET of the burst's, so the two agree on every cursor but the
# ones between them: $1f is where a burst masked with the dropper's would fire and the real one
# holds. The sweep found that hole — `type07/cadence-masks-swapped` survived without this row.
@pytest.mark.parametrize("cursor,state", [(0, SWOOP_ACQUIRE), (1, SWOOP_ACQUIRE),
                                          (TYPE07_DROP_MASK, SWOOP_ACQUIRE),
                                          (2 * (TYPE07_DROP_MASK + 1) - 1, SWOOP_ACQUIRE),
                                          (TYPE07_BURST_MASK, SWOOP_RUN_PATH)],
                         ids=["cadence-unmet", "cadence-unmet-2", "dropper-cadence",
                              "dropper-cadence-2", "mid-swoop"])
def test_slot07_burst_holds_its_fire(cursor, state):
    """The two gates in front of it, in the order the bytes have them: the cursor is stepped BEFORE
    `tst.b 22(a0)`, so a record mid-swoop still advances its cadence but never masks it — which is
    why the third row leaves WB_ACTOR_FIELD_31 at $80 and not at 0."""
    what = f"actor_behavior_type07 burst held cursor={cursor:#04x} state={state}"
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_22: bytes([state]),
                                 ACTOR + FIELD_24: word(0),
                                 ACTOR + FIELD_26: word(SWOOP_ACTOR_Y),
                                 ACTOR + FIELD_30: bytes([1 << TYPE08_MARK_BIT]),
                                 ACTOR + FIELD_31: bytes([cursor])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    expected = (cursor + 1) & 0xff if state != SWOOP_ACQUIRE \
        else (cursor + 1) & TYPE07_BURST_MASK
    assert written[ACTOR + FIELD_31] == expected
    assert _high_record(0) + ACTOR_TYPE not in written, f"{what}: a shot was spawned anyway"


def test_slot07_burst_ENDS_THE_FRAME_when_the_pool_runs_out():
    """`cmpa.l #$0,a1 / beq.w $7206` — a failed allocation returns from the WHOLE routine, so the
    dropper below never runs. Driven with both mark bits up and two free records: two shots land,
    the third allocation fails, and WB_ACTOR_FIELD_31 is left at the burst's own 0 rather than the
    1 the dropper's `addq` would have made it."""
    what = "actor_behavior_type07 burst on a short pool"
    free = 2
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_30: bytes([MARK_BOTH]),
                                 ACTOR + FIELD_31: bytes([TYPE07_BURST_MASK])},
                          free_high=free)

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    for index in range(free):
        assert _written_word(written, _high_record(index), ACTOR_TYPE) == TYPE07_SHOT_TYPE
    assert written[ACTOR + FIELD_31] == 0, (
        f"{what}: the dropper ran, so the failed allocation did not end the frame")


@pytest.mark.parametrize("side,field_26", [(1 << SIDE_BIT, TYPE07_DROP_FIELD_26), (0, None)],
                         ids=["left", "right"])
def test_slot07_dropper_drops_one_shot_above_itself(side, field_26):
    """One shot, WB_ACTOR_TYPE07_DROP_RISE pixels ABOVE the record — `move.l (a0),(a1)` copies both
    coordinates as one longword and the `subi.w` then lifts the y — with a WORD velocity where the
    burst writes a longword, and 26(a1) written only while the side bit is SET."""
    what = f"actor_behavior_type07 dropper side={side:#04x}"
    pokes = _slot07_spawn_pokes(what, side, {ACTOR + FIELD_30: bytes([1 << TYPE59_MARK_BIT]),
                                             ACTOR + FIELD_31: bytes([TYPE07_DROP_MASK])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    shot = _high_record(0)
    assert written[ACTOR + ACTOR_FLAGS] == side
    assert written[ACTOR + FIELD_31] == 0
    assert _written_word(written, shot, ACTOR_X) == SWOOP_ACTOR_X
    assert _written_word(written, shot, ACTOR_Y) == SWOOP_ACTOR_Y - TYPE07_DROP_RISE
    assert _written_word(written, shot, ACTOR_TYPE) == TYPE07_SHOT_TYPE
    assert _written_word(written, shot, ACTOR_SPRITE) == TYPE07_DROP_SPRITE
    assert _written_word(written, shot, FIELD_24) == TYPE07_DROP_VELOCITY
    if field_26 is None:
        assert shot + FIELD_26 not in written, f"{what}: 26(a1) was written on the clear-side arm"
    else:
        assert _written_word(written, shot, FIELD_26) == field_26


@pytest.mark.parametrize("cursor", [0, 1, TYPE07_DROP_MASK - 1], ids=lambda v: f"cursor{v:#04x}")
def test_slot07_dropper_waits_for_its_own_cadence(cursor):
    """`andi.b #$1f` where the burst's is `#$7f`, so the dropper fires four times as often — and the
    frames in between advance the cursor and write nothing else."""
    what = f"actor_behavior_type07 dropper held at {cursor:#04x}"
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_30: bytes([1 << TYPE59_MARK_BIT]),
                                 ACTOR + FIELD_31: bytes([cursor])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_31] == (cursor + 1) & TYPE07_DROP_MASK
    assert _high_record(0) + ACTOR_TYPE not in written, f"{what}: a shot landed off-cadence"


def test_slot07_dropper_does_not_advance_its_cursor_on_a_full_pool():
    """THE ORDER, as a case: the allocation and its null test come BEFORE `addq.b #1,31(a0)`, so a
    frame that found the pool full leaves the cadence exactly where it was."""
    what = "actor_behavior_type07 dropper on a full pool"
    cursor = 7
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_30: bytes([1 << TYPE59_MARK_BIT]),
                                 ACTOR + FIELD_31: bytes([cursor])}, free_high=0)

    info = _run_handler(TYPE07, what, pokes)
    assert ACTOR + FIELD_31 not in program_writes(info), (
        f"{what}: the cadence advanced although nothing could be allocated")


# --- slot 7's prologue exits ------------------------------------------------------------------------
def test_slot07_damages_the_followed_record_on_a_BODY_overlap():
    """Bit 1 of the overlap mask, and the one arm of this handler that ends on a TAIL JUMP:
    `bsr.s $701c / bra.w $69fe`, so nothing below runs. The followed record is invulnerable, which
    makes actor_damage_followed write nothing and leaves $701c's own two writes as the whole set."""
    what = "actor_behavior_type07 body overlap"
    x, y = 0x0100, STAND_Y
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                 ACTOR + FIELD_22: bytes([SWOOP_DESCEND]),
                                 FOLLOWED_DEFAULT + ACTOR_X: word(x),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(y),
                                 FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0),
                                 FOLLOWED_DEFAULT + FLAGS2: bytes([1 << INVULNERABLE_BIT])})

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_22] == FIELD_22_HOLD, f"{what}: $701c did not force 22(a0)"
    assert ACTOR + ACTOR_SPRITE not in written, (
        f"{what}: the frame ran on past its tail jump into actor_damage_followed")


# The POINT arm's geometry: the followed record's POINT lands inside the actor's box while its own
# footprint (given zero extent) does not, so the mask comes back with bit 2 alone. Slot 7 tests bits
# 1 and 2 and NOT bit 0 — the strike bit every $5a-band slot reads is ignored here.
def _point_geometry():
    return {ACTOR + ACTOR_X: word(SWOOP_ACTOR_X), ACTOR + ACTOR_Y: word(SWOOP_ACTOR_Y),
            FOLLOWED_DEFAULT + ACTOR_X: word(SWOOP_ACTOR_X - POINT_RIGHT),
            FOLLOWED_DEFAULT + ACTOR_Y: word(SWOOP_ACTOR_Y - 4 + POINT_UP),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(POINT_LO),
            FOLLOWED_DEFAULT + HALF_WIDTH: word(0), FOLLOWED_DEFAULT + SIZE_SECOND: word(0),
            FOLLOWED_DEFAULT + FLAGS2: bytes([0])}


def test_slot07_takes_damage_and_KEEPS_RUNNING_when_it_survives():
    """`bclr #0,9(a0) / btst #3,9(a0) / bne` — the damage arm is NOT an ending. A record that was
    hit but not defeated falls straight through into the sprite and the state below, which is where
    this handler parts from every $2462-band one (theirs all `bra.w` out of it).

    Bit 0 of WB_ACTOR_FLAGS2 is call-scoped here too: raised across
    actor_damage_template_hitpoints and lowered again immediately, so it is DOWN at the end of a
    frame that ran the arm."""
    what = "actor_behavior_type07 damaged and surviving"
    pokes = _template_environment(
        case_salt(what),
        _slot07_pokes(what, leaf.overlay({ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                          ACTOR + FIELD_18: bytes([6]),
                                          ACTOR + TEMPLATE_SLOT: bytes([2])},
                                         _point_geometry())))
    image = harness.make_image(pokes)
    mask = _model_overlap_mask(image, ACTOR, FOLLOWED_DEFAULT)
    assert mask & (1 << POINT_BIT) and not mask & (1 << BODY_BIT), (
        f"{what}: the seed does not reach bit 2 alone, so this case drives another arm")
    own = {ACTOR + FLAGS2: image[ACTOR + FLAGS2] | (1 << FLAGS2_BIT_0), ACTOR + FIELD_18: 0}

    info = _run_handler(TYPE07, what, pokes, band=_foreign_band(image, own, "damage-template"))
    written = program_writes(info)
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the hit animation's cursor was not cleared"
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: bit 0 of 9(a0) was left up — it is call-scoped here")
    assert ACTOR + ACTOR_SPRITE in written, f"{what}: the frame stopped at the damage arm"


def test_slot07_ignores_the_STRIKE_bit_every_5a_band_slot_reads():
    """`btst #1,d0` and `btst #2,d0` and no `btst #0` at all: a record inside the followed one's
    strike box takes no damage arm here and simply animates. The seed is the same
    `_strike_geometry` slots 51..53 are driven with."""
    what = "actor_behavior_type07 struck"
    strike = leaf.overlay(_strike_geometry(),
                          # No extent at all, so the record's own footprint cannot also reach bit 1
                          # — which slots 51..53 never had to separate, because they read bit 0
                          # first and never get as far as bit 1 on this geometry.
                          {FOLLOWED_DEFAULT + HALF_WIDTH: word(0),
                           FOLLOWED_DEFAULT + SIZE_SECOND: word(0)})
    pokes = _slot07_pokes(what, leaf.overlay({ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                              ACTOR + FIELD_23: bytes([0])}, strike))
    image = harness.make_image(pokes)
    mask = _model_overlap_mask(image, ACTOR, FOLLOWED_DEFAULT)
    assert mask == 1 << STRIKE_BIT, (
        f"{what}: the mask is {mask:#x}, not bit 0 alone — this case would drive another arm")

    info = _run_handler(TYPE07, what, pokes)
    written = program_writes(info)
    assert ACTOR + FLAGS2 not in written, f"{what}: the strike bit reached a damage arm"
    assert written[ACTOR + FIELD_23] == 1, f"{what}: the frame did not reach its animation"


# --- the two RE-READ pins: a record whose coordinate stores are DROPPED --------------------------
# $7378 and $73c0 compare a word the instruction above them just STORED, and the compare reads
# MEMORY. The two agree with a port that kept the value in a local everywhere the store lands — so
# the only seed that separates them is a record whose store does NOT land, which is what bus.h and
# the shim both do for an address outside the loaded image.
#
# WB_ACTOR_FIELD_22 and WB_ACTOR_FIELD_26 are the part that DOES land: 24-bit addressing folds
# $fffff0 + 22 and + 26 back to $6 and $a, which are inside the image and below the program. So the
# state byte the two arms write is observable while the coordinates they compare are not. Both cores
# mask the same way (CPU_ADDRESS_MASK $ffffff), and neither address is one the shim models as
# hardware.
REFUSED_RECORD = 0xfffff0
REFUSED_FIELD_22 = (REFUSED_RECORD + FIELD_22) & BUS_ADDR_MASK
REFUSED_FIELD_26 = (REFUSED_RECORD + FIELD_26) & BUS_ADDR_MASK
REFUSED_BAND = [(REFUSED_FIELD_22, 1), (REFUSED_FIELD_26, WORD_BYTES)] + HANDLER_WRITE_BAND


def _refused_record_pokes(what, fields):
    """A tier seeded as usual, plus the two bytes the folded record really reaches. Nothing is poked
    at $fffff0 itself: the point is that the record is NOT there."""
    return _tier_pokes(case_salt(what), fields)


def _run_swoop_on_refused_record(name, what, pokes):
    info = leaf.run(name, _SWOOP_GLUE[name](REFUSED_RECORD), REFUSED_BAND, what,
                    regs={"a0": REFUSED_RECORD, "_pokes": pokes}, poison=False,
                    max_insns=_cap(name, extra=_SWOOP_CALLEE_INSNS[name]))
    return program_writes(info)


@pytest.mark.parametrize("target", [1, 2, 3, SWOOP_HOME_STEP], ids=lambda v: f"followed-x{v}")
def test_swoop_state2_compares_the_x_it_STORED_and_not_the_one_it_computed(target):
    """`addq.w #4,(a0) / cmp.w (a0),d0` — the arrival test RE-READS the record's x.

    With the store dropped the read answers 0, so the original arrives only for a target at or below
    ZERO and these four rows do NOT arrive. A port comparing its own local compares against 4 and
    arrives on every one of them, writing WB_ACTOR_SWOOP_DESCEND into the folded 22(a0) at $6."""
    what = f"actor_swoop_state2_home_x refused store, followed x {target}"
    pokes = _refused_record_pokes(what, {REFUSED_FIELD_22: bytes([SWOOP_HOME_X]),
                                         FOLLOWED_DEFAULT + ACTOR_X: word(target)})

    written = _run_swoop_on_refused_record(SWOOP_STATE2, what, pokes)
    assert REFUSED_FIELD_22 not in written, (
        f"{what}: the record arrived, so the compare read the computed x and not the stored one")


@pytest.mark.parametrize("launch", [0xfffe, 0xffff], ids=["launch-minus-2", "launch-minus-1"])
def test_swoop_state3_compares_the_y_it_STORED_and_not_the_one_it_computed(launch):
    """`subq.w #2,2(a0) / cmp.w 2(a0),d0` — the launch test RE-READS the record's y, and the same
    dropped store separates the two readings: the original compares WB_ACTOR_FIELD_26 against 0 and
    a port holding a local compares it against -2. Both rows are launch heights below zero, so the
    original does NOT finish the swoop and an unfixed port clears 22(a0) at $6."""
    what = f"actor_swoop_state3_descend refused store, launch {launch:#06x}"
    pokes = _refused_record_pokes(what, {REFUSED_FIELD_22: bytes([SWOOP_DESCEND]),
                                         REFUSED_FIELD_26: word(launch)})

    written = _run_swoop_on_refused_record(SWOOP_STATE3, what, pokes)
    assert REFUSED_FIELD_22 not in written, (
        f"{what}: the swoop ended, so the compare read the computed y and not the stored one")


# --- state 3's discarded probe answer, as slot 52's control is ------------------------------------
def test_swoop_state3_rises_even_when_the_map_refuses_its_step():
    """Nothing follows the `bsr` — no `tst.b d0` — so a wall stops this state by leaving x alone and
    NOTHING else: the record still rises WB_ACTOR_SWOOP_RISE and still ends the swoop at its launch
    height. The same control slot 52 has for the same shape."""
    what = "actor_swoop_state3_descend blocked"
    # The x every other blocked case in this file uses: `_block_the_walk` fills DEFAULT_STRIDE
    # columns, and a record at $200 probes a cell past the end of them.
    x, y = 0x0100, STAND_Y
    pokes = _swoop_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                ACTOR + FIELD_26: word(y - SWOOP_RISE),
                                ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)
    _block_the_walk(pokes)

    written = _run_swoop(SWOOP_STATE3, what, pokes)
    # The probe STORES the x either way — it parks the record rather than declining to write — so
    # what says the step was refused is the VALUE, not the ledger entry.
    assert _written_word(written, ACTOR, ACTOR_X) == x, (
        f"{what}: the blocked step moved the record anyway")
    assert _written_word(written, ACTOR, ACTOR_Y) == y - SWOOP_RISE, (
        f"{what}: the rise was skipped, so the probe's answer reached it")
    assert written[ACTOR + FIELD_22] == SWOOP_ACQUIRE, (
        f"{what}: the swoop did not end, so the probe's answer reached the launch test")


# --- slot 7's defeat exit -------------------------------------------------------------------------
def test_slot07_transfers_to_the_defeat_when_the_damage_kills_it():
    """`btst #3,9(a0) / bne.w $6bb8` — the ONE arm of the damage path that ends the frame. Driven
    with both mark bits up and both cadences met, so a port that ran on would fire five shots and a
    dropper into the high pool; the pin is that it did not."""
    what = "actor_behavior_type07 defeated"
    pokes = _template_environment(
        case_salt(what),
        _slot07_pokes(what, leaf.overlay({ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                          ACTOR + TEMPLATE_SLOT: bytes([2]),
                                          ACTOR + FIELD_30: bytes([MARK_BOTH]),
                                          ACTOR + FIELD_31: bytes([TYPE07_BURST_MASK]),
                                          # The bit the damage path READS on its way out. Seeding it
                                          # rather than spending the pool keeps this case about the
                                          # transfer and leaves the arithmetic to test_actor.py.
                                          ACTOR + FLAGS2: bytes([1 << DEFEATED_BIT])},
                                         _point_geometry())))
    image = harness.make_image(pokes)
    own = {ACTOR + FLAGS2: image[ACTOR + FLAGS2] | (1 << FLAGS2_BIT_0), ACTOR + FIELD_18: 0}

    # BOTH foreign tails run on this frame — the damage path with its SFX and then the defeat — so
    # the band is both models, where every other case in this file reaches one or the other.
    band = _foreign_band(image, own, "damage-template") + _foreign_band(image, own, "defeat")

    info = _run_handler(TYPE07, what, pokes, band=band)
    written = program_writes(info)
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template was not touched, so actor_defeat_and_score never ran")
    assert _high_record(0) + ACTOR_TYPE not in written, (
        f"{what}: a dead record fired its burst — the defeat's tail jump did not end the frame")


# --- the two prologues with the spawn gate DOWN ---------------------------------------------------
# Every other slot-7-family seed raises WB_ACTOR_FLAGS2_SPAWNED_BIT, which makes the frame one
# animation step and never crosses the join with the mark bit live. These two do cross it: the bit
# each prologue raises has to be IN the record before the body reads it, so a port that raised it
# after the call would take the unmarked arms.
@pytest.mark.parametrize("name,mark,frames", [
    ("actor_behavior_type08", 1 << TYPE08_MARK_BIT, "ACTOR_TYPE07_FRAMES_MARKED_LEFT"),
    ("actor_behavior_type59", 1 << TYPE59_MARK_BIT, None),
], ids=["slot08", "slot59"])
def test_a_prologues_mark_bit_is_LIVE_by_the_time_the_shared_body_reads_it(name, mark, frames):
    """Slot 8's mark selects the frame LIST and slot 59's replaces the animation with a constant
    sprite, so each row has its own observable. Neither spawner can fire: the cadence byte is seeded
    away from both wraps."""
    what = f"{name} gate down"
    cursor = 3
    pokes = _slot07_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
                                 ACTOR + FLAGS2: bytes([0]),
                                 ACTOR + FIELD_23: bytes([cursor]),
                                 ACTOR + FIELD_31: bytes([1])})

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_30] & mark, f"{what}: the prologue's own bit is not in the record"
    if frames is None:
        assert _written_word(written, ACTOR, ACTOR_SPRITE) == TYPE07_SPRITE_LEFT, (
            f"{what}: the body animated, so it did not see slot 59's mark")
        assert ACTOR + FIELD_23 not in written
    else:
        assert _written_word(written, ACTOR, ACTOR_SPRITE) \
            == _image_word(wb(frames) + (cursor + 1) * ANIM_FRAME_BYTES), (
            f"{what}: the body took the unmarked frame list, so it did not see slot 8's mark")


# --- batch 33: the three collectables and the payout cluster --------------------------------------
# What separates these from the creature slots above is the CONTACT TEST: `bsr $5c6e / btst #1,d0`
# and nothing else, so the followed record collects one by standing on it and a shot cannot touch it
# at all. Every collect seed below therefore puts both records on one point with a followed sprite
# outside $5c6e's two gated bands, which is the mask-of-bit-1-alone recipe slot 51's cases use.
#
# THE PAYOUT CLUSTER READS HARDWARE, which is why slots 31 AND 32's collect arms and every case
# for $51ac and $517a passes `hw_seed=`. `bcd_add_random_1_to_4` sums $ff8209 and $ff8207 into its
# draw; undeclared, the model serves both cores a fabricated 0 and they agree on it, which is the
# T3-DATA false green ../PORTABILITY.md names. `test_the_award_draw_is_REFUSED_without_a_declaration`
# is the negative control.
#
# `bcd_expected` is leaf.py's — the DECIMAL statement of what the packed-BCD accumulators leave,
# shared by the three batteries that reach one. It moved there from test_hud.py in this batch for
# `hw_declared`'s reason: a battery must not reach into a sibling battery for a shared fact.

_AWARD = leaf.image_glue(AWARD)
_GOLD_DIGITS = leaf.register_glue(GOLD_DIGITS, [ctypes.c_uint32])

# The draw's glue is hand-rolled where the two above are factory-made, because the routine has a
# SECOND output that is not a register: the X its `abcd` leaves, which $5188's counter add folds in.
# The reconstruction hands that back through a pointer, so the glue owns the storage. The oracle
# reports no CCR (emu.REPORTED_REGS is d0..d7 and a0..a6), so no case here can compare it — what
# pins it is the whole-payout chain row in `PAYOUT_CASES`.
_bcd_random_fn = leaf.bind(BCD_RANDOM,
                           leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint)],
                           ctypes.c_uint32)


def _BCD_RANDOM(entry_d0):
    def glue(_lib, image):
        exit_extend = ctypes.c_uint(0)
        return _bcd_random_fn(image, entry_d0, ctypes.byref(exit_extend))

    return glue

# The instruction cap, DERIVED — the cluster's three pinned bodies plus the two accumulators, whose
# shape is test_hud.py's `_bcd_entry`: `movem / move.<n> d0,addend / lea / lea / length x abcd /
# movem / rts`, so one is BCD_ACCUMULATOR_FIXED_INSNS plus a digit pair per byte. That makes the
# counter 8 and the score 10 rather than the round 40 this line first carried — and a cap of 116
# over a 52-instruction run would not have caught the chain executing twice.
BCD_ACCUMULATOR_FIXED_INSNS = 6
AWARD_INSN_CAP = (INSN_COUNT[AWARD] + INSN_COUNT[BCD_RANDOM] + INSN_COUNT[GOLD_DIGITS]
                  + 2 * BCD_ACCUMULATOR_FIXED_INSNS + BCD_COUNTER_LEN + BCD_SCORE_LEN
                  + leaf.RUNNER_SENTINEL_INSN)

# A declaration whose two bytes DIFFER, so the ordered read stream the kit compares says which
# counter was read first — a port that swapped $ff8209 and $ff8207 would sum to the same number.
VCOUNT_LOW_SEED, VCOUNT_MID_SEED = 0x21, 0x40
VCOUNT_ORDERED = {leaf.VIDEO_COUNTER_LOW: VCOUNT_LOW_SEED,
                  leaf.VIDEO_COUNTER_MID: VCOUNT_MID_SEED}

# Where a case parks the scene descriptor: inside the image, clear of everything else these cases
# seed, and NOT a keyed address — the award word is the input the whole cluster turns on.
DESCRIPTOR_AT = 0x30000


def _draw_from(image, video_low, video_mid):
    """The 1..4 the routine picks: four BYTE adds, masked and stepped. The two counter bytes are
    what the case DECLARED and the other two are the followed record's x, high byte first."""
    total = (video_low + video_mid
             + image[FOLLOWED_DEFAULT] + image[FOLLOWED_DEFAULT + 1]) & 0xff
    return (total & BCD_RANDOM_MASK) + 1


def _award_pokes(award, followed_x=0x1234, counter=0x0000, score=0x00000000,
                 descriptor=DESCRIPTOR_AT):
    """Everything the payout reads: the descriptor and the pointer to it, the two accumulators, and
    the followed record's x — which is the draw's non-hardware entropy and so an INPUT here.

    NOT case-salted, unlike `_collectable_pokes`: every address here is one the payout READS and a
    case chooses, so there is no keyed block for a salt to key."""
    pokes = {RECORD_PTR_10424: longword(descriptor),
             descriptor + SCENE_GOLD_AWARD: word(award),
             FOLLOWED_DEFAULT: word(followed_x),
             BCD_COUNTER: word(counter),
             BCD_SCORE: longword(score),
             GOLD_DIGITS_AT: bytes([DIGIT_BLANK, DIGIT_BLANK]),
             TEXT_REQUEST: bytes([0]),
             TEXT_LIFETIME_REQUEST: word(0)}
    return pokes


# --- $51d8: the two digits ------------------------------------------------------------------------
@pytest.mark.parametrize("entry_d0,tens,units", [
    (0x0000, DIGIT_BLANK, ord("0")),
    (0x0005, DIGIT_BLANK, ord("5")),
    (0x0010, ord("1"), ord("0")),
    (0x0042, ord("4"), ord("2")),
    (0x0099, ord("9"), ord("9")),
    # The nibbles above 9 a packed-BCD byte never holds: `addi.b #$30` is applied anyway, so the
    # characters run on past '9' rather than being refused. Faithfulness, not correctness.
    (0x00af, ord("0") + 0xa, ord("0") + 0xf),
    # ...and a register whose other three bytes must not reach the field: only the low byte's two
    # nibbles are drawn, whatever the high word and the low word's own high byte hold.
    (0xdead1242, ord("4"), ord("2")),
], ids=lambda v: f"{v:#x}" if isinstance(v, int) and v > 0xff else None)
def test_the_gold_digits_are_two_characters_with_the_leading_zero_blanked(entry_d0, tens, units):
    what = f"text_write_gold_digits_a2ac d0={entry_d0:#010x}"
    pokes = {GOLD_DIGITS_AT: bytes([0, 0])}

    info = leaf.run(GOLD_DIGITS, _GOLD_DIGITS(entry_d0), [(GOLD_DIGITS_AT, 2)], what,
                    regs={"d0": entry_d0, "_pokes": pokes},
                    max_insns=_cap(GOLD_DIGITS))
    _assert_writes(info, {GOLD_DIGITS_AT: tens, GOLD_DIGITS_AT + 1: units}, what)


def test_the_gold_digits_land_inside_message_3s_own_shipped_string():
    """The claim the plate rests on, read off the IMAGE rather than restated: text_message_table's
    entry 2 (id WB_TEXT_MESSAGE_GOLD_GET, the ids being 1-based) points at a record whose string
    contains the two bytes this routine writes, and those two bytes ship as SPACES."""
    table = wb("TEXT_MESSAGE_TABLE")
    record = _image_long(table + (MESSAGE_GOLD_GET - wb("TEXT_MESSAGE_FIRST_ID")) * LONGWORD_BYTES)
    header = 2                       # {byte height, byte top scanline} before the string
    assert record + header <= GOLD_DIGITS_AT, (
        f"{GOLD_DIGITS_AT:#x} is not inside message {MESSAGE_GOLD_GET}'s string, which starts at "
        f"{record + header:#x}")
    assert bytes(harness.BASE_IMAGE[GOLD_DIGITS_AT:GOLD_DIGITS_AT + 2]) == b"  ", (
        "the two characters do not ship as spaces, so the shipped message already carries a number")


# --- $51ac: the packed-BCD draw -------------------------------------------------------------------
@pytest.mark.parametrize("video_low,video_mid,followed_x", [
    (0x00, 0x00, 0x0000),
    (0x01, 0x00, 0x0000),
    (0x02, 0x00, 0x0000),
    (0x03, 0x00, 0x0000),
    (0x21, 0x40, 0x1234),
    (0xff, 0xff, 0xffff),
    (0x00, 0x00, 0x0102),
], ids=lambda v: f"{v:#04x}")
def test_the_draw_is_the_two_declared_counters_plus_the_followed_x(video_low, video_mid,
                                                                  followed_x):
    """FOUR BYTE ADDS and nothing else. The parametrisation drives every value the mask can leave —
    a draw of 1, 2, 3 and 4 — and one seed per SOURCE, so a port that dropped any of the four terms
    is red on at least one row."""
    entry_d0 = 0x00
    what = (f"bcd_add_random_1_to_4 video={video_low:#04x}/{video_mid:#04x} "
            f"followed={followed_x:#06x}")
    pokes = {FOLLOWED_DEFAULT: word(followed_x)}
    image = harness.make_image(pokes)
    expected = _draw_from(image, video_low, video_mid)

    info = leaf.run(BCD_RANDOM, _BCD_RANDOM(entry_d0), [], what,
                    regs={"d0": entry_d0, "_pokes": pokes}, max_insns=_cap(BCD_RANDOM),
                    hw_seed={leaf.VIDEO_COUNTER_LOW: video_low,
                             leaf.VIDEO_COUNTER_MID: video_mid})
    assert not program_writes(info), f"{what}: the draw wrote memory, which it does not"
    assert info["ret"] == expected, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not the {expected:#x} the four "
        f"declared bytes give")
    assert info["regs"]["d0"] == expected, f"{what}: the ORIGINAL left d0={info['regs']['d0']:#x}"


# The KIT's own wording for an undeclared modeled-hardware read, and the two rules the refusal cases
# below follow because of it. A `match=` on a loose word like "declar" would also be satisfied by
# `leaf.run`'s OTHER assertions, whose messages open with the case's own ``what`` string — so the
# pattern is a phrase only harness.py produces, and the ``what`` those cases pass carries no word
# that could stand in for it. Without both, a mutant that DELETED the refusal would fall through to
# the byte-for-byte diff, fail on the fabricated 0, and be reported as the refusal firing.
# It also names the UNDECLARED refusal in particular: harness.py has three siblings (a STALE
# declaration, one that is too WIDE, and a VOLATILE slot read twice) whose messages share the phrase
# "modeled hardware byte", and each is a different defect with a different remedy.
HW_REFUSAL = "which this case does not declare"
UNDECLARED_CASE = "the draw with the counter pair left unstated"


def test_the_award_draw_is_REFUSED_without_a_declaration():
    """THE NEGATIVE CONTROL, and the reason every case above carries `hw_seed`. Undeclared, the
    model serves both cores a fabricated 0 for $ff8209/$ff8207, they agree on it, and a green run
    would be green about a draw with no machine input in it. The refusal is `differential`'s, so it
    surfaces as an AssertionError rather than as `emu.run` sinking (leaf.run's docstring)."""
    pokes = {FOLLOWED_DEFAULT: word(0x1234)}
    with pytest.raises(AssertionError, match=HW_REFUSAL):
        leaf.run(BCD_RANDOM, _BCD_RANDOM(0), [], UNDECLARED_CASE,
                 regs={"d0": 0, "_pokes": pokes}, max_insns=_cap(BCD_RANDOM))


@pytest.mark.parametrize("entry_d0,expected_low", [
    (0x00, 0x01),      # 0 + 1
    (0x08, 0x09),      # 8 + 1, still inside the low digit
    (0x09, 0x10),      # THE DECIMAL CARRY: a binary add would give $0a
    (0x19, 0x20),
    (0x99, 0x00),      # ...and the carry out of the byte, which wraps to 00
], ids=lambda v: f"{v:#04x}")
def test_the_draw_is_added_in_PACKED_BCD_and_not_in_binary(entry_d0, expected_low):
    """The whole of the rename. A draw of exactly ONE is forced (all four source bytes zero), so
    what these rows separate is the ADDITION: `abcd` corrects the nibble and a binary `add.b` — or
    the `and.b` the disassembler printed — would not."""
    what = f"bcd_add_random_1_to_4 {entry_d0:#04x} + 1"
    pokes = {FOLLOWED_DEFAULT: word(0)}
    entry = 0xdead1200 | entry_d0

    info = leaf.run(BCD_RANDOM, _BCD_RANDOM(entry), [], what,
                    regs={"d0": entry, "_pokes": pokes}, max_insns=_cap(BCD_RANDOM),
                    hw_seed=leaf.hw_declared())
    # `abcd` writes the LOW BYTE alone, so the low word's high byte and the register's high half
    # both come back as the caller left them — which is what makes the entry d0 an input.
    assert info["ret"] == (0xdead1200 | expected_low), (
        f"{what}: {info['ret']:#010x} is not the packed-BCD sum with the caller's other bytes kept")


# --- $517a: the payout -----------------------------------------------------------------------------
# EVERY CONSUMER READS A DIFFERENT WIDTH of the one register, which is what these cases separate:
# the draw and the digits take d0's low BYTE, the counter stages its whole WORD, and the score's
# addend is a constant longword with nothing of the award in it.

# A descriptor address the 24-bit bus reaches and the loaded image does not, for the case about a
# pointer the game has not filled in yet. bus.h answers such a read with zero and the oracle's shim
# answers the ORACLE with zero, which is the agreement that makes the case a differential at all.
DESCRIPTOR_OFF_IMAGE = 0xf00000


# The X `text_write_gold_digits_a2ac` ($51d8) leaves, and so the entry X of the score add at $5196
# that follows it — 0 on both of that routine's exits, argued from its bytes in `_model_award`.
GOLD_DIGITS_LEAVE_EXTEND_CLEAR = 0


def _model_award(image, video_low=VCOUNT_LOW_SEED, video_mid=VCOUNT_MID_SEED, award=None):
    """{address: byte} for one payout — the WRITE SET and the values together, composed out of the
    batteries that own each half:
    `bcd_expected` is leaf.py's DECIMAL statement of the two accumulators, and the draw is this
    section's own. Nothing here restates src/behavior.c's nibble arithmetic.

    THE X CHAIN IS MODELLED, not assumed away: `bcd_add_random_1_to_4`'s `abcd d1,d0` at $51d4 is
    the last instruction before `bsr $b562` at $5188, so the carry it leaves is the counter's ENTRY
    X. The score's own entry X is 0 by a reading of $51d8, which runs between the two accumulators:
    its last X-writer on BOTH exits is `addi.b #$30` on a nibble masked to $0..$f, which cannot
    carry out of $30..$3f, and `ror.w`/`andi.w`/`move.b` leave X alone.
    """
    if award is None:
        # Slot 38's gold arm hands the same five calls WB_STAGE_NUMBER instead, which is the ONE
        # thing it changes about them — so the amount is a parameter and the model is not copied.
        descriptor = int.from_bytes(image[RECORD_PTR_10424:RECORD_PTR_10424 + LONGWORD_BYTES],
                                    "big")
        at = (descriptor + SCENE_GOLD_AWARD) & BUS_ADDR_MASK
        award = leaf.u16(image, at) if at + WORD_BYTES <= harness.IMAGE_SIZE else 0

    extend = [0]
    low = _abcd(award & 0xff, _draw_from(image, video_low, video_mid), extend)
    d0 = (award & 0xff00) | low

    counter = bcd_expected(leaf.u16(image, BCD_COUNTER), d0, BCD_COUNTER_LEN, False, extend[0])
    score = bcd_expected(int.from_bytes(image[BCD_SCORE:BCD_SCORE + BCD_SCORE_LEN], "big"),
                         COLLECT_SCORE, BCD_SCORE_LEN, False, GOLD_DIGITS_LEAVE_EXTEND_CLEAR)
    tens = (low >> BCD_DIGIT_BITS) & BCD_DIGIT_MASK

    out = {}
    # The score's `move.l d0,$bd78` overwrites the counter's `move.w`, so the staging bytes end as
    # the score's addend — and all four are in the ledger because both stores happened.
    _put(out, BCD_ADDEND, COLLECT_SCORE, LONGWORD_BYTES)
    _put(out, BCD_COUNTER, counter.value, BCD_COUNTER_LEN)
    _put(out, BCD_SCORE, score.value, BCD_SCORE_LEN)
    out[GOLD_DIGITS_AT] = DIGIT_BLANK if tens == 0 else ord("0") + tens
    out[GOLD_DIGITS_AT + 1] = ord("0") + (low & BCD_DIGIT_MASK)
    out[TEXT_REQUEST] = MESSAGE_GOLD_GET
    _put(out, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    return out


def _abcd(accumulator, addend, extend):
    """One `abcd` byte pair, as the 68000's decimal correction — the same statement src/hud.c makes,
    kept here rather than imported because what a case needs is a SECOND spelling of it."""
    low = (accumulator & 0xf) + (addend & 0xf) + extend[0]
    if low > 9:
        low += 6
    total = low + (accumulator & 0xf0) + (addend & 0xf0)
    extend[0] = 1 if total > 0x99 else 0
    return (total - 0xa0 if extend[0] else total) & 0xff


def _run_award(what, pokes, video=VCOUNT_ORDERED):
    image = harness.make_image(pokes)
    expected = _model_award(image, video[leaf.VIDEO_COUNTER_LOW], video[leaf.VIDEO_COUNTER_MID])
    info = leaf.run(AWARD, _AWARD, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=AWARD_INSN_CAP, hw_seed=video)
    _assert_writes(info, expected, what)
    return info


# THE AWARD THAT DRIVES THE CHAIN: its low BCD byte plus the draw the two declared counters give
# passes $99, so `bcd_add_random_1_to_4`'s `abcd d1,d0` at $51d4 carries OUT — and $5188's counter
# add, the very next instruction, folds that carry into the gold counter's lowest digit.
AWARD_THAT_CARRIES_INTO_THE_COUNTER = 0x0096

# (award, counter, score).
PAYOUT_CASES = (
    (0x0012, 0x0100, 0x00001000),
    (0x0005, 0x0000, 0x00000000),      # a one-digit amount: the TENS character is blanked
    (0x0095, 0x0900, 0x00099999),      # the largest low byte whose `abcd` cannot carry out
    (AWARD_THAT_CARRIES_INTO_THE_COUNTER, 0x0900, 0x00099999),   # ...and one more, which does
    (0x1234, 0x0000, 0x00000000),      # a two-BYTE award: the counter stages the word, the digits
                                       # draw the low byte alone, so the two disagree by design
)


@pytest.mark.parametrize("award,counter,score", PAYOUT_CASES, ids=lambda v: f"{v:#06x}")
def test_the_payout_moves_both_accumulators_the_message_and_its_digits(award, counter, score):
    what = f"hud_award_gold_from_descriptor award={award:#06x}"
    _run_award(what, _award_pokes(award, counter=counter, score=score))


def test_exactly_one_payout_row_carries_the_draw_out_into_the_counter():
    """The premise `AWARD_THAT_CARRIES_INTO_THE_COUNTER` names, computed off the seeds rather than
    asserted from a reader's arithmetic — the draw is four here, so $96 is the smallest award whose
    `abcd` carries and $95 the largest whose does not. If the video-counter declaration or the
    followed record's x ever moved, the draw would change and the row would stop driving the chain
    while staying green."""
    image = harness.make_image(_award_pokes(0))
    draw = _draw_from(image, VCOUNT_LOW_SEED, VCOUNT_MID_SEED)
    carrying = []
    for award, _counter, _score in PAYOUT_CASES:
        extend = [0]
        _abcd(award & 0xff, draw, extend)
        if extend[0]:
            carrying.append(award)
    assert carrying == [AWARD_THAT_CARRIES_INTO_THE_COUNTER], (
        f"a draw of {draw} makes {[hex(a) for a in carrying]} carry out of the award's own `abcd` — "
        f"the rows above need exactly {AWARD_THAT_CARRIES_INTO_THE_COUNTER:#06x} to")


# A CASE THAT COULD NOT FAIL, removed rather than kept (a measured trim, ../STATUS.md records it):
# "the score is a constant and not the award" ran two more differentials to assert what `_run_award`
# had already asserted — `_assert_writes` requires the write set to EQUAL `_model_award`'s, and that
# model's score term is `bcd_expected(score, COLLECT_SCORE, ...)` with no award in it. Any port that
# let the award reach the score was already red inside `_run_award`, on every row above.


def test_the_award_word_is_read_through_the_bus_and_a_stale_pointer_pays_the_draw_alone():
    """WB_RECORD_PTR_10424 is a runtime pointer that ships as ZERO, so the amount is fetched through
    an address the reconstruction computed and bus.h guards. Off the image both cores read 0 and the
    payout is the draw alone — a case that would be a false green if either side had refused."""
    what = "hud_award_gold_from_descriptor off-image descriptor"
    pokes = _award_pokes(0, descriptor=DESCRIPTOR_OFF_IMAGE)
    info = _run_award(what, pokes)
    paid = leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, what)
    assert 1 <= paid <= 4, f"{what}: {paid:#06x} is not a bare one-to-four draw"


def test_the_payout_reaches_the_draw_and_is_refused_without_a_declaration():
    """The cluster's own negative control: the refusal $51ac raises really does reach the caller two
    frames up, so no whole-payout case can be green on a fabricated counter."""
    pokes = _award_pokes(0x0012)
    with pytest.raises(AssertionError, match=HW_REFUSAL):
        leaf.run(AWARD, _AWARD, [], UNDECLARED_CASE, regs={"_pokes": pokes},
                 max_insns=AWARD_INSN_CAP)


# --- slots 28, 30, 31, 32 and 33, arm by arm ---------------------------------------------------------------
COLLECT_SLOTS = (28, 30, 31, 32, 33)
COLLECT_HANDLERS = {slot: f"actor_behavior_type{slot:02d}" for slot in COLLECT_SLOTS}

# Where a collectable case stands its record, and where the followed one stands to pick it up: ONE
# point, with a followed sprite outside both of $5c6e's gated bands so the mask comes back with the
# footprint bit alone. Slot 51's own body-overlap case uses the same recipe — and this IS that
# seed's x, taken from `_type51_pokes` through `_band5a_pokes` rather than restated, which
# `test_the_collect_point_is_the_seeded_records_own_x` keeps honest.
COLLECT_X = 0x0100


# A countdown that is neither 1 (slot 28 reads WB_ACTOR_FIELD_12's BYTE and would expire on it) nor
# WB_ACTOR_FLICKER_AT_FIELD_12 (slots 30 and 31 read the WORD and would start flickering), so a case
# that is not about the countdown never trips it.
COLLECT_FIELD_12_IDLE = 0x1010

# ...and slot 32's hop counter, seeded well above 1 so a landing relaunches rather than spending the
# last hop, which is the arm its own cases below drive on purpose.
COLLECT_FIELD_10_IDLE = 0x08


def _collectable_pokes(what, slot, fields=None, collected=False, ground=True):
    """A collectable of `slot`'s type on ACTOR, out of contact unless `collected` puts the followed
    record on top of it.

    DELEGATES to `_band5a_pokes`, which is `_type51_pokes` with the type overridden — the tier's
    shared premise (a followed record out of every arm of $5c6e's reach, a WIDE
    WB_BG_SCROLL_LIMIT_X, the ground rows the settle lands on) is stated THERE and not restated
    here. What this adds is only what a collectable reads and that seed does not name: the two
    countdown bytes, the animation cursor, the two accumulators the payout moves, and the position
    that puts the followed record ON the record rather than away from it.
    """
    base = {ACTOR + FIELD_18: bytes([0]), ACTOR + FIELD_30: bytes([0]),
            ACTOR + FIELD_31: bytes([0]), ACTOR + FIELD_12: word(COLLECT_FIELD_12_IDLE),
            ACTOR + FIELD_10: bytes([COLLECT_FIELD_10_IDLE]),
            BCD_COUNTER: word(0x0100), BCD_SCORE: longword(0x00001000),
            FRAME_TOGGLE: word(0), TYPE30_CURSOR: word(0),
            # Batch 34's two rows read three more globals between them, and slot 32's latches decide
            # which arm it takes — so a collectable seed states them exactly as it states the two
            # countdowns above. The hops latch is DOWN, so a landing really does drive the machine.
            TYPE32_WALKING: bytes([0]), TYPE32_HOPS_SPENT: bytes([0]),
            TYPE32_CURSOR: word(0),
            PANEL_FRAME_REWIND: word(0), PANEL_FRAME_HOLD: word(0)}
    if collected:
        base[FOLLOWED_DEFAULT + ACTOR_X] = word(COLLECT_X)
        base[FOLLOWED_DEFAULT + ACTOR_Y] = word(STAND_Y)
    return _band5a_pokes(what, slot, leaf.overlay(base, fields or {}), ground=ground)


def _assert_contact(image, what, wanted):
    """The premise every collect case rests on, taken from the battery's own model of $5c6e rather
    than from the seed's geometry: bit 1 up (or down) and the two gated bits never in the way.

    Takes the IMAGE the caller already built rather than the pokes, so a collect case builds one."""
    mask = _model_overlap_mask(image, ACTOR, FOLLOWED_DEFAULT)
    assert bool(mask & (1 << BODY_BIT)) is wanted, (
        f"{what}: the seed's overlap mask is {mask:#x}, so this case drives the other arm")
    assert not mask & ((1 << STRIKE_BIT) | (1 << POINT_BIT)), (
        f"{what}: the seed reaches a GATED bit as well, which these handlers never read")


# WHAT EACH COLLECT ARM PAYS, as the addresses it is allowed to touch — and they are FOUR
# different sets, which is what "and by nothing else" in the first case's name is about. Slot 28
# moves the two packed-BCD accumulators and the four bytes they stage through; slot 30 moves the
# meter word alone; slot 33 the two panel words and the score; only slots 31 and 32 reach the
# payout cluster, and only those two read hardware.
COLLECT_PAYOUT_BAND = {
    "actor_behavior_type28": [(BCD_ADDEND, LONGWORD_BYTES), (BCD_COUNTER, BCD_COUNTER_LEN),
                              (BCD_SCORE, BCD_SCORE_LEN)],
    # Slot 33 pays the PANEL and the score, and nothing else in the game does that pair.
    "actor_behavior_type33": [(BCD_ADDEND, LONGWORD_BYTES), (BCD_SCORE, BCD_SCORE_LEN),
                              (PANEL_FRAME_REWIND, WORD_BYTES), (PANEL_FRAME_HOLD, WORD_BYTES)],
    "actor_behavior_type30": [(METER_VALUE, WORD_BYTES)],
}
# The two rows that pay through the $517a cluster, and so the two whose collect arm READS HARDWARE.
PAYING_HANDLERS = ("actor_behavior_type31", "actor_behavior_type32")


def _collect_band(name, image):
    """What a collect frame may write: the handler's own band, WB_ACTOR_REQUEST9_SFX's — which
    test_sound.py owns and this file takes from `_sfx_bytes` rather than listing — and that
    handler's OWN payout. Slot 31's comes from `_model_award`, so the band and the values it is
    checked against are one statement."""
    band = _handler_band(name) + merge_bands(_sfx_bytes(image, REQUEST9_SFX, SND_CHANNEL_A))
    if name in PAYING_HANDLERS:
        return band + merge_bands(_model_award(image))
    return band + COLLECT_PAYOUT_BAND[name]


def test_the_collect_point_is_the_seeded_records_own_x():
    """COLLECT_X is `_type51_pokes`'s x reached through `_band5a_pokes`, not a number of this
    section's — and the collect seeds put the FOLLOWED record on it. If that seed ever moves, the
    two records stop coinciding and every collect case below would quietly drive the waiting arm
    instead, so the equality is asserted rather than assumed."""
    image = harness.make_image(_collectable_pokes("the collect point", 28))
    assert leaf.u16(image, ACTOR + ACTOR_X) == COLLECT_X, (
        f"the tier's seed stands its record at {leaf.u16(image, ACTOR + ACTOR_X):#06x}, not the "
        f"{COLLECT_X:#06x} the collect cases put the followed record on")


@pytest.mark.parametrize("slot", COLLECT_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_a_collectable_is_taken_by_the_FOOTPRINT_bit_and_by_nothing_else(slot):
    """`bsr $5c6e / btst #1,d0` and no actor_hit_by_player_shot in front of it. The case drives the
    contact and then asserts the one write every arm shares — the free marker — so what it pins
    is that the frame ENDED the record rather than which currency it paid."""
    name = COLLECT_HANDLERS[slot]
    what = f"{name} collected"
    fields = {ACTOR + FIELD_30: bytes([TYPE30_COLLECT_MIN])} if slot == 30 else {}
    pokes = _collectable_pokes(what, slot, fields, collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    # Only the PAYING_HANDLERS rows read the video counter, and only through the payout — the
    # others must NOT be handed a declaration they do not need, or the row would stop saying they
    # read no hardware.
    declared = VCOUNT_ORDERED if name in PAYING_HANDLERS else None

    info = _run_handler(name, what, pokes, band=_collect_band(name, image), hw_seed=declared)
    assert _written_word(program_writes(info), ACTOR, ACTOR_X) == FREE_MARKER, (
        f"{what}: the slot was not handed back")


@pytest.mark.parametrize("slot", COLLECT_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_a_collectable_out_of_reach_keeps_its_slot(slot):
    """The control for the row above: the same seed with the followed record elsewhere runs the
    WAITING arm, and the countdown is seeded far from zero so nothing else can free the record."""
    name = COLLECT_HANDLERS[slot]
    what = f"{name} out of reach"
    pokes = _collectable_pokes(what, slot, collected=False)
    _assert_contact(harness.make_image(pokes), what, False)

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert ACTOR + ACTOR_X not in written or _written_word(written, ACTOR, ACTOR_X) != FREE_MARKER, (
        f"{what}: an untouched record freed its own slot")


# THE ENTRY X OF SLOT 28's FIRST ACCUMULATOR. The instruction before `bsr $b562` at $4e5a is
# `move.w #$5,d0`, and before that `bsr $6786` — sound_request_9, which tail-jumps into the sound
# module, so what it leaves in X is not readable off these bytes. It is pinned by the DIFFERENTIAL
# instead: the ordinary row below seeds $0100 and five more is $0105 with X clear and $0106 with X
# set, so the byte-for-byte diff would already be red if the trigger left a carry behind.
TYPE28_COUNTER_ENTRY_EXTEND = 0

# A counter within WB_ACTOR_TYPE28_GOLD of $9999, so the counter's LAST `abcd` carries OUT and the
# score add two instructions later folds that carry into its own lowest digit.
TYPE28_COUNTER_AT_THE_WRAP = 0x9996

# ...and the counter that carries out of the accumulator's LOWEST byte and NOT out of its top one:
# $96 + 5 is $01 with a carry, which the tens digits then absorb. The score must NOT gain a unit
# here, which is what separates "the X the routine leaves" from "the X its FIRST `abcd` leaves" —
# the mutation `exit/add-returns-the-carry-out-of-the-LOWEST-byte` survived until this row existed,
# because the wrap row above carries out of BOTH bytes and cannot tell the two apart.
TYPE28_COUNTER_CARRYING_ONE_BYTE = 0x0096

# (counter, score) — the ordinary payout, then the two that drive the chain's two answers.
TYPE28_PAYOUT_CASES = ((0x0100, 0x00001000),
                       (TYPE28_COUNTER_AT_THE_WRAP, 0x00001000),
                       (TYPE28_COUNTER_CARRYING_ONE_BYTE, 0x00001000))


@pytest.mark.parametrize("counter,score", TYPE28_PAYOUT_CASES,
                         ids=lambda v: f"{v:#06x}")
def test_slot28_pays_five_gold_and_the_collect_score(counter, score):
    """The two accumulators, compared against leaf.py's DECIMAL model — and they run BACK TO BACK
    here, `bsr $b562` then `bsr $b5a2` with only a `move.l #imm,d0` between, which does not touch X.
    So the SCORE is entered with the X the counter's last `abcd` left, and the second row is the
    seed that makes that a 1: it was red against the port that folded in a 0 there, off by one in
    the score's low byte and by nothing else."""
    what = f"actor_behavior_type28 collected counter={counter:#06x}"
    pokes = _collectable_pokes(what, 28, {BCD_COUNTER: word(counter),
                                          BCD_SCORE: longword(score)}, collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)

    info = _run_handler("actor_behavior_type28", what, pokes, band=_collect_band(
        "actor_behavior_type28", image) + [(BCD_ADDEND, LONGWORD_BYTES),
                                           (BCD_COUNTER, BCD_COUNTER_LEN),
                                           (BCD_SCORE, BCD_SCORE_LEN)])
    counted = bcd_expected(counter, TYPE28_GOLD, BCD_COUNTER_LEN, False,
                           TYPE28_COUNTER_ENTRY_EXTEND)
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, what) == counted.value
    assert leaf.read_int(info, BCD_SCORE, BCD_SCORE_LEN, what) \
        == bcd_expected(score, COLLECT_SCORE, BCD_SCORE_LEN, False, counted.extend).value


def test_exactly_one_slot28_payout_row_carries_out_of_the_counter():
    """The premise the rows above rest on, asserted rather than left to a reader's arithmetic: if
    WB_ACTOR_TYPE28_GOLD or a seed ever moved, the chain row would quietly stop carrying and the
    set would pass while pinning only the X = 0 half again."""
    carrying = [counter for counter, _score in TYPE28_PAYOUT_CASES
                if bcd_expected(counter, TYPE28_GOLD, BCD_COUNTER_LEN, False,
                                TYPE28_COUNTER_ENTRY_EXTEND).extend]
    assert carrying == [TYPE28_COUNTER_AT_THE_WRAP], (
        f"{[hex(c) for c in carrying]} are the counter seeds whose four digits wrap — the rows "
        f"above need exactly one, and it must be {TYPE28_COUNTER_AT_THE_WRAP:#06x}")


def test_one_slot28_payout_row_carries_out_of_the_low_byte_alone():
    """...and the other half of that premise, which is what makes the pair separate the ACCUMULATOR's
    carry from its FIRST digit pair's: `TYPE28_COUNTER_CARRYING_ONE_BYTE` must carry out of the low
    byte (so a port returning that bit scores a unit too many) while leaving the four digits inside
    their range (so the faithful port scores none)."""
    low_carry = [TYPE28_COUNTER_ENTRY_EXTEND]
    _abcd(TYPE28_COUNTER_CARRYING_ONE_BYTE & 0xff, TYPE28_GOLD, low_carry)
    assert low_carry[0], (
        f"{TYPE28_COUNTER_CARRYING_ONE_BYTE:#06x} plus {TYPE28_GOLD} does not carry out of the low "
        f"byte, so the row pins nothing the ordinary row does not")
    assert not bcd_expected(TYPE28_COUNTER_CARRYING_ONE_BYTE, TYPE28_GOLD, BCD_COUNTER_LEN, False,
                            TYPE28_COUNTER_ENTRY_EXTEND).extend, (
        f"{TYPE28_COUNTER_CARRYING_ONE_BYTE:#06x} wraps all four digits as well, which makes it the "
        f"wrap row over again")


def test_slot28_cannot_be_collected_while_it_is_moving():
    """The SECOND gate: `btst #0,8(a0) / bne` sends a record with WB_ACTOR_FLAG_MOVING_BIT up to the
    waiting arm however hard the followed record is standing on it."""
    what = "actor_behavior_type28 collected mid-hop"
    pokes = _collectable_pokes(what, 28, {ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                          ACTOR + SPEED: bytes([2])}, collected=True)
    _assert_contact(harness.make_image(pokes), what, True)

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert BCD_COUNTER not in written, f"{what}: a moving record paid out"
    assert ACTOR + ACTOR_X not in written, f"{what}: a moving record handed its slot back"
    # ...and the waiting arm really RAN: actor_hop_ascend_step spends the record's own speed byte,
    # which is the one write that separates "took the other arm" from "did nothing at all".
    assert written[ACTOR + SPEED] == 1, f"{what}: the ascent did not run"


# --- slot 28's walk, and the WORD test at $4e98 ----------------------------------------------------
# THE ONE BLOCKED-STEP TEST IN THIS FILE THAT READS A WORD. The probes leave a map column, a clamp
# limit or a parked x in the byte ABOVE the outcome (map.h), so `tst.w d0` answers "turn round" only
# when that byte is zero as well — which the tier's every other `tst.b d0` would not. The two rows
# below drive one blocked step of each kind, and BOTH are reachable off the game's own geometry.
#
# THE MUTANT THIS CATCHES is `step_word_was_blocked_at_column_0` replaced by `step_was_blocked`:
# the clamped row
# reports $0100, whose byte is WB_ACTOR_STEP_BLOCKED, so a byte-testing port turns the record round
# where the original does not.
WALK_X_AT_COLUMN_0 = 8            # x + half_width + step stays inside map column 0
TIGHT_LIMIT = 0x14                # WB_BG_SCROLL_LIMIT_X small enough that COLLECT_X is past it
WALK_STEP = 2


def _walk_pokes_28(what, fields=None, block=False, facing=0):
    pokes = _collectable_pokes(what, 28, leaf.overlay(
        {ACTOR + FIELD_31: bytes([WALK_STEP]), ACTOR + ACTOR_FLAGS: bytes([facing])}, fields or {}))
    return _block_the_walk(pokes) if block else pokes


def test_slot28_turns_round_when_the_whole_low_word_of_the_probe_is_zero():
    """A step blocked in map column 0: the probe's own column sits in the byte above the outcome and
    is zero here too, so `tst.w d0` is zero and the `bchg #3,8(a0)` fires.

    ONE ROW, NOT ONE PER FACING. `_block_the_walk` fills the whole probe row and from this x BOTH
    probes land in column 0, so the two arms report the same $0000 and commit the same (zero) move —
    a facing parametrisation here would add a row that kills no mutant the other does not. What
    separates the arms is the case below, where they leave different x."""
    what = "actor_behavior_type28 blocked at column 0"
    pokes = _walk_pokes_28(what, {ACTOR + ACTOR_X: word(WALK_X_AT_COLUMN_0)}, block=True)

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side bit did not FLIP, so the word test read something other than zero")
    assert written[ACTOR + FIELD_31] == WALK_STEP - 1, f"{what}: the step byte was not counted down"


def test_slot28_does_NOT_turn_round_when_the_LEFT_probe_runs_off_the_map():
    """THE LEFT ARM, and the only case that separates it from the right one. `btst #3,8(a0)` picks
    the probe, and the bit is reachable in play from this handler's own `bchg` — a record that turns
    round walks left on the very next frame — so a port that reached for `step_right` outright has
    to be caught somewhere.

    A left probe that goes NEGATIVE parks the record at its own half-width and reports the probe's
    column, which is negative too: the byte above the outcome is $ff and the `bchg` does not fire.
    `asr.w #4` is what makes the column signed; an unsigned shift would report a huge positive one.
    The x is chosen so the RIGHT arm would commit a DIFFERENT one (`x + d7`, not the half-width),
    which is what makes the arms observable apart rather than merely both non-flipping."""
    what = "actor_behavior_type28 walking off the left edge"
    half_width, x = 4, 1
    pokes = _walk_pokes_28(what, {ACTOR + ACTOR_X: word(x), ACTOR + HALF_WIDTH: word(half_width)},
                           facing=1 << SIDE_BIT)
    # The cell the negative column lands on is one byte BELOW the probe's row and outside the window
    # `_stand_on_ground` seeds, so it is stated rather than left keyed — a WB_MAP_TILE_BLOCK there
    # would send the walk down the backing-off path instead of the off-the-map one.
    pokes[COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS
          + DEFAULT_STRIDE * (STAND_ROW - 1) - 1] = bytes([0])

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == half_width, (
        f"{what}: the record is at {_written_word(written, ACTOR, ACTOR_X):#06x}, not parked on the "
        f"map's left edge — the RIGHT probe would have committed {x + WALK_STEP:#06x} instead")
    assert half_width != x + WALK_STEP, "the two arms would leave the same x, so this case is blind"
    # The record was seeded FACING LEFT, so "did not turn round" is the bit still UP. (The rest of
    # the byte does move: actor_relaunch_and_anim_5160 raises WB_ACTOR_FLAG_MOVING_BIT and
    # WB_ACTOR_FLAG_LAUNCHED_BIT on the same frame.)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side bit flipped — the test read the outcome BYTE, not the whole word")


def test_slot28_does_NOT_turn_round_when_the_probes_high_byte_is_set():
    """THE PIN ON THE WORD, and the case a `tst.b` port fails. A step past the level's right edge
    comes back with the CLAMP LIMIT under the outcome byte — `WB_BG_SCROLL_LIMIT_X + $f0 - 14(a0)`,
    which is $0100 for the limit seeded here — so the byte says BLOCKED and the word does not, and
    the record keeps facing the way it was."""
    what = "actor_behavior_type28 clamped at the level edge"
    pokes = _walk_pokes_28(what, {SCROLL_LIMIT_X: word(TIGHT_LIMIT)})
    clamped = TIGHT_LIMIT + wb("BG_SCROLL_LIMIT_BIAS") - 4
    assert clamped >> 8, "the seeded limit does not put anything in the probe's high byte"
    assert clamped & 0xff == 0, "the clamp's low byte is not the one the outcome overwrites"

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side bit flipped — the test read the outcome BYTE, not the whole word")
    assert _written_word(written, ACTOR, ACTOR_X) == clamped, (
        f"{what}: the record was not parked on the level's edge, so the clamp never fired")


def test_slot28_skips_the_whole_step_while_its_distance_byte_is_zero():
    """`move.b 31(a0),d7 / beq` jumps the probe AND the `subq.b #1,31(a0)` below it, so a zero byte
    is left alone rather than wrapping to $ff."""
    what = "actor_behavior_type28 with no step"
    pokes = _walk_pokes_28(what, {ACTOR + FIELD_31: bytes([0])})

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert ACTOR + FIELD_31 not in written, f"{what}: the zero step byte was decremented"
    assert ACTOR + ACTOR_X not in written, f"{what}: a skipped step still moved the record"


# --- slot 28's TWO expiries -------------------------------------------------------------------------
def test_slot28_flickers_on_its_first_expiry_and_frees_itself_on_the_second():
    """`bset #6,8(a0) / bne` reads the bit the instruction OVERWROTE. So the first expiry finds the
    flicker down, raises it and reloads WB_ACTOR_FIELD_12 with WB_ACTOR_TYPE28_FIELD_12_RELOAD; the
    second finds it up and hands the slot back with no reload at all. Both rows run the SAME
    countdown value, so what separates them is the flag byte and nothing else."""
    for flags, expect_free in ((0, False), (1 << FLICKER_BIT, True)):
        what = f"actor_behavior_type28 expiry, flags={flags:#04x}"
        pokes = _collectable_pokes(what, 28, {ACTOR + FIELD_12: word(0x0100),
                                              ACTOR + ACTOR_FLAGS: bytes([flags])})
        info = _run_handler("actor_behavior_type28", what, pokes)
        written = program_writes(info)
        assert written[ACTOR + ACTOR_FLAGS] & (1 << FLICKER_BIT), (
            f"{what}: the `bset` did not leave the bit up, whichever arm it took")
        if expect_free:
            assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
            assert written[ACTOR + FIELD_12] == 0, f"{what}: the countdown was reloaded anyway"
        else:
            assert written[ACTOR + FIELD_12] == TYPE28_FIELD_12_RELOAD
            assert ACTOR + ACTOR_X not in written, f"{what}: the first expiry freed the slot"


def test_slot28_counts_its_byte_down_without_expiring():
    """The ordinary frame: `subq.b #1,12(a0)` alone, and the flicker bit is not touched."""
    what = "actor_behavior_type28 counting down"
    pokes = _collectable_pokes(what, 28, {ACTOR + FIELD_12: word(0x0500)})

    info = _run_handler("actor_behavior_type28", what, pokes)
    written = program_writes(info)
    assert written[ACTOR + FIELD_12] == 4
    # The flag byte is written by the settle and the relaunch either way, so what this asserts is
    # the BIT rather than the address.
    assert not written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << FLICKER_BIT), (
        f"{what}: a live countdown raised the flicker bit")


# --- slot 30: the count-up gate, the meter, the drift and the GLOBAL cursor ------------------------
@pytest.mark.parametrize("field_30,collected", [
    (TYPE30_COLLECT_MIN - 1, False),
    (TYPE30_COLLECT_MIN, True),
    # `cmpi.b #$a,30(a0) / blt` is SIGNED, so a byte that has counted past $7f reads as NEGATIVE and
    # is refused again — a record left alone for 128 frames becomes uncollectable until it wraps.
    # ONE row, not two: $ff was a second and is trimmed, being the same claim as $80 (both negative
    # signed, both above the minimum unsigned, so both kill the signed-to-unsigned mutant alone).
    (0x80, False),
], ids=lambda v: f"{v:#04x}" if isinstance(v, int) else str(v))
def test_slot30_refuses_the_collect_until_its_count_up_byte_reaches_the_minimum(field_30,
                                                                               collected):
    what = f"actor_behavior_type30 count-up {field_30:#04x}"
    pokes = _collectable_pokes(what, 30, {ACTOR + FIELD_30: bytes([field_30])}, collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)

    info = _run_handler("actor_behavior_type30", what, pokes,
                        band=_collect_band("actor_behavior_type30", image))
    written = program_writes(info)
    took = ACTOR + ACTOR_X in written and _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
    assert took is collected, (
        f"{what}: the record {'was' if took else 'was not'} collected, against the signed compare")
    if not collected:
        assert written[ACTOR + FIELD_30] == (field_30 + 1) & 0xff, (
            f"{what}: the waiting arm did not count the byte up")


@pytest.mark.parametrize("value,maximum,expect_write", [
    (0x0010, 0x0028, False),   # +4 falls short: THE SHIPPED BUG — the sum is computed and dropped
    (0x0023, 0x0028, False),   # ...one short of reaching it, still nothing
    (0x0024, 0x0028, True),    # exactly reaching it: the MAXIMUM is stored, not the sum
    (0x0030, 0x0028, True),    # ...and OVER it, which stores the maximum DOWNWARD. An already-full
                               # $0028 was a third row here and is trimmed: same arm, same stored
                               # value, and this one witnesses the downward store as well
    # THE SIGNEDNESS, which the four rows above cannot see: `cmp.w $b6f8.l,d0 / blt` is a SIGNED
    # compare, and every value they use is small and positive, so an unsigned port answers the same
    # on all four. Here `addq.w #4` wraps the meter into $8002 — NEGATIVE as a word — so the signed
    # reading falls short and stores nothing while an unsigned one would see a huge value and
    # refill. A reviewer dropped both (int16_t) casts from type30_top_up_the_meter and the whole
    # suite stayed green; this is the row that reds it.
    (0x7ffe, 0x0028, False),
], ids=lambda v: f"{v:#06x}" if isinstance(v, int) else str(v))
def test_slot30_only_refills_the_meter_when_the_step_would_REACH_the_maximum(value, maximum,
                                                                            expect_write):
    """`move.w $b6fa,d0 / addq.w #4,d0 / cmp.w $b6f8,d0 / blt` — and no store on the `blt` arm. So a
    pickup is worth NOTHING unless the player was already within WB_ACTOR_TYPE30_METER_STEP of full,
    and worth exactly "top up" when they were. That is the original's behaviour and not a
    simplification; hud_meter_add_clamped ($b6fe) is the routine that adds properly and this handler
    does not call it."""
    what = f"actor_behavior_type30 meter {value:#06x}/{maximum:#06x}"
    pokes = _collectable_pokes(what, 30, {ACTOR + FIELD_30: bytes([TYPE30_COLLECT_MIN]),
                                          METER_VALUE: word(value), METER_MAX: word(maximum)},
                               collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    band = _collect_band("actor_behavior_type30", image) + [(METER_VALUE, WORD_BYTES)]

    info = _run_handler("actor_behavior_type30", what, pokes, band=band)
    written = program_writes(info)
    assert (METER_VALUE in written) is expect_write, (
        f"{what}: the meter {'was' if METER_VALUE in written else 'was not'} written")
    if expect_write:
        assert _written_word(written, METER_VALUE) == maximum, (
            f"{what}: the meter was set to the SUM rather than to its maximum")


# The last two rows are the SWEEP'S FINDING: every cursor below $8000 answers the same whether the
# extension word is sign-extended or not, so a battery without them passes with `sign_ext16` dropped.
# $fffe reads the word two bytes BELOW the table — which is WB_ACTOR_TYPE30_CURSOR itself — and
# $8000 reaches an address the 24-bit bus puts past the image, where both cores answer zero.
@pytest.mark.parametrize("cursor", [0, 2, 0x10, TYPE30_DRIFT_MASK - 1, TYPE30_DRIFT_MASK,
                                    TYPE30_DRIFT_MASK + 1, 0xff, 0xfffe, 0x8000],
                         ids=lambda v: f"cursor{v:#06x}")
def test_slot30_drifts_by_the_word_its_global_cursor_names(cursor):
    """The table is SIGNED and read through the bus at WB_ACTOR_TYPE30_DRIFT + a sign-extended word,
    with the mask applied only to what is STORED — so a cursor past the table still fetches (out of
    the 256-byte window above it, all inside the image) exactly as slot 52's frame cursor does."""
    what = f"actor_behavior_type30 drift {cursor:#06x}"
    pokes = _collectable_pokes(what, 30, {TYPE30_CURSOR: word(cursor)})
    at = (TYPE30_DRIFT + s16(cursor)) & BUS_ADDR_MASK
    # The seeded cursor is what $4f5a holds when the fetch happens, so a cursor that reads the word
    # BELOW the table reads the cursor itself and the model has to say so rather than read the image.
    if at == TYPE30_CURSOR:
        drift = cursor
    elif at + WORD_BYTES <= harness.IMAGE_SIZE:
        drift = _image_word(at)
    else:
        drift = 0                    # off the loaded image: the shim answers the oracle with zero

    info = _run_handler("actor_behavior_type30", what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == (COLLECT_X + drift) & 0xffff, (
        f"{what}: the record did not move by the table's own word {drift:#06x}")
    assert _written_word(written, TYPE30_CURSOR) \
        == (cursor + TYPE30_DRIFT_STRIDE) & TYPE30_DRIFT_MASK


def test_slot30s_drift_table_is_a_triangle_that_sums_to_zero():
    """What makes the handler a HOVER rather than a drift, read off the image: 32 signed words from
    +8 down to -8 and back, whose sum is zero — so a record returns to the x it spawned at every
    WB_ACTOR_TYPE30_DRIFT_MASK + 1 bytes. Nothing in the port depends on this; it is the evidence
    the plate's reading rests on."""
    words = [s16(_image_word(TYPE30_DRIFT + at))
             for at in range(0, TYPE30_DRIFT_MASK + 1, TYPE30_DRIFT_STRIDE)]
    assert len(words) == 32 and sum(words) == 0, f"the table sums to {sum(words)}"
    assert max(words) == 8 and min(words) == -8


def test_slot30s_cursor_is_a_GLOBAL_two_records_share():
    """The one animation cursor in the tier that is not a record field. Two live type-30 records are
    stepped in turn and the SECOND takes the word the first advanced to — which a per-record cursor
    could not produce, and which is why WB_ACTOR_TYPE30_CURSOR has a `var` of its own."""
    what = "actor_behavior_type30 shared cursor"
    other = _record(TABLE_DEFAULT, ACTOR_SLOT + 1)
    pokes = _collectable_pokes(what, 30, {
        TYPE30_CURSOR: word(0),
        other + ACTOR_TYPE: word(30), other + HALF_WIDTH: word(4), other + SIZE_SECOND: word(8),
        other + ACTOR_X: word(COLLECT_X), other + ACTOR_Y: word(STAND_Y),
        other + ACTOR_FLAGS: bytes([0]), other + FLAGS2: bytes([0]),
        other + FIELD_30: bytes([0]), other + FIELD_12: word(0x1010)})

    first = _run_handler("actor_behavior_type30", what, pokes)
    assert _written_word(program_writes(first), TYPE30_CURSOR) == TYPE30_DRIFT_STRIDE

    # The second record runs on the image the first LEFT, which is what makes the two share a phase:
    # its drift is the table's SECOND word, not its first.
    stepped = leaf.overlay(pokes, {TYPE30_CURSOR: word(TYPE30_DRIFT_STRIDE)})
    glue = _HANDLER_GLUE["actor_behavior_type30"](other)
    info = leaf.run("actor_behavior_type30", glue,
                    _handler_band("actor_behavior_type30"), f"{what}, second record",
                    regs={"a0": other, "_pokes": stepped}, poison=False,
                    max_insns=_handler_cap("actor_behavior_type30"))
    written = program_writes(info)
    assert _written_word(written, other, ACTOR_X) \
        == (COLLECT_X + _image_word(TYPE30_DRIFT + TYPE30_DRIFT_STRIDE)) & 0xffff, (
        f"{what}: the second record started the table from the beginning")


@pytest.mark.parametrize("toggle,rises", [(0x0000, False), (0xffff, True), (0xff00, True),
                                          (0x00ff, False)],
                         ids=lambda v: f"{v:#06x}" if isinstance(v, int) else str(v))
def test_slot30_rises_on_the_frames_the_toggle_byte_is_nonzero(toggle, rises):
    """`tst.b $712.w` reads WB_FRAME_TOGGLE's HIGH byte, so the two rows with only a low byte set
    are what say it is a byte test and not a word one. flip_screen only ever writes $0000/$ffff."""
    what = f"actor_behavior_type30 toggle {toggle:#06x}"
    pokes = _collectable_pokes(what, 30, {FRAME_TOGGLE: word(toggle)})

    info = _run_handler("actor_behavior_type30", what, pokes)
    written = program_writes(info)
    assert (ACTOR + ACTOR_Y in written) is rises, (
        f"{what}: the record {'rose' if ACTOR + ACTOR_Y in written else 'did not rise'}")
    if rises:
        assert _written_word(written, ACTOR, ACTOR_Y) == STAND_Y - 1


@pytest.mark.parametrize("field_12,flickers,frees", [(FLICKER_AT_FIELD_12, True, False),
                                                     (FLICKER_AT_FIELD_12 + 1, False, False),
                                                     # BELOW the mark, and still alive — the row the
                                                     # sweep asked for: a threshold reading flickers
                                                     # here and the equality does not.
                                                     (FLICKER_AT_FIELD_12 - 1, False, False),
                                                     (1, False, True)],
                         ids=lambda v: f"{v}" if isinstance(v, int) else str(v))
def test_slot30_flickers_on_one_countdown_value_and_frees_itself_at_zero(field_12, flickers, frees):
    """`cmpi.w #$14,12(a0)` is an EQUALITY and not a threshold, so a record seeded past the mark
    never flickers at all; `subq.w #1,12(a0) / bne` is what ends it."""
    what = f"actor_behavior_type30 countdown {field_12}"
    pokes = _collectable_pokes(what, 30, {ACTOR + FIELD_12: word(field_12)})

    info = _run_handler("actor_behavior_type30", what, pokes)
    written = program_writes(info)
    up = bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << FLICKER_BIT))
    freed = ACTOR + ACTOR_X in written and _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
    assert up is flickers and freed is frees, f"{what}: flicker={up}, freed={freed}"
    if frees:
        assert _written_word(written, TYPE30_CURSOR) == 0, f"{what}: the global cursor was not reset"


# --- slot 31: the join into actor_select_sprite_by_flag, and the payout ----------------------------
def _sprite_for(flags):
    """actor_select_sprite_by_flag's own rule, restated here as the JOIN's expectation — that
    routine's body has its own cases above, and what these rows pin is that slot 31 reaches it."""
    if flags & (1 << SUPPORTED_BIT):
        return SPRITE_SUPPORTED
    return SPRITE_MOVING if flags & (1 << MOVING_BIT) else SPRITE_IDLE


@pytest.mark.parametrize("flags", [0, 1 << MOVING_BIT, 1 << SUPPORTED_BIT,
                                   (1 << SUPPORTED_BIT) | (1 << MOVING_BIT)],
                         ids=lambda v: f"flags{v:#04x}")
def test_slot31_publishes_a_sprite_through_the_routine_its_last_branch_enters(flags):
    """`bne.w $4fea` is a BRANCH OUT OF THE BODY: the handler's own bytes end at $4fe9 and the sprite
    is published by actor_select_sprite_by_flag, whose `rts` returns to the dispatcher. The expected
    id is taken from the flag byte the frame LEAVES, because actor_fall_and_settle writes it."""
    what = f"actor_behavior_type31 sprite, flags={flags:#04x}"
    pokes = _collectable_pokes(what, 31, {ACTOR + ACTOR_FLAGS: bytes([flags]),
                                          ACTOR + SPEED: bytes([1])})

    info = _run_handler("actor_behavior_type31", what, pokes)
    written = program_writes(info)
    ended = written.get(ACTOR + ACTOR_FLAGS, flags)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _sprite_for(ended), (
        f"{what}: the tail published the wrong id for a flag byte of {ended:#04x}")


def test_slot31_frees_itself_instead_of_publishing_when_its_countdown_expires():
    """The other side of that branch: `subq.w #1,12(a0)` reaching zero falls through to the free
    arm, so the sprite is NOT published on the frame the record ends."""
    what = "actor_behavior_type31 countdown expiring"
    pokes = _collectable_pokes(what, 31, {ACTOR + FIELD_12: word(1),
                                          ACTOR + ACTOR_FLAGS: bytes([1 << FLICKER_BIT])})

    info = _run_handler("actor_behavior_type31", what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << FLICKER_BIT), f"{what}: the flicker stayed up"
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the expiring frame published a sprite"


@pytest.mark.parametrize("field_12,flickers", [
    (FLICKER_AT_FIELD_12, True),
    # STRICTLY BELOW the mark, and still alive so nothing clears the bit again. Without this row
    # slot 31's `cmpi.w` was pinned only through slot 30's copy — a reviewer changed `==` to `<=` in
    # the SHARED helper and exactly one case failed, and it was a slot-30 row. Each handler now
    # states its own.
    (FLICKER_AT_FIELD_12 - 1, False),
    (FLICKER_AT_FIELD_12 + 1, False),
], ids=lambda v: f"{v}" if isinstance(v, int) else str(v))
def test_slot31_starts_flickering_on_one_countdown_value(field_12, flickers):
    """`cmpi.w #$14,12(a0) / bne / bset #6,8(a0)` on a WAITING frame, and an equality rather than a
    threshold — the same claim slot 30's own row makes, in the place slot 31 spells it.

    WHAT THIS DOES NOT PIN, and no case can: slot 31 runs the `cmpi`/`bset` BEFORE its contact test
    where slot 30 runs it after the drift, and that ordering is unobservable. A collected frame ends
    at `bclr #6,8(a0)`, so the flag byte it writes has the bit DOWN whether the `bset` ran first or
    not — the two orders converge on every arm. ../STATUS.md carries it in the not-pinned list."""
    what = f"actor_behavior_type31 flicker mark, countdown {field_12}"
    pokes = _collectable_pokes(what, 31, {ACTOR + FIELD_12: word(field_12)})

    info = _run_handler("actor_behavior_type31", what, pokes)
    written = program_writes(info)
    up = bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << FLICKER_BIT))
    assert up is flickers, (
        f"{what}: the flicker bit is {'up' if up else 'down'} — the mark is an EQUALITY, not a "
        f"threshold")


def test_slot31_pays_the_descriptors_gold_award_when_it_is_collected():
    """The whole cluster from the dispatch row down: contact, WB_ACTOR_REQUEST9_SFX, the draw off a
    DECLARED video counter, both accumulators, the digits inside message 3 and the message posted.
    The award model is the one $517a's own cases compare against, so the two cannot disagree."""
    what = "actor_behavior_type31 payout"
    award, counter = 0x0021, 0x0100
    # The award seeding names the followed record's x too — it is the draw's non-hardware entropy —
    # so it is given the COLLECT point rather than its own, or it would undo the contact.
    pokes = _collectable_pokes(what, 31, _award_pokes(award, followed_x=COLLECT_X,
                                                  counter=counter), collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    expected = _model_award(image)
    band = _collect_band("actor_behavior_type31", image) + merge_bands(expected)

    info = _run_handler("actor_behavior_type31", what, pokes, band=band, hw_seed=VCOUNT_ORDERED)
    written = program_writes(info)
    for addr, value in expected.items():
        assert written[addr] == value, (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the payout model's {value:#04x}")
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER


def test_slot31_skips_the_contact_test_while_it_is_moving_but_still_ages():
    """`btst #0,8(a0) / bne $4fd6` jumps STRAIGHT to the countdown — so a moving record cannot be
    collected and does not stop ageing either, which is what separates this gate from slot 28's
    (that one sends a moving record to the whole waiting arm instead)."""
    what = "actor_behavior_type31 moving"
    pokes = _collectable_pokes(what, 31, {ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                          ACTOR + SPEED: bytes([3]),
                                          ACTOR + FIELD_12: word(0x0500)}, collected=True)
    _assert_contact(harness.make_image(pokes), what, True)

    info = _run_handler("actor_behavior_type31", what, pokes)
    written = program_writes(info)
    assert BCD_COUNTER not in written, f"{what}: a moving record was collected"
    assert _written_word(written, ACTOR, FIELD_12) == 0x04ff, f"{what}: it did not age"


# --- batch 34: slots 32..37, and what CLOSES the $4e38..$5407 band --------------------------------
# The two new COLLECTABLES are already inside `COLLECT_SLOTS` above, so the shared contact rows cover
# them; what follows is each row's own arms. Slots 34..37 are not collectables at all and get their
# own seeds.
TYPE32 = "actor_behavior_type32"
TYPE33 = "actor_behavior_type33"
TYPE34 = "actor_behavior_type34"
TYPE35 = "actor_behavior_type35"
TYPE36 = "actor_behavior_type36"
TYPE37 = "actor_behavior_type37"

# Slot 32's hop machine, shut: the second latch UP means no landing relaunches anything, which is
# what leaves the walk and the animation as the only things a case is driving.
HOPS_SPENT = {TYPE32_HOPS_SPENT: bytes([TYPE32_LATCH_SET])}


def _type32_pokes(what, fields=None, collected=False, ground=True):
    return _collectable_pokes(what, 32, fields, collected=collected, ground=ground)


def test_slot32_pays_the_descriptors_gold_award_when_it_is_collected():
    """The same cluster slot 31 pays through, from a second table row: contact, the sound, the draw
    off a DECLARED video counter, both accumulators, the digits and the message. The award model is
    $517a's own, so the two rows cannot disagree about what a payout is."""
    what = "actor_behavior_type32 payout"
    pokes = _type32_pokes(what, _award_pokes(0x0021, followed_x=COLLECT_X, counter=0x0100),
                          collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    expected = _model_award(image)

    info = _run_handler(TYPE32, what, pokes,
                        band=_collect_band(TYPE32, image) + merge_bands(expected),
                        hw_seed=VCOUNT_ORDERED)
    written = program_writes(info)
    for addr, value in expected.items():
        assert written[addr] == value, (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the payout model's {value:#04x}")
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER


@pytest.mark.parametrize("walking,moving,collects", [
    (0, 0, True),                 # never landed and standing still: the ordinary collect
    (0, 1, False),                # ...and the ONE combination that skips the test
    (TYPE32_LATCH_SET, 0, True),
    (TYPE32_LATCH_SET, 1, True),  # once it has landed, even a hopping record is collectable
], ids=["fresh-still", "fresh-hopping", "landed-still", "landed-hopping"])
def test_slot32s_contact_test_runs_unless_it_has_NEVER_landed_and_is_moving(walking, moving,
                                                                           collects):
    """`tst.b $515c.l / bne` jumps STRAIGHT to the contact test, so the moving gate slots 28 and 31
    have is only half of this one: it applies while WB_ACTOR_TYPE32_WALKING is still down and stops
    applying for ever afterwards. All four combinations are driven, and the three that collect are
    what separates this from a plain `btst #0,8(a0)` port."""
    what = f"actor_behavior_type32 gate walking={walking:#04x} moving={moving}"
    pokes = _type32_pokes(what, leaf.overlay(
        {TYPE32_WALKING: bytes([walking]), ACTOR + ACTOR_FLAGS: bytes([moving << MOVING_BIT]),
         ACTOR + SPEED: bytes([3])}, HOPS_SPENT), collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    # `_collect_band` already folds the payout in for a PAYING_HANDLERS row, so nothing is added.
    info = _run_handler(TYPE32, what, pokes, band=_collect_band(TYPE32, image),
                        hw_seed=VCOUNT_ORDERED)
    written = program_writes(info)
    paid = BCD_COUNTER in written
    assert paid is collects, (
        f"{what}: the record {'paid' if paid else 'did not pay'}, which is the other arm")


# (WB_ACTOR_FIELD_10 on entry, the speed the landing launches at). A counter of ONE spends the last
# hop and launches NOTHING, which is what makes the hops shorten and then stop.
TYPE32_HOP_CASES = ((4, 3), (2, 1), (1, None))


@pytest.mark.parametrize("field_10,speed", TYPE32_HOP_CASES, ids=lambda v: f"{v}")
def test_slot32_relaunches_a_hop_on_every_landing_until_its_counter_runs_out(field_10, speed):
    """The machine, and the two things it does on every landing whatever the count: it raises
    WB_ACTOR_TYPE32_WALKING and it spends one of WB_ACTOR_FIELD_10. Only a NONZERO remainder
    launches, and the speed it launches at is that remainder — so the hops get shorter by one each
    time and the last one is skipped."""
    what = f"actor_behavior_type32 landing with {field_10} hops left"
    pokes = _type32_pokes(what, {ACTOR + FIELD_10: bytes([field_10]),
                                 ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                 ACTOR + SPEED: bytes([0])})

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    assert written[TYPE32_WALKING] == TYPE32_LATCH_SET, f"{what}: the walk gate stayed down"
    assert written[ACTOR + FIELD_10] == field_10 - 1, f"{what}: the counter did not step"
    # WB_ACTOR_SPEED is written on EVERY frame — the settle spends it as the fall step — so what
    # says the launch happened is the flag byte, and the speed is only checked where it is the
    # counter's own value.
    launched = bool(written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT))
    assert launched is (speed is not None), f"{what}: it {'did' if launched else 'did not'} launch"
    if speed is None:
        assert written[TYPE32_HOPS_SPENT] == TYPE32_LATCH_SET, f"{what}: the machine did not stop"
        return
    assert TYPE32_HOPS_SPENT not in written, f"{what}: the machine stopped early"
    assert written[ACTOR + SPEED] == speed, (
        f"{what}: it launched at {written[ACTOR + SPEED]}, not the counter's own {speed}")
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)


@pytest.mark.parametrize("flags,spent,steps", [
    (1 << SUPPORTED_BIT, TYPE32_LATCH_SET, False),   # the machine is over
    (0, 0, False),                                   # ...and a record in the air never lands
    (1 << SUPPORTED_BIT, 0, True),
], ids=["hops-spent", "airborne", "lands"])
def test_slot32s_hop_machine_needs_a_landing_and_an_unspent_counter(flags, spent, steps):
    """Both gates, driven either way. The airborne row is the control that says the SUPPORTED test
    is read at all — a port that ran the machine every frame would spend the counter here."""
    what = f"actor_behavior_type32 hop gate flags={flags:#04x} spent={spent:#04x}"
    pokes = _type32_pokes(what, {ACTOR + FIELD_10: bytes([4]), TYPE32_HOPS_SPENT: bytes([spent]),
                                 ACTOR + ACTOR_FLAGS: bytes([flags])},
                          ground=flags != 0)

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    stepped = written.get(ACTOR + FIELD_10) == 3
    assert stepped is steps, f"{what}: the counter {'stepped' if stepped else 'held'}"


@pytest.mark.parametrize("walking,side,delta", [
    (0, 0, 0),
    (TYPE32_LATCH_SET, 0, TYPE32_WALK_STEP),
    (TYPE32_LATCH_SET, 1 << SIDE_BIT, -TYPE32_WALK_STEP),
], ids=["latch-down", "right", "left"])
def test_slot32_walks_one_pixel_only_once_its_latch_is_up(walking, side, delta):
    """`tst.b $515c.l / beq` gates the whole step, and WB_ACTOR_FLAG_SIDE_BIT picks the probe —
    actor_step_facing's own two arms, spelt inline. The latch-down row is what says a fresh record
    stands still until it has landed once."""
    what = f"actor_behavior_type32 walk walking={walking:#04x} side={side:#04x}"
    pokes = _type32_pokes(what, leaf.overlay(
        {TYPE32_WALKING: bytes([walking]), ACTOR + ACTOR_FLAGS: bytes([side | 1 << SUPPORTED_BIT])},
        HOPS_SPENT))

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    moved = _written_word(written, ACTOR, ACTOR_X) if ACTOR + ACTOR_X in written else COLLECT_X
    assert moved == (COLLECT_X + delta) & 0xffff, (
        f"{what}: the record is at {moved:#06x}, not the {(COLLECT_X + delta) & 0xffff:#06x} this "
        f"arm walks to")


def test_slot32_turns_round_when_its_step_is_blocked():
    """`tst.b d0 / bne / bchg #3,8(a0)` — the BYTE test every other walk in the tier uses, and NOT
    slot 28's `tst.w`: the two sit sixty bytes apart in the same band and disagree."""
    what = "actor_behavior_type32 blocked walk"
    pokes = _block_the_walk(_type32_pokes(what, leaf.overlay(
        {TYPE32_WALKING: bytes([TYPE32_LATCH_SET]),
         ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}, HOPS_SPENT)))

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: a blocked step did not turn the record round")


def test_slot32_TURNS_ROUND_on_a_clamped_step_where_slot_28_does_not():
    """THE SWEEP'S FINDING, and the case that separates the two blocked-step tests in this band.

    Slot 28's `tst.w d0` and slot 32's `tst.b d0` sit sixty bytes apart and answer differently on
    exactly one input: a step the RIGHT-EDGE CLAMP refused, which comes back with the clamp limit in
    the byte above the outcome ($0100 for the limit seeded here). The byte says BLOCKED and the word
    does not — so slot 32 turns its record round on the level's edge and slot 28, on the identical
    seed, does not (`test_slot28_does_NOT_turn_round_when_the_probes_high_byte_is_set`).

    Without this row `walk/type32-word-step-test` SURVIVES: every other blocked step these cases
    drive lands in map column 0, where the whole low word is zero and the two tests agree."""
    what = "actor_behavior_type32 clamped at the level edge"
    pokes = _type32_pokes(what, leaf.overlay(
        {TYPE32_WALKING: bytes([TYPE32_LATCH_SET]), SCROLL_LIMIT_X: word(TIGHT_LIMIT),
         ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}, HOPS_SPENT))
    clamped = TIGHT_LIMIT + wb("BG_SCROLL_LIMIT_BIAS") - 4
    assert clamped >> 8, "the seeded limit does not put anything in the probe's high byte"
    assert clamped & 0xff == 0, "the clamp's low byte is not the one the outcome overwrites"

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side bit did NOT flip — the test read the whole low WORD, which is slot 28's "
        f"reading and not this one's")
    assert _written_word(written, ACTOR, ACTOR_X) == clamped, (
        f"{what}: the record was not parked on the level's edge, so the clamp never fired")


def test_slot32s_latches_are_GLOBALS_two_records_share():
    """The tier's second WB_ACTOR_TYPE30_CURSOR, and over three bytes rather than one word. Record A
    lands and raises the walk gate; record B is airborne and has never landed, and it walks anyway —
    which a per-record latch could not produce."""
    what = "actor_behavior_type32 shared latches"
    other = _record(TABLE_DEFAULT, ACTOR_SLOT + 1)
    other_x = COLLECT_X + 0x40
    pokes = _type32_pokes(what, {
        ACTOR + FIELD_10: bytes([4]), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        other + ACTOR_TYPE: word(32), other + HALF_WIDTH: word(4), other + SIZE_SECOND: word(8),
        other + ACTOR_X: word(other_x), other + ACTOR_Y: word(STAND_Y),
        other + ACTOR_FLAGS: bytes([0]), other + FLAGS2: bytes([0]),
        other + SPEED: bytes([0]), other + FIELD_10: bytes([4]),
        other + FIELD_12: word(COLLECT_FIELD_12_IDLE), other + FIELD_18: bytes([0])})

    first = _run_handler(TYPE32, what, pokes)
    # THREADED for the event rows' reason: the latch the second runs see is the BYTE the first run
    # left, taken from its ledger. (A hand-stated $ff would be the same number by construction and
    # would make the "saw the first one's latch" comment describe something the case never did.)
    raised = program_writes(first)[TYPE32_WALKING]
    assert raised == TYPE32_LATCH_SET

    # The second record runs on the image the FIRST left, so the latch it reads is the one A raised
    # — and it is AIRBORNE, so nothing in its own frame could have raised one.
    # BOTH SECOND-RECORD RUNS SHUT THE HOP MACHINE, and that is the whole rigour of the case: the
    # walk gate is RE-READ after the machine may have raised it ($50be `tst.b $515c` sits below
    # $508c's `st`), so a record that lands raises the latch ITSELF and would walk whatever the
    # first record did. With WB_ACTOR_TYPE32_HOPS_SPENT up the machine returns before the `st`, so
    # the only thing that can put the latch up is the run before this one. (The first attempt at
    # this case omitted it and proved nothing; the negative control below is what caught that.)
    def _second_run(label, latch):
        seeded = leaf.overlay(pokes, {TYPE32_WALKING: bytes([latch]),
                                      TYPE32_HOPS_SPENT: bytes([TYPE32_LATCH_SET])})
        assert latch in (0, raised), "the latch seeded here is neither down nor the one A raised"
        run = leaf.run(TYPE32, _HANDLER_GLUE[TYPE32](other), _handler_band(TYPE32),
                       f"{what}, {label}", regs={"a0": other, "_pokes": seeded},
                       poison=False, max_insns=_handler_cap(TYPE32))
        assert run["ret"] == DISPATCH_RAN, f"{what}: the {label} record reported a boundary"
        return program_writes(run)

    walked = _second_run("second record", raised)
    assert _written_word(walked, other, ACTOR_X) == other_x + TYPE32_WALK_STEP, (
        f"{what}: the second record did not walk, so it did not see the first one's latch")

    # THE NEGATIVE CONTROL. Without it the GLOBAL claim is pinned only on the write side: the tier's
    # seeding fills every record with keyed NONZERO bytes, so a port reading a per-RECORD latch byte
    # would find one and walk anyway. With the global down the same record must stand still.
    assert other + ACTOR_X not in _second_run("latch down", 0), (
        f"{what}: the record walked with the GLOBAL latch down, so the gate is a record field")


# Every byte offset the cursor can hold, plus the two the sweep asked for: the LAST frame, whose
# look-ahead reads the $ffff and zeroes the cursor, and one past the table, which shows the fetch is
# not bounded where the store is.
TYPE32_CURSOR_CASES = (0, 2, 0x14, 0x16, 0x18, 0xfffe)


@pytest.mark.parametrize("cursor", TYPE32_CURSOR_CASES, ids=lambda v: f"cursor{v:#06x}")
def test_slot32_publishes_the_frame_its_global_cursor_names_and_looks_ONE_WORD_AHEAD(cursor):
    """THE PLATE CORRECTION, as a case. The frame published is the word AT the cursor and the
    terminator is read at cursor + 2, so the $ffff is never itself drawn — the same look-ahead
    `actor_relaunch_and_anim_5160` has, which the next case drives from the other side.

    The frames come out of the IMAGE, and the cursor is sign-extended into the fetch and masked
    nowhere, so the $fffe row reads the two bytes below the table (WB_ACTOR_TYPE32_CURSOR itself).

    WHAT THE $fffe ROW DOES NOT PIN: its stepped cursor is 0 because the 16-bit add itself wraps to
    0, not because the look-ahead terminated — so that row pins the FETCH's sign extension and says
    nothing about the wrap. The rows that pin the wrap are the ones at and beside the terminator
    ($14/$16/$18), where the add lands somewhere other than 0."""
    what = f"actor_behavior_type32 frame {cursor:#06x}"
    pokes = _type32_pokes(what, leaf.overlay({TYPE32_CURSOR: word(cursor)}, HOPS_SPENT))
    at = (ANIM_5160_FRAMES + s16(cursor)) & BUS_ADDR_MASK
    frame = cursor if at == TYPE32_CURSOR else _image_word(at)
    ahead = (ANIM_5160_FRAMES + s16(cursor) + ANIM_FRAME_BYTES) & BUS_ADDR_MASK
    wraps = (cursor if ahead == TYPE32_CURSOR else _image_word(ahead)) == ANIM_5160_END

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == frame, (
        f"{what}: the record published {_written_word(written, ACTOR, ACTOR_SPRITE):#06x}, not the "
        f"table's own {frame:#06x}")
    stepped = 0 if wraps else (cursor + ANIM_FRAME_BYTES) & 0xffff
    assert _written_word(written, TYPE32_CURSOR) == stepped


def test_two_of_the_three_readers_of_the_5160_table_wrap_on_the_SAME_cursor():
    """The correction ../names.txt carried the other way round, driven against the ORACLE from both
    sides. $6872 publishes with `move.w (a1)+,6(a0)` and then tests `(a1)`; slot 32 publishes with
    `move.w (a1),6(a0)` and tests `2(a1)`. Those are the same address, so the two readers must zero
    their cursors on the same value — and the row below it must zero neither.

    TWO OF THREE, and the name says so. The table has a THIRD reader — `$58f8`, inside the unported
    `actor_behavior_type46` — which is $6872's shape again over the same record byte. Nothing here
    drives it, so this case is a two-of-three pin until slot 46 is ported; the `var` plate in
    ../names.txt carries the whole census."""
    terminator = min(at for at in range(0, 0x100, ANIM_FRAME_BYTES)
                     if _image_word(ANIM_5160_FRAMES + at) == ANIM_5160_END)
    last = terminator - ANIM_FRAME_BYTES
    for cursor, wraps in ((last, True), (last - ANIM_FRAME_BYTES, False)):
        what = f"the two 5160 readers at cursor {cursor}"
        pokes = _type32_pokes(what, leaf.overlay({TYPE32_CURSOR: word(cursor)}, HOPS_SPENT))
        slot32 = _run_handler(TYPE32, what, pokes)
        assert (_written_word(program_writes(slot32), TYPE32_CURSOR) == 0) is wraps

        relaunch_pokes = _type32_pokes(what + " relaunch", {ACTOR + FIELD_18: bytes([cursor]),
                                                            ACTOR + ACTOR_FLAGS: bytes([0])})
        info = leaf.run(RELAUNCH_5160, _ANIM_5160(ACTOR), HANDLER_WRITE_BAND, what + " relaunch",
                        regs={"a0": ACTOR, "_pokes": relaunch_pokes}, poison=False,
                        max_insns=_cap(RELAUNCH_5160))
        assert (program_writes(info)[ACTOR + FIELD_18] == 0) is wraps, (
            f"{what}: the two readers disagree about the terminator, which is the reading the plate "
            f"correction rests on")


@pytest.mark.parametrize("field_12,flickers,frees", [
    (FLICKER_AT_FIELD_12, True, False),
    (FLICKER_AT_FIELD_12 + 1, False, False),
    (1, False, True),
], ids=["at-the-mark", "past-the-mark", "expired"])
def test_slot32_flickers_on_one_countdown_value_and_frees_itself_at_zero(field_12, flickers, frees):
    """The WORD countdown slots 30, 31 and 33 share, in the place slot 32 spells it — and the free
    arm that clears BOTH LATCHES, which is what makes the next type-32 record start its hop machine
    from the beginning.

    AND NOT THE CURSOR. Slot 30's free arm `clr.w`s its global cursor between the `bclr` and the
    free marker; this one clears the two latch bytes and leaves WB_ACTOR_TYPE32_CURSOR standing, so
    the next type-32 record picks the animation up where the last one left it. The two handlers are
    a hundred bytes apart and disagree, which is what the last assertion here pins."""
    what = f"actor_behavior_type32 countdown {field_12}"
    cursor = ANIM_FRAME_BYTES
    pokes = _type32_pokes(what, leaf.overlay(
        {ACTOR + FIELD_12: word(field_12), TYPE32_WALKING: bytes([TYPE32_LATCH_SET]),
         TYPE32_CURSOR: word(cursor)}, HOPS_SPENT))

    info = _run_handler(TYPE32, what, pokes)
    written = program_writes(info)
    assert bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << FLICKER_BIT)) is flickers
    freed = _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
    assert freed is frees, f"{what}: the record {'was' if freed else 'was not'} freed"
    if not frees:
        assert _written_word(written, TYPE32_CURSOR) == cursor + ANIM_FRAME_BYTES
        return
    assert written[TYPE32_WALKING] == 0 and written[TYPE32_HOPS_SPENT] == 0
    assert TYPE32_CURSOR not in written, f"{what}: the free arm cleared the cursor as well"


# --- slot 33 ($5208): the panel's clock ------------------------------------------------------------
# (score on entry). The second seed's lowest digit pair wraps under WB_ACTOR_COLLECT_SCORE, which is
# what says the accumulator is a packed-BCD one and not a binary add.
TYPE33_SCORE_CASES = (0x00001000, 0x00009985)


@pytest.mark.parametrize("score", TYPE33_SCORE_CASES, ids=lambda v: f"{v:#010x}")
def test_slot33_winds_the_panel_clock_back_and_scores(score):
    """The two panel words go up TOGETHER, one instruction apart — the rewind that climbs
    WB_PANEL_FRAME_DELAY and the hold that stops it being spent while it climbs. Nothing else in
    this tier writes either, which is why they are this row's whole payout beside the score.

    THE SCORE'S ENTRY X is the sound trigger's and is not readable off these bytes; it is pinned
    here, because $20 added to any seed differs in its lowest digit between a folded-in 0 and 1."""
    what = f"actor_behavior_type33 collected score={score:#010x}"
    pokes = _collectable_pokes(what, 33, {BCD_SCORE: longword(score)}, collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)

    info = _run_handler(TYPE33, what, pokes, band=_collect_band(TYPE33, image))
    written = program_writes(info)
    assert _written_word(written, PANEL_FRAME_REWIND) == PANEL_FRAME_REWIND_SET
    assert _written_word(written, PANEL_FRAME_HOLD) == PANEL_FRAME_HOLD_SET
    assert leaf.read_int(info, BCD_SCORE, BCD_SCORE_LEN, what) \
        == bcd_expected(score, COLLECT_SCORE, BCD_SCORE_LEN, False,
                        TYPE33_SCORE_ENTRY_EXTEND).value


# The entry X the row above pins. It is a claim about the sound trigger, not about these bytes.
TYPE33_SCORE_ENTRY_EXTEND = 0


def test_exactly_one_slot33_score_row_carries_out_of_its_lowest_digit_pair():
    """The premise `TYPE33_SCORE_CASES` rests on, computed off the seeds: without a row whose low
    byte wraps, `abcd` and a binary `add.b` answer alike and the rows pin only the address."""
    carrying = [score for score in TYPE33_SCORE_CASES
                if (score & 0xff) + COLLECT_SCORE > 0x99]
    assert carrying == [TYPE33_SCORE_CASES[1]], (
        f"{[hex(s) for s in carrying]} are the seeds whose lowest digit pair wraps — the rows above "
        f"need exactly one")


def test_slot33_is_collected_EVEN_WHILE_IT_IS_MOVING():
    """WHAT SEPARATES IT FROM THE OTHER FOUR. Slots 28, 31 and 32 all refuse a record with
    WB_ACTOR_FLAG_MOVING_BIT up; this row has no `btst #0,8(a0)` anywhere in it, so a clock picked
    up mid-hop is taken. The same seed that sends slot 31 to its ageing arm pays out here."""
    what = "actor_behavior_type33 collected mid-hop"
    pokes = _collectable_pokes(what, 33, {ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                          ACTOR + SPEED: bytes([3])}, collected=True)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)

    info = _run_handler(TYPE33, what, pokes, band=_collect_band(TYPE33, image))
    written = program_writes(info)
    assert _written_word(written, PANEL_FRAME_REWIND) == PANEL_FRAME_REWIND_SET, (
        f"{what}: a moving record was refused, which is slot 31's gate and not this row's")
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER


@pytest.mark.parametrize("field_12,flickers,frees", [
    (FLICKER_AT_FIELD_12, True, False),
    (FLICKER_AT_FIELD_12 + 1, False, False),
    (1, False, True),
], ids=["at-the-mark", "past-the-mark", "expired"])
def test_slot33_flickers_on_one_countdown_value_and_frees_itself_at_zero(field_12, flickers, frees):
    """Slots 30, 31 and 33 spell the same six instructions; this is the third site, and the free
    tail here is the one the COLLECT arm reaches by a `bra.w` rather than by falling into."""
    what = f"actor_behavior_type33 countdown {field_12}"
    pokes = _collectable_pokes(what, 33, {ACTOR + FIELD_12: word(field_12)})

    info = _run_handler(TYPE33, what, pokes)
    written = program_writes(info)
    assert bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << FLICKER_BIT)) is flickers
    freed = ACTOR + ACTOR_X in written and _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER
    assert freed is frees, f"{what}: the record {'was' if freed else 'was not'} freed"


# --- slot 34 ($525a): the shop's item cursor -------------------------------------------------------
# NOT A CREATURE. What this record's WB_ACTOR_X holds is a menu selection, and the handler's whole
# job is to walk it between three values on the joystick's EDGES and to publish what the player
# asked for. It reads no map, takes no contact test and never frees its slot.

# Where a case parks the shop record. It is 70 bytes and lies past the program in the real game, so
# a case has to place one somewhere it can seed — clear of the scene descriptor the payout cases use.
SHOP_RECORD_AT = 0x31000

# The two ids a case seeds into the record's cursor-message words. Each is a WORD in the record and
# a BYTE in WB_TEXT_REQUEST, and the two differ ABOVE the low byte, which is what says the store is
# `move.b d0` and not `move.w`.
SHOP_ITEM1_MSG_SEED = 0x1141
SHOP_ITEM2_MSG_SEED = 0x2242


def _type34_pokes(what, x, joystick, pending=0, ack=0, fields=None):
    """A slot-34 record at the menu position `x`, with the two gate words, the joystick edge byte
    and the shop record all stated. `joystick` is the edge SET, so the pipeline is seeded with a
    clear previous frame and this frame's bits."""
    base = {ACTOR + ACTOR_TYPE: word(34), ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(0),
            SCENE_MESSAGE_PENDING: word(pending), SCENE_ACK_WAIT: word(ack),
            JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([joystick]),
            SHOP_RECORD_PTR: longword(SHOP_RECORD_AT),
            SHOP_RECORD_AT + SHOP_ITEM1_CURSOR_MSG: word(SHOP_ITEM1_MSG_SEED),
            SHOP_RECORD_AT + SHOP_ITEM2_CURSOR_MSG: word(SHOP_ITEM2_MSG_SEED),
            TEXT_REQUEST: bytes([0]), TEXT_LIFETIME_REQUEST: word(0), SHOP_REQUEST: word(0)}
    return _tier_pokes(case_salt(what), leaf.overlay(base, fields or {}))


@pytest.mark.parametrize("pending,ack", [(SCENE_MESSAGE_PENDING_SET, 0),
                                         (0, SCENE_MESSAGE_PENDING_SET)],
                         ids=["message-pending", "ack-wait"])
def test_slot34_writes_nothing_while_the_driver_is_talking(pending, ack):
    """Both gates, one row each, and with the joystick held HARD LEFT so a port that read it first
    would move the cursor. The two `tst.w`s come before `bsr $682` in the original, which is what
    stops a held direction walking the menu under an open box."""
    what = f"actor_behavior_type34 pending={pending:#06x} ack={ack:#06x}"
    pokes = _type34_pokes(what, TYPE34_MIDDLE_X, joystick=1 << JOY1_LEFT_BIT,
                          pending=pending, ack=ack)

    info = _run_handler(TYPE34, what, pokes)
    assert not program_writes(info), f"{what}: the handler wrote memory while the driver was busy"


# (edge bit, x on entry) -> (x, y, the message id posted). A `None` message is the MIDDLE, which
# posts WB_TEXT_REQUEST_DISMISS and no lifetime at all.
TYPE34_WALK_CASES = (
    (JOY1_LEFT_BIT, TYPE34_ITEM2_X, TYPE34_MIDDLE_X, TYPE34_MIDDLE_Y, None),
    (JOY1_LEFT_BIT, TYPE34_MIDDLE_X, TYPE34_ITEM1_X, TYPE34_ITEM_Y, SHOP_ITEM1_MSG_SEED),
    (JOY1_RIGHT_BIT, TYPE34_ITEM1_X, TYPE34_MIDDLE_X, TYPE34_MIDDLE_Y, None),
    (JOY1_RIGHT_BIT, TYPE34_MIDDLE_X, TYPE34_ITEM2_X, TYPE34_ITEM_Y, SHOP_ITEM2_MSG_SEED),
)


@pytest.mark.parametrize("bit,start,end,end_y,message", TYPE34_WALK_CASES,
                         ids=["left-from-item2", "left-from-middle",
                              "right-from-item1", "right-from-middle"])
def test_slot34_walks_its_cursor_between_the_three_items(bit, start, end, end_y, message):
    """The four moves the menu has, and each plants its x AND its y as one longword — so the middle
    really does sit WB_ACTOR_TYPE34_ITEM_Y minus WB_ACTOR_TYPE34_MIDDLE_Y pixels above the ends.
    Arriving on an END also posts that item's own message id out of the shop record, taken as a
    WORD and stored as a BYTE; arriving on the middle posts the DISMISS and no lifetime."""
    what = f"actor_behavior_type34 bit {bit} from {start:#04x}"
    pokes = _type34_pokes(what, start, joystick=1 << bit)

    info = _run_handler(TYPE34, what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == end, f"{what}: the cursor went elsewhere"
    assert _written_word(written, ACTOR, ACTOR_Y) == end_y, f"{what}: the y did not travel with it"
    if message is None:
        assert written[TEXT_REQUEST] == TEXT_REQUEST_DISMISS
        assert TEXT_LIFETIME_REQUEST not in written, (
            f"{what}: the middle posted a lifetime, which only the two item arms do")
        return
    assert written[TEXT_REQUEST] == message & 0xff, (
        f"{what}: the id posted is {written[TEXT_REQUEST]:#04x} — the record's word is "
        f"{message:#06x} and only its LOW BYTE reaches the request")
    assert _written_word(written, TEXT_LIFETIME_REQUEST) == TEXT_LIFETIME_DEFAULT


@pytest.mark.parametrize("bit", [JOY1_LEFT_BIT, JOY1_RIGHT_BIT], ids=["left", "right"])
def test_slot34_ignores_a_direction_it_has_nowhere_to_take(bit):
    """The two ends of the walk: LEFT from the left item and RIGHT from the right one fall through
    both `cmpi.w`s to a bare `rts`, so the menu does not wrap round."""
    start = TYPE34_ITEM1_X if bit == JOY1_LEFT_BIT else TYPE34_ITEM2_X
    what = f"actor_behavior_type34 bit {bit} at the end of the walk"
    pokes = _type34_pokes(what, start, joystick=1 << bit)

    info = _run_handler(TYPE34, what, pokes)
    assert not program_writes(info), f"{what}: the cursor moved off the end of the menu"


@pytest.mark.parametrize("x,asked", [
    (TYPE34_ITEM1_X, SHOP_REQUEST_ITEM1),
    (TYPE34_MIDDLE_X, SHOP_REQUEST_FAREWELL),
    (TYPE34_ITEM2_X, SHOP_REQUEST_ITEM2),
    (0x0000, None),
], ids=["item1", "middle", "item2", "nowhere"])
def test_slot34_asks_for_whatever_the_cursor_is_pointing_at(x, asked):
    """AND THE MAPPING IS NOT THE POSITIONAL ORDER: the two ends buy items 1 and 2 and the MIDDLE is
    WB_SHOP_REQUEST_FAREWELL, so the request word runs 1, 3, 2 across the screen. The last row is
    the control — a cursor at none of the three writes nothing at all."""
    what = f"actor_behavior_type34 fire at {x:#06x}"
    pokes = _type34_pokes(what, x, joystick=1 << JOY1_FIRE_BIT)

    info = _run_handler(TYPE34, what, pokes)
    written = program_writes(info)
    if asked is None:
        assert not written, f"{what}: an unknown position asked the shop for something"
        return
    assert _written_word(written, SHOP_REQUEST) == asked, (
        f"{what}: the shop was asked for {_written_word(written, SHOP_REQUEST)}, not {asked}")
    assert ACTOR + ACTOR_X not in written, f"{what}: fire moved the cursor"


def test_slot34_reads_its_three_edge_bits_in_order_and_takes_the_first():
    """`btst #2 / bne / btst #3 / bne / btst #7 / bne` — each arm ends in its own `rts`, so a frame
    with every edge set takes the LEFT one alone and neither moves twice nor fires."""
    what = "actor_behavior_type34 every edge at once"
    edges = (1 << JOY1_LEFT_BIT) | (1 << JOY1_RIGHT_BIT) | (1 << JOY1_FIRE_BIT)
    pokes = _type34_pokes(what, TYPE34_MIDDLE_X, joystick=edges)

    info = _run_handler(TYPE34, what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == TYPE34_ITEM1_X, f"{what}: LEFT did not win"
    assert SHOP_REQUEST not in written, f"{what}: the fire arm ran as well"


def test_the_two_names_for_the_joysticks_fire_bit_are_one_bit():
    """WB_JOY1_FIRE_BIT and WB_ACTOR_TYPE61_FIRE_BIT are the same bit under two names, because the
    two ORIGINALS read it differently — slot 61 as a SIGN (`tst.b d0 / bpl`) and slot 34 as a
    `btst #7`. layout.py scrapes plain integer literals only, so neither #define can derive from the
    other; pinning them equal here is the substitute this project already uses for that
    (test_effects.py's two-headers slot-byte case). If one ever moves, this fails instead of the two
    handlers quietly disagreeing about which bit fire is."""
    assert JOY1_FIRE_BIT == wb("ACTOR_TYPE61_FIRE_BIT")


def test_slot34_reads_the_joystick_EDGE_and_not_the_held_byte():
    """`joy1_newly_pressed` is `current & ~previous`, so a direction HELD from last frame moves
    nothing — which is what stops the cursor sliding along the menu while the stick is over."""
    what = "actor_behavior_type34 held direction"
    pokes = _type34_pokes(what, TYPE34_MIDDLE_X, joystick=1 << JOY1_LEFT_BIT,
                          fields={JOY1_PREV: bytes([1 << JOY1_LEFT_BIT])})

    info = _run_handler(TYPE34, what, pokes)
    assert not program_writes(info), f"{what}: a held direction walked the cursor"


# --- slots 35 and 36 ($5336, $53bc): one animation, one GLOBAL cursor, two rows -------------------
EVENT_ROWS = {TYPE35: (35, EVENT_ANIM_DONE_B12), TYPE36: (36, EVENT_ANIM_DONE_B16)}
EVENT_FRAME_COUNT = (EVENT_ANIM_MASK + 1) // 2


def _event_pokes(what, name, cursor, fields=None):
    slot, _flag = EVENT_ROWS[name]
    base = {ACTOR + ACTOR_TYPE: word(slot), ACTOR + ACTOR_SPRITE: word(0),
            EVENT_ANIM_CURSOR: word(cursor),
            EVENT_ANIM_DONE_B12: word(0), EVENT_ANIM_DONE_B16: word(0)}
    return _tier_pokes(case_salt(what), leaf.overlay(base, fields or {}))


@pytest.mark.parametrize("name", sorted(EVENT_ROWS), ids=sorted(EVENT_ROWS))
@pytest.mark.parametrize("cursor", [0, 2, EVENT_ANIM_MASK - 1, 0xfffe, 0x8000],
                         ids=lambda v: f"cursor{v:#06x}")
def test_the_event_animation_publishes_the_frame_its_shared_cursor_names(name, cursor):
    """One word of WB_ACTOR_EVENT_ANIM_FRAMES a frame, off a cursor that is a BYTE OFFSET. The mask
    is applied to what is STORED and not to the fetch, so the last two rows reach outside the table
    — $fffe reads the cursor word itself, two bytes below the table, and $8000 leaves the image,
    where both cores answer zero."""
    what = f"{name} frame {cursor:#06x}"
    pokes = _event_pokes(what, name, cursor)
    at = (EVENT_ANIM_FRAMES + s16(cursor)) & BUS_ADDR_MASK
    if at == EVENT_ANIM_CURSOR:
        frame = cursor
    elif at + WORD_BYTES <= harness.IMAGE_SIZE:
        frame = _image_word(at)
    else:
        frame = 0

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == frame, (
        f"{what}: it published {_written_word(written, ACTOR, ACTOR_SPRITE):#06x}, not the table's "
        f"own {frame:#06x}")
    assert _written_word(written, EVENT_ANIM_CURSOR) \
        == (cursor + ANIM_FRAME_BYTES) & EVENT_ANIM_MASK


@pytest.mark.parametrize("name", sorted(EVENT_ROWS), ids=sorted(EVENT_ROWS))
def test_the_event_animation_raises_ITS_OWN_flag_when_the_cursor_wraps(name):
    """The one thing the two rows do not share. Both wrap on the same cursor and each raises a
    DIFFERENT word — which is what makes them the two halves of `player_pending_event_gate` — and
    only slot 36 also `clr.w`s its own WB_ACTOR_TYPE, retyping the record into the bare `rts`."""
    slot, flag = EVENT_ROWS[name]
    other = EVENT_ANIM_DONE_B16 if flag == EVENT_ANIM_DONE_B12 else EVENT_ANIM_DONE_B12
    what = f"{name} cursor wrap"
    pokes = _event_pokes(what, name, EVENT_ANIM_MASK + 1 - ANIM_FRAME_BYTES)

    info = _run_handler(name, what, pokes)
    written = program_writes(info)
    assert _written_word(written, EVENT_ANIM_CURSOR) == 0, f"{what}: the cursor did not wrap"
    assert _written_word(written, flag) == EVENT_DONE_SET, f"{what}: the flag stayed down"
    assert other not in written, f"{what}: it raised the OTHER row's flag as well"
    # NEITHER row frees its slot — that is what makes these two "animation and a flag" and not
    # collectables, and it is the claim the free marker would contradict.
    assert ACTOR + ACTOR_X not in written, f"{what}: the record handed its slot back"
    retyped = ACTOR + ACTOR_TYPE in written
    assert retyped is (name == TYPE36), (
        f"{what}: the record {'was' if retyped else 'was not'} retyped")
    if retyped:
        assert _written_word(written, ACTOR, ACTOR_TYPE) == 0
        # ...and WHAT slot 0 is, which `clr.w 4(a0)` only means through the table: the same
        # precedent slot 60's retype case sets, so "retypes itself to the bare `rts`" is pinned
        # against the IMAGE's own row 0 rather than against the number zero.
        assert _image_slot(0) == leaf.entry_of("actor_behavior_null"), (
            f"{what}: table row 0 is not the null handler, so the retype does not mean what the "
            f"plate says it means")


@pytest.mark.parametrize("name", sorted(EVENT_ROWS), ids=sorted(EVENT_ROWS))
def test_the_event_rows_raise_nothing_before_the_wrap(name):
    """The control for the row above: every frame but the wrapping one leaves both flags alone, so
    the gate does not run its script early."""
    what = f"{name} mid-animation"
    pokes = _event_pokes(what, name, 0)

    written = program_writes(_run_handler(name, what, pokes))
    assert EVENT_ANIM_DONE_B12 not in written and EVENT_ANIM_DONE_B16 not in written


# THE CURSOR THE HANDOVER CASE STARTS FROM, and it is not 0. The table holds each of its four
# sprites for FOUR frames, so a first run from cursor 0 leaves 2 — and the frame at 2 is the same
# word as the frame at 0. A case built that way asserts nothing: the sweep showed it stays green
# when the second record is reseeded to 0, i.e. when it does NOT see the first one's step. Starting
# on the LAST frame of a group makes the handover cross into the next sprite, so "continued" and
# "started again" are different words.
EVENT_HANDOVER_FROM = 6


def test_the_two_event_rows_share_ONE_cursor():
    """WB_ACTOR_EVENT_ANIM_CURSOR is a GLOBAL, and the two rows address it in the two absolute
    forms — long in slot 35 and short in slot 36 — so this is also what says the two `lea`s name the
    same word. A type-35 record steps it and a type-36 record then takes the NEXT frame, which is a
    DIFFERENT sprite because the step crosses a four-frame group."""
    what = "the two event rows share one cursor"
    other = _record(TABLE_DEFAULT, ACTOR_SLOT + 1)
    pokes = _event_pokes(what, TYPE35, EVENT_HANDOVER_FROM, {
        other + ACTOR_TYPE: word(36), other + ACTOR_SPRITE: word(0)})
    handed_on = EVENT_HANDOVER_FROM + ANIM_FRAME_BYTES
    restart = _image_word(EVENT_ANIM_FRAMES)
    continued = _image_word(EVENT_ANIM_FRAMES + handed_on)
    assert continued != restart, (
        f"the frame at {handed_on} is the frame at 0 — this case cannot tell a shared cursor from a "
        f"per-record one, which is exactly what EVENT_HANDOVER_FROM exists to avoid")

    first = _run_handler(TYPE35, what, pokes)
    assert _written_word(program_writes(first), EVENT_ANIM_CURSOR) == handed_on

    # THREADED, so the comment is true: the poke is the word the first run actually left, read out
    # of its ledger rather than recomputed. `handed_on` above is only the assertion's expectation.
    carried = _written_word(program_writes(first), EVENT_ANIM_CURSOR)
    stepped = leaf.overlay(pokes, {EVENT_ANIM_CURSOR: word(carried)})
    info = leaf.run(TYPE36, _HANDLER_GLUE[TYPE36](other), _handler_band(TYPE36),
                    f"{what}, second record", regs={"a0": other, "_pokes": stepped},
                    poison=False, max_insns=_handler_cap(TYPE36))
    assert info["ret"] == DISPATCH_RAN, f"{what}: the second record reported a boundary"
    written = program_writes(info)
    assert _written_word(written, other, ACTOR_SPRITE) == continued, (
        f"{what}: the type-36 record published {_written_word(written, other, ACTOR_SPRITE):#06x} — "
        f"the restart frame is {restart:#06x} and the CONTINUED frame {continued:#06x}")


def test_the_event_frame_table_holds_four_sprites_four_frames_each():
    """The table read off the IMAGE, which is the evidence the plate's reading rests on: sixteen
    words that take four values, each held four frames, and the FIRST of them is the sprite
    `player_pending_event_gate` seeds a type-36 record with. Nothing in the port depends on it."""
    frames = [_image_word(EVENT_ANIM_FRAMES + at)
              for at in range(0, EVENT_ANIM_MASK + 1, ANIM_FRAME_BYTES)]
    assert len(frames) == EVENT_FRAME_COUNT
    distinct = sorted(set(frames))
    assert len(distinct) == 4 and distinct == list(range(distinct[0], distinct[0] + 4))
    assert all(frames[at:at + 4] == [frames[at]] * 4 for at in range(0, EVENT_FRAME_COUNT, 4))


# --- slot 37 ($53e2): the riser, and the band's last row ------------------------------------------
def _type37_pokes(what, y, target=TYPE37_TARGET_Y):
    """A slot-37 record at `y`, with a descriptor whose WB_SCENE_VARIANT puts the target
    WB_ACTOR_TYPE37_RISE below it. The off-image-pointer case builds its own pokes, because
    the whole point of it is that there is no descriptor to seed."""
    base = {ACTOR + ACTOR_TYPE: word(37), ACTOR + ACTOR_Y: word(y),
            RECORD_PTR_10420: longword(DESCRIPTOR_AT),
            DESCRIPTOR_AT + SCENE_VARIANT: word((target + TYPE37_RISE) & 0xffff),
            EVENT_ANIM_DONE_B16: word(0)}
    return _tier_pokes(case_salt(what), base)


@pytest.mark.parametrize("y,arrives", [
    (TYPE37_START_Y, False),
    (TYPE37_TARGET_Y + 1, False),
    (TYPE37_TARGET_Y, True),
    (TYPE37_TARGET_Y - 1, False),      # BELOW the target: the equality is missed, and it keeps going
], ids=["far", "one-short", "arrived", "past"])
def test_slot37_rises_one_pixel_a_frame_until_its_y_EQUALS_its_target(y, arrives):
    """`cmp.w 2(a0),d0 / beq` and not a `ble`, which the last row is what says: a record already
    PAST its target keeps counting down rather than stopping, so it takes the whole 16-bit range to
    come back round. On the frame it arrives it moves nothing and raises the flag instead."""
    what = f"actor_behavior_type37 at {y:#06x}"
    pokes = _type37_pokes(what, y)

    info = _run_handler(TYPE37, what, pokes)
    written = program_writes(info)
    if arrives:
        assert ACTOR + ACTOR_Y not in written, f"{what}: it moved on the frame it arrived"
        assert _written_word(written, EVENT_ANIM_DONE_B16) == EVENT_DONE_SET
        return
    assert _written_word(written, ACTOR, ACTOR_Y) == (y - 1) & 0xffff, f"{what}: it did not rise"
    assert EVENT_ANIM_DONE_B16 not in written, f"{what}: it signalled without arriving"


@pytest.mark.parametrize("target", [0x0000, 0x0100, 0x0400], ids=lambda v: f"target{v:#06x}")
@pytest.mark.parametrize("at_target", [True, False], ids=["arrived", "one-short"])
def test_slot37s_target_is_the_descriptors_own_word_less_the_rise(target, at_target):
    """The target is not a constant: it is WB_SCENE_VARIANT out of the record WB_RECORD_PTR_10420
    names, less WB_ACTOR_TYPE37_RISE — which is the y the gate spawned the record at, so the rise
    is exactly 32 pixels whatever the scene.

    BOTH ARMS PER DESCRIPTOR. Driving only the arrived arm would leave a port whose target is a
    hardcoded constant red on one row and green on the rest; running each descriptor one pixel short
    as well means every row has to agree about WHERE the boundary is, not just that there is one."""
    what = f"actor_behavior_type37 target {target:#06x} {'at' if at_target else 'below'}"
    pokes = _type37_pokes(what, target if at_target else target + 1, target=target)

    written = program_writes(_run_handler(TYPE37, what, pokes))
    if at_target:
        assert _written_word(written, EVENT_ANIM_DONE_B16) == EVENT_DONE_SET, (
            f"{what}: it did not arrive, so the target is not the descriptor's own word")
        assert ACTOR + ACTOR_Y not in written
        return
    assert EVENT_ANIM_DONE_B16 not in written, f"{what}: it arrived a pixel early"
    assert _written_word(written, ACTOR, ACTOR_Y) == target, f"{what}: it did not rise"


def test_slot37_reads_its_descriptor_THROUGH_THE_BUS():
    """WB_RECORD_PTR_10420 is a runtime pointer that ships as ZERO, so the target is fetched through
    an address the reconstruction computed. Off the loaded image both cores read 0 and the target is
    the bare negative rise — a record parked there arrives, and one anywhere else rises."""
    what = "actor_behavior_type37 off-image descriptor"
    off_image = DESCRIPTOR_OFF_IMAGE
    pokes = _tier_pokes(case_salt(what), {
        ACTOR + ACTOR_TYPE: word(37), ACTOR + ACTOR_Y: word((0 - TYPE37_RISE) & 0xffff),
        RECORD_PTR_10420: longword(off_image), EVENT_ANIM_DONE_B16: word(0)})

    written = program_writes(_run_handler(TYPE37, what, pokes))
    assert _written_word(written, EVENT_ANIM_DONE_B16) == EVENT_DONE_SET, (
        f"{what}: an unfilled pointer did not give a target of {(0 - TYPE37_RISE) & 0xffff:#06x}")


# ==== batch 35: the monster-prologue family, dispatch rows 9..13 ====================================
# These five share the $2462 band's WHOLE grammar, so what is driven here is the MIDDLE of each and
# the two things the family does that the band does not: a hurt tail that only TESTS the defeated
# bit, and (slots 10 and 13) a cursor stepped as two read-modify-writes on memory.
#
# THE SEED IS `_walk_pokes_for`'s, unchanged — the same ground window, the same out-of-reach followed
# record — because these handlers read exactly what slots 2..6 read. Arms that leave the tier take
# `_band_slot_pokes` and `_run_band_handler` for the same reason those did.
FAMILY35_HURT_CURSOR_LAST = LAST_FRAME[ANIM16_MASK]

# Where each of the five publishes its hurt frames from, and how the arm ENDS. Slot 13 has no entry:
# its hurt arm never wraps, never lowers bit 0 and never tests the mark — it always dies.
FAMILY35_HURT_WRAPPERS = (9, 10, 11, 12)


def _family35_pokes(what, slot, fields=None, ground=True):
    """`_walk_pokes_for` with the two words the family's own arms read stated: WB_TILE_33_MODE (slots
    9 and 12 call $d78) and a cursor at zero, so a keyed byte cannot index a frame table."""
    base = {ACTOR + FIELD_18: bytes([0]), TILE_33_MODE: word(TILE_33_MODE_SET)}
    return _walk_pokes_for(what, slot, leaf.overlay(base, fields or {}), ground=ground)


@pytest.mark.parametrize("slot", FAMILY35_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family35_spawn_gate_takes_the_whole_frame(slot):
    """`btst #2,9(a0) / bne.w $698a` — the same four instructions slots 2..6 open with, and the same
    consequence: the frame is one animation step and nothing else."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} spawning"
    cursor = 4
    pokes = _monster_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << SPAWNED_BIT]),
                                        ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + FIELD_18: cursor + ANIM_FRAME_BYTES}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + cursor))
    _assert_writes(info, expected, what)


# Which of the five faces the followed record between `bset #0,9(a0) / clr.b 18(a0)` and the tail
# jump into actor_damage_template_hitpoints. Read off the bytes, not guessed: $2e52, $307a and $33fc
# are `bsr $67c2` and slots 11 and 13 have no such instruction.
FAMILY35_STRUCK_FACES = {9: True, 10: True, 11: False, 12: True, 13: False}


@pytest.mark.parametrize("slot", FAMILY35_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family35_struck_arm_enters_the_hurt_animation_and_spends_the_pool(slot):
    """Driven through $23b6's FLASH path, as the band's own struck case is. The followed record is
    seeded to the actor's LEFT so the side flag the three facing slots raise is visible, and the two
    that do not raise it are the same case with the assertion inverted."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} struck by the flash"
    x = 0x0100
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_18: bytes([4]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        FLASH_TIMER: word(1), FOLLOWED_DEFAULT + ACTOR_X: word(x - 1)})

    info = _run_band_handler(slot, what, pokes, "damage-template")
    written = program_writes(info)
    assert written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), f"{what}: the hurt animation was not entered"
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the animation cursor was not zeroed"
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template's pool was not spent, so the tail jump never happened")
    faced = bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << SIDE_BIT))
    assert faced == FAMILY35_STRUCK_FACES[slot], (
        f"{what}: the side flag {'was not' if FAMILY35_STRUCK_FACES[slot] else 'was'} raised, "
        f"against the `bsr $67c2` the bytes {'do' if FAMILY35_STRUCK_FACES[slot] else 'do not'} hold")


@pytest.mark.parametrize("slot", FAMILY35_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family35_hurt_animation_that_wraps_undefeated_comes_back_to_life(slot):
    """`bclr #0,9(a0)` on the wrap, with the mark down: the record returns to its live handler next
    frame and nothing outside the actor tables is touched."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, not defeated"
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + FIELD_18: bytes([FAMILY35_HURT_CURSOR_LAST]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        TILE_33_MODE: word(TILE_33_MODE_SET)})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the record is still in its hurt animation after the wrap")
    assert all(addr < TEMPLATE_TABLE for addr in written), (
        f"{what}: something outside the actor tables was written, so the defeat ran")


@pytest.mark.parametrize("slot", FAMILY35_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family35_hurt_wrap_transfers_and_LEAVES_the_defeated_bit_standing(slot):
    """THE FAMILY'S OWN TAIL, and where it parts from slots 2, 3 and 4: `btst #3,9(a0)`, not `bclr`.
    The transfer into actor_defeat_and_score happens and the mark is still set behind it — so a case
    that only checked "the defeat ran" would pass against the band's spelling too."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, defeated"
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + FIELD_18: bytes([FAMILY35_HURT_CURSOR_LAST]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
        TILE_33_MODE: word(TILE_33_MODE_SET)})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template was not touched, so the transfer never happened")
    assert written[ACTOR + FLAGS2] & (1 << DEFEATED_BIT), (
        f"{what}: the defeated bit was cleared, which is the $2462 band's spelling and not this one's")
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0)


# --- $2f46: the random-facing hop -----------------------------------------------------------------
# The generator's word is the frame tick plus its three counters, so the tick is what steers
# `btst #2` — the same lever test_the_timer_counts_down uses, and the same two values.
_RANDOM_HOP = leaf.register_glue(RANDOM_HOP, [ctypes.c_uint32])


def test_the_random_hop_reads_the_bit_the_timer_table_was_built_for():
    """TICKS_BY_RNG_BIT is stated for WB_ACTOR_TIMER30_RNG_BIT and the case below reuses it to steer
    WB_ACTOR_RANDOM_HOP_RNG_BIT. The two ticks separate that bit's values only because the two
    constants are equal, and nothing else says so — batch 34 pinned WB_JOY1_FIRE_BIT against
    WB_ACTOR_TYPE61_FIRE_BIT for exactly this. Read apart, the parametrisation below would collapse
    onto one arm in silence, and it could not catch that itself: it computes its expectation FROM
    the drawn word, so a divergence agrees with itself."""
    assert RANDOM_HOP_RNG_BIT == TIMER30_RNG_BIT, (
        f"bit {RANDOM_HOP_RNG_BIT} and bit {TIMER30_RNG_BIT} are read apart now, so TICKS_BY_RNG_BIT "
        f"no longer steers the hop's facing")


@pytest.mark.parametrize("tick", sorted(TICKS_BY_RNG_BIT.values()), ids=lambda v: f"tick{v:#06x}")
@pytest.mark.parametrize("flags", [0x00, 1 << SUPPORTED_BIT, 0xff], ids=lambda v: f"flags{v:#04x}")
def test_the_random_hop_turns_AND_launches_a_supported_record(flags, tick):
    """The plate correction as a case: bit 2 of the generator's word picks the FACING and nothing
    vetoes the launch, so an unvetoed hop happens on both values of the bit. An unsupported record
    is left entirely alone — no facing, no speed, no flags."""
    what = f"actor_random_facing_hop flags={flags:#04x} tick={tick:#06x}"
    pokes = _tier_pokes(case_salt(what), leaf.overlay(
        _record_fields(ACTOR, {ACTOR_FLAGS: (flags, 1), SPEED: (0x11, 1)}),
        {FRAME_TICK: word(tick)}))

    expected = {}
    if flags & (1 << SUPPORTED_BIT):
        drawn, counters = model_rng(harness.make_image(pokes), 0)
        expected.update(counters)
        faced = (flags & ~(1 << SIDE_BIT)) if drawn & (1 << RANDOM_HOP_RNG_BIT) \
            else (flags | (1 << SIDE_BIT))
        launched = (faced | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & ~(1 << SUPPORTED_BIT)
        expected[ACTOR + ACTOR_FLAGS] = launched
        expected[ACTOR + SPEED] = RANDOM_HOP_SPEED

    info = leaf.run(RANDOM_HOP, _RANDOM_HOP(ACTOR), merge_bands(expected), what,
                    hw_seed=leaf.hw_declared(), regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap(RANDOM_HOP, extra=RNG_INSNS))
    _assert_writes(info, expected, what)


# --- slot 9 ($2e12): the random hopper --------------------------------------------------------------
TYPE09 = "actor_behavior_type09"
TYPE09_WALK_LISTS = wb("ACTOR_TYPE09_WALK_LISTS")
TYPE09_HURT_LISTS = wb("ACTOR_TYPE09_HURT_LISTS")


def _list_of(pair, left):
    """Which of a $3006 PAIR's two longwords the side flag selects: (a1) while it is SET."""
    return (_image_word(pair + (0 if left else ANIM_LIST_ENTRY)) << 16
            | _image_word(pair + (0 if left else ANIM_LIST_ENTRY) + WORD_BYTES))


@pytest.mark.parametrize("tick", sorted(TICKS_BY_RNG_BIT.values()), ids=lambda v: f"tick{v:#06x}")
def test_slot09_walks_then_asks_the_generator_for_a_new_direction(tick):
    """The whole live frame, and the ORDER inside it — which is what makes the two halves separable.

    actor_step_facing runs BEFORE actor_random_facing_hop and walks on the facing the record ARRIVED
    with (clear here, so three pixels right); the hop then rewrites that facing from bit 2 of the
    generator's word; and actor_anim_step_facing_list, which runs LAST, reads the flag byte the hop
    left. So the step and the frame can disagree about which way the record is looking, and on the
    draw that turns it they do.
    """
    what = f"{TYPE09} walking tick={tick:#06x}"
    x = 0x0100
    pokes = _family35_pokes(what, 9, {ACTOR + ACTOR_X: word(x),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                      FRAME_TICK: word(tick)})

    drawn, counters = model_rng(harness.make_image(pokes), 0)
    info = _run_handler(TYPE09, what, pokes, hw_seed=leaf.hw_declared(),
                        band=_handler_band(TYPE09) + merge_bands(counters))
    written = program_writes(info)
    faces_left_next = not drawn & (1 << RANDOM_HOP_RNG_BIT)
    assert _written_word(written, ACTOR, ACTOR_X) == (x + wb("ACTOR_TYPE09_WALK_STEP")) & 0xffff, (
        f"{what}: the step did not use the facing the record arrived with")
    assert bool(written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)) == faces_left_next, (
        f"{what}: the hop did not set the facing bit 2 of the draw names")
    assert written[ACTOR + SPEED] == RANDOM_HOP_SPEED, f"{what}: the hop did not launch"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        _list_of(TYPE09_WALK_LISTS, left=faces_left_next)), (
        f"{what}: the frame is not the list the hop's NEW facing names")
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


def test_slot09_leaves_an_airborne_record_to_finish_its_arc():
    """`btst #2,8(a0) / beq` inside $2f46: with the record unsupported the hop writes nothing, so
    the flag byte and the speed keep the values the case gave them and the frame is the walk alone.
    """
    what = f"{TYPE09} walking airborne"
    speed = 0x11
    pokes = _family35_pokes(what, 9, {ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                      ACTOR + SPEED: bytes([speed])}, ground=False)

    written = program_writes(_run_handler(TYPE09, what, pokes))
    assert ACTOR + SPEED not in written or written[ACTOR + SPEED] != RANDOM_HOP_SPEED, (
        f"{what}: an airborne record was relaunched")


def test_slot09_stops_at_the_player_gate_on_its_hurt_arm():
    """THE PORT'S BOUNDARY, and the same one slot 53 reports: `bsr $d78` while WB_TILE_33_MODE is
    clear branches into WB_PLAYER_STEP_BODY. Everything below the call — the retreat, the frame and
    the wrap — must therefore be missing from the write set."""
    what = f"{TYPE09} stopped at the player gate"
    pokes = _family35_pokes(what, 9, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                      ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                      TILE_33_MODE: word(0)})

    info = _run_handler(TYPE09, what, pokes, expect=PLAYER_STEP_BODY,
                        stop_pc=PLAYER_STEP_BODY, transfer=_player_gate_beq())
    written = program_writes(info)
    for field in (ACTOR_SPRITE, FIELD_18):
        assert ACTOR + field not in written, (
            f"{what}: {field} was written, so the frame ran on past the gate")


@pytest.mark.parametrize("side,left", [(0, False), (1 << SIDE_BIT, True)], ids=["right", "left"])
def test_slot09_retreats_four_pixels_and_plays_the_hurt_list_its_facing_names(side, left):
    """The hurt arm below the gate: actor_face_and_step_away4 faces the followed record FIRST, so
    the list the frame comes out of is the one the CALL chose and not the one the record arrived
    with. The followed record is seeded on the side the case names."""
    what = f"{TYPE09} hurt side={side:#04x}"
    x = 0x0100
    followed_x = x - 0x40 if left else x + 0x40
    pokes = _family35_pokes(what, 9, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                      ACTOR + ACTOR_X: word(x),
                                      ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)]),
                                      FOLLOWED_DEFAULT + ACTOR_X: word(followed_x),
                                      FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y)})

    written = program_writes(_run_handler(TYPE09, what, pokes))
    assert bool(written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)) == left, (
        f"{what}: actor_set_side_flag did not run before the step")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        _list_of(TYPE09_HURT_LISTS, left=left))
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


# --- slot 10 ($303a): the flier ---------------------------------------------------------------------
TYPE10 = "actor_behavior_type10"
TYPE10_HOVER = wb("ACTOR_TYPE10_HOVER")
TYPE10_HOVER_MASK = wb("ACTOR_TYPE10_HOVER_MASK")
TYPE10_CLOSE_STEP = wb("ACTOR_TYPE10_CLOSE_STEP")
TYPE10_DRIFT_STEP = wb("ACTOR_TYPE10_DRIFT_STEP")
TYPE10_TURN_FRAMES = wb("ACTOR_TYPE10_TURN_FRAMES")
TYPE10_HOME_STEP = wb("ACTOR_TYPE10_HOME_STEP")
TYPE10_HURT_STEP = wb("ACTOR_TYPE10_HURT_STEP")
# The hover cursor one step below its wrap, derived from the mask the handler spells.
TYPE10_HOVER_LAST = TYPE10_HOVER_MASK - 1


def _type10_pokes(what, fields=None):
    """Slot 10 never touches the map while alive, so its cases need no ground under the record.
    Everything else — the turn timer, the hover cursor and a clear flag byte — is `_walk_pokes_for`'s
    own base already, so this wrapper is the ground and nothing more."""
    return _family35_pokes(what, 10, fields, ground=False)


# EVERY CURSOR HERE IS EVEN, deliberately: the handler indexes a WORD table with it, and an odd
# value would have the oracle take a word read at an odd address — legal only because the kit builds
# Musashi with address-error emulation off (TRAP_MODEL.md), and unreachable from the game's own
# state, since the cursor starts at zero and steps by two.
@pytest.mark.parametrize("cursor", [0, 2, 0x20, TYPE10_HOVER_LAST - ANIM_FRAME_BYTES],
                         ids=lambda v: f"cursor{v:#04x}")
def test_slot10_adds_the_hover_table_word_and_steps_its_cursor_in_memory(cursor):
    """One SIGNED word of actor_type10_hover onto the y, and the cursor stepped `addq.b` and masked
    `andi.b` — both on memory. Away from the wrap the close does not run, so the y moves by the
    table word alone and that is what the case reads."""
    what = f"{TYPE10} hovering cursor={cursor:#04x}"
    y = STAND_Y
    pokes = _type10_pokes(what, {ACTOR + FIELD_31: bytes([cursor]), ACTOR + ACTOR_Y: word(y)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    delta = s16(_image_word(TYPE10_HOVER + cursor))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta) & 0xffff, (
        f"{what}: the y did not move by the table's own word")
    assert written[ACTOR + FIELD_31] == (cursor + ANIM_FRAME_BYTES) & TYPE10_HOVER_MASK


@pytest.mark.parametrize("below", [True, False], ids=["followed-below", "followed-above"])
def test_slot10_closes_on_the_followed_y_only_on_the_frame_the_hover_wraps(below):
    """`bne.w` on the MASKED cursor, so the close runs once per 32-frame cycle. Which way it moves
    is a SIGNED compare of the two y words: the actor's own y BELOW the followed record's adds
    WB_ACTOR_TYPE10_CLOSE_STEP, and otherwise it subtracts."""
    what = f"{TYPE10} hover wrapping, followed {'below' if below else 'above'}"
    y = STAND_Y
    delta = s16(_image_word(TYPE10_HOVER + TYPE10_HOVER_LAST))
    followed_y = (y + delta + 0x40) if below else (y + delta - 0x40)
    pokes = _type10_pokes(what, {ACTOR + FIELD_31: bytes([TYPE10_HOVER_LAST]),
                                 ACTOR + ACTOR_Y: word(y),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(followed_y)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    close = TYPE10_CLOSE_STEP if below else -TYPE10_CLOSE_STEP
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta + close) & 0xffff, (
        f"{what}: the vertical close is not the table word plus {close}")
    assert written[ACTOR + FIELD_31] == 0, f"{what}: the hover cursor did not wrap"


@pytest.mark.parametrize("side,delta", [(0, TYPE10_DRIFT_STEP), (1 << SIDE_BIT, -TYPE10_DRIFT_STEP)],
                         ids=["right", "left"])
def test_slot10_drifts_one_pixel_a_frame_with_no_probe_at_all(side, delta):
    """`addq.w #1,(a0)` / `subq.w #1,(a0)` on the side flag, and NOTHING between them and the map:
    this is the one handler in the family that can walk through a wall."""
    what = f"{TYPE10} drifting side={side:#04x}"
    x = 0x0100
    pokes = _type10_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_FLAGS: bytes([side])})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == (x + delta) & 0xffff, (
        f"{what}: a solid row stopped a record that takes no probe")


def test_slot10_counts_its_turn_timer_down_and_publishes_the_side_it_already_had():
    """The ordinary frame: 30(a0) stepped down, no `bchg`, and the animation off the facing the
    record arrived with."""
    what = f"{TYPE10} turn timer running"
    timer = 5
    pokes = _type10_pokes(what, {ACTOR + FIELD_30: bytes([timer]),
                                 ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT])})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert written[ACTOR + FIELD_30] == timer - 1
    assert ACTOR + ACTOR_FLAGS not in written, f"{what}: it turned early"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(wb("ACTOR_TYPE10_WALK_LEFT"))


def test_slot10_turns_reloads_and_takes_one_homing_step_when_the_timer_runs_out():
    """`bchg #3,8(a0)`, a reload of WB_ACTOR_TYPE10_TURN_FRAMES and ONE actor_step_toward_followed
    of WB_ACTOR_TYPE10_HOME_STEP pixels on BOTH axes — the only frame this handler moves diagonally.

    AND THE FRAME PUBLISHED IS THE NEW SIDE'S: the `btst #3,8(a0)` below the turn re-reads the byte
    the `bchg` wrote, where slot 3's walk chooses its list before its own turn."""
    what = f"{TYPE10} turn timer expired"
    x, y = 0x0100, STAND_Y
    pokes = _type10_pokes(what, {ACTOR + FIELD_30: bytes([0]), ACTOR + ACTOR_FLAGS: bytes([0]),
                                 ACTOR + FIELD_31: bytes([2]),
                                 ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                 FOLLOWED_DEFAULT + ACTOR_X: word(x + 0x100),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(y + 0x100)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert written[ACTOR + FIELD_30] == TYPE10_TURN_FRAMES, f"{what}: the timer was not reloaded"
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: `bchg` did not flip the side"
    # The drift moved x by one and the homing step then moved it again, toward a followed record to
    # the right — so the total is the drift plus the home step and not either alone.
    assert _written_word(written, ACTOR, ACTOR_X) == (x + TYPE10_DRIFT_STEP + TYPE10_HOME_STEP) \
        & 0xffff, f"{what}: the homing step did not run"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(wb("ACTOR_TYPE10_WALK_LEFT")), (
        f"{what}: the frame is the OLD side's, so the facing was read before the turn")


@pytest.mark.parametrize("defeated", [False, True], ids=["alive", "marked"])
def test_slot10s_hurt_retreat_is_the_only_thing_the_defeated_mark_suppresses(defeated):
    """`btst #3,9(a0) / bne` jumps over the four-pixel retreat and lands on the animation, so a
    marked record still steps its cursor toward the wrap that kills it."""
    what = f"{TYPE10} hurt {'marked' if defeated else 'alive'}"
    x = 0x0100
    flags2 = (1 << FLAGS2_BIT_0) | ((1 << DEFEATED_BIT) if defeated else 0)
    pokes = _type10_pokes(what, {ACTOR + FLAGS2: bytes([flags2]), ACTOR + ACTOR_X: word(x),
                                 ACTOR + FIELD_18: bytes([2])})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    moved = _written_word(written, ACTOR, ACTOR_X) if ACTOR + ACTOR_X in written else x
    assert (moved == x) == defeated, (
        f"{what}: the retreat {'ran' if defeated else 'did not run'} against the mark")
    if not defeated:
        # The flag byte is clear, so the followed record counts as being to the RIGHT and the
        # retreat goes left — `step_away_without_facing` with nothing facing it first.
        assert moved == (x - TYPE10_HURT_STEP) & 0xffff
    assert written[ACTOR + FIELD_18] == 2 + ANIM_FRAME_BYTES, f"{what}: the animation did not step"


# --- slot 11 ($3218): the decider ------------------------------------------------------------------
TYPE11 = "actor_behavior_type11"
TYPE11_RELOAD = wb("ACTOR_TYPE11_RELOAD")
TYPE11_HOP_SPEED = wb("ACTOR_TYPE11_HOP_SPEED")
TYPE11_FACE_RNG_BIT = wb("ACTOR_TYPE11_FACE_RNG_BIT")
TYPE11_HOP_RNG_BIT = wb("ACTOR_TYPE11_HOP_RNG_BIT")
TYPE11_HURT_BIT = wb("ACTOR_TYPE11_HURT_BIT")

# Frame ticks that put the generator's word on each of the four (face, hop) combinations bits 2 and
# 1 name. Found by search rather than stated, so a change to the generator moves them rather than
# silently collapsing the parametrisation onto one arm.
def _ticks_for_slot11_draws():
    wanted, found = {(0, 0), (0, 1), (1, 0), (1, 1)}, {}
    for tick in range(0x40):
        if wanted <= set(found):        # every probe builds a 1 MiB image; stop at the fourth hit
            break
        pokes = _tier_pokes(case_salt(f"slot11 tick probe {tick}"), {FRAME_TICK: word(tick)})
        drawn, _counters = model_rng(harness.make_image(pokes), 0)
        key = ((drawn >> TYPE11_FACE_RNG_BIT) & 1, (drawn >> TYPE11_HOP_RNG_BIT) & 1)
        found.setdefault(key, tick)
    assert wanted <= set(found), f"no frame tick reaches {sorted(wanted - set(found))}"
    return found


SLOT11_TICKS = _ticks_for_slot11_draws()


def test_slot11_walks_and_animates_while_its_countdown_runs():
    """The ordinary frame: 30(a0) stepped down, actor_step_facing's two pixels, and one frame off
    the list the facing names. No generator is read at all."""
    what = f"{TYPE11} walking"
    x, timer = 0x0100, 7
    pokes = _family35_pokes(what, 11, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE11, what, pokes))
    assert written[ACTOR + FIELD_30] == timer - 1
    assert _written_word(written, ACTOR, ACTOR_X) == (x + wb("ACTOR_TYPE11_WALK_STEP")) & 0xffff
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(wb("ACTOR_TYPE11_WALK_RIGHT"))
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


def test_slot11_turns_round_on_a_blocked_step():
    """`tst.b d0 / bchg #3,8(a0)` — actor_step_facing's own tail, spelt inline here. The BYTE of the
    probe's answer is what decides, which is the reading batch 34 had to separate from slot 28's."""
    what = f"{TYPE11} blocked"
    pokes = _family35_pokes(what, 11, {ACTOR + FIELD_30: bytes([7]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE11, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: a blocked step did not turn it"


def test_slot11_that_is_airborne_when_its_countdown_expires_only_reloads():
    """The reload runs BEFORE `btst #2,8(a0)`, so an unsupported record gets a fresh countdown and
    nothing else — no draw, no facing, no hop, and no animation either, because the decision frame
    returns above the walk."""
    what = f"{TYPE11} decision airborne"
    pokes = _family35_pokes(what, 11, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                       ACTOR + SPEED: bytes([0])}, ground=False)

    written = program_writes(_run_handler(TYPE11, what, pokes))
    assert written[ACTOR + FIELD_30] == TYPE11_RELOAD
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the decision frame published a frame"
    assert ACTOR + FIELD_18 not in written, f"{what}: the decision frame stepped the cursor"


@pytest.mark.parametrize("draw", sorted(SLOT11_TICKS), ids=lambda v: f"face{v[0]}hop{v[1]}")
def test_slot11_decides_a_facing_and_a_hop_from_one_generator_word(draw):
    """ONE `rng_next` word does both jobs. Bit 2 SET faces LEFT — the OPPOSITE reading to $2f46's
    on the same bit — and bit 1 SET VETOES the hop, so three of the four combinations move the
    record and one of them only turns it."""
    face, hop_vetoed = draw
    what = f"{TYPE11} decision face={face} hop={hop_vetoed}"
    pokes = _family35_pokes(what, 11, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       ACTOR + SPEED: bytes([0x11]),
                                       FRAME_TICK: word(SLOT11_TICKS[draw])})

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    info = _run_handler(TYPE11, what, pokes, hw_seed=leaf.hw_declared(),
                        band=_handler_band(TYPE11) + merge_bands(counters))
    written = program_writes(info)
    assert written[ACTOR + FIELD_30] == TYPE11_RELOAD
    assert bool(written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)) == bool(face), (
        f"{what}: bit {TYPE11_FACE_RNG_BIT} of the draw did not choose the facing")
    # The SPEED byte is not the witness: actor_fall_and_settle writes it on every frame. What only
    # the hop can do is the three-bit motion contract.
    if hop_vetoed:
        assert not written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT), (
            f"{what}: bit {TYPE11_HOP_RNG_BIT} did not veto the hop")
        assert written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)
    else:
        assert written[ACTOR + SPEED] == TYPE11_HOP_SPEED
        assert written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT)
        assert not written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)


@pytest.mark.parametrize("timer,marked", [(TYPE11_RELOAD, True), (TYPE11_RELOAD & ~(1 << 3), False)],
                         ids=["bit3-set", "bit3-clear"])
def test_slot11_picks_its_hurt_list_off_bit_3_of_the_COUNTDOWN_byte(timer, marked):
    """THE ONE TABLE SELECT IN THE FAMILY THAT IS NOT THE SIDE FLAG. Both seeds face the same way,
    so a port that read WB_ACTOR_FLAG_SIDE_BIT here would publish one list for both — and the two
    values are the reload itself and the reload with bit 3 knocked out, i.e. states the live arm
    really produces as its countdown runs down."""
    what = f"{TYPE11} hurt timer={timer:#04x}"
    frames = wb("ACTOR_TYPE11_HURT_MARKED") if marked else wb("ACTOR_TYPE11_HURT_PLAIN")
    pokes = _family35_pokes(what, 11, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE11, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames), (
        f"{what}: the hurt list is not the one bit {TYPE11_HURT_BIT} of 30(a0) names")
    assert ACTOR + FIELD_30 not in written, f"{what}: the hurt arm touched the countdown"


# --- slot 12 ($33bc): the chaser -------------------------------------------------------------------
TYPE12 = "actor_behavior_type12"
TYPE12_GROUND_LISTS = wb("ACTOR_TYPE12_GROUND_LISTS")
TYPE12_AIR_LISTS = wb("ACTOR_TYPE12_AIR_LISTS")
TYPE12_HURT_LISTS = wb("ACTOR_TYPE12_HURT_LISTS")


@pytest.mark.parametrize("side,left", [(0, False), (1 << SIDE_BIT, True)], ids=["right", "left"])
def test_slot12_faces_the_followed_record_and_steps_toward_it(side, left):
    """actor_face_and_step_toward: the side flag is written from the followed record's x FIRST and
    the step then goes that way, so the seeded flag is overwritten rather than obeyed."""
    what = f"{TYPE12} chasing from side={side:#04x}"
    x = 0x0100
    followed_x = x - 0x40 if left else x + 0x40
    pokes = _family35_pokes(what, 12, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([5]),
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x), FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y)})

    written = program_writes(_run_handler(TYPE12, what, pokes))
    step = wb("ACTOR_TYPE12_WALK_STEP")
    assert bool(written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)) == left
    assert _written_word(written, ACTOR, ACTOR_X) == (x + (-step if left else step)) & 0xffff


@pytest.mark.parametrize("supported", [True, False], ids=["grounded", "airborne"])
def test_slot12_picks_its_animation_by_the_SUPPORTED_bit_and_not_by_a_cursor(supported):
    """`btst #2,8(a0)` chooses between two whole list PAIRS. The airborne pair's lists are ONE word
    and a terminator, so $3006's look-ahead zeroes the cursor on the very frame it publishes —
    which is what makes an airborne record hold one frame rather than animate."""
    what = f"{TYPE12} {'grounded' if supported else 'airborne'}"
    flags = (1 << SUPPORTED_BIT) if supported else (1 << MOVING_BIT)
    pokes = _family35_pokes(what, 12, {ACTOR + FIELD_30: bytes([5]),
                                       ACTOR + ACTOR_FLAGS: bytes([flags]),
                                       ACTOR + SPEED: bytes([0])}, ground=supported)

    written = program_writes(_run_handler(TYPE12, what, pokes))
    pair = TYPE12_GROUND_LISTS if supported else TYPE12_AIR_LISTS
    # The chase re-faces the record first, and the followed one is far to the RIGHT in this seed.
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(_list_of(pair, left=False))
    assert written[ACTOR + FIELD_18] == (0 if not supported else ANIM_FRAME_BYTES), (
        f"{what}: the one-word list did not wrap the cursor on its own frame")


def test_slot12_stops_at_the_player_gate_on_its_hurt_arm():
    """Slot 9's boundary again, in the second of the two handlers that reach it."""
    what = f"{TYPE12} stopped at the player gate"
    pokes = _family35_pokes(what, 12, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       TILE_33_MODE: word(0)})

    info = _run_handler(TYPE12, what, pokes, expect=PLAYER_STEP_BODY,
                        stop_pc=PLAYER_STEP_BODY, transfer=_player_gate_beq())
    written = program_writes(info)
    for field in (ACTOR_SPRITE, FIELD_18):
        assert ACTOR + field not in written, (
            f"{what}: {field} was written, so the frame ran on past the gate")


def test_slot12s_hurt_arm_retreats_and_plays_its_own_pair():
    """Below the gate it is slot 9's arm exactly, over slot 12's own lists."""
    what = f"{TYPE12} hurt"
    x = 0x0100
    pokes = _family35_pokes(what, 12, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + ACTOR_X: word(x),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(x + 0x40),
                                       FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y)})

    written = program_writes(_run_handler(TYPE12, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == (x - STEP_AWAY_PIXELS) & 0xffff, (
        f"{what}: the retreat did not go AWAY from the followed record")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        _list_of(TYPE12_HURT_LISTS, left=False))


# --- slot 13 ($34d2): the bouncer, and the family's one certain death -------------------------------
TYPE13 = "actor_behavior_type13"
TYPE13_FRAMES = wb("ACTOR_TYPE13_FRAMES")
TYPE13_HOP_SPEED = wb("ACTOR_TYPE13_HOP_SPEED")
TYPE13_DEATH_FRAMES = wb("ACTOR_TYPE13_DEATH_FRAMES")
TYPE13_DEATH_SPEED = wb("ACTOR_TYPE13_DEATH_SPEED")
TYPE13_HURT_STEP = wb("ACTOR_TYPE13_HURT_STEP")
TYPE13_HURT_SPRITE = wb("ACTOR_TYPE13_HURT_SPRITE")
TYPE13_DYING = wb("ACTOR_TYPE13_DYING")


@pytest.mark.parametrize("cursor", [0, 4, LAST_FRAME[ANIM16_MASK]], ids=lambda v: f"cursor{v:#04x}")
def test_slot13_relaunches_on_every_supported_frame_and_animates(cursor):
    """NO countdown and NO draw: `btst #2,8(a0)` alone, so a record that lands is airborne again the
    same frame. Its cursor is the family's other two-write one."""
    what = f"{TYPE13} hopping cursor={cursor:#04x}"
    pokes = _family35_pokes(what, 13, {ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       ACTOR + FIELD_18: bytes([cursor]),
                                       ACTOR + SPEED: bytes([0])})

    written = program_writes(_run_handler(TYPE13, what, pokes))
    assert written[ACTOR + SPEED] == TYPE13_HOP_SPEED, f"{what}: a supported record did not relaunch"
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE13_FRAMES + cursor)
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & ANIM16_MASK


def test_slot13_leaves_an_airborne_record_to_finish_its_arc():
    """The other side of that `beq`: the frame is the settle, the ascent and one animation frame."""
    what = f"{TYPE13} airborne"
    speed = 3
    pokes = _family35_pokes(what, 13, {ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT]),
                                       ACTOR + SPEED: bytes([speed])}, ground=False)

    written = program_writes(_run_handler(TYPE13, what, pokes))
    assert written.get(ACTOR + SPEED, speed) != TYPE13_HOP_SPEED, (
        f"{what}: an airborne record was relaunched")


@pytest.mark.parametrize("followed_left", [False, True], ids=["followed-right", "followed-left"])
def test_slot13_arms_its_throe_on_the_frame_the_latch_is_down(followed_left):
    """`tst.b 30(a0)` zero is the FIRST frame of the throe: WB_ACTOR_TYPE13_DEATH_FRAMES into
    31(a0), `st 30(a0)`, the inline relaunch at WB_ACTOR_TYPE13_DEATH_SPEED and one
    actor_set_side_flag. It then falls straight through into the throe's own step.

    THE SEEDED FLAG IS THE OPPOSITE OF WHAT THE CALL WILL WRITE on both rows, which is what makes
    the call observable at all: with the record already facing the right way, dropping it changes
    nothing (`slot13/side-flag-not-set-on-the-first-throe-frame` survived the sweep's first pass on
    exactly that). The step below then goes the other way on the two rows."""
    what = f"{TYPE13} throe armed, followed {'left' if followed_left else 'right'}"
    x = 0x0100
    seeded_side = 0 if followed_left else (1 << SIDE_BIT)
    pokes = _family35_pokes(what, 13, {
        ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([0]),
        ACTOR + ACTOR_X: word(x),
        ACTOR + ACTOR_FLAGS: bytes([seeded_side | (1 << SUPPORTED_BIT)]),
        FOLLOWED_DEFAULT + ACTOR_X: word(x - 0x40 if followed_left else x + 0x40),
        FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y)})

    written = program_writes(_run_handler(TYPE13, what, pokes))
    assert written[ACTOR + FIELD_30] == TYPE13_DYING, f"{what}: the latch was not set"
    # $19 stored, then the throe's own `subq.b #1` below it — so the byte lands one below the count.
    assert written[ACTOR + FIELD_31] == TYPE13_DEATH_FRAMES - 1
    assert written[ACTOR + SPEED] == TYPE13_DEATH_SPEED
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == TYPE13_HURT_SPRITE
    assert bool(written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT)) == followed_left, (
        f"{what}: actor_set_side_flag did not run before the step")
    step = TYPE13_HURT_STEP if followed_left else -TYPE13_HURT_STEP
    assert _written_word(written, ACTOR, ACTOR_X) == (x + step) & 0xffff, (
        f"{what}: the throe stepped toward the followed record rather than away")


def test_slot13_does_not_re_arm_a_throe_that_is_already_running():
    """The latch again, from the other side: with 30(a0) nonzero the setup is skipped whole, so the
    countdown keeps falling and the speed is whatever the arc left."""
    what = f"{TYPE13} throe running"
    throe, speed = 7, 0x11
    pokes = _family35_pokes(what, 13, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + FIELD_30: bytes([TYPE13_DYING]),
                                       ACTOR + FIELD_31: bytes([throe]),
                                       ACTOR + SPEED: bytes([speed]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                            ground=False)

    written = program_writes(_run_handler(TYPE13, what, pokes))
    assert written[ACTOR + FIELD_31] == throe - 1
    assert ACTOR + FIELD_30 not in written, f"{what}: the latch was re-stamped"
    assert written.get(ACTOR + SPEED, speed) != TYPE13_DEATH_SPEED, f"{what}: it was re-armed"


@pytest.mark.parametrize("defeated", [False, True], ids=["unmarked", "marked"])
def test_slot13_ALWAYS_dies_when_its_throe_runs_out(defeated):
    """THE ONE UNCONDITIONAL TRANSFER IN THE FAMILY. `subq.b #1,31(a0) / bne` reaching zero does
    `clr.b 30(a0)` and `bra.w $6bb8` with no `btst` anywhere near it, so the defeat runs whether the
    record was marked or not — which is what separates this row from the other four."""
    what = f"{TYPE13} throe expired, {'marked' if defeated else 'unmarked'}"
    flags2 = (1 << FLAGS2_BIT_0) | ((1 << DEFEATED_BIT) if defeated else 0)
    pokes = _band_slot_pokes(what, 13, {ACTOR + FLAGS2: bytes([flags2]),
                                        ACTOR + FIELD_30: bytes([TYPE13_DYING]),
                                        ACTOR + FIELD_31: bytes([1]),
                                        ACTOR + TEMPLATE_SLOT: bytes([2]),
                                        ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                                       ground=False)

    info = _run_band_handler(13, what, pokes, "defeat")
    written = program_writes(info)
    assert written[ACTOR + FIELD_31] == 0
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: actor_defeat_and_score did not run, so the transfer is conditional after all")
    # `clr.b 30(a0)` is only OBSERVABLE on the defeat's retire tail: its respawn continuation stamps
    # WB_ACTOR_RESPAWN_FIELD_30 into the same byte. Which tail this seed reaches comes from
    # test_actor.py's own model rather than from a guess here.
    if ACTOR + FIELD_30 not in _model_defeat(harness.make_image(pokes), ACTOR)[2]:
        assert written[ACTOR + FIELD_30] == 0, f"{what}: the latch was not cleared"


# --- the census, as cases --------------------------------------------------------------------------
# Batch 34's lesson applied before the fact: every table this batch names is claimed to have ONE
# operand site, and the claim is checked against the image rather than against the plate.
FAMILY35_TABLES = (
    "ACTOR_TYPE09_WALK_LISTS", "ACTOR_TYPE09_HURT_LISTS",
    "ACTOR_TYPE10_HOVER", "ACTOR_TYPE10_WALK_LEFT", "ACTOR_TYPE10_WALK_RIGHT",
    "ACTOR_TYPE10_HURT_LEFT", "ACTOR_TYPE10_HURT_RIGHT",
    "ACTOR_TYPE11_WALK_LEFT", "ACTOR_TYPE11_WALK_RIGHT",
    "ACTOR_TYPE11_HURT_MARKED", "ACTOR_TYPE11_HURT_PLAIN",
    "ACTOR_TYPE12_GROUND_LISTS", "ACTOR_TYPE12_AIR_LISTS", "ACTOR_TYPE12_HURT_LISTS",
    "ACTOR_TYPE13_FRAMES",
)
# The three forms a `lea` can name an address in, one per addressing mode — and ALL THREE are swept,
# because the plates claim "one operand site in the whole image" and each of the other two is a form
# that has already hidden something in this project: batch 34's $5160 miss was the SHORT absolute,
# and batch 28's whole coverage wall was the PC-relative INDEXED displacement.
LEA_ABS_L_OPCODES_W = tuple(0x41f9 | (reg << 9) for reg in range(8))
LEA_ABS_W_OPCODES_W = tuple(0x41f8 | (reg << 9) for reg in range(8))
LEA_PC_INDEXED_OPCODES_W = tuple(0x41fb | (reg << 9) for reg in range(8))
LEA_PC_DISP_OPCODES_W = tuple(0x41fa | (reg << 9) for reg in range(8))


def _lea_sites(addr):
    """Every `lea` in the image that names `addr`, in any of its three forms.

    A lookup into `INSTRUCTION_TARGETS` (defined below, beside the cases that need the wider scan)
    rather than a sweep of its own: the two used to be separate passes with different bounds, and a
    negative proved with one while the plate quoted the other is not a negative at all.
    """
    return sorted(at for at, op in INSTRUCTION_TARGETS.get(addr, []) if op in LEA_FORM_OPCODES)


# ...and batch 36's, swept the same way before the fact. The two GLOBAL cursors are NOT here: they
# are read and written by absolute `move.w`, not named by a `lea`, and have their own case below.
FAMILY36_TABLES = (
    "ACTOR_TYPE14_WALK_LEFT", "ACTOR_TYPE14_WALK_RIGHT", "ACTOR_TYPE14_HURT",
    "ACTOR_TYPE15_WALK_LEFT", "ACTOR_TYPE15_WALK_RIGHT",
    "ACTOR_TYPE15_HURT_LEFT", "ACTOR_TYPE15_HURT_RIGHT",
    "ACTOR_TYPE16_WALK_LEFT", "ACTOR_TYPE16_WALK_RIGHT",
    "ACTOR_TYPE16_HURT_LEFT", "ACTOR_TYPE16_HURT_RIGHT",
    "ACTOR_TYPE17_LIVE_LISTS", "ACTOR_TYPE17_HURT_LISTS",
    "ACTOR_TYPE17_DX", "ACTOR_TYPE17_DY",
    "ACTOR_TYPE18_WALK_LEFT", "ACTOR_TYPE18_WALK_RIGHT",
    "ACTOR_TYPE18_HURT_LEFT", "ACTOR_TYPE18_HURT_RIGHT",
    "ACTOR_TYPE19_DRIFT", "ACTOR_TYPE19_FRAMES_LEFT", "ACTOR_TYPE19_FRAMES_RIGHT",
    "ACTOR_TYPE19_DEATH",
)
CENSUSED_TABLES = FAMILY35_TABLES + FAMILY36_TABLES


@pytest.mark.parametrize("name", CENSUSED_TABLES)
def test_every_table_this_batch_names_has_exactly_one_lea_naming_it(name):
    """The plate for each of these says "one operand site, by a whole-image scan of both absolute
    encodings and of the `lea d8(PC,Dn.w)` displacement". This case IS that scan, so the claim is
    re-run on every commit rather than being true only on the day it was written."""
    addr = wb(name)
    sites = _lea_sites(addr)
    assert len(sites) == 1, (
        f"{name} ({addr:#06x}) is named by {len(sites)} `lea`s, not one: "
        f"{[hex(at) for at in sites]}")


# --- THE FRAME READ IS RAW, AND THE MASK BOUNDS ONLY THE STORE ------------------------------------
# `move.b 18(a0),d0 / lea 0(a1,d0.w),a1 / move.w (a1),6(a0)` publishes FIRST, and the `andi.b` runs
# afterwards on the value going BACK into the record — at all four of this batch's frame reads
# ($332e, $3110, $3548 and the hover's $3084). So the mask says where the cursor GOES and never
# where it came from, and a record holding a cursor above it reads PAST the table its `lea` names.
#
# THE PLATES USED TO ASSERT THE INVERSE and the battery rested on it: the case below asserted
# `LAST_FRAME[mask] + 2 == mask + 1`, which compares two constants and cannot fail, and three
# mask-BEFORE-index mutants survived the whole suite. These drive the over-read instead.
TYPE11_PADDING = {wb("ACTOR_TYPE11_HURT_MARKED"): 0x338c, wb("ACTOR_TYPE11_HURT_PLAIN"): 0x33ac}
# One whole table past the start: the first cursor the mask can never STORE and a record can hold.
OVER_READ_CURSOR = ANIM16_MASK + 1
# ...and two tables past, which is where slot 13's over-read leaves its own data entirely.
TYPE13_OVER_CURSOR = 2 * (ANIM16_MASK + 1)
TYPE10_HOVER_OVER_CURSOR = TYPE10_HOVER_MASK + 1


@pytest.mark.parametrize("live,padding", sorted(TYPE11_PADDING.items()), ids=lambda v: f"{v:#06x}")
def test_slot11s_duplicate_blocks_are_REACHABLE_padding(live, padding):
    """WHAT THE TWO DUPLICATES ARE FOR, re-derived now that the read is known to be raw: sixteen
    bytes above each hurt list repeating it exactly, so an over-read publishes the same frame.

    No `lea` names either block — they are not tables in their own right — and a cursor of
    OVER_READ_CURSOR reaches the first of them through the LIVE table's own `lea`. That is batch
    28's coverage wall one addressing mode over, and it is why "no operand site" is a statement
    about DIRECT readers and not about reachability."""
    image = bytes(harness.BASE_IMAGE)
    span = ANIM16_MASK + 1
    assert image[padding:padding + span] == image[live:live + span], (
        f"{padding:#06x} is not a copy of {live:#06x} after all")
    assert not _lea_sites(padding), f"{padding:#06x} is named by a `lea` after all"
    assert live + OVER_READ_CURSOR == padding, (
        f"a cursor of {OVER_READ_CURSOR} off {live:#06x} does not land on {padding:#06x}")


@pytest.mark.parametrize("bit3", [True, False], ids=["hurt-marked", "hurt-plain"])
def test_slot11_publishes_the_SAME_frame_from_the_padding_as_from_the_table(bit3):
    """...and the consequence, driven rather than argued: with the cursor one whole table past the
    start the handler publishes out of the padding, and the frame is the one the table would have
    given. THE PADDING IS WHY THE OVER-READ IS HARMLESS HERE — slot 13 below has none."""
    what = f"{TYPE11} hurt over-read {'marked' if bit3 else 'plain'}"
    frames = wb("ACTOR_TYPE11_HURT_MARKED") if bit3 else wb("ACTOR_TYPE11_HURT_PLAIN")
    timer = TYPE11_RELOAD if bit3 else TYPE11_RELOAD & ~(1 << TYPE11_HURT_BIT)
    assert _image_word(frames + OVER_READ_CURSOR) == _image_word(frames), (
        f"{what}: the padding no longer repeats the table, so this case would prove nothing")
    pokes = _family35_pokes(what, 11, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + FIELD_18: bytes([OVER_READ_CURSOR]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE11, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames + OVER_READ_CURSOR)
    # The STORE is masked even though the read was not, which is the whole asymmetry.
    assert written[ACTOR + FIELD_18] == (OVER_READ_CURSOR + ANIM_FRAME_BYTES) & ANIM16_MASK


def test_slot13_publishes_from_PAST_its_table_when_the_cursor_is_over_the_mask():
    """The same over-read where NOTHING pads it. actor_type13_frames is sixteen bytes and
    actor_behavior_type14's code begins sixteen bytes above that, so a cursor of TYPE13_OVER_CURSOR
    publishes a word of the NEXT HANDLER'S OPCODES as a sprite id — which is what says the index is
    the raw record byte and not the masked one."""
    what = f"{TYPE13} cursor past its table"
    assert _image_word(TYPE13_FRAMES + TYPE13_OVER_CURSOR) != _image_word(TYPE13_FRAMES), (
        f"{what}: the word past the table equals the first one, so this case could not separate the "
        f"raw index from the masked one")
    pokes = _family35_pokes(what, 13, {ACTOR + FIELD_18: bytes([TYPE13_OVER_CURSOR]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                            ground=False)

    written = program_writes(_run_handler(TYPE13, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE13_FRAMES
                                                                     + TYPE13_OVER_CURSOR)
    assert written[ACTOR + FIELD_18] == (TYPE13_OVER_CURSOR + ANIM_FRAME_BYTES) & ANIM16_MASK


def test_slot10_walks_off_the_end_of_its_frame_list_the_same_way():
    """The third of the four raw reads, and the one whose over-read lands on the NEIGHBOURING LIST:
    the four eight-word lists are contiguous, so a cursor of OVER_READ_CURSOR off the left one
    publishes the right one's first frame."""
    what = f"{TYPE10} walk cursor past its list"
    left, right = wb("ACTOR_TYPE10_WALK_LEFT"), wb("ACTOR_TYPE10_WALK_RIGHT")
    assert _image_word(left + OVER_READ_CURSOR) == _image_word(right) != _image_word(left), (
        f"{what}: the two lists are no longer adjacent-and-different, so the seed is stale")
    pokes = _type10_pokes(what, {ACTOR + FIELD_18: bytes([OVER_READ_CURSOR]),
                                 ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT])})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(left + OVER_READ_CURSOR)


def test_slot10s_hover_indexes_with_the_RAW_cursor_byte_too():
    """The fourth, and the only one that is not a sprite: a hover cursor past
    WB_ACTOR_TYPE10_HOVER_MASK reads a word of actor_behavior_type11's own opcodes and ADDS IT TO
    THE Y. The table is 64 bytes and slot 11's entry is the next thing above it."""
    what = f"{TYPE10} hover cursor past its table"
    y = STAND_Y
    delta = s16(_image_word(TYPE10_HOVER + TYPE10_HOVER_OVER_CURSOR))
    assert delta != s16(_image_word(TYPE10_HOVER)), f"{what}: the seed cannot separate the two reads"
    pokes = _type10_pokes(what, {ACTOR + FIELD_31: bytes([TYPE10_HOVER_OVER_CURSOR]),
                                 ACTOR + ACTOR_Y: word(y)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta) & 0xffff, (
        f"{what}: the hover indexed the MASKED cursor, not the byte the record holds")


def test_the_two_bounded_hurt_arms_are_exactly_the_two_that_call_the_player_gate():
    """FAMILY35_BOUNDED is prose until something checks it. The pins hold each body's bytes, so the
    `bsr.w $d78` either is in them or is not."""
    call = bsr_w(0, leaf.entry_of(PLAYER_GATE))[:2]
    for slot in FAMILY35_SLOTS:
        body = ENTRY_BYTES[f"actor_behavior_type{slot:02d}"]
        calls = [at for at in range(0, len(body), 2)
                 if body[at:at + 2] == call
                 and leaf.entry_of(PLAYER_GATE) == leaf.entry_of(f"actor_behavior_type{slot:02d}")
                 + at + leaf.BRANCH_EXTENSION + s16(body[at + 2] << 8 | body[at + 3])]
        assert bool(calls) == (slot in FAMILY35_BOUNDED), (
            f"slot {slot} has {len(calls)} calls to the player gate, against FAMILY35_BOUNDED")


# --- the three holes the mutation sweep found -------------------------------------------------------
# Each of these closes a mutant that SURVIVED the first pass, and each hole is the same shape: an arm
# the cases above reached with only one value of the state that steers it.
@pytest.mark.parametrize("side,delta", [(0, -TYPE10_HURT_STEP), (1 << SIDE_BIT, TYPE10_HURT_STEP)],
                         ids=["side-clear", "side-set"])
def test_slot10s_hurt_retreat_goes_BOTH_ways_on_the_facing_it_arrived_with(side, delta):
    """`step/family-away-becomes-toward` SURVIVED: every case above reached
    `step_away_without_facing` with WB_ACTOR_FLAG_SIDE_BIT CLEAR, so its SET arm — the one that steps
    RIGHT — was never driven and a port with both arms the same way passed. The retreat has no
    actor_set_side_flag in front of it, so the seeded flag is what steers it."""
    what = f"{TYPE10} hurt retreat side={side:#04x}"
    x = 0x0100
    pokes = _type10_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                 ACTOR + ACTOR_X: word(x),
                                 ACTOR + ACTOR_FLAGS: bytes([side]),
                                 ACTOR + FIELD_18: bytes([2])})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == (x + delta) & 0xffff, (
        f"{what}: the retreat went the wrong way for this facing")


def test_slot12_publishes_the_AIRBORNE_list_when_its_own_timer_launches_it():
    """`slot12/list-chosen-before-the-timer-runs` SURVIVED: no case above let actor_tick_timer30
    reach its relaunch, so the SUPPORTED bit the list select reads never changed inside a frame.

    Here the countdown is already zero and the generator's word permits, so the record is supported
    when the frame starts and AIRBORNE by the time the select runs — and the frame published must be
    the air pair's."""
    what = f"{TYPE12} launched by its own timer"
    tick = TICKS_BY_RNG_BIT[0]           # the draw whose bit 2 is CLEAR, i.e. the relaunch fires
    pokes = _family35_pokes(what, 12, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       ACTOR + SPEED: bytes([0]), FRAME_TICK: word(tick)})

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    info = _run_handler(TYPE12, what, pokes, hw_seed=leaf.hw_declared(),
                        band=_handler_band(TYPE12) + merge_bands(counters))
    written = program_writes(info)
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT), (
        f"{what}: the timer did not launch the record, so the select cannot have moved")
    assert written[ACTOR + SPEED] == TIMER30_SPEED
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        _list_of(TYPE12_AIR_LISTS, left=False)), (
        f"{what}: the ground list was published, so the SUPPORTED bit was read before the timer ran")


# ...and `cursor/memory-step-becomes-one-store`, which SURVIVES and is an EQUIVALENCE UNDER THIS
# HARNESS rather than a hole — with the argument checked against the geometry rather than asserted.
#
# `addq.b #2,d16(a0)` then `andi.b #mask,d16(a0)` agree with a port that computed both in a register
# everywhere the store LANDS, so the only seed that could separate them is a record whose cursor byte
# bus.h refuses: there the mask reads back ZERO where the register holds the stepped value.
#
# TWO OF THE THREE SITES CANNOT SHOW IT AT ALL, because nothing reads the answer: slot 10's walk
# cursor and slot 13's discard it, so the frame is identical either way. The third — slot 10's hover
# cursor — DOES branch on it, and the difference lands in the record's own WB_ACTOR_Y.
#
# AND NO RECORD ADDRESS PUTS THAT Y WHERE THE DIFFERENTIAL CAN SEE IT. `os_in_image` refuses exactly
# [$100000, $ffffff] after the 24-bit fold, and the diff covers [0, emu.STACK_GUARD_LO) — the top
# $1000 bytes of the image are the oracle's own machine stack and are excluded. For
# WB_ACTOR_FIELD_31 to be refused the record must start at $fffe1 or above (or fold past $ffffff, in
# which case the y is refused too), and every such record's y is at $fffe3 or above — inside the
# excluded band. The two spellings are therefore indistinguishable here for a reason that is about
# the harness's window and not about the code, and the original's is reproduced regardless.
#
# (Contrast the swoop's $7378/$73c0 pin, which uses a record at $fffff0: it works because the fields
# it OBSERVES fold back to $6 and $a, low addresses inside the compared prefix. Nothing folds a byte
# 29 offsets away from another into that prefix while leaving the other one refused.)


# --- three more holes, from the review gate's own mutation probes ------------------------------------
# Each of these was found by mutating the reconstruction and watching the whole suite stay green.
@pytest.mark.parametrize("y,followed_y,close", [
    (0x0080, 0x0600, TYPE10_CLOSE_STEP),
    # THE SIGN BIT, which every other seed in this file leaves clear: as a SIGNED word the actor is
    # far ABOVE the followed record and closes downward, and an unsigned reading of the same two
    # words says the opposite.
    (0xff00, 0x0010, TYPE10_CLOSE_STEP),
], ids=["both-positive", "actor-y-negative"])
def test_slot10s_vertical_close_compares_the_two_y_words_SIGNED(y, followed_y, close):
    """`cmp.w 2(a1),d1 / blt` — the compare src/behavior.c spells with `field_w`, which returns
    int16_t. A port that compared the raw words agrees on every seed whose y is a small positive and
    closes the WRONG WAY for a record above the screen origin."""
    what = f"{TYPE10} signed close y={y:#06x}"
    pokes = _type10_pokes(what, {ACTOR + FIELD_31: bytes([TYPE10_HOVER_LAST]),
                                 ACTOR + ACTOR_Y: word(y),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(followed_y)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    delta = s16(_image_word(TYPE10_HOVER + TYPE10_HOVER_LAST))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta + close) & 0xffff, (
        f"{what}: the close went the wrong way, so the compare read the words UNSIGNED")


def test_slot10s_close_compares_the_y_the_hover_JUST_WROTE():
    """`move.w 2(a0),d1` reads the record's y out of MEMORY, one instruction after `add.w d1,2(a0)`
    put the hover's own delta there — so the compare sees the stepped y and not the entry one.

    The followed record is placed ONE PIXEL between the two readings, which is the only gap that can
    separate them: the hover word at the wrap cursor is -2, so the pre-hover y is 2 above the
    post-hover one and a target in between answers the compare differently each way."""
    what = f"{TYPE10} close reads the stepped y"
    y = STAND_Y
    delta = s16(_image_word(TYPE10_HOVER + TYPE10_HOVER_LAST))
    assert delta == -ANIM_FRAME_BYTES, f"{what}: the wrap frame's delta moved, so the seed is stale"
    pokes = _type10_pokes(what, {ACTOR + FIELD_31: bytes([TYPE10_HOVER_LAST]),
                                 ACTOR + ACTOR_Y: word(y),
                                 FOLLOWED_DEFAULT + ACTOR_Y: word(y - 1)})

    written = program_writes(_run_handler(TYPE10, what, pokes))
    # Stepped y (y-2) is ABOVE the followed record's (y-1), so the close is downward and lands back
    # on y; a port comparing the ENTRY y would find y > y-1 and close upward, to y-4.
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta + TYPE10_CLOSE_STEP) & 0xffff, (
        f"{what}: the compare read the y from before the hover step")


# The four family slots whose live arm opens `bsr $1334 / bsr $501a`. Slot 10 has neither.
FAMILY35_SETTLE_THEN_ASCEND = (9, 11, 12, 13)
# The speed a case seeds so the ascent's `subq.b #1,11(a0)` reaches zero on the frame it drives —
# the one frame the pair's ORDER changes anything — and the pixel that ascent lifts.
WB_ASCENT_LAST_SPEED = 1
WB_ASCENT_LAST_STEP = WB_ASCENT_LAST_SPEED


@pytest.mark.parametrize("slot", FAMILY35_SETTLE_THEN_ASCEND, ids=lambda v: f"slot{v:02d}")
def test_the_family35_live_arms_settle_BEFORE_they_ascend(slot):
    """`bsr $1334` then `bsr $501a`, in that order, in all four — and the order is observable on the
    frame an ascent ENDS, because each of the two reads WB_ACTOR_FLAG_MOVING_BIT and one of them
    writes it.

    A record already MOVING is one actor_start_motion_at_speed launched, and actor_fall_and_settle
    returns for exactly that — so in the original the settle does nothing and the ascent lifts the
    record one pixel, ending the arc and lowering the bit. Swap the two and the ascent lowers the
    bit FIRST, the settle then finds it clear, and the record is stepped back down by the speed byte
    the ascent left behind. One pixel apart, and only on this frame.
    """
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} settle before ascend"
    y = STAND_Y
    pokes = _family35_pokes(what, slot, {ACTOR + ACTOR_Y: word(y),
                                         ACTOR + SPEED: bytes([WB_ASCENT_LAST_SPEED]),
                                         ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                            ground=False)

    written = program_writes(_run_handler(name, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_Y) == y - WB_ASCENT_LAST_STEP, (
        f"{what}: the ascent ran first, so the settle stepped the record back down")
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT), (
        f"{what}: the ascent did not end this frame, so the order is not observable in this seed")


# ==== batch 36: the family's second block, dispatch rows 14..19 =====================================
# These six run the same grammar as batch 35's five, so what is driven here is each middle plus the
# three things this block adds: a hurt tail in a SECOND order, five SPAWNERS, and a struck arm that
# depends on WHICH test struck.
TYPE14, TYPE15, TYPE16 = (f"actor_behavior_type{slot}" for slot in (14, 15, 16))
TYPE17, TYPE18, TYPE19 = (f"actor_behavior_type{slot}" for slot in (17, 18, 19))

MINION_SIZE = wb("ACTOR_MINION_SIZE")
MINION_SPEED = wb("ACTOR_MINION_SPEED")
TYPE14_WALK_LEFT = wb("ACTOR_TYPE14_WALK_LEFT")
TYPE14_WALK_RIGHT = wb("ACTOR_TYPE14_WALK_RIGHT")
TYPE14_HURT = wb("ACTOR_TYPE14_HURT")
TYPE14_WALK_STEP = wb("ACTOR_TYPE14_WALK_STEP")
TYPE14_TURN_FRAMES = wb("ACTOR_TYPE14_TURN_FRAMES")
TYPE14_SPAWN_GAP = wb("ACTOR_TYPE14_SPAWN_GAP")
TYPE14_MINION_TYPE = wb("ACTOR_TYPE14_MINION_TYPE")
TYPE14_MINION_TIMER = wb("ACTOR_TYPE14_MINION_TIMER")
TYPE15_WALK_LEFT = wb("ACTOR_TYPE15_WALK_LEFT")
TYPE15_WALK_RIGHT = wb("ACTOR_TYPE15_WALK_RIGHT")
TYPE15_HURT_LEFT = wb("ACTOR_TYPE15_HURT_LEFT")
TYPE15_HURT_RIGHT = wb("ACTOR_TYPE15_HURT_RIGHT")
TYPE15_WALK_STEP = wb("ACTOR_TYPE15_WALK_STEP")
TYPE16_WALK_LEFT = wb("ACTOR_TYPE16_WALK_LEFT")
TYPE16_WALK_RIGHT = wb("ACTOR_TYPE16_WALK_RIGHT")
TYPE16_HURT_LEFT = wb("ACTOR_TYPE16_HURT_LEFT")
TYPE16_HURT_RIGHT = wb("ACTOR_TYPE16_HURT_RIGHT")
TYPE16_RELOAD = wb("ACTOR_TYPE16_RELOAD")
TYPE16_HOP_SPEED = wb("ACTOR_TYPE16_HOP_SPEED")
TYPE16_MINION_TYPE = wb("ACTOR_TYPE16_MINION_TYPE")
TYPE17_DX = wb("ACTOR_TYPE17_DX")
TYPE17_DX_MASK = wb("ACTOR_TYPE17_DX_MASK")
TYPE17_DY = wb("ACTOR_TYPE17_DY")
TYPE17_DY_MASK = wb("ACTOR_TYPE17_DY_MASK")
TYPE17_SEED_ODDS_MASK = wb("ACTOR_TYPE17_SEED_ODDS_MASK")
TYPE17_SEED_FIRST = wb("ACTOR_TYPE17_SEED_FIRST")
TYPE17_SEED_TYPE = wb("ACTOR_TYPE17_SEED_TYPE")
TYPE17_SEED_SIZE = wb("ACTOR_TYPE17_SEED_SIZE")
TYPE17_SEED_SPEED = wb("ACTOR_TYPE17_SEED_SPEED")
TYPE18_WALK_LEFT = wb("ACTOR_TYPE18_WALK_LEFT")
TYPE18_WALK_RIGHT = wb("ACTOR_TYPE18_WALK_RIGHT")
TYPE18_HURT_LEFT = wb("ACTOR_TYPE18_HURT_LEFT")
TYPE18_HURT_RIGHT = wb("ACTOR_TYPE18_HURT_RIGHT")
TYPE18_WALK_STEP = wb("ACTOR_TYPE18_WALK_STEP")
TYPE18_HURT_STEP = wb("ACTOR_TYPE18_HURT_STEP")
TYPE18_CHARGING = wb("ACTOR_TYPE18_CHARGING")
TYPE18_HOP_SPEED = wb("ACTOR_TYPE18_HOP_SPEED")
TYPE18_MINION_TYPE = wb("ACTOR_TYPE18_MINION_TYPE")
TYPE18_TURN_FRAMES = wb("ACTOR_TYPE18_TURN_FRAMES")
TYPE19_DRIFT = wb("ACTOR_TYPE19_DRIFT")
TYPE19_DRIFT_MASK = wb("ACTOR_TYPE19_DRIFT_MASK")
TYPE19_GLIDE_SPRITE = wb("ACTOR_TYPE19_GLIDE_SPRITE")
TYPE19_GLIDE_HEIGHT = wb("ACTOR_TYPE19_GLIDE_HEIGHT")
TYPE19_ATTACK_HEIGHT = wb("ACTOR_TYPE19_ATTACK_HEIGHT")
TYPE19_PHASE2 = wb("ACTOR_TYPE19_PHASE2")
TYPE19_FRAMES_LEFT = wb("ACTOR_TYPE19_FRAMES_LEFT")
TYPE19_FRAMES_RIGHT = wb("ACTOR_TYPE19_FRAMES_RIGHT")
TYPE19_FRAME_MASK = wb("ACTOR_TYPE19_FRAME_MASK")
TYPE19_DEATH = wb("ACTOR_TYPE19_DEATH")
TYPE19_SHOT_CURSOR = wb("ACTOR_TYPE19_SHOT_CURSOR")
TYPE19_SHOT_TYPE = wb("ACTOR_TYPE19_SHOT_TYPE")
TYPE19_SHOT_RISE = wb("ACTOR_TYPE19_SHOT_RISE")
TYPE19_SHOT_DX_RIGHT = wb("ACTOR_TYPE19_SHOT_DX_RIGHT")
TYPE19_SHOT_DX_LEFT = wb("ACTOR_TYPE19_SHOT_DX_LEFT")
TYPE19_SHOT_SIZE = wb("ACTOR_TYPE19_SHOT_SIZE")

# The high pool's first record, which every spawner in this batch is handed while the pool is
# untouched — `_walk_pokes_for` frees all six, so the allocator's answer is its first.
FIRST_HIGH_RECORD = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST)


def _family36_pokes(what, slot, fields=None, ground=True):
    """`_walk_pokes_for` under this batch's own name — batch 35's seed WITHOUT WB_TILE_33_MODE,
    because none of these six calls the player gate. It adds no pin of its own: the frame cursor
    these cases depend on is already stated at zero by `_walk_pokes_for`, and restating it here
    would be a second copy that could disagree."""
    return _walk_pokes_for(what, slot, fields, ground=ground)


def _full_pool_pokes(pokes):
    """Every record of the high pool OCCUPIED, so actor_alloc_slot_high answers WB_ACTOR_ALLOC_NONE.
    The x word is what carries WB_ACTOR_FREE_MARKER, so overwriting it is what fills the pool."""
    for high in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        pokes[_record(TABLE_DEFAULT, high) + ACTOR_X] = word(OCCUPIED_X)
    return pokes


# --- the three things this block adds to the grammar ----------------------------------------------
@pytest.mark.parametrize("slot", FAMILY36_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family36_spawn_gate_takes_the_whole_frame(slot):
    """`btst #2,9(a0) / bne.w $698a` — the same four instructions the eleven handlers before these
    open with, and the same consequence: the frame is one animation step and nothing else."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} spawning"
    cursor = 4
    pokes = _monster_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << SPAWNED_BIT]),
                                        ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + FIELD_18: cursor + ANIM_FRAME_BYTES}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + cursor))
    _assert_writes(info, expected, what)


# WHICH of the six faces the followed record on the struck arm, and WHICH TEST struck decides it for
# two of them. Read off the bytes: $3a86 is slot 17's `bsr $67c2` below BOTH arms' join, and $3cc0 /
# $3ec8 are slots 18's and 19's, ABOVE the join and reached only from the overlap-POINT branch.
FAMILY36_STRUCK_FACES = {
    # slot: (faces after a SHOT hit, faces after an overlap-POINT hit)
    14: (False, False), 15: (False, False), 16: (False, False),
    17: (True, True), 18: (False, True), 19: (False, True),
}


def _point_strike_pokes(what, slot, fields=None):
    """A seed whose followed record strikes the actor through $5c6e's POINT test and NOT its body
    test: the point is `followed.x + WB_ACTOR_POINT_RIGHT`, `followed.y - WB_ACTOR_POINT_UP`, so
    placing the record that far to the LEFT lands the point inside the actor's box while its own
    body box (half-width 4) stops well short of it."""
    base = {FOLLOWED_DEFAULT + ACTOR_SPRITE: word(POINT_LO),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0100 - POINT_RIGHT),
            FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y - 4 + POINT_UP)}
    return _band_slot_pokes(what, slot, leaf.overlay(base, fields or {}))


@pytest.mark.parametrize("by_point", [False, True], ids=["struck-by-shot", "struck-by-point"])
@pytest.mark.parametrize("slot", FAMILY36_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family36_struck_arm_faces_on_the_arm_the_bytes_say(slot, by_point):
    """THE SPLIT THIS BLOCK ADDS. Slots 18 and 19 call actor_set_side_flag on the overlap-POINT arm
    ALONE — a shot hit reaches `bset #0,9(a0)` from above it — where slot 17 faces on both arms and
    slots 14, 15 and 16 on neither. Driving only one of the two would leave the other unpinned and
    a port that faced on both would still be green."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} struck by {'the overlap point' if by_point else 'the flash'}"
    fields = {ACTOR + FIELD_18: bytes([4]), ACTOR + TEMPLATE_SLOT: bytes([2]),
              ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}
    if by_point:
        pokes = _point_strike_pokes(what, slot, fields)
    else:
        # The flash reports a hit for anything within WB_ACTOR_FLASH_REACH, and the followed record
        # is to the actor's LEFT so a facing call is visible in the side flag.
        pokes = _band_slot_pokes(what, slot, leaf.overlay(
            {FLASH_TIMER: word(1), FOLLOWED_DEFAULT + ACTOR_X: word(0x0100 - 1)}, fields))

    info = _run_band_handler(slot, what, pokes, "damage-template")
    written = program_writes(info)
    assert written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), f"{what}: the hurt animation was not entered"
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the animation cursor was not zeroed"
    faced = bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << SIDE_BIT))
    expected = FAMILY36_STRUCK_FACES[slot][by_point]
    assert faced == expected, (
        f"{what}: the side flag {'was not' if expected else 'was'} raised, against the "
        f"`bsr $67c2` the bytes {'do' if expected else 'do not'} place on this arm")


# Which slots FLIP the side flag between $5c6e's body bit and the tail jump into $69fe. Slot 3 has
# the same `bchg` and no other handler in this family does.
FAMILY36_BODY_ARM_FLIPS = {14: False, 15: False, 16: False, 17: False, 18: True, 19: True}


@pytest.mark.parametrize("slot", FAMILY36_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family36_body_arm_flips_the_facing_only_where_the_bchg_is(slot):
    """`bchg #3,8(a0) / bra.w $69fe` — slots 18 and 19 turn the monster round as it deals damage and
    the other four do not."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} touching the followed record"
    side = 1 << SIDE_BIT
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)]),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0100), FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0x0100)})

    info = _run_handler(name, what, pokes, band=_foreign_band(harness.make_image(pokes), {},
                                                              "damage-followed"))
    written = program_writes(info)
    # THE POSITIVE CONTROL. Without it the four rows that expect NO flip are satisfied by the body
    # arm never having been reached — `written.get(..., side)` reads "no write" as "did not flip" —
    # so each row first requires actor_damage_followed to have marked the followed record.
    assert written[FOLLOWED_DEFAULT + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the followed record was not damaged, so this seed never reached the body arm")
    flipped = not (written.get(ACTOR + ACTOR_FLAGS, side) & (1 << SIDE_BIT))
    assert flipped == FAMILY36_BODY_ARM_FLIPS[slot], (
        f"{what}: the facing {'did not flip' if FAMILY36_BODY_ARM_FLIPS[slot] else 'flipped'}, "
        f"against the `bchg` the bytes {'do' if FAMILY36_BODY_ARM_FLIPS[slot] else 'do not'} hold")


# WHERE EACH HURT ARM WRAPS, and in WHICH ORDER it reads the two marks. `defeat-first` is slots 15
# and 16's `btst #3,9(a0) / bne / bclr #0,9(a0)`, which leaves bit 0 STANDING behind the transfer;
# `clear-first` is batch 35's tail. Slot 19 is neither and has its own cases below.
# Slot 17 has no mask at all: it animates through $3006, whose look-ahead ends the list on a
# NEGATIVE word — and its four lists are eight frames plus that terminator, so the cursor that wraps
# is the same LAST_FRAME[ANIM16_MASK] an eight-word masked table gives.
FAMILY36_HURT = {
    14: (TYPE14_HURT, ANIM16_MASK, "clear-first"),
    15: (TYPE15_HURT_RIGHT, ANIM32_MASK, "defeat-first"),
    16: (TYPE16_HURT_RIGHT, ANIM32_MASK, "defeat-first"),
    17: (None, ANIM16_MASK, "clear-first"),
    18: (TYPE18_HURT_RIGHT, ANIM16_MASK, "clear-first"),
}
FAMILY36_HURT_WRAPPERS = tuple(sorted(FAMILY36_HURT))


def _hurt_wrap_cursor(slot):
    """The cursor that sits on the last frame, so one more step wraps it."""
    return LAST_FRAME[FAMILY36_HURT[slot][1]]


@pytest.mark.parametrize("slot", FAMILY36_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family36_hurt_animation_that_wraps_undefeated_comes_back_to_life(slot):
    """With the mark down, both orders agree: bit 0 goes down and the record returns to its live
    handler next frame. It is the DEFEATED case below that separates them."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, not defeated"
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + FIELD_18: bytes([_hurt_wrap_cursor(slot)]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the record is still in its hurt animation after the wrap")
    assert all(addr < TEMPLATE_TABLE for addr in written), (
        f"{what}: something outside the actor tables was written, so the defeat ran")
    # ...and the frame published is the LAST of that slot's own hurt table, which is what makes this
    # a case about the wrap of a named list rather than about a cursor in the abstract. Slot 17
    # animates through $3006's list PAIR, whose address is not a table this case can index.
    frames = FAMILY36_HURT[slot][0]
    if frames is not None:
        assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
            frames + _hurt_wrap_cursor(slot)), f"{what}: the last frame is not this slot's"


@pytest.mark.parametrize("slot", FAMILY36_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family36_hurt_wrap_transfers_and_the_TAIL_ORDER_decides_what_it_leaves(slot):
    """THE SECOND ORDER, and it is only visible behind the transfer: slots 15 and 16 branch into
    actor_defeat_and_score BEFORE lowering bit 0, so a defeated record arrives there still marked
    hurt, where slots 14, 17 and 18 lower it first. Both spellings run the defeat, so a case that
    only checked "the defeat ran" would pass against either."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, defeated"
    order = FAMILY36_HURT[slot][2]
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + FIELD_18: bytes([_hurt_wrap_cursor(slot)]),
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template was not touched, so the transfer never happened")
    assert written[ACTOR + FLAGS2] & (1 << DEFEATED_BIT), (
        f"{what}: the defeated bit was cleared, which is the $2462 band's spelling and not this one's")
    still_hurt = bool(written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0))
    assert still_hurt == (order == "defeat-first"), (
        f"{what}: bit 0 is {'set' if still_hurt else 'clear'} behind the transfer, against the "
        f"{order} tail the bytes hold")


# --- slot 14 ($35d8): the patroller that drops escorts ---------------------------------------------
def test_slot14_turns_and_takes_the_frame_OFF_when_its_countdown_expires():
    """`bchg #3,8(a0) / move.b #$46,30(a0) / rts` — the turn frame steps nothing and publishes
    nothing. A port that fell through into the walk would move the record and animate it on the very
    frame it turned round. (The settle above it still lands the record, which is why this asserts
    the two bytes the ARM writes and the two it must not rather than the whole set.)"""
    what = f"{TYPE14} turning"
    x = 0x0100
    pokes = _family36_pokes(what, 14, {ACTOR + FIELD_30: bytes([0]), ACTOR + ACTOR_X: word(x),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE14, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: it did not turn"
    assert written[ACTOR + FIELD_30] == TYPE14_TURN_FRAMES
    assert ACTOR + ACTOR_X not in written, f"{what}: the turn frame stepped"
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the turn frame animated"


def test_slot14_drops_an_escort_when_the_gap_byte_runs_out():
    """The drop: a WB_ACTOR_TYPE14_MINION_TYPE record on the patroller's own square, and the frame
    ENDS there — no step and no animation. WB_ACTOR_FIELD_31 comes back as the gap."""
    what = f"{TYPE14} dropping"
    timer, x, y = 7, 0x0100, STAND_Y
    pokes = _family36_pokes(what, 14, {ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + FIELD_31: bytes([0]),
                                       ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE14, what, pokes))
    escort = FIRST_HIGH_RECORD
    assert _written_word(written, escort, ACTOR_X) == x
    assert _written_word(written, escort, ACTOR_Y) == y
    assert _written_word(written, escort, ACTOR_TYPE) == TYPE14_MINION_TYPE
    assert _written_word(written, escort, HALF_WIDTH) == MINION_SIZE >> 16
    assert _written_word(written, escort, SIZE_SECOND) == MINION_SIZE & 0xffff
    assert written[escort + FIELD_30] == TYPE14_MINION_TIMER
    assert written[escort + FIELD_31] == 0 and written[escort + FIELD_18] == 0
    assert written[ACTOR + FIELD_31] == TYPE14_SPAWN_GAP
    assert written[ACTOR + FIELD_30] == timer - 1
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the drop frame animated as well"


def test_slot14_leaves_the_gap_byte_at_zero_when_the_pool_is_full():
    """`move.b #$1e,31(a0)` sits BELOW the failed-allocation branch, so a record that could not drop
    tries again on the very next walking frame instead of waiting out the gap."""
    what = f"{TYPE14} dropping into a full pool"
    timer = 7
    pokes = _full_pool_pokes(_family36_pokes(what, 14, {
        ACTOR + FIELD_30: bytes([timer]), ACTOR + FIELD_31: bytes([0]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    written = program_writes(_run_handler(TYPE14, what, pokes))
    assert written[ACTOR + FIELD_30] == timer - 1
    assert ACTOR + FIELD_31 not in written, f"{what}: the gap byte was armed on a refused drop"
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the refused drop animated"


@pytest.mark.parametrize("side,frames,step", [
    (0, TYPE14_WALK_RIGHT, TYPE14_WALK_STEP),
    (1 << SIDE_BIT, TYPE14_WALK_LEFT, -TYPE14_WALK_STEP),
], ids=["facing-right", "facing-left"])
def test_slot14_walks_one_pixel_and_publishes_the_list_its_facing_names(side, frames, step):
    """The ordinary frame: both countdowns down one, one pixel of map-checked step, and a frame off
    the list the facing chose AFTER actor_toggle_side_flag could have turned it."""
    what = f"{TYPE14} walking side={side:#04x}"
    x, timer, gap = 0x0100, 7, 5
    pokes = _family36_pokes(what, 14, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]), ACTOR + FIELD_31: bytes([gap]),
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)])})

    written = program_writes(_run_handler(TYPE14, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == x + step
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames)
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES
    assert written[ACTOR + FIELD_31] == gap - 1


def test_slot14_publishes_THIS_frames_turn_and_not_last_frames():
    """The list select re-reads 8(a0) AFTER `bsr $2b82`, so a step blocked into a turn shows in the
    frame published on the SAME frame — slot 6's order, where slot 3 chooses before its own turn."""
    what = f"{TYPE14} blocked and turning"
    pokes = _family36_pokes(what, 14, {ACTOR + FIELD_30: bytes([7]), ACTOR + FIELD_31: bytes([5]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE14, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: the blocked step did not turn it"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE14_WALK_LEFT), (
        f"{what}: the frame published is the PRE-turn list's, so the facing was read too early")


# --- slot 15 ($3764): the walker that turns AND hops -----------------------------------------------
@pytest.mark.parametrize("side,frames,step", [
    (0, TYPE15_WALK_RIGHT, TYPE15_WALK_STEP),
    (1 << SIDE_BIT, TYPE15_WALK_LEFT, -TYPE15_WALK_STEP),
], ids=["facing-right", "facing-left"])
def test_slot15_steps_four_pixels_toward_the_side_flag(side, frames, step):
    what = f"{TYPE15} walking side={side:#04x}"
    x = 0x0100
    pokes = _family36_pokes(what, 15, {ACTOR + ACTOR_X: word(x),
                                       ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)])})

    written = program_writes(_run_handler(TYPE15, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == x + step
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames)
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


def test_slot15_turns_AND_LAUNCHES_when_its_step_is_blocked():
    """`bsr $2b8e` where slots 6, 14, 18 and 25 call $2b82: a blocked step on a SUPPORTED record flips
    the facing AND relaunches it — bits 0 and 1 up, bit 2 down and the speed byte written. Nothing
    else in this family hops off a failed step."""
    what = f"{TYPE15} blocked"
    pokes = _family36_pokes(what, 15, {ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE15, what, pokes))
    flags = written[ACTOR + ACTOR_FLAGS]
    assert flags & (1 << SIDE_BIT), f"{what}: it did not turn"
    assert flags & (1 << MOVING_BIT) and flags & (1 << LAUNCHED_BIT), f"{what}: it did not launch"
    assert not flags & (1 << SUPPORTED_BIT)
    assert written[ACTOR + SPEED] == wb("ACTOR_TURN_LAUNCH_SPEED")


def test_slot15_publishes_the_list_it_chose_BEFORE_the_turn():
    """The `lea` sits between the probe and `bsr $2b8e`, so on the frame the record turns it is
    still animating out of the OLD side's table — the opposite order to slot 14's."""
    what = f"{TYPE15} turning"
    pokes = _family36_pokes(what, 15, {ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE15, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), f"{what}: this seed did not turn it"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE15_WALK_RIGHT), (
        f"{what}: the POST-turn list was published, so the `lea` was read too late")


# --- slot 16 ($38ae): the hopper that lobs ---------------------------------------------------------
@pytest.mark.parametrize("followed_x,side,frames", [
    (0x0600, 0, TYPE16_WALK_RIGHT),
    (0x0010, 1 << SIDE_BIT, TYPE16_WALK_LEFT),
], ids=["followed-right", "followed-left"])
def test_slot16_faces_the_followed_record_BEFORE_it_picks_a_list(followed_x, side, frames):
    """`bsr $67c2` runs above the `btst`, so the frame published is always the side the followed
    record is on THIS frame."""
    what = f"{TYPE16} facing {followed_x:#06x}"
    pokes = _family36_pokes(what, 16, {ACTOR + FIELD_30: bytes([7]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(followed_x)})

    written = program_writes(_run_handler(TYPE16, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT) == side
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames)
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES
    assert written[ACTOR + FIELD_30] == 6


def test_slot16_launches_and_lobs_when_its_countdown_expires():
    """The launch and the lob together: three flag bits, the speed, a fresh countdown, and a
    WB_ACTOR_TYPE16_MINION_TYPE record carrying the flag byte the launch JUST wrote."""
    what = f"{TYPE16} launching"
    x, y = 0x0100, STAND_Y
    pokes = _family36_pokes(what, 16, {ACTOR + FIELD_30: bytes([0]), ACTOR + ACTOR_X: word(x),
                                       ACTOR + ACTOR_Y: word(y),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE16, what, pokes))
    flags = written[ACTOR + ACTOR_FLAGS]
    assert flags & (1 << MOVING_BIT) and flags & (1 << LAUNCHED_BIT)
    assert not flags & (1 << SUPPORTED_BIT)
    assert written[ACTOR + SPEED] == TYPE16_HOP_SPEED
    assert written[ACTOR + FIELD_30] == TYPE16_RELOAD
    minion = FIRST_HIGH_RECORD
    assert _written_word(written, minion, ACTOR_TYPE) == TYPE16_MINION_TYPE
    assert written[minion + ACTOR_FLAGS] == flags, (
        f"{what}: the minion did not inherit the flag byte the three bit writes above it left")
    assert written[minion + SPEED] == MINION_SPEED
    assert _written_word(written, minion, ACTOR_X) == x and _written_word(written, minion, ACTOR_Y) == y


def test_slot16_that_is_airborne_when_its_countdown_expires_neither_launches_nor_lobs():
    """`bclr #2,8(a0)` is the test AND the write, and the branch reads the bit as it WAS — so an
    airborne record leaves with nothing done but that store.

    THE STORE ITSELF IS NOT OBSERVABLE HERE, and saying so is the point of this note: `bsr $67c2` at
    $38fa runs on every live frame and ends in a `bset`/`bclr` of the same byte, so 8(a0) is in the
    write ledger whatever the `bclr` below does. What the case can pin is the branch — the record
    does not launch and does not lob — and the store is carried by the entry pin instead."""
    what = f"{TYPE16} airborne at the reload"
    pokes = _family36_pokes(what, 16, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    written = program_writes(_run_handler(TYPE16, what, pokes))
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << MOVING_BIT), f"{what}: it launched"
    assert ACTOR + SPEED not in written or written[ACTOR + SPEED] != TYPE16_HOP_SPEED
    assert FIRST_HIGH_RECORD + ACTOR_TYPE not in written, f"{what}: it lobbed"


def test_slot16_still_launches_when_the_pool_is_full():
    """The lob is the LAST thing the arm does, so a refused allocation costs the minion and nothing
    else — the parent has already left the ground."""
    what = f"{TYPE16} launching into a full pool"
    pokes = _full_pool_pokes(_family36_pokes(what, 16, {
        ACTOR + FIELD_30: bytes([0]), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    written = program_writes(_run_handler(TYPE16, what, pokes))
    assert written[ACTOR + SPEED] == TYPE16_HOP_SPEED
    assert written[ACTOR + FIELD_30] == TYPE16_RELOAD
    assert FIRST_HIGH_RECORD + ACTOR_TYPE not in written


# --- slot 17 ($3a46): the drifter that seeds five --------------------------------------------------
# The y cursor that WRAPS on the next step, so the seeding is reached. Derived from the mask, like
# LAST_FRAME, rather than transcribed.
TYPE17_DY_LAST = TYPE17_DY_MASK - (ANIM_FRAME_BYTES - 1)


def _type17_pokes(what, fields=None):
    """A drifter and its two GLOBAL cursors stated, since neither is a record field and a fresh
    image would leave both at whatever the last case wrote."""
    base = {wb("ACTOR_TYPE17_DX_CURSOR"): word(0), wb("ACTOR_TYPE17_DY_CURSOR"): word(0)}
    return _family36_pokes(what, 17, leaf.overlay(base, fields or {}))


# The third row steps the X cursor over its own wrap while the Y one stays inside — a Y wrap would
# reach the seeding, whose `rng_next` needs a declared hardware byte, and that arm has its own case.
# The FOURTH row is the sweep's finding: every earlier seed answered the same under a $7f mask as
# under a $3f one, so `slot17/axis-masks-exchanged` survived. $40 is the smallest cursor the two
# masks disagree about ($42 against $02).
@pytest.mark.parametrize("dx_cursor,dy_cursor", [(0, 0), (0x10, 0x08), (0x40, 0x20), (0x7e, 0x3c)],
                         ids=lambda v: f"{v:#04x}")
def test_slot17_drifts_on_BOTH_axes_out_of_two_global_cursors(dx_cursor, dy_cursor):
    """The x and y deltas are two SIGNED words indexed by two words that live in the image rather
    than in the record — so what steers the drift is state no record owns."""
    what = f"{TYPE17} drifting {dx_cursor:#04x}/{dy_cursor:#04x}"
    x, y = 0x0100, STAND_Y
    pokes = _type17_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                 wb("ACTOR_TYPE17_DX_CURSOR"): word(dx_cursor),
                                 wb("ACTOR_TYPE17_DY_CURSOR"): word(dy_cursor)})

    written = program_writes(_run_handler(TYPE17, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == (x + _image_word(TYPE17_DX + dx_cursor)) & 0xffff
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + _image_word(TYPE17_DY + dy_cursor)) & 0xffff
    assert _written_word(written, TYPE17_DX_CURSOR) == (dx_cursor + ANIM_FRAME_BYTES) & TYPE17_DX_MASK
    assert _written_word(written, TYPE17_DY_CURSOR) == (dy_cursor + ANIM_FRAME_BYTES) & TYPE17_DY_MASK


# THE STARTING CURSORS MATTER, and the first draft of the case below got them wrong. Both drift
# tables run in blocks of four equal words, so a record starting at cursor 0 and one starting at
# cursor 2 move by the SAME delta — which is exactly what a port holding the cursors in the record
# would produce, and the case could not fail. These two sit on the last entry of a block, so the
# successor the first record leaves behind is a different number.
TYPE17_DX_BLOCK_END = 0x06
TYPE17_DY_BLOCK_END = 0x04


def test_two_slot17_records_drift_in_LOCKSTEP_through_the_shared_cursors():
    """THE CONSEQUENCE OF THE CURSORS BEING GLOBAL, threaded rather than argued: the first record's
    frame is run, the pair of words IT left is read out of the write ledger and poked into the
    second record's seed, and the second record is then required to move by the NEXT entry of each
    table. A port holding either cursor in the record would give both records the same delta."""
    first_what = f"{TYPE17} drifting, first record"
    x, y = 0x0100, STAND_Y
    for table, start in ((TYPE17_DX, TYPE17_DX_BLOCK_END), (TYPE17_DY, TYPE17_DY_BLOCK_END)):
        assert _image_word(table + start) != _image_word(table + start + ANIM_FRAME_BYTES), (
            f"{table:#06x} holds the same delta either side of {start:#04x}, so the second record "
            f"would move like the first however the cursor is held")
    first = program_writes(_run_handler(TYPE17, first_what, _type17_pokes(first_what, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        wb("ACTOR_TYPE17_DX_CURSOR"): word(TYPE17_DX_BLOCK_END),
        wb("ACTOR_TYPE17_DY_CURSOR"): word(TYPE17_DY_BLOCK_END)})))
    dx_cursor = _written_word(first, TYPE17_DX_CURSOR)
    dy_cursor = _written_word(first, TYPE17_DY_CURSOR)
    assert (dx_cursor, dy_cursor) == (TYPE17_DX_BLOCK_END + ANIM_FRAME_BYTES,
                                      TYPE17_DY_BLOCK_END + ANIM_FRAME_BYTES)

    second_what = f"{TYPE17} drifting, second record"
    second = program_writes(_run_handler(TYPE17, second_what, _type17_pokes(second_what, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        wb("ACTOR_TYPE17_DX_CURSOR"): word(dx_cursor),
        wb("ACTOR_TYPE17_DY_CURSOR"): word(dy_cursor)})))
    assert _written_word(second, ACTOR, ACTOR_X) == (x + _image_word(TYPE17_DX + dx_cursor)) & 0xffff
    assert _written_word(second, ACTOR, ACTOR_Y) == (y + _image_word(TYPE17_DY + dy_cursor)) & 0xffff


def _ticks_for_slot17_draw():
    """One frame tick whose `rng_next` word passes WB_ACTOR_TYPE17_SEED_ODDS_MASK and one that does
    not — found by probing rather than transcribed, exactly as SLOT11_TICKS is."""
    found = {}
    for tick in range(0x80):
        if len(found) == 2:
            break
        pokes = _tier_pokes(case_salt(f"slot17 tick probe {tick}"), {FRAME_TICK: word(tick)})
        drawn, _counters = model_rng(harness.make_image(pokes), 0)
        found.setdefault((drawn & TYPE17_SEED_ODDS_MASK) == 0, tick)
    assert len(found) == 2, f"no frame tick separates the seeding draw: {found}"
    return found


SLOT17_TICKS = _ticks_for_slot17_draw()


@pytest.mark.parametrize("seeds", [True, False], ids=["draw-permits", "draw-refuses"])
def test_slot17_seeds_five_records_when_the_y_cursor_wraps_and_the_draw_permits(seeds):
    """`andi.w #$7,d0 / bne` — a one-in-eight gate on the frame the y cursor comes back round, and
    behind it a `dbf` that takes FIVE records and numbers them WB_ACTOR_TYPE17_SEED_FIRST down."""
    what = f"{TYPE17} seeding, draw {'permits' if seeds else 'refuses'}"
    x, y = 0x0100, STAND_Y
    pokes = _type17_pokes(what, {ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                                 wb("ACTOR_TYPE17_DY_CURSOR"): word(TYPE17_DY_LAST),
                                 FRAME_TICK: word(SLOT17_TICKS[seeds])})

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    info = _run_handler(TYPE17, what, pokes, hw_seed=leaf.hw_declared(),
                        band=_handler_band(TYPE17) + merge_bands(counters))
    written = program_writes(info)
    assert _written_word(written, TYPE17_DY_CURSOR) == 0, f"{what}: the y cursor did not wrap"
    if not seeds:
        assert FIRST_HIGH_RECORD + ACTOR_TYPE not in written, f"{what}: it seeded anyway"
        return

    for index in range(ALLOC_HIGH_SLOTS):
        seed = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST + index)
        if index >= TYPE17_SEEDS:
            assert seed + ACTOR_TYPE not in written, f"{what}: a sixth record was seeded"
            continue
        assert _written_word(written, seed, ACTOR_TYPE) == TYPE17_SEED_TYPE
        assert written[seed + FIELD_30] == TYPE17_SEED_FIRST - index, (
            f"{what}: the ordinals do not count DOWN from WB_ACTOR_TYPE17_SEED_FIRST")
        assert written[seed + SPEED] == TYPE17_SEED_SPEED
        assert _written_word(written, seed, HALF_WIDTH) == TYPE17_SEED_SIZE >> 16
        flags = written[seed + ACTOR_FLAGS]
        assert flags & (1 << MOVING_BIT) and flags & (1 << LAUNCHED_BIT)
        assert not flags & (1 << SUPPORTED_BIT)
        # The x/y longword is copied AFTER the drift above, so the seeds land where the drifter now is.
        assert _written_word(written, seed, ACTOR_X) == _written_word(written, ACTOR, ACTOR_X)


def test_slot17_seeds_what_the_pool_HAS_when_it_cannot_seed_five():
    """The `dbf` closes onto the `bsr $1b8e`, so the burst is five SEPARATE lookups and a pool with
    room for fewer than five fills what it has.

    IT DOES NOT PIN THE EARLY EXIT, and nothing can: actor_alloc_slot_high is a stateless first-fit
    scan that writes nothing, so once it has refused it refuses for the rest of the frame — leaving
    the loop and running it out both write the same bytes. That equivalence is argued in
    ../STATUS.md rather than asserted; what this case holds is that the records which DO fit are
    filled, and numbered from the top."""
    what = f"{TYPE17} seeding into a nearly full pool"
    room = 2
    pokes = _type17_pokes(what, {wb("ACTOR_TYPE17_DY_CURSOR"): word(TYPE17_DY_LAST),
                                 FRAME_TICK: word(SLOT17_TICKS[True])})
    for high in range(ALLOC_HIGH_FIRST + room, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        pokes[_record(TABLE_DEFAULT, high) + ACTOR_X] = word(OCCUPIED_X)

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    written = program_writes(_run_handler(TYPE17, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE17) + merge_bands(counters)))
    for index in range(room):
        seed = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST + index)
        assert _written_word(written, seed, ACTOR_TYPE) == TYPE17_SEED_TYPE
        assert written[seed + FIELD_30] == TYPE17_SEED_FIRST - index


def test_slot17_never_touches_the_collision_map_or_the_settle():
    """The second handler in the family with no `bsr $1334` and no probe on EITHER arm: a solid row
    right under it changes nothing, and its y follows the hover table straight through."""
    what = f"{TYPE17} over solid ground"
    y = STAND_Y
    pokes = _type17_pokes(what, {ACTOR + ACTOR_Y: word(y)})
    _block_the_walk(pokes)

    written = program_writes(_run_handler(TYPE17, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + _image_word(TYPE17_DY)) & 0xffff
    assert ACTOR + SPEED not in written, f"{what}: something settled the record"


# --- slot 18 ($3c84): the charger ------------------------------------------------------------------
@pytest.mark.parametrize("side,frames,step", [
    (0, TYPE18_WALK_RIGHT, TYPE18_WALK_STEP),
    (1 << SIDE_BIT, TYPE18_WALK_LEFT, -TYPE18_WALK_STEP),
], ids=["facing-right", "facing-left"])
def test_slot18_walks_while_its_countdown_runs(side, frames, step):
    what = f"{TYPE18} walking side={side:#04x}"
    x, timer = 0x0100, 7
    pokes = _family36_pokes(what, 18, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]),
                                       ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)])})

    written = program_writes(_run_handler(TYPE18, what, pokes))
    assert written[ACTOR + FIELD_30] == timer - 1
    assert _written_word(written, ACTOR, ACTOR_X) == x + step
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames)


def test_slot18_charges_and_SAVES_its_flag_byte_before_the_launch_rewrites_it():
    """WB_ACTOR_FIELD_29 takes 8(a0) as it stands, and only then does actor_set_side_flag and
    actor_start_motion_at_speed rewrite the byte — which is what makes the landing arm a RESTORE.
    The record is seeded facing the way the followed record is NOT, so the saved byte and the
    launched one differ and a port that saved the wrong one is red."""
    what = f"{TYPE18} charging"
    entry_flags = (1 << SIDE_BIT) | (1 << SUPPORTED_BIT)
    pokes = _family36_pokes(what, 18, {
        ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([0]),
        ACTOR + ACTOR_FLAGS: bytes([entry_flags]),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0600)})

    written = program_writes(_run_handler(TYPE18, what, pokes))
    assert written[ACTOR + FIELD_29] == entry_flags, (
        f"{what}: the byte saved is not the one the record arrived with")
    assert written[ACTOR + FIELD_31] == TYPE18_CHARGING
    flags = written[ACTOR + ACTOR_FLAGS]
    assert not flags & (1 << SIDE_BIT), f"{what}: it did not face the followed record"
    assert flags & (1 << MOVING_BIT) and not flags & (1 << SUPPORTED_BIT)
    assert written[ACTOR + SPEED] == TYPE18_HOP_SPEED
    minion = FIRST_HIGH_RECORD
    assert _written_word(written, minion, ACTOR_TYPE) == TYPE18_MINION_TYPE
    assert written[minion + ACTOR_FLAGS] == flags


def test_slot18_restores_the_saved_byte_and_turns_when_the_charge_LANDS():
    """`move.b 29(a0),8(a0) / bchg #3,8(a0)` — the whole flag byte comes back and the record then
    turns round, so what it walks off with is the SAVED facing inverted and not the charge's."""
    what = f"{TYPE18} landing"
    saved = (1 << SIDE_BIT) | (1 << SUPPORTED_BIT)
    pokes = _family36_pokes(what, 18, {
        ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([TYPE18_CHARGING]),
        ACTOR + FIELD_29: bytes([saved]), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE18, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] == saved & ~(1 << SIDE_BIT), (
        f"{what}: the restore did not put the saved byte back and turn it")
    assert written[ACTOR + FIELD_30] == TYPE18_TURN_FRAMES
    assert written[ACTOR + FIELD_31] == 0
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the landing frame animated"


def test_slot18_mid_charge_and_airborne_ANIMATES_and_nothing_else():
    """`beq.w $3d86` past the restore: a record still in the air runs the frame table alone — no
    step, no turn, no restore, so the charge's own flag byte stays written."""
    what = f"{TYPE18} airborne mid-charge"
    pokes = _family36_pokes(what, 18, {
        ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([TYPE18_CHARGING]),
        ACTOR + FIELD_29: bytes([0xff]), ACTOR + ACTOR_X: word(0x0100),
        ACTOR + ACTOR_FLAGS: bytes([0])}, ground=False)

    written = program_writes(_run_handler(TYPE18, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE18_WALK_RIGHT)
    assert ACTOR + ACTOR_X not in written, f"{what}: it stepped"
    assert ACTOR + FIELD_31 not in written, f"{what}: the latch was touched in the air"
    assert ACTOR + FIELD_30 not in written, f"{what}: the countdown was reloaded in the air"


@pytest.mark.parametrize("defeated", [False, True], ids=["not-defeated", "defeated"])
def test_slot18s_hurt_arm_retreats_only_while_the_mark_is_DOWN(defeated):
    """`btst #3,9(a0) / bne` skips the retreat for a record already defeated — the shape slot 10 has
    — and BOTH arms then publish out of the list the same `btst #3,8(a0)` chooses."""
    what = f"{TYPE18} hurt, {'defeated' if defeated else 'alive'}"
    x = 0x0100
    flags2 = (1 << FLAGS2_BIT_0) | ((1 << DEFEATED_BIT) if defeated else 0)
    pokes = _band_slot_pokes(what, 18, {ACTOR + FLAGS2: bytes([flags2]),
                                        ACTOR + ACTOR_X: word(x),
                                        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_band_handler(18, what, pokes, "defeat"))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE18_HURT_RIGHT)
    if defeated:
        assert ACTOR + ACTOR_X not in written, f"{what}: a defeated record retreated"
    else:
        assert _written_word(written, ACTOR, ACTOR_X) == x - TYPE18_HURT_STEP, (
            f"{what}: the retreat is not AWAY from the followed record")


# --- slot 19 ($3e8c): the glider that turns into an attacker ---------------------------------------
TYPE19_DRIFT_LAST = TYPE19_DRIFT_MASK - (ANIM_FRAME_BYTES - 1)
TYPE19_FRAME_LAST = TYPE19_FRAME_MASK - (ANIM_FRAME_BYTES - 1)


# $40 is the sweep's row again: under it a $7f mask stores $42 and a $3f one $02, where every other
# cursor here answers the same under both (`slot19/drift-mask`).
@pytest.mark.parametrize("cursor", [0, 0x10, 0x40, TYPE19_DRIFT_LAST],
                         ids=lambda v: f"cursor{v:#04x}")
def test_slot19_glides_on_its_own_drift_table_with_one_fixed_frame(cursor):
    """The glide publishes WB_ACTOR_TYPE19_GLIDE_SPRITE on every frame and narrows the box to
    WB_ACTOR_TYPE19_GLIDE_HEIGHT, and the x moves by one SIGNED word of the drift table per frame.
    The wrap latches the record into its attack phase FOR GOOD."""
    what = f"{TYPE19} gliding at {cursor:#04x}"
    x = 0x0100
    pokes = _family36_pokes(what, 19, {ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([cursor]),
                                       ACTOR + FIELD_31: bytes([0])})

    written = program_writes(_run_handler(TYPE19, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == TYPE19_GLIDE_SPRITE
    assert _written_word(written, ACTOR, SIZE_SECOND) == TYPE19_GLIDE_HEIGHT
    assert _written_word(written, ACTOR, ACTOR_X) == (x + _image_word(TYPE19_DRIFT + cursor)) & 0xffff
    stepped = (cursor + ANIM_FRAME_BYTES) & TYPE19_DRIFT_MASK
    assert written[ACTOR + FIELD_30] == stepped
    if stepped == 0:
        assert written[ACTOR + FIELD_31] == TYPE19_PHASE2, f"{what}: the wrap did not latch"
    else:
        assert ACTOR + FIELD_31 not in written, f"{what}: it latched early"


@pytest.mark.parametrize("followed_x,side,frames", [
    (0x0600, 0, TYPE19_FRAMES_RIGHT),
    (0x0010, 1 << SIDE_BIT, TYPE19_FRAMES_LEFT),
], ids=["followed-right", "followed-left"])
def test_slot19_attacks_facing_the_followed_record_with_the_box_doubled(followed_x, side, frames):
    what = f"{TYPE19} attacking, followed at {followed_x:#06x}"
    pokes = _family36_pokes(what, 19, {ACTOR + FIELD_31: bytes([TYPE19_PHASE2]),
                                       ACTOR + FIELD_18: bytes([0]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(followed_x)})

    written = program_writes(_run_handler(TYPE19, what, pokes))
    assert _written_word(written, ACTOR, SIZE_SECOND) == TYPE19_ATTACK_HEIGHT
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT) == side
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames)
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


def test_slot19_drops_a_shot_on_ONE_cursor_value_and_publishes_the_NEW_RECORD_as_its_frame():
    """THE ORIGINAL'S OWN DEFECT, reproduced rather than repaired. `bsr $1b8e` returns the record in
    a1 — the register the frame table was `lea`d into two instructions earlier — and the publish
    below the two arms' join reads through it. So the sprite published on the firing frame is the
    word at offset WB_ACTOR_TYPE19_SHOT_CURSOR of the record just allocated, which the spawn does
    not write, and the case asserts that word rather than a frame from either table."""
    what = f"{TYPE19} firing"
    x, y = 0x0100, STAND_Y
    pokes = _family36_pokes(what, 19, {
        ACTOR + FIELD_31: bytes([TYPE19_PHASE2]), ACTOR + FIELD_18: bytes([TYPE19_SHOT_CURSOR]),
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0600)})
    image = harness.make_image(pokes)
    garbage = int.from_bytes(image[FIRST_HIGH_RECORD + TYPE19_SHOT_CURSOR:
                                   FIRST_HIGH_RECORD + TYPE19_SHOT_CURSOR + WORD_BYTES], "big")

    written = program_writes(_run_handler(TYPE19, what, pokes))
    shot = FIRST_HIGH_RECORD
    assert _written_word(written, shot, ACTOR_TYPE) == TYPE19_SHOT_TYPE
    assert _written_word(written, shot, ACTOR_Y) == y - TYPE19_SHOT_RISE
    assert _written_word(written, shot, ACTOR_X) == (x + TYPE19_SHOT_DX_RIGHT) & 0xffff
    assert _written_word(written, shot, HALF_WIDTH) == TYPE19_SHOT_SIZE >> 16
    assert not written[shot + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)
    assert garbage != _image_word(TYPE19_FRAMES_RIGHT + TYPE19_SHOT_CURSOR), (
        f"{what}: the keyed word happens to equal the table's, so this case would prove nothing")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == garbage, (
        f"{what}: the frame published is a TABLE entry, so a1 was not the allocator's answer")


def test_slot19_publishes_from_ADDRESS_14_when_the_pool_refuses_its_shot():
    """The other half of the same defect: a refused allocation leaves a1 at ZERO and the `beq` goes
    to the SAME publish, so the word read is at address WB_ACTOR_TYPE19_SHOT_CURSOR itself — inside
    the 68000 vector page, four hundred bytes below the program."""
    what = f"{TYPE19} firing into a full pool"
    pokes = _full_pool_pokes(_family36_pokes(what, 19, {
        ACTOR + FIELD_31: bytes([TYPE19_PHASE2]), ACTOR + FIELD_18: bytes([TYPE19_SHOT_CURSOR]),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0600)}))

    for table in (TYPE19_FRAMES_RIGHT, TYPE19_FRAMES_LEFT):
        assert _image_word(TYPE19_SHOT_CURSOR) != _image_word(table + TYPE19_SHOT_CURSOR), (
            f"{what}: the word at {TYPE19_SHOT_CURSOR:#04x} equals the one a bounded port would "
            f"publish out of {table:#06x}, so this case would prove nothing")

    written = program_writes(_run_handler(TYPE19, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(TYPE19_SHOT_CURSOR), (
        f"{what}: a1 was not zero, so the refused allocation published a table entry")
    assert FIRST_HIGH_RECORD + ACTOR_TYPE not in written


def test_slot19s_attack_wrap_puts_the_record_back_into_its_GLIDE():
    """`clr.b 31(a0)` on the wrap — the attack is a RUN rather than a state, and the glide's own
    wrap will latch the record back into it."""
    what = f"{TYPE19} attack wrapping"
    pokes = _family36_pokes(what, 19, {ACTOR + FIELD_31: bytes([TYPE19_PHASE2]),
                                       ACTOR + FIELD_18: bytes([TYPE19_FRAME_LAST]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(0x0600)})

    written = program_writes(_run_handler(TYPE19, what, pokes))
    assert written[ACTOR + FIELD_18] == 0
    assert written[ACTOR + FIELD_31] == 0, f"{what}: the record stayed in its attack phase"


def test_slot19_that_is_hurt_but_NOT_defeated_recovers_on_the_first_frame():
    """The only hurt arm in the family that plays no animation at all: `btst #3,9(a0) / bne /
    bclr #0,9(a0) / rts`. A record that survives its hit is live again next frame."""
    what = f"{TYPE19} hurt, not defeated"
    pokes = _family36_pokes(what, 19, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                                       ACTOR + FIELD_18: bytes([4])})

    info = _run_handler(TYPE19, what, pokes)
    _assert_writes(info, {ACTOR + FLAGS2: 0}, what)


def test_slot19s_death_animation_ALWAYS_transfers_when_it_wraps():
    """`bclr #0,9(a0) / bra.w $6bb8` — the family's SECOND unconditional transfer after slot 13's,
    and here the defeated mark is what got the record onto the arm in the first place."""
    what = f"{TYPE19} death animation wrapping"
    pokes = _band_slot_pokes(what, 19, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + FIELD_18: bytes([LAST_FRAME[ANIM32_MASK]]),
        ACTOR + TEMPLATE_SLOT: bytes([2])})

    written = program_writes(_run_band_handler(19, what, pokes, "defeat"))
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the transfer never happened")
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0)
    assert written[ACTOR + FLAGS2] & (1 << DEFEATED_BIT), (
        f"{what}: the defeated bit was cleared, which this tail does not do")


# --- THE RAW-INDEX CONVENTION, AT ALL THIRTEEN OF THIS BATCH'S CURSOR READS ------------------------
# Batch 35's defect, driven before the fact this time: every one of these reads
# `move.b <cursor>,dN` (or `move.w <global>,d0`) and INDEXES with it, and the `andi` runs afterwards
# on the value going back into the record. So the mask bounds where the cursor GOES, never where it
# came from, and a cursor above it reads past the table its own `lea` names.
#
# Each row seeds a cursor ONE WHOLE TABLE past the start — the first value the mask can never store
# and a record can hold — and requires the answer to be the word at table + RAW cursor. Every row is
# checked against the masked read first, so a row whose over-read happens to repeat the table would
# fail as a case that proves nothing rather than pass silently.
LIVE, HURT = "live", "hurt"

# THE CURSOR IS PER ROW, and five of the thirteen could not be `mask + 1`. Where a handler's two
# facing tables are CONTIGUOUS, `table + mask + 1` IS `sibling + 0` — so a row seeded one whole
# table past cannot tell "raw index on the right table" from "masked index on the SIBLING table",
# which is a composite a reader fixing the over-read by masking could easily produce. The five
# affected rows (15 walk, 15 hurt, 16 walk, 19 attack and 17 dx below) are seeded further on, at the
# smallest cursor that gives three different words; the guard in the case is what enforces it, so a
# row whose table moves fails rather than quietly going ambiguous again.
#
# (slot, arm, label, cursor field, table, SIBLING table or None, mask, cursor, extra seed fields)
FAMILY36_OVER_READS = (
    (14, LIVE, "walk", FIELD_18, TYPE14_WALK_RIGHT, TYPE14_WALK_LEFT, ANIM32_MASK, 0x20,
     {ACTOR + FIELD_30: bytes([7]), ACTOR + FIELD_31: bytes([5])}),
    (14, HURT, "hurt", FIELD_18, TYPE14_HURT, None, ANIM16_MASK, 0x10, {}),
    (15, LIVE, "walk", FIELD_18, TYPE15_WALK_RIGHT, TYPE15_WALK_LEFT, ANIM16_MASK, 0x20, {}),
    (15, HURT, "hurt", FIELD_18, TYPE15_HURT_RIGHT, TYPE15_HURT_LEFT, ANIM32_MASK, 0x40, {}),
    (16, LIVE, "walk", FIELD_18, TYPE16_WALK_RIGHT, TYPE16_WALK_LEFT, ANIM16_MASK, 0x50,
     {ACTOR + FIELD_30: bytes([7])}),
    (16, HURT, "hurt", FIELD_18, TYPE16_HURT_RIGHT, TYPE16_HURT_LEFT, ANIM32_MASK, 0x20, {}),
    (18, LIVE, "walk", FIELD_18, TYPE18_WALK_RIGHT, TYPE18_WALK_LEFT, ANIM32_MASK, 0x20,
     {ACTOR + FIELD_30: bytes([7])}),
    # The DEFEATED mark skips the retreat, so this row is about the publish alone.
    (18, HURT, "hurt", FIELD_18, TYPE18_HURT_RIGHT, TYPE18_HURT_LEFT, ANIM16_MASK, 0x10,
     {ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)])}),
    (19, LIVE, "attack", FIELD_18, TYPE19_FRAMES_RIGHT, TYPE19_FRAMES_LEFT, TYPE19_FRAME_MASK, 0x80,
     {ACTOR + FIELD_31: bytes([TYPE19_PHASE2])}),
    (19, HURT, "death", FIELD_18, TYPE19_DEATH, None, ANIM32_MASK, 0x20,
     {ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)])}),
)


def _assert_the_three_readings_differ(what, table, sibling, mask, cursor):
    """The row's premise, and BOTH halves of it. `raw` is what the original publishes; `masked` is
    what a mask-before-index port on the same table would; `masked_sibling` is what a port that both
    masked AND took the other facing's table would. A row where any two of the three agree cannot
    tell those implementations apart, and says so here rather than passing."""
    raw = _image_word(table + cursor)
    masked = _image_word(table + (cursor & mask))
    assert raw != masked, (
        f"{what}: the word at {table + cursor:#06x} equals the masked read at "
        f"{table + (cursor & mask):#06x}, so this row would prove nothing")
    if sibling is not None:
        masked_sibling = _image_word(sibling + (cursor & mask))
        assert raw != masked_sibling, (
            f"{what}: the word at {table + cursor:#06x} equals a MASKED read of the sibling table "
            f"at {sibling + (cursor & mask):#06x} — the two tables are contiguous, so this cursor "
            f"cannot separate a raw index from a masked one on the wrong list")
    return raw


def _over_read_pokes(what, slot, arm, field, cursor, fields):
    base = {ACTOR + field: bytes([cursor]), FOLLOWED_DEFAULT + ACTOR_X: word(0x0600)}
    if arm == HURT:
        base.setdefault(ACTOR + FLAGS2, bytes([1 << FLAGS2_BIT_0]))
    base[ACTOR + ACTOR_FLAGS] = bytes([1 << SUPPORTED_BIT])
    return _family36_pokes(what, slot, leaf.overlay(base, fields))


@pytest.mark.parametrize("slot,arm,label,field,table,sibling,mask,cursor,fields",
                         FAMILY36_OVER_READS, ids=lambda v: v if isinstance(v, str) else "")
def test_every_frame_read_this_batch_adds_indexes_on_the_RAW_cursor(slot, arm, label, field, table,
                                                                    sibling, mask, cursor, fields):
    """The publish sites. A record holding a cursor past the mask publishes the word the RAW byte
    names — for slot 14's hurt arm the first opcode word of actor_behavior_type15, for slot 19's
    death arm the first of slot 20's, and for slot 16's walk the first of slot 17's — and the cursor
    it stores is still masked."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} {label} over-read"
    over = _assert_the_three_readings_differ(what, table, sibling, mask, cursor)
    pokes = _over_read_pokes(what, slot, arm, field, cursor, fields)

    written = program_writes(_run_handler(name, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == over, (
        f"{what}: the frame published is not the word the RAW cursor names, so the index was bounded")
    assert written[ACTOR + field] == (cursor + ANIM_FRAME_BYTES) & mask, (
        f"{what}: the STORE was not masked, which is the other half of the asymmetry")


# ...and the three reads whose answer is ADDED TO A COORDINATE rather than published, where the same
# over-read moves the record instead of drawing it. Slot 17's y cursor at $40 reaches
# actor_behavior_type18's own entry opcode ($0828) and adds 2,088 pixels to the y.
# The x table's neighbour is the y one, so `dx` needs the same treatment and a cursor of $100 — it
# is a WORD global rather than a record byte, so the value fits.
FAMILY36_COORDINATE_OVER_READS = (
    (17, "dx", ACTOR_X, TYPE17_DX, TYPE17_DY, TYPE17_DX_MASK, 0x100),
    (17, "dy", ACTOR_Y, TYPE17_DY, TYPE17_DX, TYPE17_DY_MASK, 0x40),
    (19, "drift", ACTOR_X, TYPE19_DRIFT, None, TYPE19_DRIFT_MASK, 0x80),
)


@pytest.mark.parametrize("slot,axis,field,table,sibling,mask,cursor",
                         FAMILY36_COORDINATE_OVER_READS,
                         ids=lambda v: v if isinstance(v, str) else "")
def test_every_drift_read_this_batch_adds_indexes_on_the_RAW_cursor(slot, axis, field, table,
                                                                    sibling, mask, cursor):
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} {axis} over-read"
    over = _assert_the_three_readings_differ(what, table, sibling, mask, cursor)
    start = 0x0100 if field == ACTOR_X else STAND_Y

    if slot == 17:
        which = wb(f"ACTOR_TYPE17_D{axis[1].upper()}_CURSOR")
        other = (wb("ACTOR_TYPE17_DY_CURSOR") if axis == "dx" else wb("ACTOR_TYPE17_DX_CURSOR"))
        pokes = _type17_pokes(what, {ACTOR + field: word(start), which: word(cursor),
                                     other: word(0)})
        stored_at, stored_is_word = which, True
    else:
        pokes = _family36_pokes(what, 19, {ACTOR + field: word(start),
                                           ACTOR + FIELD_30: bytes([cursor]),
                                           ACTOR + FIELD_31: bytes([0])})
        stored_at, stored_is_word = ACTOR + FIELD_30, False

    written = program_writes(_run_handler(name, what, pokes))
    assert _written_word(written, ACTOR, field) == (start + over) & 0xffff, (
        f"{what}: the delta added is the MASKED table entry, so the index was bounded")
    stepped = (cursor + ANIM_FRAME_BYTES) & mask
    assert (_written_word(written, stored_at) if stored_is_word else written[stored_at]) == stepped


# --- the census of the things a `lea` does NOT name -------------------------------------------------
# The direct-reader census above bounds routines that name an address DIRECTLY. Three kinds of
# address in this batch have no `lea` at all, and each needs its own statement.
TYPE17_LISTS = (0x3b78, 0x3b8a, 0x3b9c, 0x3bae)
# The band this batch owns, from the image's OWN table rather than from a transcribed top: slot 20
# is the next row and its entry is where slot 19's data stops.
BAND36_LO, BAND36_HI = wb("ACTOR_BEHAVIOR_TYPE14"), _image_slot(20)

# EVERY WAY AN INSTRUCTION CAN NAME AN ADDRESS, resolved ONCE over the program and keyed by target.
# `_lea_sites` above is now derived from this rather than sweeping the image again per case, which
# is what keeps the two censuses from disagreeing about the same instruction: they had different
# tail bounds and different form coverage, and a negative proved with one and quoted from the other
# is not a proof at all.
#
# THE FORM LIST IS THE FINDING. The first draft claimed "both PC-relative `lea` forms" and swept
# only the INDEXED one — so `lea d16(PC),An`, `jsr/jmp/pea d16(PC)` and their indexed siblings, and
# every `DBcc` (always a 16-bit displacement, and a branch) were invisible. An under-reporting scan
# is exactly the failure the two cases below exist to rule out, so the scan has to be wider than the
# claim rather than narrower. `movea.l #imm` and any pointer assembled at runtime are still outside
# it, and the cases say so.
BRANCH_OPCODE_LO, BRANCH_OPCODE_HI = 0x6000, 0x6fff
DBCC_MASK, DBCC_MATCH = 0xf0f8, 0x50c8
ABS_L_OPCODES = (0x4eb9, 0x4ef9, 0x4879) + LEA_ABS_L_OPCODES_W
ABS_W_OPCODES = (0x4eb8, 0x4ef8, 0x4878) + LEA_ABS_W_OPCODES_W
PC_DISP_OPCODES = (0x4eba, 0x4efa, 0x487a) + LEA_PC_DISP_OPCODES_W
PC_INDEXED_OPCODES = (0x4ebb, 0x4efb, 0x487b) + LEA_PC_INDEXED_OPCODES_W
# The three `lea` forms alone, for the census that asks specifically about a `lea`.
LEA_FORM_OPCODES = LEA_ABS_L_OPCODES_W + LEA_ABS_W_OPCODES_W + LEA_PC_INDEXED_OPCODES_W


def _sign_byte(value):
    return value - 0x100 if value >= 0x80 else value


def _instruction_targets():
    """{target address: [(instruction address, opcode word)]} over the PROGRAM.

    Bounded to `loader.PROGRAM_END` because everything above it is uninitialised image, and decoding
    zeros as instructions would put phantom edges into a case that asserts an exact set.
    """
    image = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    targets = {}

    def note(at, op, target):
        targets.setdefault(target & BUS_ADDR_MASK, []).append((at, op))

    for at in range(0, len(image) - LONGWORD_BYTES - WORD_BYTES, WORD_BYTES):
        op = int.from_bytes(image[at:at + WORD_BYTES], "big")
        extension = int.from_bytes(image[at + WORD_BYTES:at + 2 * WORD_BYTES], "big")
        if op & DBCC_MASK == DBCC_MATCH:
            note(at, op, at + WORD_BYTES + s16(extension))
        elif BRANCH_OPCODE_LO <= op <= BRANCH_OPCODE_HI:
            # $00 and $ff are the word and (68020) long forms' escapes, not displacements.
            displacement = op & 0xff
            if displacement == 0:
                note(at, op, at + WORD_BYTES + s16(extension))
            elif displacement != 0xff:
                note(at, op, at + WORD_BYTES + _sign_byte(displacement))
        elif op in ABS_L_OPCODES:
            note(at, op, int.from_bytes(image[at + WORD_BYTES:at + WORD_BYTES + LONGWORD_BYTES],
                                        "big"))
        elif op in ABS_W_OPCODES:
            # An abs.w operand is SIGN-EXTENDED to the full address, which is how $ffxxxx hardware
            # addresses are spelt in two bytes.
            note(at, op, s16(extension))
        elif op in PC_DISP_OPCODES:
            note(at, op, at + WORD_BYTES + s16(extension))
        elif op in PC_INDEXED_OPCODES:
            note(at, op, at + WORD_BYTES + _sign_byte(extension & 0xff))
    return targets


INSTRUCTION_TARGETS = _instruction_targets()
CONTROL_FLOW_TARGETS = {target: [at for at, _op in sites]
                        for target, sites in INSTRUCTION_TARGETS.items()}


@pytest.mark.parametrize("slot", FAMILY36_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_each_new_entry_is_reached_ONLY_through_the_dispatch_longword(slot):
    """"Reached ONLY through `jmp (a1)`" is what every plate in this tier says, and batch 31's
    hidden `jsr $6f9e.w` is why it is measured rather than assumed: no instruction anywhere in the
    image aims at these six addresses, and the only longword holding one is the dispatch table's."""
    entry = leaf.entry_of(f"actor_behavior_type{slot:02d}")
    assert entry not in CONTROL_FLOW_TARGETS, (
        f"{entry:#06x} is named by {[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}")
    holders = [at for at in _operand_sites(longword(entry)) if at % WORD_BYTES == 0]
    assert holders == [BEHAVIOR_TABLE + slot * BEHAVIOR_ENTRY], (
        f"{entry:#06x} is held as a longword at {[hex(at) for at in holders]}, not only its slot")


# TWO INSTRUCTIONS OUTSIDE THIS BAND AIM INSIDE IT, and both are in handlers this port does not
# have — so slot 17's body is NOT slot 17's alone. Recorded as a case rather than as prose because a
# later batch porting either handler has to know the code is shared before it writes a second copy.
FOREIGN_EDGES_INTO_BAND36 = {0x48b2: 0x3ae6, 0x4aa8: 0x3e2a}


def test_the_only_foreign_entrances_into_this_band_are_the_two_the_plates_name():
    """`bra.w $3ae6` at $48b2 enters slot 17's SEEDING block, and `bne.w $3e2a` at $4aa8 borrows
    slot 18's final `rts`. Nothing else in the image jumps into $35d8..$4117."""
    found = {at: target
             for target, sites in CONTROL_FLOW_TARGETS.items() if BAND36_LO <= target < BAND36_HI
             for at in sites if not BAND36_LO <= at < BAND36_HI}
    edges = ", ".join(f"{at:#06x}->{target:#06x}" for at, target in sorted(found.items()))
    assert found == FOREIGN_EDGES_INTO_BAND36, f"the foreign edges into this band are {edges}"


@pytest.mark.parametrize("addr", TYPE17_LISTS, ids=lambda v: f"{v:#06x}")
def test_slot17s_four_frame_lists_are_named_by_NO_instruction(addr):
    """They are reached by DEREFERENCE, not by an operand: WB_ACTOR_TYPE17_LIVE_LISTS and _HURT_LISTS
    are two longwords each and $3006 does `movea.l (a1),a1`. A census that only counted `lea`s would
    call these unreachable, which is exactly the inference batch 35 had to retract — so the positive
    half is stated too: each list's ADDRESS is one of the four longwords inside the two pairs."""
    image = bytes(harness.BASE_IMAGE)
    # The `lea` census is a SUBSET of the instruction one, so only the wider claim is asserted.
    assert addr not in CONTROL_FLOW_TARGETS, f"{addr:#06x} is named by an instruction after all"
    pairs = (wb("ACTOR_TYPE17_LIVE_LISTS"), wb("ACTOR_TYPE17_HURT_LISTS"))
    # A $3006 pair is a LEFT list and a RIGHT one, and the two pairs sit back to back — so the
    # longword count comes out of the gap between them rather than being written down.
    per_pair = (pairs[1] - pairs[0]) // LONGWORD_BYTES
    held = [pair + entry * LONGWORD_BYTES
            for pair in pairs for entry in range(per_pair)
            if int.from_bytes(image[pair + entry * LONGWORD_BYTES:
                                    pair + (entry + 1) * LONGWORD_BYTES], "big") == addr]
    assert len(held) == 1, f"{addr:#06x} is held by {len(held)} of the two pairs' longwords, not one"


@pytest.mark.parametrize("name", ["ACTOR_TYPE17_DX_CURSOR", "ACTOR_TYPE17_DY_CURSOR"])
def test_slot17s_global_cursors_have_exactly_two_absolute_sites_each(name):
    """One `move.w <abs>.l,d0` and one `move.w d0,<abs>.l`, both inside slot 17 — which is what says
    the pair is this handler's private state and that nothing else in the image steers the drift."""
    addr = wb(name)
    image = bytes(harness.BASE_IMAGE)
    sites = sorted(at - WORD_BYTES for at in _operand_sites(longword(addr))
                   if at % WORD_BYTES == 0
                   and image[at - WORD_BYTES:at] in (leaf.move_w_abs_l_dn(D0, 0)[:WORD_BYTES],
                                                     move_w_dn_abs_l(D0, 0)[:WORD_BYTES]))
    assert len(sites) == 2, f"{name} has {len(sites)} absolute sites: {[hex(at) for at in sites]}"
    assert all(wb("ACTOR_BEHAVIOR_TYPE17") <= at < wb("ACTOR_BEHAVIOR_TYPE18") for at in sites), (
        f"{name} is read or written from outside slot 17: {[hex(at) for at in sites]}")


# --- three holes the mutation sweep found, closed ---------------------------------------------------
@pytest.mark.parametrize("followed_x,side", [(0x0010, 1 << SIDE_BIT), (0x0600, 0)],
                         ids=["followed-left", "followed-right"])
def test_slot17_faces_the_followed_record_before_it_animates(followed_x, side):
    """`bsr $67c2` opens the live arm, and $3006 then picks its list off the flag that call wrote.
    THE SWEEP FOUND THIS UNPINNED: every earlier slot-17 seed left the record already facing the way
    actor_set_side_flag would leave it, so dropping the call changed nothing. Each row here seeds
    the OPPOSITE flag to what the call writes."""
    what = f"{TYPE17} facing {followed_x:#06x}"
    lists = wb("ACTOR_TYPE17_LIVE_LISTS")
    frames = _image_long(lists if side else lists + LONGWORD_BYTES)
    pokes = _type17_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([side ^ (1 << SIDE_BIT)]),
                                 FOLLOWED_DEFAULT + ACTOR_X: word(followed_x)})

    written = program_writes(_run_handler(TYPE17, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT) == side, (
        f"{what}: the side flag is not the one actor_set_side_flag writes")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames), (
        f"{what}: the list published is the other side's")


# `move.b #n,d7` writes the LOW BYTE of the register actor_fall_and_settle handed back, and the
# settle's EARLY EXIT is what makes the rest of it drivable: a record already MOVING is returned
# from untouched, so what comes back is the handler's own entry d7 — the followed record's SPRITE
# word, which `_walk_pokes_for` states. With that word's low byte above zero the left arm steps
# `(sprite & ~0xff) | n` pixels instead of n, and the right arm (a `move.w`) steps n either way.
#
# THE SWEEP FOUND THIS UNPINNED for the shared helper. Slot 3 spells the same instructions in its
# own body and has had a case since batch 33
# (`test_slot03s_left_step_carries_the_settles_leftover_high_byte`); slots 6, 14, 18 and 25 reach it
# through `walk_and_toggle`, and none of the three had ever been driven with a high byte in that
# register — so a mutant that widened the left arm to a whole word survived.
WALK_ARM_SLOTS = {6: wb("ACTOR_TYPE06_WALK_STEP"), 14: TYPE14_WALK_STEP, 18: TYPE18_WALK_STEP,
                  25: wb("ACTOR_TYPE25_WALK_STEP")}
SETTLE_SPAN_HIGH_SPRITE = 0x0300     # a followed-record sprite whose LOW BYTE's top half is set


@pytest.mark.parametrize("slot", sorted(WALK_ARM_SLOTS), ids=lambda v: f"slot{v:02d}")
def test_the_left_walk_arm_takes_only_the_LOW_BYTE_of_the_settles_register(slot):
    name = f"actor_behavior_type{slot:02d}"
    step = WALK_ARM_SLOTS[slot]
    what = f"{name} left walk over a live register"
    x = 0x0100
    pokes = _family36_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([7]), ACTOR + FIELD_31: bytes([5]),
        ACTOR + SPEED: bytes([1]),
        ACTOR + ACTOR_FLAGS: bytes([(1 << SIDE_BIT) | (1 << MOVING_BIT)]),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(SETTLE_SPAN_HIGH_SPRITE)})

    written = program_writes(_run_handler(name, what, pokes))
    # The probe is `x - 14(a0) - d7`; a step this size takes it NEGATIVE, and $10a2 parks the record
    # at its own half-width. A step of `step` alone would leave it at x - step.
    assert _written_word(written, ACTOR, ACTOR_X) == _image_half_width(pokes), (
        f"{what}: the step was {step} pixels, so only the byte the arm writes reached the probe")


# --- batch 37: dispatch rows 20..27, and the family CLOSES ----------------------------------------
TYPE20_HOP_RELOAD = wb("ACTOR_TYPE20_HOP_RELOAD")
TYPE20_HOP_RNG_BIT = wb("ACTOR_TYPE20_HOP_RNG_BIT")
TYPE20_HOP_SPEED = wb("ACTOR_TYPE20_HOP_SPEED")
TYPE20_WALK_STEP = wb("ACTOR_TYPE20_WALK_STEP")
TYPE21_REACH = wb("ACTOR_TYPE21_REACH")
TYPE21_SHOT_ODDS_MASK = wb("ACTOR_TYPE21_SHOT_ODDS_MASK")
TYPE21_AIM_ROW = wb("ACTOR_TYPE21_AIM_ROW")
TYPE22_RELOAD = wb("ACTOR_TYPE22_RELOAD")
TYPE23_STEAL_MAX = wb("ACTOR_TYPE23_STEAL_MAX")
AIM_TABLE = wb("ACTOR_AIM_TABLE")
AIM_ROW_BYTES = wb("ACTOR_AIM_ROW_BYTES")


def _family37_pokes(what, slot, fields=None, ground=True):
    """`_walk_pokes_for` with WB_TILE_33_MODE stated, because slots 22 and 26 reach the player gate
    through the very `gated_hurt_frame` slots 9 and 12 do — batch 35's seed under this batch's
    name, and it adds nothing else."""
    base = {TILE_33_MODE: word(TILE_33_MODE_SET)}
    return _walk_pokes_for(what, slot, leaf.overlay(base, fields or {}), ground=ground)


@pytest.mark.parametrize("slot", FAMILY37_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family37_spawn_gate_takes_the_whole_frame(slot):
    """`btst #2,9(a0) / bne.w $698a` — the same four instructions the seventeen handlers before
    these open with, and the same consequence."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} spawning"
    cursor = 4
    pokes = _monster_pokes(what, slot, {ACTOR + FLAGS2: bytes([1 << SPAWNED_BIT]),
                                        ACTOR + FIELD_18: bytes([cursor])})

    info = _run_handler(name, what, pokes)
    expected = {ACTOR + FIELD_18: cursor + ANIM_FRAME_BYTES}
    _put(expected, ACTOR + ACTOR_SPRITE, _image_word(SPAWN_ANIM_FRAMES + cursor))
    _assert_writes(info, expected, what)


# WHICH of the eight faces the followed record on the struck arm, and WHICH TEST struck decides it
# for FOUR of them — where through batch 36 only slots 18 and 19 split. Read off the bytes: $414a,
# $432e, $4952 and $4c90 are `bsr $67c2` reached ONLY from the overlap-point branch, $44fc, $488c
# and $4b5e sit BELOW both writes on the shared join, and slot 23 has no such instruction at all.
FAMILY37_STRUCK_FACES = {
    # slot: (faces after a SHOT hit, faces after an overlap-POINT hit)
    20: (False, True), 21: (False, True), 22: (True, True), 23: (False, False),
    24: (True, True), 25: (False, True), 26: (True, True), 27: (False, True),
}


@pytest.mark.parametrize("by_point", [False, True], ids=["struck-by-shot", "struck-by-point"])
@pytest.mark.parametrize("slot", FAMILY37_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family37_struck_arm_faces_on_the_arm_the_bytes_say(slot, by_point):
    """THE SPLIT IS NO LONGER TWO HANDLERS' PECULIARITY. Four of these eight call actor_set_side_flag
    on the overlap-POINT arm alone, three on both arms and one on neither — so a port that faced on
    both everywhere would be wrong at half the block, and one that faced on neither at the other
    half."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} struck by {'the overlap point' if by_point else 'the flash'}"
    fields = {ACTOR + FIELD_18: bytes([4]), ACTOR + TEMPLATE_SLOT: bytes([2]),
              ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}
    if by_point:
        pokes = _point_strike_pokes(what, slot, fields)
    else:
        pokes = _band_slot_pokes(what, slot, leaf.overlay(
            {FLASH_TIMER: word(1), FOLLOWED_DEFAULT + ACTOR_X: word(0x0100 - 1)}, fields))

    info = _run_band_handler(slot, what, pokes, "damage-template")
    written = program_writes(info)
    assert written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), f"{what}: the hurt animation was not entered"
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the animation cursor was not zeroed"
    faced = bool(written.get(ACTOR + ACTOR_FLAGS, 0) & (1 << SIDE_BIT))
    expected = FAMILY37_STRUCK_FACES[slot][by_point]
    assert faced == expected, (
        f"{what}: the side flag {'was not' if expected else 'was'} raised, against the "
        f"`bsr $67c2` the bytes {'do' if expected else 'do not'} place on this arm")


# Which of the eight FLIP the side flag between $5c6e's body bit and the tail jump into $69fe.
FAMILY37_BODY_ARM_FLIPS = {20: False, 21: True, 22: False, 23: False,
                           24: False, 25: True, 26: False, 27: False}


@pytest.mark.parametrize("slot", FAMILY37_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_family37_body_arm_flips_the_facing_only_where_the_bchg_is(slot):
    """`bchg #3,8(a0) / bra.w $69fe` — slots 21 and 25 turn the monster round as it deals damage,
    the other six do not. Slot 23's arm ROBS first, which is why its purse is seeded empty here: the
    theft is the case below, and this one is about the facing alone."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} touching the followed record"
    side = 1 << SIDE_BIT
    pokes = _band_slot_pokes(what, slot, {
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)]),
        BCD_COUNTER: word(0),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0100), FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0x0100)})

    info = _run_handler(name, what, pokes, band=_foreign_band(harness.make_image(pokes), {},
                                                              "damage-followed"))
    written = program_writes(info)
    assert written[FOLLOWED_DEFAULT + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the followed record was not damaged, so this seed never reached the body arm")
    flipped = not (written.get(ACTOR + ACTOR_FLAGS, side) & (1 << SIDE_BIT))
    assert flipped == FAMILY37_BODY_ARM_FLIPS[slot], (
        f"{what}: the facing {'did not flip' if FAMILY37_BODY_ARM_FLIPS[slot] else 'flipped'}, "
        f"against the `bchg` the bytes {'do' if FAMILY37_BODY_ARM_FLIPS[slot] else 'do not'} hold")


# WHERE EACH HURT ARM WRAPS. Every one of the eight spells batch 35's clear-first tail except slot
# 23, which is slot 4's `bclr #0 / bclr #3 / bne` and CLEARS the defeated bit — it has its own rows
# among the $2462 band's. The four that animate through $3006 have no mask of their own: their
# lists are eight frames and a terminator, so the wrapping cursor is an eight-word table's.
FAMILY37_HURT = {
    20: (wb("ACTOR_TYPE20_HURT_RIGHT"), ANIM32_MASK),
    21: (wb("ACTOR_TYPE21_HURT_RIGHT"), ANIM16_MASK),
    22: (None, ANIM16_MASK),
    24: (None, ANIM16_MASK),
    25: (wb("ACTOR_TYPE25_HURT_RIGHT"), ANIM16_MASK),
    26: (None, ANIM16_MASK),
    27: (wb("ACTOR_TYPE27_HURT_RIGHT"), ANIM32_MASK),
}
FAMILY37_HURT_WRAPPERS = tuple(sorted(FAMILY37_HURT))


@pytest.mark.parametrize("slot", FAMILY37_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family37_hurt_animation_that_wraps_undefeated_comes_back_to_life(slot):
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, not defeated"
    cursor = LAST_FRAME[FAMILY37_HURT[slot][1]]
    pokes = _template_environment(case_salt(what), _family37_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + FIELD_18: bytes([cursor]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert not written[ACTOR + FLAGS2] & (1 << FLAGS2_BIT_0), (
        f"{what}: the record is still in its hurt animation after the wrap")
    assert all(addr < TEMPLATE_TABLE for addr in written), (
        f"{what}: something outside the actor tables was written, so the defeat ran")
    frames = FAMILY37_HURT[slot][0]
    if frames is not None:
        assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames + cursor), (
            f"{what}: the last frame is not this slot's")


@pytest.mark.parametrize("slot", FAMILY37_HURT_WRAPPERS, ids=lambda v: f"slot{v:02d}")
def test_the_family37_hurt_animation_that_wraps_DEFEATED_transfers(slot):
    """...and with the mark UP the same frame leaves for actor_defeat_and_score. Every one of these
    seven spells the CLEAR-FIRST tail, so bit 0 is down behind the transfer and the defeated bit is
    still standing — a case that only checked "the defeat ran" would pass against either order."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt animation wrapping, defeated"
    cursor = LAST_FRAME[FAMILY37_HURT[slot][1]]
    pokes = _template_environment(case_salt(what), _family37_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([(1 << FLAGS2_BIT_0) | (1 << DEFEATED_BIT)]),
        ACTOR + FIELD_18: bytes([cursor]),
        # The template slot the band's own defeat case names: it keeps actor_defeat_and_score on
        # the RETIRE exit, whose respawn draw would otherwise read the video counter.
        ACTOR + TEMPLATE_SLOT: bytes([2]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    info = _run_band_handler(slot, what, pokes, "defeat")
    written = program_writes(info)
    assert any(TEMPLATE_TABLE <= addr < TEMPLATE_TABLE + TEMPLATE_BAND_BYTES for addr in written), (
        f"{what}: the template was not touched, so the defeat never ran")
    marks = written[ACTOR + FLAGS2]
    assert not marks & (1 << FLAGS2_BIT_0), f"{what}: bit 0 was still up behind the transfer"
    assert marks & (1 << DEFEATED_BIT), (
        f"{what}: the defeated bit was CLEARED — this tail only tests it")


TYPE20, TYPE21, TYPE22, TYPE23 = (f"actor_behavior_type{slot}" for slot in (20, 21, 22, 23))
TYPE24, TYPE25, TYPE26, TYPE27 = (f"actor_behavior_type{slot}" for slot in (24, 25, 26, 27))


# --- slots 20 and 27: ONE body, twice -------------------------------------------------------------
HOPPER_FRAMES = {
    20: (wb("ACTOR_TYPE20_WALK_LEFT"), wb("ACTOR_TYPE20_WALK_RIGHT"),
         wb("ACTOR_TYPE20_HURT_LEFT"), wb("ACTOR_TYPE20_HURT_RIGHT"),
         wb("ACTOR_TYPE20_AIR_LEFT"), wb("ACTOR_TYPE20_AIR_RIGHT")),
    27: (wb("ACTOR_TYPE27_WALK_LEFT"), wb("ACTOR_TYPE27_WALK_RIGHT"),
         wb("ACTOR_TYPE27_HURT_LEFT"), wb("ACTOR_TYPE27_HURT_RIGHT"),
         wb("ACTOR_TYPE27_AIR_LEFT"), wb("ACTOR_TYPE27_AIR_RIGHT")),
}
HOPPER_SLOTS = tuple(sorted(HOPPER_FRAMES))
# What the six operands cost in BYTES: four `lea <abs>.l` longwords whose high halves are both zero
# (so two bytes each) and two `move.w #imm` words whose high bytes are both zero (one byte each).
HOPPER_OPERAND_RUNS = (2, 2, 1, 1, 2, 2)


def test_slots_20_and_27_are_the_SAME_body_with_six_operands_changed():
    """THE HEADLINE OF THIS BLOCK, as a byte count rather than as prose. Both handlers are assembled
    from ONE builder here, so the claim would be circular if it stopped there — what makes it a
    finding is that assembling slot 20's OPERANDS at slot 27's address reproduces slot 27's image
    bytes everywhere but the six operands, i.e. the two really are one routine duplicated."""
    entry27 = leaf.entry_of("actor_behavior_type27")
    as_slot20 = _asm(entry27, _hopper_pieces(*HOPPER_FRAMES[20]))
    real27 = bytes(harness.BASE_IMAGE[entry27:entry27 + len(as_slot20)])

    assert len(as_slot20) == BODY_SIZES["actor_behavior_type20"] == BODY_SIZES["actor_behavior_type27"]
    differing = [at for at in range(len(real27)) if real27[at] != as_slot20[at]]
    runs = []
    for at in differing:
        if runs and at == runs[-1][-1] + 1:
            runs[-1].append(at)
        else:
            runs.append([at])
    assert tuple(len(run) for run in runs) == HOPPER_OPERAND_RUNS, (
        f"the two bodies differ in {len(runs)} runs of {[len(r) for r in runs]} bytes, not the six "
        f"their operands account for: {[hex(entry27 + at) for at in differing]}")


def test_the_hoppers_rng_bit_is_the_one_the_tick_table_steers():
    """`TICKS_BY_RNG_BIT` is stated for WB_ACTOR_TIMER30_RNG_BIT and used below for the hopper's own
    veto. The two ticks separate the bit's values only because the two constants are EQUAL, and
    nothing else says so — batch 35 shipped exactly this gap for the random hop."""
    assert TYPE20_HOP_RNG_BIT == TIMER30_RNG_BIT


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("followed_x,side,step", [(0x0010, 1 << SIDE_BIT, -TYPE20_WALK_STEP),
                                                 (0x0600, 0, TYPE20_WALK_STEP)],
                         ids=["followed-left", "followed-right"])
def test_the_hopper_walks_while_its_countdown_runs(slot, followed_x, side, step):
    """A supported record with the countdown above zero: `subq.b #1,30(a0)` alone, a two-pixel step
    toward the followed record, and the walk list the facing names.

    THE FACING IS THE CALL'S, not the seed's: `bsr $67c2` runs above the countdown on every
    supported frame, so the followed record's position is what steers both — which is why these two
    rows move the followed record rather than poking the flag."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} walking toward {followed_x:#06x}"
    x, timer = 0x0100, 7
    walk_left, walk_right = HOPPER_FRAMES[slot][0], HOPPER_FRAMES[slot][1]
    pokes = _family37_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([timer]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x),
        ACTOR + ACTOR_FLAGS: bytes([(1 << SIDE_BIT) ^ side | (1 << SUPPORTED_BIT)])})

    written = program_writes(_run_handler(name, what, pokes))
    assert written[ACTOR + FIELD_30] == timer - 1, f"{what}: the countdown did not tick"
    assert _written_word(written, ACTOR, ACTOR_X) == x + step, f"{what}: the step was not {step}"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        walk_left if side else walk_right), f"{what}: the wrong walk list"
    assert written[ACTOR + FIELD_18] == ANIM_FRAME_BYTES


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("bit,tick", sorted(TICKS_BY_RNG_BIT.items()),
                         ids=["draw-permits", "draw-vetoes"])
def test_the_hopper_reloads_on_the_frame_its_countdown_goes_NEGATIVE(slot, bit, tick):
    """`subq.b #1,30(a0) / bpl` reads the SIGN of what the decrement left, so a byte of zero — not
    of one — is what reaches the reload. The draw then decides: bit CLEAR launches (and the launch
    is a TAIL jump, so nothing steps and nothing animates), bit SET falls through into the walk."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} countdown expiring, draw bit {bit}"
    x = 0x0100
    pokes = _family37_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_30: bytes([0]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]), FRAME_TICK: word(tick)})

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    written = program_writes(_run_handler(name, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(name) + merge_bands(counters)))
    assert written[ACTOR + FIELD_30] == TYPE20_HOP_RELOAD, f"{what}: the countdown was not reloaded"
    if bit == 0:
        assert written[ACTOR + SPEED] == TYPE20_HOP_SPEED, f"{what}: the hop did not launch"
        assert not written[ACTOR + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)
        assert ACTOR + ACTOR_X not in written, f"{what}: the launch frame stepped as well"
        assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the launch frame animated as well"
    else:
        # The settle and the ascent write WB_ACTOR_SPEED on every frame, so what separates the two
        # arms is the SUPPORTED bit the launch clears — and the step the launch's tail jumps over.
        assert written.get(ACTOR + ACTOR_FLAGS, 1 << SUPPORTED_BIT) & (1 << SUPPORTED_BIT), (
            f"{what}: the veto did not stop the launch")
        assert _written_word(written, ACTOR, ACTOR_X) == x + TYPE20_WALK_STEP


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("side", [1 << SIDE_BIT, 0], ids=["facing-left", "facing-right"])
def test_the_hopper_that_is_AIRBORNE_publishes_one_sprite_and_animates_nothing(slot, side):
    """`move.w #imm,6(a0)` instead of a table read: an unsupported record shows one frame for the
    whole flight and its cursor is never touched."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} airborne {side:#04x}"
    air_left, air_right = HOPPER_FRAMES[slot][4], HOPPER_FRAMES[slot][5]
    pokes = _family37_pokes(what, slot, {
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << MOVING_BIT)]),
        ACTOR + FIELD_18: bytes([4])}, ground=False)

    written = program_writes(_run_handler(name, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == (air_left if side else air_right)
    assert ACTOR + FIELD_18 not in written, f"{what}: the airborne arm stepped the frame cursor"
    assert ACTOR + FIELD_30 not in written, f"{what}: the airborne arm ticked the countdown"


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_hopper_hurt_wrap_LATCHES_its_countdown_before_the_two_marks(slot):
    """`st 30(a0)` above the `bclr`/`btst` pair — the only hurt tail in the family with a write of
    its own — so a recovered record's next live frame finds the countdown already negative."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt wrap latching"
    pokes = _template_environment(case_salt(what), _family37_pokes(what, slot, {
        ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + FIELD_30: bytes([0x10]),
        ACTOR + FIELD_18: bytes([LAST_FRAME[ANIM32_MASK]]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    written = program_writes(_run_band_handler(slot, what, pokes, "defeat"))
    assert written[ACTOR + FIELD_30] == ST_BYTE, f"{what}: the countdown was not latched"


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
@pytest.mark.parametrize("defeated", [False, True], ids=["undefeated", "defeated"])
def test_the_hopper_hurt_arm_retreats_unless_the_record_is_marked(slot, defeated):
    """`btst #3,9(a0) / bne` over the retreat: a dying record stands still while it plays out its
    animation, and an ordinary hurt one backs away WB_ACTOR_TYPE20_HURT_STEP pixels."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} hurt {'defeated' if defeated else 'undefeated'}"
    x, marks = 0x0100, (1 << FLAGS2_BIT_0) | ((1 << DEFEATED_BIT) if defeated else 0)
    # `bsr $67c2` runs above the retreat here as well, so the followed record to the LEFT is what
    # makes the retreat walk RIGHT — seeding the flag alone would be overwritten.
    pokes = _family37_pokes(what, slot, {
        ACTOR + ACTOR_X: word(x), ACTOR + FLAGS2: bytes([marks]),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0010),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(name, what, pokes))
    if defeated:
        assert ACTOR + ACTOR_X not in written, f"{what}: a marked record still recoiled"
    else:
        assert _written_word(written, ACTOR, ACTOR_X) == x + wb("ACTOR_TYPE20_HURT_STEP")


# --- slot 21: the sentry that aims ----------------------------------------------------------------
def _sub_w_n_and_v(minuend, subtrahend):
    """The N and V a `sub.w <subtrahend>,<minuend>` leaves, from the 68000's own flag definitions —
    NOT from a comparison of the two operands, which is the shortcut whose equivalence is the thing
    under test. V is set when the operands differ in sign AND the result takes the subtrahend's."""
    result = (minuend - subtrahend) & 0xffff
    n = (result >> 15) & 1
    v = (((minuend ^ subtrahend) & (minuend ^ result)) >> 15) & 1
    return n, v


def _aim_velocity(image, from_x, from_y, to_x, to_y, row):
    """$6528, transcribed INDEPENDENTLY of src/actor.c so the two can disagree.

    THE TWO SIGN TESTS ARE DIFFERENT TESTS. `sub.w d0,d2 / bge.s` at $653e reads N^V, so it is the
    exact signed comparison of the two operands; `tst.w d3 / bge.s` at $6548 clears V first and so
    reads the SIGN OF THE WRAPPED DIFFERENCE. This model spells the first from the flags and the
    second from the sign, which is what lets it disagree with a port that spells both alike.

    The `roxl.w #1,d2` at $6564 reads the X flag the `asr.w #1,d2` above it left — an exact
    halve-and-restore — unless the `addq.w #1,d4` between them ran, which overwrites X with its own
    (always zero) carry and so drops the low bit.
    """
    code = wb("ACTOR_AIM_CODE_BASE")
    dx = s16((to_x - from_x) & 0xffff)
    dy = s16((to_y - from_y) & 0xffff)
    n, v = _sub_w_n_and_v(to_x & 0xffff, from_x & 0xffff)
    if n ^ v:
        dx, code = s16(-dx & 0xffff), code ^ wb("ACTOR_AIM_CODE_DX_EOR")
    if dy < 0:
        dy, code = -dy, code ^ wb("ACTOR_AIM_CODE_DY_EOR")
        dx, dy = dy, dx
    if not code & (1 << wb("ACTOR_AIM_CODE_SWAP_BIT")):
        dx, dy = dy, dx

    extend = dx & 1
    dx >>= 1
    if dy < dx:
        code, extend = code + 1, 0
    dx = s16(((dx << 1) | extend) & 0xffff)
    if dy < dx:
        code += 1
    dx = s16((dx << 1) & 0xffff)
    if dy < dx:
        code += 1
    pair = AIM_TABLE + row * AIM_ROW_BYTES + code * wb("ACTOR_AIM_PAIR_BYTES")
    return leaf.s8(image[pair]), leaf.s8(image[pair + 1])


# --- $6528 driven DIRECTLY, for the states slot 21's reach gate cannot produce -------------------
# WB_ACTOR_TYPE21_REACH bounds |to_x - from_x| to $96, so no frame of slot 21 can make the x
# subtraction OVERFLOW — and overflow is the only state in which N^V and the sign of the wrapped
# result disagree. The leaf is exported, so the pair below enters it at its own address with the
# registers the original takes, which is the only surface that reaches those states at all.
_AIM_FN = leaf.bind("actor_aim_velocity",
                    leaf.IMAGE_ARG + [ctypes.c_uint32] * 5
                    + [ctypes.POINTER(ctypes.c_int16)] * 2)
AIM_INSN_CAP = AIM_VELOCITY_INSNS + leaf.RUNNER_SENTINEL_INSN


def _aim_glue(from_x, from_y, to_x, to_y, row, dx, dy):
    """$6528 returns TWO registers, so the reconstruction hands both back through pointers."""
    return lambda _lib, image: _AIM_FN(image, from_x, from_y, to_x, to_y, row,
                                       ctypes.byref(dx), ctypes.byref(dy))


def _run_aim(what, from_x, from_y, to_x, to_y, row=None):
    """One differential over the leaf, with the oracle's own d0/d1 compared as well as the port's.
    It writes no memory at all, so the two returned registers ARE the whole surface."""
    row = wb("ACTOR_TYPE21_AIM_ROW") if row is None else row
    dx, dy = ctypes.c_int16(0), ctypes.c_int16(0)
    regs = {"d0": from_x, "d1": from_y, "d2": to_x, "d3": to_y, "d4": row}
    info = leaf.run("actor_aim_velocity", _aim_glue(from_x, from_y, to_x, to_y, row, dx, dy),
                    [], what, regs=regs, max_insns=AIM_INSN_CAP)
    assert info["regs"]["d0"] & 0xffff == dx.value & 0xffff, (
        f"{what}: the reconstruction's dx is {dx.value:#06x}, not the original's "
        f"{info['regs']['d0'] & 0xffff:#06x}")
    assert info["regs"]["d1"] & 0xffff == dy.value & 0xffff, (
        f"{what}: the reconstruction's dy is {dy.value:#06x}, not the original's "
        f"{info['regs']['d1'] & 0xffff:#06x}")
    return dx.value, dy.value


# The two pairs whose `sub.w` OVERFLOWS — opposite signs, a true difference past $7fff — and one
# that does not, as the control. On the overflowing pairs a port that reads the SIGN OF THE RESULT
# folds the delta the wrong way round and lands on a different direction entirely.
AIM_OVERFLOW_PAIRS = ((0xffff, 0x7fff), (0x7fff, 0xffff), (0x8000, 0x0001))
AIM_CONTROL_PAIR = (0x0100, 0x0140)


@pytest.mark.parametrize("from_x,to_x", AIM_OVERFLOW_PAIRS + (AIM_CONTROL_PAIR,),
                         ids=lambda v: f"{v:#06x}")
def test_the_aim_leafs_first_sign_test_reads_N_XOR_V_and_not_the_RESULT(from_x, to_x):
    """`sub.w d0,d2 / bge.s $6548` — BGE is N^V, i.e. the exact signed comparison of the two
    operands, where the SECOND test (`tst.w d3 / bge.s`, V cleared) really is a sign test. Spelling
    the two alike diverges exactly on overflow, and slot 21's own reach gate can never produce it —
    so these rows enter the leaf directly."""
    what = f"actor_aim_velocity from x {from_x:#06x} to {to_x:#06x}"
    from_y, to_y = 0x0100, 0x0140
    dx, dy = _run_aim(what, from_x, from_y, to_x, to_y)
    assert (dx, dy) == _aim_velocity(bytes(harness.BASE_IMAGE), from_x, from_y, to_x, to_y,
                                     wb("ACTOR_TYPE21_AIM_ROW")), (
        f"{what}: the battery's own model does not agree with either core")


def test_the_aim_leaf_ignores_the_HIGH_HALVES_of_its_five_registers():
    """Every operand is a word op and the only index it builds is sign-extended from a word, so the
    high halves cannot reach the answer — which is why the C takes whole registers and truncates at
    each operation. Driven rather than argued: the same five low words with $dead in every high half
    give the same pair."""
    low = (0x0100, 0x0080, 0x0140, 0x0060)
    row = wb("ACTOR_TYPE21_AIM_ROW")
    plain = _run_aim("actor_aim_velocity low halves", *low, row=row)
    dirty = _run_aim("actor_aim_velocity high halves poisoned",
                     *(0xdead0000 | value for value in low), row=0xdead0000 | row)
    assert plain == dirty, f"a high half reached the answer: {plain} against {dirty}"


def test_slot21_animates_until_its_list_wraps_and_then_LATCHES():
    """WB_ACTOR_FIELD_30 is a FLAG here, not a countdown — nothing steps it — and the frame the idle
    animation wraps is the one that raises it."""
    what = f"{TYPE21} idle wrapping"
    pokes = _family37_pokes(what, 21, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + FIELD_18: bytes([LAST_FRAME[ANIM32_MASK]])})

    written = program_writes(_run_handler(TYPE21, what, pokes))
    assert written[ACTOR + FIELD_18] == 0, f"{what}: the animation did not wrap"
    assert written[ACTOR + FIELD_30] == ST_BYTE, f"{what}: the aiming flag was not latched"
    assert ACTOR + ACTOR_X not in written, f"{what}: this handler stepped"


def test_slot21_out_of_reach_fires_nothing_and_keeps_its_flag():
    """`move.w #$96,d0 / bsr $67f8 / bmi` — the reach test, and its refusal ends the frame ABOVE the
    `clr.b 30(a0)`, so the record stays armed."""
    what = f"{TYPE21} out of reach"
    pokes = _family37_pokes(what, 21, {
        ACTOR + FIELD_30: bytes([ST_BYTE]), ACTOR + ACTOR_X: word(0x0100),
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0100 + TYPE21_REACH + 1)})

    written = program_writes(_run_handler(TYPE21, what, pokes))
    assert ACTOR + FIELD_30 not in written, f"{what}: the flag was cleared out of reach"
    assert ACTOR + ACTOR_SPRITE not in written, f"{what}: the aiming arm animated"


@pytest.mark.parametrize("bit,tick", sorted(TICKS_BY_RNG_BIT.items()),
                         ids=["draw-permits", "draw-vetoes"])
def test_slot21_needs_the_draw_to_come_up_ZERO(bit, tick):
    """`andi.w #$1f,d0 / bne` — one frame in $20. The two ticks this file already uses differ in
    bit 2 alone, so one of them is a nonzero word and the other is not."""
    what = f"{TYPE21} draw bit {bit}"
    pokes = _family37_pokes(what, 21, {ACTOR + FIELD_30: bytes([ST_BYTE]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(IN_REACH_X)})
    # One tick that fires and one that does not, so BOTH arms of the `bne` are driven.
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, TYPE21_SHOT_ODDS_MASK) + bit)
    drawn, counters = model_rng(harness.make_image(pokes), 0)
    fires = (drawn & TYPE21_SHOT_ODDS_MASK) == 0
    assert fires == (bit == 0), f"{what}: the two ticks do not separate the arms"

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    assert (ACTOR + FIELD_30 in written) == fires, (
        f"{what}: the draw was {drawn:#06x} and the flag was "
        f"{'not ' if fires else ''}cleared")


# Slot 21's reach is WB_ACTOR_TYPE21_REACH, so every geometry below sits inside it — a followed
# record farther off never reaches the aim at all, which is the case above.
IN_REACH_X = 0x0100 + 0x40
# ...and the ONE direction whose table entry has a nonzero dy at an equal y, which is what makes
# `clr.w d1` observable: a record LEFT and level folds to a different entry from one to the right.
LEVEL_LEFT_X = 0x0100 - 0x40


def _tick_that_draws_zero(pokes, mask):
    """A WB_FRAME_TICK whose `rng_next` word comes up zero under `mask`, so a one-in-$20 arm can be
    driven at all. Scanned by editing the tick inside the image the case has ALREADY built rather
    than by seeding and rebuilding one per candidate — batch 35 built sixty-four megabyte images
    doing that."""
    image = bytearray(harness.make_image(pokes))
    for tick in range(0x100):
        image[FRAME_TICK:FRAME_TICK + WORD_BYTES] = word(tick)
        drawn, _counters = model_rng(bytes(image), 0)
        if (drawn & mask) == 0:
            return tick
    raise AssertionError("no frame tick in 0..$ff makes this draw come up zero")


@pytest.mark.parametrize("followed_x,followed_y", [(0x0140, STAND_Y - 0x40), (0x00c0, STAND_Y - 0x40),
                                                   (0x0102, STAND_Y - 0x80), (0x00a0, STAND_Y + 0x40),
                                                   # ...and the (+dx,+dy) fold quadrant, which no
                                                   # row above reaches at a non-trivial ratio: the
                                                   # only other (+, >=0) row degenerates at dy = 0.
                                                   (0x0140, STAND_Y + 0x18),
                                                   (0x0141, STAND_Y + 0x19)],
                         ids=["right-up", "left-up", "near-up", "left-down",
                              "right-down", "right-down-odd"])
def test_slot21_fires_a_shot_AIMED_out_of_the_image_table(followed_x, followed_y):
    """The whole spawn: the parent's x/y, six pixels up, the type, the flag byte AS IT STANDS, the
    size longword — and the velocity pair $6528's row WB_ACTOR_TYPE21_AIM_ROW gives for the vector
    to the followed record. Four geometries, so a fold that dropped a sign or a swap fails."""
    what = f"{TYPE21} firing at {followed_x:#06x},{followed_y:#06x}"
    x, y = 0x0100, STAND_Y
    pokes = _family37_pokes(what, 21, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        ACTOR + FIELD_30: bytes([ST_BYTE]), ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x), FOLLOWED_DEFAULT + ACTOR_Y: word(followed_y)})
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, TYPE21_SHOT_ODDS_MASK))
    image = harness.make_image(pokes)
    drawn, counters = model_rng(image, 0)
    assert (drawn & TYPE21_SHOT_ODDS_MASK) == 0, f"{what}: this tick does not fire"
    dx, dy = _aim_velocity(image, x, y, followed_x, followed_y, TYPE21_AIM_ROW)

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    shot = FIRST_HIGH_RECORD
    assert _written_word(written, shot, ACTOR_X) == x
    assert _written_word(written, shot, ACTOR_Y) == y - wb("ACTOR_TYPE21_SHOT_RISE")
    assert _written_word(written, shot, ACTOR_TYPE) == wb("ACTOR_TYPE21_SHOT_TYPE")
    assert written[shot + FIELD_30] == dx & 0xff, f"{what}: the shot's dx is not the table's"
    assert written[shot + FIELD_31] == dy & 0xff, f"{what}: the shot's dy is not the table's"
    assert written[shot + FIELD_29] == wb("ACTOR_TYPE21_SHOT_LIFE")
    assert not written[shot + ACTOR_FLAGS] & (1 << SUPPORTED_BIT)
    assert written[ACTOR + FIELD_30] == 0, f"{what}: the aiming flag survived the shot"


def test_slot21_zeroes_the_shots_DY_when_the_two_records_are_LEVEL():
    """`move.w 2(a0),d7 / cmp.w 2(a2),d7 / bne / clr.w d1` — the dy the table returned is discarded
    on an equal y. The row asserts the table's own answer is NONZERO first, so a seed whose entry
    happened to be zero could not pass as a proof."""
    what = f"{TYPE21} firing level"
    x, y = 0x0100, STAND_Y
    pokes = _family37_pokes(what, 21, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        ACTOR + FIELD_30: bytes([ST_BYTE]),
        FOLLOWED_DEFAULT + ACTOR_X: word(LEVEL_LEFT_X), FOLLOWED_DEFAULT + ACTOR_Y: word(y)})
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, TYPE21_SHOT_ODDS_MASK))
    image = harness.make_image(pokes)
    _drawn, counters = model_rng(image, 0)
    _dx, dy = _aim_velocity(image, x, y, LEVEL_LEFT_X, y, TYPE21_AIM_ROW)
    assert dy != 0, f"{what}: the table's own dy is zero here, so this case would prove nothing"

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    assert written[FIRST_HIGH_RECORD + FIELD_31] == 0, f"{what}: the level dy was not cleared"


def test_slot21_clears_its_flag_even_when_the_POOL_REFUSES():
    """`clr.b 30(a0)` sits ABOVE `bsr $1b8e`, so a full pool costs the record its shot AND its armed
    state — where slot 14's refused drop leaves its own gap byte standing."""
    what = f"{TYPE21} firing into a full pool"
    pokes = _full_pool_pokes(_family37_pokes(what, 21, {
        ACTOR + FIELD_30: bytes([ST_BYTE]), FOLLOWED_DEFAULT + ACTOR_X: word(IN_REACH_X)}))
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, TYPE21_SHOT_ODDS_MASK))
    _drawn, counters = model_rng(harness.make_image(pokes), 0)

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    assert written[ACTOR + FIELD_30] == 0, f"{what}: the flag survived a refused allocation"


# A WB_ACTOR_FLAGS2 bit the image never names: bits 0..4 are the five this tier writes.
FLAGS2_WITNESS_BIT = 1 << 6


# --- slot 22: the launcher ------------------------------------------------------------------------
def test_slot22_launches_itself_when_its_countdown_reaches_zero():
    """The three bit writes and the speed spelt INLINE rather than through
    actor_start_motion_at_speed, and the reload above them."""
    what = f"{TYPE22} launching"
    pokes = _family37_pokes(what, 22, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    written = program_writes(_run_handler(TYPE22, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE22) + merge_bands(counters)))
    flags = written[ACTOR + ACTOR_FLAGS]
    assert written[ACTOR + FIELD_30] == TYPE22_RELOAD, f"{what}: the countdown was not reloaded"
    assert flags & (1 << MOVING_BIT) and flags & (1 << LAUNCHED_BIT)
    assert not flags & (1 << SUPPORTED_BIT)
    assert written[ACTOR + SPEED] == wb("ACTOR_TYPE22_LAUNCH_SPEED")


def test_slot22_that_is_AIRBORNE_at_zero_wraps_its_countdown_to_ff():
    """`bclr #2,8(a0) / beq` falls into `subq.b #1,30(a0)` on the arm that did NOT launch, so a
    record already off the ground does not merely skip the launch — its countdown wraps to $ff and
    it waits the longest possible time for the next one."""
    what = f"{TYPE22} airborne at zero"
    pokes = _family37_pokes(what, 22, {ACTOR + FIELD_30: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([1 << MOVING_BIT])},
                            ground=False)

    _drawn, counters = model_rng(harness.make_image(pokes), 0)
    written = program_writes(_run_handler(TYPE22, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE22) + merge_bands(counters)))
    assert written[ACTOR + FIELD_30] == 0xff, f"{what}: the countdown did not wrap"
    # The settle writes WB_ACTOR_SPEED on every frame, so what says the launch did NOT run is the
    # value it would have written and the two bits it would have raised.
    assert written.get(ACTOR + SPEED) != wb("ACTOR_TYPE22_LAUNCH_SPEED"), (
        f"{what}: an airborne record launched")
    assert not written[ACTOR + ACTOR_FLAGS] & (1 << LAUNCHED_BIT), (
        f"{what}: the launch raised its bits anyway")


def test_slot22_drops_NO_minion_while_the_slot53_word_is_up():
    """`tst.w $5c6c.l / bne` — the same word slot 53 raises while it is alive, read here as a veto
    on this handler's own spawn."""
    what = f"{TYPE22} vetoed by the slot-53 word"
    pokes = _family37_pokes(what, 22, {TYPE53_ALIVE: word(wb("ACTOR_TYPE53_ALIVE_SET"))})

    written = program_writes(_run_handler(TYPE22, what, pokes))
    assert not any(addr >= FIRST_HIGH_RECORD for addr in written), (
        f"{what}: a minion was allocated with the word up")


def test_slot22_drops_a_minion_carrying_its_flag_WORD():
    """`move.w 8(a0),8(a1)` — a WORD, so WB_ACTOR_FLAGS2 crosses with the flag byte where every
    other spawner in the family copies the byte alone."""
    what = f"{TYPE22} dropping a minion"
    # A bit of WB_ACTOR_FLAGS2 no arm of this frame writes, so what reaches the minion is the
    # copy and not a coincidence — the LANDED bit the settle rewrites would prove nothing.
    y, marks = STAND_Y, FLAGS2_WITNESS_BIT
    pokes = _family37_pokes(what, 22, {
        ACTOR + ACTOR_Y: word(y), ACTOR + FLAGS2: bytes([marks]),
        ACTOR + ACTOR_FLAGS: bytes([1 << SIDE_BIT]), TYPE53_ALIVE: word(0)})
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, wb("ACTOR_TYPE22_SEED_ODDS_MASK")))
    _drawn, counters = model_rng(harness.make_image(pokes), 0)

    written = program_writes(_run_handler(TYPE22, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE22) + merge_bands(counters)))
    minion = FIRST_HIGH_RECORD
    assert _written_word(written, minion, ACTOR_TYPE) == wb("ACTOR_TYPE22_MINION_TYPE")
    assert _written_word(written, minion, ACTOR_Y) == y - wb("ACTOR_TYPE22_MINION_RISE")
    assert written[minion + FLAGS2] & marks, f"{what}: the SECOND byte of the word did not cross"
    assert written.get(ACTOR + FLAGS2, marks) & marks, (
        f"{what}: the parent lost the witness bit, so the copy proves nothing")
    assert written[minion + FIELD_30] == wb("ACTOR_TYPE22_MINION_TIMER")


# --- slot 23: the gold thief ----------------------------------------------------------------------
def _thief_pokes(what, purse, fields=None):
    """Slot 23 with its footprints on the followed record's, so the body arm runs, and a purse
    stated. The followed record is left INVULNERABLE so actor_damage_followed writes nothing and the
    write set is the theft's own."""
    base = {ACTOR + ACTOR_X: word(0x0100), ACTOR + ACTOR_Y: word(STAND_Y),
            ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
            BCD_COUNTER: word(purse),
            FOLLOWED_DEFAULT + ACTOR_X: word(0x0100), FOLLOWED_DEFAULT + ACTOR_Y: word(STAND_Y),
            FOLLOWED_DEFAULT + ACTOR_SPRITE: word(0),
            FOLLOWED_DEFAULT + FLAGS2: bytes([1 << INVULNERABLE_BIT])}
    return _family37_pokes(what, 23, leaf.overlay(base, fields or {}))


def _thief_band(pokes):
    """The record tier, the purse and the BCD accumulator's own staging longword — the same three
    slot 28's collect arm allows, and for the same reason."""
    return _handler_band(TYPE23) + [(BCD_ADDEND, LONGWORD_BYTES), (BCD_COUNTER, BCD_COUNTER_LEN)] \
        + _foreign_band(harness.make_image(pokes), {}, "damage-followed")


@pytest.mark.parametrize("purse,left", [(0x0500, 0x0490), (TYPE23_STEAL_MAX, 0),
                                        (TYPE23_STEAL_MAX + 1, 1)],
                         ids=["above-the-max", "at-the-max", "one-over"])
def test_slot23_charges_a_purse_ABOVE_its_maximum_and_EMPTIES_one_below_it(purse, left):
    """`cmpi.w #$10,$bd6e.l / bgt` — a SIGNED compare, and the two arms are not one clamped
    subtraction: above the maximum the counter is charged in BCD, at or below it the whole word is
    `clr.w`ed. $0500 - $10 is $0490 in packed BCD, which is what says the subtract really is one."""
    what = f"{TYPE23} robbing a purse of {purse:#06x}"
    pokes = _thief_pokes(what, purse)

    info = _run_handler(TYPE23, what, pokes, band=_thief_band(pokes))
    written = program_writes(info)
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, what) == left, (
        f"{what}: the purse is wrong")
    assert _written_word(written, FIRST_HIGH_RECORD, ACTOR_TYPE) == wb("ACTOR_TYPE23_LOOT_TYPE")
    assert written[FIRST_HIGH_RECORD + FIELD_30] == wb("ACTOR_TYPE23_LOOT_TIMER")
    assert written[FIRST_HIGH_RECORD + FIELD_21] == wb("ACTOR_TYPE23_STUN_FRAMES")


def test_slot23_robs_NOTHING_from_a_flickering_record():
    """`btst #6,8(a1) / bne.w $69fe` — a record already mid-invulnerability keeps its gold, and the
    frame is an ordinary body-arm frame."""
    what = f"{TYPE23} robbing a flickering record"
    pokes = _thief_pokes(what, 0x0500,
                         {FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([1 << FLICKER_BIT])})

    written = program_writes(_run_handler(TYPE23, what, pokes, band=_thief_band(pokes)))
    assert BCD_COUNTER not in written, f"{what}: the purse was charged anyway"
    assert not any(addr >= FIRST_HIGH_RECORD for addr in written), f"{what}: loot was dropped"


def test_slot23_robs_NOTHING_from_an_empty_purse():
    """`tst.w $bd6e.l / beq.w $69fe` — and this is the arm that says the empty case is a REFUSAL and
    not a subtraction of zero: no loot record is allocated at all."""
    what = f"{TYPE23} robbing an empty purse"
    pokes = _thief_pokes(what, 0)

    written = program_writes(_run_handler(TYPE23, what, pokes, band=_thief_band(pokes)))
    assert not any(addr >= FIRST_HIGH_RECORD for addr in written), f"{what}: loot was dropped"


def test_slot23_stuns_ADDRESS_ZERO_when_the_pool_is_full():
    """SLOT 19's DEFECT ONE HANDLER ON. `move.b #$64,21(a1)` sits BELOW the failed-allocation
    branch, so with a1 at zero the byte lands at WB_ACTOR_FIELD_21 — address $15, four hundred bytes
    below the program and inside the 68000's own vector page. Reproduced, not repaired."""
    what = f"{TYPE23} robbing with the pool full"
    pokes = _full_pool_pokes(_thief_pokes(what, 0x0500))
    band = _thief_band(pokes) + merge_bands([FIELD_21])

    written = program_writes(_run_handler(TYPE23, what, pokes, band=band))
    assert written[FIELD_21] == wb("ACTOR_TYPE23_STUN_FRAMES"), (
        f"{what}: address {FIELD_21:#x} was not written, so the store was guarded")


def test_slot23_hovers_on_SLOT_4s_OWN_table():
    """The reuse, driven: slot 23's copy of the hover reads WB_ACTOR_TYPE04_HOVER through the SHORT
    absolute encoding, so the delta added to its y is the word slot 4's table holds."""
    what = f"{TYPE23} hovering"
    y, cursor = STAND_Y, 6
    pokes = _family37_pokes(what, 23, {ACTOR + ACTOR_Y: word(y), ACTOR + FIELD_30: bytes([cursor])})

    written = program_writes(_run_handler(TYPE23, what, pokes))
    delta = s16(_image_word(wb("ACTOR_TYPE04_HOVER") + cursor))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta) & 0xffff
    assert written[ACTOR + FIELD_30] == cursor + ANIM_FRAME_BYTES


# --- slot 24: the row whose tail is SLOT 17's -----------------------------------------------------
def test_slot24_runs_SLOT_17s_seeding_burst_as_its_own_tail():
    """`bra.w $3ae6` at $48b2 — the obligation ../names.txt's plate on $484c states, driven rather
    than asserted: the frame ends with WB_ACTOR_TYPE17_SEED_DBF_COUNT + 1 records of slot 17's own
    seed type on the parent's square, numbered down from WB_ACTOR_TYPE17_SEED_FIRST."""
    what = f"{TYPE24} seeding"
    pokes = _family37_pokes(what, 24, {ACTOR + ACTOR_X: word(0x0100)})
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, wb("ACTOR_TYPE17_SEED_ODDS_MASK")))
    _drawn, counters = model_rng(harness.make_image(pokes), 0)

    written = program_writes(_run_handler(TYPE24, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE24) + merge_bands(counters)))
    seeds = wb("ACTOR_TYPE17_SEED_DBF_COUNT") + 1
    for ordinal in range(seeds):
        seed = _record(TABLE_DEFAULT, ALLOC_HIGH_FIRST + ordinal)
        assert _written_word(written, seed, ACTOR_TYPE) == wb("ACTOR_TYPE17_SEED_TYPE"), (
            f"{what}: high record {ordinal} is not one of slot 17's seeds")
        assert written[seed + FIELD_30] == wb("ACTOR_TYPE17_SEED_FIRST") - ordinal


def test_slot24_steps_and_animates_before_it_leaves():
    """The five instructions that ARE slot 24's: the settle, the ascent, the facing, a one-pixel
    step and one frame out of a PAIR whose two longwords hold the same list."""
    what = f"{TYPE24} walking"
    x = 0x0100
    pokes = _family37_pokes(what, 24, {ACTOR + ACTOR_X: word(x),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(0x0010)})
    _drawn, counters = model_rng(harness.make_image(pokes), 0)

    written = program_writes(_run_handler(TYPE24, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE24) + merge_bands(counters)))
    assert _written_word(written, ACTOR, ACTOR_X) == x - wb("ACTOR_TYPE24_WALK_STEP")
    assert ACTOR + ACTOR_SPRITE in written, f"{what}: nothing was published"


def test_slot24s_two_list_pairs_hold_the_SAME_list_twice():
    """Which is why the facing $3006 reads decides nothing here, where it decides everything at the
    other four pair sites in this tier."""
    for name in ("ACTOR_TYPE24_LIVE_LISTS", "ACTOR_TYPE24_HURT_LISTS"):
        pair = wb(name)
        left = int.from_bytes(harness.BASE_IMAGE[pair:pair + LONGWORD_BYTES], "big")
        right = int.from_bytes(harness.BASE_IMAGE[pair + LONGWORD_BYTES:
                                                  pair + 2 * LONGWORD_BYTES], "big")
        assert left == right, f"{name}'s two longwords are {left:#06x} and {right:#06x}"


# --- slot 25: slot 18's charge again --------------------------------------------------------------
def test_slot25_charges_and_spawns_its_OWN_minion_type():
    """The whole charge: the latch, the flag byte saved, the facing, the launch and a companion of
    WB_ACTOR_TYPE25_MINION_TYPE — slot 18's frame with one word changed."""
    what = f"{TYPE25} charging"
    flags = 1 << SUPPORTED_BIT
    pokes = _family37_pokes(what, 25, {ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([0]),
                                       ACTOR + ACTOR_FLAGS: bytes([flags])})

    written = program_writes(_run_handler(TYPE25, what, pokes))
    assert written[ACTOR + FIELD_31] == wb("ACTOR_TYPE25_CHARGING")
    assert written[ACTOR + FIELD_29] == flags, f"{what}: the flag byte was not saved first"
    assert written[ACTOR + SPEED] == wb("ACTOR_TYPE25_HOP_SPEED")
    assert _written_word(written, FIRST_HIGH_RECORD, ACTOR_TYPE) == wb("ACTOR_TYPE25_MINION_TYPE")


def test_slot25_restores_its_flag_byte_and_turns_when_it_lands():
    """`move.b 29(a0),8(a0) / bchg #3,8(a0)` and the reload — the shared `restore_flags_and_turn`,
    reached with the latch up and the record supported again."""
    what = f"{TYPE25} landing"
    saved = 1 << SIDE_BIT
    pokes = _family37_pokes(what, 25, {
        ACTOR + FIELD_30: bytes([0]), ACTOR + FIELD_31: bytes([wb("ACTOR_TYPE25_CHARGING")]),
        ACTOR + FIELD_29: bytes([saved]), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    written = program_writes(_run_handler(TYPE25, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] == (saved ^ (1 << SIDE_BIT)), (
        f"{what}: the byte was not put back and turned round")
    assert written[ACTOR + FIELD_30] == wb("ACTOR_TYPE25_TURN_FRAMES")
    assert written[ACTOR + FIELD_31] == 0


# --- slot 26: slot 12's chase, with a shot --------------------------------------------------------
@pytest.mark.parametrize("moving", [False, True], ids=["still", "moving"])
def test_slot26_picks_its_list_off_the_MOVING_bit_and_shoots_on_that_arm(moving):
    """`btst #0,8(a0)` where slot 12 reads the SUPPORTED bit — and the shot hangs off the same
    branch, so the still arm allocates nothing at all."""
    what = f"{TYPE26} {'moving' if moving else 'still'}"
    flags = (1 << MOVING_BIT) if moving else (1 << SUPPORTED_BIT)
    y = STAND_Y
    pokes = _family37_pokes(what, 26, {ACTOR + ACTOR_Y: word(y), ACTOR + ACTOR_FLAGS: bytes([flags]),
                                       ACTOR + FIELD_30: bytes([5])}, ground=not moving)

    written = program_writes(_run_handler(TYPE26, what, pokes))
    shot = FIRST_HIGH_RECORD
    lists = wb("ACTOR_TYPE26_MOVING_LISTS") if moving else wb("ACTOR_TYPE26_STILL_LISTS")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(_list_of(lists, left=False)), (
        f"{what}: the other list was published")
    if moving:
        assert _written_word(written, shot, ACTOR_TYPE) == wb("ACTOR_TYPE26_SHOT_TYPE")
        assert _written_word(written, shot, ACTOR_Y) == y - wb("ACTOR_TYPE26_SHOT_RISE")
        assert _written_word(written, shot, HALF_WIDTH) == wb("ACTOR_TYPE26_SHOT_SIZE") >> 16
    else:
        assert not any(addr >= shot for addr in written), f"{what}: the still arm allocated"


# --- the census, and the two plate corrections it makes -------------------------------------------
FAMILY37_TABLES = (
    "ACTOR_TYPE20_WALK_LEFT", "ACTOR_TYPE20_WALK_RIGHT",
    "ACTOR_TYPE20_HURT_LEFT", "ACTOR_TYPE20_HURT_RIGHT",
    "ACTOR_TYPE21_WALK_LEFT", "ACTOR_TYPE21_WALK_RIGHT",
    "ACTOR_TYPE21_HURT_LEFT", "ACTOR_TYPE21_HURT_RIGHT",
    "ACTOR_TYPE22_LIVE_LISTS", "ACTOR_TYPE22_HURT_LISTS",
    "ACTOR_TYPE23_DEAD_LEFT", "ACTOR_TYPE23_DEAD_RIGHT",
    "ACTOR_TYPE24_LIVE_LISTS", "ACTOR_TYPE24_HURT_LISTS",
    "ACTOR_TYPE25_WALK_LEFT", "ACTOR_TYPE25_WALK_RIGHT",
    "ACTOR_TYPE25_HURT_LEFT", "ACTOR_TYPE25_HURT_RIGHT",
    "ACTOR_TYPE26_MOVING_LISTS", "ACTOR_TYPE26_STILL_LISTS", "ACTOR_TYPE26_HURT_LISTS",
    "ACTOR_TYPE27_WALK_LEFT", "ACTOR_TYPE27_WALK_RIGHT",
    "ACTOR_TYPE27_HURT_LEFT", "ACTOR_TYPE27_HURT_RIGHT",
    "ACTOR_AIM_TABLE",
)


@pytest.mark.parametrize("name", FAMILY37_TABLES)
def test_every_table_batch37_names_has_exactly_one_lea_naming_it(name):
    addr = wb(name)
    sites = _lea_sites(addr)
    assert len(sites) == 1, (
        f"{name} ({addr:#06x}) is named by {len(sites)} `lea`s, not one: "
        f"{[hex(at) for at in sites]}")


@pytest.mark.parametrize("name", ["ACTOR_TYPE23_FLY_LEFT", "ACTOR_TYPE23_FLY_RIGHT"])
def test_slot23s_two_fly_tables_are_named_TWICE_EACH_as_slot_4s_are(name):
    """The exception to the one-site rule, and it is structural rather than accidental: this arm
    `lea`s its table once on the LEVEL branch and once on the stepping one, exactly as slot 4 does,
    so a census that demanded one site would have reported a defect that is not there."""
    sites = _lea_sites(wb(name))
    assert len(sites) == 2, f"{name} is named by {[hex(at) for at in sites]}"
    assert all(wb("ACTOR_BEHAVIOR_TYPE23") <= at < wb("ACTOR_BEHAVIOR_TYPE24") for at in sites), (
        f"{name} is named from outside slot 23: {[hex(at) for at in sites]}")


def test_slot_4s_hover_table_has_TWO_operand_sites_and_the_second_is_SLOT_23s():
    """THE PLATE CORRECTION THIS BATCH MAKES. WB_ACTOR_TYPE04_HOVER's plate counted one reference —
    slot 4's `lea $296c.l` — and slot 23 reads the same table through the SHORT absolute encoding
    inside its own body. A census run in one encoding only is exactly what batch 34's $5160 miss
    was, and this is the same shape at a different address."""
    sites = _lea_sites(wb("ACTOR_TYPE04_HOVER"))
    assert len(sites) == 2, f"the hover table is named by {[hex(at) for at in sites]}"
    inside_23 = [at for at in sites
                 if wb("ACTOR_BEHAVIOR_TYPE23") <= at < wb("ACTOR_BEHAVIOR_TYPE24")]
    inside_4 = [at for at in sites
                if wb("ACTOR_BEHAVIOR_TYPE04") <= at < wb("ACTOR_BEHAVIOR_TYPE05")]
    assert len(inside_4) == len(inside_23) == 1, (
        f"the two sites are not one in slot 4 and one in slot 23: {[hex(at) for at in sites]}")


@pytest.mark.parametrize("slot", FAMILY37_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_each_batch37_entry_is_reached_ONLY_through_the_dispatch_longword(slot):
    entry = leaf.entry_of(f"actor_behavior_type{slot:02d}")
    assert entry not in CONTROL_FLOW_TARGETS, (
        f"{entry:#06x} is named by {[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}")
    holders = [at for at in _operand_sites(longword(entry)) if at % WORD_BYTES == 0]
    assert holders == [BEHAVIOR_TABLE + slot * BEHAVIOR_ENTRY], (
        f"{entry:#06x} is held as a longword at {[hex(at) for at in holders]}, not only its slot")


# THREE INSTRUCTIONS INSIDE THIS BAND AIM OUT OF IT, and each lands in another handler's body — so
# three of these eight rows do not end in their own extent. Stated as an exact set for the same
# reason batch 36 stated the inbound one: a fourth appearing later is a finding, not a detail.
BAND37_LO, BAND37_HI = wb("ACTOR_BEHAVIOR_TYPE20"), wb("ACTOR_BEHAVIOR_TYPE28")
FOREIGN_EDGES_OUT_OF_BAND37 = {
    0x46fe: wb("ACTOR_TYPE04_FLY_PUBLISH"),   # slot 23 -> slot 4's publish-and-hover tail
    0x48b2: wb("ACTOR_TYPE17_SEED_BURST"),    # slot 24 -> slot 17's seeding block
    0x4aa8: wb("ACTOR_TYPE18_WALK_LEFT") - len(RTS),   # slot 25 -> slot 18's own `rts`
}
# ...and the routines every handler in the band legitimately calls, which are edges too.
BAND37_CALLEES = frozenset(leaf.entry_of(name) for name in (
    SPAWN_ANIM, HIT_BY_SHOT, OVERLAP, DAMAGE_FOLLOWED, DAMAGE_TEMPLATE, DEFEAT, FALL_AND_SETTLE,
    HOP_ASCEND, SIDE_FLAG, WITHIN, FOLLOWED_RECORD, RNG_NEXT, ALLOC_HIGH, START_MOTION,
    TOGGLE_SIDE, STEP_LEFT, STEP_RIGHT, STEP_FACING, FACE_TOWARD, FACE_AWAY4, TICK_TIMER30,
    ANIM_LIST, PLAYER_GATE, AIM_VELOCITY, BCD_SUB_COUNTER))


# The opcodes that TRANSFER CONTROL, as against the `lea`/`pea` forms the same scan also collects:
# a linear sweep over a band that holds frame tables decodes data words as instructions, and three
# of this band's data words happen to encode `lea <abs>.w`. Filtering by opcode is what keeps a
# phantom out of an exact-set assertion.
TRANSFER_OPCODES = frozenset(range(BRANCH_OPCODE_LO, BRANCH_OPCODE_HI + 1)) \
    | {0x4eb8, 0x4eb9, 0x4eba, 0x4ebb, 0x4ef8, 0x4ef9, 0x4efa, 0x4efb}


def _is_transfer(op):
    return op in TRANSFER_OPCODES or op & DBCC_MASK == DBCC_MATCH


TRANSFER_TARGETS = {target: [at for at, op in sites if _is_transfer(op)]
                    for target, sites in INSTRUCTION_TARGETS.items()}


def test_the_only_foreign_exits_from_band37_are_the_three_the_plates_name():
    """Every instruction inside $4118..$4e37 that TRANSFERS outside it, minus the routines the
    handlers call: what is left is the three branches that land inside another handler's body."""
    found = {}
    for target, sites in TRANSFER_TARGETS.items():
        if BAND37_LO <= target < BAND37_HI or target in BAND37_CALLEES:
            continue
        for at in sites:
            if BAND37_LO <= at < BAND37_HI:
                found[at] = target
    edges = ", ".join(f"{at:#06x}->{target:#06x}" for at, target in sorted(found.items()))
    assert found == FOREIGN_EDGES_OUT_OF_BAND37, f"the foreign exits from this band are {edges}"


# --- the RAW-INDEX convention, driven at every one of this batch's own frame reads -----------------
# `move.b 18(a0),d0 / lea 0(a1,d0.w),a1 / move.w (a1),6(a0)` publishes FIRST and masks the value
# going BACK into the record, so a cursor above the mask reads PAST the table its `lea` names. Batch
# 35 had to retract three plates over this and batch 36 drove all thirteen of its sites; these are
# batch 37's eight direct reads, and the ninth is slot 23's hover below.
#
# THE SIBLING-TABLE RESIDUE IS CLOSED THE SAME WAY: where two facing tables are contiguous,
# `table + mask + 1` IS `sibling + 0`, so a row seeded exactly one table past cannot tell "raw index
# on the right table" from "masked index on the SIBLING". Each cursor below is the smallest one at
# which all THREE readings differ, and the premise guard checks all three.
def _over_read_cursor(table, mask):
    """The smallest even cursor past `mask` whose RAW word, its MASKED word and the SIBLING table's
    masked word are three different values — so one row separates all three readings at once."""
    for cursor in range(mask + 1, 4 * (mask + 1), ANIM_FRAME_BYTES):
        raw = _image_word(table + cursor)
        masked = _image_word(table + (cursor & mask))
        sibling = _image_word(table + mask + 1 + (cursor & mask))
        if raw != masked and raw != sibling:
            return cursor
    raise AssertionError(f"no cursor past {mask:#04x} separates the three readings at {table:#06x}")


FAMILY37_OVER_READS = (
    (20, "ACTOR_TYPE20_WALK_RIGHT", ANIM16_MASK, "walk"),
    (20, "ACTOR_TYPE20_HURT_RIGHT", ANIM32_MASK, "hurt"),
    (21, "ACTOR_TYPE21_WALK_RIGHT", ANIM32_MASK, "idle"),
    (21, "ACTOR_TYPE21_HURT_RIGHT", ANIM16_MASK, "hurt"),
    (25, "ACTOR_TYPE25_WALK_RIGHT", ANIM32_MASK, "walk"),
    (25, "ACTOR_TYPE25_HURT_RIGHT", ANIM16_MASK, "hurt"),
    (27, "ACTOR_TYPE27_WALK_RIGHT", ANIM16_MASK, "walk"),
    (27, "ACTOR_TYPE27_HURT_RIGHT", ANIM32_MASK, "hurt"),
)
OVER_READ_ARMS = {
    # The live arm with a countdown that will not expire this frame, and the hurt one.
    "walk": {ACTOR + FIELD_30: bytes([7]), ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])},
    "idle": {ACTOR + FIELD_30: bytes([0])},
    "hurt": {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
             ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])},
}


@pytest.mark.parametrize("slot,table,mask,arm", FAMILY37_OVER_READS,
                         ids=lambda v: str(v) if not isinstance(v, int) else f"{v:#04x}")
def test_the_batch37_frame_reads_index_on_the_RAW_cursor(slot, table, mask, arm):
    name = f"actor_behavior_type{slot:02d}"
    frames = wb(table)
    cursor = _over_read_cursor(frames, mask)
    what = f"{name} {arm} over-read at {cursor:#04x}"
    pokes = _family37_pokes(what, slot, leaf.overlay(
        {ACTOR + FIELD_18: bytes([cursor])}, OVER_READ_ARMS[arm]))

    written = program_writes(_run_handler(name, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(frames + cursor), (
        f"{what}: the word published is not the one at table + RAW cursor")
    assert written[ACTOR + FIELD_18] == (cursor + ANIM_FRAME_BYTES) & mask, (
        f"{what}: the STORE was not masked, which is the other half of the asymmetry")


def test_slot23s_hover_cursor_indexes_on_the_RAW_byte_too():
    """The ninth site, and the sharpest: WB_ACTOR_TYPE04_HOVER's mask is $7f, so a cursor of $80
    reads the word ABOVE the table and ADDS IT TO THE Y. Slot 4 has the same defect at its own
    copy; what this row adds is that slot 23 reaches it through the SHORT encoding."""
    what = f"{TYPE23} hover over-read"
    y, cursor = STAND_Y, wb("ACTOR_TYPE04_HOVER_MASK") + 1
    hover = wb("ACTOR_TYPE04_HOVER")
    assert _image_word(hover + cursor) != _image_word(hover), (
        f"{what}: the word past the table repeats its first, so this case would prove nothing")
    pokes = _family37_pokes(what, 23, {ACTOR + ACTOR_Y: word(y), ACTOR + FIELD_30: bytes([cursor])})

    written = program_writes(_run_handler(TYPE23, what, pokes))
    delta = s16(_image_word(hover + cursor))
    assert _written_word(written, ACTOR, ACTOR_Y) == (y + delta) & 0xffff
    assert written[ACTOR + FIELD_30] == (cursor + ANIM_FRAME_BYTES) & wb("ACTOR_TYPE04_HOVER_MASK")


# --- the five holes the mutation sweep found, closed ----------------------------------------------
@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_hopper_turns_round_when_the_blocked_probes_WHOLE_WORD_is_zero(slot):
    """THE SWEEP FOUND THIS UNPINNED: every hopper case above walked a CLEAR row, so
    `step_word_was_blocked_at_column_0` replaced by the tier's ordinary byte test survived. This is
    the arm where the two AGREE — a step blocked in map column 0 reports $0000 — and the case below
    is the one that separates them."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} blocked in column 0"
    pokes = _block_the_walk(_family37_pokes(what, slot, {
        ACTOR + ACTOR_X: word(WALK_X_AT_COLUMN_0), ACTOR + FIELD_30: bytes([7]),
        # The followed record to the RIGHT, so `bsr $67c2` leaves the side bit CLEAR and the record
        # walks INTO the blocked row rather than away from it.
        FOLLOWED_DEFAULT + ACTOR_X: word(0x0600),
        ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}))

    written = program_writes(_run_handler(name, what, pokes))
    assert written[ACTOR + ACTOR_FLAGS] & (1 << SIDE_BIT), (
        f"{what}: the side bit did not flip, so the word test read something other than zero")


# A record whose LEFT probe goes negative: `x - half_width - step` below zero parks it at its own
# half-width and reports the probe's CELL INDEX, which is negative — so the byte above the outcome
# is $ff and the whole word is not zero, where the outcome BYTE alone is still "blocked".
WALK_X_OFF_THE_LEFT_EDGE = 2


@pytest.mark.parametrize("slot", HOPPER_SLOTS, ids=lambda v: f"slot{v:02d}")
def test_the_hopper_does_NOT_turn_when_the_left_probe_runs_off_the_map(slot):
    """THE MUTANT THIS CATCHES, and the reason the pair exists: with the tier's ordinary `tst.b` the
    record turns here and the original does not. Slot 28 carries the same pair one handler over."""
    name = f"actor_behavior_type{slot:02d}"
    what = f"{name} blocked off the left edge"
    side = 1 << SIDE_BIT
    pokes = _family37_pokes(what, slot, {
        ACTOR + ACTOR_X: word(WALK_X_OFF_THE_LEFT_EDGE), ACTOR + FIELD_30: bytes([7]),
        # ...and to the LEFT, so the record walks left into the edge.
        FOLLOWED_DEFAULT + ACTOR_X: word(0),
        ACTOR + ACTOR_FLAGS: bytes([side | (1 << SUPPORTED_BIT)])})

    written = program_writes(_run_handler(name, what, pokes))
    assert written.get(ACTOR + ACTOR_FLAGS, side) & side, (
        f"{what}: the side bit flipped, so the test read the outcome BYTE rather than the word")
    assert _written_word(written, ACTOR, ACTOR_X) == _image_half_width(pokes), (
        f"{what}: the probe did not park the record at its own half-width")


def _tick_that_draws(pokes, predicate):
    """The generalisation `_tick_that_draws_zero` is one case of: a WB_FRAME_TICK whose `rng_next`
    word satisfies `predicate`. The odds mask needs a draw that is zero under HALF the mask and
    nonzero under the whole of it, which no "comes up zero" scan can produce."""
    image = bytearray(harness.make_image(pokes))
    for tick in range(0x400):
        image[FRAME_TICK:FRAME_TICK + WORD_BYTES] = word(tick & 0xffff)
        drawn, _counters = model_rng(bytes(image), 0)
        if predicate(drawn):
            return tick & 0xffff
    raise AssertionError("no frame tick in 0..$3ff makes this draw satisfy the predicate")


def test_slot21s_odds_mask_is_the_WHOLE_five_bits():
    """THE SWEEP FOUND THIS UNPINNED: narrowing `andi.w #$1f` to `#$f` survived, because every draw
    the cases above reached was either zero under both masks or nonzero under both. The separating
    draw is one whose low five bits are exactly $10 — zero under the narrower mask and not under the
    real one — and on it the record must NOT fire."""
    what = f"{TYPE21} draw that only a narrower mask would pass"
    half = TYPE21_SHOT_ODDS_MASK >> 1
    pokes = _family37_pokes(what, 21, {ACTOR + FIELD_30: bytes([ST_BYTE]),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(IN_REACH_X)})
    pokes[FRAME_TICK] = word(_tick_that_draws(
        pokes, lambda drawn: (drawn & half) == 0 and (drawn & TYPE21_SHOT_ODDS_MASK) != 0))
    drawn, counters = model_rng(harness.make_image(pokes), 0)

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    assert ACTOR + FIELD_30 not in written, (
        f"{what}: the draw was {drawn:#06x} and the record fired anyway")


# THE GEOMETRY THAT SEPARATES $6528's X-FLAG RESTORE from a port that never restores the bit. The
# `asr.w #1,d2` at $655c leaves the shifted-out bit in X and the `roxl.w #1,d2` at $6564 puts it
# back, so the halving is exact on the arm where no `addq.w #1,d4` intervenes — and that changes the
# direction code, and the table entry, only for an ODD delta at a ratio near the boundary. Found by
# sweeping the model over +-100 pixels rather than guessed.
AIM_ODD_DX, AIM_ODD_DY = -99, 98


def test_slot21s_aim_restores_the_bit_the_HALVING_shifted_out():
    """THE SWEEP FOUND THIS UNPINNED: `restored_low_bit = 0` — a port that simply halves and doubles
    — survived all four geometries above, because none of them reached the second ratio test with an
    odd delta. This one does, and the entry it lands on is a different direction."""
    what = f"{TYPE21} firing at an odd delta"
    x, y = 0x0100, STAND_Y
    followed_x, followed_y = x + AIM_ODD_DX, y + AIM_ODD_DY
    pokes = _family37_pokes(what, 21, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
        ACTOR + FIELD_30: bytes([ST_BYTE]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x),
        FOLLOWED_DEFAULT + ACTOR_Y: word(followed_y)})
    pokes[FRAME_TICK] = word(_tick_that_draws_zero(pokes, TYPE21_SHOT_ODDS_MASK))
    image = harness.make_image(pokes)
    _drawn, counters = model_rng(image, 0)
    dx, dy = _aim_velocity(image, x, y, followed_x, followed_y, TYPE21_AIM_ROW)

    written = program_writes(_run_handler(TYPE21, what, pokes, hw_seed=leaf.hw_declared(),
                                          band=_handler_band(TYPE21) + merge_bands(counters)))
    assert written[FIRST_HIGH_RECORD + FIELD_30] == dx & 0xff
    assert written[FIRST_HIGH_RECORD + FIELD_31] == dy & 0xff


# THE TWO FOLLOWED-RECORD X VALUES THAT SEPARATE THE THREADED ENTRY X. $5c6e's last arithmetic on
# the path to its `rts` is `addi.w #$16,d5` on the followed record's x, so the carry it leaves — and
# therefore the BCD subtract's entry extend two calls later — is set only for an x within
# WB_ACTOR_POINT_RIGHT of the word's top.
THIEF_X_CARRY_CLEAR = 0x0100
THIEF_X_CARRY_SET = (0x10000 - wb("ACTOR_POINT_RIGHT")) & 0xffff


@pytest.mark.parametrize("x,extend", [(THIEF_X_CARRY_CLEAR, 0), (THIEF_X_CARRY_SET, 1)],
                         ids=["entry-x-clear", "entry-x-set"])
def test_slot23s_bcd_subtract_THREADS_the_x_the_overlap_mask_left(x, extend):
    """THE SWEEP FOUND THIS UNPINNED: forcing the entry extend to 0 survived, because every thief
    case above sat at an x whose `addi.w #$16` does not carry. Here the two rows differ by ONE unit
    of gold, which is what says the bit is threaded and not assumed."""
    what = f"{TYPE23} robbing from x {x:#06x}"
    purse = 0x0500
    pokes = _thief_pokes(what, purse, {ACTOR + ACTOR_X: word(x),
                                       FOLLOWED_DEFAULT + ACTOR_X: word(x)})
    expected = bcd_expected(purse, TYPE23_STEAL_MAX, BCD_COUNTER_LEN, True, extend).value
    other = bcd_expected(purse, TYPE23_STEAL_MAX, BCD_COUNTER_LEN, True, 1 - extend).value
    assert expected != other, f"{what}: the two extends give the same purse, so this proves nothing"

    info = _run_handler(TYPE23, what, pokes, band=_thief_band(pokes))
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, what) == expected, (
        f"{what}: the entry extend the subtract read was not the one $5c6e left")


@pytest.mark.parametrize("followed_x,side,frames", [(0x0010, 1 << SIDE_BIT, "ACTOR_TYPE23_DEAD_RIGHT"),
                                                    (0x0600, 0, "ACTOR_TYPE23_DEAD_LEFT")],
                         ids=["followed-left", "followed-right"])
def test_slot23s_death_arm_recoils_AWAY_out_of_the_table_that_names_the_step(followed_x, side,
                                                                            frames):
    """THE SWEEP FOUND THIS UNPINNED: slot 23's death arm had no case at all, so exchanging its two
    tables survived. It is slot 4's arm — no settle, a WB_ACTOR_TYPE23_DEAD_STEP recoil AWAY unless
    the record is already marked, and a table named by the SAME branch that picked the step."""
    what = f"{TYPE23} dying, followed at {followed_x:#06x}"
    x, step = 0x0100, wb("ACTOR_TYPE23_DEAD_STEP")
    pokes = _family37_pokes(what, 23, {
        ACTOR + ACTOR_X: word(x), ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
        ACTOR + ACTOR_FLAGS: bytes([side]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x)})

    written = program_writes(_run_handler(TYPE23, what, pokes))
    # SET means the followed record is to the LEFT, so the recoil walks RIGHT.
    assert _written_word(written, ACTOR, ACTOR_X) == x + (step if side else -step)
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(wb(frames)), (
        f"{what}: the other death table was published")


# --- slot 23's LIVE arm, which no case reached until the sweep said so ----------------------------
# `_walk_pokes_for` parks the followed record at $0600 — outside WB_ACTOR_CHASE_REACH — and
# `_thief_pokes` overlaps it into the TOUCHED arm, so every slot-23 case above ran either the hover
# alone or the theft. Exchanging the two fly tables and widening the step survived the whole suite.
# These rows put the followed record INSIDE the reach and clear of the actor's box (its y is far
# below, which the reach test does not look at).
CHASE_IN_REACH_LEFT = 0x0100 - 0x40
CHASE_IN_REACH_RIGHT = 0x0100 + 0x40
CHASE_CLEAR_Y = 0x0600


@pytest.mark.parametrize("followed_x,step,frames",
                         [(CHASE_IN_REACH_LEFT, -1, "ACTOR_TYPE23_FLY_LEFT"),
                          (CHASE_IN_REACH_RIGHT, 1, "ACTOR_TYPE23_FLY_RIGHT")],
                         ids=["followed-left", "followed-right"])
def test_slot23_closes_on_a_followed_record_INSIDE_its_reach(followed_x, step, frames):
    """The chase: one WB_ACTOR_TYPE23_FLY_STEP pixel toward the followed record and the fly table
    the facing names, published on the RAW cursor. Both facings, so the two tables are separated."""
    what = f"{TYPE23} chasing {followed_x:#06x}"
    x, cursor = 0x0100, 6
    pokes = _family37_pokes(what, 23, {
        ACTOR + ACTOR_X: word(x), ACTOR + FIELD_18: bytes([cursor]),
        FOLLOWED_DEFAULT + ACTOR_X: word(followed_x),
        FOLLOWED_DEFAULT + ACTOR_Y: word(CHASE_CLEAR_Y)})

    written = program_writes(_run_handler(TYPE23, what, pokes))
    assert _written_word(written, ACTOR, ACTOR_X) == x + step * wb("ACTOR_TYPE23_FLY_STEP"), (
        f"{what}: the chase step was not one pixel toward the followed record")
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(wb(frames) + cursor), (
        f"{what}: the other fly table was published")
    assert written[ACTOR + FIELD_18] == cursor + ANIM_FRAME_BYTES


def test_slot23_LEVEL_with_the_followed_record_leaves_for_SLOT_4s_publish():
    """THE HEADLINE REUSE, finally EXECUTED on both cores. `cmp.w (a1),d0 / beq` skips the two
    probes, and on the arm where the side bit is CLEAR the handler does `lea $482c,a1 / bra.w $2840`
    — leaving its own extent for actor_behavior_type04's publish-and-hover tail. An equal x is the
    ONLY state that takes it, and an equal x also leaves the side bit clear (`bsr $67c2` raises it
    only where the actor is STRICTLY to the right), so this one seed is the whole path."""
    what = f"{TYPE23} level with the followed record"
    x, y, cursor = 0x0100, STAND_Y, 6
    pokes = _family37_pokes(what, 23, {
        ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y), ACTOR + FIELD_18: bytes([cursor]),
        ACTOR + FIELD_30: bytes([4]),
        FOLLOWED_DEFAULT + ACTOR_X: word(x), FOLLOWED_DEFAULT + ACTOR_Y: word(CHASE_CLEAR_Y)})

    written = program_writes(_run_handler(TYPE23, what, pokes))
    assert ACTOR + ACTOR_X not in written, f"{what}: a record level with its target still stepped"
    assert _written_word(written, ACTOR, ACTOR_SPRITE) == _image_word(
        wb("ACTOR_TYPE23_FLY_RIGHT") + cursor), (
        f"{what}: slot 4's publish did not run out of slot 23's own table")
    # ...and the hover BELOW that publish is slot 4's too, so the frame ends with the y stepped.
    assert _written_word(written, ACTOR, ACTOR_Y) == (
        y + s16(_image_word(wb("ACTOR_TYPE04_HOVER") + 4))) & 0xffff


# --- the reach-point arm of the threaded entry X -------------------------------------------------
# Every thief row above hard-seeds the followed record's sprite to 0, so `overlap_mask_exit_extend`
# only ever took its `addi.w #$16` arm — `return 1` outright survived. These two put the reach-point
# sprite on the record, which is the state in which $5c6e's LAST arithmetic is `subi.w #$9,d6` on
# its y instead, and drive that borrow both ways.
POINT_SPRITE = wb("FOLLOWED_SPRITE_POINT_LO")


@pytest.mark.parametrize("y,extend", [(POINT_UP - 1, 1), (POINT_UP + 1, 0)],
                         ids=["y-below-the-borrow", "y-above-it"])
def test_slot23s_entry_X_comes_off_the_Y_when_the_followed_record_has_a_REACH_POINT(y, extend):
    """`cmp.w #$117,d7 / beq` picks which of the two arithmetics runs last, so the sprite decides
    WHICH WORD the BCD subtract's entry extend comes off. The two rows differ by one unit of gold."""
    what = f"{TYPE23} robbing a reach-point record at y {y:#06x}"
    purse = 0x0500
    pokes = _thief_pokes(what, purse, {
        ACTOR + ACTOR_Y: word(y),
        FOLLOWED_DEFAULT + ACTOR_SPRITE: word(POINT_SPRITE),
        FOLLOWED_DEFAULT + ACTOR_Y: word(y)})
    expected = bcd_expected(purse, TYPE23_STEAL_MAX, BCD_COUNTER_LEN, True, extend).value
    other = bcd_expected(purse, TYPE23_STEAL_MAX, BCD_COUNTER_LEN, True, 1 - extend).value
    assert expected != other, f"{what}: the two extends give the same purse, so this proves nothing"

    info = _run_handler(TYPE23, what, pokes, band=_thief_band(pokes))
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, what) == expected, (
        f"{what}: the entry extend came off the x arm, not the reach point's y arm")


# --- slot 38 ($5408) and the PICKUP TIER (batch 38) ------------------------------------------------
#
# THE FIRST DISPATCH ROW WHOSE FRAME REACHES A SECOND DISPATCH. Everything the record does while it
# waits is slot 31's; what is new is the collect arm, which reads the record's own KIND row out of
# WB_ACTOR_KIND_TABLE and pays what the row says. The fourteen handlers behind
# WB_PICKUP_EFFECT_TABLE are test_effects.py's — this section drives the ARITHMETIC that reaches
# them, the refusal when the index leaves the table, and the two arms above it.
#
# EVERY COLLECT CASE HERE ENDS IN `actor_defeat_and_score`, so its band is `_foreign_band`'s and its
# kill count is seeded ABOVE the respawn threshold: the retire tail draws no kind, which keeps the
# frame's ONE video-counter read the payout's own (a modeled address may be read once a run).
PICKUP_ENTRY_ADDRS = [_image_word(PICKUP_EFFECT_TABLE + row * PICKUP_EFFECT_ENTRY + WORD_BYTES)
                      | (_image_word(PICKUP_EFFECT_TABLE + row * PICKUP_EFFECT_ENTRY) << 16)
                      for row in range(PICKUP_EFFECT_ENTRIES)]

# A kind whose row this section OWNS: seeded whole, so no case rests on a shipped row's contents.
# It is inside the 22 rows the table really has, which is what keeps the `lea` arithmetic honest.
PICKUP_KIND = 5
PICKUP_ROW = KIND_TABLE + PICKUP_KIND * KIND_RECORD_BYTES
# ...and a kill count past `actor_defeat_and_score`'s `cmpi.w #$2,6(a1) / ble`, so the defeat
# RETIRES the slot instead of drawing a new kind through the PRNG.
PICKUP_KILLS_PAST_RESPAWN = 0x0010
# A stage number that is a plausible packed-BCD one and not a round figure, so a port that dropped
# the `move.w $bd88,d0` and folded in a zero would differ in the counter.
PICKUP_STAGE_NUMBER = 0x0012
# ...and the meter the two meter grants move, seeded well below its maximum so `pickup_effect_add4_meter`
# STORES rather than skipping (its skip arm is test_effects.py's — what this file's rows say is only
# that entry 11 reached it at all).
PICKUP_METER_SEED = 0x0010
PICKUP_METER_MAX = 0x0028


def _pickup_pokes(what, kind, effect_index, score=0, fields=None, collected=True):
    """A type-38 record on ACTOR whose KIND row this case owns outright.

    Built on `_collectable_pokes` (the tier's collect geometry) plus `_award_pokes` (everything the
    gold arm reads) plus `_template_environment` (everything the defeat reads), so nothing about the
    seeding is restated here — only what this row decides: the kind byte, the row's score longword,
    the row's effect index, the stage number the gold arm pays, and the meter the two meter grants
    move.

    THE `followed_x` OVERLAY IS CONDITIONAL, and that is the whole of `collected=False`'s premise.
    `_award_pokes` names the followed record's x because it is the draw's non-hardware entropy — but
    that x is also what `_band5a_pokes` parks FAR AWAY to shut the contact test, so overlaying it
    unconditionally left only the y separating the two records and the waiting cases were resting on
    a geometry nobody had stated. Every waiting case now also runs `_assert_contact(.., False)`.
    """
    award = _award_pokes(0, followed_x=COLLECT_X)
    if not collected:
        del award[FOLLOWED_DEFAULT]
    base = leaf.overlay(award, {
        ACTOR + KIND: bytes([kind]),
        PICKUP_ROW + KIND_SCORE: longword(score),
        PICKUP_ROW + KIND_PICKUP_EFFECT: word(effect_index),
        STAGE_NUMBER: word(PICKUP_STAGE_NUMBER),
        BONUS_DIGITS_AT: bytes([DIGIT_BLANK] * BONUS_DIGIT_COUNT),
        # The two METER grants (entries 10 and 11) are the only handlers whose witness is a word
        # rather than a HUD slot, so the meter is an INPUT of the fourteen-way case and is stated
        # here: well below the maximum, so the raise stores rather than being skipped.
        METER_VALUE: word(PICKUP_METER_SEED), METER_MAX: word(PICKUP_METER_MAX),
        PANEL_FRAME_DELAY: word(PANEL_FRAME_DELAY_INIT ^ 0xffff),
    }, fields or {})
    pokes = _collectable_pokes(what, 38, base, collected=collected)
    _template_environment(case_salt(what), pokes)
    for template in range(TEMPLATE_SLOTS):
        pokes[TEMPLATE_TABLE + template * SPAWN_RECORD_BYTES + wb("SPAWN_KILL_COUNT")] = word(
            PICKUP_KILLS_PAST_RESPAWN)
    return pokes


def _pickup_band(image, own):
    """What a collect frame may write: the SFX trigger's set, whatever the arm itself writes, and
    then the defeat's — composed by `_foreign_band`, which applies `own` to a copy of the image
    FIRST so the defeat's model reads the state it really would."""
    return (_foreign_band(image, own, "defeat")
            + merge_bands(_sfx_bytes(image, REQUEST9_SFX, SND_CHANNEL_A)))


def test_slot38_pays_the_STAGE_NUMBER_as_gold_when_its_kind_is_below_the_threshold():
    """`move.w $bd88,d0` and then `hud_award_gold_from_descriptor`'s own five calls — the draw, both
    accumulators, the digits inside message 3 and the message posted. The award model is the one
    $517a's cases compare against, handed this arm's amount instead of the descriptor's, so the two
    spellings of the payout cannot disagree."""
    what = "actor_behavior_type38_pickup gold arm"
    pokes = _pickup_pokes(what, PICKUP_KIND_FIRST - 1, 0)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)
    paid = _model_award(image, award=PICKUP_STAGE_NUMBER)

    info = _run_handler(TYPE38, what, pokes, band=_pickup_band(image, paid),
                        hw_seed=VCOUNT_ORDERED)
    written = program_writes(info)
    for addr, value in paid.items():
        assert written[addr] == value, (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the payout model's {value:#04x}")
    assert written[TEXT_REQUEST] == MESSAGE_GOLD_GET, f"{what}: the gold message was not posted"


# A kind byte with its top bit set. `cmpi.b #$2,20(a0) / bge` is a SIGNED byte compare, so this is
# BELOW the threshold and takes the gold arm — where an unsigned reading would send it to row 255's
# address, 4080 bytes past the table.
PICKUP_KIND_NEGATIVE = 0xff


def test_the_kind_compare_is_a_SIGNED_byte_compare():
    """The row that separates `bge` from `bhs`. A kind of $ff pays GOLD; read unsigned it would have
    indexed row 255 instead and paid whatever longword sits 4080 bytes above the table."""
    what = "actor_behavior_type38_pickup with a negative kind byte"
    pokes = _pickup_pokes(what, PICKUP_KIND_NEGATIVE, 0)
    image = harness.make_image(pokes)
    paid = _model_award(image, award=PICKUP_STAGE_NUMBER)

    info = _run_handler(TYPE38, what, pokes, band=_pickup_band(image, paid),
                        hw_seed=VCOUNT_ORDERED)
    assert program_writes(info)[TEXT_REQUEST] == MESSAGE_GOLD_GET, (
        f"{what}: the kind arm ran, so the compare was read as unsigned")


# The score the kind-row cases pay, and it is chosen for what it makes VISIBLE: five nonzero packed
# BCD digits, so `text_post_bonus_points_a4be` draws all five and no leading blank — and a sixth
# nibble above them that must NOT appear, which is what says only the low five are drawn.
PICKUP_ROW_SCORE = 0x00612345


def _bonus_digits_for(addend):
    """The five characters $6938 leaves at WB_TEXT_BONUS_DIGITS, as an independent statement of the
    routine: nibbles 4..0 of the addend, most significant first, with LEADING zeros drawn as spaces
    and every other nibble as `$30 + nibble` however large it is."""
    nibbles = [(addend >> (BCD_DIGIT_BITS * shift)) & BCD_DIGIT_MASK
               for shift in reversed(range(BONUS_DIGIT_COUNT))]
    out, leading = [], True
    for nibble in nibbles:
        leading = leading and nibble == 0
        out.append(DIGIT_BLANK if leading else DIGIT_ZERO + nibble)
    return bytes(out)


def test_slot38_pays_the_kind_rows_score_and_draws_it_into_the_bonus_message():
    """The kind arm: `move.l 4(a1),d0 / beq` nonzero, so the longword goes into the score AND into
    the five digits, and the message the digit routine posts is the one it patched."""
    what = "actor_behavior_type38_pickup scored kind"
    pokes = _pickup_pokes(what, PICKUP_KIND, 0, score=PICKUP_ROW_SCORE)
    image = harness.make_image(pokes)
    # The row's score goes in with a PROVED-clear entry X: `lsl.l #4,d0` above it leaves X the
    # bit shifted out of a zero-extended byte, which is bit 28 and always 0.
    scored = bcd_expected(int.from_bytes(image[BCD_SCORE:BCD_SCORE + BCD_SCORE_LEN], "big"),
                          PICKUP_ROW_SCORE, BCD_SCORE_LEN, False, 0)
    own = {}
    _put(own, BCD_ADDEND, PICKUP_ROW_SCORE, LONGWORD_BYTES)
    _put(own, BCD_SCORE, scored.value, BCD_SCORE_LEN)
    for offset, character in enumerate(_bonus_digits_for(PICKUP_ROW_SCORE)):
        own[BONUS_DIGITS_AT + offset] = character
    own[TEXT_REQUEST] = MESSAGE_BONUS_POINTS
    _put(own, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)

    info = _run_handler(TYPE38, what, pokes, band=_pickup_band(image, own))
    written = program_writes(info)
    assert bytes(written[BONUS_DIGITS_AT + offset]
                 for offset in range(BONUS_DIGIT_COUNT)) == _bonus_digits_for(PICKUP_ROW_SCORE), (
        f"{what}: the digits drawn are not nibbles 4..0 of the row's score")
    assert written[TEXT_REQUEST] == MESSAGE_BONUS_POINTS, f"{what}: the bonus message was not posted"


def test_slot38_skips_both_score_calls_when_the_rows_longword_is_zero():
    """`beq.w $5492`, and the control for the row above: a zero score writes NEITHER accumulator NOR
    a digit, which is what says the branch is on the longword and not on some other field."""
    what = "actor_behavior_type38_pickup unscored kind"
    pokes = _pickup_pokes(what, PICKUP_KIND, 0, score=0)
    image = harness.make_image(pokes)

    info = _run_handler(TYPE38, what, pokes, band=_pickup_band(image, {}))
    written = program_writes(info)
    assert BONUS_DIGITS_AT not in written, f"{what}: a zero score still drew digits"
    assert written.get(TEXT_REQUEST) != MESSAGE_BONUS_POINTS, f"{what}: it posted the bonus message"


# WHICH BYTE EACH OF THE FOURTEEN LEAVES BEHIND, so a case can say "this entry ran" rather than only
# "the frame ended". Every value is include/wonderboy.h's, and the addresses are the ones
# test_effects.py's own cases assert on — this table names one witness per entry and nothing else.
PICKUP_EFFECT_WITNESS = {
    0: None,                                            # the bare `rts` writes nothing at all
    1: (wb("HUD_SLOT_BBC4"), wb("PICKUP_SLOT_BBC4_VALUE")),
    2: (wb("HUD_SLOT_BBC2"), wb("PICKUP_SLOT_WING_BOOTS_VALUE")),
    3: (wb("HUD_SLOT_BBBE"), wb("PICKUP_SLOT_HELMET_VALUE")),
    4: (wb("HUD_SLOT_BBC0"), wb("PICKUP_SLOT_GAUNTLET_VALUE")),
    5: (wb("HUD_SLOT_BBC6"), wb("PICKUP_SLOT_REVIVAL_VALUE")),
}
# ...and the TWO entries whose witness is a word rather than a HUD slot: the meter grants. Neither
# posts a message and neither writes a slot, so without these two rows they would rest entirely on
# the band and execute no assertion of their own. The values are what the seed above makes them:
# entry 10 fills the meter to its maximum, entry 11 raises it by WB_PICKUP_METER_STEP (the seed is
# far enough below the maximum that the raise STORES — its skip arm is test_effects.py's).
PICKUP_METER_WITNESS = {10: PICKUP_METER_MAX, 11: PICKUP_METER_SEED + PICKUP_METER_STEP}
PICKUP_EFFECT_MESSAGE = {
    2: wb("TEXT_MESSAGE_WING_BOOTS"), 3: wb("TEXT_MESSAGE_HELMET"),
    4: wb("TEXT_MESSAGE_GAUNTLET"), 5: wb("TEXT_MESSAGE_REVIVAL"),
    6: wb("TEXT_MESSAGE_FIRE_BALLS"), 7: wb("TEXT_MESSAGE_BOMBS"),
    8: wb("TEXT_MESSAGE_WIND_SPOUTS"), 9: wb("TEXT_MESSAGE_LIGHTNING"),
    12: wb("TEXT_MESSAGE_ATTACK_UP"), 13: wb("TEXT_MESSAGE_VANISHED"),
}


def _pickup_effect_band(image, own):
    """`_pickup_band` widened by the union of what the FOURTEEN can write, which is what lets one
    case drive every entry: the six HUD slots as one span, the meter and the panel countdown, the
    record list and its write pointer, the scene exit request, the followed record (the vanish
    grant writes three of its bytes) and the message pair."""
    return _pickup_band(image, own) + [
        (wb("HUD_SLOT_BBBE"), 12), (METER_VALUE, WORD_BYTES), (PANEL_FRAME_DELAY, WORD_BYTES),
        (wb("EFFECT_RECORD_WRITE_PTR"), LONGWORD_BYTES), (wb("EFFECT_RECORD_LIST"), 0x104),
        (wb("SCENE_EXIT_REQUEST"), WORD_BYTES), (FOLLOWED_DEFAULT, RECORD_BYTES),
        (TEXT_REQUEST, 1), (TEXT_LIFETIME_REQUEST, WORD_BYTES)]


@pytest.mark.parametrize("index", range(PICKUP_EFFECT_ENTRIES), ids=lambda v: f"entry{v:02d}")
def test_slot38_runs_the_entry_its_kind_rows_index_names(index):
    """ALL FOURTEEN, driven through the dispatch rather than entered directly — which is what makes
    this a case about the arithmetic at $5492..$54a4 and not a second copy of test_effects.py.

    THE WITNESS DIFFERS BY ENTRY and every entry has one. Ten of the fourteen post a MESSAGE naming
    themselves. THREE post none — entry 1, which writes a HUD slot, and entries 10 and 11, which
    write the METER and the panel countdown. Entry 0 is the one that leaves NOTHING behind, so its
    row asserts the absence — which is also what separates it from the refusal below.
    """
    what = f"actor_behavior_type38_pickup effect {index}"
    pokes = _pickup_pokes(what, PICKUP_KIND, index)
    image = harness.make_image(pokes)
    info = _run_handler(TYPE38, what, pokes, band=_pickup_effect_band(image, {}))
    written = program_writes(info)

    if index in PICKUP_EFFECT_MESSAGE:
        assert written[TEXT_REQUEST] == PICKUP_EFFECT_MESSAGE[index], (
            f"{what}: the message posted is not the one this entry is named for")
    slot = PICKUP_EFFECT_WITNESS.get(index)
    if slot is not None:
        assert _written_word(written, slot[0]) == (slot[1] << 8) | wb("HUD_SLOT_CHANGED"), (
            f"{what}: the entry's HUD slot was not written")
    meter = PICKUP_METER_WITNESS.get(index)
    if meter is not None:
        assert _written_word(written, METER_VALUE) == meter, (
            f"{what}: the meter ended at {_written_word(written, METER_VALUE):#06x}, not "
            f"{meter:#06x}")
        assert _written_word(written, PANEL_FRAME_DELAY) == PANEL_FRAME_DELAY_INIT, (
            f"{what}: the panel countdown was not restarted")
    if index == 0:
        assert TEXT_REQUEST not in written, f"{what}: the bare `rts` posted a message"


# THE HANDLER'S OWN POST OVERWRITES THE BONUS BOX, and until this case nothing executed both.
# Every fourteen-way row above seeds a ZERO score (so the bonus is never posted) and the one nonzero
# score row uses entry 0 (which posts nothing), so no run had a bonus post AND a handler post live —
# and moving `run_pickup_effect` ABOVE the score/bonus pair survived the whole suite. These four
# rows put the two together: the score arm posts WB_TEXT_MESSAGE_BONUS_POINTS at $548e and the
# handler runs at $54a4, so what the frame LEAVES in WB_TEXT_REQUEST is the handler's id — the
# entry's own message for entry 2, and a ZERO for the three that post none, which takes the bonus
# box back down before it is ever composed. That zero is the CANCEL the plates claim.
PICKUP_POST_ORDER_INDICES = (1, 2, 10, 11)


@pytest.mark.parametrize("index", PICKUP_POST_ORDER_INDICES, ids=lambda v: f"entry{v:02d}")
def test_the_effect_handlers_post_lands_ON_TOP_of_the_bonus_box(index):
    what = f"actor_behavior_type38_pickup scored kind with effect {index}"
    expected = PICKUP_EFFECT_MESSAGE.get(index, TEXT_REQUEST_NONE)
    assert expected != MESSAGE_BONUS_POINTS, (
        f"{what}: this entry posts the bonus id itself, so the row could not tell the two apart")
    pokes = _pickup_pokes(what, PICKUP_KIND, index, score=PICKUP_ROW_SCORE)
    image = harness.make_image(pokes)
    _assert_contact(image, what, True)

    info = _run_handler(TYPE38, what, pokes, band=_pickup_effect_band(image, {}) + [
        (BONUS_DIGITS_AT, BONUS_DIGIT_COUNT), (BCD_ADDEND, LONGWORD_BYTES),
        (BCD_SCORE, BCD_SCORE_LEN)])
    written = program_writes(info)
    # The bonus box really WAS asked for on this run — the digits it patched are still there — and
    # the handler's post then landed on top of the id.
    assert bytes(written[BONUS_DIGITS_AT + offset]
                 for offset in range(BONUS_DIGIT_COUNT)) == _bonus_digits_for(PICKUP_ROW_SCORE), (
        f"{what}: the score arm never ran, so nothing was there to overwrite")
    assert written[TEXT_REQUEST] == expected, (
        f"{what}: the frame left {written[TEXT_REQUEST]:#04x} in WB_TEXT_REQUEST, not the "
        f"{expected:#04x} the handler posts — the two posts ran in the wrong order")


# --- the refusal, and the ALIAS structure above it -------------------------------------------------
# `move.w 10(a1),d0 / add.w d0,d0 / add.w d0,d0 / movea.l 0(a1,d0.w),a1 / jsr (a1)` — the state-65
# class. The scale wraps in sixteen bits and the extension word sign-extends, so what selects an
# entry is the OFFSET and not the index: entry `s` is reached by four index values a $4000 apart.
#
# A REFUSAL HAS NO DIFFERENTIAL, exactly as the behaviour dispatch's does not: the original reads a
# longword outside the table and `jsr`s through it. So the enumeration below runs the reconstruction
# ALONE, and what it states is the SET.
PICKUP_ALIAS_STRIDE = 0x10000 // PICKUP_EFFECT_ENTRY


def _pickup_dispatched(index):
    """Which entry `index` reaches, or None — this battery's own model of the wrapped offset."""
    offset = s16((index * PICKUP_EFFECT_ENTRY) & 0xffff)
    if 0 <= offset < PICKUP_EFFECT_ENTRIES * PICKUP_EFFECT_ENTRY:
        return offset // PICKUP_EFFECT_ENTRY
    return None


def test_the_pickup_index_aliases_four_ways_and_everything_else_is_refused():
    """The counting half, stated once rather than per shard: 56 of the 65,536 index values reach one
    of the fourteen entries and 65,480 do not. A guard on the RAW index would have refused 42 of the
    56 — the same defect the behaviour dispatch's own alias bands exist to rule out."""
    dispatched = [index for index in range(0x10000) if _pickup_dispatched(index) is not None]
    bands = sorted({index & ~(PICKUP_ALIAS_STRIDE - 1) for index in dispatched})
    assert len(dispatched) == PICKUP_EFFECT_ENTRIES * len(bands) == 56
    assert bands == [0x0000, 0x4000, 0x8000, 0xc000]
    assert len([i for i in dispatched if i >= PICKUP_EFFECT_ENTRIES]) == PICKUP_EFFECT_ENTRIES * 3


def test_the_four_dispatch_CODES_collide_with_no_entry_the_table_can_hand_back():
    """WHY THE REFUSAL IS A CODE AND NOT AN ADDRESS. Slot 7's state `jsr` reports the address it
    would have entered; here the answer has to separate "entry 0 ran" from "no entry ran", and entry
    0's own address would do — but the span the index reads holds ZEROS, and 0 is
    WB_ACTOR_DISPATCH_RAN. So behavior.h spends a fourth code, and this case checks the image's own
    fourteen longwords against all four rather than assuming none collides."""
    codes = {DISPATCH_RAN, DISPATCH_REFUSED, wb("ACTOR_DISPATCH_UNBOUNDED"),
             DISPATCH_PICKUP_REFUSED}
    assert len(codes) == 4, "two of the dispatch codes are the same value"
    assert not codes & set(PICKUP_ENTRY_ADDRS), (
        f"an entry of {PICKUP_EFFECT_TABLE:#x} collides with a dispatch code")
    # ...and the span really does hold zeros, which is the fact that rules the address out.
    below = _image_word(PICKUP_EFFECT_TABLE - PICKUP_EFFECT_ENTRY) << 16 | _image_word(
        PICKUP_EFFECT_TABLE - PICKUP_EFFECT_ENTRY + WORD_BYTES)
    assert below == 0, "the longword below the table is no longer zero"


# Two refused indices whose target longwords DIFFER, so a reconstruction that leaked anything of the
# target into memory would leave two different images. One is just below the table and one just
# above it, which are the two ends the refusal has to hold.
PICKUP_REFUSED_PAIR = (0xffff, PICKUP_EFFECT_ENTRIES)


@pytest.mark.parametrize("index", PICKUP_REFUSED_PAIR, ids=lambda v: f"index{v:04x}")
def test_slot38_refuses_an_index_outside_the_table(index):
    what = f"actor_behavior_type38_pickup effect index {index:#06x}"
    assert _pickup_dispatched(index) is None, f"{what}: this index reaches an entry after all"
    answer, _image = leaf.run_candidate_only(_HANDLER_GLUE[TYPE38](ACTOR),
                                             _pickup_pokes(what, PICKUP_KIND, index))
    assert answer == DISPATCH_PICKUP_REFUSED, (
        f"{what}: the reconstruction answered {answer:#x}, not the pickup refusal")


def test_a_refused_pickup_index_writes_NOTHING_the_target_could_have_told_it():
    """The other half of the refusal, and the one an answer alone does not give: the two refused
    indices above read DIFFERENT longwords, and the images they leave are identical everywhere but
    the index word the case itself seeded. So the refusal is a stop and not a partial run."""
    what = "actor_behavior_type38_pickup refusal"
    images, targets = [], []
    for index in PICKUP_REFUSED_PAIR:
        # ONE salt for both runs: `case_salt` keys the whole tier's seeding, so two `what` strings
        # would make the two images differ everywhere the keyed block does and the comparison below
        # would say nothing.
        pokes = _pickup_pokes(what, PICKUP_KIND, index)
        answer, image = leaf.run_candidate_only(_HANDLER_GLUE[TYPE38](ACTOR), pokes)
        assert answer == DISPATCH_PICKUP_REFUSED
        at = (PICKUP_EFFECT_TABLE + s16((index * PICKUP_EFFECT_ENTRY) & 0xffff)) & BUS_ADDR_MASK
        targets.append(image[at:at + LONGWORD_BYTES])
        images.append(bytearray(image))
    assert targets[0] != targets[1], (
        f"{what}: the two refused indices read the same longword, so this case proves nothing")

    for image in images:
        image[PICKUP_ROW + KIND_PICKUP_EFFECT:PICKUP_ROW + KIND_PICKUP_EFFECT + WORD_BYTES] = b"\0\0"
    differing = [at for at in range(len(images[0])) if images[0][at] != images[1][at]]
    assert not differing, (
        f"{what}: the two refusals left different memory at {[hex(a) for a in differing[:8]]}")


# --- the waiting arm ------------------------------------------------------------------------------
def test_slot38_gives_a_PICKUP_kind_the_flash_countdown_only_while_a32_is_set():
    """`cmpi.b #$2,20(a0) / blt` then `tst.w $a32.w / beq` — two gates, and the write between them is
    the ONE thing this arm does. With the flag clear the frame writes no countdown at all and the
    tick below simply runs the byte down."""
    for a32, flashes in ((1, True), (0, False)):
        what = f"actor_behavior_type38_pickup waiting, a32={a32}"
        pokes = _pickup_pokes(what, PICKUP_KIND, 0, collected=False,
                              fields={FLAG_A32: word(a32),
                                      ACTOR + FIELD_12: word(COLLECT_FIELD_12_IDLE)})
        _assert_contact(harness.make_image(pokes), what, False)
        info = _run_handler(TYPE38, what, pokes)
        written = program_writes(info)
        # The tick below the arm ALWAYS decrements, so what says the flash fired is the value.
        left = (TYPE38_FLASH - 1) if flashes else ((COLLECT_FIELD_12_IDLE & 0xff) - 1)
        assert written[ACTOR + FIELD_12] == left, (
            f"{what}: the countdown byte is {written[ACTOR + FIELD_12]:#04x}, not {left:#04x}")


@pytest.mark.parametrize("kind,relaunches", [(0, True), (1, False)],
                         ids=["kind-zero-relaunches", "kind-one-publishes"])
def test_a_GOLD_kind_waiting_splits_on_whether_its_kind_byte_is_zero(kind, relaunches):
    """`tst.b 20(a0) / bne` below the threshold test: kind 0 runs
    `actor_relaunch_and_anim_5160` (which writes WB_ACTOR_FIELD_30 as well as the sprite) and any
    other gold kind publishes through `actor_select_sprite_by_flag` (which writes only the sprite).
    The two are told apart by the field the first one touches and the second does not."""
    what = f"actor_behavior_type38_pickup waiting, kind {kind}"
    pokes = _pickup_pokes(what, kind, 0, collected=False,
                          fields={ACTOR + FIELD_12: word(COLLECT_FIELD_12_IDLE),
                                  ACTOR + FIELD_30: bytes([4])})
    _assert_contact(harness.make_image(pokes), what, False)
    written = program_writes(_run_handler(TYPE38, what, pokes))
    assert (ACTOR + FIELD_30 in written) is relaunches, (
        f"{what}: the {'relaunch' if relaunches else 'sprite'} arm did not run")
    assert ACTOR + ACTOR_SPRITE in written, f"{what}: no sprite was published either way"


def test_slot38s_countdown_expires_TWICE_like_slot_28s():
    """`subq.b #1,12(a0) / bne` then `bset #6,8(a0) / bne` — the branch reads the bit the `bset` has
    just overwritten, so the FIRST expiry raises the flicker and reloads the byte and the SECOND
    leaves for `actor_defeat_and_score`. It is a BYTE countdown, which is what separates this row
    from slots 30 and 31."""
    what = "actor_behavior_type38_pickup first expiry"
    pokes = _pickup_pokes(what, PICKUP_KIND, 0, collected=False,
                          fields={ACTOR + FIELD_12: bytes([1]),
                                  ACTOR + ACTOR_FLAGS: bytes([0]),
                                  FLAG_A32: word(0)})
    _assert_contact(harness.make_image(pokes), what, False)
    written = program_writes(_run_handler(TYPE38, what, pokes))
    assert written[ACTOR + FIELD_12] == TYPE38_FIELD_12_RELOAD, f"{what}: it did not reload"
    assert written[ACTOR + ACTOR_FLAGS] & (1 << FLICKER_BIT), f"{what}: the flicker stayed down"

    what = "actor_behavior_type38_pickup second expiry"
    pokes = _pickup_pokes(what, PICKUP_KIND, 0, collected=False,
                          fields={ACTOR + FIELD_12: bytes([1]),
                                  ACTOR + ACTOR_FLAGS: bytes([1 << FLICKER_BIT]),
                                  FLAG_A32: word(0)})
    image = harness.make_image(pokes)
    _assert_contact(image, what, False)
    info = _run_handler(TYPE38, what, pokes, band=_foreign_band(image, {}, "defeat"))
    written = program_writes(info)
    assert _written_word(written, ACTOR, ACTOR_X) == FREE_MARKER, (
        f"{what}: the second expiry did not retire the record")
    # THE FREE MARKER ALONE DOES NOT SAY WHICH ARM RAN — the collect arm reaches the same defeat.
    # What separates them is the payout: an EXPIRY pays nothing, so neither accumulator moves and no
    # message is posted, where every collect arm writes at least one of the three.
    assert BCD_ADDEND not in written and TEXT_REQUEST not in written, (
        f"{what}: the record was COLLECTED, not expired — the payout ran")


# --- $6938: the five digits, on its own -----------------------------------------------------------
# Entered DIRECTLY, because what the one caller can hand it is bounded by the 22 shipped kind rows
# and the properties below are about the register: the SWAP that makes nibble 4 the first digit, the
# leading blanks, and the four nibbles above the five drawn that must not appear.
_BONUS_DIGITS = leaf.register_glue(BONUS_DIGITS, [ctypes.c_uint32])

BONUS_ADDENDS = (
    0x00012345,          # five digits, none of them leading zeros
    0x00000005,          # four leading blanks and one digit — the blanking loop's own arm
    0x00099999,          # every drawn nibble at 9
    0xfedc12345 & 0xffffffff,   # nibbles ABOVE the five drawn: they must not reach the string
    0x0000000f,          # a nibble past 9: `addi.b #$30` runs anyway and draws past '9'
)


@pytest.mark.parametrize("addend", BONUS_ADDENDS, ids=[f"{a:08x}" for a in BONUS_ADDENDS])
def test_the_bonus_digits_are_nibbles_4_to_0_with_leading_zeros_blanked(addend):
    what = f"text_post_bonus_points_a4be with {addend:#010x}"
    expected = _bonus_digits_for(addend)
    pokes = {BONUS_DIGITS_AT: bytes([DIGIT_BLANK ^ 0xff] * BONUS_DIGIT_COUNT),
             TEXT_REQUEST: bytes([0]), TEXT_LIFETIME_REQUEST: word(0)}
    allowed = [(BONUS_DIGITS_AT, BONUS_DIGIT_COUNT), (TEXT_REQUEST, 1),
               (TEXT_LIFETIME_REQUEST, WORD_BYTES)]

    info = leaf.run(BONUS_DIGITS, _BONUS_DIGITS(addend), allowed, what,
                    regs={"d0": addend, "_pokes": pokes},
                    max_insns=_cap(BONUS_DIGITS, extra=8 * BONUS_DIGIT_COUNT))
    assert leaf.read_bytes(info, BONUS_DIGITS_AT, BONUS_DIGIT_COUNT, what) == expected, (
        f"{what}: the five characters are not nibbles 4..0 with the leading zeros blanked")
    assert leaf.read_int(info, TEXT_REQUEST, 1, what) == MESSAGE_BONUS_POINTS
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, what) == TEXT_LIFETIME_DEFAULT


def test_no_kind_the_SITE_ADMITS_can_reach_the_digit_loops_RUNAWAY():
    """The honest half of the two runaways ../names.txt records. An addend whose low FIVE nibbles are
    all zero enters the digit loop with the counter already at zero and wraps it to $ffff; an addend
    of zero never leaves the blanking loop at all. Neither is DRIVEN, and the reason is sharper than
    "no case covers it": the blanking loop has no counter, so entering it with zero HANGS rather than
    failing — a case would not terminate and no assertion could report it.

    THE RANGE IS THE SITE'S, NOT THE TABLE'S. `cmpi.b #$2,20(a0) / bge` admits kinds 2..127, so the
    row the `lea` lands on is one of 126 and not one of the table's own 22 — 106 of them lie past the
    table, in `pickup_effect_table` and the handlers above it. The first draft walked rows 0..21,
    which both checked two rows the site cannot reach and left 106 it can unchecked. The wider walk
    finds nothing either, so this is a correction of PROOF SCOPE and not of a live defect."""
    image = bytes(harness.BASE_IMAGE)
    low_five = (1 << (BCD_DIGIT_BITS * BONUS_DIGIT_COUNT)) - 1
    for kind in range(PICKUP_KIND_FIRST, 0x80):
        at = KIND_TABLE + kind * KIND_RECORD_BYTES + KIND_SCORE
        score = int.from_bytes(image[at:at + LONGWORD_BYTES], "big")
        assert score == 0 or score & low_five, (
            f"kind {kind}'s row at {at:#07x} holds {score:#010x}, whose low five nibbles are all "
            f"zero — the digit loop would run 65,536 times")


# --- the census, run before the fact --------------------------------------------------------------
@pytest.mark.parametrize("index", range(PICKUP_EFFECT_ENTRIES), ids=lambda v: f"entry{v:02d}")
def test_each_pickup_entry_is_reached_ONLY_through_the_tables_longword(index):
    """The claim every plate in this tier makes, measured rather than assumed — and here it is the
    load-bearing one, because it is what says the fourteen handlers are the pickup dispatch's alone
    and share nothing with WB_EFFECT_HANDLER_TABLE's twenty-nine."""
    entry = PICKUP_ENTRY_ADDRS[index]
    assert entry not in CONTROL_FLOW_TARGETS, (
        f"{entry:#07x} is named by {[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}")
    holders = [at for at in _operand_sites(longword(entry)) if at % WORD_BYTES == 0]
    assert holders == [PICKUP_EFFECT_TABLE + index * PICKUP_EFFECT_ENTRY], (
        f"{entry:#07x} is held as a longword at {[hex(at) for at in holders]}, not only its entry")


@pytest.mark.parametrize("name,sites", [("PICKUP_EFFECT_TABLE", 1), ("TEXT_BONUS_DIGITS", 1),
                                        ("ACTOR_KIND_TABLE", 2)],
                         ids=lambda v: str(v))
def test_the_addresses_this_batch_names_have_the_lea_count_their_plates_claim(name, sites):
    """Batch 34's lesson before the fact. WB_ACTOR_KIND_TABLE is the interesting row: its plate
    claimed ONE `lea` for a year and the scan gives TWO — $6d3c and slot 38's own $5476 — so the
    figure here is the corrected one and the case is what keeps it corrected."""
    found = _lea_sites(wb(name))
    assert len(found) == sites, (
        f"{name} ({wb(name):#07x}) is named by {len(found)} `lea`s, not {sites}: "
        f"{[hex(at) for at in found]}")


def test_the_two_kind_table_lea_sites_are_the_two_readers_the_plate_names():
    """...and WHERE they are, since "two" alone would not separate the corrected reading from a
    second `lea` inside one routine. One is in the respawn continuation and one inside slot 38."""
    pickup, respawn = _lea_sites(KIND_TABLE)     # sorted by ADDRESS, so slot 38's is first
    assert respawn == 0x6d3c, f"the respawn's `lea $1044c` moved to {respawn:#06x}"
    assert leaf.entry_of(TYPE38) <= pickup < leaf.entry_of(TYPE38) + BODY_SIZES[TYPE38], (
        f"the second `lea $1044c` is at {pickup:#06x}, outside slot 38's body")


def test_slot38_is_reached_ONLY_through_the_dispatch_longword():
    entry = leaf.entry_of(TYPE38)
    assert entry not in CONTROL_FLOW_TARGETS, (
        f"{entry:#06x} is named by {[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}")
    holders = [at for at in _operand_sites(longword(entry)) if at % WORD_BYTES == 0]
    assert holders == [BEHAVIOR_TABLE + 38 * BEHAVIOR_ENTRY]


def test_the_bonus_digit_routine_has_exactly_one_caller_and_it_is_slot_38():
    """`bsr.w $6938` at $548e, and nothing else in the image aims at it. That is what makes the
    routine's runaway argument above a statement about ONE caller rather than about a family."""
    callers = CONTROL_FLOW_TARGETS.get(leaf.entry_of(BONUS_DIGITS), [])
    assert len(callers) == 1, f"{BONUS_DIGITS} is reached from {[hex(at) for at in callers]}"
    assert leaf.entry_of(TYPE38) <= callers[0] < leaf.entry_of(TYPE38) + BODY_SIZES[TYPE38]


# --- ALL 65,536 EFFECT INDICES, against the reconstruction alone -----------------------------------
# The refusal's only surface, for the reason the behaviour dispatch's enumeration gives: the original
# would `jsr` through arbitrary data, so no differential can drive one. What this states is that the
# port's answer is the WRAPPED offset's for every index and the refusal for every other — which is
# the claim a guard on the raw index would get wrong on 42 of the 56 that dispatch.
PICKUP_INDEX_CHUNKS = 8
PICKUP_INDICES_PER_CHUNK = 0x10000 // PICKUP_INDEX_CHUNKS


@pytest.mark.parametrize("chunk", range(PICKUP_INDEX_CHUNKS), ids=lambda v: f"chunk{v}")
def test_every_effect_index_runs_the_wrapped_entry_or_is_refused(chunk):
    """One FFI call per index, on ONE buffer — so the seed the frame consumes is re-applied every
    iteration rather than being left to whatever the previous index's handler wrote. The 56 indices
    that dispatch run a pickup handler AND `actor_defeat_and_score` on top, which is exactly why the
    record's own fields are put back each time."""
    what = f"pickup index enumeration chunk {chunk}"
    pokes = _pickup_pokes(what, PICKUP_KIND, 0)
    image = harness.make_image(pokes)
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(bytearray(image))
    handler = leaf.bind(TYPE38, [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32], ctypes.c_uint32)
    # Everything the frame reads and can also write, taken out of the seeded image rather than
    # restated — a list of literals here would be a second copy of `_pickup_pokes`.
    restore = {addr: image[addr]
               for field, length in ((ACTOR_X, WORD_BYTES), (ACTOR_Y, WORD_BYTES),
                                     (ACTOR_TYPE, WORD_BYTES), (KIND, 1), (ACTOR_FLAGS, 1),
                                     (FLAGS2, 1), (FIELD_12, 1), (FIELD_18, 1), (SPEED, 1))
               for addr in range(ACTOR + field, ACTOR + field + length)}
    dispatched = 0

    for index in range(chunk * PICKUP_INDICES_PER_CHUNK, (chunk + 1) * PICKUP_INDICES_PER_CHUNK):
        for addr, value in restore.items():
            buf[addr] = value
        buf[PICKUP_ROW + KIND_PICKUP_EFFECT] = index >> 8
        buf[PICKUP_ROW + KIND_PICKUP_EFFECT + 1] = index & 0xff
        entry = _pickup_dispatched(index)
        answer = handler(buf, ACTOR)
        if entry is None:
            assert answer == DISPATCH_PICKUP_REFUSED, (
                f"index {index:#06x} answered {answer:#x}, not the refusal its offset earns")
            continue
        dispatched += 1
        assert answer == DISPATCH_RAN, (
            f"index {index:#06x} answered {answer:#x} against entry {entry}'s run")

    # $4000 is exactly half a chunk, so an alias band lands wholly inside one: the chunks that hold
    # one dispatch all fourteen entries and the rest dispatch nothing.
    assert dispatched == (PICKUP_EFFECT_ENTRIES
                          if chunk % (PICKUP_INDEX_CHUNKS // 4) == 0 else 0)


# THE SWEEP'S ONE SURVIVOR, and closing it took a differential rather than an argument.
# `movea.l 0(a1,d0.w),a1` SIGN-EXTENDS the wrapped offset, and dropping that sign extension survived
# the whole suite: every legal offset is positive, and a high index refuses either way — below the
# table with the sign, above it without — because the census says each of the fourteen addresses is
# held as a longword in exactly ONE place, the table. So no index at all separates the two spellings
# on the image as it ships.
#
# What separates them is a TARGET the sign-extended read can reach and the other cannot. Index
# $ffff scales to offset $fffc, which is FOUR BYTES BELOW the table — the last longword of
# WB_ACTOR_KIND_TABLE's row 21, zero in the shipped image. Put an entry address there and the
# original `jsr`s to it; the zero-extended spelling reads $205a8 instead and refuses. It is a
# DIFFERENTIAL and not a C-only claim: the oracle runs the same `jsr`.
PICKUP_BELOW_TABLE_INDEX = 0xffff
PICKUP_BELOW_TABLE_AT = PICKUP_EFFECT_TABLE - PICKUP_EFFECT_ENTRY


def test_the_effect_offset_is_SIGN_extended_so_an_index_can_read_BELOW_the_table():
    what = "actor_behavior_type38_pickup effect index below the table"
    assert _image_word(PICKUP_BELOW_TABLE_AT) == 0 and _image_word(
        PICKUP_BELOW_TABLE_AT + WORD_BYTES) == 0, (
        "the longword below the table is no longer zero, so this seed is not a change")
    # The bare `rts`, chosen because it is the one entry whose whole effect is "nothing happened":
    # what the case is about is WHICH ADDRESS the fetch read, not what the handler then did.
    pokes = _pickup_pokes(what, PICKUP_KIND, PICKUP_BELOW_TABLE_INDEX,
                          fields={PICKUP_BELOW_TABLE_AT: longword(wb("PICKUP_EFFECT_NONE"))})
    assert _pickup_dispatched(PICKUP_BELOW_TABLE_INDEX) is None, (
        f"{what}: this index is inside the table, so it says nothing about the extension")

    image = harness.make_image(pokes)
    info = _run_handler(TYPE38, what, pokes, band=_pickup_band(image, {}))
    assert info["ret"] == DISPATCH_RAN
