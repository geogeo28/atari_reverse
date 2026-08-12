"""Differential test for the scene tier — `scene_run_frame` ($dbc0) and `scene_spend_visit_budget`
($de80), src/scene.c.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image and
requires the two to agree byte for byte, with the original's write set bounded by what the case says
it may touch. Two things make this battery different from the leaf ones under it.

ONE BOUNDARY IS LEFT, AND IT IS NOT THE ONE THIS FILE WAS WRITTEN FOR. Four of $dbc0's exits
transfer to `$dfbe` and one of $de80's to `$1ab4`. `$dfbe` is now RECONSTRUCTED (batch 27) — its
eight-entry dispatch table is all ported code and `stage_load_window` under it has run whole since
batch 26 — so those four cases are FULL RUNS: the arm, the exit, the dispatched action and the whole
stage reload, ending at the original's own `rts`. `$1ab4` is still not reconstructed, and a case that
expects it runs the oracle with the kit's `stop_pc` set to that address, which diffs the whole prefix
at the instant control arrives there.

WHICH EXIT WAS TAKEN IS NEVER INFERRED FROM THE C, checkpoint or no checkpoint: every case that
names an exit also names the TRANSFER INSTRUCTION it expects to leave through and requires the
oracle's executed-PC coverage to hold it (`leaf.run_reaching`). The transfer instructions themselves
are pinned by their bytes at their own addresses.

WHAT THE FULL RUNS TRADED FOR THE CHECKPOINT THEY REPLACED. A `stop_pc` run compared the image at the
INSTANT of the transfer; a full run compares it at the end, so a byte the arm writes and the tail
then overwrites would only be seen in its final state. Nothing here is such a byte, and that is an
argument rather than a hope: the write set of each of the four arms
(nothing / nothing / the visit budget / WB_SCENE_EXIT_REQUEST and the boss slots) is DISJOINT from
$dfbe's own (the box byte, the freeze word, the four state words, and everything the hinge writes),
so every arm byte is still compared at the value the arm left it. What is genuinely gone is ORDER:
an arm that wrote its byte after the tail rather than before is now indistinguishable.

EVERYTHING IT READS IS SEEDED. The scene descriptor table ($21828) and the shop records ($21a28..)
lie past the program and are loaded from disk — the image ships zeros for the first and nothing at
all for the second — so no case can be built from the game's own data and all of it is seeded,
address-keyed, the way test_actor.py's tables are. What IS the game's own data, and pinned as such:
the 23 effect handlers the purchase arm dispatches to, the eight entries of the exit-action table,
and the eight speech scripts.

KNOWINGLY NOT PINNED
  * anything past `$1ab4`, the one exit still not reconstructed.
  * an effect index outside 0..22, and an exit-action index whose OFFSET leaves its table. Both
    dispatches scale by a WORD `lsl` and add the result SIGN-EXTENDED, so the offset — not the index
    — is what selects an entry, and 32 exit-action index values reach the eight entries rather than
    8 (the bands at $4000/$8000/$c000 alias onto 0..7, and cases drive one from each). What is
    refused is only an offset that genuinely leaves the table, where the original `jsr`s through a
    longword outside it; that is src/blit.c's sprite-dispatch refusal, and a case states it. The
    START-table index is the deliberate contrast and IS reproduced whole: it is a data read, so the
    C follows it wherever it lands and a case drives it below the table.
  * WHAT THE SHIPPED DESCRIPTORS SELECT. Both indices come from the 32-byte descriptor, and the
    descriptor table lies past the program and is loaded from disk — the .PRG ships $a8 bytes of
    ZEROS for it. So no shipped datum names any entry but 0, and every other row here is a case's own
    seed. Which entries the game actually reaches is a question about the disk, not about the image.
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
                  clr_b_abs_l, clr_w_abs_l, clr_w_abs_w, cmpi_w_abs_l, cmpi_w_d16, jsr_abs_l,
                  keyed_block, lea_abs_l, lea_indexed, longword, lsl_w_imm_dn, merge_bands,
                  move_l_imm_abs_l, move_w_imm_abs_l, move_w_imm_abs_w, move_w_ind_dn,
                  movea_l_abs_l, opcode, overlay, program_writes, run_reaching, s16, seeded_bytes,
                  sub_w_dn_d16, tst_w_abs_w, word)
from layout import wb
# The reload tail RUNS stage_load_window, so a composed case's write set CONTAINS that routine's.
# The model, the seeds, the instruction cap and the unmatched latch all come from the battery that
# owns them — two copies could disagree while both stayed green, which is the rule test_stage.py
# itself follows towards test_hud.py and test_sound.py.
from test_stage import (LATCH_UNMATCHED, LOAD_WINDOW_INSN_CAP,               # noqa: E402
                        build_cursors, load_window_pokes, model_load_window)
from test_sound import PLAY_SONG_MIXER, PSG_REG_MIXER, assert_psg_state      # noqa: E402
# ...and the six `set_state_*` stubs the exit table dispatches to are test_effects.py's, destination
# and immediate alike — that table is its transcription of the disassembly, not a second copy.
from test_effects import WORD_SETTERS                                        # noqa: E402

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
SCENE_EXIT_ACTION = wb("SCENE_EXIT_ACTION")
SCENE_START_INDEX = wb("SCENE_START_INDEX")
EXIT_ALLOC_COUNT = wb("SCENE_EXIT_ALLOC_COUNT")

# --- what the exit tail reads and writes ---------------------------------------------------------
# $dfbe's three `lea` literals: the LEVEL MAP (which is WB_MAP_ROW_STRIDE's own address — the header
# word and the global stride word are ONE word for this caller), the shipped tile bank, and the
# eight-entry table it indexes for the start record.
STAGE_START_TABLE = wb("STAGE_START_TABLE")
STAGE_START_TABLE_ENTRIES = wb("STAGE_START_TABLE_ENTRIES")
TILE_BITMAPS = wb("TILE_BITMAPS")
START_RECORD_LEN = wb("START_RECORD_LEN")
START_FOLLOW_X = wb("START_FOLLOW_X")
START_FOLLOW_Y = wb("START_FOLLOW_Y")
START_TUNE = wb("START_TUNE")
START_PALETTE = wb("START_PALETTE")
STATE_FLAG_A34 = wb("STATE_FLAG_A34")
PANEL_FRAME_HOLD = wb("PANEL_FRAME_HOLD")
SCROLL_FOLLOW_FROZEN = wb("SCROLL_FOLLOW_FROZEN")

# ...and what entry 1 of the table touches.
HUD_SLOT_BBC6 = wb("HUD_SLOT_BBC6")
HUD_SLOT_CHANGED = wb("HUD_SLOT_CHANGED")
EXIT_SLOT_BBC6 = (1 << 8) | HUD_SLOT_CHANGED       # the `move.w #$1ff` at $101be, as its two bytes
EFFECT_STATE_21E4 = wb("EFFECT_STATE_21E4")
EFFECT_RECORD_LIST = wb("EFFECT_RECORD_LIST")
TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
TABLE_A30 = wb("ACTOR_TABLE_A30")
ALLOC_LOW_FIRST = wb("ACTOR_ALLOC_LOW_FIRST")
ALLOC_LOW_SLOTS = wb("ACTOR_ALLOC_LOW_SLOTS")
ALLOC_NONE = wb("ACTOR_ALLOC_NONE")

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
# Both are ABOVE the level map $dfbe hands the hinge, which begins at WB_MAP_ROW_STRIDE and whose
# eleven cursors reach ~$2233c at the stride below. A composed case seeds both structures, so an
# overlap would leave one of them reading the other's bytes; the assertion under COMPOSED_MAP_TOP
# is what keeps that true if either number moves.
MARKER_CELL = 0x24000
RECORD_WRITE_TARGET = 0x24800
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

# --- the two exits, one of them now followed -----------------------------------------------------
RELOAD_TAIL = 0xdfbe              # scene_exit_and_reload — RECONSTRUCTED, so no checkpoint
STAGE_RESET_TAIL = 0x1ab4
STOP_PC_FOR = {EXIT_STAGE_RESET: STAGE_RESET_TAIL}

# ...and the two arms the a30 half's kind ladder branches to, which are targets rather than tails.
SPEECH_ARM = 0xdc00
SHOP_ARM = 0xdc2a


# --- the encodings this battery pins its entries with --------------------------------------------
# Only the ones no other battery spells; the shared ones come from leaf.py above.
BMI_W, BEQ_W, BNE_W, BRA_W, BGT_W = 0x6b00, 0x6700, 0x6600, 0x6000, 0x6e00


def jmp_abs_w(addr):
    """`jmp <abs>.w` — $de80's tail into $1ab4, and the only jump in either routine."""
    return opcode(0x4ef8) + word(addr)


