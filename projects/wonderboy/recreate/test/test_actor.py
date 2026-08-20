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
from leaf import (BRANCH_EXTENSION, JSR_ABS_L, RTS, add_w_dn_dn, addi_w_dn, addq_b_d16,
                  tst_b_d16,
                  adda_w_dn_an, addq_w_dn,
                  asl_w_imm_dn, asr_w_imm_dn, backward_branch, branch, branch_over, branch_w_to,
                  bsr_w, btst_imm_dn,
                  eori_w_dn, exg_dn_dn, ext_w_dn, move_b_postinc_dn,
                  movem_l_pop, movem_l_push, neg_w_dn, roxl_w_imm_dn,
                  case_salt, clr_b_d16, clr_w_d16, clr_w_dn, cmp_w_dn_dn, cmp_w_imm_dn, cmpi_b_dn,
                  cmpi_w_d16,
                  dbf, dbf_over,
                  keyed_block, lea_abs_l, lea_d16, lea_indexed, longword, lsl_w_imm_dn,
                  merge_bands, move_b_d16_dn, move_b_imm_d16, move_l_imm_abs_l,
                  move_l_imm_postinc, move_w_abs_l_dn, move_w_imm_dn, move_w_ind_dn,
                  move_w_postinc_d16,
                  movea_l_abs_l, movea_l_an_an, moveq_0_dn, opcode, program_writes, s16,
                  sub_w_dn_d16,
                  sub_w_dn_dn, subi_w_dn, tst_w_abs_w, tst_w_dn, u16, word,
                  # ...and the five hoisted to leaf.py by batch 41 phase B's spawn-tree pin
                  move_w_imm_d16)
from leaf import (WORD_MASK, clr_w_abs_l, move_b_abs_l_dn, move_b_imm_abs_l,
                  move_w_imm_abs_l, move_w_indexed_dn, tst_b_abs_l)
from layout import wb

# The two damage paths call the SOUND MODULE, so the battery that owns $1a48a owns that half of
# their write set too — imported rather than restated, exactly as test_hud.py imports it for $bbca.
from test_sound import (STOP_INSN_CAP, STOP_WRITES, STUB_INSN_CAP,          # noqa: E402
                        STUB_TRIGGER_OFFSET, PSG_REG_MIXER,
                        STUB_TABLE_BASE as SND_STUB_TABLE,
                        assert_written as assert_sfx_written,
                        assert_psg_state as assert_stop_chain_psg_state,
                        expected_writes as sfx_expected_writes)

# ...and $6bb8's boss arm pays a score and raises the meter, so the two models the PANEL battery owns
# come from there for the same reason: two copies of "what packed BCD does" could disagree while both
# batteries stayed green.
# `bcd_expected` and `meter_add_expected` moved from test_hud.py to leaf.py in batch 33 — three
# batteries need them, and a battery importing a shared fact from a SIBLING battery is the coupling
# leaf.py exists to remove. What this file still imports from test_hud.py is that battery's own
# models, which is a different thing.
from leaf import bcd_expected, meter_add_expected                           # noqa: E402

# ...and the respawn continuation draws its new kind through both of them, so the RNG battery's model
# and instruction counts come from there rather than being restated: a second copy of the generator's
# three counter steps could disagree with src/rng.c while test_rng.py stayed green.
from test_rng import (COUNTERS as RNG_COUNTERS, DRAW8, DRAW32,             # noqa: E402
                      FRAME_TICK, KIND32_INSN_CAP, STAGE_NUMBER,
                      model_kind as model_stage_kind)

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

# ...and the spawn PASS's own (batch 13)
SPAWN_TERMINATOR = wb("SPAWN_TERMINATOR")
SPAWN_HEADER_BYTES = wb("SPAWN_HEADER_BYTES")
HEADER_MAX_LIVE = wb("SPAWN_HEADER_MAX_LIVE")
HEADER_LIVE = wb("SPAWN_HEADER_LIVE")
HEADER_CURSOR = wb("SPAWN_HEADER_CURSOR")
HEADER_WRAPPED = wb("SPAWN_HEADER_WRAPPED")
WRAPPED_SET = wb("SPAWN_WRAPPED_SET")
SPAWN_ARMED = wb("SPAWN_ARMED")
SPAWN_COUNTDOWN = wb("SPAWN_COUNTDOWN")
SPAWN_HITPOINTS = wb("SPAWN_HITPOINTS")
SPAWN_KILL_COUNT = wb("SPAWN_KILL_COUNT")
HITPOINT_TABLE = wb("SPAWN_HITPOINT_TABLE")
HITPOINT_TABLE_ENTRIES = wb("SPAWN_HITPOINT_TABLE_ENTRIES")
HITPOINT_TYPE_FIXED = wb("SPAWN_HITPOINT_TYPE_FIXED")
HITPOINT_FIXED_BASE = wb("SPAWN_HITPOINT_FIXED_BASE")
STEP_BLOCKED = wb("ACTOR_STEP_BLOCKED")
GROUND_STEP_UP_BIT = wb("ACTOR_GROUND_STEP_UP_BIT")
GROUND_DROP_TWO_BIT = wb("ACTOR_GROUND_DROP_TWO_BIT")
GROUND_DROP_ONE_BIT = wb("ACTOR_GROUND_DROP_ONE_BIT")
HOP_SPEED = wb("ACTOR_HOP_SPEED")
TURN_LAUNCH_SPEED = wb("ACTOR_TURN_LAUNCH_SPEED")

# ...and the two damage paths' own (batch 17)
FIELD_22 = wb("ACTOR_FIELD_22")
FLICKER_COUNTDOWN = wb("ACTOR_FLICKER_COUNTDOWN")
FLAGS2_BIT_0 = wb("ACTOR_FLAGS2_BIT_0")
FLAGS2_DEFEATED_BIT = wb("ACTOR_FLAGS2_DEFEATED_BIT")
FLAGS2_INVULNERABLE_BIT = wb("ACTOR_FLAGS2_INVULNERABLE_BIT")
DAMAGE_TABLE = wb("ACTOR_DAMAGE_TABLE")
DAMAGE_TABLE_ENTRIES = wb("ACTOR_DAMAGE_TABLE_ENTRIES")
DAMAGE_INLINE_MASK = wb("ACTOR_DAMAGE_INLINE_MASK")
DAMAGE_FIELD_31_BASE = wb("ACTOR_DAMAGE_FIELD_31_BASE")
DAMAGE_FLICKER_FRAMES = wb("ACTOR_DAMAGE_FLICKER_FRAMES")
DAMAGE_FIELD_30_SET = wb("ACTOR_DAMAGE_FIELD_30_SET")
DAMAGE_KNOCKBACK_SPEED = wb("ACTOR_DAMAGE_KNOCKBACK_SPEED")
DAMAGE_FOLLOWED_SFX = wb("ACTOR_DAMAGE_FOLLOWED_SFX")
DAMAGE_TEMPLATE_SFX = wb("ACTOR_DAMAGE_TEMPLATE_SFX")
SLOT_BBBE = wb("HUD_SLOT_BBBE")
SLOT_BBC0 = wb("HUD_SLOT_BBC0")
SLOT_REQUEST = wb("HUD_SLOT_REQUEST")
SLOT_REARM = wb("HUD_SLOT_REARM")
METER_VALUE = wb("HUD_METER_VALUE")
METER_MAX = wb("HUD_METER_MAX")
TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")
TEXT_MESSAGE_TABLE = wb("TEXT_MESSAGE_TABLE")
TEXT_MESSAGE_FIRST_ID = wb("TEXT_MESSAGE_FIRST_ID")
TEXT_RECORD_STRING = wb("TEXT_RECORD_STRING")
TEXT_STRING_END = wb("TEXT_STRING_END")
MSG_HELMET_BROKEN = wb("TEXT_MSG_HELMET_BROKEN")
MSG_GAUNTLET_BROKEN = wb("TEXT_MSG_GAUNTLET_BROKEN")
EFFECT_STATE_BD66 = wb("EFFECT_STATE_BD66")
EFFECT_RECORD_LIST = wb("EFFECT_RECORD_LIST")
SND_CHANNEL_A = wb("SND_CHANNEL_A")
SND_CHANNEL_B = wb("SND_CHANNEL_B")

WORD_LEN = 2
LONGWORD_LEN = 4
TABLE_BYTES = SCREEN_RECORD_COUNT * RECORD_BYTES

# The routines are straight-line bar one loop of nineteen records; the cap is that loop's own
# geometry with room for the entry and the tail, so a case that ran away fails loudly.
LIST_INSN_CAP = 64 * SCREEN_RECORD_COUNT

# --- register numbers, and the opcodes only this battery spells -----------------------------------
# The ordinals and the three immediate BIT opcodes moved to leaf.py in batch 38 (third-copy rule) and
# are re-exported here, because two other batteries name THIS file as their source for them.
from leaf import (A0, A1, A2, A5, A6, D0, D1, D2, D7,                      # noqa: E402,F401
                  BSET_IMM, BCLR_IMM, BTST_IMM, bit_op_d16)
from leaf import tst_w_d16  # noqa: E402   # hoisted out of this file by batch 41 phase C

BNE_W, BEQ_W, BPL_W, BLE_W, BLT_W, BGT_W, BRA_W = (0x6600, 0x6700, 0x6a00, 0x6f00,
                                                   0x6d00, 0x6e00, 0x6000)
BMI_W = 0x6b00
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


def move_w_dn_postinc(reg, destination):
    return opcode(0x30c0 | (destination << 9) | reg)


def move_w_imm_ind(reg, value):
    return opcode(0x30bc | (reg << 9)) + word(value)


def move_w_d16_ind(source, displacement, destination):
    """`move.w d16(As),(Ad)` — the projection's sprite arm."""
    return opcode(0x3080 | (destination << 9) | 0x28 | source) + word(displacement)


def cmpa_l_imm(reg, value):
    """`cmpa.l #imm,An` — a LONGWORD compare, which is what ends a record walk. ALSO IN
    test_blit.py, under the same name and in the same operand order."""
    return opcode(0xb1fc | (reg << 9)) + longword(value)


# ...and the encodings only the LIFECYCLE routines use.
def clr_l_postinc(reg):
    return opcode(0x4298 | reg)


def cmpi_w_ind(reg, value):
    return opcode(0x0c50 | reg) + word(value)


def movea_l_imm(reg, value):
    return opcode(0x207c | (reg << 9)) + longword(value)


def move_w_d16_d16(source, source_displacement, destination, destination_displacement):
    """`move.w d16(As),d16(Ad)` — how the spawn copies a template field into a record.

    The destination's register and mode sit in the HIGH half of the opcode word but its extension
    word comes SECOND: a `move` emits the source EA's extensions first. The spawn's own arm copying
    14(a0) to 14(a1) has the two displacements equal and so cannot tell the order apart; the two
    that copy 26(a0) to 2(a1) and 12(a0) to 4(a1) can, and the entry pin is where they do.
    """
    return (opcode(0x3168 | (destination << 9) | source)
            + word(source_displacement) + word(destination_displacement))


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


# ...and the encodings the SPAWN PASS and the flag family add (batch 13).
def tst_b_dn(reg):
    """`tst.b Dn` — the three flag routines test only the LOW BYTE of the step's outcome."""
    return opcode(0x4a00 | reg)


def subq_b_d16(amount, base, displacement):
    """`subq.b #n,d16(An)` — addq_b_d16's other direction; the countdown walk's whole payload.
    ALSO IN test_sound.py (`SUBQ_B_D16_AN`), which is the second speller — annotated on both sides
    rather than hoisted, per leaf.py's rule that an encoding moves there on its THIRD."""
    return opcode(0x5128 | ((amount & 7) << 9) | base) + word(displacement)


def addq_w_d16(amount, base, displacement):
    return opcode(0x5068 | ((amount & 7) << 9) | base) + word(displacement)


def cmp_w_d16_dn(reg, base, displacement):
    return opcode(0xb068 | (reg << 9) | base) + word(displacement)



def lsl_l_imm_dn(count, reg):
    return opcode(0xe188 | ((count & 7) << 9) | reg)


def adda_l_dn_an(reg, source):
    return opcode(0xd1c0 | (reg << 9) | source)


def add_w_ind_dn(reg, base):
    return opcode(0xd050 | (reg << 9) | base)


def move_w_dn_d16(reg, base, displacement):
    return opcode(0x3140 | (base << 9) | reg) + word(displacement)


# ...and the encodings only the two DAMAGE PATHS use (batch 17). Each is the one member of a family
# leaf.py already carries that no other battery has needed yet, so each stands at ONE user and stays
# here: `tst.b <abs>.w` beside leaf's `tst_w_abs_w`, `subq.b <abs>.l` beside its `subq_w_abs_l`,
# and the `sub.w Dn,<ea>` pair beside its register-to-register `sub_w_dn_dn`. (The two this batch
# found at THREE users — `move_w_indexed_dn` and `move_w_imm_abs_l` — went to leaf.py instead and
# are imported above.)
def tst_b_abs_w(addr):
    """`tst.b <abs>.w` — $69fe reads WB_STATE_FLAG_A32 one size DOWN from every other reader of it
    in the image, so this encoding is the whole difference the battery is here to pin."""
    return opcode(0x4a38) + word(addr)


def subq_b_abs_l(amount, addr):
    """`subq.b #n,<abs>.l` — one charge off a HUD slot."""
    return opcode(0x5139 | ((amount & 7) << 9)) + longword(addr)


def addq_b_dn(amount, reg):
    """`addq.b #n,Dn` — a BYTE add, so $ff comes back 0."""
    return opcode(0x5000 | ((amount & 7) << 9) | reg)


def sub_w_dn_abs_l(reg, addr):
    """`sub.w Dn,<abs>.l` — a read-modify-write on the meter word itself."""
    return opcode(0x9179 | (reg << 9)) + longword(addr)


def jsr_d16_an(reg, displacement):
    """`jsr d16(An)` — how everything outside the sound module reaches its stub table. test_hud.py
    spells the a1 form as a two-byte literal (`JSR_D16_A1`) for $bbca's call; both damage paths use
    the a5 one, so the pair stands at two users and each says so."""
    return opcode(0x4ea8 | reg) + word(displacement)


def bclr_imm_dn(bit, reg):
    """`bclr #n,Dn` — a LONGWORD operation on a register, where `bit_op_d16` above is a BYTE one
    against memory. $69fe strips bit 7 off the damage byte with it.

    Only the `bclr` of the register family is spelt here: `btst #n,Dn` is leaf.btst_imm_dn, which
    three batteries import, and nothing in this battery assembles `bset #n,Dn` at all — so an `op`
    parameter like `bit_op_d16`'s would be a family with one member."""
    return opcode(BCLR_IMM | reg) + word(bit)


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


BCHG_IMM = 0x0840


def _branch_s(condition, here, target):
    """A conditional branch in its SHORT form, assembled at ``here``. $2b82's two branches both go
    BACKWARDS out of its own body into the tail it shares, which is exactly what made Ghidra record
    20 bytes for a 12-byte routine — so their displacements are built from the two addresses."""
    displacement = target - (here + BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0x80, f"{displacement} does not fit a short branch"
    return opcode(condition | (displacement & BYTE_MASK))


def _spawn_pass_entry():
    """$ff42's whole 162 bytes. Built with a running offset because it holds four calls, and a
    `bsr.w`'s displacement depends on where it sits — so a pin aimed at the wrong callee fails."""
    at = leaf.entry_of("actor_spawn_pass")
    alloc = jsr_abs_w(leaf.entry_of("actor_alloc_slot_low"))

    # The countdown walk: one `subq.b` per armed template, closed on the terminator by a SHORT
    # backward branch to its own first instruction.
    decrement = subq_b_d16(1, A0, SPAWN_COUNTDOWN)
    step = lea_d16(A0, SPAWN_RECORD_BYTES) + cmpi_w_ind(A0, SPAWN_TERMINATOR)
    walk_body = tst_b_d16(A0, SPAWN_ARMED) + branch(BEQ_W, decrement) + decrement + step
    walk = walk_body + opcode(BNE_S | (backward_branch(len(walk_body))[1] & BYTE_MASK))

    # ...the capacity test the two arms hang off...
    capacity = (move_w_ind_dn(D0, A6, -SPAWN_HEADER_BYTES + HEADER_MAX_LIVE)
                + cmp_w_d16_dn(D0, A6, -SPAWN_HEADER_BYTES + HEADER_LIVE))

    def spawn_calls(here):
        return alloc + bsr_w(here + len(alloc), leaf.entry_of("actor_spawn_from_template")) + bsr_w(
            here + len(alloc) + len(bsr_w(0, 0)), leaf.entry_of("actor_template_set_hitpoints"))

    # ...the arm that spawns the ONE template the cursor names...
    raise_wrapped = move_w_imm_d16(A6, WRAPPED_SET, -SPAWN_HEADER_BYTES + HEADER_WRAPPED)
    cursor_head = (moveq_0_dn(D0)
                   + move_w_ind_dn(D0, A6, -SPAWN_HEADER_BYTES + HEADER_CURSOR)
                   + addq_w_d16(1, A6, -SPAWN_HEADER_BYTES + HEADER_CURSOR)
                   + lsl_l_imm_dn(TEMPLATE_SLOT_SHIFT, D0)
                   + movea_l_an_an(A0, A6)
                   + lea_indexed(A0, D0)
                   + cmpi_w_d16(A0, SPAWN_TERMINATOR, SPAWN_RECORD_BYTES)
                   + branch(BNE_W, raise_wrapped) + raise_wrapped
                   + addq_w_d16(1, A6, -SPAWN_HEADER_BYTES + HEADER_LIVE))
    cursor_at = at + 4 + 4 + 6 + 2 + len(walk) + len(capacity) + 4 + 6 + 4
    cursor_arm = cursor_head + spawn_calls(cursor_at + len(cursor_head)) + RTS

    # ...and the arm that sweeps the whole table for every template whose countdown has run out.
    sweep_at = cursor_at + len(cursor_arm)
    armed_test = tst_b_d16(A0, SPAWN_ARMED) + branch(BEQ_W, b"")
    countdown_test = tst_b_d16(A0, SPAWN_COUNTDOWN) + branch(BNE_W, b"")
    sweep_disarm = clr_b_d16(A0, SPAWN_ARMED) + addq_w_d16(
        1, A6, -SPAWN_HEADER_BYTES + HEADER_LIVE)
    sweep_calls_at = (sweep_at + len(movea_l_an_an(A0, A6)) + len(armed_test)
                      + len(countdown_test) + len(sweep_disarm))
    sweep_spawn = sweep_disarm + spawn_calls(sweep_calls_at)
    # Both tests skip the WHOLE spawn, so the first one also spans the second.
    sweep_body = (tst_b_d16(A0, SPAWN_ARMED) + branch(BEQ_W, countdown_test, sweep_spawn)
                  + tst_b_d16(A0, SPAWN_COUNTDOWN) + branch(BNE_W, sweep_spawn) + sweep_spawn
                  + step)
    sweep_arm = movea_l_an_an(A0, A6) + sweep_body + opcode(
        BNE_S | (backward_branch(len(sweep_body))[1] & BYTE_MASK))

    return (tst_w_abs_w(FLAG_A30)
            + branch_over(BNE_W, 6 + 2 + len(walk) + len(capacity) + 4 + 6 + 4
                          + len(cursor_arm) + len(sweep_arm))
            + movea_l_abs_l(A6, TABLE_PTR) + movea_l_an_an(A0, A6) + walk
            + capacity + branch_over(BEQ_W, 6 + 4 + len(cursor_arm) + len(sweep_arm))
            + cmpi_w_d16(A6, WRAPPED_SET, -SPAWN_HEADER_BYTES + HEADER_WRAPPED)
            + branch(BEQ_W, cursor_arm)
            + cursor_arm + sweep_arm + RTS)


def _set_hitpoints_entry():
    store = move_w_dn_d16(D0, A0, SPAWN_HITPOINTS) + RTS
    from_table = (add_w_dn_dn(D1, D1) + lea_abs_l(A2, HITPOINT_TABLE)
                  + adda_l_dn_an(A2, D1) + add_w_ind_dn(D0, A2))
    fixed = addi_w_dn(D0, HITPOINT_FIXED_BASE) + branch(BRA_W, from_table)
    return (moveq_0_dn(D0) + moveq_0_dn(D1)
            + move_w_ind_dn(D0, A0, SPAWN_KILL_COUNT) + asr_w_imm_dn(1, D0)
            + move_w_ind_dn(D1, A0, SPAWN_TYPE) + cmp_w_imm_dn(D1, HITPOINT_TYPE_FIXED)
            + branch(BNE_W, fixed) + fixed + from_table + store)


# The eight bytes at $2b7a, which four branches reach and no call does. All three pins below are
# built from THIS, which is the claim `test_the_three_flag_routines_share_one_tail` states.
SIDE_FLIP_TAIL = bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS) + RTS


def _hop_or_flip_entry():
    at = leaf.entry_of("actor_hop_or_flip_side")
    hop = (move_w_imm_dn(D0, HOP_SPEED)
           + _bsr_s(at + 18, leaf.entry_of("actor_start_motion_at_speed")) + RTS)
    second_arm = btst_imm_dn(GROUND_DROP_TWO_BIT, D1) + branch(BNE_W, RTS) + RTS
    return (tst_b_dn(D0) + branch(BNE_W, btst_imm_dn(0, D1), branch(BEQ_W, b""), hop)
            + btst_imm_dn(GROUND_STEP_UP_BIT, D1) + branch(BEQ_W, hop, second_arm)
            + hop + second_arm + SIDE_FLIP_TAIL)


def _side_flip_tail_address():
    """Where the shared tail sits: the LAST eight bytes of $2b5a's body, derived from that body
    rather than written down, so a pin that got $2b5a's length wrong fails here too."""
    return (leaf.entry_of("actor_hop_or_flip_side")
            + len(_hop_or_flip_entry()) - len(SIDE_FLIP_TAIL))


def _toggle_side_entry():
    """Twelve bytes, and BOTH branches leave them — backwards, into $2b5a's tail. Ghidra's 20 is
    those 12 plus the 8 they land on, which is why the size table below states 12."""
    at = leaf.entry_of("actor_toggle_side_flag")
    tail = _side_flip_tail_address()
    return (tst_b_dn(D0) + _branch_s(BEQ_W, at + 2, tail)
            + btst_imm_dn(GROUND_DROP_ONE_BIT, D1) + _branch_s(BNE_W, at + 8, tail) + RTS)


def _turn_and_launch_entry():
    launch = (bit_op_d16(BCHG_IMM, SIDE_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS)
              + bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS)
              + move_b_imm_d16(A0, TURN_LAUNCH_SPEED, SPEED))
    supported = (bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS)
                 + branch(BEQ_W, launch) + launch + RTS)
    return (tst_b_dn(D0) + branch(BEQ_W, btst_imm_dn(0, D1), branch(BNE_W, b""), RTS)
            + btst_imm_dn(GROUND_DROP_ONE_BIT, D1) + branch(BNE_W, RTS) + RTS
            + supported)


# --- the two damage paths' bodies ($69fe, $6b46) --------------------------------------------------
# Both are one straight run with a handful of forward branches, and both END in a call into the
# sound module's stub table — so each pin also states the stub OFFSET and the table's own address,
# which test_sound.py owns. The `lea $6b08.l,a2` inside the first one names the WORD TABLE that sits
# between the two bodies, which is what fixes both boundaries at once.

def _slot_rearm(slot, message_id):
    """`move.w #$ff,slot / move.b #id,$c030 / move.w #$32,$c034` — the three stores both paths make
    on the frame a slot's last charge goes.

    This is the only part of the two spend blocks that is common CODE rather than a common shape:
    $69fe's `bne` lands past its whole fallback arm and $6b46's lands on the doubling in front of
    the beq's own target, so the two blocks' branches are different instructions. src/actor.c's one
    `hud_slot_spend_charge` behind both is a claim about the WRITES, which the cases below make.
    """
    return (move_w_imm_abs_l(SLOT_REARM, slot)
            + move_b_imm_abs_l(message_id, TEXT_REQUEST)
            + move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST))


def _knock_back_and_launch_entry():
    """$6ade's forty-two bytes: the SFX on channel A, then the three flag bits and the speed byte.

    THE SAME BYTES ARE $69fe's LAST FORTY-TWO, so `_damage_followed_entry` below builds its own tail
    out of this call rather than spelling them a second time — two spellings of one instruction
    stream can disagree while both entry pins stay green, and this one is now a routine of its own
    only because a THIRD entrance ($15e8's `bra.w`, in `player_run_map_cell`) reaches it.
    `test_the_shared_tail_is_the_last_forty_two_bytes_of_the_damage_path` is the address half of
    that claim; this function is the byte half.

    The three bit ops are `bset #0 / bset #1 / bclr #2` where $2af2's `_start_motion_entry` spells
    `bclr #2 / bset #0 / bset #1` — one byte and one final value, so the pin is the only thing in
    the project that can tell the two orders apart.
    """
    trigger = (move_w_imm_dn(D0, DAMAGE_FOLLOWED_SFX) + clr_w_dn(D1)
               + lea_abs_l(A5, SND_STUB_TABLE) + jsr_d16_an(A5, STUB_TRIGGER_OFFSET))
    return (trigger
            + bit_op_d16(BSET_IMM, MOVING_BIT, A1, ACTOR_FLAGS)
            + bit_op_d16(BSET_IMM, LAUNCHED_BIT, A1, ACTOR_FLAGS)
            + bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A1, ACTOR_FLAGS)
            + move_b_imm_d16(A1, DAMAGE_KNOCKBACK_SPEED, SPEED) + RTS)


