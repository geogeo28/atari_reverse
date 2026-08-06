"""Differential test for the scene tier — `scene_run_frame` ($dbc0) and `scene_spend_visit_budget`
($de80), src/scene.c.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image and
requires the two to agree byte for byte, with the original's write set bounded by what the case says
it may touch. Two things make this battery different from the leaf ones under it.

THE ROUTINE HAS A BOUNDARY. Four of $dbc0's exits transfer to `$dfbe` and one of $de80's to `$1ab4`,
and both of those end in `jsr stage_load_window` — unverifiable here, because its palette write
lands off the mapped image where the oracle silently drops it, so a reconstruction that skipped it
would come back GREEN. The C therefore RETURNS which tail it reached, and a case that expects a tail
runs the oracle with the kit's `stop_pc` set to that tail's address, which diffs the whole prefix at
the instant control arrives there. That the tail really was taken is not inferred from the C: every
such case names the TRANSFER INSTRUCTION it expects to leave through and requires the oracle's
executed-PC coverage to hold it (`leaf.run_reaching`), which distinguishes the two stops a checkpointed
run can make and says which transfer fired. The transfer instructions themselves are pinned by their
bytes at their own addresses, so a checkpoint that stopped somewhere else would fail there.

EVERYTHING IT READS IS SEEDED. The scene descriptor table ($21828) and the shop records ($21a28..)
lie past the program and are loaded from disk — the image ships zeros for the first and nothing at
all for the second — so no case can be built from the game's own data and all of it is seeded,
address-keyed, the way test_actor.py's tables are. What IS the game's own data, and pinned as such:
the 23 effect handlers the purchase arm dispatches to, the eight entries of the exit-action table,
and the eight speech scripts.

KNOWINGLY NOT PINNED
  * anything past a boundary. `$dfbe` and `$1ab4` are not reconstructed, so what a scene does on the
    way out — the exit action it dispatches, the stage reload — is outside this file entirely.
  * an effect index outside 0..22. The original `jsr`s through a longword outside the table; the C
    refuses, the way src/blit.c's sprite dispatch refuses a width code past its own table, and
    `test_the_battery_refuses_an_index_outside_the_table` states that refusal rather than hiding it.
  * the three descriptor words the farewell arm loads and discards. No exit can observe a register
    the next instruction overwrites, so no case can hold them; ../names.txt records them.
  * what a shop SELLS. The effect a purchase runs is seeded here, not read off shipped data.
"""
import ctypes
from typing import NamedTuple

import pytest

import harness
import leaf
import emu
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, assert_entry_is, branch_w_to, bsr_w, case_salt,
                  cmpi_w_abs_l, cmpi_w_d16, keyed_block, longword, merge_bands, movea_l_abs_l,
                  opcode, program_writes, run_reaching, s16, sub_w_dn_d16, tst_w_abs_w, word)
from layout import wb

# --- the exits, from include/scene.h -------------------------------------------------------------
EXIT_RETURN = wb("SCENE_EXIT_RETURN")
EXIT_RELOAD = wb("SCENE_EXIT_RELOAD")
EXIT_STAGE_RESET = wb("SCENE_EXIT_STAGE_RESET")

# --- the image's own layout, from include/wonderboy.h --------------------------------------------
FLAG_A30 = wb("STATE_FLAG_A30")
FLAG_A32 = wb("STATE_FLAG_A32")
DESCRIPTOR_PTR = wb("RECORD_PTR_10420")
SCENE_KIND = wb("SCENE_KIND")
KIND_SPEECH = wb("SCENE_KIND_SPEECH")
KIND_SHOP = wb("SCENE_KIND_SHOP")
KIND_BOSS = wb("SCENE_KIND_BOSS_DEFEAT")
SCENE_VARIANT = wb("SCENE_VARIANT")
EXIT_ACTION_TABLE = wb("SCENE_EXIT_ACTION_TABLE")
EXIT_ACTION_COUNT = wb("SCENE_EXIT_ACTION_COUNT")

SCRIPT_CURSOR = wb("SPEECH_SCRIPT_CURSOR")
SCRIPT_TABLE = wb("SPEECH_SCRIPT_TABLE")
SCRIPT_COUNT = wb("SPEECH_SCRIPT_COUNT")
SCRIPTS = wb("SPEECH_SCRIPTS")
SPEECH_LIFETIME = wb("SPEECH_LIFETIME")

SHOP_RECORD_PTR = wb("SHOP_RECORD_PTR")
SHOP_RECORD_TABLE = wb("SHOP_RECORD_TABLE")
SHOP_RECORD_COUNT = wb("SHOP_RECORD_COUNT")
SHOP_RECORD_BYTES = wb("SHOP_RECORD_BYTES")
ITEM1_MSG_FIRST = wb("SHOP_ITEM1_MSG_FIRST")
ITEM1_MSG_REPEAT = wb("SHOP_ITEM1_MSG_REPEAT")
ITEM2_MSG_FIRST = wb("SHOP_ITEM2_MSG_FIRST")
ITEM2_MSG_REPEAT = wb("SHOP_ITEM2_MSG_REPEAT")
GREET_MSG_FIRST = wb("SHOP_GREET_MSG_FIRST")
GREET_MSG_SECOND = wb("SHOP_GREET_MSG_SECOND")
GREET_MSG_LATER = wb("SHOP_GREET_MSG_LATER")
VISIT_BUDGET = wb("SHOP_VISIT_BUDGET")
ITEM1_COUNT = wb("SHOP_ITEM1_COUNT")
ITEM2_COUNT = wb("SHOP_ITEM2_COUNT")
GREET_COUNT = wb("SHOP_GREET_COUNT")
LEAVE_CHARGED = wb("SHOP_LEAVE_CHARGED")
FAREWELL_COUNT = wb("SHOP_FAREWELL_COUNT")
ITEM1_PRICE = wb("SHOP_ITEM1_PRICE")
ITEM2_PRICE = wb("SHOP_ITEM2_PRICE")
ITEM1_EFFECT = wb("SHOP_ITEM1_EFFECT")
ITEM2_EFFECT = wb("SHOP_ITEM2_EFFECT")
MESSAGE_COST = wb("SHOP_MESSAGE_COST")
PURCHASE_COST = wb("SHOP_PURCHASE_COST")
FAREWELL_ID_FIRST = wb("SHOP_FAREWELL_ID_FIRST")
FAREWELL_ID_REPEAT = wb("SHOP_FAREWELL_ID_REPEAT")

MESSAGE_PENDING = wb("SCENE_MESSAGE_PENDING")
MESSAGE_PENDING_SET = wb("SCENE_MESSAGE_PENDING_SET")
SHOP_REQUEST = wb("SHOP_REQUEST")
REQUEST_ITEM1 = wb("SHOP_REQUEST_ITEM1")
REQUEST_ITEM2 = wb("SHOP_REQUEST_ITEM2")
REQUEST_FAREWELL = wb("SHOP_REQUEST_FAREWELL")
ACK_WAIT = wb("SCENE_ACK_WAIT")
GREET_COUNTDOWN = wb("SHOP_GREET_COUNTDOWN")
MARKER_CELL_PTR = wb("SCENE_MARKER_CELL_PTR")
SCENE_EXIT_REQUEST = wb("SCENE_EXIT_REQUEST")

BOSS_DEFEAT_FLAG = wb("BOSS_DEFEAT_FLAG")
BOSS_PARAMS = wb("BOSS_FRAGMENT_PARAMS")
BOSS_PARAM_LEN = wb("BOSS_FRAGMENT_PARAM_LEN")
BOSS_SLOTS = wb("BOSS_FRAGMENT_SLOTS")
BOSS_COUNT = wb("BOSS_FRAGMENT_COUNT")
BOSS_HEAD_SLOTS = wb("BOSS_HEAD_SLOT_COUNT")
BOSS_ORIGIN = wb("BOSS_FRAGMENT_ORIGIN")
BOSS_TYPE_1 = wb("BOSS_FRAGMENT_TYPE_1")
BOSS_TYPE_2 = wb("BOSS_FRAGMENT_TYPE_2")
BOSS_SIZE = wb("BOSS_FRAGMENT_SIZE")
BOSS_FIELD_12 = wb("BOSS_FRAGMENT_FIELD_12")
BOSS_FIELD_30 = wb("BOSS_FRAGMENT_FIELD_30")
BOSS_MIRROR_AT = wb("BOSS_FRAGMENT_MIRROR_AT")

TABLE_A32 = wb("ACTOR_TABLE_A32")
RECORD_BYTES = wb("ACTOR_RECORD_BYTES")
FREE_MARKER = wb("ACTOR_FREE_MARKER")
ACTOR_X = wb("ACTOR_X")
ACTOR_TYPE = wb("ACTOR_TYPE")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
ACTOR_FIELD_10 = wb("ACTOR_FIELD_10")
ACTOR_SPEED = wb("ACTOR_SPEED")
ACTOR_FIELD_12 = wb("ACTOR_FIELD_12")
ACTOR_HALF_WIDTH = wb("ACTOR_HALF_WIDTH")
ACTOR_FIELD_30 = wb("ACTOR_FIELD_30")
ACTOR_FIELD_31 = wb("ACTOR_FIELD_31")
FLAG_MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
FLAG_LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
FLAG_SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
FLAG_SIDE_BIT = wb("ACTOR_FLAG_SIDE_BIT")

EFFECT_TABLE = wb("EFFECT_HANDLER_TABLE")
EFFECT_COUNT = wb("EFFECT_HANDLER_COUNT")
EFFECT_SHIFT = wb("EFFECT_HANDLER_SHIFT")

TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_BOX_ACTIVE = wb("TEXT_BOX_ACTIVE")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")
BCD_COUNTER = wb("BCD_COUNTER")
BCD_COUNTER_LEN = wb("BCD_COUNTER_LEN")
BCD_ADDEND = wb("BCD_ADDEND")
HUD_SLOT_BBC4 = wb("HUD_SLOT_BBC4")