def jsr_abs_w(addr):
    """`jsr <abs>.w` — $101be's call into actor_alloc_slot_low, which lives below $8000."""
    return opcode(0x4eb8) + word(addr)


def jsr_ind(an):
    """`jsr (An)` — the exit dispatch, once the table entry is in the register."""
    return opcode(0x4e90 | an)


def movea_l_ind(destination, source):
    """`movea.l (As),Ad` — how both of $dfbe's tables turn an entry into the thing it names."""
    return opcode(0x2050 | (destination << 9) | source)


def cmpa_l_imm(an, value):
    """`cmpa.l #imm,An` — $101be's one test, and it is a LONGWORD compare of the whole pointer."""
    return opcode(0xb1fc | (an << 9)) + longword(value)


def addq_w_ind(amount, an):
    """`addq.w #n,(An)` — the counter bump, through a pointer the instruction before it `lea`d."""
    return opcode(0x5050 | ((amount & 7) << 9) | an)


A0, A1, A6 = 0, 1, 6
D0 = 0

# $dfbe, whole: the exit dispatch, the box byte, the three register arguments of the hinge, the
# freeze word cleared LAST, the call, and the five state words. Assembled rather than transcribed, so
# a wrong operand or a wrong addressing mode fails here instead of inside a case.
#
# KEPT AS A TUPLE OF INSTRUCTIONS rather than one byte string, because `len()` of it is then the
# routine's INSTRUCTION COUNT — which is what the caps below need, and restating that count as a
# number beside a pin that already contains it is how a cap stops being derived from geometry.
EXIT_AND_RELOAD_PIECES = (
    movea_l_abs_l(A6, DESCRIPTOR_PTR),
    move_w_ind_dn(D0, A6, SCENE_EXIT_ACTION), lsl_w_imm_dn(2, D0),
    lea_abs_l(A6, EXIT_ACTION_TABLE), lea_indexed(A6, D0), movea_l_ind(A6, A6), jsr_ind(A6),
    clr_b_abs_l(TEXT_BOX_ACTIVE),
    lea_abs_l(A0, MAP_ROW_STRIDE), lea_abs_l(A6, TILE_BITMAPS),
    movea_l_abs_l(A1, DESCRIPTOR_PTR),
    move_w_ind_dn(D0, A1, SCENE_START_INDEX), lsl_w_imm_dn(2, D0),
    lea_abs_l(A1, STAGE_START_TABLE), lea_indexed(A1, D0), movea_l_ind(A1, A1),
    clr_w_abs_w(SCROLL_FOLLOW_FROZEN),
    jsr_abs_l(leaf.entry_of("stage_load_window")),
    clr_w_abs_w(STATE_FLAG_A34), clr_w_abs_l(PANEL_FRAME_HOLD),
    clr_w_abs_w(FLAG_A30), clr_w_abs_w(FLAG_A32), clr_w_abs_l(MESSAGE_PENDING), RTS)
EXIT_AND_RELOAD_BYTES = b"".join(EXIT_AND_RELOAD_PIECES)
# Straight-line: it has no branch of its own, so every instruction of it runs on every path.
EXIT_AND_RELOAD_INSN = len(EXIT_AND_RELOAD_PIECES)

# ...and $101be, whole. The two `move.l #imm` either side of the `jsr` are the ordering the port has
# to keep: the allocator runs against WB_ACTOR_TABLE_DEFAULT and the pointer is then republished as
# WB_ACTOR_TABLE_A30.
EXIT_ACTION_1_PIECES = (
    move_w_imm_abs_l(EXIT_SLOT_BBC6, HUD_SLOT_BBC6),
    move_w_imm_abs_w(1, EFFECT_STATE_21E4),
    clr_b_abs_l(EFFECT_RECORD_LIST),
    move_l_imm_abs_l(TABLE_DEFAULT, TABLE_SELECTED),
    jsr_abs_w(leaf.entry_of("actor_alloc_slot_low")),
    move_l_imm_abs_l(TABLE_A30, TABLE_SELECTED),
    cmpa_l_imm(A1, ALLOC_NONE), branch_w_to(BNE_W, 0x101f0, 0x101f6), RTS,
    lea_abs_l(A1, EXIT_ALLOC_COUNT), addq_w_ind(1, A1), RTS)
EXIT_ACTION_1_BYTES = b"".join(EXIT_ACTION_1_PIECES)
# ...less the early `rts` the LONGEST path (the one that finds a slot and bumps the counter) skips.
EXIT_ACTION_1_INSN = len(EXIT_ACTION_1_PIECES) - 1

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
    # ...and the two routines batch 27 ported, each pinned WHOLE rather than at its entry.
    "scene_exit_and_reload": (RELOAD_TAIL, EXIT_AND_RELOAD_BYTES),
    "scene_exit_action_select_a30_table": (0x101be, EXIT_ACTION_1_BYTES),
}
RECORDED_PINS = 20


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