def _damage_followed_entry():
    """$69fe's whole 266 bytes, ending exactly where WB_ACTOR_DAMAGE_TABLE begins."""
    # The tail every arm that does any work funnels into: the x compare, then the shared forty-two
    # bytes above — which are `actor_knock_back_and_launch` and this routine's ending at once.
    attacker_right = bit_op_d16(BCLR_IMM, SIDE_BIT, A1, ACTOR_FLAGS) + clr_b_d16(A1, FIELD_30)
    attacker_left = (bit_op_d16(BSET_IMM, SIDE_BIT, A1, ACTOR_FLAGS)
                     + move_b_imm_d16(A1, DAMAGE_FIELD_30_SET, FIELD_30))
    tail = (move_w_ind_dn(D0, A1, ACTOR_X) + move_w_ind_dn(D1, A0, ACTOR_X) + cmp_w_dn_dn(D1, D0)
            + branch(BGT_W, attacker_left, branch(BRA_W, attacker_right))
            + attacker_left + branch(BRA_W, attacker_right)
            + attacker_right + _knock_back_and_launch_entry())

    # The meter arm, which is what the slot spend falls back on...
    meter = (sub_w_dn_abs_l(D0, METER_VALUE) + branch(BPL_W, clr_w_abs_l(METER_VALUE))
             + clr_w_abs_l(METER_VALUE)
             + move_b_imm_d16(A1, DAMAGE_FLICKER_FRAMES, FLICKER_COUNTDOWN))

    # ...and the `bclr #7` arm, which rejoins the slot test FROM BELOW. Its `bra.s` spans the whole
    # spend block bar its own opcode word, so the block is assembled once for its length and once
    # with the displacement that length gives.
    rearm = _slot_rearm(SLOT_BBBE, MSG_HELMET_BROKEN)

    def spend(inline_arm):
        join = branch(BRA_W, inline_arm)      # `bra.w` past the inline arm, into the funnel
        charge = (subq_b_abs_l(1, SLOT_BBBE)
                  + branch(BNE_W, rearm, branch(BRA_W, meter, join), meter, join, inline_arm)
                  + rearm + branch(BRA_W, meter, join, inline_arm))
        return (tst_b_abs_l(SLOT_BBBE) + branch(BEQ_W, charge) + charge
                + meter + join + inline_arm)

    inline_head = bclr_imm_dn(DAMAGE_INLINE_MASK.bit_length(), D0)
    spend_block = spend(inline_head + bra_s_back(len(spend(inline_head + RTS)) - WORD_LEN))

    # The damage word: the type of the template WB_ACTOR_TEMPLATE_SLOT names, into the word table.
    lookup = (movea_l_abs_l(A6, TABLE_PTR) + lsl_l_imm_dn(TEMPLATE_SLOT_SHIFT, D0)
              + move_w_indexed_dn(D0, A6, D0, SPAWN_TYPE) + add_w_dn_dn(D0, D0)
              + lea_abs_l(A2, DAMAGE_TABLE)
              # ...and the SAME encoder with the extension word's longword bit, which is
              # the one bit that separates the two lookups.
              + move_w_indexed_dn(D0, A2, D0, longword_index=True))
    # The `bmi` lands on the inline arm, i.e. past everything but the last six bytes of the spend.
    inline_arm_bytes = len(inline_head) + WORD_LEN
    cost = (moveq_0_dn(D0) + move_b_d16_dn(D0, A0, TEMPLATE_SLOT)
            + branch_over(BMI_W, len(lookup) + len(spend_block) - inline_arm_bytes)
            + lookup + spend_block)

    default_record = (lea_abs_l(A1, FOLLOWED_DEFAULT)
                      + branch(BRA_W, lea_abs_l(A1, FOLLOWED_A32)))
    return (tst_b_abs_w(FLAG_A32) + branch(BNE_W, default_record) + default_record
            + lea_abs_l(A1, FOLLOWED_A32)
            + bit_op_d16(BTST_IMM, FLAGS2_INVULNERABLE_BIT, A1, FLAGS2)
            + branch(BEQ_W, RTS) + RTS
            + bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A1, FLAGS2)
            + move_w_abs_l_dn(D0, EFFECT_STATE_BD66) + add_w_dn_dn(D0, D0)
            + move_w_imm_dn(D1, DAMAGE_FIELD_31_BASE) + sub_w_dn_dn(D1, D0)
            + move_b_dn_d16(D1, A1, FIELD_31) + clr_b_d16(A1, FIELD_22)
            + bit_op_d16(BSET_IMM, FLICKER_BIT, A1, ACTOR_FLAGS) + branch(BNE_W, cost)
            + cost + tail)


def _damage_template_entry():
    """$6b46's whole 114 bytes. Its FIRST FOUR INSTRUCTIONS are the sound call — and the d1 they
    pass is WB_SND_CHANNEL_B, the one site in the image that is not channel A."""
    kill = bit_op_d16(BSET_IMM, FLAGS2_DEFEATED_BIT, A0, FLAGS2) + RTS
    double = add_w_dn_dn(D0, D0)
    rearm = _slot_rearm(SLOT_BBC0, MSG_GAUNTLET_BROKEN)
    charge = subq_b_abs_l(1, SLOT_BBC0) + branch(BNE_W, rearm) + rearm
    # The `beq` clears the doubling and the `bne` does NOT, which is what says the doubling runs on
    # both arms that spent a charge and only on those.
    spend = tst_b_abs_l(SLOT_BBC0) + branch(BEQ_W, charge, double) + charge + double
    return (move_w_imm_dn(D0, DAMAGE_TEMPLATE_SFX) + move_w_imm_dn(D1, SND_CHANNEL_B)
            + lea_abs_l(A5, SND_STUB_TABLE) + jsr_d16_an(A5, STUB_TRIGGER_OFFSET)
            + movea_l_abs_l(A1, TABLE_PTR)
            + moveq_0_dn(D0) + move_b_d16_dn(D0, A0, TEMPLATE_SLOT)
            + lsl_l_imm_dn(TEMPLATE_SLOT_SHIFT, D0) + lea_indexed(A1, D0)
            + moveq_0_dn(D0) + move_b_abs_l_dn(D0, EFFECT_RECORD_LIST) + addq_b_dn(1, D0)
            + spend
            + sub_w_dn_d16(D0, A1, SPAWN_HITPOINTS)
            + branch(BEQ_W, branch(BMI_W, RTS), RTS) + branch(BMI_W, RTS) + RTS
            + kill)


# --- $6bb8 + $6cdc: paying for a defeat, and what comes back --------------------------------------
# The routine's own 164 bytes end at WB_SPAWN_SCORE_TABLE, which is its own data — so the entry pin
# and the table's extent bound each other. The `ble.w` at DEFEAT_TRANSFER leaves for the respawn
# continuation at DEFEAT_RESPAWN_PC, which batch 22 reconstructed: there is no checkpoint here any
# more, both exits run to an `rts`, and the two codes report which of them the run TOOK.
DEFEAT_RETIRED = wb("ACTOR_DEFEAT_RETIRED")
DEFEAT_RESPAWN = wb("ACTOR_DEFEAT_RESPAWN")
DEFEAT_RESPAWN_PC = 0x6cdc
BRANCH_W_BYTES = 4
BSR_W_BYTES = BRANCH_W_BYTES    # opcode + displacement word, the same shape as a `bcc.w`
KIND = wb("ACTOR_KIND")
FIELD_10 = wb("ACTOR_FIELD_10")
FIELD_12 = wb("ACTOR_FIELD_12")
KIND_TABLE = wb("ACTOR_KIND_TABLE")
KIND_TABLE_ROWS = wb("ACTOR_KIND_TABLE_ROWS")
KIND_RECORD_BYTES = wb("ACTOR_KIND_RECORD_BYTES")
KIND_RECORD_SHIFT = wb("ACTOR_KIND_RECORD_SHIFT")
KIND_TYPE = wb("ACTOR_KIND_TYPE")
KIND_TABLE_LAST_TYPE = 0x3d      # row 21 alone; every other row is WB_ACTOR_TYPE_UNSCORED
KIND_SPRITE = wb("ACTOR_KIND_SPRITE")
RESPAWN_FIELD_10 = wb("ACTOR_RESPAWN_FIELD_10")
RESPAWN_SPEED = wb("ACTOR_RESPAWN_SPEED")
RESPAWN_FIELD_12 = wb("ACTOR_RESPAWN_FIELD_12")
RESPAWN_FIELD_30 = wb("ACTOR_RESPAWN_FIELD_30")
RESPAWN_SIZE = wb("ACTOR_RESPAWN_SIZE")
SPAWN_RESPAWN_KIND = wb("SPAWN_RESPAWN_KIND")
SPAWN_FINAL_KIND = wb("SPAWN_FINAL_KIND")
TYPE_UNSCORED = wb("ACTOR_TYPE_UNSCORED")
SCORE_TABLE = wb("SPAWN_SCORE_TABLE")
SCORE_TABLE_ENTRIES = wb("SPAWN_SCORE_TABLE_ENTRIES")
SCORE_LEN = wb("SPAWN_SCORE_LEN")
SCORE_SHIFT = wb("SPAWN_SCORE_SHIFT")
KILL_RESPAWN_LIMIT = wb("SPAWN_KILL_RESPAWN_LIMIT")
SPAWN_REARM = wb("SPAWN_REARM")
BOSS_ORIGIN = wb("BOSS_FRAGMENT_ORIGIN")
BOSS_DEFEAT_FLAG = wb("BOSS_DEFEAT_FLAG")
BOSS_DEFEAT_SET = wb("BOSS_DEFEAT_SET")
BOSS_DEFEAT_SFX = wb("BOSS_DEFEAT_SFX")
BOSS_DEFEAT_METER_BONUS = wb("BOSS_DEFEAT_METER_BONUS")
STUB_STOP_OFFSET = 28           # `jsr 28(a1)`: the stub that silences the chip
FIELD_18_SEED = 0x5a            # a byte the `clr.b` has to change


def subq_w_d16(amount, base, displacement):
    """`subq.w #n,d16(An)` — the mirror of `addq_w_d16` above, and the one instruction that lowers
    the template table's live count."""
    return opcode(0x5168 | ((amount & 7) << 9) | base) + word(displacement)


def move_l_indexed_dn(reg, base, index):
    """`move.l 0(An,Dm.l),Dn` — the score-table read, whose extension word's LONGWORD bit is what
    lets the shifted type address the whole 64 KiB above the table."""
    return opcode(0x2030 | (reg << 9) | base) + word((index << 12) | 0x800)


# The two destination modes the respawn continuation adds, and the only site of each in the image.
_MOVE_TO_D16 = 5 << 6           # the DESTINATION mode field of a `move`: d16(An)
_MOVE_FROM_IMM = 0x3c           # ...and a SOURCE mode of 7 reg 4, an immediate in the stream


def move_l_imm_d16(base, value, displacement):
    """`move.l #imm,d16(An)` — the SOURCE longword comes first in the stream and the destination
    displacement after it, which is the order the bytes at $6d50 are in."""
    return opcode(0x2000 | (base << 9) | _MOVE_TO_D16 | _MOVE_FROM_IMM) + longword(value) + word(
        displacement)


def _defeat_entry():
    """$6bb8, whole. Its three branch displacements come out of the pieces they skip, so the boss
    block's length, the score block's and the re-arm's are each part of the claim."""
    base = leaf.entry_of("actor_defeat_and_score")

    def boss_block(at):
        return leaf.assemble(at, [
            lea_abs_l(A1, SND_STUB_TABLE), jsr_d16_an(A1, STUB_STOP_OFFSET),
            move_w_imm_abs_l(BOSS_DEFEAT_SET, BOSS_DEFEAT_FLAG),
            move_w_imm_dn(D0, BOSS_DEFEAT_SFX), clr_w_dn(D1),
            lea_abs_l(A1, SND_STUB_TABLE), jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
            move_w_imm_dn(D0, BOSS_DEFEAT_METER_BONUS),
            lambda site: bsr_w(site, leaf.entry_of("hud_meter_add_clamped")),
        ])

    def score_block(at):
        return leaf.assemble(at, [
            moveq_0_dn(D2), lea_abs_l(A2, SCORE_TABLE), move_w_ind_dn(D2, A1, SPAWN_TYPE),
            lsl_w_imm_dn(SCORE_SHIFT, D2), move_l_indexed_dn(D0, A2, D2),
            lambda site: bsr_w(site, leaf.entry_of("bcd_add_score_bd70")),
            addq_w_d16(1, A1, SPAWN_KILL_COUNT),
            cmpi_w_d16(A1, KILL_RESPAWN_LIMIT, SPAWN_KILL_COUNT),
            lambda site: branch_w_to(BLE_W, site, DEFEAT_RESPAWN_PC),
        ])

    rearm = (move_b_imm_d16(A1, SPAWN_REARM, SPAWN_ARMED)
             + move_b_imm_d16(A1, SPAWN_REARM, SPAWN_COUNTDOWN))
    gate_skips = cmpa_l_imm(A0, BOSS_ORIGIN) + opcode(BNE_W) + word(0) + boss_block(0)

    return leaf.assemble(base, [
        tst_w_abs_w(FLAG_A32), branch(BEQ_W, gate_skips),
        cmpa_l_imm(A0, BOSS_ORIGIN), lambda at: branch(BNE_W, boss_block(at)), boss_block,
        clr_b_d16(A0, FIELD_18), moveq_0_dn(D0), movea_l_abs_l(A1, TABLE_PTR),
        move_b_d16_dn(D0, A0, TEMPLATE_SLOT), lsl_l_imm_dn(TEMPLATE_SLOT_SHIFT, D0),
        lea_indexed(A1, D0),
        cmpi_w_d16(A0, TYPE_UNSCORED, ACTOR_TYPE),
        lambda at: branch(BEQ_W, score_block(at)), score_block,
        movea_l_abs_l(A6, TABLE_PTR),
        subq_w_d16(1, A6, -SPAWN_HEADER_BYTES + HEADER_LIVE),
        move_w_imm_ind(A0, FREE_MARKER),
        tst_w_d16(A6, -SPAWN_HEADER_BYTES + HEADER_WRAPPED),
        branch(BEQ_W, rearm), rearm, RTS,
    ])


DEFEAT_BODY = _defeat_entry()


def _transfer_site():
    """SEARCHED for rather than transcribed: the one address in the body at which the four bytes are
    a `ble.w` aimed at DEFEAT_RESPAWN_PC. A displacement depends on where it sits, so a wrong address
    cannot match — and a second match would mean the routine has two exits, which is the thing worth
    failing on."""
    entry = leaf.entry_of("actor_defeat_and_score")
    sites = [entry + at for at in range(0, len(DEFEAT_BODY), WORD_LEN)
             if DEFEAT_BODY[at:at + BRANCH_W_BYTES] == branch_w_to(BLE_W, entry + at,
                                                                   DEFEAT_RESPAWN_PC)]
    assert len(sites) == 1, f"the body has {len(sites)} `ble.w {DEFEAT_RESPAWN_PC:#x}` site(s)"
    return sites[0]


# The `ble.w` itself: the witness that a run really left through the tail rather than returning. Its
# address is the score block's own end, so the entry pin above puts it here — and the RETIRE TAIL is
# the instruction immediately after it, which is where the continuation's `bmi.w` comes back to.
DEFEAT_TRANSFER = _transfer_site()
RETIRE_TAIL_PC = DEFEAT_TRANSFER + BRANCH_W_BYTES


def _respawn_entry():
    """$6cdc, whole. Its four LOCAL branch displacements come out of the pieces they skip, and the
    one that is not local — the `bmi.w` back into $6bb8's retire tail — is derived from the `ble.w`
    the body above assembles rather than transcribed."""
    base = DEFEAT_RESPAWN_PC

    def drawn(field, routine):
        """`move.w N(a1),d0 / tst.w d0 / bne <past the bsr> / bsr.w <draw>` — a nonzero forced kind
        skips the draw, which is the whole of what the two template fields are for. The `bsr.w`'s
        displacement needs its own address, so an arm is a list of pieces rather than bytes."""
        return [move_w_ind_dn(D0, A1, field), tst_w_dn(D0), branch_over(BNE_W, BSR_W_BYTES),
                lambda at: bsr_w(at, leaf.entry_of(routine))]

    final_arm = drawn(SPAWN_FINAL_KIND, "stage_random_kind8")
    final_bytes = len(leaf.assemble(base, final_arm))
    early_arm = drawn(SPAWN_RESPAWN_KIND, "stage_random_kind32") + [
        branch_over(BRA_W, final_bytes)]
    early_bytes = len(leaf.assemble(base, early_arm))

    return leaf.assemble(base, [
        moveq_0_dn(D0), cmpi_w_d16(A1, KILL_RESPAWN_LIMIT, SPAWN_KILL_COUNT),
        branch_over(BEQ_W, early_bytes), *early_arm, *final_arm,
        tst_w_dn(D0), lambda at: branch_w_to(BMI_W, at, RETIRE_TAIL_PC),
        move_b_dn_d16(D0, A0, KIND),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, RESPAWN_FIELD_10, FIELD_10),
        move_b_imm_d16(A0, RESPAWN_SPEED, SPEED),
        move_b_imm_d16(A0, RESPAWN_FIELD_12, FIELD_12),
        move_b_imm_d16(A0, RESPAWN_FIELD_30, FIELD_30),
        lea_abs_l(A2, KIND_TABLE), lsl_w_imm_dn(KIND_RECORD_SHIFT, D0), lea_indexed(A2, D0),
        move_w_postinc_d16(A2, A0, ACTOR_TYPE), move_w_postinc_d16(A2, A0, ACTOR_SPRITE),
        move_l_imm_d16(A0, RESPAWN_SIZE, HALF_WIDTH),
        RTS,
    ])


# --- $6528: the aim table, and the eight encodings it took to pin it ------------------------------
# THE PIN ../STATUS.md CARRIED AS AN OBLIGATION SINCE BATCH 37. This routine's 94 bytes need eight
# encodings no other body in this project spells — `movem.l` in both directions (whose register mask
# is numbered the OPPOSITE way round for the two), `roxl.w`, `exg` in both operand orders, `neg.w`,
# `eori.w`, `addq.w`, `adda.w` and `ext.w` — so until slot 45 arrived with a second caller it was
# pinned only by the differential over slot 21's aimed shot. All eight are in leaf.py now.
AIM_TABLE = wb("ACTOR_AIM_TABLE")
AIM_ROW_SHIFT = 5                # `asl.w #5,d4` == log2(WB_ACTOR_AIM_ROW_BYTES)
AIM_PAIR_SHIFT = 1               # `asl.w #1,d4` == log2(WB_ACTOR_AIM_PAIR_BYTES)
AIM_CODE_BASE = wb("ACTOR_AIM_CODE_BASE")
AIM_CODE_DX_EOR = wb("ACTOR_AIM_CODE_DX_EOR")
AIM_CODE_DY_EOR = wb("ACTOR_AIM_CODE_DY_EOR")
AIM_CODE_SWAP_BIT = wb("ACTOR_AIM_CODE_SWAP_BIT")
AIM_SAVED_PUSH_MASK = 0x3ffe     # d2-a6 as -(An) numbers it, a7 down to d0
AIM_SAVED_POP_MASK = 0x7ffc      # ...and the SAME registers as (An)+ numbers them, d0 up to a7
BGE_S = 0x6c00
D3, D4 = 3, 4


def _bcc_s(condition, *over):
    """`bcc.s` past exactly ``over``. A short branch's displacement is the spanned bytes THEMSELVES,
    with no BRANCH_EXTENSION: the byte sits in the opcode word rather than after it. $6528 spells
    every one of its six branches short, which is the whole reason this file needed the form."""
    spanned = sum(len(piece) for piece in over)
    assert 0 < spanned < 0x80, f"{spanned} does not fit a `bcc.s` byte displacement"
    return opcode(condition | spanned)


def _aim_ratio_step(shift):
    """One of the three ratio tests: halve or double the far axis, compare, and count the near one
    past it. `shift` is the instruction that moves d2 before the compare."""
    bump = addq_w_dn(1, D4)
    return [shift, cmp_w_dn_dn(D3, D2), _bcc_s(BGE_S, bump), bump]


def _aim_velocity_entry():
    """The whole 94 bytes. Two sign folds into the first quadrant, each recording itself in d4 with
    an `eori.w`; a THIRD swap on the bit those two `eori`s leave; then the three ratio steps, whose
    middle one is the `roxl.w` that reads the X flag `asr.w #1,d2` left — and which the `addq.w`
    between them can overwrite. d4 is finally doubled into a pair index and added to the row."""
    swap_back = exg_dn_dn(D3, D2)
    dx_negative = [neg_w_dn(D2), eori_w_dn(D4, AIM_CODE_DX_EOR)]
    dy_negative = [neg_w_dn(D3), exg_dn_dn(D2, D3), eori_w_dn(D4, AIM_CODE_DY_EOR)]

    return b"".join([
        movem_l_push(AIM_SAVED_PUSH_MASK),
        asl_w_imm_dn(AIM_ROW_SHIFT, D4), lea_abs_l(A1, AIM_TABLE), lea_indexed(A1, D4),
        move_w_imm_dn(D4, AIM_CODE_BASE),
        # The y delta is taken FIRST and the x one second, and it is the SECOND whose `bge` runs.
        sub_w_dn_dn(D3, D1), sub_w_dn_dn(D2, D0), _bcc_s(BGE_S, *dx_negative), *dx_negative,
        # ...and this one is a `tst.w`, which CLEARS V — so it reads the sign of the wrapped
        # difference where the one above reads N^V of the two operands.
        tst_w_dn(D3), _bcc_s(BGE_S, *dy_negative), *dy_negative,
        btst_imm_dn(AIM_CODE_SWAP_BIT, D4), _bcc_s(BNE_S, swap_back), swap_back,
        *_aim_ratio_step(asr_w_imm_dn(1, D2)),
        *_aim_ratio_step(roxl_w_imm_dn(1, D2)),
        *_aim_ratio_step(asl_w_imm_dn(1, D2)),
        asl_w_imm_dn(AIM_PAIR_SHIFT, D4), adda_w_dn_an(A1, D4),
        move_b_postinc_dn(D0, A1), move_b_postinc_dn(D1, A1),
        ext_w_dn(D0), ext_w_dn(D1),
        movem_l_pop(AIM_SAVED_POP_MASK),
        RTS,
    ])