VECTOR_LINE_A = wb("VECTOR_LINE_A")
VECTOR_LINE_F = wb("VECTOR_LINE_F")
VECTOR_ARM = wb("VECTOR_ARM_SELECTOR")

JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")
JOY1_FIRE = 0x80                  # the edge byte's sign bit — what `tst.b d0 / bpl` reads
JOY1_NOT_FIRE = 0x01              # any other bit, for the arm that tests the WHOLE byte

MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
MAP_CELL_BIAS = wb("STAMP_CELL_BIAS")

# --- addresses this battery seeds ----------------------------------------------------------------
# The descriptor is slot 0 of the game's own scene_descriptor_table and the shop record is entry 0
# of its own table; both are real addresses whose CONTENTS the .PRG does not ship, which is exactly
# why they are seeded. The marker cell and the record-list write pointer are aimed into the free
# space above the collision map, well inside the image, so no run reaches the unmapped territory
# src/effects.c's comment registers.
DESCRIPTOR = 0x21828
SHOP_RECORD = 0x21a28
MARKER_CELL = 0x22200
RECORD_WRITE_TARGET = 0x23000
MAP_CELL_INDEX = 0x40             # descriptor word 24: which cell map_stamp_block stamps
MAP_STRIDE = 0x50
MAP_BAND_LEN = 0x200              # the window of collision map each case seeds and allows
DESCRIPTOR_MAP_CELL = wb("RECORD_10420_CELL")
EFFECT_RECORD_WRITE_PTR = wb("EFFECT_RECORD_WRITE_PTR")
EFFECT_RECORD_PTR_LEN = wb("EFFECT_RECORD_PTR_LEN")
EFFECT_RECORD_LEN = wb("EFFECT_RECORD_LEN")
# What the two fixed message destinations hold BEFORE the call. Neither value is one any case
# expects, which is what makes a candidate that skipped the store fail the plain diff — the
# substitute for the attribution pass `run_frame` explains it cannot use.
# A push handler leaves a1 on the record it just pushed, so the spend two instructions later lands
# one record's worth past the write pointer, at that record's own WB_SHOP_VISIT_BUDGET offset.
MISAIMED_BUDGET = RECORD_WRITE_TARGET + EFFECT_RECORD_LEN + VISIT_BUDGET
SEED_TEXT_REQUEST = 0xa5
SEED_TEXT_LIFETIME = 0x5a5a

# --- instruction caps, from the arms' own geometry -----------------------------------------------
# The gate is four instructions and a branch; the speech arm adds joy1_newly_pressed's five and four
# stores; a shop arm adds the request ladder, the message post and $de80, and a PURCHASE adds
# bcd_sub_counter_bd6e's packed-BCD loop, one effect handler and map_stamp_block's twenty-five. The
# boss arm is the outlier: ten freed records plus eight fragments of seventeen stores each.
GATE_CAP = 16
SPEECH_CAP = 32
SHOP_CAP = 160
BOSS_CAP = 288

# --- the tails the reconstruction does not follow ------------------------------------------------
RELOAD_TAIL = 0xdfbe              # scene_exit_and_reload
STAGE_RESET_TAIL = 0x1ab4
STOP_PC_FOR = {EXIT_RELOAD: RELOAD_TAIL, EXIT_STAGE_RESET: STAGE_RESET_TAIL}

# ...and the two arms the a30 half's kind ladder branches to, which are targets rather than tails.
SPEECH_ARM = 0xdc00
SHOP_ARM = 0xdc2a


# --- the encodings this battery pins its entries with --------------------------------------------
# Only the ones no other battery spells; the shared ones come from leaf.py above.
BMI_W, BEQ_W, BNE_W, BRA_W, BGT_W = 0x6b00, 0x6700, 0x6600, 0x6000, 0x6e00


def jmp_abs_w(addr):
    """`jmp <abs>.w` — $de80's tail into $1ab4, and the only jump in either routine."""
    return opcode(0x4ef8) + word(addr)


A0, A1 = 0, 1
D0 = 0

# Every pinned instruction, by the address it sits at. A wrong address, a wrong operand or a wrong
# branch distance fails here rather than inside a case that then blames its own seeding.
ENTRY_BYTES = {
    # $dbc0: the two mode gates and the `rts` between them.
    "scene_run_frame": (0xdbc0, tst_w_abs_w(FLAG_A30) + branch_w_to(BMI_W, 0xdbc4, 0xdbd2)
                        + tst_w_abs_w(FLAG_A32) + branch_w_to(BMI_W, 0xdbcc, 0xdbee) + RTS),
    # $dbd2..$dbec: the a30 half's whole kind ladder, and the `rts` that ENDS it. Two tests and no
    # third, then a return — so a descriptor naming kind 4 with the a30 flag down does nothing at
    # all, and a port that fell through into the a32 half instead would run the boss arm.
    "kind ladder": (0xdbd2, movea_l_abs_l(A0, DESCRIPTOR_PTR)
                    + cmpi_w_d16(A0, KIND_SPEECH, SCENE_KIND)
                    + branch_w_to(BEQ_W, 0xdbde, SPEECH_ARM)
                    + cmpi_w_d16(A0, KIND_SHOP, SCENE_KIND)
                    + branch_w_to(BEQ_W, 0xdbe8, SHOP_ARM) + RTS),
    # $de80: the word spend and the borrow test.
    "scene_spend_visit_budget": (0xde80, sub_w_dn_d16(D0, A1, VISIT_BUDGET)
                                 + branch_w_to(BMI_W, 0xde84, 0xde8a) + RTS),
    # The four transfers into $dfbe...
    "speech terminator": (0xdc12, branch_w_to(BMI_W, 0xdc12, RELOAD_TAIL)),
    "leave uncharged": (0xdc52, branch_w_to(BEQ_W, 0xdc52, RELOAD_TAIL)),
    "leave charged": (0xdc5e, branch_w_to(BRA_W, 0xdc5e, RELOAD_TAIL)),
    "boss exit": (0xdf98, bsr_w(0xdf98, RELOAD_TAIL) + RTS),
    # ...and the one into $1ab4.
    "budget exhausted": (0xdeb0, jmp_abs_w(STAGE_RESET_TAIL)),
    # The shipped slip, and the sibling test each half of it was meant to be.
    "farewell count": (0xdcba, cmpi_w_d16(A1, 0, FAREWELL_COUNT)),
    "farewell slip": (0xdcd4, cmpi_w_abs_l(VECTOR_ARM, VECTOR_LINE_F)),
    "greet count": (0xdd2a, cmpi_w_d16(A1, 0, GREET_COUNT)),
    "greet slip": (0xdd42, cmpi_w_abs_l(VECTOR_ARM, VECTOR_LINE_A)),
    # The two dispatches, whose whole seven-instruction shape is the same bar the field.
    "item 1 dispatch": (0xddea, opcode(0x7000) + leaf.move_w_ind_dn(D0, A1, ITEM1_EFFECT)
                        + leaf.lsl_w_imm_dn(EFFECT_SHIFT, D0) + leaf.lea_abs_l(A0, EFFECT_TABLE)
                        + leaf.lea_indexed(A0, D0) + opcode(0x2050) + opcode(0x4e90)),
    "item 2 dispatch": (0xde60, opcode(0x7000) + leaf.move_w_ind_dn(D0, A1, ITEM2_EFFECT)
                        + leaf.lsl_w_imm_dn(EFFECT_SHIFT, D0) + leaf.lea_abs_l(A0, EFFECT_TABLE)
                        + leaf.lea_indexed(A0, D0) + opcode(0x2050) + opcode(0x4e90)),
    # The greeting's countdown, which is a memory `subq` and not a register one.
    "greet countdown": (0xdd12, leaf.subq_w_abs_l(1, GREET_COUNTDOWN)
                        + branch_w_to(BNE_W, 0xdd18, 0xdd7a)),
    # The price compare: a SIGNED word compare against the packed-BCD purse.
    "item 1 price": (0xdda0, leaf.move_w_ind_dn(D0, A1, ITEM1_PRICE) + opcode(0xb079)
                     + longword(BCD_COUNTER) + branch_w_to(BGT_W, 0xddaa, 0xdd12)),
    # The two `bsr $de80` amounts, which are what "a message costs 2 and a purchase 3" is read off.
    "message cost": (0xdd72, leaf.move_w_imm_dn(D0, MESSAGE_COST) + bsr_w(0xdd76, 0xde80)),
    "purchase cost": (0xde00, leaf.move_w_imm_dn(D0, PURCHASE_COST) + bsr_w(0xde04, 0xde80)),
}
RECORDED_PINS = 18


def transfer_at(label):
    """The address of one pinned transfer instruction — the witness a checkpointed case names.

    Taken out of the table above rather than restated, so the instruction a case says took it to a
    tail is the same one `test_the_instruction_at_each_pinned_address_is_the_one_reconstructed`
    compares against the image.
    """
    return ENTRY_BYTES[label][0]


# --- seeding -------------------------------------------------------------------------------------
# One address-keyed band per region the routine can read or write, with a margin around each: the
# descriptor, the shop record, the actor slots the boss arm fills, the collision map around both the
# stamped block and the marker cell, and the record list the effect handlers push onto. Keyed on the
# ADDRESS so that a walk with the wrong stride lands on bytes that are wrong for where they were
# written rather than on zeros.
SEED_MARGIN = RECORD_BYTES
SEED_BANDS = (
    (DESCRIPTOR - SEED_MARGIN, 3 * RECORD_BYTES),
    (SHOP_RECORD - SEED_MARGIN, SHOP_RECORD_BYTES + 2 * SEED_MARGIN),
    (TABLE_A32 - SEED_MARGIN, (BOSS_SLOTS - TABLE_A32) + BOSS_COUNT * RECORD_BYTES
     + 2 * SEED_MARGIN),
    # PAST the stride word, which is a poke of its own below: a band keyed at the same address as a
    # poke is REPLACED by it (see `_poke`), and this one was — the map read as zeros for a batch.
    (MAP_ROW_STRIDE + WORD_BYTES, MAP_BAND_LEN - WORD_BYTES),
    (MARKER_CELL - SEED_MARGIN, 2 * SEED_MARGIN),
    (RECORD_WRITE_TARGET - SEED_MARGIN, 4 * SEED_MARGIN),
)