def run_frame(case, seeds, expected_exit, allowed=None, cap=SHOP_CAP, via=None, psg_seed=None):
    """One `scene_run_frame` case: the differential, the exit the C reports, and — for anything but
    a plain return — the witness that ``via`` (a label in ENTRY_BYTES) is the transfer that took it.
    Only the STAGE-RESET exit still needs a checkpoint; the reload one RUNS.

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
    assert (via is not None) == (expected_exit != EXIT_RETURN), (
        f"{case}: a case that expects an exit must name the transfer that takes it, and one that "
        f"expects a plain return must not")
    how = dict(regs={"_pokes": seeds}, max_insns=cap, stop_pc=stop_pc, poison=False,
               psg_seed=psg_seed)
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


@pytest.mark.parametrize("name", ["scene_run_frame", "scene_spend_visit_budget",
                                  "scene_exit_and_reload", "scene_exit_action_select_a30_table"])
def test_each_reconstructed_entry_is_where_names_txt_says(name):
    """Each `fn` address, cross-checked against the pin table — `assert_entry_is` is the same check
    the leaf batteries make, and it is what ties ../names.txt to the bytes."""
    addr, expected = ENTRY_BYTES[name]
    assert leaf.entry_of(name) == addr, (
        f"../names.txt puts {name} at {leaf.entry_of(name):#x}, not at this battery's {addr:#x}")
    assert_entry_is(name, expected)


# The two whole-body pins above are also LENGTH claims, and each one is bounded by its own
# neighbour rather than by a number this file chose.
@pytest.mark.parametrize("name,ends_at,neighbour", [
    ("scene_exit_and_reload", MESSAGE_PENDING, "WB_SCENE_MESSAGE_PENDING"),
    ("scene_exit_action_select_a30_table", 0x10200, "the first set_state_* stub"),
])
def test_each_reconstructed_body_ends_exactly_where_its_neighbour_begins(name, ends_at, neighbour):
    addr, body = ENTRY_BYTES[name]
    assert addr + len(body) == ends_at, (
        f"{name}'s {len(body)} bytes end at {addr + len(body):#x}, not at {neighbour} "
        f"({ends_at:#x}) — so the pin above is not the whole routine")


def test_the_first_stub_the_exit_table_names_is_where_the_ported_entry_ends():
    """...and the second half of that: $10200 is not a number either, it is the address
    ../names.txt gives the first of the six stubs entries 2..7 dispatch to."""
    assert leaf.entry_of("set_state_bbc8_1ff") == 0x10200


def test_the_scene_exit_action_none_entry_is_a_bare_rts():
    """Entry 0 of the table, whose whole body IS the two bytes — which is also what BOUNDS the
    table: being the first of its own targets is what says eight entries and not nine."""
    assert_entry_is("scene_exit_action_none", RTS)
    assert leaf.entry_of("scene_exit_action_none") == (
        EXIT_ACTION_TABLE + EXIT_ACTION_COUNT * LONGWORD_BYTES)
    assert leaf.entry_of("scene_exit_action_none") + len(RTS) == leaf.entry_of(
        "scene_exit_action_select_a30_table")


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


# The eight targets, in the order src/scene.c's EXIT_ACTIONS array lists them. Transcribed from
# ../names.txt's `fn` block rather than composed, so the table below and the C are two independent
# statements of the same order — the same rule HANDLER_NAMES above follows.
EXIT_ACTION_NAMES = (
    "scene_exit_action_none", "scene_exit_action_select_a30_table",
    "set_state_bbc8_1ff", "set_state_bbc8_2ff", "set_state_bbc8_3ff", "set_state_bbc8_4ff",
    "set_state_bbc8_6ff", "set_state_6f9c_ffff",
)


def exit_action_table_entry(index):
    at = EXIT_ACTION_TABLE + index * LONGWORD_BYTES
    return int.from_bytes(bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES]), "big")


@pytest.mark.parametrize("index,name", list(enumerate(EXIT_ACTION_NAMES)))
def test_each_exit_action_table_entry_is_the_routine_names_txt_names(index, name):
    """The shipped table, entry by entry. Every one of the eight is reconstructed code — that is why
    $dfbe's dispatch has no boundary — and this is what makes the C's array an ORDER claim about the
    image rather than a list of its own."""
    assert exit_action_table_entry(index) == leaf.entry_of(name), (
        f"exit_action_table[{index}] holds {exit_action_table_entry(index):#x}, not {name} at "
        f"{leaf.entry_of(name):#x}")


def test_the_battery_refuses_an_exit_action_offset_outside_the_table():
    """The refusal src/scene.c makes, stated — the same shape as
    `test_the_battery_refuses_an_index_outside_the_table` one table over, and it is about the
    OFFSET rather than the index (see `exit_action_offset`).

    An index whose offset leaves the table makes the original `jsr` through a longword outside it;
    at index 8 that longword is $101bc's own first four BYTES, an `rts` and half of the instruction
    after it read as an address. There is no C for calling that, so it is an input this file
    declines. IT IS ALSO A COVERAGE HOLE AND IS NAMED AS ONE: batch 27's sweep turned the port's
    `>=` into a `>` and nothing here caught it, because nothing here can.
    """
    assert exit_action_entry(EXIT_ACTION_COUNT) is None, (
        "index 8 is supposed to be genuinely outside — if it aliased, this case would be testing "
        "nothing")
    past = int.from_bytes(bytes(harness.BASE_IMAGE[EXIT_ACTION_TABLE
                                                   + EXIT_ACTION_COUNT * LONGWORD_BYTES:
                                                   EXIT_ACTION_TABLE
                                                   + (EXIT_ACTION_COUNT + 1) * LONGWORD_BYTES]),
                          "big")
    assert not any(past == leaf.entry_of(name) for name in EXIT_ACTION_NAMES), (
        f"{past:#x} past the table IS one of the eight targets, so the bound would be wrong")
    assert past >= harness.IMAGE_SIZE or past & 1, (
        f"{past:#x} past the table is an even address inside the image, so 'the original calls "
        f"something no C can stand in for' would need a different argument")


# The addresses this battery has BOTH a header #define and a ../names.txt `var` for. Only the header
# is read at run time, so without this pin the name map could label a different address after a
# re-bootstrap and every case here would stay green — batch 26's own rule, and test_stage.py's
# TWO_SOURCE_ADDRESSES is the same claim one file over. WB_SCENE_EXIT_ALLOC_COUNT is batch 27's new
# one; the table beside it had gone unpinned since it was named.
TWO_SOURCE_ADDRESSES = (("scene_exit_alloc_count", EXIT_ALLOC_COUNT),
                        ("scene_exit_action_table", EXIT_ACTION_TABLE))


@pytest.mark.parametrize("name,constant", TWO_SOURCE_ADDRESSES,
                         ids=[name for name, _c in TWO_SOURCE_ADDRESSES])
def test_the_name_map_and_the_header_agree_about_each_address(name, constant):
    assert leaf.entry_of(name) == constant, (
        f"../names.txt puts {name} at {leaf.entry_of(name):#x} and include/wonderboy.h at "
        f"{constant:#x} — the reconstruction reads the header and nothing reads the name map")


def test_the_exit_action_table_is_bounded_by_its_own_first_target():
    """WB_SCENE_EXIT_ACTION_COUNT is not a number this battery chose: the table ends exactly where
    the routine its first entry names begins, which is what makes eight the whole of it."""
    assert exit_action_table_entry(0) == EXIT_ACTION_TABLE + EXIT_ACTION_COUNT * LONGWORD_BYTES, (
        f"the table's first target is {exit_action_table_entry(0):#x}, so it is not "
        f"{EXIT_ACTION_COUNT} entries")
    assert len(EXIT_ACTION_NAMES) == EXIT_ACTION_COUNT


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


def test_a_zero_variant_returns_before_reading_the_hud_slot():
    """...and the variant-zero return happens BEFORE that test, which is what separates the two
    early exits: a zero variant with the slot up still returns."""
    case = "boss variant 0 with the slot up"
    info = run_frame(case, boss_pokes(case, flag=0xffff, variant=0, slot_bbc4=0x01), EXIT_RETURN,
                     cap=BOSS_CAP)
    assert BOSS_SLOTS + ACTOR_TYPE not in program_writes(info)


# --- $101be and $101bc: the two exit actions this project reconstructs ----------------------------
#
# Entries 2..7 are effects.h's `set_state_*` stubs and test_effects.py owns them; the two below are
# the scene tier's own. $101be is the interesting one, and everything interesting about it is
# ORDERING: it publishes WB_ACTOR_TABLE_DEFAULT, allocates out of THAT table, and then republishes
# the pointer as WB_ACTOR_TABLE_A30 — so the table the search ran against is not the one it leaves
# selected, and the only surviving trace of the search is a counter no reader reads.

_EXIT_ACTION_NONE = leaf.image_glue("scene_exit_action_none")
_EXIT_ACTION_A30 = leaf.image_glue("scene_exit_action_select_a30_table")

# $101be's own longest path is EXIT_ACTION_1_INSN, counted off the pin above rather than restated.
# Its callee actor_alloc_slot_low is `movea.l`+`lea`+`move.w` before the loop, FOUR per record
# (`cmpi.w`, `beq.w`, `lea`, `dbf`) over WB_ACTOR_ALLOC_LOW_SLOTS of them, and two after it — the
# `movea.l #$0,a1` a full pool takes, and the `rts` both answers share.
ALLOC_SLOT_INSN = 3 + 4 * ALLOC_LOW_SLOTS + 2
EXIT_ACTION_INSN = EXIT_ACTION_1_INSN + ALLOC_SLOT_INSN
EXIT_ACTION_CAP = EXIT_ACTION_INSN + leaf.RUNNER_SENTINEL_INSN

# Seeds no case expects back, so a candidate that skipped a store fails the plain diff rather than
# matching a byte that already held the value (the substitute for the poison pass this file's
# `run_frame` explains it cannot use — and which IS on for the two cases below, since nothing $101be
# writes steers its own next branch).
SEED_SLOT_BBC6 = 0x5a5a
SEED_STATE_21E4 = 0xa5a5
SEED_RECORD_LIST = 0xbeef         # the `clr.b` takes the first byte; $ef must survive
SEED_ALLOC_COUNT = 0x0100
POOL_OCCUPIED = 0x0123            # any word that is not WB_ACTOR_FREE_MARKER


def alloc_pool_pokes(table, free_slot=None):
    """One actor table's LOW pool as actor_alloc_slot_low sees it: WB_ACTOR_ALLOC_LOW_SLOTS records
    from WB_ACTOR_ALLOC_LOW_FIRST, every one occupied except (optionally) one.

    Only each record's WB_ACTOR_X word is read, which is why that is all this seeds."""
    return {table + (ALLOC_LOW_FIRST + slot) * RECORD_BYTES + ACTOR_X:
            word(FREE_MARKER if slot == free_slot else POOL_OCCUPIED)
            for slot in range(ALLOC_LOW_SLOTS)}