ENTRY_BYTES = {
    "actor_aim_velocity": _aim_velocity_entry(),
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
    "actor_spawn_pass": _spawn_pass_entry(),
    "actor_template_set_hitpoints": _set_hitpoints_entry(),
    "actor_hop_or_flip_side": _hop_or_flip_entry(),
    "actor_toggle_side_flag": _toggle_side_entry(),
    "actor_turn_and_launch": _turn_and_launch_entry(),
    "actor_damage_followed": _damage_followed_entry(),
    "actor_knock_back_and_launch": _knock_back_and_launch_entry(),
    "actor_damage_template_hitpoints": _damage_template_entry(),
    "actor_defeat_and_score": DEFEAT_BODY,
    "actor_respawn_as_new_kind": _respawn_entry(),
}
RECONSTRUCTED_ROUTINES = 23


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    # $6528 is bounded by its OWN table, which its `lea $6586.l` names — the same shape as the two
    # damage paths below rather than a Ghidra function.
    ("actor_aim_velocity", 94),
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
    ("actor_spawn_pass", 162),
    ("actor_template_set_hitpoints", 48),
    # The three below are NOT the scan's numbers, and each says why. $2b5a and $2b8e have no Ghidra
    # function at all; $2b82 has one, of 20 bytes, and it is 20 because Ghidra folded the 8-byte tail
    # its two backward branches reach into the body. The extents here are the `rts` each routine's
    # own instruction stream ends at — $2b5a's 40 DOES include the shared tail, which sits inside it.
    ("actor_hop_or_flip_side", 40),
    ("actor_toggle_side_flag", 12),
    ("actor_turn_and_launch", 58),
    # ...and the two damage paths, whose extents are the DATA either side of them rather than a
    # Ghidra function: $69fe ends where its own `lea $6b08.l,a2` names, and $6b46 begins where that
    # word table stops (test_the_damage_table_is_the_data_between_the_two_bodies).
    ("actor_damage_followed", 266),
    # ...and $6ade, which has no Ghidra function either and never could: it is the last forty-two
    # bytes of the body above, so its extent is that body's end minus its own entry — the arithmetic
    # `test_the_shared_tail_is_the_last_forty_two_bytes_of_the_damage_path` states.
    ("actor_knock_back_and_launch", 42),
    ("actor_damage_template_hitpoints", 114),
    # ...and $6cdc, which Ghidra has no function for at all: its extent runs from the one
    # `ble.w` aimed at it to the `rts` at $6d58, whose second byte is the last of the body.
    ("actor_respawn_as_new_kind", 126),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The pins above would still pass on a PREFIX of a routine. These are the sizes the Ghidra
    function table gives (../out/hw_scan.tsv) except where the comment above says otherwise, so a
    body reconstructed one instruction short fails here instead of leaving the tail unpinned."""
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records")


def test_the_three_flag_routines_share_one_tail():
    """`flip_side_flag` is one static helper behind three reconstructions, so this states the claim
    that makes that legitimate: the eight bytes really are at $2b5a's end, and $2b82's and $2b8e's
    branch displacements really do land on them and on nothing else."""
    tail = _side_flip_tail_address()
    actual = bytes(harness.BASE_IMAGE[tail:tail + len(SIDE_FLIP_TAIL)])
    assert actual == SIDE_FLIP_TAIL, (
        f"the shared tail at {tail:#x} is {actual.hex()}, not the {SIDE_FLIP_TAIL.hex()} all three "
        f"pins are built from")

    toggle = leaf.entry_of("actor_toggle_side_flag")
    for name, at in (("actor_toggle_side_flag beq", toggle + 2),
                     ("actor_toggle_side_flag bne", toggle + 8)):
        displacement = harness.BASE_IMAGE[at + 1]
        landing = at + BRANCH_EXTENSION + (displacement - 0x100)
        assert landing == tail, f"{name} at {at:#x} lands on {landing:#x}, not the tail {tail:#x}"

    # $2b8e reaches the same three writes through its OWN copy rather than through the tail, which
    # is why src/actor.c spells them out there; the two are different instruction streams.
    launch = leaf.entry_of("actor_turn_and_launch")
    assert bytes(harness.BASE_IMAGE[launch:launch + len(ENTRY_BYTES["actor_turn_and_launch"])]
                 ).find(SIDE_FLIP_TAIL[:-len(RTS)]) > 0, (
        "actor_turn_and_launch no longer contains the `bchg` its own tail repeats")


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
        assert program[at - WORD_LEN:at] == opcode(JSR_ABS_L), (
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


# --- $ff42 and $1006a: the per-frame spawn pass ----------------------------------------------------
# The template table lives in plain RAM (the spawn battery's own), and the pass reads a FOUR-WORD
# HEADER below it — so a case seeds a band that starts SPAWN_HEADER_BYTES lower, with a whole record
# of margin at each end and every byte keyed on its ADDRESS. A walk that ran one record long, or a
# header field read from the wrong offset, then lands on bytes that are wrong for where they were
# written rather than on zeros.
SPAWN_TABLE = TEMPLATE_TABLE
SPAWN_TABLE_SLOTS = 8                 # records before the terminator
SPAWN_BAND_MARGIN = SPAWN_RECORD_BYTES
HITPOINT_TABLE_BYTES = HITPOINT_TABLE_ENTRIES * WORD_LEN

# The pass walks the table twice at worst and can spawn every record in it; the cap is that geometry
# with room for the calls, and it is sized for the WORST case because the attribution pass poisons
# the very bytes (WB_SPAWN_ARMED, the countdowns) that decide how many spawns run.
SPAWN_PASS_INSN_PER_RECORD = 10
SPAWN_PASS_INSN_PER_SPAWN = 130
SPAWN_PASS_INSN_CAP = (SPAWN_PASS_INSN_PER_RECORD * 2 * (SPAWN_TABLE_SLOTS + 1)
                       + SPAWN_PASS_INSN_PER_SPAWN * SPAWN_TABLE_SLOTS + LOOP_INSN_TAIL)

# A first word that is NOT the terminator, so the address-keyed filler cannot end a walk by accident.
TEMPLATE_LIVE_MARK = 0x0111

_SPAWN_PASS = leaf.image_glue("actor_spawn_pass")
_SET_HITPOINTS = leaf.register_glue("actor_template_set_hitpoints", [ctypes.c_uint32])


def hitpoint_entry(spawn_type):
    """WHERE the routine looks: `add.w d1,d1` on a zero-extended type, then `adda.l d1,a2`. Every
    case keys its seed off this rather than off the type it happens to have to hand, which is
    docs/methodology.md's second seeding rule."""
    return HITPOINT_TABLE + ((spawn_type * 2) & 0xffff)


def _model_hitpoints(image, template):
    """`4(a0) := (6(a0) asr.w #1) + base` — a SIGNED word shift and a word add."""
    value = s16(u16(image, template + SPAWN_KILL_COUNT)) >> 1
    spawn_type = u16(image, template + SPAWN_TYPE)
    value += (HITPOINT_FIXED_BASE if spawn_type == HITPOINT_TYPE_FIXED
              else u16(image, hitpoint_entry(spawn_type)))
    out = {}
    _put_word(out, template + SPAWN_HITPOINTS, value)
    return out


def _read_long(image, addr):
    return int.from_bytes(bytes(image[addr:addr + LONGWORD_LEN]), "big")


def _model_alloc_low(image):
    """`jsr $1b68.w` — the first free record of the LOW pool of the published table, or
    WB_ACTOR_ALLOC_NONE. Modelled here rather than called because the pass runs it more than once
    and the answer moves as records fill up."""
    table = _read_long(image, TABLE_SELECTED)
    for slot in range(ALLOC_LOW_FIRST, ALLOC_LOW_FIRST + ALLOC_LOW_SLOTS):
        record = table + slot * RECORD_BYTES
        if u16(image, record + ACTOR_X) == FREE_MARKER:
            return record
    return ALLOC_NONE


def _model_spawn_pass(image):
    """The whole pass, transcribed. It runs on a MUTABLE copy and records every byte it writes,
    because the arms are sequential: the record one spawn fills in is no longer free when the next
    allocation looks, and the sweep can spawn several in one pass."""
    mem = bytearray(image)
    out = {}

    def apply(writes):
        for addr, value in writes.items():
            mem[addr] = value
            out[addr] = value

    def put_word(addr, value):
        applied = {}
        _put_word(applied, addr, value)
        apply(applied)

    def walk_to_terminator(record):
        """`lea 32(a0),a0 / cmpi.w #$ffff,(a0) / bne` — the FIRST record is always handled and the
        terminator is only ever tested after one has been."""
        while True:
            yield record
            record += SPAWN_RECORD_BYTES
            if u16(mem, record) == SPAWN_TERMINATOR:
                return

    if u16(mem, FLAG_A30) != 0:
        return out
    table = _read_long(mem, TABLE_PTR)
    header = table - SPAWN_HEADER_BYTES

    for record in walk_to_terminator(table):
        if mem[record + SPAWN_ARMED] != 0:
            apply({record + SPAWN_COUNTDOWN: (mem[record + SPAWN_COUNTDOWN] - 1) & BYTE_MASK})

    def spawn(template):
        put_word(header + HEADER_LIVE, u16(mem, header + HEADER_LIVE) + 1)
        apply(_model_spawn(mem, template, _model_alloc_low(mem)))
        apply(_model_hitpoints(mem, template))

    if u16(mem, header + HEADER_MAX_LIVE) == u16(mem, header + HEADER_LIVE):
        return out

    if u16(mem, header + HEADER_WRAPPED) != WRAPPED_SET:
        cursor = u16(mem, header + HEADER_CURSOR)
        put_word(header + HEADER_CURSOR, cursor + 1)
        # `lsl.l #5,d0` then `lea 0(a0,d0.w),a0`: the extension word is $0000, so the LOW WORD of
        # the shifted cursor is SIGN-EXTENDED into the sum and the long result never reaches it.
        template = table + s16(cursor * SPAWN_RECORD_BYTES)
        if u16(mem, template + SPAWN_RECORD_BYTES) == SPAWN_TERMINATOR:
            put_word(header + HEADER_WRAPPED, WRAPPED_SET)
        spawn(template)
        return out

    for record in walk_to_terminator(table):
        if mem[record + SPAWN_ARMED] != 0 and mem[record + SPAWN_COUNTDOWN] == 0:
            apply({record + SPAWN_ARMED: 0})
            spawn(record)
    return out


def _template_band(salt, base, slots, pokes):
    """One address-keyed band over a template table, its header and a record of margin either side,
    with every record's first word forced away from the terminator."""
    lo = base - SPAWN_HEADER_BYTES - SPAWN_BAND_MARGIN
    length = SPAWN_HEADER_BYTES + SPAWN_BAND_MARGIN + (slots + 1) * SPAWN_RECORD_BYTES + (
        SPAWN_BAND_MARGIN)
    pokes[lo] = keyed_block(lo, length, salt)
    for slot in range(slots):
        pokes[base + slot * SPAWN_RECORD_BYTES] = word(TEMPLATE_LIVE_MARK + slot)
    pokes[base + slots * SPAWN_RECORD_BYTES] = word(SPAWN_TERMINATOR)


def _spawn_pass_pokes(salt, records, header, flag_a30=0, free_slots=None,
                      actor_table=TABLE_DEFAULT, extra_tables=(), slots=SPAWN_TABLE_SLOTS,
                      terminate_slot=None):
    """`records` is one dict per template slot — any of armed/countdown/type/kills/x/y — and
    `header` the four words by name. `free_slots` is which actor slots hold WB_ACTOR_FREE_MARKER;
    None means the whole LOW pool is free. `terminate_slot` stamps a SECOND terminator inside the
    table, which is how a case makes the walk's very first record the terminating one."""
    pokes = _state_pokes(salt, {FLAG_A30: flag_a30})
    pokes[SIZE_TABLE] = keyed_block(SIZE_TABLE, SIZE_TABLE_ENTRIES * LONGWORD_LEN, salt)
    pokes[HITPOINT_TABLE] = keyed_block(HITPOINT_TABLE, HITPOINT_TABLE_BYTES, salt)
    pokes[TABLE_PTR] = longword(SPAWN_TABLE)
    pokes[TABLE_SELECTED] = longword(actor_table)

    _template_band(salt, SPAWN_TABLE, slots, pokes)
    for base, extra_slots in extra_tables:
        _template_band(salt, base, extra_slots, pokes)
    if terminate_slot is not None:
        pokes[SPAWN_TABLE + terminate_slot * SPAWN_RECORD_BYTES] = word(SPAWN_TERMINATOR)

    for name, value in header.items():
        pokes[SPAWN_TABLE - SPAWN_HEADER_BYTES + name] = word(value)
    for slot, fields in enumerate(records):
        record = SPAWN_TABLE + slot * SPAWN_RECORD_BYTES
        for field, value in fields.items():
            offset = {"armed": SPAWN_ARMED, "countdown": SPAWN_COUNTDOWN}.get(field)
            if offset is not None:
                pokes[record + offset] = bytes([value])
                continue
            pokes[record + {"type": SPAWN_TYPE, "kills": SPAWN_KILL_COUNT,
                            "x": SPAWN_X, "y": SPAWN_Y}[field]] = word(value)

    if free_slots is None:
        free_slots = set(range(ALLOC_LOW_FIRST, ALLOC_LOW_FIRST + ALLOC_LOW_SLOTS))
    for slot in range(SCREEN_RECORD_COUNT):
        pokes[actor_table + slot * RECORD_BYTES + ACTOR_X] = word(
            FREE_MARKER if slot in free_slots else OCCUPIED)
    return pokes


def _run_spawn_pass(case, pokes):
    what = f"actor_spawn_pass {case}"
    image = harness.make_image(pokes)
    expected = _model_spawn_pass(image)
    info = leaf.run("actor_spawn_pass", _SPAWN_PASS, merge_bands(expected), what,
                    regs={"_pokes": pokes}, max_insns=SPAWN_PASS_INSN_CAP)
    _assert_writes(info, expected, what)
    return expected


# A table whose live count has already reached its maximum: the countdown walk still runs, and
# nothing else does.
FULL_HEADER = {HEADER_MAX_LIVE: 4, HEADER_LIVE: 4, HEADER_CURSOR: 0, HEADER_WRAPPED: 0}
CURSOR_HEADER = {HEADER_MAX_LIVE: 9, HEADER_LIVE: 1, HEADER_CURSOR: 0, HEADER_WRAPPED: 0}
SWEEP_HEADER = {HEADER_MAX_LIVE: 9, HEADER_LIVE: 1, HEADER_CURSOR: SPAWN_TABLE_SLOTS,
                HEADER_WRAPPED: WRAPPED_SET}


def _armed_records(armed_countdowns, spawn_type=0x10, kills=0):
    return [{"armed": armed, "countdown": countdown, "type": spawn_type, "kills": kills,
             "x": 0x0140 + slot, "y": 0x0080 + slot}
            for slot, (armed, countdown) in enumerate(armed_countdowns)]


@pytest.mark.parametrize("flag", [0xffff, 0x0001, 0x8000, 0x7fff],
                         ids=lambda v: f"a30{v:#06x}")
def test_the_pass_does_nothing_at_all_while_the_mode_flag_is_set(flag):
    """`tst.w $a30.w / bne` is a NONZERO test where the two projections read the same word with a
    `bpl`, so $0001 and $7fff are the values that tell the two readings apart — and the countdown
    walk, which runs before everything else, must not run either."""
    what = f"actor_spawn_pass gated a30={flag:#06x}"
    pokes = _spawn_pass_pokes(case_salt(what), _armed_records([(0xff, 3)] * SPAWN_TABLE_SLOTS),
                              CURSOR_HEADER, flag_a30=flag)
    info = leaf.run("actor_spawn_pass", _SPAWN_PASS, [], what, regs={"_pokes": pokes},
                    max_insns=SPAWN_PASS_INSN_CAP)
    assert not program_writes(info), f"{what}: it wrote memory behind a raised gate"


def test_the_countdown_walk_runs_before_the_capacity_test_returns():
    """The walk is above the `cmp.w -6(a6),d0`, so a table at capacity still counts down. Half the
    records are armed and half are not, and only the armed ones may move."""
    case = "at capacity"
    records = _armed_records([(0xff, 3), (0, 3), (1, 1), (0, 0), (0x80, 0x40), (0, 9),
                              (0xff, 0x10), (0, 2)])
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"), records, FULL_HEADER))
    assert set(expected) == {SPAWN_TABLE + slot * SPAWN_RECORD_BYTES + SPAWN_COUNTDOWN
                             for slot, fields in enumerate(records) if fields["armed"]}, (
        "the capacity arm wrote something other than the armed records' countdown bytes")


def test_the_countdown_byte_wraps_rather_than_sticking_at_zero():
    """`subq.b #1` on a record already at zero — reachable in the CURSOR arm, where the sweep that
    would have cleared WB_SPAWN_ARMED has not run yet."""
    _run_spawn_pass("countdown at zero", _spawn_pass_pokes(
        case_salt("actor_spawn_pass countdown at zero"),
        _armed_records([(0xff, 0), (0xff, 1), (0, 0)] + [(0, 5)] * 5), CURSOR_HEADER))


@pytest.mark.parametrize("cursor", [0, 1, SPAWN_TABLE_SLOTS - 2],
                         ids=lambda v: f"cursor{v}")
def test_the_cursor_arm_spawns_the_one_template_it_names(cursor):
    header = {**CURSOR_HEADER, HEADER_CURSOR: cursor}
    case = f"cursor arm at {cursor}"
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"), _armed_records([(0, 5)] * SPAWN_TABLE_SLOTS),
        header))
    template = SPAWN_TABLE + cursor * SPAWN_RECORD_BYTES
    assert template + SPAWN_HITPOINTS in expected, (
        f"{case}: the hit-point seeder never ran on template {cursor}")


def test_the_cursor_arm_raises_the_wrapped_flag_on_the_last_record():
    """`cmpi.w #$ffff,32(a0)`: the flag goes up when the record AFTER the one being spawned is the
    terminator, i.e. one pass before the cursor would have run off the end."""
    case = "cursor arm at the last record"
    header = {**CURSOR_HEADER, HEADER_CURSOR: SPAWN_TABLE_SLOTS - 1}
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"), _armed_records([(0, 5)] * SPAWN_TABLE_SLOTS),
        header))
    wrapped = SPAWN_TABLE - SPAWN_HEADER_BYTES + HEADER_WRAPPED
    assert expected.get(wrapped) == WRAPPED_SET >> 8, (
        f"{case}: the wrapped flag at {wrapped:#x} was not raised")


def test_the_cursor_is_a_word_and_the_lea_that_consumes_it_sign_extends():
    """`lsl.l #5,d0 / lea 0(a0,d0.w),a0` with a $0000 extension word — a cursor of 1024 shifts to
    $8000 and indexes 32 KB BELOW the table, not 32 KB above it. Unreachable from the shipped data,
    which is why the template it names is seeded rather than assumed."""
    below = SPAWN_TABLE - 0x8000
    cursor = 0x8000 // SPAWN_RECORD_BYTES
    case = "cursor past the sign boundary"
    _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"), _armed_records([(0, 5)] * SPAWN_TABLE_SLOTS),
        {**CURSOR_HEADER, HEADER_CURSOR: cursor},
        extra_tables=((below, 4),)))


# A record is READY at the sweep only if it reaches it holding zero, and the countdown walk above
# has already run — so a case seeds 1 for the records it means to spawn. Seeding 0 instead makes the
# walk wrap the byte to $ff, which is its own case below.
SWEEP_READY_COUNTDOWN = 1


@pytest.mark.parametrize("armed_countdowns,case", [
    ([(0xff, SWEEP_READY_COUNTDOWN), (0, 0), (0xff, SWEEP_READY_COUNTDOWN), (0, 5), (0xff, 2),
      (0, 0), (0, 0), (0xff, SWEEP_READY_COUNTDOWN)], "three of eight ready"),
    ([(0, 0)] * SPAWN_TABLE_SLOTS, "none armed"),
    ([(0xff, SWEEP_READY_COUNTDOWN)] * SPAWN_TABLE_SLOTS, "every record ready"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_sweep_arm_spawns_every_armed_template_whose_countdown_has_run_out(armed_countdowns,
                                                                              case):
    """Both `tst.b` tests, over the three shapes SWEEP_HEADER's own seeds reach: no record ready,
    three of eight, and all eight — which raises the live count from 1 to exactly
    WB_SPAWN_HEADER_MAX_LIVE and fills eight of the nine free records without exhausting the pool.
    CROSSING the maximum and running the pool out are the case below, which seeds for them."""
    _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"), _armed_records(armed_countdowns), SWEEP_HEADER))


# The seeds SWEEP_HEADER cannot supply: a maximum the eight spawns CROSS (it is compared once, above
# both arms, so nothing re-reads it) and a pool smaller than the sweep needs. Three free records
# against eight ready templates is what makes the pool run out with five spawns still to come.
OVERSHOOT_MAX_LIVE = 3
OVERSHOOT_LIVE = 1
OVERSHOOT_FREE_SLOTS = 3


def test_the_sweep_crosses_the_capacity_and_runs_the_pool_out_partway():
    """The capacity test is ABOVE both arms and runs ONCE, while the sweep raises `-6(a6)` per
    spawn — so a pass entered below the maximum carries the live count past it and keeps spawning.
    A port that re-tested capacity per spawn stops at OVERSHOOT_MAX_LIVE and both the header word
    and the records below it come out different.

    The pool runs out partway on purpose: only the first OVERSHOOT_FREE_SLOTS records of the low
    pool are free, so the later spawns get WB_ACTOR_ALLOC_NONE and land on the vector page — the
    same untested `jsr $1b68.w` result the two cases below pin from an empty pool, reached here
    with the pool emptying UNDER the routine instead."""
    case = f"sweep across the capacity with {OVERSHOOT_FREE_SLOTS} free records"
    header = {**SWEEP_HEADER, HEADER_MAX_LIVE: OVERSHOOT_MAX_LIVE, HEADER_LIVE: OVERSHOOT_LIVE}
    free_slots = set(range(ALLOC_LOW_FIRST, ALLOC_LOW_FIRST + OVERSHOOT_FREE_SLOTS))
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"),
        _armed_records([(0xff, SWEEP_READY_COUNTDOWN)] * SPAWN_TABLE_SLOTS), header,
        free_slots=free_slots))

    live = SPAWN_TABLE - SPAWN_HEADER_BYTES + HEADER_LIVE
    live_after = expected[live] << 8 | expected[live + 1]
    assert live_after == OVERSHOOT_LIVE + SPAWN_TABLE_SLOTS, (
        f"{case}: the live count came back {live_after}, not the "
        f"{OVERSHOOT_LIVE + SPAWN_TABLE_SLOTS} that one spawn per ready template makes — the pass "
        f"stopped at the maximum, so the capacity test was read more than once")
    assert live_after > header[HEADER_MAX_LIVE], (
        f"{case}: the count ended at {live_after}, not past the {header[HEADER_MAX_LIVE]} it was "
        f"compared against — the seeds no longer cross the capacity at all")

    filled = {(addr - TABLE_DEFAULT) // RECORD_BYTES
              for addr in expected if TABLE_DEFAULT <= addr < TABLE_DEFAULT + TABLE_BYTES}
    assert filled == free_slots, (
        f"{case}: the spawns filled slots {sorted(filled)}, not the {sorted(free_slots)} the case "
        f"left free")
    assert any(addr < RECORD_BYTES for addr in expected), (
        f"{case}: nothing reached the vector page, so the pool never ran out and the case is no "
        f"longer testing what it says")


def test_the_countdown_walk_runs_before_the_sweep_reads_the_same_byte():
    """The two loops are not independent: an armed record seeded at ZERO is decremented to $ff by
    the walk and the sweep then skips it, so the ready state cannot be reached from below. A port
    that ran the sweep first, or that clamped the `subq.b`, spawns here and the original does not."""
    case = "armed at zero before the sweep"
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"),
        _armed_records([(0xff, 0)] + [(0, 5)] * (SPAWN_TABLE_SLOTS - 1)), SWEEP_HEADER))
    countdown = SPAWN_TABLE + SPAWN_COUNTDOWN
    assert set(expected) == {countdown}, (
        f"{case}: the pass wrote {[hex(a) for a in sorted(expected)]}, not the wrapped countdown "
        f"byte alone")
    assert expected[countdown] == BYTE_MASK


@pytest.mark.parametrize("arm,header", [("cursor", CURSOR_HEADER), ("sweep", SWEEP_HEADER)],
                         ids=["cursor", "sweep"])
def test_a_full_pool_stamps_the_spawn_over_the_vector_page(arm, header):
    """THE registered finding, pinned. Neither `jsr $1b68.w` site tests its result, so a table with
    no free record in the LOW pool hands `actor_spawn_from_template` a1 = $0 and its stores land on
    absolute $0..$1f. The case seeds BOTH pools full — the high one is not this routine's, and
    seeding only the low one would leave the claim resting on which allocator was called.

    The write set is asserted EXACTLY, so this states which vector-page bytes move: eighteen of the
    thirty-two, because the spawn writes ten fields and not a whole record.
    """
    case = f"{arm} arm with a full pool"
    expected = _run_spawn_pass(case, _spawn_pass_pokes(
        case_salt(f"actor_spawn_pass {case}"),
        _armed_records([(0xff, SWEEP_READY_COUNTDOWN)] + [(0, 5)] * (SPAWN_TABLE_SLOTS - 1)),
        header, free_slots=set()))
    stamped = sorted(addr for addr in expected if addr < RECORD_BYTES)
    assert stamped == ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
                       + [0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x1e, 0x1f]), (
        f"{case}: the vector page took {[hex(a) for a in stamped]}, which is not the spawn's own "
        f"eighteen fields")


def test_the_pass_walks_whichever_actor_table_was_published():
    """`jsr $1b68.w` follows WB_ACTOR_TABLE_SELECTED, so the spawn lands in the table
    `project_actor_list` last named — the other two are seeded with no free record at all."""
    case = "against the A32 table"
    pokes = _spawn_pass_pokes(case_salt(f"actor_spawn_pass {case}"),
                              _armed_records([(0, 5)] * SPAWN_TABLE_SLOTS), CURSOR_HEADER,
                              actor_table=TABLE_A32)
    for other in (TABLE_DEFAULT, TABLE_A30):
        for slot in range(SCREEN_RECORD_COUNT):
            pokes[other + slot * RECORD_BYTES + ACTOR_X] = word(OCCUPIED)
    expected = _run_spawn_pass(case, pokes)
    assert any(TABLE_A32 <= addr < TABLE_A32 + TABLE_BYTES for addr in expected), (
        f"{case}: nothing was written into the published table")


# --- $1006a on its own ------------------------------------------------------------------------------
# Every case seeds the hit-point table ADDRESS-KEYED and then reads its expectation back out of the
# seeded image at `hitpoint_entry(type)` — the routine's own arithmetic — so a case cannot agree with
# a port that indexed the table differently.
HITPOINT_INSN_CAP = 24
HITPOINT_TYPES = (0, 1, 2, HITPOINT_TYPE_FIXED, HITPOINT_TYPE_FIXED - 1, HITPOINT_TYPE_FIXED + 1,
                  HITPOINT_TABLE_ENTRIES - 1, HITPOINT_TABLE_ENTRIES, 0x8000, 0xffff)
HITPOINT_KILLS = (0, 1, 2, 3, 0x7fff, 0xffff, 0xfffe, 0x8000)