def _poke(out, addr, data, case):
    """One poke into the dict `harness.make_image` will apply, refusing to REPLACE what is keyed
    there.

    make_image writes each key's own bytes, so a poke whose address is a seeded band's START does
    not overwrite the band's first bytes — it replaces the whole band with its own two or four.
    That is how the 0x200-byte collision-map band above became just its stride word, leaving every
    cell the stamp writes over seeded with the image's zeros. Refuse the collision instead.
    """
    assert addr not in out, (
        f"{case}: the poke at {addr:#x} would replace the {len(out[addr])} bytes already keyed "
        f"there — key it past them, or fold it into the block, so that both survive")
    out[addr] = data


def pokes(case, words=(), longwords=(), bytes_=()):
    """The seeded bands plus the state a case names. `words`/`longwords`/`bytes_` are (addr, value)
    pairs, since every address here is a number rather than a keyword name."""
    salt = case_salt(case)
    out = {lo: keyed_block(lo, length, salt) for lo, length in SEED_BANDS}
    fixed = ((MAP_ROW_STRIDE, word(MAP_STRIDE)),
             (DESCRIPTOR_PTR, longword(DESCRIPTOR)),
             (SHOP_RECORD_PTR, longword(SHOP_RECORD)),
             (MARKER_CELL_PTR, longword(MARKER_CELL)),
             (EFFECT_RECORD_WRITE_PTR, longword(RECORD_WRITE_TARGET)),
             (DESCRIPTOR + DESCRIPTOR_MAP_CELL, word(MAP_CELL_INDEX)),
             (TEXT_REQUEST, bytes([SEED_TEXT_REQUEST])),
             (TEXT_LIFETIME_REQUEST, word(SEED_TEXT_LIFETIME)))
    for addr, data in fixed:
        _poke(out, addr, data, case)
    for addr, value in words:
        _poke(out, addr, word(value), case)
    for addr, value in longwords:
        _poke(out, addr, longword(value), case)
    for addr, value in bytes_:
        _poke(out, addr, bytes([value & 0xff]), case)
    return out


def joystick(edge):
    """The two IKBD bytes that make joy1_newly_pressed return `edge` — the pipeline's own inputs,
    since nothing here may hand the routine a register it does not read."""
    return ((JOY1_PREV, 0), (JOY1_CURRENT, edge))


# The whole band any arm may write, per region. Stated once: a case that named only the words it
# expects would have to restate the effect handlers' targets as well, and the point of `allowed` is
# to catch a write somewhere else entirely.
STATE_BAND = merge_bands(
    list(range(MESSAGE_PENDING, MARKER_CELL_PTR + LONGWORD_BYTES))
    + list(range(TEXT_REQUEST, TEXT_LIFETIME_REQUEST + WORD_BYTES))
    + list(range(SCRIPT_CURSOR, SCRIPT_CURSOR + LONGWORD_BYTES))
    + list(range(SCENE_EXIT_REQUEST, SCENE_EXIT_REQUEST + WORD_BYTES))
    + list(range(BOSS_DEFEAT_FLAG, BOSS_DEFEAT_FLAG + WORD_BYTES))
    + list(range(BCD_COUNTER, BCD_COUNTER + BCD_COUNTER_LEN))
    + list(range(BCD_ADDEND, BCD_ADDEND + LONGWORD_BYTES)))
RECORD_BAND = [(SHOP_RECORD, SHOP_RECORD_BYTES)]
MAP_BAND = [(MAP_ROW_STRIDE, MAP_BAND_LEN), (MARKER_CELL - 1, 3)]
SLOT_BAND = [(TABLE_A32, (BOSS_SLOTS - TABLE_A32) + BOSS_COUNT * RECORD_BYTES)]
# The effect handlers' own destinations: every global include/effects.h writes, plus the record the
# four push handlers store through the seeded write pointer.
EFFECT_BAND = merge_bands(
    list(range(wb("HUD_SLOT_BBBE"), wb("HUD_SLOT_BBC8") + WORD_BYTES))
    + list(range(wb("HUD_METER_VALUE"), wb("HUD_METER_VALUE") + WORD_BYTES))
    + list(range(wb("EFFECT_STATE_BD66"), wb("EFFECT_STATE_BD6A") + WORD_BYTES))
    + list(range(wb("EFFECT_STATE_21E4"), wb("EFFECT_STATE_21E4") + WORD_BYTES))
    + list(range(wb("STATE_WORD_6F9C"), wb("STATE_WORD_6F9C") + WORD_BYTES))
    + list(range(EFFECT_RECORD_WRITE_PTR, EFFECT_RECORD_WRITE_PTR + EFFECT_RECORD_PTR_LEN))
    + list(range(RECORD_WRITE_TARGET, RECORD_WRITE_TARGET + 2 * EFFECT_RECORD_LEN))
    # ...and the word a MIS-AIMED visit spend lands on: a push handler hands a1 back pointing at the
    # record it just pushed, so the `sub.w d0,32(a1)` that follows writes 32 bytes into the list.
    + list(range(MISAIMED_BUDGET, MISAIMED_BUDGET + WORD_BYTES)))
EVERYTHING = STATE_BAND + RECORD_BAND + MAP_BAND + SLOT_BAND + EFFECT_BAND


# --- glue ----------------------------------------------------------------------------------------
_RUN_FRAME = leaf.image_glue("scene_run_frame", ctypes.c_uint32)
_SPEND = leaf.register_glue("scene_spend_visit_budget", [ctypes.c_uint32] * 2, ctypes.c_uint32)


def run_frame(case, seeds, expected_exit, allowed=None, cap=SHOP_CAP, via=None):
    """One `scene_run_frame` case: the differential, the exit the C reports, and — for a tail — the
    checkpoint and the witness that ``via`` (a label in ENTRY_BYTES) is the transfer that took it.

    THE ATTRIBUTION (POISON) PASS IS OFF FOR THIS WHOLE ROUTINE, and this is where that is argued.
    It re-runs both cores on an image whose oracle-written bytes are INVERTED, which works for a
    leaf whose outputs it never reads back. Every output here steers the routine's own next branch:
    the visit budget by its SIGN (`bmi`), the script cursor as an ADDRESS the next run reads a
    branch byte through, the two shop counts as first-time/repeat selects, the mode and pending
    words as gates, and effect_record_write_ptr as an address a push handler stores THROUGH — off
    the mapped image once inverted, the divergence class src/effects.c registers. So a poisoned
    re-run does not re-run this function; it runs a different one, usually into the tail the
    checkpoint is not set for.

    WHAT STANDS IN FOR IT, since "the candidate matched a byte it never wrote" is a real hazard:
    `pokes` seeds every fixed destination the routine writes with a value NO case expects
    (SEED_TEXT_REQUEST, SEED_TEXT_LIFETIME), and the record and the actor slots are address-keyed,
    so a candidate that skipped a store leaves the seed and fails the plain diff. Each case then
    also asserts the VALUE at the address out of the oracle's write set — `leaf.read_int` fails
    outright on a byte the original never wrote — and the cases that can state their whole write
    set compare it for equality.
    """
    stop_pc = STOP_PC_FOR.get(expected_exit, 0)
    assert bool(stop_pc) == (via is not None), (
        f"{case}: a case that expects a tail must name the transfer that takes it, and one that "
        f"expects a return must not")
    how = dict(regs={"_pokes": seeds}, max_insns=cap, stop_pc=stop_pc, poison=False)
    bands = allowed if allowed is not None else EVERYTHING
    if via is None:
        info = leaf.run("scene_run_frame", _RUN_FRAME, bands, case, **how)
    else:
        info = run_reaching("scene_run_frame", _RUN_FRAME, bands, case, transfer_at(via), **how)
    assert info["ret"] == expected_exit, (
        f"{case}: the reconstruction reported exit {info['ret']}, not the {expected_exit} this "
        f"case expects")
    return info


# --- the pins ------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", sorted(ENTRY_BYTES))
def test_the_instruction_at_each_pinned_address_is_the_one_reconstructed(label):
    """Each pinned instruction, against the bytes at its own address."""
    addr, expected = ENTRY_BYTES[label]
    actual = bytes(harness.BASE_IMAGE[addr:addr + len(expected)])
    assert actual == expected, (
        f"{label} @ {addr:#x} is {actual.hex()}, not the {expected.hex()} this battery "
        f"reconstructs")


def test_the_two_reconstructed_entries_are_where_names_txt_says():
    """The two `fn` addresses, cross-checked against the pin table — `assert_entry_is` is the same
    check the leaf batteries make, and it is what ties ../names.txt to the bytes."""
    for name in ("scene_run_frame", "scene_spend_visit_budget"):
        addr, expected = ENTRY_BYTES[name]
        assert leaf.entry_of(name) == addr, (
            f"../names.txt puts {name} at {leaf.entry_of(name):#x}, not at this battery's {addr:#x}")
        assert_entry_is(name, expected)


def test_the_pin_table_still_holds_every_instruction_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECORDED_PINS)


