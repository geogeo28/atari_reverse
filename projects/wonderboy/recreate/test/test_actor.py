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
from leaf import (RTS, backward_branch, branch, bsr_w, case_salt, keyed_block, lea_abs_l, lea_d16,
                  longword, merge_bands, move_w_imm_dn, opcode, program_writes, word)
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

WORD_LEN = 2
LONGWORD_LEN = 4
TABLE_BYTES = SCREEN_RECORD_COUNT * RECORD_BYTES

# The routines are straight-line bar one loop of nineteen records; the cap is that loop's own
# geometry with room for the entry and the tail, so a case that ran away fails loudly.
LIST_INSN_CAP = 64 * SCREEN_RECORD_COUNT

# --- register numbers, and the opcodes only this battery spells -----------------------------------
A0, A1 = 0, 1
D0, D1, D2 = 0, 1, 2

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


def tst_w_abs_w(addr):
    return opcode(0x4a78) + word(addr)


def jsr_abs_w(addr):
    return opcode(0x4eb8) + word(addr)


def movea_l_an_an(destination, source):
    return opcode(0x2048 | (destination << 9) | source)


def movea_l_abs_l(reg, addr):
    return opcode(0x2079 | (reg << 9)) + longword(addr)


def move_w_abs_l_dn(reg, addr):
    return opcode(0x3039 | (reg << 9)) + longword(addr)


def move_w_ind_dn(reg, base, displacement=0):
    """`move.w (An),Dn` and its `d16(An)` form — the original uses both."""
    if displacement == 0:
        return opcode(0x3010 | (reg << 9) | base)
    return opcode(0x3028 | (reg << 9) | base) + word(displacement)


def move_w_dn_postinc(reg, destination):
    return opcode(0x30c0 | (destination << 9) | reg)


def move_w_imm_ind(reg, value):
    return opcode(0x30bc | (reg << 9)) + word(value)


def move_w_d16_ind(source, displacement, destination):
    """`move.w d16(As),(Ad)` — the projection's sprite arm."""
    return opcode(0x3080 | (destination << 9) | 0x28 | source) + word(displacement)


def move_l_imm_abs_l(value, addr):
    return opcode(0x23fc) + longword(value) + longword(addr)


def subi_w_dn(reg, value):
    return opcode(0x0440 | reg) + word(value)


def sub_w_dn_dn(destination, source):
    return opcode(0x9040 | (destination << 9) | source)


def add_w_dn_dn(destination, source):
    return opcode(0xd040 | (destination << 9) | source)


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


ENTRY_BYTES = {
    "followed_actor_record": _followed_record_entry(),
    "actor_set_side_flag": _side_flag_entry(),
    "actor_followed_x_within": _within_entry(),
    "project_followed_actor": _project_followed_entry(),
    "project_actor_list": _project_list_entry(),
}
RECONSTRUCTED_ROUTINES = 5


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


def _u16(image, addr):
    return int.from_bytes(bytes(image[addr:addr + WORD_LEN]), "big")


def _s16(value):
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def _put_word(out, addr, value):
    for offset, byte in enumerate(word(value)):
        out[addr + offset] = byte


def _put_long(out, addr, value):
    for offset, byte in enumerate(longword(value)):
        out[addr + offset] = byte


def _model_projection(image, record, screen):
    """One actor record into one screen record: {address: byte}."""
    out = {}
    scroll_x = _u16(image, POS_X)
    scroll_y = _u16(image, POS_Y)
    _put_word(out, screen + SCREEN_X,
              _u16(image, record + ACTOR_X) - SCREEN_X_BIAS - scroll_x)
    _put_word(out, screen + SCREEN_Y,
              _u16(image, record + ACTOR_Y) - SCREEN_Y_BIAS - scroll_y)
    flickering = (image[record + ACTOR_FLAGS] & (1 << FLICKER_BIT)) and _u16(image, FRAME_TOGGLE)
    _put_word(out, screen + SCREEN_SPRITE,
              SPRITE_HIDDEN if flickering else _u16(image, record + ACTOR_SPRITE))
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

    raised = _s16(actor_x) > _s16(followed_x)
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

    here, followed = _s16(actor_x), _s16(followed_x)
    if followed > here:
        outside = followed > _s16(here + reach)
    else:
        outside = _s16(followed + reach) < here
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