@pytest.mark.parametrize("kills", HITPOINT_KILLS, ids=lambda v: f"kills{v:#06x}")
@pytest.mark.parametrize("spawn_type", HITPOINT_TYPES, ids=lambda v: f"type{v:#06x}")
def test_the_hitpoint_seed_is_half_the_kill_count_plus_the_types_base(spawn_type, kills):
    """`asr.w #1` is SIGNED — $ffff halves to $ffff, not to $7fff — and every add is a word, so the
    sum wraps inside sixteen bits. `type` $3b takes the constant arm and its two neighbours do not;
    $8000 and $ffff are where `add.w d1,d1` wraps the index back into the table."""
    template = SPAWN_TABLE + 2 * SPAWN_RECORD_BYTES
    case = f"type {spawn_type:#x} kills {kills:#x}"
    what = f"actor_template_set_hitpoints {case}"
    salt = case_salt(what)

    pokes = _state_pokes(salt, {})
    pokes[HITPOINT_TABLE] = keyed_block(HITPOINT_TABLE, HITPOINT_TABLE_BYTES, salt)
    _template_band(salt, SPAWN_TABLE, SPAWN_TABLE_SLOTS, pokes)
    pokes[template + SPAWN_TYPE] = word(spawn_type)
    pokes[template + SPAWN_KILL_COUNT] = word(kills)
    # The entry the routine will index, wherever that lands — including outside the 32 entries the
    # two tables' boundary gives, which is what the last three types are for.
    entry = hitpoint_entry(spawn_type)
    pokes[entry] = word(0x0037)

    image = harness.make_image(pokes)
    expected = _model_hitpoints(image, template)
    info = leaf.run("actor_template_set_hitpoints", _SET_HITPOINTS(template),
                    merge_bands(expected), what, regs={"a0": template, "_pokes": pokes},
                    max_insns=HITPOINT_INSN_CAP)
    _assert_writes(info, expected, what)

    stored = ((expected[template + SPAWN_HITPOINTS] << 8)
              | expected[template + SPAWN_HITPOINTS + 1])
    assert info["regs"]["d0"] == stored, (
        f"{what}: the original left d0={info['regs']['d0']:#x}, not the {stored:#x} it stored — "
        f"`moveq #0,d0` clears the high half, so the whole register is the word")
    assert info["regs"]["d1"] == (spawn_type if spawn_type == HITPOINT_TYPE_FIXED
                                 else (spawn_type * 2) & 0xffff), (
        f"{what}: d1 came back {info['regs']['d1']:#x} — the table arm DOUBLES it and the constant "
        f"arm does not")


def test_the_hitpoint_table_sits_immediately_above_the_size_table():
    """Neither table declares a length, so the 32 entries the header states rest on their being
    back to back — arithmetic over the header's own constants, which fails here if either moves."""
    assert SIZE_TABLE + HITPOINT_TABLE_ENTRIES * LONGWORD_LEN == HITPOINT_TABLE, (
        f"the size table's 32 longwords end at "
        f"{SIZE_TABLE + HITPOINT_TABLE_ENTRIES * LONGWORD_LEN:#x}, not at {HITPOINT_TABLE:#x}")


# --- $2b5a, $2b82, $2b8e: what an actor does when a map step reports back ---------------------------
# All three read d0's low BYTE and three bits of d1. The outcome seeds include two whose LOW byte is
# zero under a nonzero register ($ff00, $deadbe00): those are the only thing that tells `tst.b` from
# a `tst.w`, and the routines' own callers only ever produce $00 and $ff.
FLAG_FAMILY_INSN_CAP = 24
OUTCOME_SEEDS = (0x00, 0xff, 0x01, 0xff00, 0xdeadbe00)
GROUND_SEEDS = (0x0000, 1 << GROUND_STEP_UP_BIT, 1 << GROUND_DROP_TWO_BIT,
                1 << GROUND_DROP_ONE_BIT, 0x0007, 0xffff, 0xdead0000)
SIDE_MASK = 1 << SIDE_BIT

_HOP_OR_FLIP = leaf.register_glue("actor_hop_or_flip_side", [ctypes.c_uint32] * 3)
_TOGGLE_SIDE = leaf.register_glue("actor_toggle_side_flag", [ctypes.c_uint32] * 3)
_TURN_AND_LAUNCH = leaf.register_glue("actor_turn_and_launch", [ctypes.c_uint32] * 3)


def _blocked(outcome):
    return (outcome & BYTE_MASK) == STEP_BLOCKED


def _ground(ground_flags, bit):
    return (ground_flags >> bit) & 1


def _model_hop_or_flip(flags, outcome, ground_flags, actor):
    if not _blocked(outcome):
        return ({actor + ACTOR_FLAGS: flags ^ SIDE_MASK}
                if _ground(ground_flags, GROUND_DROP_TWO_BIT) else {})
    if not _ground(ground_flags, GROUND_STEP_UP_BIT):
        return {actor + ACTOR_FLAGS: flags ^ SIDE_MASK}
    return {actor + ACTOR_FLAGS: (flags & ~(1 << SUPPORTED_BIT)
                                  | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & BYTE_MASK,
            actor + SPEED: HOP_SPEED}


def _model_toggle_side(flags, outcome, ground_flags, actor):
    if _blocked(outcome) or _ground(ground_flags, GROUND_DROP_ONE_BIT):
        return {actor + ACTOR_FLAGS: flags ^ SIDE_MASK}
    return {}


def _model_turn_and_launch(flags, outcome, ground_flags, actor):
    if not (_blocked(outcome) or _ground(ground_flags, GROUND_DROP_ONE_BIT)):
        return {}
    if not flags & (1 << SUPPORTED_BIT):
        return {}
    return {actor + ACTOR_FLAGS: ((flags ^ SIDE_MASK) & ~(1 << SUPPORTED_BIT)
                                  | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & BYTE_MASK,
            actor + SPEED: TURN_LAUNCH_SPEED}


FLAG_FAMILY = {
    "actor_hop_or_flip_side": (_HOP_OR_FLIP, _model_hop_or_flip),
    "actor_toggle_side_flag": (_TOGGLE_SIDE, _model_toggle_side),
    "actor_turn_and_launch": (_TURN_AND_LAUNCH, _model_turn_and_launch),
}


@pytest.mark.parametrize("ground_flags", GROUND_SEEDS, ids=lambda v: f"ground{v:#x}")
@pytest.mark.parametrize("outcome", OUTCOME_SEEDS, ids=lambda v: f"d0{v:#x}")
@pytest.mark.parametrize("flags", STATE_FLAG_SEEDS, ids=lambda v: f"flags{v:#04x}")
@pytest.mark.parametrize("name", sorted(FLAG_FAMILY), ids=sorted(FLAG_FAMILY))
def test_the_step_reaction_writes_exactly_the_flag_bits_its_arm_names(name, flags, outcome,
                                                                     ground_flags):
    """One grid over all three, because they are one shape with three different bits: the outcome
    byte, the ground flag each reads, and the four flag-byte seeds the rest of this battery uses —
    which is what says a `bchg` FLIPS rather than sets, and that a byte-wide op leaves its
    neighbours alone."""
    glue, model = FLAG_FAMILY[name]
    actor = TABLE_DEFAULT + 4 * RECORD_BYTES
    what = f"{name} flags={flags:#04x} d0={outcome:#x} d1={ground_flags:#x}"
    pokes = _state_pokes(case_salt(what), {})
    pokes[actor + ACTOR_FLAGS] = bytes([flags])

    expected = model(flags, outcome, ground_flags, actor)
    info = leaf.run(name, glue(actor, outcome, ground_flags), merge_bands(expected), what,
                    regs={"a0": actor, "d0": outcome, "d1": ground_flags, "_pokes": pokes},
                    max_insns=FLAG_FAMILY_INSN_CAP)
    _assert_writes(info, expected, what)

    assert info["regs"]["a0"] == actor, f"{what}: a0 moved, which none of the three does"
    assert info["regs"]["d1"] == ground_flags, f"{what}: d1 moved"
    # $2b5a is the only one that clobbers d0, and only on the arm that launches: `move.w #$4,d0`
    # writes the LOW WORD, so the caller's high half survives.
    hops = (name == "actor_hop_or_flip_side" and _blocked(outcome)
            and _ground(ground_flags, GROUND_STEP_UP_BIT))
    wanted = (outcome & ~0xffff) | HOP_SPEED if hops else outcome
    assert info["regs"]["d0"] == wanted, (
        f"{what}: the original left d0={info['regs']['d0']:#x}, not {wanted:#x}")


def test_the_launch_arm_is_the_routine_the_hop_calls_and_the_turn_spells_out():
    """$2b5a reaches WB_ACTOR_HOP_SPEED through `bsr $2af2` while $2b8e writes the same three bits
    and a speed byte inline — so this states that the two really are the same three writes, which is
    the claim src/actor.c makes by NOT calling actor_start_motion_at_speed from the second one."""
    actor = TABLE_DEFAULT + 4 * RECORD_BYTES
    for flags in STATE_FLAG_SEEDS:
        launched = _model_turn_and_launch(flags | (1 << SUPPORTED_BIT), STEP_BLOCKED, 0, actor)
        hopped = _model_hop_or_flip(flags ^ SIDE_MASK | (1 << SUPPORTED_BIT), STEP_BLOCKED,
                                    1 << GROUND_STEP_UP_BIT, actor)
        assert launched[actor + ACTOR_FLAGS] == hopped[actor + ACTOR_FLAGS], (
            f"the two launches leave different flag bytes for {flags:#04x}")
        assert launched[actor + SPEED] == TURN_LAUNCH_SPEED != HOP_SPEED == hopped[actor + SPEED]


def test_the_first_record_is_walked_before_the_terminator_is_tested():
    """`lea 32(a0),a0 / cmpi.w #$ffff,(a0) / bne` closes both walks, so a record is always handled
    BEFORE the terminator is looked at — and a table whose very first word is the terminator still
    has that record's countdown byte stepped. Every other case here has records in front of the
    terminator and cannot tell a `do/while` from a `while`, which is what a surviving mutation said.
    """
    case = "an empty table"
    pokes = _spawn_pass_pokes(case_salt(f"actor_spawn_pass {case}"),
                              [{"armed": 0xff, "countdown": 3}], FULL_HEADER,
                              slots=1, terminate_slot=0)
    expected = _run_spawn_pass(case, pokes)
    assert set(expected) == {SPAWN_TABLE + SPAWN_COUNTDOWN}, (
        f"{case}: the pass wrote {[hex(a) for a in sorted(expected)]}, not the terminating "
        f"record's countdown byte alone")


# =================================================================================================
# $69fe AND $6b46 — the two damage paths (batch 17).
#
# TWO ROUTINES, ONE SHAPE: an SFX through the sound module's stub, a HUD slot spent one charge at a
# time, and a SECOND pool taken from when that slot is empty. $69fe pays for a hit ON the followed
# record (the helmet, else WB_HUD_METER_VALUE); $6b46 deals one (the gauntlet DOUBLES what comes off
# the attacker's template pool). Both were rejected in batches 10 and 13 for the `jsr 56(a5)` that
# batch 16b's port made C-calling-C, so the cases below run the ORIGINAL over the real sound module
# and compare its writes against test_sound.py's model — imported, never restated.
#
# WHAT THE CASES HOLD THAT NOTHING ELSE DOES
#   * THE MODE FLAG READ AS A BYTE. `tst.b $a32.w` looks at the word's HIGH byte alone, where all
#     twelve other readers in the image are `tst.w`. A flag of $0001 or $00ff therefore picks the
#     DEFAULT record here and the A32 one in `followed_actor_record` — opposite answers from the
#     same word, and the only thing that tells the two encodings apart.
#   * THE ARM THAT WRITES NOTHING. A record already carrying WB_ACTOR_FLAGS2_INVULNERABLE_BIT is
#     returned from before any store, so its case is a differential over an EMPTY write set plus the
#     registers the body never got as far as loading.
#   * CHANNEL B, FROM A REAL CALLER'S REGISTERS. $6b46's `move.w #$1,d1` is the one site in the
#     image that asks for a channel other than A, so these cases are what makes the trigger's B arm
#     live code rather than the dead arm batch 16b took it for.
#   * THE DAMAGE TABLE FROM BOTH SIDES. WB_ACTOR_DAMAGE_TABLE is DATA between the two bodies, so a
#     case can read the words the game ships AND poke one of its own; and the index that reaches it
#     is an unsigned doubled word taken as a LONGWORD, which a type from $4000 up sends off the end.
#
# KNOWINGLY NOT PINNED
#   * WHAT THE TWO SLOTS AND THE METER ARE FOR beyond the messages that name them. The strings the
#     posted ids resolve to are read out of the image below; what a charge or a meter unit DOES is
#     the tier above these two, and unported.
#   * THE REGISTERS, for the reconstruction. As everywhere in this file the C returns none of them;
#     the cases assert the ORACLE's against a model.

# The chain either body runs, plus the whole SOUND STUB one of them enters: `jsr 56(a5)` reaches
# $17b14, whose `movem` pair and `bsr` sit around $1a48a. STUB_INSN_CAP is test_sound.py's, so a
# change to the trigger's own geometry moves this cap with it.
DAMAGE_CHAIN_INSNS = 45
DAMAGE_INSN_CAP = DAMAGE_CHAIN_INSNS + STUB_INSN_CAP

_DAMAGE_FOLLOWED = leaf.register_glue("actor_damage_followed", [ctypes.c_uint32])
_DAMAGE_TEMPLATE = leaf.register_glue("actor_damage_template_hitpoints", [ctypes.c_uint32])

# Entry values for every register neither routine takes as an argument, each distinct: a register a
# body never touches has to come back, and one it writes only a WORD of has to keep its high half.
DAMAGE_ENTRY_REGS = {"d0": 0xfeed1234, "d1": 0xbeef5678, "a2": 0x40000, "a5": 0x40100,
                     "a6": 0x40200}

# Which records a case uses: the attacker is any slot but the followed one, and the two followed
# records are the routine's own choice rather than a case's.
DAMAGE_ATTACKER = TABLE_DEFAULT + 3 * RECORD_BYTES

# The state both paths read, all of it seeded — neither may be entered on a byte a case did not
# choose. `bbbe`/`bbc0` are whole SLOTS (value byte, request byte) so the rearm's second byte is a
# write a case can see land.
DAMAGE_STATE = dict(
    a32=0x0000, bd66=0x0000, meter=0x0028, bbbe=0x0000, bbc0=0x0000,
    request=0x00, lifetime=0x0000, record_list=0x0000, pool=0x0040,
    record_x=0x0140, record_flags=0x00, record_flags2=0x00,
    attacker_x=0x0100, template_slot=2, spawn_type=4, damage_entry=None,
)

# A slot's request byte, seeded away from what the rearm writes so the store is a change and not a
# coincidence, and a lifetime word likewise.
SLOT_REQUEST_SEED = 0x5a
LIFETIME_SEED = 0x1111


def _u32(image, addr):
    """The longword at ``addr`` — WB_TABLE_PTR_21E8C is the only one either path reads."""
    return int.from_bytes(bytes(image[addr:addr + LONGWORD_LEN]), "big")


def _damage_pokes(what, **overrides):
    state = dict(DAMAGE_STATE, **overrides)
    salt = case_salt(what)
    pokes = _state_pokes(salt, {FLAG_A32: state["a32"], EFFECT_STATE_BD66: state["bd66"],
                                METER_VALUE: state["meter"],
                                SLOT_BBBE: (state["bbbe"] << 8) | SLOT_REQUEST_SEED,
                                SLOT_BBC0: (state["bbc0"] << 8) | SLOT_REQUEST_SEED,
                                TEXT_LIFETIME_REQUEST: LIFETIME_SEED,
                                EFFECT_RECORD_LIST: state["record_list"] << 8})
    pokes[TEXT_REQUEST] = bytes([state["request"]])

    # EVERY template in the band carries the case's type and pool, not just the one the slot byte
    # names: the two paths index it differently ($6b46 with the whole byte, $69fe with the seven
    # bits below its sign), so seeding one record would leave a wrongly-indexed port reading keyed
    # noise instead of a number the case chose. The cases that need the records to DIFFER override
    # them afterwards, and a slot past this band seeds its own record.
    _template_band(salt, TEMPLATE_TABLE, TEMPLATE_SLOTS, pokes)
    pokes[TABLE_PTR] = longword(TEMPLATE_TABLE)
    for slot in range(TEMPLATE_SLOTS):
        record = TEMPLATE_TABLE + slot * SPAWN_RECORD_BYTES
        pokes[record + SPAWN_TYPE] = word(state["spawn_type"])
        pokes[record + SPAWN_HITPOINTS] = word(state["pool"])
    if state["damage_entry"] is not None:
        pokes[_damage_table_entry(state["spawn_type"])] = word(state["damage_entry"])

    pokes[DAMAGE_ATTACKER + ACTOR_X] = word(state["attacker_x"])
    pokes[DAMAGE_ATTACKER + TEMPLATE_SLOT] = bytes([state["template_slot"]])
    for record in (FOLLOWED_DEFAULT, FOLLOWED_A32):
        pokes[record + ACTOR_X] = word(state["record_x"])
        pokes[record + ACTOR_FLAGS] = bytes([state["record_flags"]])
        pokes[record + FLAGS2] = bytes([state["record_flags2"]])
    return pokes


def _damage_table_entry(spawn_type):
    """WHERE the second lookup goes: `add.w d0,d0` wraps the type in SIXTEEN BITS and
    `move.w 0(a2,d0.l)` then takes the whole longword, so the offset is unsigned and a type from
    $4000 up reads ABOVE the table rather than below it."""
    return DAMAGE_TABLE + ((2 * spawn_type) & WORD_MASK)


# --- the model both runners compare against -------------------------------------------------------

def _model_damage_word(image, attacker):
    """`moveq #0,d0 / move.b 19(a0),d0 / bmi` — the slot byte's SIGN BIT picks the arm, and on the
    table arm the byte indexes WB_TABLE_PTR_21E8C and that template's type indexes the word table."""
    slot = image[attacker + TEMPLATE_SLOT]
    if slot > DAMAGE_INLINE_MASK:
        return slot & DAMAGE_INLINE_MASK
    template = _u32(image, TABLE_PTR) + slot * SPAWN_RECORD_BYTES
    return u16(image, _damage_table_entry(u16(image, template + SPAWN_TYPE)))


def _model_slot_spend(image, out, slot, message_id):
    """One charge off a slot, extending ``out`` with what that wrote. Answers whether the slot HELD
    one, which is what each path hangs its other arm off."""
    if image[slot] == 0:
        return False
    left = (image[slot] - 1) & BYTE_MASK
    out[slot] = left
    if left == 0:
        _put_word(out, slot, SLOT_REARM)
        out[TEXT_REQUEST] = message_id
        _put_word(out, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    return True


def _model_damage_followed(image, attacker):
    """(the record it damages, {address: byte})."""
    record = FOLLOWED_A32 if image[FLAG_A32] else FOLLOWED_DEFAULT
    if image[record + FLAGS2] & (1 << FLAGS2_INVULNERABLE_BIT):
        return record, {}

    out = {record + FLAGS2: image[record + FLAGS2] | (1 << FLAGS2_BIT_0),
           record + FIELD_31: (DAMAGE_FIELD_31_BASE
                               - 2 * u16(image, EFFECT_STATE_BD66)) & BYTE_MASK,
           record + FIELD_22: 0}

    flags = image[record + ACTOR_FLAGS]
    if not flags & (1 << FLICKER_BIT):
        damage = _model_damage_word(image, attacker)
        if not _model_slot_spend(image, out, SLOT_BBBE, MSG_HELMET_BROKEN):
            left = (u16(image, METER_VALUE) - damage) & WORD_MASK
            _put_word(out, METER_VALUE, 0 if s16(left) < 0 else left)
            out[record + FLICKER_COUNTDOWN] = DAMAGE_FLICKER_FRAMES
    flags |= 1 << FLICKER_BIT

    if s16(u16(image, attacker + ACTOR_X)) > s16(u16(image, record + ACTOR_X)):
        flags &= ~(1 << SIDE_BIT)
        out[record + FIELD_30] = 0
    else:
        flags |= 1 << SIDE_BIT
        out[record + FIELD_30] = DAMAGE_FIELD_30_SET

    out[record + ACTOR_FLAGS] = (flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
                                 ) & ~(1 << SUPPORTED_BIT) & BYTE_MASK
    out[record + SPEED] = DAMAGE_KNOCKBACK_SPEED
    return record, out


def _model_damage_template(image, actor):
    """(the template record it spends, the damage it spent, {address: byte})."""
    template = _u32(image, TABLE_PTR) + image[actor + TEMPLATE_SLOT] * SPAWN_RECORD_BYTES
    out = {}
    damage = (image[EFFECT_RECORD_LIST] + 1) & BYTE_MASK        # `addq.b`, so $ff wraps to 0
    if _model_slot_spend(image, out, SLOT_BBC0, MSG_GAUNTLET_BROKEN):
        damage = (damage + damage) & WORD_MASK

    left = (u16(image, template + SPAWN_HITPOINTS) - damage) & WORD_MASK
    _put_word(out, template + SPAWN_HITPOINTS, left)
    if s16(left) <= 0:
        out[actor + FLAGS2] = image[actor + FLAGS2] | (1 << FLAGS2_DEFEATED_BIT)
    return template, damage, out


def _sfx_bytes(image, effect_id, channel):
    """test_sound.py's model of the trigger's writes, flattened to this battery's {address: byte} —
    so the EXACT write-set compare covers the sound module too, and a port that reached a field the
    trigger does not touch reddens here as well as in that battery."""
    return {addr + index: value[index]
            for addr, value in sfx_expected_writes(image, effect_id, channel).items()
            for index in range(len(value))}


# --- the two runners --------------------------------------------------------------------------------
# Both enter on DAMAGE_ATTACKER, which is the record `_damage_pokes` seeds and the only one either
# routine is ever handed here: a case that wants a different record moves the SEEDS under this one
# rather than passing another address, so neither runner takes the record as a parameter.

def _run_damage_followed(case, pokes):
    what = f"actor_damage_followed {case}"
    image = harness.make_image(pokes)
    record, expected = _model_damage_followed(image, DAMAGE_ATTACKER)
    sound = {}
    if expected:                       # the invulnerable arm never reaches the trigger either
        sound = sfx_expected_writes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A)
        expected.update(_sfx_bytes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A))

    info = leaf.run("actor_damage_followed", _DAMAGE_FOLLOWED(DAMAGE_ATTACKER),
                    merge_bands(expected), what,
                    regs={"a0": DAMAGE_ATTACKER, "_pokes": pokes, **DAMAGE_ENTRY_REGS},
                    max_insns=DAMAGE_INSN_CAP)
    _assert_writes(info, expected, what)
    if sound:
        assert_sfx_written(info, sound, f"{what}: the effect it triggers")
    assert info["regs"]["a0"] == DAMAGE_ATTACKER, f"{what}: a0 moved, which this routine does not"
    assert info["regs"]["a1"] == record, (
        f"{what}: the original left a1={info['regs']['a1']:#x}, not the {record:#x} the mode flag "
        f"picks")
    return info, record, expected


def _run_damage_template(case, pokes):
    what = f"actor_damage_template_hitpoints {case}"
    image = harness.make_image(pokes)
    template, damage, expected = _model_damage_template(image, DAMAGE_ATTACKER)
    sound = sfx_expected_writes(image, DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B)
    expected.update(_sfx_bytes(image, DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B))

    info = leaf.run("actor_damage_template_hitpoints", _DAMAGE_TEMPLATE(DAMAGE_ATTACKER),
                    merge_bands(expected), what,
                    regs={"a0": DAMAGE_ATTACKER, "_pokes": pokes, **DAMAGE_ENTRY_REGS},
                    max_insns=DAMAGE_INSN_CAP)
    _assert_writes(info, expected, what)
    assert_sfx_written(info, sound, f"{what}: the effect it triggers")
    assert info["regs"]["a0"] == DAMAGE_ATTACKER, f"{what}: a0 moved, which this routine does not"
    assert info["regs"]["a1"] == template, (
        f"{what}: the original left a1={info['regs']['a1']:#x}, not the template {template:#x}")
    assert info["regs"]["d0"] == damage, (
        f"{what}: the original left d0={info['regs']['d0']:#x}, not the {damage:#x} it spent — "
        f"`moveq #0,d0` clears the high half, so the whole register is the damage")
    return info, template, expected


# --- what the two paths' own data says ---------------------------------------------------------------

def test_the_damage_table_is_the_data_between_the_two_bodies():
    """Neither body has a Ghidra function, so both extents rest on the word table between them: it
    starts where $69fe's last `rts` does and ends where the twenty-five sites that enter $6b46 land.
    Its `lea` is also its ONLY reference in the image — a second reader would mean a second reading
    of where it stops."""
    followed = leaf.entry_of("actor_damage_followed")
    template = leaf.entry_of("actor_damage_template_hitpoints")
    assert followed + len(ENTRY_BYTES["actor_damage_followed"]) == DAMAGE_TABLE, (
        f"$69fe's body ends at {followed + len(ENTRY_BYTES['actor_damage_followed']):#x}, not at "
        f"the table {DAMAGE_TABLE:#x} its own `lea` names")
    assert DAMAGE_TABLE + DAMAGE_TABLE_ENTRIES * WORD_LEN == template, (
        f"{DAMAGE_TABLE_ENTRIES} words from {DAMAGE_TABLE:#x} end at "
        f"{DAMAGE_TABLE + DAMAGE_TABLE_ENTRIES * WORD_LEN:#x}, not at {template:#x}")

    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    # WHERE the pin puts that `lea`'s operand, so the scan is checked against the reconstruction
    # rather than against a transcribed address.
    naming = lea_abs_l(A2, DAMAGE_TABLE)
    operand = followed + ENTRY_BYTES["actor_damage_followed"].index(naming) + len(naming) \
        - LONGWORD_LEN
    inside = [at for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN)
              if DAMAGE_TABLE <= int.from_bytes(program[at:at + LONGWORD_LEN], "big") < template]
    assert inside == [operand], (
        f"the table is named as a longword at {[hex(a) for a in inside]}, which is not the one "
        f"`lea $6b08.l,a2` operand at {operand:#x} that this battery reconstructs")