# The 23 handlers, in the order src/scene.c's EFFECT_HANDLERS array lists them. Transcribed from
# ../names.txt's `fn` block rather than composed, so the table below and the C are two independent
# statements of the same order.
HANDLER_NAMES = (
    "effect_add4_clamped_b6fa", "effect_add2_clamped_b6fa",
    "effect_set_bd6a_1", "effect_set_bd6a_2", "effect_set_bd6a_3", "effect_set_bd6a_4",
    "effect_set_bbc2_80ff",
    "effect_set_bd66_1", "effect_set_bd66_2", "effect_set_bd66_3", "effect_set_bd66_4",
    "effect_set_bd66_5",
    "effect_set_bbbe_05ff",
    "effect_set_bd68_1", "effect_set_bd68_2", "effect_set_bd68_3",
    "effect_set_bbc0_05ff", "effect_set_bbc6_01ff",
    "effect_push_record_0605", "effect_push_record_0508", "effect_push_record_0705",
    "effect_push_record_0803",
    "effect_restore_b6fa_to_max",
)


@pytest.mark.parametrize("index,name", list(enumerate(HANDLER_NAMES)))
def test_each_effect_table_entry_is_the_handler_names_txt_names(index, name):
    """The shipped table, entry by entry. This is what makes the C's array an ORDER claim about the
    image and not a list of its own."""
    entry = EFFECT_TABLE + index * LONGWORD_BYTES
    held = int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + LONGWORD_BYTES]), "big")
    assert held == leaf.entry_of(name), (
        f"effect_handler_table[{index}] holds {held:#x}, not {name} at {leaf.entry_of(name):#x}")


def test_the_effect_table_is_bounded_by_its_own_first_target():
    """WB_EFFECT_HANDLER_COUNT is not a number this battery chose: the table ends exactly where the
    handler its first entry names begins, which is what makes 23 the whole of it."""
    first = int.from_bytes(bytes(harness.BASE_IMAGE[EFFECT_TABLE:EFFECT_TABLE + LONGWORD_BYTES]),
                           "big")
    assert first == EFFECT_TABLE + EFFECT_COUNT * LONGWORD_BYTES, (
        f"the first handler is at {first:#x}, not at the {EFFECT_COUNT * LONGWORD_BYTES} bytes of "
        f"table this battery reads")
    assert len(HANDLER_NAMES) == EFFECT_COUNT


def test_the_exit_action_table_is_bounded_and_holds_the_six_state_stubs():
    """$dfbe's table — not reconstructed, so this is a READ pinned rather than a port: it is bounded
    the same way the handler table is, entries 2..7 are the effects.h stubs, and entry 1 is the one
    routine nothing has read (which is a third reason $dfbe cannot be ported)."""
    entries = [int.from_bytes(bytes(harness.BASE_IMAGE[EXIT_ACTION_TABLE + i * LONGWORD_BYTES:
                                                      EXIT_ACTION_TABLE + (i + 1) * LONGWORD_BYTES]),
                              "big")
               for i in range(EXIT_ACTION_COUNT)]
    assert entries[0] == EXIT_ACTION_TABLE + EXIT_ACTION_COUNT * LONGWORD_BYTES, (
        f"the table's first target is {entries[0]:#x}, so it is not {EXIT_ACTION_COUNT} entries")
    assert bytes(harness.BASE_IMAGE[entries[0]:entries[0] + len(RTS)]) == RTS, (
        "entry 0's whole body is supposed to be an `rts`")
    stubs = ("set_state_bbc8_1ff", "set_state_bbc8_2ff", "set_state_bbc8_3ff", "set_state_bbc8_4ff",
             "set_state_bbc8_6ff", "set_state_6f9c_ffff")
    assert entries[2:] == [leaf.entry_of(name) for name in stubs]
    assert entries[1] not in [leaf.entry_of(name) for name in stubs]


def test_the_speech_script_table_is_bounded_and_its_scripts_terminate():
    """The eight shipped scripts, which is the one thing about the speech arm that IS game data: the
    pointer block runs up to WB_SPEECH_SCRIPTS and every script ends in a byte with bit 7 set."""
    pointers = [int.from_bytes(bytes(harness.BASE_IMAGE[SCRIPT_TABLE + i * LONGWORD_BYTES:
                                                        SCRIPT_TABLE + (i + 1) * LONGWORD_BYTES]),
                               "big")
                for i in range(SCRIPT_COUNT)]
    assert SCRIPT_TABLE + SCRIPT_COUNT * LONGWORD_BYTES == SCRIPT_CURSOR, (
        "the script table is supposed to end exactly where its cursor is")
    assert pointers[0] == SCRIPTS
    assert pointers == sorted(pointers), "the eight scripts are supposed to run in order"
    for index, start in enumerate(pointers):
        at = start
        while at < start + 0x40 and not harness.BASE_IMAGE[at] & 0x80:
            at += 1
        assert harness.BASE_IMAGE[at] & 0x80, f"script {index} at {start:#x} has no terminator"


def test_the_shop_record_table_is_bounded_and_gives_the_record_its_length():
    """Eight pointers a fixed stride apart, ending exactly where WB_SHOP_RECORD_PTR is — which is
    what WB_SHOP_RECORD_BYTES is read off, and every one of them is past the program."""
    pointers = [int.from_bytes(bytes(harness.BASE_IMAGE[SHOP_RECORD_TABLE + i * LONGWORD_BYTES:
                                                        SHOP_RECORD_TABLE + (i + 1)
                                                        * LONGWORD_BYTES]), "big")
                for i in range(SHOP_RECORD_COUNT)]
    assert SHOP_RECORD_TABLE + SHOP_RECORD_COUNT * LONGWORD_BYTES == SHOP_RECORD_PTR
    assert pointers[0] == SHOP_RECORD
    strides = {later - earlier for earlier, later in zip(pointers, pointers[1:])}
    assert strides == {SHOP_RECORD_BYTES}, f"the eight pointers are {strides} apart, not one stride"
    assert min(pointers) > emu.loader.PROGRAM_END, (
        "the shop records are supposed to lie past the program, which is why nothing about their "
        "contents is shipped and every case here seeds them")


def test_the_boss_fragment_parameters_are_the_symmetric_pairs_the_arm_reads():
    """The sixteen bytes at $dfae, which ARE shipped: four pairs and then the same four backwards,
    ending exactly where scene_exit_and_reload begins."""
    params = bytes(harness.BASE_IMAGE[BOSS_PARAMS:BOSS_PARAMS + BOSS_COUNT * BOSS_PARAM_LEN])
    assert BOSS_PARAMS + BOSS_COUNT * BOSS_PARAM_LEN == RELOAD_TAIL
    pairs = [tuple(params[i:i + BOSS_PARAM_LEN]) for i in range(0, len(params), BOSS_PARAM_LEN)]
    assert pairs[:BOSS_COUNT // 2] == pairs[BOSS_COUNT // 2:][::-1], (
        f"the parameter pairs {pairs} are not mirrored, which is what the side-bit split is for")


# --- the mode gate -------------------------------------------------------------------------------

@pytest.mark.parametrize("a30,a32,kind", [
    (0x0000, 0x0000, KIND_SPEECH),        # neither flag: nothing runs whatever the descriptor says
    (0x0001, 0x7fff, KIND_SHOP),          # positive is not negative — the test is a SIGN one
    (0xffff, 0x0000, 0x0000),             # a30 down, but no kind matches
    (0xffff, 0xffff, 0x0003),             # ...and a30 wins over a32, so kind 3 still does nothing
    (0x0000, 0xffff, KIND_SPEECH),        # a32 down, but only kind 4 is its arm
    (0x0000, 0xffff, KIND_SHOP),
    (0x0000, 0x8000, 0x0005),
])
def test_the_mode_gate_returns_without_writing(a30, a32, kind):
    case = f"gate a30={a30:#06x} a32={a32:#06x} kind={kind}"
    info = run_frame(case, pokes(case, words=((FLAG_A30, a30), (FLAG_A32, a32),
                                              (DESCRIPTOR + SCENE_KIND, kind))),
                     EXIT_RETURN, cap=GATE_CAP)
    assert not program_writes(info), f"{case}: the gate wrote {sorted(program_writes(info))}"


def test_a_zero_a32_is_not_negative_even_with_the_boss_arm_armed():
    """`tst.w $a32.w / bmi` is a SIGN test, and zero is not negative — the one gate case where a
    `>= 0` and a `> 0` reading differ. It needs the boss arm ARMED to be observable at all: with
    the defeat flag down, both readings return having written nothing."""
    case = "gate a32 zero with the boss armed"
    info = run_frame(case, pokes(case, words=((FLAG_A30, 0x0000), (FLAG_A32, 0x0000),
                                              (DESCRIPTOR + SCENE_KIND, KIND_BOSS),
                                              (DESCRIPTOR + SCENE_VARIANT, 1),
                                              (BOSS_DEFEAT_FLAG, 0xffff))),
                     EXIT_RETURN, cap=GATE_CAP)
    assert not program_writes(info), f"{case}: the gate wrote {sorted(program_writes(info))}"


def test_the_a30_ladder_returns_rather_than_falling_into_the_a32_arm():
    """$dbec is an `rts` and the two halves are exclusive, which only a descriptor naming kind 4
    with BOTH flags down can show. The a30 half wins, its ladder tests 1 and 2 and matches neither,
    and the routine returns — while the boss arm the other half would run is ARMED and would write
    eighteen actor records if anything fell through to it."""
    case = "gate a30 wins over an armed kind-4 a32"
    info = run_frame(case, pokes(case, words=((FLAG_A30, 0xffff), (FLAG_A32, 0xffff),
                                              (DESCRIPTOR + SCENE_KIND, KIND_BOSS),
                                              (DESCRIPTOR + SCENE_VARIANT, 1),
                                              (BOSS_DEFEAT_FLAG, 0xffff))),
                     EXIT_RETURN, cap=GATE_CAP)
    assert not program_writes(info), f"{case}: the gate wrote {sorted(program_writes(info))}"


# --- the speech script ---------------------------------------------------------------------------
SPEECH_CURSOR_AT = SCRIPTS + 1        # inside script 0, so the byte under it is shipped data