def exit_action_pokes(free_table=None, free_slot=0, selected=TABLE_A32,
                      counter=SEED_ALLOC_COUNT, list_word=SEED_RECORD_LIST):
    """Everything $101be reads: the pointer WB_ACTOR_TABLE_SELECTED holds ON ENTRY, the low pool of
    ALL THREE actor tables, the counter it bumps and the two words it overwrites.

    Seeding three pools rather than one is what makes the ordering observable: `free_table` names
    the ONE table with a free record, and which of the three that is decides whether the counter
    moves. `selected` defaults to the third table, so a port that dropped the first publish and
    allocated out of whatever was already selected is a different answer again.
    """
    out = {}
    for table in (TABLE_DEFAULT, TABLE_A30, TABLE_A32):
        out.update(alloc_pool_pokes(table, free_slot if table == free_table else None))
    out[TABLE_SELECTED] = longword(selected)
    out[EXIT_ALLOC_COUNT] = word(counter)
    out[EFFECT_RECORD_LIST] = word(list_word)
    out[HUD_SLOT_BBC6] = word(SEED_SLOT_BBC6)
    out[EFFECT_STATE_21E4] = word(SEED_STATE_21E4)
    return out


def exit_action_offset(index):
    """WHERE $dfbe's dispatch lands, which is NOT `index * 4`.

    `lsl.w #2` wraps inside the WORD and `lea 0(a6,d0.w),a6` sign-extends the result, so the offset
    is `s16((index * 4) & $ffff)` — and an index three orders of magnitude past the table can come
    back INSIDE it. src/scene.c's dispatch computes the same value; this is the second statement of
    it, which is what makes the aliased cases below a claim rather than a restatement.
    """
    return s16((index * LONGWORD_BYTES) & 0xffff)


def exit_action_entry(index):
    """...and the entry that offset selects, or None when it leaves the table."""
    offset = exit_action_offset(index)
    if not 0 <= offset < EXIT_ACTION_COUNT * LONGWORD_BYTES:
        return None
    return offset // LONGWORD_BYTES


def model_exit_action(index, allocated=False, counter=SEED_ALLOC_COUNT):
    """Every byte the exit action `index` selects leaves, as {address: bytes}.

    The argument is the DESCRIPTOR'S WORD, not the entry — the two differ for the 24 aliased indices
    above, and a model that took the entry would have to resolve them at every call site.

    Entries 2..7 come from test_effects.py's own WORD_SETTERS table rather than being restated —
    those routines' destinations and immediates are that battery's transcription of the
    disassembly, and a second copy here could disagree with it while both stayed green.
    """
    index = exit_action_entry(index)
    assert index is not None, "an index outside the table has no model — this file refuses it"
    if index == 0:
        return {}
    if index == 1:
        written = {HUD_SLOT_BBC6: word(EXIT_SLOT_BBC6),
                   EFFECT_STATE_21E4: word(1),
                   EFFECT_RECORD_LIST: b"\x00",
                   # Written TWICE — the default, then the a30 table — and only the LAST value
                   # survives. Which is why the order is pinned by the allocation's RESULT below and
                   # not by this longword.
                   TABLE_SELECTED: longword(TABLE_A30)}
        if allocated:
            written[EXIT_ALLOC_COUNT] = word((counter + 1) & 0xffff)
        return written
    destination, immediate = STUB_WRITES[EXIT_ACTION_NAMES[index]]
    return {destination: word(immediate)}