def test_the_two_slots_are_named_by_the_messages_their_paths_post():
    """WHY the constants can say "helmet" and "gauntlet" at all: each path posts a message id as its
    slot empties, and the string that id resolves to is in the image. This resolves both through the
    message table's own arithmetic (1-based, a longword per entry), so a table that moved would fail
    here rather than leaving two names resting on a transcription."""
    image = harness.BASE_IMAGE
    for message_id, expected in ((MSG_HELMET_BROKEN, b"Helmet is Broken"),
                                 (MSG_GAUNTLET_BROKEN, b"Gauntlet is Broken")):
        entry = TEXT_MESSAGE_TABLE + (message_id - TEXT_MESSAGE_FIRST_ID) * LONGWORD_LEN
        record = _u32(image, entry)
        text = bytes(image[record + TEXT_RECORD_STRING:record + TEXT_RECORD_STRING + 0x40])
        assert expected in text.split(bytes([TEXT_STRING_END]))[0], (
            f"message {message_id:#04x} at {record:#x} is {text[:32]!r}, which does not name "
            f"{expected!r}")


def test_the_sound_module_is_clear_of_the_game_state_both_paths_write():
    """The composed expectation is one dict, so a case would silently lose a claim if the trigger's
    bands and the damage paths' overlapped. Checked against BOTH channels, since the two paths use
    different ones."""
    state = {SLOT_BBBE, SLOT_BBBE + SLOT_REQUEST, SLOT_BBC0, SLOT_BBC0 + SLOT_REQUEST,
             TEXT_REQUEST, METER_VALUE, METER_VALUE + 1,
             TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_REQUEST + 1}
    state |= set(range(FOLLOWED_DEFAULT, FOLLOWED_DEFAULT + RECORD_BYTES))
    state |= set(range(FOLLOWED_A32, FOLLOWED_A32 + RECORD_BYTES))
    state |= set(range(TEMPLATE_TABLE, TEMPLATE_TABLE + TEMPLATE_SLOTS * SPAWN_RECORD_BYTES))
    for effect_id, channel in ((DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A),
                               (DAMAGE_TEMPLATE_SFX, SND_CHANNEL_B)):
        assert not state & set(_sfx_bytes(harness.BASE_IMAGE, effect_id, channel)), (
            f"sfx {effect_id:#x} on channel {channel} writes bytes this battery also models")


def test_the_enemy_path_asks_for_a_channel_the_rest_of_the_image_never_does():
    """The correction batch 17 carries. `snd_trigger_effect`'s B and C arms were recorded as dead
    code on the strength of "every call site passes d1 = 0"; $6b46's second instruction is
    `move.w #$1,d1`, so the B arm is reached from the shipped game. Stated as arithmetic over the
    entry pin rather than as prose, so a rebuilt pin cannot quietly lose it."""
    assert SND_CHANNEL_B != SND_CHANNEL_A
    body = ENTRY_BYTES["actor_damage_template_hitpoints"]
    assert body.startswith(move_w_imm_dn(D0, DAMAGE_TEMPLATE_SFX)
                           + move_w_imm_dn(D1, SND_CHANNEL_B)), (
        "the enemy path no longer opens by loading the channel-B selector")


# --- $69fe: the mode flag, read one size down -------------------------------------------------------
# `tst.b $a32.w` sees the word's HIGH byte alone. $0001 and $00ff are the two values a `tst.w` port
# — which is what every other reader of this word is — answers the other way round on.
BYTE_FLAG_CASES = [
    ("clear", 0x0000, FOLLOWED_DEFAULT),
    ("all-ones", 0xffff, FOLLOWED_A32),
    ("low-byte-one", 0x0001, FOLLOWED_DEFAULT),
    ("low-byte-only", 0x00ff, FOLLOWED_DEFAULT),
    ("high-byte-one", 0x0100, FOLLOWED_A32),
    ("largest-positive", 0x7fff, FOLLOWED_A32),
    ("sign-boundary", 0x8000, FOLLOWED_A32),
]


@pytest.mark.parametrize("case,flag,expected", BYTE_FLAG_CASES, ids=[c[0] for c in BYTE_FLAG_CASES])
def test_the_damage_path_reads_the_mode_flag_as_a_byte(case, flag, expected):
    what = f"a32={flag:#06x}"
    _info, record, _writes = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", a32=flag))
    assert record == expected, f"{what}: the flag picked {record:#x}, not {expected:#x}"


def test_the_byte_flag_cases_disagree_with_the_word_reading_the_rest_of_the_image_uses():
    """The guard on the sweep above: without a value whose two readings differ, every case there
    would pass against a `tst.w` port too."""
    differing = [flag for _case, flag, expected in BYTE_FLAG_CASES
                 if (FOLLOWED_A32 if flag else FOLLOWED_DEFAULT) != expected]
    assert differing, "no seed tells `tst.b` from `tst.w`, so the sweep pins only the addresses"


# --- $69fe: the arm that writes nothing --------------------------------------------------------------
# WB_ACTOR_FLAGS2_INVULNERABLE_BIT alone, and beside every neighbour: a byte-wide `btst` must read
# that bit and no other.
INVULNERABLE_SEEDS = (1 << FLAGS2_INVULNERABLE_BIT, 0xff, 0xff ^ (1 << FLAGS2_BIT_0),
                      (1 << FLAGS2_INVULNERABLE_BIT) | (1 << FLAGS2_DEFEATED_BIT))
VULNERABLE_SEEDS = (0x00, 0xff ^ (1 << FLAGS2_INVULNERABLE_BIT), 1 << FLAGS2_BIT_0,
                    1 << FLAGS2_DEFEATED_BIT)


@pytest.mark.parametrize("flags2", INVULNERABLE_SEEDS, ids=lambda v: f"flags2{v:#04x}")
def test_a_record_already_invulnerable_is_left_completely_alone(flags2):
    """The one path out that writes NOTHING — no slot, no meter, no SFX, not even the flicker. The
    registers say as much as the empty write set does: the body returns before it has loaded any of
    them, so every one but a1 has to come back exactly as it was entered."""
    what = f"invulnerable flags2={flags2:#04x}"
    info, _record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", record_flags2=flags2, bbbe=3, meter=0x28))
    assert not expected, f"{what}: the model expected writes on a path that makes none"
    for name, entered in DAMAGE_ENTRY_REGS.items():
        assert info["regs"][name] == entered, (
            f"{what}: {name} came back {info['regs'][name]:#010x}, not the {entered:#010x} it was "
            f"entered with — the body got further than the `btst`")


@pytest.mark.parametrize("flags2", VULNERABLE_SEEDS, ids=lambda v: f"flags2{v:#04x}")
def test_a_record_without_that_bit_takes_the_hit_and_keeps_its_other_flags2_bits(flags2):
    """The other side, and what says the `bset #0,9(a1)` is a bit and not a byte store."""
    what = f"vulnerable flags2={flags2:#04x}"
    _info, record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", record_flags2=flags2))
    assert expected[record + FLAGS2] == flags2 | (1 << FLAGS2_BIT_0), (
        f"{what}: the second flag byte came back {expected[record + FLAGS2]:#04x}")


# --- $69fe: the four arms that funnel into the tail ---------------------------------------------------
# (flicker seed, slot seed, which arm, why). Each is a different branch INTO the funnel at $6aba,
# and the model's write set is what tells them apart: only the meter arm touches WB_HUD_METER_VALUE,
# only the two slot arms touch the slot, and only the emptying one posts a message.
FUNNEL_ARMS = [
    ("flicker-already-up", 1 << FLICKER_BIT, 3, "the `bne` at $6a44: the cost is skipped outright"),
    ("slot-decremented", 0x00, 3, "the `bne` at $6a7a: a charge off the slot and nothing else"),
    ("slot-emptied", 0x00, 1, "the `bra` at $6a96: the rearm and the message"),
    ("meter-spent", 0x00, 0, "the `bra` at $6ab0: the slot was empty, so the meter pays"),
]


@pytest.mark.parametrize("case,flicker,slot,why", FUNNEL_ARMS, ids=[c[0] for c in FUNNEL_ARMS])
def test_each_arm_of_the_funnel_pays_for_the_hit_its_own_way(case, flicker, slot, why):
    what = f"{case} ({why})"
    _info, record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", record_flags=flicker, bbbe=slot, damage_entry=4))

    paid_meter = METER_VALUE in expected
    paid_slot = SLOT_BBBE in expected
    posted = TEXT_REQUEST in expected
    assert (paid_meter, paid_slot, posted) == (case == "meter-spent",
                                               case.startswith("slot"),
                                               case == "slot-emptied"), (
        f"{what}: meter={paid_meter} slot={paid_slot} message={posted}")
    # Every arm reaches the funnel, so the knock-back and the SFX land whatever paid.
    assert expected[record + SPEED] == DAMAGE_KNOCKBACK_SPEED, f"{what}: no knock-back"
    # The flicker countdown is the meter arm's alone — nothing else in the body writes it.
    assert (record + FLICKER_COUNTDOWN in expected) == paid_meter, (
        f"{what}: the flicker countdown moved on an arm that does not write it")


@pytest.mark.parametrize("slot", [1, 2, 3, 0x80, 0xff], ids=lambda v: f"slot{v:#04x}")
def test_a_slot_with_a_charge_loses_exactly_one_and_rearms_only_at_zero(slot):
    """The slot boundary from both sides. `subq.b #1` on a 1 reaches zero and the whole rearm runs;
    on anything else only the count byte moves, and the request byte beside it must not."""
    what = f"slot at {slot:#04x}"
    _info, _record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", bbbe=slot, damage_entry=4))
    assert expected[SLOT_BBBE] == (slot - 1) & BYTE_MASK
    if slot == 1:
        assert expected[SLOT_BBBE + SLOT_REQUEST] == SLOT_REARM & BYTE_MASK
        assert expected[TEXT_REQUEST] == MSG_HELMET_BROKEN
        assert leaf.read_int(_info, TEXT_LIFETIME_REQUEST, WORD_LEN, what) == TEXT_LIFETIME_DEFAULT
    else:
        assert SLOT_BBBE + SLOT_REQUEST not in expected, (
            f"{what}: the request byte moved on a slot that did not empty")
        assert TEXT_REQUEST not in expected, f"{what}: a message was posted early"


# --- $69fe: the meter, and its floor ------------------------------------------------------------------
# (meter, damage, why). `sub.w d0,$b6fa / bpl / clr.w` reads the RESULT, so a meter already negative
# that the subtraction carries back into the positive half is STORED rather than floored.
METER_CASES = [
    (0x0028, 0x0004, "an ordinary hit"),
    (0x0004, 0x0004, "exactly to zero, which both readings of the floor store as zero"),
    (0x0003, 0x0004, "one past zero: the `bpl` fails and the `clr.w` fires"),
    (0x0000, 0x0000, "nothing off nothing"),
    (0x0000, 0x0001, "straight into the negative half"),
    (0x8000, 0x0001, "a meter already NEGATIVE, carried back positive and kept"),
    (0x8000, 0x8000, "...and one carried exactly to zero"),
    (0xffff, 0xffff, "two negatives that cancel"),
    (0x0001, 0xffff, "a damage word the `sub.w` reads as -1, so the meter goes UP"),
    (0x7fff, 0x0001, "the largest positive meter"),
]


@pytest.mark.parametrize("meter,damage,why", METER_CASES,
                         ids=[f"meter{c[0]:04x}_dmg{c[1]:04x}" for c in METER_CASES])
def test_the_meter_arm_floors_only_a_result_that_went_negative(meter, damage, why):
    what = f"meter {meter:#06x} less {damage:#06x} ({why})"
    _info, _record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", meter=meter, bbbe=0, damage_entry=damage))
    left = (meter - damage) & WORD_MASK
    stored = (expected[METER_VALUE] << 8) | expected[METER_VALUE + 1]
    assert stored == (0 if s16(left) < 0 else left), (
        f"{what}: the meter came back {stored:#06x}")


def test_the_meter_sweep_reaches_both_sides_of_the_floor_and_the_case_it_cannot_see():
    """A sweep that only ever went negative would pass a port with no floor at all, and one that
    never started negative would pass a port whose floor tested the OPERAND instead of the result."""
    results = [s16((meter - damage) & WORD_MASK) for meter, damage, _why in METER_CASES]
    assert any(r < 0 for r in results) and any(r > 0 for r in results) and 0 in results
    assert any(s16(meter) < 0 <= s16((meter - damage) & WORD_MASK)
               for meter, damage, _why in METER_CASES), (
        "no case starts negative and ends positive, so the floor's position is unpinned")


# --- $69fe: where the damage word comes from -----------------------------------------------------------

# One type per DISTINCT word the shipped table holds, chosen off the image rather than listed: the
# 31 entries carry six numbers between them, so sweeping all of them was 31 differentials over six
# values. The table's LENGTH is not what this sweep holds — that is
# test_the_damage_table_is_the_data_between_the_two_bodies, whose arithmetic ends exactly on $6b46.
_FIRST_TYPE_PER_WORD = {}
for _spawn_type in range(DAMAGE_TABLE_ENTRIES):
    _FIRST_TYPE_PER_WORD.setdefault(u16(harness.BASE_IMAGE, _damage_table_entry(_spawn_type)),
                                    _spawn_type)
SHIPPED_DAMAGE_TYPES = tuple(sorted(_FIRST_TYPE_PER_WORD.values()))


@pytest.mark.parametrize("spawn_type", SHIPPED_DAMAGE_TYPES, ids=lambda v: f"type{v:#04x}")
def test_every_word_the_shipped_damage_table_holds_is_taken_off_the_meter(spawn_type):
    """The table is program data, so these run the game's OWN numbers — one type for each distinct
    word in it, which is every value the meter arm can be driven with without poking anything."""
    what = f"shipped damage word for type {spawn_type:#x}"
    _run_damage_followed(what, _damage_pokes(f"actor_damage_followed {what}",
                                             spawn_type=spawn_type, bbbe=0, meter=0x7f00))


# Types whose doubled index leaves the table. The offset is UNSIGNED and taken as a longword, so
# these read above the table rather than below it, and $8000 is where the `add.w` wraps to zero.
OUT_OF_RANGE_TYPES = (
    (DAMAGE_TABLE_ENTRIES, "the first type past the table — its word is $6b46's own first"),
    (0x0100, "well past it"),
    (0x3fff, "the largest index that still fits a signed word once doubled"),
    (0x4000, "...and the first that does not, which a SIGNED index would send 32 KB below"),
    (0x8000, "the `add.w` wraps to zero, so this reads entry 0"),
    (0xffff, "the last index the wrap allows, two bytes below the table's end + 64 KB"),
)


@pytest.mark.parametrize("spawn_type,why", OUT_OF_RANGE_TYPES,
                         ids=[f"type{c[0]:04x}" for c in OUT_OF_RANGE_TYPES])
def test_a_type_outside_the_damage_table_indexes_it_anyway(spawn_type, why):
    what = f"type {spawn_type:#06x} ({why})"
    _run_damage_followed(what, _damage_pokes(f"actor_damage_followed {what}",
                                             spawn_type=spawn_type, bbbe=0, meter=0x7f00))


def test_the_out_of_range_types_really_do_leave_the_table_and_one_wraps_to_its_start():
    """The guard: a sweep whose entries all landed back inside the table would pin nothing about the
    index, and one with no wrap would agree with a port that took the index as a longword."""
    entries = [_damage_table_entry(spawn_type) for spawn_type, _why in OUT_OF_RANGE_TYPES]
    end = DAMAGE_TABLE + DAMAGE_TABLE_ENTRIES * WORD_LEN
    assert any(entry >= end for entry in entries), entries
    assert DAMAGE_TABLE in entries, "no case exercises the `add.w`'s wrap back to entry 0"
    assert all(entry < loader.PROGRAM_END for entry in entries), (
        "an out-of-range type reads past the program, where the model would be reading a byte the "
        "oracle does not have")


@pytest.mark.parametrize("damage", [0x0000, 0x0001, 0x0007, 0x00ff, 0x7fff, 0x8000, 0xffff],
                         ids=lambda v: f"seeded{v:04x}")
def test_a_seeded_damage_word_is_reached_through_the_template_the_slot_byte_names(damage):
    """The shipped table's own words are small, so only a poked entry drives the subtraction with a
    value that wraps — and poking it is also what says the routine reaches the table THROUGH
    WB_TABLE_PTR_21E8C and the template's type, rather than off the slot byte directly."""
    what = f"a seeded damage word of {damage:#06x}"
    _run_damage_followed(what, _damage_pokes(f"actor_damage_followed {what}",
                                             bbbe=0, meter=0x4000, damage_entry=damage))


# The type every template but the one under test carries, and the damage word it selects — both
# different from the case's own, so a port that indexed the wrong record answers with the wrong
# number instead of with the same one.
NEIGHBOUR_TYPE, NEIGHBOUR_DAMAGE = 7, 0x0022
SLOT_UNDER_TEST_TYPE, SLOT_UNDER_TEST_DAMAGE = 6, 0x0011


@pytest.mark.parametrize("template_slot", [0, 1, 2, TEMPLATE_SLOTS - 1, DAMAGE_INLINE_MASK],
                         ids=lambda v: f"slot{v:#04x}")
def test_the_table_arm_indexes_the_template_the_slot_byte_names(template_slot):
    """`lsl.l #5,d0 / move.w 12(a6,d0.w),d0` — a whole template's stride per slot, and the type it
    lands on is what selects the damage word. WB_ACTOR_DAMAGE_INLINE_MASK is the largest slot this
    arm can see, and it is past the default band, so the band is widened to reach it."""
    what = f"template slot {template_slot:#04x}"
    salt = case_salt(f"actor_damage_followed {what}")
    pokes = _damage_pokes(f"actor_damage_followed {what}", template_slot=template_slot, bbbe=0,
                          spawn_type=NEIGHBOUR_TYPE, damage_entry=NEIGHBOUR_DAMAGE)
    _template_band(salt, TEMPLATE_TABLE, template_slot + 1, pokes)
    for slot in range(template_slot + 1):
        pokes[TEMPLATE_TABLE + slot * SPAWN_RECORD_BYTES + SPAWN_TYPE] = word(NEIGHBOUR_TYPE)
    pokes[TEMPLATE_TABLE + template_slot * SPAWN_RECORD_BYTES + SPAWN_TYPE] = word(
        SLOT_UNDER_TEST_TYPE)
    pokes[_damage_table_entry(SLOT_UNDER_TEST_TYPE)] = word(SLOT_UNDER_TEST_DAMAGE)
    _run_damage_followed(what, pokes)


@pytest.mark.parametrize("template_slot", [0x80, 0x81, 0xc4, 0xff], ids=lambda v: f"slot{v:#04x}")
def test_a_slot_byte_with_its_sign_bit_set_carries_the_damage_itself(template_slot):
    """`bmi` then `bclr #7,d0`: no table is read at all, and the seven bits left ARE the damage. The
    case seeds the template table with a type whose word is large, so a port that took the table arm
    anyway comes out with a different number rather than the same small one."""
    what = f"inline damage from slot {template_slot:#04x}"
    pokes = _damage_pokes(f"actor_damage_followed {what}", template_slot=template_slot, bbbe=0,
                          meter=0x4000, spawn_type=9, damage_entry=0x4321)
    _run_damage_followed(what, pokes)


# --- $69fe: the x compare, and what it writes ------------------------------------------------------
# (record x, attacker x): both arms, the EQUAL case — inclusive here where actor_set_side_flag's
# `ble` on the same comparison is strict — and the pairs that make it a SIGNED compare.
DAMAGE_SIDE_CASES = [
    ("attacker-right", 0x0100, 0x0140),
    ("attacker-left", 0x0140, 0x0100),
    ("level", 0x0120, 0x0120),
    ("one-apart", 0x0120, 0x0121),
    ("one-apart-other-way", 0x0121, 0x0120),
    ("attacker-negative", 0x0010, 0xffff),
    ("record-negative", 0xffff, 0x0010),
    ("sign-boundary", 0x7fff, 0x8000),
    ("sign-boundary-other-way", 0x8000, 0x7fff),
]


@pytest.mark.parametrize("flags", STATE_FLAG_SEEDS, ids=lambda v: f"flags{v:#04x}")
@pytest.mark.parametrize("case,record_x,attacker_x", DAMAGE_SIDE_CASES,
                         ids=[c[0] for c in DAMAGE_SIDE_CASES])
def test_the_hit_turns_the_record_towards_whatever_struck_it(case, record_x, attacker_x, flags):
    what = f"{case} record={record_x:#06x} attacker={attacker_x:#06x} flags={flags:#04x}"
    _info, record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", record_x=record_x, attacker_x=attacker_x,
        record_flags=flags, bbbe=0))

    raised = not s16(attacker_x) > s16(record_x)
    assert bool(expected[record + ACTOR_FLAGS] & (1 << SIDE_BIT)) == raised, what
    assert expected[record + FIELD_30] == (DAMAGE_FIELD_30_SET if raised else 0), what


def test_the_side_compare_is_inclusive_where_the_other_reading_of_it_is_strict():
    """$67c2's `ble` and $69fe's `bgt` are the same comparison read two ways, and they differ on
    EXACTLY the equal case — which is why src/actor.c spells this one out instead of calling
    `actor_set_side_flag` on the record."""
    level = [case for case, record_x, attacker_x in DAMAGE_SIDE_CASES if record_x == attacker_x]
    assert level, "no case has the two level, so the two readings are indistinguishable here"


# --- $69fe: the countdown field, and the registers each arm leaves ---------------------------------

@pytest.mark.parametrize("bd66", [0x0000, 0x0001, 0x0005, 0x0006, 0x0007, 0x8000, 0xffff],
                         ids=lambda v: f"bd66{v:04x}")
def test_the_field_31_seed_is_twelve_less_twice_the_state_word(bd66):
    """`move.w #$c,d1 / sub.w d0,d1 / move.b d1,31(a1)` — a WORD subtraction of which only the LOW
    BYTE is stored, so a state word past 6 stores a byte that has gone round."""
    what = f"bd66={bd66:#06x}"
    _info, record, expected = _run_damage_followed(what, _damage_pokes(
        f"actor_damage_followed {what}", bd66=bd66))
    assert expected[record + FIELD_31] == (DAMAGE_FIELD_31_BASE - 2 * bd66) & BYTE_MASK, what


@pytest.mark.parametrize("case,flicker", [("table-arm", 0x00),
                                          ("flicker-arm", 1 << FLICKER_BIT)],
                         ids=["table-arm", "flicker-arm"])
def test_the_two_arms_leave_different_registers_behind(case, flicker):
    """What separates the arms in the REGISTERS rather than in memory. The table arm clears d0's
    high half with a `moveq` and loads a2 and a6; the arm that skips the cost never touches any of
    the three, so the caller's own values survive — including d0's high half, which the `move.w
    #$b,d0` before the SFX call cannot reach."""
    what = f"registers on the {case}"
    pokes = _damage_pokes(f"actor_damage_followed {what}", record_flags=flicker, bbbe=0)
    info, _record, _writes = _run_damage_followed(what, pokes)

    took_table = not flicker
    # `moveq #0,d0` on the table arm clears the WHOLE register, so the SFX id is all that is left in
    # it; on the other arm only the `move.w` lands and the caller's high half survives.
    expected_d0 = (DAMAGE_FOLLOWED_SFX if took_table
                   else leaf.set_low_word(DAMAGE_ENTRY_REGS["d0"], DAMAGE_FOLLOWED_SFX))
    assert info["regs"]["a5"] == SND_STUB_TABLE, f"{what}: a5 is not the stub table"
    assert info["regs"]["d0"] == expected_d0, (
        f"{what}: d0 came back {info['regs']['d0']:#010x}, not {expected_d0:#010x}")
    assert info["regs"]["d1"] == leaf.set_low_word(DAMAGE_ENTRY_REGS["d1"], 0), (
        f"{what}: `clr.w d1` reached the high half")
    assert info["regs"]["a2"] == (DAMAGE_TABLE if took_table else DAMAGE_ENTRY_REGS["a2"]), what
    assert info["regs"]["a6"] == (TEMPLATE_TABLE if took_table else DAMAGE_ENTRY_REGS["a6"]), what


# --- $6b46: the gauntlet, the pool and the kill bit ---------------------------------------------------
# (slot, whether the damage doubles, why). The `beq` at the top of the slot test is the ONLY thing
# that skips the `add.w`, so both arms that spend a charge double and only an empty slot does not.
GAUNTLET_ARMS = [
    ("empty", 0, False, "the `beq` at $6b7a jumps PAST the doubling"),
    ("decremented", 3, True, "the `bne` at $6b84 lands ON it"),
    ("emptied", 1, True, "...and so does the fall-through from the rearm"),
]

# The list byte these three run at, and a pool deep enough that none of them empties it.
GAUNTLET_RECORD_LIST = 4
GAUNTLET_POOL = 0x0100


@pytest.mark.parametrize("case,slot,doubles,why", GAUNTLET_ARMS, ids=[c[0] for c in GAUNTLET_ARMS])
def test_a_gauntlet_charge_doubles_the_damage_on_both_arms_that_spend_one(case, slot, doubles, why):
    what = f"gauntlet {case} ({why})"
    info, _template, expected = _run_damage_template(what, _damage_pokes(
        f"actor_damage_template_hitpoints {what}", bbc0=slot, record_list=GAUNTLET_RECORD_LIST,
        pool=GAUNTLET_POOL))
    # `addq.b #1,d0` over the OVERRIDE alone — the same arithmetic the sweep below states, and not
    # DAMAGE_STATE's default plus it, which happens to agree only because that default is zero.
    base = (GAUNTLET_RECORD_LIST + 1) & BYTE_MASK
    spent = base * 2 if doubles else base
    assert info["regs"]["d0"] == spent, (
        f"{what}: the damage came out {info['regs']['d0']:#x}, not the {spent:#x} this arm gives")
    assert (TEXT_REQUEST in expected) == (case == "emptied"), what