def speech_pokes(case, edge, script_byte=None):
    words = ((FLAG_A30, 0xffff), (FLAG_A32, 0x0000), (DESCRIPTOR + SCENE_KIND, KIND_SPEECH))
    bytes_ = joystick(edge) + (() if script_byte is None else ((SPEECH_CURSOR_AT, script_byte),))
    return pokes(case, words=words, longwords=((SCRIPT_CURSOR, SPEECH_CURSOR_AT),), bytes_=bytes_)


@pytest.mark.parametrize("edge", [0x00, JOY1_NOT_FIRE, 0x7f])
def test_the_speech_arm_ignores_every_edge_but_fire(edge):
    """`tst.b d0 / bpl` is a SIGN test, so only the joystick byte's top bit advances the script —
    unlike the shop's acknowledge test, which reads the whole byte."""
    case = f"speech edge {edge:#04x}"
    info = run_frame(case, speech_pokes(case, edge), EXIT_RETURN, cap=SPEECH_CAP)
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


@pytest.mark.parametrize("script_byte", [0x01, 0x63, 0x7f])
def test_the_speech_arm_posts_the_byte_under_the_cursor_and_advances(script_byte):
    """The whole arm: the id with a lifetime of ZERO (so the box waits rather than expiring) and the
    cursor one byte on. The lifetime is what separates this post from every shop one."""
    case = f"speech post {script_byte:#04x}"
    info = run_frame(case, speech_pokes(case, JOY1_FIRE, script_byte), EXIT_RETURN, cap=SPEECH_CAP)
    written = program_writes(info)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == script_byte
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, case) == SPEECH_LIFETIME
    assert leaf.read_int(info, SCRIPT_CURSOR, LONGWORD_BYTES, case) == SPEECH_CURSOR_AT + 1
    assert set(written) == set(range(TEXT_REQUEST, TEXT_REQUEST + 1)) | set(
        range(TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_REQUEST + WORD_BYTES)) | set(
        range(SCRIPT_CURSOR, SCRIPT_CURSOR + LONGWORD_BYTES)), (
        f"{case}: it wrote {sorted(hex(a) for a in written)}")


@pytest.mark.parametrize("script_byte", [0x80, 0xff])
def test_a_script_byte_with_its_sign_bit_set_ends_the_scene(script_byte):
    """The terminator is a SIGN test and it is not consumed: the arm transfers to the tail having
    written nothing at all, cursor included."""
    case = f"speech terminator {script_byte:#04x}"
    info = run_frame(case, speech_pokes(case, JOY1_FIRE, script_byte), EXIT_RELOAD, cap=SPEECH_CAP,
                     via="speech terminator")
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


# --- the shop: the two waits ---------------------------------------------------------------------
def shop_pokes(case, words=(), longwords=(), bytes_=()):
    base = ((FLAG_A30, 0xffff), (FLAG_A32, 0x0000), (DESCRIPTOR + SCENE_KIND, KIND_SHOP))
    return pokes(case, words=base + tuple(words), longwords=longwords, bytes_=bytes_)


@pytest.mark.parametrize("edge,box", [(0x00, 0xff), (JOY1_NOT_FIRE, 0x01), (0x7f, 0xff)])
def test_a_pending_message_holds_the_shop_until_fire(edge, box):
    """While scene_message_pending is up, only the FIRE edge lets the player out — and only while a
    box is actually up, which is the second half of the `bpl` / `bne` pair."""
    case = f"pending hold edge={edge:#04x} box={box:#04x}"
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),),
                                      bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                     EXIT_RETURN)
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


@pytest.mark.parametrize("edge,box", [(JOY1_FIRE, 0xff), (0xff, 0x01), (0x00, 0x00)])
def test_a_pending_message_leaves_for_nothing_when_the_record_is_not_charged(edge, box):
    """`tst.w 42(a1) / beq` — a zero WB_SHOP_LEAVE_CHARGED transfers to the tail with no write at
    all, budget included."""
    case = f"leave free edge={edge:#04x} box={box:#04x}"
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                   (SHOP_RECORD + LEAVE_CHARGED, 0)),
                                      bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                     EXIT_RELOAD, via="leave uncharged")
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


@pytest.mark.parametrize("budget", [0x0010, MESSAGE_COST, MESSAGE_COST + 1])
def test_a_charged_leave_spends_the_message_cost_first(budget):
    """The other arm: a nonzero WB_SHOP_LEAVE_CHARGED spends WB_SHOP_MESSAGE_COST and only then
    transfers. Every budget here stays non-negative, so the spend is the only write."""
    case = f"leave charged budget={budget}"
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                   (SHOP_RECORD + LEAVE_CHARGED, 1),
                                                   (SHOP_RECORD + VISIT_BUDGET, budget)),
                                      bytes_=joystick(JOY1_FIRE) + ((TEXT_BOX_ACTIVE, 0xff),)),
                     EXIT_RELOAD, via="leave charged")
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == budget - MESSAGE_COST
    assert set(program_writes(info)) == set(range(SHOP_RECORD + VISIT_BUDGET,
                                                  SHOP_RECORD + VISIT_BUDGET + WORD_BYTES))


@pytest.mark.parametrize("edge,box", [(0x00, 0xff), (0x00, 0x01)])
def test_the_acknowledge_wait_holds_the_shop_while_a_box_is_up(edge, box):
    """scene_ack_wait's test reads the WHOLE edge byte — a zero edge with a box up returns."""
    case = f"ack hold edge={edge:#04x} box={box:#04x}"
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, 0), (ACK_WAIT, 0xffff)),
                                      bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                     EXIT_RETURN)
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


@pytest.mark.parametrize("edge,box", [(JOY1_NOT_FIRE, 0xff), (JOY1_FIRE, 0xff), (0x00, 0x00)])
def test_the_acknowledge_wait_clears_and_the_frame_carries_on(edge, box):
    """ANY edge, or a box already gone, takes the box down and clears the wait — and then the frame
    runs the request rather than returning, which is what the greeting countdown below proves."""
    case = f"ack clear edge={edge:#04x} box={box:#04x}"
    countdown = 0x0040
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, 0), (ACK_WAIT, 0xffff),
                                                   (SHOP_REQUEST, 0),
                                                   (GREET_COUNTDOWN, countdown)),
                                      bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                     EXIT_RETURN)
    assert leaf.read_int(info, ACK_WAIT, WORD_BYTES, case) == 0
    assert leaf.read_int(info, TEXT_BOX_ACTIVE, 1, case) == 0
    assert leaf.read_int(info, GREET_COUNTDOWN, WORD_BYTES, case) == countdown - 1


# --- the greeting --------------------------------------------------------------------------------

@pytest.mark.parametrize("countdown", [0x0002, 0x0040, 0x0000])
def test_the_greeting_counts_down_and_a_zero_word_wraps(countdown):
    """`subq.w #1 / bne` tests the DECREMENTED word, so a countdown seeded 0 wraps to $ffff and the
    greeting is 65536 frames away rather than due now."""
    case = f"greet countdown {countdown:#06x}"
    info = run_frame(case, shop_pokes(case, words=((MESSAGE_PENDING, 0), (ACK_WAIT, 0),
                                                   (SHOP_REQUEST, 0),
                                                   (GREET_COUNTDOWN, countdown))),
                     EXIT_RETURN)
    assert leaf.read_int(info, GREET_COUNTDOWN, WORD_BYTES, case) == (countdown - 1) & 0xffff
    assert set(program_writes(info)) == set(range(GREET_COUNTDOWN, GREET_COUNTDOWN + WORD_BYTES))


# (greet count, the vector-page word, which record field the id comes from)
GREET_ARMS = (
    (0, 0x0000, GREET_MSG_FIRST),
    (0, VECTOR_ARM, GREET_MSG_FIRST),      # the count wins: the vector is not even read
    (1, VECTOR_ARM, GREET_MSG_SECOND),     # the arm the shipped slip makes unreachable on hardware
    (1, 0x0000, GREET_MSG_LATER),
    (7, 0xfc06, GREET_MSG_LATER),          # a realistic Line-A vector high word: never 1
)


@pytest.mark.parametrize("count,vector,field", GREET_ARMS)
def test_the_greeting_posts_the_id_its_three_way_select_names(count, vector, field):
    """All three greeting ids, including the middle arm the `cmpi.w #$1,$28.l` slip made dead on
    hardware — reachable here only by seeding the Line-A vector, which is all the instruction reads.
    """
    case = f"greet count={count} vector={vector:#06x} field={field}"
    ids = {GREET_MSG_FIRST: 0x11, GREET_MSG_SECOND: 0x22, GREET_MSG_LATER: 0x33}
    info = run_frame(case, shop_pokes(
        case,
        words=((MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, 0), (GREET_COUNTDOWN, 1),
               (VECTOR_LINE_A, vector), (SHOP_RECORD + GREET_COUNT, count),
               (SHOP_RECORD + VISIT_BUDGET, 0x40))
        + tuple((SHOP_RECORD + offset, value) for offset, value in ids.items())),
        EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == ids[field]
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, case) == TEXT_LIFETIME_DEFAULT
    assert leaf.read_int(info, MESSAGE_PENDING, WORD_BYTES, case) == MESSAGE_PENDING_SET
    assert leaf.read_int(info, SHOP_RECORD + GREET_COUNT, WORD_BYTES, case) == count + 1
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == 0x40 - MESSAGE_COST