STUB_WRITES = {name: (destination, immediate)
               for name, destination, immediate, _abs_long in WORD_SETTERS}


def run_exit_action(case, seeds, model, cap=EXIT_ACTION_CAP):
    info = leaf.run("scene_exit_action_select_a30_table", _EXIT_ACTION_A30,
                    merge_bands(seeded_bytes(model)), case,
                    regs={"_pokes": seeds}, max_insns=cap)
    leaf.assert_written_is(info, model, case)
    return info


def test_the_exit_action_writes_its_four_words_and_bumps_the_counter():
    """The whole of $101be with a free record to find: the HUD slot, the state word, the list's
    first BYTE, the republished table pointer, and the counter one on."""
    case = "exit action, pool free"
    run_exit_action(case, exit_action_pokes(free_table=TABLE_DEFAULT),
                    model_exit_action(1, allocated=True))


def test_a_full_low_pool_leaves_the_counter_alone():
    """`cmpa.l #$0,a1 / bne` — the allocator's "table full" answer is the only thing that stops the
    bump, and the four state writes happen either way."""
    case = "exit action, pool full"
    run_exit_action(case, exit_action_pokes(free_table=None), model_exit_action(1))


# (which table holds the one free record, does the counter move?) — the ORDERING pin. The publish of
# WB_ACTOR_TABLE_DEFAULT, the allocation and the republish as WB_ACTOR_TABLE_A30 all leave the same
# longword behind, so no image byte can separate them; the allocation's RESULT can, and does.
ALLOC_TABLES = (
    (TABLE_DEFAULT, True, "default — the table published BEFORE the call"),
    (TABLE_A30, False, "a30 — the table published after it, and searched by nothing"),
    (TABLE_A32, False, "a32 — what was selected on entry, and overwritten before the call"),
)


@pytest.mark.parametrize("free_table,bumps,label", ALLOC_TABLES,
                         ids=[label.split(" ")[0] for _t, _b, label in ALLOC_TABLES])
def test_the_allocation_runs_against_the_table_published_before_the_call(free_table, bumps, label):
    case = f"exit action allocates from {label}"
    run_exit_action(case, exit_action_pokes(free_table=free_table),
                    model_exit_action(1, allocated=bumps))