@pytest.mark.parametrize("record_list", [0x00, 0x01, 0x7f, 0x80, 0xfe, 0xff],
                         ids=lambda v: f"list{v:#04x}")
@pytest.mark.parametrize("slot", [0, 2], ids=["gauntlet-empty", "gauntlet-charged"])
def test_the_damage_is_the_list_byte_plus_one_added_in_a_byte(record_list, slot):
    """`addq.b #1,d0` — a BYTE add over a `moveq`-cleared register, so a list byte of $ff comes back
    0 and the whole hit does nothing to the pool, doubled or not."""
    what = f"list byte {record_list:#04x} with slot {slot}"
    info, _template, _writes = _run_damage_template(what, _damage_pokes(
        f"actor_damage_template_hitpoints {what}", record_list=record_list, bbc0=slot,
        pool=0x0400))
    expected = (record_list + 1) & BYTE_MASK
    assert info["regs"]["d0"] == (expected * 2 if slot else expected), (
        f"{what}: d0 came back {info['regs']['d0']:#x}")


# (pool, list byte, whether the kill bit goes up, why). `beq` then `bmi`, both on the WORD result.
POOL_CASES = [
    (0x0040, 0x04, False, "an ordinary hit"),
    (0x0005, 0x04, True, "exactly to zero, which the `beq` catches"),
    (0x0006, 0x04, False, "one above it"),
    (0x0004, 0x04, True, "one past it, which the `bmi` catches"),
    (0x0000, 0xff, True, "a damage of zero on a pool of zero: the `beq` again"),
    (0x0001, 0xff, False, "a damage of zero on a pool of one"),
    (0x8000, 0x00, False, "a NEGATIVE pool carried back into the positive half and left alive"),
    (0x8000, 0xff, True, "...and the same pool with a damage of zero, still negative"),
    (0xffff, 0x00, True, "a pool already at -1"),
]


# The flags2 seeds: the bit alone, every neighbour but it, all of them and none, which is what says
# `bset #3,9(a0)` is a BIT and not a byte store. They are a SEPARATE case from the pool sweep rather
# than a second axis over it — the arithmetic that decides whether the store happens and the shape
# of the store itself are independent, so the product of the two was 36 runs of the same routine
# where 17 hold the same claims.
DEFEATED_FLAGS2_SEEDS = (0x00, 0xff, 1 << FLAGS2_DEFEATED_BIT, 0xff ^ (1 << FLAGS2_DEFEATED_BIT))
POOL_SWEEP_FLAGS2 = 0x00

# One case either side of the store, taken from the sweep's own table so the two cannot drift apart.
KILLING_POOL_CASE = next(case for case in POOL_CASES if case[2])
SURVIVING_POOL_CASE = next(case for case in POOL_CASES if not case[2])


def _run_pool_case(pool, record_list, killed, flags2, what):
    """One hit on a seeded pool, checked for whether the defeated bit went up and for what the whole
    flag byte came back as."""
    pokes = _damage_pokes(f"actor_damage_template_hitpoints {what}", pool=pool, bbc0=0,
                          record_list=record_list)
    pokes[DAMAGE_ATTACKER + FLAGS2] = bytes([flags2])
    _info, _template, expected = _run_damage_template(what, pokes)

    assert (DAMAGE_ATTACKER + FLAGS2 in expected) == killed, (
        f"{what}: the defeated bit {'did not go' if killed else 'went'} up")
    if killed:
        assert expected[DAMAGE_ATTACKER + FLAGS2] == flags2 | (1 << FLAGS2_DEFEATED_BIT), what


@pytest.mark.parametrize("pool,record_list,killed,why", POOL_CASES,
                         ids=[f"pool{c[0]:04x}_list{c[1]:02x}" for c in POOL_CASES])
def test_a_pool_that_reaches_zero_or_goes_negative_raises_the_defeated_bit(pool, record_list,
                                                                          killed, why):
    """The signed test on the pool: `beq` then `bmi`, both on the word the subtraction left."""
    _run_pool_case(pool, record_list, killed, POOL_SWEEP_FLAGS2,
                   f"pool {pool:#06x} list {record_list:#04x} ({why})")


@pytest.mark.parametrize("flags2", DEFEATED_FLAGS2_SEEDS, ids=lambda v: f"flags2{v:#04x}")
@pytest.mark.parametrize("pool,record_list,killed,why", (KILLING_POOL_CASE, SURVIVING_POOL_CASE),
                         ids=["killing", "surviving"])
def test_the_defeated_bit_is_a_bit_and_leaves_its_neighbours_alone(pool, record_list, killed, why,
                                                                   flags2):
    """The flag seeds run beside every neighbour, so a byte store would show — and on BOTH sides of
    the test, since a port that stored the byte unconditionally would only fail on the arm that is
    supposed to write nothing."""
    _run_pool_case(pool, record_list, killed, flags2,
                   f"flags2 {flags2:#04x} on a pool of {pool:#06x} ({why})")


@pytest.mark.parametrize("template_slot", [0, 1, 2, DAMAGE_INLINE_MASK, 0x80, 0xff],
                         ids=lambda v: f"slot{v:#04x}")
def test_the_pool_is_the_one_in_the_template_the_slot_byte_names(template_slot):
    """No sign discriminator here: `lea 0(a1,d0.w),a1` takes the whole BYTE, so a slot of $ff names
    template 255 and not a negative one. The table is seeded that far up so the record exists."""
    what = f"pool of template {template_slot:#04x}"
    salt = case_salt(f"actor_damage_template_hitpoints {what}")
    pokes = _damage_pokes(f"actor_damage_template_hitpoints {what}", template_slot=template_slot,
                          bbc0=0)
    _template_band(salt, TEMPLATE_TABLE, template_slot + 1, pokes)
    pokes[TEMPLATE_TABLE + template_slot * SPAWN_RECORD_BYTES + SPAWN_HITPOINTS] = word(0x0080)
    _run_damage_template(what, pokes)


def test_the_enemy_path_leaves_the_stub_table_and_the_channel_it_asked_for():
    """The registers, and the half of the channel-B claim memory cannot show on its own: d1's low
    word is the selector the trigger read and its HIGH half is still the caller's."""
    what = "registers"
    info, template, _writes = _run_damage_template(what, _damage_pokes(
        f"actor_damage_template_hitpoints {what}", bbc0=2))
    assert info["regs"]["a5"] == SND_STUB_TABLE, f"{what}: a5 is not the stub table"
    assert info["regs"]["a1"] == template
    assert info["regs"]["d1"] == leaf.set_low_word(DAMAGE_ENTRY_REGS["d1"], SND_CHANNEL_B), (
        f"{what}: d1 came back {info['regs']['d1']:#010x}, not the caller's high half over "
        f"channel {SND_CHANNEL_B}")


@pytest.mark.parametrize("table_base", [TEMPLATE_TABLE, TEMPLATE_TABLE + 0x2000],
                         ids=["table-a", "table-b"])
def test_both_paths_follow_whichever_template_table_the_pointer_names(table_base):
    """WB_TABLE_PTR_21E8C is what `select_table_21e8c_and_tick_b39a` publishes off
    WB_STATE_FLAG_A32, so both paths read a table chosen once a frame rather than a fixed one. A
    port that hardcoded either address passes half of these."""
    what = f"table at {table_base:#x}"
    for name, runner, extra in (("actor_damage_followed", _run_damage_followed, dict(bbbe=0)),
                                ("actor_damage_template_hitpoints", _run_damage_template,
                                 dict(bbc0=0))):
        case = f"{what} for {name}"
        salt = case_salt(f"{name} {case}")
        pokes = _damage_pokes(f"{name} {case}", spawn_type=5, damage_entry=0x0013, **extra)
        _template_band(salt, table_base, TEMPLATE_SLOTS, pokes)
        pokes[TABLE_PTR] = longword(table_base)
        template = table_base + DAMAGE_STATE["template_slot"] * SPAWN_RECORD_BYTES
        pokes[template + SPAWN_TYPE] = word(5)
        pokes[template + SPAWN_HITPOINTS] = word(DAMAGE_STATE["pool"])
        runner(case, pokes)


# --- $6ade: the knock-back, as a routine of its own -------------------------------------------------
# THE LAST FORTY-TWO BYTES OF $69fe, and a SHARED TAIL rather than only that body's ending. Three
# entrances reach them: $6ad0's `bra.w` and the fall-through at $6adc, both inside $69fe, and
# `bra.w $6ade` at $15e8 inside `player_run_map_cell` — off the tiles that hurt. The third is the
# whole reason src/actor.c exports them instead of spelling them twice.
#
# WHAT THESE CASES ADD over the $69fe ones above, which already run these bytes on every arm that
# does any work:
#   * THE RECORD IS a1 AND NOTHING ELSE. Two of the three entrances hand it the FOLLOWED record, so
#     a port that read WB_ACTOR_FOLLOWED_DEFAULT instead of its argument still passes every case in
#     the damage battery bar the four `test_the_damage_path_reads_the_mode_flag_as_a_byte` rows the
#     A32 flag picks the other record on — a MEASURED figure, from the mutant. The cases below enter
#     on ORDINARY slots as well, with a0 pointing at a different record.
#   * THE BYTE WRITE IS A WRITE EVEN WHEN THE VALUE DOES NOT MOVE. One seed already carries the two
#     bits raised and the third clear, which is what the attribution pass turns into a real claim.
#   * THE OTHER FIVE BITS OF WB_ACTOR_FLAGS. `bset`/`bclr` are bit ops on a byte the rest of the
#     tier also writes, so a seed with every neighbouring bit set comes back with them all intact.
#
# KNOWINGLY NOT PINNED
#   * WHICH ENTRANCE RAN. All three arrive with a1 already loaded and nothing in the write set says
#     where control came from; the census below is what bounds them, and it is a statement about the
#     image rather than about a run.

# The nine instructions the entry pin holds — the trigger's four, the two `bset`s, the `bclr`, the
# speed store and the `rts` — plus the whole sound stub the `jsr 56(a5)` enters. STUB_INSN_CAP is
# test_sound.py's and carries no sentinel of its own (see the defeat block below), so one is added
# here for the `rts` this run ends on.
KNOCK_BACK_BODY_INSNS = 9
KNOCK_BACK_INSN_CAP = KNOCK_BACK_BODY_INSNS + STUB_INSN_CAP + leaf.RUNNER_SENTINEL_INSN

_KNOCK_BACK = leaf.register_glue("actor_knock_back_and_launch", [ctypes.c_uint32])

# An ordinary slot, clear of the followed records and of the ones the batteries above use, plus the
# DECOY the same seeds put under a0: the routine reads neither, so a port that took the record from
# the wrong register writes into a record no case expects rather than into the one it was handed.
KNOCK_BACK_RECORD = TABLE_DEFAULT + 6 * RECORD_BYTES
KNOCK_BACK_DECOY = TABLE_DEFAULT + 7 * RECORD_BYTES

KNOCK_BACK_MOTION_BITS = (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
KNOCK_BACK_TOUCHED_BITS = KNOCK_BACK_MOTION_BITS | (1 << SUPPORTED_BIT)
# The exact opposite of the state the routine wants, which is what the cases that do not sweep the
# flags seed: every bit it names has to move.
KNOCK_BACK_INVERTED = 1 << SUPPORTED_BIT
# ...and the sweep, where each seed says something the others cannot: `settled` is the state the
# routine wants ALREADY, so its byte write moves no value at all; `neighbours` and `all-set` are
# what says the five bits nothing here names come back untouched.
KNOCK_BACK_FLAG_SEEDS = (
    ("settled", KNOCK_BACK_MOTION_BITS),
    ("inverted", KNOCK_BACK_INVERTED),
    ("neighbours", 0xff ^ KNOCK_BACK_TOUCHED_BITS),
    ("all-set", 0xff),
)
# The speed seeds. WB_ACTOR_DAMAGE_KNOCKBACK_SPEED is the value the routine stamps, so its store
# moves no value either; the rest are bytes it must overwrite whatever they held, and the last is
# the one the cases that do not sweep the speed use.
KNOCK_BACK_SPEED_SEED = 0x5a
KNOCK_BACK_SPEED_SEEDS = (DAMAGE_KNOCKBACK_SPEED, 0x00, 0xff, KNOCK_BACK_SPEED_SEED)


def _run_knock_back(case, record, flags, speed):
    """One entrance at $6ade with ``record`` in a1, against an EXACT write set: the record's flags
    byte, its speed byte and the trigger's own, which come from test_sound.py's model the way the
    two damage paths' do."""
    what = f"actor_knock_back_and_launch {case}"
    pokes = _state_pokes(case_salt(what), {})
    for at in (record, KNOCK_BACK_DECOY):
        pokes[at + ACTOR_FLAGS] = bytes([flags])
        pokes[at + SPEED] = bytes([speed])

    image = harness.make_image(pokes)
    expected = {
        record + ACTOR_FLAGS: (flags | KNOCK_BACK_MOTION_BITS) & ~(1 << SUPPORTED_BIT) & BYTE_MASK,
        record + SPEED: DAMAGE_KNOCKBACK_SPEED,
    }
    sound = sfx_expected_writes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A)
    expected.update(_sfx_bytes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A))

    info = leaf.run("actor_knock_back_and_launch", _KNOCK_BACK(record), merge_bands(expected), what,
                    regs={"a1": record, "a0": KNOCK_BACK_DECOY, "_pokes": pokes,
                          **DAMAGE_ENTRY_REGS},
                    max_insns=KNOCK_BACK_INSN_CAP)
    _assert_writes(info, expected, what)
    assert_sfx_written(info, sound, f"{what}: the effect it triggers")
    assert info["regs"]["a1"] == record, (
        f"{what}: the original left a1={info['regs']['a1']:#x}, not the {record:#x} it was entered "
        f"with — nothing here moves it")
    return info


@pytest.mark.parametrize("speed", KNOCK_BACK_SPEED_SEEDS, ids=lambda v: f"speed{v:#04x}")
@pytest.mark.parametrize("flags", [seed for _id, seed in KNOCK_BACK_FLAG_SEEDS],
                         ids=[case_id for case_id, _seed in KNOCK_BACK_FLAG_SEEDS])
def test_the_knock_back_launches_the_record_and_stamps_one_exact_speed(flags, speed):
    """`bset #0 / bset #1 / bclr #2 / move.b #$5,11(a1)` and the SFX in front of them, as the whole
    write set. The `settled` and `speed0x05` rows are the ones the attribution pass earns: both
    stores land on bytes that already held the value, and are writes all the same."""
    _run_knock_back(f"flags={flags:#04x} speed={speed:#04x}", KNOCK_BACK_RECORD, flags, speed)


@pytest.mark.parametrize("record", [FOLLOWED_DEFAULT, FOLLOWED_A32, KNOCK_BACK_RECORD,
                                    TABLE_A32 + 9 * RECORD_BYTES],
                         ids=["followed-default", "followed-a32", "default-slot-6", "a32-slot-9"])
def test_the_knock_back_lands_on_whichever_record_a1_names(record):
    """a1 is the only thing that says where the record is. Two of the three entrances hand it one of
    the two FOLLOWED records, so those two rows are the ones a port that hardcoded either address
    would still pass — the other two are what fails it."""
    _run_knock_back(f"into {record:#x}", record, KNOCK_BACK_INVERTED, KNOCK_BACK_SPEED_SEED)


def test_the_knock_back_leaves_the_stub_table_and_the_effect_it_asked_for():
    """The registers, which no write set can show: `move.w #$b,d0 / clr.w d1` are WORD stores into
    two longwords the caller owns, and the stub's `movem` pair hands both back across the call."""
    info = _run_knock_back("registers", KNOCK_BACK_RECORD, KNOCK_BACK_INVERTED,
                           KNOCK_BACK_SPEED_SEED)
    assert info["regs"]["a5"] == SND_STUB_TABLE, "a5 is not the stub table the `lea` names"
    assert info["regs"]["d0"] == leaf.set_low_word(DAMAGE_ENTRY_REGS["d0"], DAMAGE_FOLLOWED_SFX), (
        f"d0 came back {info['regs']['d0']:#010x}, not the caller's high half over effect "
        f"{DAMAGE_FOLLOWED_SFX:#x}")
    assert info["regs"]["d1"] == leaf.set_low_word(DAMAGE_ENTRY_REGS["d1"], SND_CHANNEL_A), (
        f"d1 came back {info['regs']['d1']:#010x}, not the caller's high half over channel "
        f"{SND_CHANNEL_A}")


def test_the_shared_tail_is_the_last_forty_two_bytes_of_the_damage_path():
    """`_damage_followed_entry` builds its own ending out of `_knock_back_and_launch_entry`, so this
    is the address half of what makes that legitimate: $6ade really is where $69fe's body ends less
    those forty-two bytes, and the pin at each of the two entries really is the image's."""
    followed = leaf.entry_of("actor_damage_followed")
    tail = ENTRY_BYTES["actor_knock_back_and_launch"]
    assert leaf.entry_of("actor_knock_back_and_launch") == (
        followed + len(ENTRY_BYTES["actor_damage_followed"]) - len(tail)), (
        f"$6ade is not the last {len(tail)} bytes of the "
        f"{len(ENTRY_BYTES['actor_damage_followed'])} at {followed:#x}")
    assert ENTRY_BYTES["actor_damage_followed"].endswith(tail), (
        "the damage path's pin no longer ends in the shared tail's bytes")


def test_the_knock_back_is_named_by_exactly_the_two_branches_the_plate_says():
    """$6ad0's `bra.w` and $15e8's, and nothing else in the program names the address.

    THE THIRD ENTRANCE DOES NOT APPEAR HERE AND CANNOT: $69fe also FALLS THROUGH into these bytes at
    $6adc, and a fall-through is the absence of an instruction naming the address rather than one
    more site. What bounds that entrance is the arithmetic in the case above, not this census.

    The scan is test_behavior.py's — every way an instruction can name an address, keyed by target —
    imported rather than restated so the two censuses cannot disagree about the same instruction. It
    is imported INSIDE the case because that module imports THIS one: a module-level import here
    would be a cycle whose failure depended on which file pytest collected first.
    """
    from test_behavior import INSTRUCTION_TARGETS

    entry = leaf.entry_of("actor_knock_back_and_launch")
    sites = sorted(INSTRUCTION_TARGETS.get(entry, []))
    assert [at for at, _op in sites] == [0x15e8, 0x6ad0], (
        f"{entry:#x} is named by {[hex(at) for at, _op in sites]}, not by $15e8 and $6ad0")
    for at, op in sites:
        assert op == BRA_W, f"the site at {at:#x} is {op:#06x}, not the `bra.w` the plate claims"


# --- $6bb8: what a defeat costs ---------------------------------------------------------------------
# THE FIRST GAME-LOGIC CASE IN THIS PROJECT WHOSE RUN DRIVES THE CHIP. Its boss arm calls stub +28,
# which is snd_stop -> snd_stop_all_sfx -> snd_psg_silence, so a case declares the mixer with
# `psg_seed` and test_sound.py's models say what the module state and the access ledger must be. It
# also calls the panel's score accumulator and its meter clamp, and the SFX trigger — five ported
# callees in one routine, every one of them compared through the battery that owns it.
#
# THE ATTRIBUTION (POISON) PASS IS OFF, for test_scene.py's reason. The pass inverts every
# oracle-written byte and re-runs, and here two of those bytes STEER the routine: the kill count is
# written and then read back for the `ble` that decides the exit — so a poisoned re-run of a respawn
# case takes the retire arm and never reaches the checkpoint — and the packed-BCD score, inverted,
# stops being digits at all and the model has nothing to say about it. What stands in for it is the
# address-keyed seeding every case here uses plus `_assert_writes`, which compares the oracle's write
# set against the model for EQUALITY rather than bounding it.
#
# AND SINCE BATCH 22 IT RUNS TO THE ORIGINAL'S OWN `rts` ON EVERY ARM. `ble.w` leaves for the respawn
# continuation at DEFEAT_RESPAWN_PC, which is reconstructed below, so a defeat case is a whole defeat
# — including whichever stage_random_kind draw the continuation makes, whose model comes from
# test_rng.py the way the BCD accumulator's comes from test_hud.py.

_DEFEAT = leaf.register_glue("actor_defeat_and_score", [ctypes.c_uint32], ctypes.c_uint32)
_RESPAWN = leaf.register_glue("actor_respawn_as_new_kind", [ctypes.c_uint32] * 3, ctypes.c_uint32)

# The body's own instruction count on the longest path (gate 4, boss block 9, the record and template
# setup 6, the type test 2, the score block 9, the retire tail 8), plus the three chains it calls and
# the ONE sentinel the whole run ends on.
#
# THE STOP CHAIN IS REACHED THROUGH A STUB, so its cost is stub +28's own four instructions on top of
# `snd_stop`'s cap — and that cap already carries a sentinel of its own, for a run that entered
# `snd_stop` directly. Here it does not: `osh_run` counts one instruction past the OUTERMOST `rts`
# and no other, so the chain's sentinel is subtracted and one is added for this routine instead.
# `STUB_INSN_CAP` needs no such correction — the trigger's cap never had one.
DEFEAT_BODY_INSNS = 4 + 9 + 6 + 2 + 9 + 8
STUB_INSNS = 4                  # `movem.l d0-a6,-(a7) / bsr.w / movem.l (a7)+,d0-a6 / rts`
METER_ADD_INSNS = 6
BCD_ADD_INSNS = 12
STOP_CHAIN_INSNS = STUB_INSNS + STOP_INSN_CAP - leaf.RUNNER_SENTINEL_INSN

# ...and the continuation's own longest path: the split 3, the forced-kind arm 4, the sign test 2 and
# the sixteen instructions that rebuild the record. The DRAW it calls is the wider of the two, whose
# cost is test_rng.py's cap for the sibling less that battery's own sentinel.
RESPAWN_BODY_INSNS = 3 + 4 + 2 + 16
RESPAWN_DRAW_INSNS = KIND32_INSN_CAP - leaf.RUNNER_SENTINEL_INSN
RESPAWN_INSN_CAP = RESPAWN_BODY_INSNS + RESPAWN_DRAW_INSNS + leaf.RUNNER_SENTINEL_INSN
DEFEAT_RETIRE_INSN_CAP = (DEFEAT_BODY_INSNS + STOP_CHAIN_INSNS + STUB_INSN_CAP
                          + METER_ADD_INSNS + BCD_ADD_INSNS + leaf.RUNNER_SENTINEL_INSN)
DEFEAT_INSN_CAP = DEFEAT_RETIRE_INSN_CAP + RESPAWN_BODY_INSNS + RESPAWN_DRAW_INSNS

# Where a case puts the record that died. The boss arm needs the ONE address the `cmpa.l` accepts;
# every other case uses an ordinary slot of the default table, so "which record" is a case's choice.
DEFEAT_ACTOR = TABLE_DEFAULT + 5 * RECORD_BYTES

# The mixer the chip is declared to hold. TOS leaves both port-direction bits set, and they are what
# `ori.b #$3f` must carry through — test_sound.py sweeps the rest.
DEFEAT_MIXER = {PSG_REG_MIXER: 0xc0}

# Every byte of state the routine reads, seeded: none of the five callees may be entered on a value a
# case did not choose. The module state is seeded AWAY from what the stop chain writes, so each of
# its clears is a change rather than a coincidence.
#
# The last five are the RESPAWN continuation's inputs: the two forced-kind words a template can carry
# (zero here, so the default is a DRAWN kind) and the generator's whole state, which decides which
# candidate the draw lands on. Stage 5 with an idle generator draws candidate 3 of that stage's row —
# kind 2 out of the 8-wide table and kind 13 out of the 32-wide one, two different rows of
# WB_ACTOR_KIND_TABLE, so the two arms cannot be confused for one another.
DEFEAT_STATE = dict(
    a32=0x0000, actor_type=4, template_slot=2, spawn_type=5, kills=0x0005,
    live=0x0007, wrapped=0x0000, score=0x00123400, meter=0x0028, meter_max=0x0064,
    armed=0x11, countdown=0x22, engine=0xff, sfx_flags=b"\x01\x02\x03\x04",
    shadow=b"\x11\x22\x33\x44", score_entry=None,
    respawn_kind=0x0000, final_kind=0x0000, stage=0x0005, tick=0x0000, counters=(0, 0, 0),
)
BCD_SCORE = wb("BCD_SCORE")
BCD_SCORE_LEN = wb("BCD_SCORE_LEN")
BCD_ADDEND = wb("BCD_ADDEND")
BCD_ADDEND_SEED = 0x87654321      # not a score any case adds, so the staging store is visible
SND_ENGINE_ENABLED = wb("SND_ENGINE_ENABLED")
SND_SFX_ACTIVE_FLAGS = wb("SND_SFX_ACTIVE_FLAGS")
SND_PSG_SHADOW = wb("SND_PSG_SHADOW")
SND_SHADOW_SEED_LEN = 4           # the four bytes snd_stop_all_sfx rewrites, from the mixer shadow on
PSG_REG_MIXER_SHADOW = SND_PSG_SHADOW + PSG_REG_MIXER


# `lsl.w #2,d2` shifts the type twice inside the word, so the LAST bit to leave it — the one the
# 68000 leaves in X — is bit WB_SPAWN_SCORE_EXTEND_BIT, and `bcd_add_score_bd70`'s first `abcd`
# folds it into the score's lowest digit. src/actor.c THREADS that bit (batch 33 phase B), so it is
# an ordinary input here: the shift runs inside this routine, which means the 1 is produced by the
# run and not asked of the harness's entry CCR. The shift distance is the header's, so a change
# there moves both spellings at once.
SCORE_INDEX_EXTEND_SHIFT = wb("SPAWN_SCORE_EXTEND_BIT")