def test_the_posted_greeting_id_is_the_field_word_truncated_to_a_byte():
    """`move.w n(a1),d0 / move.b d0,$c030.l` — the id is a WORD in the record and a BYTE in the
    request, so the field's high half is dropped rather than posted."""
    case = "greet id truncation"
    info = run_frame(case, shop_pokes(case, words=(
        (MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, 0), (GREET_COUNTDOWN, 1),
        (SHOP_RECORD + GREET_COUNT, 0), (SHOP_RECORD + GREET_MSG_FIRST, 0xbe63),
        (SHOP_RECORD + VISIT_BUDGET, 0x40))), EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == 0x63


# --- the farewell --------------------------------------------------------------------------------

@pytest.mark.parametrize("count,vector,expected_id", [
    (0, 0x0000, FAREWELL_ID_FIRST),
    (0, VECTOR_ARM, FAREWELL_ID_FIRST),
    (1, VECTOR_ARM, FAREWELL_ID_REPEAT),   # the middle arm — and it posts the SAME id as the third
    (1, 0x0000, FAREWELL_ID_REPEAT),
    (9, 0xfc12, FAREWELL_ID_REPEAT),
])
def test_the_farewell_posts_one_of_two_hardcoded_ids(count, vector, expected_id):
    """Message 9 " Please come again." the first time and $12 "  Never Come Back!!" afterwards. The
    ids are IMMEDIATES: the three record words the arm loads at 26/28/30 are discarded, which is why
    no seeding of them appears here."""
    case = f"farewell count={count} vector={vector:#06x}"
    info = run_frame(case, shop_pokes(case, words=(
        (MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, REQUEST_FAREWELL),
        (VECTOR_LINE_F, vector), (SHOP_RECORD + FAREWELL_COUNT, count),
        (SHOP_RECORD + VISIT_BUDGET, 0x40))), EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == expected_id
    assert leaf.read_int(info, SHOP_REQUEST, WORD_BYTES, case) == 0
    assert leaf.read_int(info, SHOP_RECORD + FAREWELL_COUNT, WORD_BYTES, case) == count + 1
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == 0x40 - MESSAGE_COST


# --- the request ladder --------------------------------------------------------------------------
class Item(NamedTuple):
    """One of the shop's two items: the request word that asks for it, and the five record fields
    the purchase arm reads for it. The request travels WITH the fields so that a case naming an item
    does not also have to name the word that selects it — the two dispatch sites differ in nothing
    else, and a case that paired them wrongly would seed one item and buy the other."""
    request: int
    price: int
    count: int
    msg_first: int
    msg_repeat: int
    effect: int


ITEM1 = Item(REQUEST_ITEM1, ITEM1_PRICE, ITEM1_COUNT, ITEM1_MSG_FIRST, ITEM1_MSG_REPEAT,
             ITEM1_EFFECT)
ITEM2 = Item(REQUEST_ITEM2, ITEM2_PRICE, ITEM2_COUNT, ITEM2_MSG_FIRST, ITEM2_MSG_REPEAT,
             ITEM2_EFFECT)
FIRST_ID, REPEAT_ID = 0x44, 0x55        # the two ids every purchase case seeds and reads back


def purchase_pokes(case, asked, item, price=0x0010, purse=0x0099, count=0, effect=0,
                   budget=0x40):
    return shop_pokes(case, words=(
        (MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, asked),
        (BCD_COUNTER, purse), (GREET_COUNTDOWN, 0x40),
        (SHOP_RECORD + item.price, price), (SHOP_RECORD + item.count, count),
        (SHOP_RECORD + item.msg_first, FIRST_ID), (SHOP_RECORD + item.msg_repeat, REPEAT_ID),
        (SHOP_RECORD + item.effect, effect), (SHOP_RECORD + VISIT_BUDGET, budget),
        # A push handler aims the spend HERE instead; seeded high so the grid's own cases do not
        # each turn into a borrow. `test_a_push_handler_hands_the_dispatcher_a_moved_a1` is where
        # that hand-back is the point rather than a side effect.
        (MISAIMED_BUDGET, 0x0400)))


@pytest.mark.parametrize("asked,item,label", [
    (ITEM1.request, ITEM1, "item 1"),
    (ITEM2.request, ITEM2, "item 2"),
    (0x0004, ITEM1, "an unlisted request"),      # no third compare: everything else is item 1
    (0xffff, ITEM1, "a negative request"),
])
def test_the_request_ladder_serves_the_item_it_names(asked, item, label):
    case = f"request {asked:#06x} -> {label}"
    info = run_frame(case, purchase_pokes(case, asked, item), EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == FIRST_ID
    assert leaf.read_int(info, SHOP_RECORD + item.count, WORD_BYTES, case) == 1
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, case) == 0x0099 - 0x0010
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == 0x40 - PURCHASE_COST
    assert SHOP_RECORD + item.price not in program_writes(info), (
        f"{case}: the price field is READ, never written")


@pytest.mark.parametrize("item,label", [(ITEM1, "item 1"), (ITEM2, "item 2")])
@pytest.mark.parametrize("count,expected_id", [(0, FIRST_ID), (1, REPEAT_ID),
                                               (0x1234, REPEAT_ID)])
def test_a_purchase_posts_its_first_message_once_and_its_repeat_afterwards(item, label, count,
                                                                          expected_id):
    case = f"{label} purchase count={count:#06x}"
    info = run_frame(case, purchase_pokes(case, item.request, item, count=count), EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == expected_id
    assert leaf.read_int(info, SHOP_RECORD + item.count, WORD_BYTES, case) == (count + 1) & 0xffff


# (price, purse, affordable?) — the `bgt` is SIGNED and the purse is packed BCD, so a purse of
# $8000 or more reads NEGATIVE and refuses every positive price. That is a shipped bug and it is
# reachable on the game's own data: the counter under the score runs to 9999.
PRICE_CASES = (
    (0x0010, 0x0099, True),
    (0x0099, 0x0099, True),      # exactly affordable — `bgt` is STRICT, so this one buys
    (0x0100, 0x0099, False),
    (0x0001, 0x8000, False),     # eight thousand gold, and nothing can be bought
    (0x0001, 0x9999, False),     # ...right up to the counter's own four-digit maximum
    (0x0000, 0x8000, False),     # even a free item: 0 > a negative purse
)


@pytest.mark.parametrize("price,purse,affordable", PRICE_CASES)
def test_the_price_compare_is_signed_and_a_refusal_falls_into_the_greeting(price, purse,
                                                                          affordable):
    """A refused purchase does not return — `bgt $dd12` lands in the greeting arm, so its countdown
    ticks and the request word has ALREADY been cleared."""
    case = f"price {price:#06x} purse {purse:#06x}"
    info = run_frame(case, purchase_pokes(case, ITEM1.request, ITEM1, price=price, purse=purse),
                     EXIT_RETURN)
    written = program_writes(info)
    assert leaf.read_int(info, SHOP_REQUEST, WORD_BYTES, case) == 0
    if affordable:
        assert GREET_COUNTDOWN not in written, f"{case}: an affordable purchase ticked the greeting"
        assert leaf.read_int(info, TEXT_REQUEST, 1, case) == FIRST_ID
    else:
        assert leaf.read_int(info, GREET_COUNTDOWN, WORD_BYTES, case) == 0x40 - 1
        assert BCD_COUNTER not in written, f"{case}: a refused purchase spent the purse"


def test_a_refusal_can_reach_the_greeting_message_itself():
    """The fall-through is a real entry into the greeting, not just its countdown: with the
    countdown at 1 the refused purchase posts a greeting and spends the MESSAGE cost."""
    case = "refusal reaches the greeting message"
    seeds = purchase_pokes(case, ITEM1.request, ITEM1, price=0x0100, purse=0x0099)
    seeds[GREET_COUNTDOWN] = word(1)
    seeds[SHOP_RECORD + GREET_COUNT] = word(0)
    seeds[SHOP_RECORD + GREET_MSG_FIRST] = word(0x66)
    info = run_frame(case, seeds, EXIT_RETURN)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == 0x66
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == 0x40 - MESSAGE_COST


# --- the purchase's effect dispatch --------------------------------------------------------------

@pytest.mark.parametrize("index", range(EFFECT_COUNT))
def test_a_purchase_dispatches_through_the_effect_table(index):
    """Every entry of the shipped table, through the ITEM 2 dispatch site ($de60). This is what pins
    the C's handler array as an ORDER: an array out of step by one runs a different effect and the
    diff lands on that effect's own global.

    Item 1's site ($ddea) runs the same twenty-three indices in
    `test_only_the_push_handlers_move_the_dispatchers_record_pointer` below, which asserts this and
    the a1 hand-back as well — so running them here too would be the same twenty-three differentials
    twice over."""
    case = f"item 2 effect {index}"
    run_frame(case, purchase_pokes(case, ITEM2.request, ITEM2, effect=index), EXIT_RETURN)


PUSH_FIRST = wb("EFFECT_HANDLER_PUSH_FIRST")
PUSH_COUNT = wb("EFFECT_HANDLER_PUSH_COUNT")


@pytest.mark.parametrize("index", range(EFFECT_COUNT))
def test_only_the_push_handlers_move_the_dispatchers_record_pointer(index):
    """WHICH handlers clobber a1, read off where the visit spend lands. A push handler's
    `movea.l $b546,a1` survives the `jsr`, so the `sub.w d0,32(a1)` two instructions later writes
    into the RECORD LIST; the other nineteen leave a1 alone and it hits the shop's own budget. The
    two destinations are far apart, so a reconstruction that got the set wrong writes to the wrong
    one of them and the diff says so.

    It runs every index through the ITEM 1 dispatch site, so it is also that site's whole-table
    coverage — which is why the case above runs item 2's alone."""
    case = f"a1 after effect {index}"
    budget = 0x0040
    info = run_frame(case, purchase_pokes(case, ITEM1.request, ITEM1, effect=index, budget=budget),
                     EXIT_RETURN)
    written = program_writes(info)
    pushes = PUSH_FIRST <= index < PUSH_FIRST + PUSH_COUNT
    assert (MISAIMED_BUDGET in written) is pushes, (
        f"{case}: the spend {'did not land' if pushes else 'landed'} in the record list")
    assert (SHOP_RECORD + VISIT_BUDGET in written) is not pushes
    if pushes:
        assert leaf.read_int(info, MISAIMED_BUDGET, WORD_BYTES, case) == 0x0400 - PURCHASE_COST
    else:
        assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES,
                             case) == budget - PURCHASE_COST


def test_the_push_handler_set_is_the_four_names_txt_names():
    """The set the C tests by range, stated by NAME so the range and the table cannot drift."""
    pushed = [name for name in HANDLER_NAMES if name.startswith("effect_push_record")]
    assert len(pushed) == PUSH_COUNT
    assert HANDLER_NAMES[PUSH_FIRST:PUSH_FIRST + PUSH_COUNT] == tuple(pushed)


def test_the_battery_refuses_an_index_outside_the_table():
    """The refusal src/scene.c makes, stated. An index at or past WB_EFFECT_HANDLER_COUNT reads a
    longword outside the table and the original calls whatever it finds — not reproducible, so it is
    an input this file declines rather than a case that would prove nothing."""
    first = int.from_bytes(bytes(harness.BASE_IMAGE[EFFECT_TABLE:EFFECT_TABLE + LONGWORD_BYTES]),
                           "big")
    past = int.from_bytes(bytes(harness.BASE_IMAGE[EFFECT_TABLE + EFFECT_COUNT * LONGWORD_BYTES:
                                                   EFFECT_TABLE + (EFFECT_COUNT + 1)
                                                   * LONGWORD_BYTES]), "big")
    assert past != first, "the longword past the table is supposed not to be a handler address"
    assert not any(past == leaf.entry_of(name) for name in HANDLER_NAMES), (
        f"{past:#x} past the table IS one of the handlers, so the bound would be wrong")


# --- the visit budget, entered directly ----------------------------------------------------------
BUDGET_CAP = 64


# The cell map_stamp_block writes, and the one below it: the descriptor's cell index, biased past
# the stride word the whole map is addressed from. Four cases name it.
STAMPED_CELL = MAP_ROW_STRIDE + MAP_CELL_INDEX + MAP_CELL_BIAS


def budget_pokes(case, budget, cell_left, cell, cell_right):
    return pokes(case, words=((DESCRIPTOR + SCENE_KIND, KIND_SHOP),
                              (SHOP_RECORD + VISIT_BUDGET, budget)),
                 bytes_=((MARKER_CELL - 1, cell_left), (MARKER_CELL, cell),
                         (MARKER_CELL + 1, cell_right)))


@pytest.mark.parametrize("budget,amount", [(0x0010, MESSAGE_COST), (0x0003, PURCHASE_COST),
                                           (0x0002, MESSAGE_COST), (0x8000, 0x0001)])
def test_the_budget_spend_that_does_not_borrow_writes_only_the_budget(budget, amount):
    """`sub.w` and `bmi` — the sign of the RESULT. $8000 - 1 is $7fff, still positive, so the
    largest budget the word can hold does not close the visit."""
    case = f"budget {budget:#06x} - {amount}"
    seeds = budget_pokes(case, budget, 0x11, 0x22, 0x33)
    info = leaf.run("scene_spend_visit_budget", _SPEND(SHOP_RECORD, amount),
                    [(SHOP_RECORD + VISIT_BUDGET, WORD_BYTES)], case,
                    regs={"a1": SHOP_RECORD, "d0": amount, "_pokes": seeds},
                    max_insns=BUDGET_CAP, poison=False)
    assert info["ret"] == EXIT_RETURN
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == budget - amount


@pytest.mark.parametrize("budget,amount", [(0x0001, MESSAGE_COST), (0x0000, PURCHASE_COST),
                                           (0x8002, 0x8003)])
def test_a_borrow_stamps_the_map_and_clears_the_marker_with_its_right_twin(budget, amount):
    """The borrow closes the visit: map_stamp_block's four cells, then the marker cell and the
    neighbour that matches it. The third case is the WRAP — $8002 - $8003 is $ffff, negative, so a
    budget the word arithmetic wraps closes the visit exactly as an honestly exhausted one does."""
    case = f"borrow right {budget:#06x} - {amount:#06x}"
    seeds = budget_pokes(case, budget, 0x11, 0x22, 0x22)
    allowed = [(SHOP_RECORD + VISIT_BUDGET, WORD_BYTES), (STAMPED_CELL, 2),
               (STAMPED_CELL + MAP_STRIDE, 2),
               (MARKER_CELL, 2)]
    info = leaf.run("scene_spend_visit_budget", _SPEND(SHOP_RECORD, amount), allowed, case,
                    regs={"a1": SHOP_RECORD, "d0": amount, "_pokes": seeds},
                    max_insns=BUDGET_CAP, poison=False)
    assert s16(budget - amount) < 0, "this case is supposed to borrow"
    assert info["ret"] == EXIT_RETURN
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES,
                         case) == (budget - amount) & 0xffff
    assert leaf.read_int(info, MARKER_CELL, 1, case) == 0
    assert leaf.read_int(info, MARKER_CELL + 1, 1, case) == 0
    # The stamp lands on a cell the case SEEDED, and seeded with neither zero nor the tile it
    # writes: a candidate that skipped the store would leave that byte behind rather than match by
    # accident on an unseeded zero, which is what the map band is for.
    seeded = harness.make_image(seeds)[STAMPED_CELL]
    assert seeded not in (0, wb("STAMP_TILES_FIRST")), (
        f"{case}: the stamped cell was seeded {seeded:#04x}, which the stamp could match by "
        f"writing nothing")
    assert leaf.read_int(info, STAMPED_CELL, 1, case) == wb("STAMP_TILES_FIRST")


def test_a_borrow_clears_the_left_twin_when_the_right_one_does_not_match():
    """The two compares run in order — right neighbour first, left second."""
    case = "borrow left"
    seeds = budget_pokes(case, 0x0000, 0x22, 0x22, 0x33)
    allowed = [(SHOP_RECORD + VISIT_BUDGET, WORD_BYTES), (STAMPED_CELL, 2),
               (STAMPED_CELL + MAP_STRIDE, 2),
               (MARKER_CELL - 1, 2)]
    info = leaf.run("scene_spend_visit_budget", _SPEND(SHOP_RECORD, MESSAGE_COST), allowed, case,
                    regs={"a1": SHOP_RECORD, "d0": MESSAGE_COST, "_pokes": seeds},
                    max_insns=BUDGET_CAP, poison=False)
    assert info["ret"] == EXIT_RETURN
    assert leaf.read_int(info, MARKER_CELL, 1, case) == 0
    assert leaf.read_int(info, MARKER_CELL - 1, 1, case) == 0


def test_a_marker_cell_matching_neither_neighbour_takes_the_stage_reset_tail():
    """The tail this file does not follow — `jmp $1ab4.w`, which is stage_load_window again."""
    case = "borrow with no twin"
    seeds = budget_pokes(case, 0x0000, 0x11, 0x22, 0x33)
    allowed = [(SHOP_RECORD + VISIT_BUDGET, WORD_BYTES), (STAMPED_CELL, 2),
               (STAMPED_CELL + MAP_STRIDE, 2),
               (MARKER_CELL, 1)]
    info = run_reaching("scene_spend_visit_budget", _SPEND(SHOP_RECORD, MESSAGE_COST), allowed,
                        case, transfer_at("budget exhausted"),
                        regs={"a1": SHOP_RECORD, "d0": MESSAGE_COST, "_pokes": seeds},
                        max_insns=BUDGET_CAP, stop_pc=STAGE_RESET_TAIL, poison=False)
    assert info["ret"] == EXIT_STAGE_RESET
    assert leaf.read_int(info, MARKER_CELL, 1, case) == 0


def test_only_the_low_word_of_the_amount_register_is_spent():
    """`sub.w d0,32(a1)` — the high half of d0 is whatever the caller left and must not reach the
    budget."""
    case = "budget amount high half"
    seeds = budget_pokes(case, 0x0010, 0x11, 0x22, 0x33)
    info = leaf.run("scene_spend_visit_budget", _SPEND(SHOP_RECORD, 0xbeef0002),
                    [(SHOP_RECORD + VISIT_BUDGET, WORD_BYTES)], case,
                    regs={"a1": SHOP_RECORD, "d0": 0xbeef0002, "_pokes": seeds},
                    max_insns=BUDGET_CAP, poison=False)
    assert leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case) == 0x0010 - 2