@pytest.mark.parametrize("free_slot", [0, ALLOC_LOW_SLOTS // 2, ALLOC_LOW_SLOTS - 1])
def test_a_free_record_anywhere_in_the_pool_is_found_and_then_discarded(free_slot):
    """Wherever the free record is, the counter moves and NOTHING is written through the pointer:
    the exact write set above contains no address inside any actor table, which is what "the
    allocated record is discarded" means on the wire."""
    case = f"exit action, free slot {free_slot}"
    info = run_exit_action(case, exit_action_pokes(free_table=TABLE_DEFAULT, free_slot=free_slot),
                           model_exit_action(1, allocated=True))
    pool = range(TABLE_DEFAULT, TABLE_DEFAULT + (ALLOC_LOW_FIRST + ALLOC_LOW_SLOTS) * RECORD_BYTES)
    assert not [at for at in program_writes(info) if at in pool], (
        f"{case}: the allocated record was written through")


def test_the_counter_bump_wraps_inside_its_word():
    """`addq.w #1,(a1)` — a WORD add through the pointer the `lea` before it loaded, so $ffff goes
    to 0 rather than carrying into the longword above."""
    case = "exit action counter wrap"
    run_exit_action(case, exit_action_pokes(free_table=TABLE_DEFAULT, counter=0xffff),
                    model_exit_action(1, allocated=True, counter=0xffff))


def test_the_record_list_clear_is_a_byte_and_leaves_the_byte_beside_it():
    """`clr.b $b444.l` — the record list's FIRST byte, which its own plate reads as the 0..4 attack
    level. A `clr.w` would take the byte after it as well, and that byte is seeded so it shows."""
    case = "exit action clears one byte"
    info = run_exit_action(case, exit_action_pokes(free_table=TABLE_DEFAULT),
                           model_exit_action(1, allocated=True))
    assert EFFECT_RECORD_LIST + 1 not in program_writes(info), (
        f"{case}: the second byte of the record list was written, so the clear was a word")
    assert harness.make_image(exit_action_pokes(free_table=TABLE_DEFAULT))[
        EFFECT_RECORD_LIST + 1] == SEED_RECORD_LIST & 0xff


def test_the_do_nothing_exit_action_writes_nothing():
    """Entry 0, entered on its own. Its whole body is an `rts`, so the claim is exactly that."""
    case = "exit action none"
    info = leaf.run("scene_exit_action_none", _EXIT_ACTION_NONE, [], case,
                    regs={"_pokes": exit_action_pokes()},
                    max_insns=1 + leaf.RUNNER_SENTINEL_INSN)
    assert not program_writes(info), f"{case}: it wrote {sorted(program_writes(info))}"


# --- $dfbe: the exit tail, entered on its own ----------------------------------------------------
#
# It dispatches the descriptor's exit action, takes the box down, and hands stage_load_window three
# registers: the LEVEL MAP, WB_TILE_BITMAPS and the WB_STAGE_START_TABLE entry the descriptor names.
# Then five state words are cleared and it returns.
#
# THE LEVEL MAP IS WB_MAP_ROW_STRIDE'S OWN ADDRESS. `lea $22090.l,a0` names the same word the
# collision map is addressed from and the same word stage_publish_scroll_state multiplies the start
# cell by — so for THIS caller the map's header width and the global stride are one word, where
# test_stage.py's own cases keep them deliberately apart. That is why the seeding below hands
# test_stage.py's helpers `map_ptr=LEVEL_MAP` and this file's own stride.
LEVEL_MAP = MAP_ROW_STRIDE

# The highest byte the eleven build cursors reach, derived from the builder's own arithmetic rather
# than stated: one map row's allowance past the last cursor. Two structures this battery seeds sit
# above it, and `test_the_seeded_structures_clear_the_level_map` is what keeps that true.
COMPOSED_MAP_TOP = max(build_cursors(0, 0, MAP_STRIDE, LEVEL_MAP)) + MAP_STRIDE

COMPOSED_TUNE = 3                 # a song id, so the tail's PLAY arm runs the real chain
COMPOSED_PALETTE = 1              # ...and a row WB_PALETTE_TABLE holds
COMPOSED_FOLLOW = (0x180, 0xc0)   # the followed object's position, so the follow words are non-zero
# Plain RAM past every band this battery seeds, for the one case whose start pointer is not one of
# the table's own eight entries.
OWN_START_RECORD = RECORD_WRITE_TARGET + 0x200
TEXT_BOX_ACTIVE_SET = wb("TEXT_BOX_ACTIVE_SET")
STATE_SET = 0xffff                # what every word $dfbe clears is seeded with, so the clear shows

# $dfbe's own instructions over the two routines it calls. THE RUNNER'S SENTINEL IS COUNTED ONCE:
# LOAD_WINDOW_INSN_CAP already carries one (through set_palette's cap), so the exit action's
# INSTRUCTION count goes in here rather than its CAP — adding both was the double-count batch 24
# recorded, recurred one tier up.
EXIT_AND_RELOAD_CAP = LOAD_WINDOW_INSN_CAP + EXIT_ACTION_INSN + EXIT_AND_RELOAD_INSN
RELOAD_FRAME_CAP = BOSS_CAP + EXIT_AND_RELOAD_CAP

_EXIT_AND_RELOAD = leaf.image_glue("scene_exit_and_reload")


def start_table_slot(index):
    """WHERE $dfbe reads the start pointer from: `lsl.w #2` then a SIGN-EXTENDED word add, so an
    index outside the eight entries is a real address on either side of the table rather than a
    wrapped one — which is what the out-of-range case below drives."""
    return (STAGE_START_TABLE + s16((index << 2) & 0xffff)) & 0xffffffff


def start_table_entry(image, index):
    """...and the pointer it finds there, out of whichever image is being asked."""
    at = start_table_slot(index)
    return int.from_bytes(bytes(image[at:at + LONGWORD_BYTES]), "big")


def start_record(tune=COMPOSED_TUNE, palette=COMPOSED_PALETTE):
    """One WB_START_RECORD_LEN-byte start record, laid out by the header's own field offsets rather
    than by position.

    The two words below WB_START_FOLLOW_X are the map cell the window opens on and are left ZERO —
    that is the cell test_stage.py's map seeding is built around, so a moved window would read cells
    no case seeded. The eight table entries point into the startup relocator's own bytes, dead by
    the time this table is used, so every case seeds the record its entry lands on.
    """
    record = bytearray(START_RECORD_LEN)
    record[START_FOLLOW_X:START_FOLLOW_X + WORD_BYTES] = word(COMPOSED_FOLLOW[0])
    record[START_FOLLOW_Y:START_FOLLOW_Y + WORD_BYTES] = word(COMPOSED_FOLLOW[1])
    record[START_TUNE] = tune & 0xff
    record[START_PALETTE] = palette
    return bytes(record)


def reload_layers(case, exit_action, start_index, start, tune, latch, free_table, middle=()):
    """The poke layers a run through $dfbe needs, in the order a later one may overwrite an earlier.

    LAYERED WITH `leaf.overlay` AND NOT `dict.update`, because these layers genuinely OVERLAP: the
    level map and the collision map are one region, the actor pools sit inside the band the boss arm
    is seeded over, and for start-table entries 4..7 the ten-byte record sits inside the descriptor
    band's lower margin. A keyed update would silently shorten whichever band lost its key, which is
    the hazard `overlay`'s own docstring records.

    THE ORDER IS THE ARGUMENT, and every position in it was earned:

      * `state` is the tail's defaults — every word it clears, seeded SET so the clear shows — and
        it goes FIRST so that a composed case's `middle` (the scene arm's own seeding, which owns
        the two mode flags, the box byte and the pending word) overrides whichever of them it cares
        about;
      * `descriptor` goes AFTER `middle`, because the scene arm seeds the WHOLE descriptor band with
        address-keyed bytes and would otherwise bury the two words the tail reads out of it — which
        it did, and the run walked off into a garbage start record rather than failing;
      * the actor pools come next, because the boss arm's slot band covers WB_ACTOR_TABLE_A32's and
        the exit action's allocation has to run against a pool THE CASE DECLARED;
      * and the hinge's 180 KB is last, because it is the biggest and reads the map the collision
        band overlaps.
    """
    state = {TEXT_BOX_ACTIVE: bytes([TEXT_BOX_ACTIVE_SET]),
             STATE_FLAG_A34: word(STATE_SET), PANEL_FRAME_HOLD: word(STATE_SET),
             FLAG_A30: word(STATE_SET), FLAG_A32: word(STATE_SET),
             MESSAGE_PENDING: word(MESSAGE_PENDING_SET)}
    descriptor = {DESCRIPTOR_PTR: longword(DESCRIPTOR),
                  DESCRIPTOR + SCENE_EXIT_ACTION: word(exit_action),
                  DESCRIPTOR + SCENE_START_INDEX: word(start_index)}
    # `frozen=True` seeds WB_SCROLL_FOLLOW_FROZEN SET and the MODEL below passes False: $dfbe clears
    # the word one instruction before the call, so this path always hands the hinge an unfrozen
    # scroll however it was entered. Seeding it set is what makes that clear observable.
    hinge = load_window_pokes(case, start, TILE_BITMAPS, True, latch, record=start_record(tune),
                              map_ptr=LEVEL_MAP, stride=MAP_STRIDE)
    return [state, *middle, descriptor, exit_action_pokes(free_table=free_table), hinge]


def model_exit_and_reload(image, exit_action, start, latch, free_table):
    """Every byte $dfbe leaves, in the order it leaves them: the dispatched action's, the box byte,
    the freeze word, the whole of stage_load_window's — taken from the battery that owns it — and
    the five state words."""
    written = dict(model_exit_action(exit_action, allocated=free_table == TABLE_DEFAULT))
    written[TEXT_BOX_ACTIVE] = b"\x00"
    written[SCROLL_FOLLOW_FROZEN] = word(0)
    written.update(model_load_window(image, start, TILE_BITMAPS, False, latch,
                                     map_ptr=LEVEL_MAP, stride=MAP_STRIDE))
    for addr in (STATE_FLAG_A34, PANEL_FRAME_HOLD, FLAG_A30, FLAG_A32, MESSAGE_PENDING):
        written[addr] = word(0)
    return written


def reload_seeds_and_model(case, exit_action, start_index, start, tune, latch, free_table,
                           extra_layers, middle=()):
    """The composed image and the model of what $dfbe leaves on it, with two guards between them.

    The FIRST is `assert_bands_are_seeded` over each layer: `overlay` merges byte by byte, so a
    layer can be partly covered by a later one, and a layer that vanished entirely would leave its
    band running on the .PRG's own residue. The SECOND is that THE THREE VALUES THIS FUNCTION IS
    TOLD ABOUT are the ones the run will actually read — the two descriptor words and the start
    pointer the second of them selects. Every one of those is a layered seed that a later layer
    could bury (and the descriptor words were, before the order above was fixed), so a model built
    from the arguments alone would describe a run that did not happen.
    """
    layers = reload_layers(case, exit_action, start_index, start, tune, latch, free_table,
                           middle) + list(extra_layers)
    seeds = overlay(*layers)
    for layer in layers:
        leaf.assert_bands_are_seeded(seeds, merge_bands(seeded_bytes(layer)), case)

    image = harness.make_image(seeds)
    for field, declared in ((SCENE_EXIT_ACTION, exit_action), (SCENE_START_INDEX, start_index)):
        held = leaf.u16(image, DESCRIPTOR + field)
        assert held == declared & 0xffff, (
            f"{case}: descriptor word {field} holds {held:#06x}, not the {declared:#06x} this case "
            f"declared — a later seed layer buried it")
    held = start_table_entry(image, start_index)
    assert held == start, (
        f"{case}: start table slot {start_index} ({start_table_slot(start_index):#x}) holds "
        f"{held:#x}, not the {start:#x} record this case seeded")
    return seeds, model_exit_and_reload(image, exit_action, start, latch, free_table)


def run_exit_and_reload(case, exit_action=0, start_index=0, start=None, tune=COMPOSED_TUNE,
                        latch=LATCH_UNMATCHED, free_table=None, extra_layers=()):
    """One run of $dfbe entered at its own address, compared against the composed model."""
    if start is None:
        start = start_table_entry(harness.BASE_IMAGE, start_index)
    seeds, written = reload_seeds_and_model(case, exit_action, start_index, start, tune, latch,
                                            free_table, extra_layers)
    info = leaf.run("scene_exit_and_reload", _EXIT_AND_RELOAD, merge_bands(seeded_bytes(written)),
                    case, regs={"_pokes": seeds}, max_insns=EXIT_AND_RELOAD_CAP, poison=False,
                    psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    leaf.assert_written_is(info, written, case)
    return info


def test_the_seeded_structures_clear_the_level_map():
    """The level map is a case's own seed and so are the marker cell and the record list, and the
    map's eleven cursors are the widest of the three. If any of those addresses moves, this is
    where the overlap shows rather than in a case blaming its own seeding."""
    for name, addr in (("the marker cell", MARKER_CELL), ("the record list", RECORD_WRITE_TARGET)):
        assert addr - SEED_MARGIN >= COMPOSED_MAP_TOP, (
            f"{name} at {addr:#x} is inside the level map, which reaches {COMPOSED_MAP_TOP:#x}")


# The exit action and the start index are two DIFFERENT descriptor words, and the sweep below pairs
# them so that no row has them equal — a port that read word 18 for both, or word 28 for both, picks
# the wrong table on every one of the eight rows rather than agreeing by accident on the diagonal.
EXIT_SWEEP = [(action, (action + 3) % STAGE_START_TABLE_ENTRIES)
              for action in range(EXIT_ACTION_COUNT)]


@pytest.mark.parametrize("exit_action,start_index", EXIT_SWEEP,
                         ids=[f"action{a}-start{s}" for a, s in EXIT_SWEEP])
def test_every_exit_action_and_every_start_table_entry_runs_the_whole_tail(exit_action,
                                                                          start_index):
    """Both tables, whole: each of the eight exit actions dispatched and each of the eight start
    entries loaded, through the dispatched action, the stage reload and the five clears."""
    run_exit_and_reload(f"exit action {exit_action}, start {start_index}",
                        exit_action=exit_action, start_index=start_index,
                        free_table=TABLE_DEFAULT if exit_action == 1 else None)


# One aliased index per band above the table's own 0..7, each landing on a DIFFERENT entry — so a
# port that guarded the raw index and silently did nothing runs three different write sets short.
EXIT_ACTION_ALIASES = (0x4002, 0x8003, 0xc001)


def test_the_indices_that_dispatch_are_the_four_bands_and_not_just_the_first():
    """`lsl.w #2` wraps inside the WORD, so THIRTY-TWO of the 65,536 index values reach the table
    and only eight of them are the obvious ones. Enumerated over the whole word rather than
    asserted, because the claim is about which values alias and not about a formula."""
    reaching = [index for index in range(0x10000) if exit_action_entry(index) is not None]
    assert reaching == [band + entry
                        for band in (0x0000, 0x4000, 0x8000, 0xc000)
                        for entry in range(EXIT_ACTION_COUNT)]
    assert all(exit_action_entry(index) == index & (EXIT_ACTION_COUNT - 1) for index in reaching)


@pytest.mark.parametrize("index", EXIT_ACTION_ALIASES,
                         ids=[f"{index:#06x}" for index in EXIT_ACTION_ALIASES])
def test_an_index_whose_offset_wraps_back_into_the_table_dispatches_that_entry(index):
    """The 24 indices a guard on the RAW index would refuse while the original ran ported code.
    Each row is a whole differential: the entry's own write set has to appear, so "the port did
    nothing here" is a failure and not a quiet agreement."""
    entry = exit_action_entry(index)
    assert entry not in (None, 0), "an aliased row that selected entry 0 would write nothing"
    run_exit_and_reload(f"exit action index {index:#06x} -> entry {entry}", exit_action=index,
                        free_table=TABLE_DEFAULT if entry == 1 else None)


def test_the_freeze_word_is_cleared_before_the_hinge_reads_it():
    """`clr.w $d76.w` sits ONE instruction before the `jsr`, so a scene entered with the scroll
    frozen still gets its WB_SCROLL_FOLLOW_X/_Y recomputed. Every case here seeds the flag SET; this
    one names the consequence, which is the two words the hinge would otherwise leave stale."""
    case = "frozen scroll unfrozen by the exit"
    info = run_exit_and_reload(case)
    for at in (wb("SCROLL_FOLLOW_X"), wb("SCROLL_FOLLOW_Y")):
        assert at in program_writes(info), (
            f"{case}: {at:#x} was not written, so the hinge still saw a frozen scroll")


def test_a_start_index_outside_the_table_reads_the_longword_it_lands_on():
    """NOTHING bounds the start index: `lsl.w #2` wraps inside the word and `lea 0(a1,d0.w),a1`
    sign-extends it. An index of $ffff therefore reads the longword FOUR bytes BELOW the table and
    hands stage_load_window whatever it names — a data read, which this port reproduces, and the
    deliberate contrast with the EXIT-ACTION index one word away, which it refuses.

    The shipped longword there is $01010101, which is past the whole address space this image
    covers, so the case seeds that slot with a record of its own — declaring the pointer rather
    than wandering into whatever the .PRG happens to hold below the table.
    """
    case = "start index past the table"
    index = 0xffff
    assert start_table_slot(index) == STAGE_START_TABLE - LONGWORD_BYTES, (
        "an index of $ffff is supposed to read the longword immediately BELOW the table")
    run_exit_and_reload(case, start_index=index, start=OWN_START_RECORD,
                        extra_layers=[{start_table_slot(index): longword(OWN_START_RECORD),
                                       OWN_START_RECORD: start_record()}])


def test_the_stop_arm_of_the_tail_is_reachable_through_the_exit():
    """A start record whose tune byte is NEGATIVE stops the sound module instead of starting a song,
    and both arms of that tail are reachable from a scene exit — this is the one that is."""
    case = "exit tail stops the module"
    info = run_exit_and_reload(case, tune=0xff)
    assert_psg_state(info, {PSG_REG_MIXER: PLAY_SONG_MIXER}, case)


# --- the four transfers, run WHOLE ---------------------------------------------------------------
#
# Each of these was a `stop_pc` checkpoint at $dfbe until batch 27; each is now the arm, the exit,
# the dispatched action and the whole stage reload, ending at the original's own `rts`. The
# checkpoint's surface and what replaced it are argued in this file's docstring — briefly: every
# arm's own write set is DISJOINT from the tail's, so no arm byte is hidden by an overwrite, and
# each case still states that write set exactly.

def run_frame_to_reload(case, scene_seeds, via, prefix=(), prefix_bands=(), exit_action=0,
                        start_index=0, free_table=None, cap=RELOAD_FRAME_CAP):
    """One `scene_run_frame` case that leaves through $dfbe, run end to end.

    `prefix` is what the ARM writes before the transfer, as {address: bytes}; `prefix_bands` is the
    escape hatch for the boss arm alone, whose eighteen actor records the fragment cases already
    assert field by field. Everything outside those bands is compared for EQUALITY against the model.

    THE DISJOINTNESS THIS FILE'S DOCSTRING ARGUES IS CHECKED HERE RATHER THAN TRUSTED. The whole
    reason a full run can replace the old checkpoint is that no arm byte is later overwritten by the
    tail — and a `dict.update` merging the two would express the opposite silently, by preferring
    the tail. If an arm ever does write into the tail's set, this says which address rather than
    quietly comparing the wrong value there.
    """
    start = start_table_entry(harness.BASE_IMAGE, start_index)
    seeds, tail = reload_seeds_and_model(case, exit_action, start_index, start, COMPOSED_TUNE,
                                         LATCH_UNMATCHED, free_table, (), middle=[scene_seeds])
    clash = sorted(seeded_bytes(dict(prefix)) & seeded_bytes(tail))
    assert not clash, (
        f"{case}: the arm and the tail both write {len(clash)} byte(s), e.g. {clash[0]:#x} — the "
        f"end-to-end run cannot see the arm's value there, so this case needs its old checkpoint")
    written = dict(prefix)
    written.update(tail)
    info = run_frame(case, seeds, EXIT_RELOAD, cap=cap, via=via,
                     allowed=merge_bands(seeded_bytes(written)) + list(prefix_bands),
                     psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    declared = {at for base, length in prefix_bands for at in range(base, base + length)}
    leaf.assert_written_is(info, written, case, declared)
    return info


@pytest.mark.parametrize("script_byte", [0x80, 0xff])
def test_a_script_byte_with_its_sign_bit_set_ends_the_scene(script_byte):
    """The terminator is a SIGN test and it is not consumed: the arm reaches the exit having written
    nothing at all, cursor included — so everything the run leaves behind is $dfbe's."""
    case = f"speech terminator {script_byte:#04x}"
    run_frame_to_reload(case, speech_pokes(case, JOY1_FIRE, script_byte), via="speech terminator",
                        cap=SPEECH_CAP + EXIT_AND_RELOAD_CAP)


def test_a_leaving_scene_runs_the_exit_action_its_descriptor_names():
    """The whole chain in one run: the speech arm's terminator, $dfbe's dispatch into $101be, that
    routine's four state words and its allocation out of WB_ACTOR_TABLE_DEFAULT, and the reload.
    Every other case here takes entry 0, whose body is an `rts`, so this is where the descriptor's
    own word 18 is shown to steer a scene EXIT and not only a direct call."""
    case = "speech terminator runs exit action 1"
    run_frame_to_reload(case, speech_pokes(case, JOY1_FIRE, 0x80), via="speech terminator",
                        exit_action=1, free_table=TABLE_DEFAULT,
                        cap=SPEECH_CAP + EXIT_AND_RELOAD_CAP)


@pytest.mark.parametrize("edge,box", [(JOY1_FIRE, 0xff), (0xff, 0x01), (0x00, 0x00)])
def test_a_pending_message_leaves_for_nothing_when_the_record_is_not_charged(edge, box):
    """`tst.w 42(a1) / beq` — a zero WB_SHOP_LEAVE_CHARGED reaches the exit with no write at all,
    budget included."""
    case = f"leave free edge={edge:#04x} box={box:#04x}"
    run_frame_to_reload(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                     (SHOP_RECORD + LEAVE_CHARGED, 0)),
                                         bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                        via="leave uncharged")


@pytest.mark.parametrize("budget", [0x0010, MESSAGE_COST, MESSAGE_COST + 1])
def test_a_charged_leave_spends_the_message_cost_first(budget):
    """The other arm: a nonzero WB_SHOP_LEAVE_CHARGED spends WB_SHOP_MESSAGE_COST and only then
    leaves. Every budget here stays non-negative, so that spend is the arm's WHOLE write set — and
    it is nowhere near anything $dfbe or the hinge touches, which is the disjointness the end-to-end
    run rests on."""
    case = f"leave charged budget={budget}"
    run_frame_to_reload(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                      (SHOP_RECORD + LEAVE_CHARGED, 1),
                                                      (SHOP_RECORD + VISIT_BUDGET, budget)),
                                         bytes_=joystick(JOY1_FIRE) + ((TEXT_BOX_ACTIVE, 0xff),)),
                        via="leave charged",
                        prefix={SHOP_RECORD + VISIT_BUDGET: word(budget - MESSAGE_COST)})


@pytest.mark.parametrize("exit_request", [0x0001, 0xffff])
def test_an_exit_request_alone_leaves_the_scene(exit_request):
    """The arm the power-up path at $10768 raises: the request is cleared and the scene ends."""
    case = f"boss exit request {exit_request:#06x}"
    run_frame_to_reload(case, boss_pokes(case, flag=0, exit_request=exit_request),
                        via="boss exit", prefix={SCENE_EXIT_REQUEST: word(0)},
                        cap=BOSS_CAP + EXIT_AND_RELOAD_CAP)


def test_the_hud_slot_takes_the_scene_out_after_the_fragments_are_built():
    """`tst.b $bbc4.l / bne $df92` — this arm is that slot's only reader among the reconstructed
    routines, and it SKIPS the exit-request test rather than replacing it: the request is zero here
    and the scene ends anyway. The eighteen actor records the arm writes are the one band this file
    declares rather than models; every other byte of the run is compared against the model."""
    case = "boss hud slot leaves"
    info = run_frame_to_reload(case, boss_pokes(case, flag=0xffff, variant=1, slot_bbc4=0x01),
                               via="boss exit", prefix_bands=SLOT_BAND,
                               prefix={SCENE_EXIT_REQUEST: word(0), BOSS_DEFEAT_FLAG: word(0)})
    assert leaf.read_int(info, BOSS_SLOTS + ACTOR_TYPE, WORD_BYTES, case) == BOSS_TYPE_1