def _score_entry_extend(spawn_type):
    """The X `lsl.w #2,d2` leaves for the score add — the last bit it pushed out of the word."""
    return (spawn_type >> SCORE_INDEX_EXTEND_SHIFT) & 1


def _scaled_spawn_type(spawn_type):
    """`lsl.w #2,d2` — the score index, and (because nothing writes d2 between that shift and the
    `ble.w`) the very d2 the respawn continuation carries into its draw. ONE derivation, so a
    correction to either reading lands on both."""
    return (spawn_type << SCORE_SHIFT) & WORD_MASK


def _defeat_template(slot):
    """Which record of the seeded template table a slot names."""
    return TEMPLATE_TABLE + slot * SPAWN_RECORD_BYTES


def _score_table_entry(spawn_type):
    """WHERE the read goes: `lsl.w #2,d2` wraps the scaled type inside SIXTEEN BITS and
    `move.l 0(a2,d2.l),d0` then takes the whole longword, so a type from $4000 up reads ABOVE the
    table rather than off its end. Every case keys its seed off this rather than off the type."""
    return SCORE_TABLE + _scaled_spawn_type(spawn_type)


def _defeat_pokes(what, **overrides):
    state = {**DEFEAT_STATE, **overrides}
    salt = case_salt(f"actor_defeat_and_score {what}")
    actor = state.pop("actor", DEFEAT_ACTOR)
    # (A bit-14 spawn type was REFUSED here until batch 33 phase B, on the grounds that the port
    # could not reproduce the X the shift leaves. It can now, and the refusal was hiding a real
    # divergence rather than protecting the battery — SCORE_EXTEND_TYPES drives both answers.)
    pokes = _state_pokes(salt, {FLAG_A32: state["a32"], METER_VALUE: state["meter"],
                                METER_MAX: state["meter_max"]})
    pokes[BCD_SCORE] = longword(state["score"])
    pokes[BCD_ADDEND] = longword(BCD_ADDEND_SEED)
    pokes[SND_ENGINE_ENABLED] = bytes([state["engine"]])
    pokes[SND_SFX_ACTIVE_FLAGS] = state["sfx_flags"]
    pokes[PSG_REG_MIXER_SHADOW] = state["shadow"]

    _template_band(salt, TEMPLATE_TABLE, TEMPLATE_SLOTS, pokes)
    pokes[TABLE_PTR] = longword(TEMPLATE_TABLE)
    pokes[STAGE_NUMBER] = word(state["stage"])
    pokes[FRAME_TICK] = word(state["tick"])
    for (counter, _limit, _name), value in zip(RNG_COUNTERS, state["counters"]):
        pokes[counter] = word(value)

    template = _defeat_template(state["template_slot"])
    pokes[template + SPAWN_TYPE] = word(state["spawn_type"])
    pokes[template + SPAWN_KILL_COUNT] = word(state["kills"])
    pokes[template + SPAWN_RESPAWN_KIND] = word(state["respawn_kind"])
    pokes[template + SPAWN_FINAL_KIND] = word(state["final_kind"])
    pokes[template + SPAWN_ARMED] = bytes([state["armed"]])
    pokes[template + SPAWN_COUNTDOWN] = bytes([state["countdown"]])
    header = TEMPLATE_TABLE - SPAWN_HEADER_BYTES
    pokes[header + HEADER_LIVE] = word(state["live"])
    pokes[header + HEADER_WRAPPED] = word(state["wrapped"])
    if state["score_entry"] is not None:
        pokes[_score_table_entry(state["spawn_type"])] = longword(state["score_entry"])

    pokes[actor + ACTOR_TYPE] = word(state["actor_type"])
    pokes[actor + TEMPLATE_SLOT] = bytes([state["template_slot"]])
    pokes[actor + FIELD_18] = bytes([FIELD_18_SEED])
    return actor, pokes


def _stop_chain_bytes():
    """test_sound.py's statement of what the stop chain writes, flattened to {address: byte} — the
    same flattening `_sfx_bytes` does for the trigger, and for the same reason."""
    return {addr + index: value[index]
            for addr, value in STOP_WRITES.items() for index in range(len(value))}


def _model_retire(image, actor, template):
    """$6c38's own writes: the live count down, the slot marked free and — on ANY nonzero wrapped
    flag — the template re-armed. Three entrances reach it, so it is one model, as it is one helper
    in src/actor.c."""
    out = {}
    table = _u32(image, TABLE_PTR)
    header = table - SPAWN_HEADER_BYTES
    _put_word(out, header + HEADER_LIVE, (u16(image, header + HEADER_LIVE) - 1) & WORD_MASK)
    _put_word(out, actor + ACTOR_X, FREE_MARKER)
    # `tst.w -2(a6) / beq` — ANY nonzero re-arms, where $ff42's own test of the same word is
    # `cmpi.w #$ffff`; the two part company on a small positive value.
    if u16(image, header + HEADER_WRAPPED) != 0:
        out[template + SPAWN_ARMED] = SPAWN_REARM
        out[template + SPAWN_COUNTDOWN] = SPAWN_REARM
    return out


def _kind_row(kind):
    """WHERE `lea $1044c.l,a2 / lsl.w #4,d0 / lea 0(a2,d0.w),a2` lands: the shift wraps INSIDE the
    word and the index is then SIGN-EXTENDED, so a kind at or above $0800 reads BELOW the table.
    Shared with the guard that bounds it, so no case can assert about a different address."""
    return KIND_TABLE + s16((kind << KIND_RECORD_SHIFT) & WORD_MASK)