def test_a_shop_message_that_exhausts_the_budget_closes_the_visit_from_the_driver():
    """The same borrow, reached the way the game reaches it — through the greeting arm, which is
    what makes $de80's `bsr` sites part of this battery rather than only its own entry."""
    case = "greeting exhausts the budget"
    info = run_frame(case, shop_pokes(case, words=(
        (MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, 0), (GREET_COUNTDOWN, 1),
        (SHOP_RECORD + GREET_COUNT, 0), (SHOP_RECORD + GREET_MSG_FIRST, 0x21),
        (SHOP_RECORD + VISIT_BUDGET, 1)),
        bytes_=((MARKER_CELL - 1, 0x77), (MARKER_CELL, 0x77), (MARKER_CELL + 1, 0x12))),
        EXIT_RETURN)
    assert s16(leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case)) == 1 - MESSAGE_COST
    assert leaf.read_int(info, MARKER_CELL, 1, case) == 0
    assert leaf.read_int(info, MARKER_CELL - 1, 1, case) == 0


# Every arm that spends the budget, and what it spends. $de80's stage-reset tail is reached THROUGH
# one of them, so each has its own chance to swallow the exit the spend hands back — the shop's
# charged leave by overwriting it with its own, and the other three by discarding it and returning.
# (label, the words that put the shop in that arm, the bytes it needs, what the spend costs)
BUDGET_SPENDING_ARMS = (
    ("charged leave",
     ((MESSAGE_PENDING, MESSAGE_PENDING_SET), (SHOP_RECORD + LEAVE_CHARGED, 1)),
     joystick(JOY1_FIRE) + ((TEXT_BOX_ACTIVE, 0xff),), MESSAGE_COST),
    ("greeting",
     ((MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, 0), (GREET_COUNTDOWN, 1),
      (SHOP_RECORD + GREET_COUNT, 0), (SHOP_RECORD + GREET_MSG_FIRST, 0x21)),
     (), MESSAGE_COST),
    ("farewell",
     ((MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, REQUEST_FAREWELL),
      (SHOP_RECORD + FAREWELL_COUNT, 0)),
     (), MESSAGE_COST),
    ("purchase",
     ((MESSAGE_PENDING, 0), (ACK_WAIT, 0), (SHOP_REQUEST, ITEM1.request), (BCD_COUNTER, 0x0099),
      (SHOP_RECORD + ITEM1.price, 0x0010), (SHOP_RECORD + ITEM1.count, 0),
      (SHOP_RECORD + ITEM1.msg_first, FIRST_ID), (SHOP_RECORD + ITEM1.effect, 0),
      (GREET_COUNTDOWN, 0x40)),
     (), PURCHASE_COST),
)


@pytest.mark.parametrize("arm,words,bytes_,cost", BUDGET_SPENDING_ARMS,
                         ids=[arm for arm, *_rest in BUDGET_SPENDING_ARMS])
def test_a_borrow_with_no_twin_takes_the_stage_reset_tail_out_of_every_arm(arm, words, bytes_,
                                                                          cost):
    """$de80's `jmp $1ab4.w`, reached the way the game reaches it: through the driver.

    The direct-entry case above pins the tail; this pins that the DRIVER hands it back. Every arm
    below spends the budget as its last act, so each is a place the transfer could be swallowed —
    and one of them, the charged leave, actively rewrites the spend's other answer into its own
    exit ($dc5e), which is exactly the arm where "pass it on" and "always reload" look alike.

    The marker cell matches neither neighbour, which is what sends the spend to $1ab4 rather than
    back with the visit merely closed."""
    case = f"stage reset out of the {arm}"
    seeds = shop_pokes(case, words=tuple(words) + ((SHOP_RECORD + VISIT_BUDGET, 0),),
                       bytes_=tuple(bytes_) + ((MARKER_CELL - 1, 0x11), (MARKER_CELL, 0x22),
                                               (MARKER_CELL + 1, 0x33)))
    info = run_frame(case, seeds, EXIT_STAGE_RESET, via="budget exhausted")
    written = program_writes(info)
    assert s16(leaf.read_int(info, SHOP_RECORD + VISIT_BUDGET, WORD_BYTES, case)) == -cost
    assert leaf.read_int(info, MARKER_CELL, 1, case) == 0
    assert leaf.read_int(info, STAMPED_CELL, 1, case) == wb("STAMP_TILES_FIRST")
    assert MARKER_CELL - 1 not in written and MARKER_CELL + 1 not in written, (
        f"{case}: a cell matching neither neighbour leaves both of them alone")


# --- the boss-defeat arm -------------------------------------------------------------------------
def boss_pokes(case, flag, variant=1, exit_request=0, slot_bbc4=0):
    return pokes(case, words=((FLAG_A30, 0x0000), (FLAG_A32, 0xffff),
                              (DESCRIPTOR + SCENE_KIND, KIND_BOSS),
                              (DESCRIPTOR + SCENE_VARIANT, variant),
                              (BOSS_DEFEAT_FLAG, flag), (SCENE_EXIT_REQUEST, exit_request)),
                 bytes_=((HUD_SLOT_BBC4, slot_bbc4),))


def test_the_boss_arm_does_nothing_while_neither_flag_nor_exit_request_is_up():
    case = "boss idle"
    info = run_frame(case, boss_pokes(case, flag=0), EXIT_RETURN, cap=BOSS_CAP)
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


@pytest.mark.parametrize("exit_request", [0x0001, 0xffff])
def test_an_exit_request_alone_leaves_the_scene(exit_request):
    """The arm the power-up path at $10768 raises: the request is cleared and the scene ends."""
    case = f"boss exit request {exit_request:#06x}"
    info = run_frame(case, boss_pokes(case, flag=0, exit_request=exit_request), EXIT_RELOAD,
                     cap=BOSS_CAP, via="boss exit")
    assert leaf.read_int(info, SCENE_EXIT_REQUEST, WORD_BYTES, case) == 0
    assert set(program_writes(info)) == set(range(SCENE_EXIT_REQUEST,
                                                  SCENE_EXIT_REQUEST + WORD_BYTES))


def _free_marked(addr_from, count):
    return {addr_from + slot * RECORD_BYTES + ACTOR_X + i: FREE_MARKER.to_bytes(2, "big")[i]
            for slot in range(count) for i in range(WORD_BYTES)}


def test_a_zero_variant_frees_ten_slots_and_leaves_them_free():
    """The free ahead of the fill is not redundant: with the descriptor's variant zero the arm
    returns with all eight fragment slots still holding WB_ACTOR_FREE_MARKER."""
    case = "boss variant 0"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=0), EXIT_RETURN, cap=BOSS_CAP)
    expected = dict(_free_marked(TABLE_A32, BOSS_HEAD_SLOTS))
    expected.update(_free_marked(BOSS_SLOTS, BOSS_COUNT))
    expected.update({BOSS_DEFEAT_FLAG: 0, BOSS_DEFEAT_FLAG + 1: 0})
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{case}: it wrote {sorted(hex(a) for a in written)} against {sorted(hex(a) for a in expected)}")
    for addr, value in expected.items():
        assert written[addr] == value


@pytest.mark.parametrize("variant,expected_type", [(1, BOSS_TYPE_1), (2, BOSS_TYPE_2),
                                                   (0xffff, BOSS_TYPE_2)])
def test_the_fragments_are_built_from_the_shipped_parameter_pairs(variant, expected_type):
    """Every field of every fragment, against the game's own sixteen parameter bytes: the origin
    longword read ONCE before the loop, the type the variant picks, the size longword, the three
    fixed bytes, the parameter byte that lands in TWO fields, and the side bit's mirror split."""
    case = f"boss variant {variant:#06x}"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=variant), EXIT_RETURN,
                     cap=BOSS_CAP)
    image = harness.make_image(boss_pokes(case, flag=0xffff, variant=variant))
    origin = int.from_bytes(bytes(image[BOSS_ORIGIN:BOSS_ORIGIN + LONGWORD_BYTES]), "big")
    params = bytes(harness.BASE_IMAGE[BOSS_PARAMS:BOSS_PARAMS + BOSS_COUNT * BOSS_PARAM_LEN])
    written = program_writes(info)

    for index in range(BOSS_COUNT):
        slot = BOSS_SLOTS + index * RECORD_BYTES
        counter = BOSS_COUNT - 1 - index
        speed, field31 = params[index * BOSS_PARAM_LEN], params[index * BOSS_PARAM_LEN + 1]
        assert leaf.read_int(info, slot + ACTOR_X, LONGWORD_BYTES, case) == origin
        assert leaf.read_int(info, slot + ACTOR_TYPE, WORD_BYTES, case) == expected_type
        assert leaf.read_int(info, slot + ACTOR_HALF_WIDTH, LONGWORD_BYTES, case) == BOSS_SIZE
        assert leaf.read_int(info, slot + ACTOR_FIELD_10, 1, case) == speed
        assert leaf.read_int(info, slot + ACTOR_SPEED, 1, case) == speed
        assert leaf.read_int(info, slot + ACTOR_FIELD_12, 1, case) == BOSS_FIELD_12
        assert leaf.read_int(info, slot + ACTOR_FIELD_30, 1, case) == BOSS_FIELD_30
        assert leaf.read_int(info, slot + ACTOR_FIELD_31, 1, case) == field31
        flags = leaf.read_int(info, slot + ACTOR_FLAGS, 1, case)
        assert flags & (1 << FLAG_MOVING_BIT) and flags & (1 << FLAG_LAUNCHED_BIT)
        assert not flags & (1 << FLAG_SUPPORTED_BIT)
        mirrored = counter <= BOSS_MIRROR_AT
        assert bool(flags & (1 << FLAG_SIDE_BIT)) is not mirrored, (
            f"{case}: fragment {index} (dbf counter {counter}) has the side bit the wrong way round")
        assert slot + ACTOR_X in written


def test_the_two_head_slots_stay_free_while_the_eight_are_refilled():
    """The first free covers WB_ACTOR_TABLE_A32's own first two records, which the fill never
    reaches — they are four records below WB_BOSS_FRAGMENT_SLOTS."""
    case = "boss head slots"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=1), EXIT_RETURN, cap=BOSS_CAP)
    for slot in range(BOSS_HEAD_SLOTS):
        addr = TABLE_A32 + slot * RECORD_BYTES + ACTOR_X
        assert leaf.read_int(info, addr, WORD_BYTES, case) == FREE_MARKER


def test_the_hud_slot_takes_the_scene_out_after_the_fragments_are_built():
    """`tst.b $bbc4.l / bne $df92` — this arm is that slot's only reader among the reconstructed
    routines, and it SKIPS the exit-request test rather than replacing it: the request is zero here
    and the scene ends anyway."""
    case = "boss hud slot leaves"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=1, slot_bbc4=0x01),
                     EXIT_RELOAD, cap=BOSS_CAP, via="boss exit")
    assert leaf.read_int(info, SCENE_EXIT_REQUEST, WORD_BYTES, case) == 0
    assert leaf.read_int(info, BOSS_SLOTS + ACTOR_TYPE, WORD_BYTES, case) == BOSS_TYPE_1


def test_a_zero_variant_returns_before_reading_the_hud_slot():
    """...and the variant-zero return happens BEFORE that test, which is what separates the two
    early exits: a zero variant with the slot up still returns."""
    case = "boss variant 0 with the slot up"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=0, slot_bbc4=0x01), EXIT_RETURN,
                     cap=BOSS_CAP)
    assert BOSS_SLOTS + ACTOR_TYPE not in program_writes(info)