def _model_respawn(image, actor, template, entry_d2, kills=None, video=0):
    """(the exit it reports, {address: byte}) for $6cdc — its own cases' model, and the one
    `_model_defeat` composes onto the end of its respawn arm.

    `kills` is the one byte pair the continuation reads that its CALLER has already rewritten: the
    count `addq.w #1,6(a1)` raised. A case entered at $6cdc leaves it None and the model reads
    memory, which is what the routine does; `_model_defeat` passes the raised value instead of
    handing this a mutated copy of the whole image."""
    out = {}
    if kills is None:
        kills = u16(image, template + SPAWN_KILL_COUNT)
    final = kills == KILL_RESPAWN_LIMIT
    draw = DRAW8 if final else DRAW32
    kind = u16(image, template + (SPAWN_FINAL_KIND if final else SPAWN_RESPAWN_KIND))
    if kind == 0:
        kind, drawn_writes = model_stage_kind(draw, image, entry_d2, video)
        out.update(drawn_writes)

    # `tst.w d0 / bmi.w $6c38` — a forced kind with its top bit set frees the slot instead.
    if s16(kind) < 0:
        out.update(_model_retire(image, actor, template))
        return DEFEAT_RETIRED, out

    out[actor + KIND] = kind & 0xff             # `move.b d0,20(a0)` — the LOW byte alone
    out[actor + ACTOR_FLAGS] = (image[actor + ACTOR_FLAGS]
                                | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & ~(1 << SUPPORTED_BIT)
    out[actor + FIELD_10] = RESPAWN_FIELD_10
    out[actor + SPEED] = RESPAWN_SPEED
    out[actor + FIELD_12] = RESPAWN_FIELD_12
    out[actor + FIELD_30] = RESPAWN_FIELD_30
    row = _kind_row(kind)
    _put_word(out, actor + ACTOR_TYPE, u16(image, row + KIND_TYPE))
    _put_word(out, actor + ACTOR_SPRITE, u16(image, row + KIND_SPRITE))
    _put_long(out, actor + HALF_WIDTH, RESPAWN_SIZE)
    return DEFEAT_RESPAWN, out


def _model_defeat(image, actor):
    """(the exit it reports, whether the `ble.w` fired, {address: byte}). The arms are SEQUENTIAL and
    only one address is both written and read (the kill count), so the model composes its callees'
    models over one dict in the order the instructions run — the SFX trigger's ACTIVE flag lands on a
    byte the stop chain cleared two calls earlier, which is exactly what that ordering says."""
    out = {}
    if u16(image, FLAG_A32) != 0 and actor == BOSS_ORIGIN:
        out.update(_stop_chain_bytes())
        _put_word(out, BOSS_DEFEAT_FLAG, BOSS_DEFEAT_SET)
        out.update(_sfx_bytes(image, BOSS_DEFEAT_SFX, SND_CHANNEL_A))
        _put_word(out, METER_VALUE, meter_add_expected(u16(image, METER_VALUE),
                                                       u16(image, METER_MAX),
                                                       BOSS_DEFEAT_METER_BONUS))
    out[actor + FIELD_18] = 0

    table = _u32(image, TABLE_PTR)
    # `lsl.l #5,d0 / lea 0(a1,d0.w),a1`: a LONG shift indexed by a sign-extended WORD.
    template = (table + s16((image[actor + TEMPLATE_SLOT] << TEMPLATE_SLOT_SHIFT) & WORD_MASK)
                ) & 0xffffffff
    if u16(image, actor + ACTOR_TYPE) != TYPE_UNSCORED:
        spawn_type = u16(image, template + SPAWN_TYPE)
        scaled_type = _scaled_spawn_type(spawn_type)
        addend = _u32(image, _score_table_entry(spawn_type))
        _put_long(out, BCD_ADDEND, addend)
        _put_long(out, BCD_SCORE,
                  bcd_expected(_u32(image, BCD_SCORE), addend, BCD_SCORE_LEN, False,
                               _score_entry_extend(spawn_type)).value)
        kills = (u16(image, template + SPAWN_KILL_COUNT) + 1) & WORD_MASK
        _put_word(out, template + SPAWN_KILL_COUNT, kills)
        # `cmpi.w #$2,6(a1) / ble` — signed, and read back out of MEMORY. The d2 the continuation
        # carries into its draw is what the `moveq #0,d2` and `lsl.w #2,d2` above left: the scaled
        # spawn type in the low word, nothing above it.
        if s16(kills) <= KILL_RESPAWN_LIMIT:
            exit_code, continued = _model_respawn(image, actor, template, scaled_type, kills=kills)
            out.update(continued)
            return exit_code, True, out

    out.update(_model_retire(image, actor, template))
    return DEFEAT_RETIRED, False, out


def _run_defeat(case, actor, pokes, psg_seed=None):
    """One defeat differential, run to the original's own `rts` on every arm. A run whose kill count
    let the `ble.w` fire also carries the WITNESS that it did — the transfer instruction executed —
    so "which tail ran" is a fact about the run and not only about the write set."""
    what = f"actor_defeat_and_score {case}"
    image = harness.make_image(pokes)
    expected_exit, took_tail, expected = _model_defeat(image, actor)
    seed = DEFEAT_MIXER if psg_seed is None else psg_seed

    # The respawn tail draws a kind, and the generator's entropy term is a MODELED hardware byte
    # since batch 33 — so every defeat that can reach it declares what the counter held.
    how = dict(regs={"a0": actor, "_pokes": pokes, **DAMAGE_ENTRY_REGS},
               max_insns=DEFEAT_INSN_CAP if took_tail else DEFEAT_RETIRE_INSN_CAP,
               poison=False, psg_seed=seed, hw_seed=leaf.hw_declared())
    runner = leaf.run_reaching if took_tail else leaf.run
    extra = (DEFEAT_TRANSFER,) if took_tail else ()
    info = runner("actor_defeat_and_score", _DEFEAT(actor), merge_bands(expected), what,
                  *extra, **how)

    _assert_writes(info, expected, what)
    assert info["ret"] == expected_exit, (
        f"{what}: the reconstruction reported exit {info['ret']}, not the {expected_exit} this "
        f"case expects")
    assert info["regs"]["a0"] == actor, f"{what}: a0 moved, which this routine does not do"
    return info, expected


# The spawn types a scoring case uses, and what the shipped table pays for each — read off the image
# rather than tabulated, so the sweep follows the data. Chosen for DISTINCT scores, so a port that
# indexed the table one entry out fails on the digits and not only on a branch.
SCORING_TYPES = (2, 4, 11, 25, 26)


def test_the_scoring_sweep_reaches_distinct_scores():
    """The guard on SCORING_TYPES: types whose table entries agreed would make the sweep one case
    repeated, and the table really does repeat ($200 and $2000 each appear several times)."""
    paid = [_u32(harness.BASE_IMAGE, _score_table_entry(t)) for t in SCORING_TYPES]
    assert len(set(paid)) == len(paid), f"the sweep pays {[hex(p) for p in paid]}"
    assert all(paid), "a zero entry would make the BCD add a no-op and pin nothing"


@pytest.mark.parametrize("spawn_type", SCORING_TYPES, ids=[f"type_{t}" for t in SCORING_TYPES])
def test_a_defeat_pays_its_templates_score_frees_the_slot_and_lowers_the_live_count(spawn_type):
    """The ordinary path, with the kill count above its limit so the routine runs to its `rts`."""
    case = f"an ordinary defeat, spawn type {spawn_type}"
    actor, pokes = _defeat_pokes(case, spawn_type=spawn_type)
    _run_defeat(case, actor, pokes)


# (seeded kill count, the exit it produces, why). The compare is `cmpi.w #2 / ble` on the value the
# `addq` left IN MEMORY, and it is SIGNED — so $7fff, raised, is a negative count and respawns.
KILL_COUNT_CASES = (
    (0x0000, DEFEAT_RESPAWN, "raised to 1, well under the limit"),
    (0x0001, DEFEAT_RESPAWN, "raised to exactly the limit, which `ble` accepts"),
    (0x0002, DEFEAT_RETIRED, "raised one PAST it — the first count that retires"),
    (0x0005, DEFEAT_RETIRED, "well past it"),
    (0x7fff, DEFEAT_RESPAWN, "raised into the NEGATIVE half, which a signed `ble` accepts"),
    (0xffff, DEFEAT_RESPAWN, "wrapped to 0"),
    (0x8000, DEFEAT_RESPAWN, "the most negative count there is"),
)


@pytest.mark.parametrize("kills,expected_exit,why", KILL_COUNT_CASES,
                         ids=[f"kills_{c[0]:04x}" for c in KILL_COUNT_CASES])
def test_the_kill_count_decides_between_freeing_the_slot_and_the_respawn_tail(kills, expected_exit,
                                                                              why):
    case = f"a kill count of {kills:#06x} ({why})"
    actor, pokes = _defeat_pokes(case, kills=kills)
    info, _expected = _run_defeat(case, actor, pokes)
    assert info["ret"] == expected_exit


def test_the_kill_count_sweep_brackets_the_limit_and_reaches_both_exits():
    """A sweep that never sat exactly ON the limit would pass a `blt` written for a `ble`, and one
    that never crossed the sign would pass an UNSIGNED compare."""
    counts = [(kills + 1) & WORD_MASK for kills, _exit, _why in KILL_COUNT_CASES]
    assert KILL_RESPAWN_LIMIT in counts and KILL_RESPAWN_LIMIT + 1 in counts
    assert any(s16(count) < 0 for count in counts)
    assert {exit_code for _kills, exit_code, _why in KILL_COUNT_CASES} == {DEFEAT_RETIRED,
                                                                          DEFEAT_RESPAWN}


def test_the_unscored_type_pays_nothing_counts_nothing_and_always_frees_the_slot():
    """`cmpi.w #$26,4(a0) / beq` jumps PAST the score, the kill count AND the `ble`, so this type
    can never respawn however low its template's count is."""
    case = "the unscored type, with a kill count that would otherwise respawn"
    actor, pokes = _defeat_pokes(case, actor_type=TYPE_UNSCORED, kills=0)
    info, expected = _run_defeat(case, actor, pokes)
    assert info["ret"] == DEFEAT_RETIRED
    assert not any(addr in expected for addr in (BCD_SCORE, BCD_ADDEND)), (
        "the unscored arm must not reach the score accumulator at all")


def test_the_type_test_is_a_word_compare_against_that_value_alone():
    """The neighbours of $26 have to take the ordinary arm, or a port that tested a BYTE or a range
    would pass. $0026 is also what the low byte of $1026 is, which is the other half of it."""
    for actor_type in (TYPE_UNSCORED - 1, TYPE_UNSCORED + 1, 0x1000 | TYPE_UNSCORED):
        case = f"actor type {actor_type:#06x}, one the unscored test must not catch"
        actor, pokes = _defeat_pokes(case, actor_type=actor_type, kills=5)
        info, expected = _run_defeat(case, actor, pokes)
        assert BCD_SCORE in expected, f"{case}: the score arm was skipped"
        assert info["ret"] == DEFEAT_RETIRED


# (wrapped word, whether the template is re-armed, why). `tst.w -2(a6) / beq` reads ANY nonzero,
# where $ff42's own test of the same word is `cmpi.w #$ffff` — so a small positive value is where
# the two readings part company, and this routine's is the looser one.
WRAPPED_CASES = (
    (0x0000, False, "the cursor has not been round: the template retires"),
    (0xffff, True, "WB_SPAWN_WRAPPED_SET, the only value the image itself writes"),
    (0x0001, True, "a small positive value — `tst.w` takes it where `cmpi.w #$ffff` would not"),
    (0x8000, True, "a negative one"),
)


@pytest.mark.parametrize("wrapped,rearms,why", WRAPPED_CASES,
                         ids=[f"wrapped_{c[0]:04x}" for c in WRAPPED_CASES])
def test_the_wrapped_flag_decides_whether_the_template_is_re_armed(wrapped, rearms, why):
    case = f"a wrapped flag of {wrapped:#06x} ({why})"
    actor, pokes = _defeat_pokes(case, wrapped=wrapped)
    _info, expected = _run_defeat(case, actor, pokes)
    template = _defeat_template(DEFEAT_STATE["template_slot"])
    armed = expected.get(template + SPAWN_ARMED)
    assert (armed == SPAWN_REARM) == rearms, (
        f"{case}: WB_SPAWN_ARMED ended {armed}, and the case expects rearms={rearms}")


# Spawn types whose SCALED index is not what an unwrapped one would be. $8000 scales to zero inside
# the word (so it reads the table's FIRST entry), $2000 to $8000 and $bfff to $fffc, which read 32
# and 64 KiB above the table — all inside the image, none anywhere near the 32 entries the data has.
# Every one of them has BIT 14 CLEAR, which the extend-bit guard below is what enforces.
SCORE_INDEX_WRAP_TYPES = (0x8000, 0x2000, 0xbfff)
WRAP_SCORE = 0x00007700         # a valid packed-BCD score to plant where each one lands


@pytest.mark.parametrize("spawn_type", SCORE_INDEX_WRAP_TYPES,
                         ids=[f"type_{t:04x}" for t in SCORE_INDEX_WRAP_TYPES])
def test_the_score_index_wraps_inside_a_word_and_reads_wherever_that_lands(spawn_type):
    """No bounds check anywhere: the type is scaled by a `lsl.w`, so the index wraps at $10000 and
    the LONGWORD read can name anything in the 64 KiB above the table."""
    case = f"a spawn type of {spawn_type:#06x}, whose scaled index wraps"
    actor, pokes = _defeat_pokes(case, spawn_type=spawn_type, score_entry=WRAP_SCORE)
    _run_defeat(case, actor, pokes)


def test_the_wrap_sweep_lands_outside_the_tables_own_entries():
    """The guard: a sweep whose types all landed inside the 32 shipped entries would be measuring
    the ordinary path under another name."""
    table_end = SCORE_TABLE + SCORE_TABLE_ENTRIES * SCORE_LEN
    reached = [_score_table_entry(t) for t in SCORE_INDEX_WRAP_TYPES]
    assert any(at >= table_end for at in reached), [hex(at) for at in reached]
    assert any(at < table_end for at in reached), (
        "the wrap that lands back INSIDE the table is the one a port using a longword index misses")


# The spawn types whose BIT 14 is SET, so `lsl.w #2,d2` leaves X SET and the score add pays one
# extra unit. $4000's scaled index wraps to zero and reads the table's FIRST entry; $ffff's wraps to
# $fffc, 64 KiB above it — so the two rows drive the extend against two different addends as well.
# These were REFUSED by `_defeat_pokes` until batch 33 phase B, and the refusal was hiding a real
# divergence: against the port that passed a hard-wired zero, $4000 is red at
# `bcd_score_bd70+3 ($bd73): oracle=0x01 cand=0x00`.
SCORE_EXTEND_TYPES = (0x4000, 0xffff)
EXTEND_SCORE = 0x00004500       # a valid packed-BCD addend to plant where each one lands


@pytest.mark.parametrize("spawn_type", SCORE_EXTEND_TYPES,
                         ids=[f"type_{t:04x}" for t in SCORE_EXTEND_TYPES])
def test_a_spawn_types_bit_14_reaches_the_score_as_the_shifts_extend_flag(spawn_type):
    """The X `lsl.w #2,d2` leaves is an INPUT to the very next call, and these are the rows that
    drive it set. Nothing else about the defeat changes, so the only difference from an ordinary
    row is one unit in the score's lowest digit — which is exactly the divergence phase B closed."""
    case = f"a spawn type of {spawn_type:#06x}, whose bit 14 enters the score add"
    actor, pokes = _defeat_pokes(case, spawn_type=spawn_type, score_entry=EXTEND_SCORE)
    _run_defeat(case, actor, pokes)


def test_the_defeat_sweep_drives_both_answers_of_the_shifts_extend_bit():
    """The guard, and the replacement for a test that asserted NO case reached bit 14 (it was named
    for an edge the port could not reproduce, and the port reproduces it). Both answers have to be
    driven or the threading could be dropped for a constant and stay green."""
    clear = set(SCORING_TYPES) | set(SCORE_INDEX_WRAP_TYPES) | {DEFEAT_STATE["spawn_type"]}
    assert not [t for t in clear if _score_entry_extend(t)], (
        f"{[hex(t) for t in clear if _score_entry_extend(t)]} carry bit 14, so the rows that are "
        f"meant to enter the score add with X CLEAR do not")
    assert all(_score_entry_extend(t) for t in SCORE_EXTEND_TYPES), (
        f"{[hex(t) for t in SCORE_EXTEND_TYPES if not _score_entry_extend(t)]} do not carry bit 14, "
        f"so no case enters bcd_add_score_bd70 with X set")


# --- the boss block ---------------------------------------------------------------------------------

def test_the_boss_record_is_slot_three_of_the_table_the_flag_selects():
    """The `cmpa.l` accepts ONE address, and this is what it is: the same slot src/scene.c's
    fragment arm copies all eight fragments' starting position out of."""
    assert BOSS_ORIGIN == TABLE_A32 + 3 * RECORD_BYTES


def test_a_boss_defeat_stops_the_music_raises_the_flag_fires_the_effect_and_pays_the_meter():
    """The whole gated block at once, and the only case in this battery that reaches the chip. The
    stop chain's module state and its PSG ledger are test_sound.py's models, the trigger's writes
    are that battery's too, and the meter's word is test_hud.py's."""
    case = "a boss defeat with the mode flag up"
    actor, pokes = _defeat_pokes(case, a32=0xffff, actor=BOSS_ORIGIN)
    info, expected = _run_defeat(case, actor, pokes)

    assert_stop_chain_psg_state(info, DEFEAT_MIXER, f"{case}: the chip the stop chain silences")
    assert leaf.read_int(info, BOSS_DEFEAT_FLAG, WORD_LEN, case) == BOSS_DEFEAT_SET, (
        "the flag src/scene.c's fragment arm reads next frame")
    assert expected[SND_ENGINE_ENABLED] == 0, "the engine flag is part of stub +28's own writes"
    for offset in range(SND_SHADOW_SEED_LEN):
        assert PSG_REG_MIXER_SHADOW + offset in expected, (
            "the module's shadow of the four silenced registers must be rewritten too")


# (mode flag, the record that died, why) — the two halves of the gate, each failing on its own.
BOSS_GATE_CASES = (
    (0x0000, BOSS_ORIGIN, "the boss record, but the mode flag is down"),
    (0xffff, DEFEAT_ACTOR, "the flag is up, but an ordinary record died"),
    (0x0000, DEFEAT_ACTOR, "neither"),
)


@pytest.mark.parametrize("a32,actor_hint,why", BOSS_GATE_CASES,
                         ids=["flag-down", "wrong-record", "neither"])
def test_the_boss_block_needs_both_the_mode_flag_and_that_one_record(a32, actor_hint, why):
    """Each half of `tst.w $a32.w / beq` and `cmpa.l #$9e94,a0 / bne`. Nothing sounds, nothing is
    flagged and the meter is untouched — and the run makes NO PSG access at all, which is what the
    empty ledger says."""
    case = f"the boss gate: {why}"
    actor, pokes = _defeat_pokes(case, a32=a32, actor=actor_hint)
    info, expected = _run_defeat(case, actor, pokes)
    assert BOSS_DEFEAT_FLAG not in expected, f"{case}: the boss flag was raised"
    assert SND_ENGINE_ENABLED not in expected, f"{case}: the sound module was stopped"
    assert METER_VALUE not in expected, f"{case}: the meter was paid"
    assert info["regs"]["psg_events"] == [], f"{case}: the chip was touched"


def test_the_boss_gate_sweep_covers_both_halves_of_the_test():
    """A sweep that only ever lowered the flag would pass a port that dropped the `cmpa.l`."""
    flags = {a32 for a32, _actor, _why in BOSS_GATE_CASES}
    records = {actor for _a32, actor, _why in BOSS_GATE_CASES}
    assert flags == {0x0000, 0xffff} and records == {BOSS_ORIGIN, DEFEAT_ACTOR}


# The gate's flag is read by `tst.w`, and $0000/$ffff — the only two values the game itself writes,
# and the only two the cases above use — agree with a reader of EITHER byte. These are the words that
# do not: $0100's low byte is zero and $00ff's high byte is, so between them they separate the word
# read from both halves it could have been.
BOSS_FLAG_HALF_ZERO_WORDS = (0x0100, 0x00ff)


@pytest.mark.parametrize("a32", BOSS_FLAG_HALF_ZERO_WORDS,
                         ids=[f"a32_{f:04x}" for f in BOSS_FLAG_HALF_ZERO_WORDS])
def test_the_mode_flag_is_read_as_a_word_and_not_as_either_of_its_bytes(a32):
    case = f"a boss defeat with the mode flag at {a32:#06x}"
    actor, pokes = _defeat_pokes(case, a32=a32, actor=BOSS_ORIGIN)
    _info, expected = _run_defeat(case, actor, pokes)
    assert BOSS_DEFEAT_FLAG in expected, (
        f"{case}: the boss block did not fire, so the gate read one byte of the flag word")


def test_the_word_read_sweep_zeroes_each_half_of_the_flag_in_turn():
    """The guard: either value alone pins only the half it happens to zero."""
    assert any(value & 0xff == 0 for value in BOSS_FLAG_HALF_ZERO_WORDS), (
        "no case zeroes the LOW byte, so a gate reading that byte alone stays unpinned")
    assert any(value >> 8 == 0 for value in BOSS_FLAG_HALF_ZERO_WORDS), (
        "no case zeroes the HIGH byte, so a gate reading that byte alone stays unpinned")
    assert all(value != 0 for value in BOSS_FLAG_HALF_ZERO_WORDS), (
        "each word must be nonzero, or the block it is meant to fire would not fire at all")


def test_the_body_ends_where_its_own_score_table_begins():
    """The two bound each other: `lea $6c5c.l,a2` names the table from inside the body, so the
    entry pin's length and the table's base are one claim. Ghidra's 290 bytes is neither — it folds
    the table in and stops two bytes short of its end."""
    entry = leaf.entry_of("actor_defeat_and_score")
    assert entry + len(ENTRY_BYTES["actor_defeat_and_score"]) == SCORE_TABLE
    assert SCORE_TABLE + SCORE_TABLE_ENTRIES * SCORE_LEN == DEFEAT_RESPAWN_PC, (
        "the table's 32 entries must end exactly on the respawn continuation")


def test_the_respawn_exit_is_the_branch_the_entry_pin_assembles():
    """DEFEAT_TRANSFER is searched for in the bytes this battery ASSEMBLES, so it is worth checking
    the same address holds that `ble.w` in the loaded IMAGE — which is what the runs that reach the
    continuation actually execute, and what RETIRE_TAIL_PC is measured from."""
    expected = branch_w_to(BLE_W, DEFEAT_TRANSFER, DEFEAT_RESPAWN_PC)
    actual = bytes(harness.BASE_IMAGE[DEFEAT_TRANSFER:DEFEAT_TRANSFER + len(expected)])
    assert actual == expected, (
        f"{DEFEAT_TRANSFER:#x} is {actual.hex()}, not the {expected.hex()} the tail's `ble.w` is")


# --- $6cdc: what the slot comes back as ---------------------------------------------------------------
# The continuation the `ble.w` above leaves for, entered on its own so that its two arms, its forced
# kinds and its table index can be reached without going through a whole defeat first. Its entry
# registers are a0 (the record that died), a1 (that record's template) and the d2 whose HIGH half
# `stage_random_kind`'s `add.l` folds into the draw's own table index — test_rng.py owns that half of
# it, so what this battery passes is the value $6bb8 reaches here with.
#
# ITS `bmi` GOES BACK INTO $6bb8, so a case whose forced kind is negative runs the retire tail too and
# the write set it states is that tail's. That is why RETIRE_TAIL_PC is derived from the `ble.w`
# rather than transcribed: one wrong address and the run would fall into the score table.

RESPAWN_TEMPLATE = _defeat_template(DEFEAT_STATE["template_slot"])

# What $6bb8 leaves in d2 by the time it branches here: `moveq #0,d2` zeroed the whole register and
# `lsl.w #2,d2` then put the scaled spawn type in its LOW word, which the draw's own
# `move.w $bd88.l,d2` overwrites. So the half that survives is zero, and that is what the game passes.
RESPAWN_ENTRY_D2 = _scaled_spawn_type(DEFEAT_STATE["spawn_type"])


def _run_respawn(case, pokes, entry_d2=RESPAWN_ENTRY_D2, video=0):
    """One continuation differential — `(info, the image it ran on, the write-set model)`. Every case
    uses DEFEAT_ACTOR and its template, so those are not parameters; the IMAGE comes back because a
    case that wants to say which kind was drawn has to ask the same bytes the run did, and rebuilding
    it from the pokes is a second megabyte for the same answer.

    `poison` is off for `_run_defeat`'s reason — the kill count it reads STEERS which arm runs, so a
    poisoned re-run is a different case."""
    what = f"actor_respawn_as_new_kind {case}"
    image = harness.make_image(pokes)
    expected_exit, expected = _model_respawn(image, DEFEAT_ACTOR, RESPAWN_TEMPLATE, entry_d2,
                                            video=video)
    info = leaf.run("actor_respawn_as_new_kind", _RESPAWN(DEFEAT_ACTOR, RESPAWN_TEMPLATE, entry_d2),
                    merge_bands(expected), what,
                    regs={"a0": DEFEAT_ACTOR, "a1": RESPAWN_TEMPLATE, "d2": entry_d2,
                          "_pokes": pokes, **DAMAGE_ENTRY_REGS},
                    max_insns=RESPAWN_INSN_CAP, poison=False,
                    hw_seed=leaf.hw_declared(video))
    _assert_writes(info, expected, what)
    assert info["ret"] == expected_exit, (
        f"{what}: the reconstruction reported exit {info['ret']}, not the {expected_exit} this "
        f"case expects")
    return info, image, expected


# (kill count, which draw it takes, why). `cmpi.w #$2,6(a1) / beq` is an EQUALITY test on the count
# the `addq` already raised, so only the last respawn a template is allowed takes the 8-wide table —
# a count PAST the limit, which $6bb8 could never branch here with, takes the 32-wide one like any
# other. The two arms land on different rows of WB_ACTOR_KIND_TABLE, which is what makes them tellable
# apart at all (a guard below computes that rather than trusting it).
RESPAWN_ARM_CASES = (
    (0x0001, DRAW32, "under the limit: the 32-wide table"),
    (0x0002, DRAW8, "EXACTLY the limit — the last respawn, and the only 8-wide draw"),
    (0x0003, DRAW32, "past the limit, which the `beq` does not catch"),
    # ...and the one that says the compare is a WORD. A `cmp.b` reading sees $02 against the limit's
    # own low byte and takes the 8-wide arm; the `cmpi.w` the bytes spell sees $0102 and does not.
    # (A byte-wide port passed the three above; this is the case that reddens it.)
    (0x0102, DRAW32, "a count whose LOW BYTE is the limit, which only a WORD compare keeps off it"),
)


@pytest.mark.parametrize("kills,draw,why", RESPAWN_ARM_CASES,
                         ids=[f"kills_{c[0]:04x}" for c in RESPAWN_ARM_CASES])
def test_the_kill_count_picks_which_of_the_two_draws_names_the_new_kind(kills, draw, why):
    case = f"a kill count of {kills:#06x} ({why})"
    _actor, pokes = _defeat_pokes(case, kills=kills)
    info, image, expected = _run_respawn(case, pokes)
    # The expected kind comes from the arm the CASE declares, not from the model's own choice, so a
    # model that picked the wrong table could not agree with itself here.
    kind, _writes = model_stage_kind(draw, image, RESPAWN_ENTRY_D2)
    assert expected[DEFEAT_ACTOR + KIND] == kind, (
        f"{case}: the slot came back as kind {expected[DEFEAT_ACTOR + KIND]}, not the {kind} the "
        f"{draw.name} draw gives")
    assert info["ret"] == DEFEAT_RESPAWN


@pytest.mark.parametrize("video", [0x00, 0x3d, 0xff], ids=lambda v: f"counter{v:#04x}")
def test_the_drawn_kind_follows_the_DECLARED_video_counter(video):
    """THE CONSUMER'S HALF of batch 33's retired false green. Every other case here declares the
    byte the model used to fabricate, so they would all still pass with the entropy term deleted;
    this one varies it and requires the kind the respawn draws to follow. The generator's own
    battery pins the arithmetic — what this adds is that the term reaches a CALLER."""
    case = f"a declared video counter of {video:#04x}"
    _actor, pokes = _defeat_pokes(case)
    info, image, expected = _run_respawn(case, pokes, video=video)
    kind, _writes = model_stage_kind(DRAW32, image, RESPAWN_ENTRY_D2, video)
    assert expected[DEFEAT_ACTOR + KIND] == kind
    assert info["ret"] == DEFEAT_RESPAWN


def test_the_declared_counter_really_changes_the_kind_that_is_drawn():
    """...and the guard on the case above: if all three declarations drew the same kind it would
    pass with the term deleted, exactly as the old fabricated 0 let everything pass."""
    _actor, pokes = _defeat_pokes("the counter guard")
    image = harness.make_image(pokes)
    kinds = {model_stage_kind(DRAW32, image, RESPAWN_ENTRY_D2, v)[0] for v in (0x00, 0x3d, 0xff)}
    assert len(kinds) > 1, (
        f"all three declared counter bytes draw kind {kinds}, so the rows above would pass with the "
        f"entropy term removed")


def test_the_two_arms_draw_from_different_tables_in_the_state_every_case_shares():
    """The guard on RESPAWN_ARM_CASES: if the two draws happened to agree in the seeded generator
    state, every case above would pass with the arms swapped and the `beq` would be unpinned."""
    case = "the arm guard"
    _actor, pokes = _defeat_pokes(case)
    image = harness.make_image(pokes)
    kinds = {draw.name: model_stage_kind(draw, image, RESPAWN_ENTRY_D2)[0] for draw in (DRAW8,
                                                                                       DRAW32)}
    assert len(set(kinds.values())) == 2, f"both arms draw {kinds} — the `beq` is unobservable"
    rows = {_kind_row(kind) for kind in kinds.values()}
    assert len(rows) == 2, "the two kinds must also name different rows of the kind table"
    counts = {kills for kills, _draw, _why in RESPAWN_ARM_CASES}
    assert counts >= {KILL_RESPAWN_LIMIT, KILL_RESPAWN_LIMIT + 1}, (
        "the sweep must sit exactly ON the limit and one past it, or the `beq` could be a `ble`")
    assert any(kills & 0xff == KILL_RESPAWN_LIMIT and kills != KILL_RESPAWN_LIMIT
               for kills in counts), (
        "no case separates a `cmp.w` from a `cmp.b`, so the compare's WIDTH would be unpinned")


# A forced kind skips the draw entirely, and it is the ONLY way a kind above WB_STAGE_KIND_MASK, or a
# negative one, can reach the rest of the routine. `0x0105` is the one that separates the byte STORED
# at WB_ACTOR_KIND from the word that INDEXES the table: `move.b d0,20(a0)` keeps $05 while
# `lsl.w #4,d0` scales the whole $0105.
FORCED_KIND_CASES = (
    (0x0015, "row 21 — the LAST row the table has"),
    (0x0016, "row 22: one PAST the end, onto the longword code pointers that bound it"),
    (0x0105, "a kind whose stored BYTE and whose table index are different numbers"),
    (0x0800, "the smallest kind whose scaled index is NEGATIVE and reads below the table"),
    (0x1000, "a kind whose `lsl.w #4` wraps the word to zero, so it reads row 0"),
    (0x7fff, "the largest kind the `bmi` lets through at all"),
)


@pytest.mark.parametrize("kind,why", FORCED_KIND_CASES,
                         ids=[f"kind_{c[0]:04x}" for c in FORCED_KIND_CASES])
def test_a_template_can_force_the_kind_and_the_index_is_bounded_by_nothing(kind, why):
    """ONE arm is enough for the index: the two share every instruction from the `tst.w` on, and the
    arms themselves are the case below. (Both arms were run over this whole grid until a measured
    trim showed the second copy killed no mutant the first did not.)"""
    case = f"a forced kind of {kind:#06x} ({why})"
    _actor, pokes = _defeat_pokes(case, kills=0x0001, respawn_kind=kind)
    info, _image, expected = _run_respawn(case, pokes)
    assert info["ret"] == DEFEAT_RESPAWN
    assert expected[DEFEAT_ACTOR + KIND] == (kind & 0xff), (
        f"{case}: WB_ACTOR_KIND took {expected[DEFEAT_ACTOR + KIND]:#04x}, not the low byte")


# (kill count, which field it fills, the arm it is on). Each case leaves the OTHER field zero, so a
# port that read the wrong one would draw a kind instead of taking this one and land on a different
# row — which is what makes the two forced-kind fields tellable apart.
FORCED_FIELD_CASES = (
    (0x0001, "respawn_kind", "the 32-wide arm"),
    (KILL_RESPAWN_LIMIT, "final_kind", "the 8-wide arm"),
)
FORCED_FIELD_KIND = 0x0007      # a row the seeded generator never draws (a guard below says so)


@pytest.mark.parametrize("kills,field,arm", FORCED_FIELD_CASES, ids=[c[1] for c in
                                                                    FORCED_FIELD_CASES])
def test_each_arm_takes_its_own_forced_field(kills, field, arm):
    case = f"a forced kind of {FORCED_FIELD_KIND:#06x} in {field}, on {arm}"
    _actor, pokes = _defeat_pokes(case, kills=kills, **{field: FORCED_FIELD_KIND})
    info, _image, expected = _run_respawn(case, pokes)
    assert info["ret"] == DEFEAT_RESPAWN
    assert expected[DEFEAT_ACTOR + KIND] == FORCED_FIELD_KIND, (
        f"{case}: the slot came back as {expected[DEFEAT_ACTOR + KIND]:#04x} — the other field was "
        f"read, or the draw ran")


def test_the_forced_field_kind_is_one_neither_draw_produces():
    """The guard: if FORCED_FIELD_KIND happened to equal what the seeded generator draws, a port
    that read the wrong (zero) field would draw that very kind and the case would pass."""
    _actor, pokes = _defeat_pokes("the forced-field guard")
    image = harness.make_image(pokes)
    drawn = {model_stage_kind(draw, image, RESPAWN_ENTRY_D2)[0] for draw in (DRAW8, DRAW32)}
    assert FORCED_FIELD_KIND not in drawn, f"the draws give {sorted(drawn)}, which includes it"


def test_the_forced_kind_sweep_reaches_both_sides_of_the_tables_own_extent():
    """The guard: a sweep confined to the 22 shipped rows would be silent about an index the
    instruction bounds at neither end, which is what `lsl.w`-then-sign-extend means."""
    rows = [_kind_row(kind) for kind, _why in FORCED_KIND_CASES]
    table_end = KIND_TABLE + KIND_TABLE_ROWS * KIND_RECORD_BYTES
    assert any(row < KIND_TABLE for row in rows), "no case reads BELOW the table"
    assert any(row >= table_end for row in rows), "no case reads past its last row"
    assert any(KIND_TABLE <= row < table_end for row in rows), "no case reads a shipped row"


def test_every_index_the_routine_can_compute_stays_inside_the_image():
    """WHY src/actor.c carries no off-image guard and no bus mask on this read, computed rather than
    asserted: the `bmi` bounds the kind to $0000..$7fff, `lsl.w #4` bounds the scaled word to
    $0000..$fff0, and the sign extension of THAT bounds the row to one 64 KiB window around the
    table — which lies inside the image at both ends, nowhere near the 24-bit bus."""
    rows = [_kind_row(kind) for kind in range(0x8000)]
    lowest, highest = min(rows), max(rows)
    assert lowest == KIND_TABLE - 0x8000 and highest == KIND_TABLE + 0x7ff0, (
        f"the index window is [{lowest:#x}, {highest:#x}], not the one the two shifts bound")
    assert 0 <= lowest and highest + KIND_RECORD_BYTES <= harness.IMAGE_SIZE, (
        "an index this routine can compute leaves the image, so the read needs a guard after all")


# (forced kind, why) — the far side of `tst.w d0 / bmi.w $6c38`, which no DRAWN kind can reach because
# both draws close with `andi.l #$1f`. It frees the slot instead, which is $6bb8's retire tail run from
# a third entrance.
NEGATIVE_KIND_CASES = (
    (0xffff, "the least negative kind there is"),
    (0x8000, "the most negative"),
    (0x8001, "one whose LOW BYTE is a perfectly ordinary kind, so a byte test would let it through"),
)


@pytest.mark.parametrize("kind,why", NEGATIVE_KIND_CASES,
                         ids=[f"kind_{c[0]:04x}" for c in NEGATIVE_KIND_CASES])
def test_a_negative_forced_kind_frees_the_slot_through_the_retire_tail(kind, why):
    case = f"a forced kind of {kind:#06x} ({why})"
    _actor, pokes = _defeat_pokes(case, kills=0x0001, respawn_kind=kind)
    info, _image, expected = _run_respawn(case, pokes)
    assert info["ret"] == DEFEAT_RETIRED
    assert expected[DEFEAT_ACTOR + ACTOR_X] == FREE_MARKER >> 8, "the slot was not marked free"
    assert DEFEAT_ACTOR + KIND not in expected, "the record was rebuilt on a kind the `bmi` refused"


def test_a_negative_kind_reached_through_a_whole_defeat_retires_the_slot():
    """The same branch, but through $6bb8: a template UNDER its kill limit — which by itself means a
    respawn — still frees the slot when the kind it forces is negative. That is the third entrance to
    the retire tail, and the reason `actor_defeat_and_score` reports its exit rather than deriving it
    from the kill count."""
    case = "a defeat under the kill limit whose forced kind is negative"
    actor, pokes = _defeat_pokes(case, kills=0x0000, respawn_kind=0x8000)
    info, expected = _run_defeat(case, actor, pokes)
    assert info["ret"] == DEFEAT_RETIRED
    assert expected[actor + ACTOR_X] == FREE_MARKER >> 8


def test_the_rebuilt_record_takes_its_type_and_sprite_from_the_kind_tables_own_row():
    """The nine writes, stated once against the row the kind names — and the row read off the shipped
    table rather than tabulated here, so the case follows the data."""
    case = "the rebuilt record's whole field set"
    actor, pokes = _defeat_pokes(case, kills=0x0001)
    info, image, expected = _run_respawn(case, pokes)
    kind, _writes = model_stage_kind(DRAW32, image, RESPAWN_ENTRY_D2)
    row = _kind_row(kind)

    assert leaf.read_int(info, actor + ACTOR_TYPE, WORD_LEN, case) == u16(image, row + KIND_TYPE)
    assert leaf.read_int(info, actor + ACTOR_SPRITE, WORD_LEN, case) == u16(image,
                                                                           row + KIND_SPRITE)
    assert leaf.read_int(info, actor + HALF_WIDTH, LONGWORD_LEN, case) == RESPAWN_SIZE
    assert expected[actor + FIELD_10] == RESPAWN_FIELD_10
    assert expected[actor + SPEED] == RESPAWN_SPEED
    assert expected[actor + FIELD_12] == RESPAWN_FIELD_12
    assert expected[actor + FIELD_30] == RESPAWN_FIELD_30
    assert actor + FIELD_31 not in expected, (
        "only WB_ACTOR_FIELD_30 is written here — the spawn clears the PAIR, this does not")


# The three flag bits, over seeds that make each one a change in one direction or the other: the two
# `bset`s must not clear their neighbours and the `bclr` must not set any.
RESPAWN_FLAG_SEEDS = (0x00, 0xff, 1 << SUPPORTED_BIT, 0xff ^ ((1 << MOVING_BIT) | (1 << LAUNCHED_BIT)))


@pytest.mark.parametrize("flags", RESPAWN_FLAG_SEEDS, ids=[f"flags_{f:#04x}" for f in
                                                           RESPAWN_FLAG_SEEDS])
def test_the_two_motion_bits_go_up_the_supported_bit_goes_down_and_nothing_else_moves(flags):
    case = f"an entry WB_ACTOR_FLAGS of {flags:#04x}"
    actor, pokes = _defeat_pokes(case, kills=0x0001)
    pokes[actor + ACTOR_FLAGS] = bytes([flags])
    _info, _image, expected = _run_respawn(case, pokes)
    ended = expected[actor + ACTOR_FLAGS]
    assert ended & (1 << MOVING_BIT) and ended & (1 << LAUNCHED_BIT)
    assert not ended & (1 << SUPPORTED_BIT)
    untouched = ~((1 << MOVING_BIT) | (1 << LAUNCHED_BIT) | (1 << SUPPORTED_BIT)) & 0xff
    assert ended & untouched == flags & untouched, f"{case}: a neighbouring bit moved"


def test_the_flag_seed_sweep_makes_each_bit_move_in_both_directions():
    """The guard: a sweep that only ever entered with the two motion bits down would pass a port that
    wrote the whole byte, and one that never entered with the supported bit UP would pass a port that
    dropped the `bclr`."""
    raised = (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
    assert any(seed & raised != raised for seed in RESPAWN_FLAG_SEEDS), "the `bset`s never change"
    assert any(seed & (1 << SUPPORTED_BIT) for seed in RESPAWN_FLAG_SEEDS), "the `bclr` never does"


def test_the_kind_table_is_bounded_by_the_code_pointers_that_follow_it():
    """Nothing in the image declares the table's length; what bounds it is that the FOURTEEN
    longwords at its end are addresses of the code immediately past them, which 16-byte creature
    records are not. Batch 38 named them — they are `pickup_effect_table` — and corrected the count
    this docstring carried, which was never checked against anything. Its 22 rows also all carry a
    type the mask a draw applies could never produce."""
    end = KIND_TABLE + KIND_TABLE_ROWS * KIND_RECORD_BYTES
    following = _u32(harness.BASE_IMAGE, end)
    assert end < following < harness.IMAGE_SIZE, (
        f"the longword at the table's end is {following:#x}, not the code pointer this extent "
        f"rests on")
    types = [u16(harness.BASE_IMAGE, KIND_TABLE + row * KIND_RECORD_BYTES + KIND_TYPE)
             for row in range(KIND_TABLE_ROWS)]
    assert types[:-1] == [TYPE_UNSCORED] * (KIND_TABLE_ROWS - 1), (
        f"every row but the last must carry WB_ACTOR_TYPE_UNSCORED — the rows are {types} — which "
        f"is what makes a respawned slot pay no score the next time it dies")
    assert types[-1] == KIND_TABLE_LAST_TYPE, (
        f"the last row's type is {types[-1]:#06x}, not the one value that is not $26")


# The entry d2 this routine does nothing with itself and hands STRAIGHT to the draw, whose `add.l`
# folds its high half into a table index (test_rng.py owns that half). $6bb8 can only ever arrive here
# with the half zeroed — its `moveq #0,d2` runs on the one arm that branches here — so a case is what
# says the value is FORWARDED rather than replaced by a 0.
RESPAWN_ENTRY_D2_HIGH = 0x00010000


# ...and BOTH arms have to say so: they are two `bsr`s to two routines, so a case on one of them is
# silent about the other. (A mutant that replaced only the 8-wide arm's d2 with a 0 survived a sweep
# that had only the 32-wide case.)
ENTRY_D2_ARM_CASES = ((0x0001, DRAW32), (KILL_RESPAWN_LIMIT, DRAW8))


@pytest.mark.parametrize("kills,draw", ENTRY_D2_ARM_CASES,
                         ids=[c[1].short for c in ENTRY_D2_ARM_CASES])
def test_the_entry_d2_is_handed_to_the_draw_rather_than_replaced(kills, draw):
    case = (f"an entry d2 of {RESPAWN_ENTRY_D2_HIGH:#010x} on the {draw.short} arm, whose high half "
            f"moves that draw's read")
    actor, pokes = _defeat_pokes(case, kills=kills)
    _info, image, expected = _run_respawn(case, pokes, entry_d2=RESPAWN_ENTRY_D2_HIGH)
    moved, _writes = model_stage_kind(draw, image, RESPAWN_ENTRY_D2_HIGH)
    unmoved, _writes = model_stage_kind(draw, image, RESPAWN_ENTRY_D2)
    assert moved != unmoved, (
        f"both entry halves draw kind {moved} from {draw.name}'s table, so this case is silent "
        f"about what is forwarded")
    assert expected[actor + KIND] == moved


def test_the_defeat_reaches_this_routine_with_d2s_high_half_already_zeroed():
    """WHY the sweep's `hand it a d2 of 0` mutant is equivalent rather than a hole: $6bb8's score arm
    — the only one that branches here — opens with `moveq #0,d2`, which clears the WHOLE register,
    and every write to d2 after it is a `.w`. So the half that reaches the draw is zero however the
    scaled type below it is spelt, and no case can tell `index` from `0` at that call."""
    body = ENTRY_BYTES["actor_defeat_and_score"]
    entry = leaf.entry_of("actor_defeat_and_score")
    clear = body.index(moveq_0_dn(D2))
    scale = body.index(lsl_w_imm_dn(SCORE_SHIFT, D2))
    assert clear < scale < DEFEAT_TRANSFER - entry, (
        "the `moveq #0,d2` must precede the `lsl.w #2,d2`, which must precede the `ble.w`")
    assert body.count(moveq_0_dn(D2)) == 1 and body.count(lsl_w_imm_dn(SCORE_SHIFT, D2)) == 1, (
        "a second writer of d2 in this body would break the argument")
