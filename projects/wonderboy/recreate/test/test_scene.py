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
import loader
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, WORD_MASK, assert_entry_is, branch_w_to, bsr_w, case_salt,
                  clr_b_abs_l, clr_b_ind, clr_w_abs_l, clr_w_abs_w, cmpi_w_abs_l, cmpi_w_d16,
                  jsr_abs_l,
                  keyed_block, lea_abs_l, lea_indexed, longword, lsl_w_imm_dn, merge_bands,
                  move_b_ind_dn,
                  move_l_imm_abs_l, move_w_imm_abs_l, move_w_imm_abs_w, move_w_ind_dn,
                  movea_l_abs_l, opcode, overlay, program_writes, run_reaching, s16, seeded_bytes,
                  sub_w_dn_d16, tst_w_abs_w, word,
                  # ...and what batch 41 phase B's spawn-tree pin adds, five of them hoisted to
                  # leaf.py by this batch because it was each one's third or fourth copy
                  addq_l_an, btst_imm_dn, clr_w_dn, cmp_w_dn_dn, cmp_w_imm_dn, cmpi_b_abs_l,
                  lea_d16, move_b_imm_ind, move_b_postinc_dn, move_w_imm_d16, move_w_imm_dn,
                  move_w_abs_l_dn, move_w_postinc_dn, moveq_0_dn, movea_l_indexed)
from layout import wb
# The reload tail RUNS stage_load_window, so a composed case's write set CONTAINS that routine's.
# The model, the seeds, the instruction cap and the unmatched latch all come from the battery that
# owns them — two copies could disagree while both stayed green, which is the rule test_stage.py
# itself follows towards test_hud.py and test_sound.py.
from test_stage import (LATCH_UNMATCHED, LOAD_WINDOW_INSN_CAP,               # noqa: E402
                        RAW_TILE_BANK, build_cursors, load_window_pokes, model_load_window)
from test_stage import MAP as STAGE_MAP                                      # noqa: E402
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
REFUSED_COUNT = wb("SHOP_REFUSED_COUNT")
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

# $1b46, whole, and the SIX INSTRUCTIONS $de94 spells again inline. The neighbours are one CELL
# either side, which on a map of one byte per cell is `1(a6)` and `-1(a6)`; the RIGHT one is tested
# first. What differs between the two originals is only the ending — this one falls to the `rts`
# where $de94 takes `jmp $1ab4.w` — which is why src/scene.c has one body returning a flag.
MARKER_PAIR_ENTRY = 0x1b46
NEIGHBOUR_CELL = wb("MAP_NEIGHBOUR_CELL")


def cmp_b_d16_dn(reg, base, displacement):
    """`cmp.b d16(An),Dn` — a neighbour against the code the cell held."""
    # ALSO IN test_player.py — second copy.
    return opcode(0xb028 | (reg << 9) | base) + word(displacement)


MARKER_PAIR_BYTES = leaf.asm(MARKER_PAIR_ENTRY, [
    move_b_ind_dn(D0, A6),
    clr_b_ind(A6),
    cmp_b_d16_dn(D0, A6, NEIGHBOUR_CELL),
    leaf.bcc(BNE_W, "left"),
    leaf.clr_b_d16(A6, NEIGHBOUR_CELL),
    leaf.bcc(BRA_W, "out"),
    leaf.lab("left"),
    cmp_b_d16_dn(D0, A6, -NEIGHBOUR_CELL & 0xffff),
    leaf.bcc(BNE_W, "out"),
    leaf.clr_b_d16(A6, -NEIGHBOUR_CELL & 0xffff),
    leaf.lab("out"),
    RTS,
])

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
    # ...and $1b46, whole. Six instructions and two branches, and it is $de94's twin: the SAME six
    # spelt inline inside `scene_spend_visit_budget`, differing only in the ending.
    "scene_clear_marker_pair": (MARKER_PAIR_ENTRY, MARKER_PAIR_BYTES),
}
RECORDED_PINS = 21


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

def assert_pinned_instruction(label):
    """One pinned instruction, against the bytes at its own address. Shared by the two
    parametrized tests over it — see the spawn tree's own, which explains why there are two."""
    addr, expected = ENTRY_BYTES[label]
    actual = bytes(harness.BASE_IMAGE[addr:addr + len(expected)])
    assert actual == expected, (
        f"{label} @ {addr:#x} is {actual.hex()}, not the {expected.hex()} this battery "
        f"reconstructs")


@pytest.mark.parametrize("label", sorted(ENTRY_BYTES))
def test_the_instruction_at_each_pinned_address_is_the_one_reconstructed(label):
    """Each pinned instruction, against the bytes at its own address."""
    assert_pinned_instruction(label)


@pytest.mark.parametrize("name", ["scene_run_frame", "scene_spend_visit_budget",
                                  "scene_exit_and_reload", "scene_exit_action_select_a30_table",
                                  "scene_clear_marker_pair"])
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
    ("scene_clear_marker_pair", 0x1b68, "actor_alloc_slot_low"),
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


# --- $1b46: the marker-pair clear, entered at its own address ------------------------------------
#
# The TWIN of the six instructions inside the budget spend above, and the reason src/scene.c has one
# body for both. Its two callers are $1aac and $1ef2, both inside the $19ac tree, and both reach it
# with a6 already holding WB_SCENE_MARKER_CELL_PTR's longword — which is why the differential enters
# it with that register rather than with a pointer of the case's own.
_CLEAR_MARKER = leaf.register_glue("scene_clear_marker_pair", [ctypes.c_uint32], ctypes.c_int)
MARKER_PAIR_CAP = 16
MARKER_PAIR_MATCHED, MARKER_PAIR_ALONE = 1, 0


def marker_pokes(case, cell_left, cell, cell_right):
    return pokes(case, bytes_=((MARKER_CELL - 1, cell_left), (MARKER_CELL, cell),
                               (MARKER_CELL + 1, cell_right)))


@pytest.mark.parametrize("left,code,right,cleared,matched", [
    (0x11, 0x22, 0x22, MARKER_CELL + 1, MARKER_PAIR_MATCHED),
    (0x22, 0x22, 0x33, MARKER_CELL - 1, MARKER_PAIR_MATCHED),
    # BOTH match: the RIGHT one is tested first, so the left neighbour survives. That is the case
    # neither budget row above can state, because each seeds only one twin.
    (0x22, 0x22, 0x22, MARKER_CELL + 1, MARKER_PAIR_MATCHED),
    (0x11, 0x22, 0x33, None, MARKER_PAIR_ALONE),
    # A cell already holding ZERO matches a zero neighbour, because the compare is against the code
    # the cell held and the `clr.b` above it does not change the answer.
    (0x11, 0x00, 0x00, MARKER_CELL + 1, MARKER_PAIR_MATCHED),
])
def test_the_marker_clear_clears_the_cell_and_the_FIRST_neighbour_that_matches(left, code, right,
                                                                              cleared, matched):
    """Right first, left second, and the flag says whether either did — which is the whole of what
    `scene_spend_visit_budget` needs to choose between its `rts` and its `jmp $1ab4.w`."""
    case = f"marker pair {left:#04x} [{code:#04x}] {right:#04x}"
    seeds = marker_pokes(case, left, code, right)
    allowed = [(MARKER_CELL - 1, 3)]
    info = leaf.run("scene_clear_marker_pair", _CLEAR_MARKER(MARKER_CELL), allowed, case,
                    regs={"a6": MARKER_CELL, "_pokes": seeds}, max_insns=MARKER_PAIR_CAP)
    assert info["ret"] == matched
    written = program_writes(info)
    expected = {MARKER_CELL} | ({cleared} if cleared is not None else set())
    assert set(written) == expected, (
        f"{case}: wrote {[hex(a) for a in sorted(written)]}, not {[hex(a) for a in sorted(expected)]}")
    for addr in expected:
        assert leaf.read_int(info, addr, 1, case) == 0


def test_the_marker_clear_is_the_SAME_six_instructions_the_budget_spend_holds_inline():
    """The de-duplication, as a byte comparison rather than as a claim in a comment. $de94's copy is
    identical up to the branch that ends it: the first four instructions and the two `clr.b`s are the
    same bytes, and only the two branch words and the `jmp $1ab4.w` between them differ."""
    twin = 0xde94
    same = len(move_b_ind_dn(D0, A6)) + len(clr_b_ind(A6)) + len(cmp_b_d16_dn(D0, A6,
                                                                             NEIGHBOUR_CELL))
    assert (bytes(harness.BASE_IMAGE[twin:twin + same])
            == MARKER_PAIR_BYTES[:same]), "the two originals do not open with the same instructions"
    assert (bytes(harness.BASE_IMAGE[twin + same + 4:twin + same + 4 + 4])
            == leaf.clr_b_d16(A6, NEIGHBOUR_CELL)), "the twin's right-hand clear is not the same"


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
     ((MESSAGE_PENDING, MESSAGE_PENDING_SET), (SHOP_RECORD + REFUSED_COUNT, 1)),
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
    """`tst.w 42(a1) / beq` — a zero WB_SHOP_REFUSED_COUNT reaches the exit with no write at all,
    budget included."""
    case = f"leave free edge={edge:#04x} box={box:#04x}"
    run_frame_to_reload(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                     (SHOP_RECORD + REFUSED_COUNT, 0)),
                                         bytes_=joystick(edge) + ((TEXT_BOX_ACTIVE, box),)),
                        via="leave uncharged")


@pytest.mark.parametrize("budget", [0x0010, MESSAGE_COST, MESSAGE_COST + 1])
def test_a_charged_leave_spends_the_message_cost_first(budget):
    """The other arm: a nonzero WB_SHOP_REFUSED_COUNT spends WB_SHOP_MESSAGE_COST and only then
    leaves. Every budget here stays non-negative, so that spend is the arm's WHOLE write set — and
    it is nowhere near anything $dfbe or the hinge touches, which is the disjointness the end-to-end
    run rests on."""
    case = f"leave charged budget={budget}"
    run_frame_to_reload(case, shop_pokes(case, words=((MESSAGE_PENDING, MESSAGE_PENDING_SET),
                                                      (SHOP_RECORD + REFUSED_COUNT, 1),
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


# =================================================================================================
# $19ac — THE SCENE-SPAWN TREE (batch 41 phase B)
#
# What ENTERS a scene, where everything above runs one once a frame, and it is driven by the SAME
# descriptor: a byte-coded script read with a walking cursor. Three arms, and each ends by handing
# `stage_load_window` a map and a tile bank, so every full case here composes with test_stage.py's
# battery exactly as the reload cases above do.
#
# WHAT IS REAL DATA AND WHAT IS SEEDED. The speech scripts, the gate table, the glyph fonts, the
# shipped start records and the shop-record pointer table are the game's own bytes and no case seeds
# any of them — a speech case posts the id the shipped script really holds. The descriptor, the shop
# record, the resource table's two price sprites and the map/tile bank the arms load are past the
# program or unshipped, so those are the case's own, address-keyed.
#
# KNOWINGLY NOT PINNED
#   * a gate index outside 1..3. The `lsl.w #2` on a script BYTE cannot wrap or turn negative, so
#     252 of the 256 values `jsr` through a longword outside the four-entry table — the refusal
#     src/blit.c's sprite dispatch makes, and this battery refuses them as inputs the same way it
#     refuses an out-of-table exit action.
#   * a map-bank index whose sign-extended offset leaves the seven entries. That one is a DATA read
#     and the port follows it, but a case that drove it would hand the hinge two arbitrary pointers
#     and measure the scroll engine rather than this tree.
#   * WHAT A SHIPPED DESCRIPTOR SELECTS, for the reason the head of this file gives: the descriptor
#     table is loaded from disk and the .PRG ships zeros for it.

SPAWN_GATE_TABLE = wb("SPAWN_GATE_TABLE")
SPAWN_GATE_COUNT = wb("SPAWN_GATE_COUNT")
SPAWN_GATE_ENTRY_0 = wb("SPAWN_GATE_ENTRY_0_NOT_AN_ADDRESS")
SPAWN_GATE_REFUSED_SCRIPT = wb("SPAWN_GATE_REFUSED_SCRIPT")
SPAWN_GATE_SLOT = wb("SCENE_SPAWN_GATE_SLOT")
HUD_SLOT_BBC8 = wb("HUD_SLOT_BBC8")

MAP_BANK_TABLE = wb("SCENE_MAP_BANK_TABLE")
MAP_BANK_COUNT = wb("SCENE_MAP_BANK_COUNT")
MAP_BANK_BYTES = wb("SCENE_MAP_BANK_BYTES")
MAP_BANK_TILES = wb("SCENE_MAP_BANK_TILES")
MAP_BANK_INDEX = wb("SCENE_MAP_BANK_INDEX")
BOSS_MAP_BANK_OFFSET = wb("SCENE_BOSS_MAP_BANK_OFFSET")

START_RECORD_BOSS = wb("SCENE_START_RECORD_BOSS")
START_RECORD_SHOP = wb("SCENE_START_RECORD_SHOP")
START_RECORD_SHOP_ALT = wb("SCENE_START_RECORD_SHOP_ALT")
START_RECORD_SPEECH = wb("SCENE_START_RECORD_SPEECH")
STAGE_START_RECORDS = wb("STAGE_START_RECORDS")

SPAWN_PAIR_DX = wb("SCENE_SPAWN_PAIR_DX")
FROZEN_SET = wb("SCROLL_FOLLOW_FROZEN_SET")
# ...and the mode flags' own, which is a different constant even though it is the same word.
STATE_FLAG_SET = wb("STATE_FLAG_SET")
LATE_STAGE_FIRST = wb("SCENE_LATE_STAGE_FIRST")
LATE_STAGE_SPRITE = wb("SCENE_LATE_STAGE_SPRITE")
SPEECH_LIFETIME_HELD = wb("SCENE_SPEECH_LIFETIME_HELD")
STAGE_NUMBER = wb("STAGE_NUMBER")
ACTOR_SPRITE = wb("ACTOR_SPRITE")
ACTOR_TABLE_END = wb("ACTOR_TABLE_END")
TABLE_A30_SLOTS = 19              # what actor_table_reset writes, and where the terminator sits
TABLE_A30_END = TABLE_A30 + TABLE_A30_SLOTS * RECORD_BYTES

SHOP_ENTER_MSG_FIRST = wb("SHOP_ENTER_MSG_FIRST")
SHOP_ENTER_MSG_SECOND = wb("SHOP_ENTER_MSG_SECOND")
SHOP_ENTER_MSG_LATER = wb("SHOP_ENTER_MSG_LATER")
SHOP_ENTER_COUNT = wb("SHOP_ENTER_COUNT")
SHOP_SIGN_SPRITE = wb("SHOP_SIGN_SPRITE")
SHOP_SIGN_SPRITE_INTRO = wb("SHOP_SIGN_SPRITE_INTRO")
SHOP_SIGN_XY = wb("SHOP_SIGN_XY")
SHOP_ITEM1_SPRITE = wb("SHOP_ITEM1_SPRITE")
SHOP_ITEM2_SPRITE = wb("SHOP_ITEM2_SPRITE")
BROKE_MSG_FIRST = wb("SHOP_BROKE_MSG_FIRST")
BROKE_MSG_SECOND = wb("SHOP_BROKE_MSG_SECOND")
BROKE_MSG_THIRD = wb("SHOP_BROKE_MSG_THIRD")
GREET_COUNTDOWN_RESET = wb("SHOP_GREET_COUNTDOWN_RESET")
DISPLAY_ITEM1_XY = wb("SHOP_DISPLAY_ITEM1_XY")
DISPLAY_ITEM2_XY = wb("SHOP_DISPLAY_ITEM2_XY")
DISPLAY_LEAVE_XY = wb("SHOP_DISPLAY_LEAVE_XY")
DISPLAY_PRICE1_XY = wb("SHOP_DISPLAY_PRICE1_XY")
DISPLAY_PRICE2_XY = wb("SHOP_DISPLAY_PRICE2_XY")
DISPLAY_EXTRA_XY = wb("SHOP_DISPLAY_EXTRA_XY")
DISPLAY_LEAVE_SPRITE = wb("SHOP_DISPLAY_LEAVE_SPRITE")
DISPLAY_PRICE1_SPRITE = wb("SHOP_DISPLAY_PRICE1_SPRITE")
DISPLAY_PRICE2_SPRITE = wb("SHOP_DISPLAY_PRICE2_SPRITE")
DISPLAY_EXTRA_SPRITE = wb("SHOP_DISPLAY_EXTRA_SPRITE")
DISPLAY_EXTRA_TYPE = wb("SHOP_DISPLAY_EXTRA_TYPE")
SHOP_DISPLAY_COUNT = 8
# Every shipped bank entry names a map and, $a4 on, that map's own tile bank.
SHIPPED_BANK_SPAN = 0xa4
# A word no arm of the tree writes and no shipped byte holds, for the destinations whose expected
# value is ZERO — a `clr.w` over a shipped zero is otherwise invisible.
SEED_UNEXPECTED = 0x5a5a

BOSS_FOLLOW = wb("ACTOR_FOLLOWED_A32")
BOSS_FOLLOW_XY = wb("SCENE_BOSS_FOLLOW_XY")
BOSS_FOLLOW_TYPE = wb("SCENE_BOSS_FOLLOW_TYPE")
BOSS_FOLLOW_SIZES = wb("SCENE_BOSS_FOLLOW_SIZES")
ACTOR_SIZE_SECOND = wb("ACTOR_SIZE_SECOND")

RESOURCE_TABLE = wb("RESOURCE_TABLE")
RESOURCE_RECORD_BYTES = wb("RESOURCE_RECORD_BYTES")
PRICE_DIGITS = wb("SHOP_PRICE_DIGITS")
PRICE_NIBBLE_BITS = wb("SHOP_PRICE_NIBBLE_BITS")
GLYPH_MASK_BYTES = wb("GLYPH_STAMP_MASK_BYTES")
GLYPH_PLANE_STEP = wb("GLYPH_STAMP_PLANE_STEP")
GLYPH_ROW_SKIP = wb("GLYPH_STAMP_ROW_SKIP")
GLYPH_ROW_BYTES = wb("GLYPH_STAMP_ROW_BYTES")
GLYPH_NEXT_EVEN = wb("GLYPH_STAMP_NEXT_EVEN")
GLYPH_NEXT_ODD = wb("GLYPH_STAMP_NEXT_ODD")
GLYPH_SPAN = wb("DIGIT_ROWS") * GLYPH_ROW_BYTES + GLYPH_MASK_BYTES
DIGIT_ROWS = wb("DIGIT_ROWS")
DIGIT_GLYPH_LEN = wb("DIGIT_GLYPH_LEN")
DIGIT_GLYPHS_ALT = wb("DIGIT_GLYPHS_ALT")
TEXT_GLYPH_TABLE = wb("TEXT_GLYPH_TABLE")
PLANES = wb("PLANES")

EXIT_ILLEGAL = wb("SCENE_EXIT_ILLEGAL")
EXIT_WILD_RETURN = wb("SCENE_EXIT_WILD_RETURN")
ILLEGAL_PC = 0x1d8e               # the `illegal` the fourth refusal reaches
WILD_RETURN_PC = 0x19e0           # ...and the `rts` that returns through the pushed a0
STOP_PC_FOR[EXIT_ILLEGAL] = ILLEGAL_PC
STOP_PC_FOR[EXIT_WILD_RETURN] = WILD_RETURN_PC
# The three arm entries the kind ladder branches to. A run that stopped at WILD_RETURN_PC without
# visiting any of them is what says the ladder FELL THROUGH rather than returning from an arm — the
# negative witness this one ending needs, because there is no instruction below the `rts` it stands
# for and the one above it (`beq.w $1ea8`) runs on the kind-4 path too.
SPAWN_ARMS = (0x19e2, 0x1bb4, 0x1ea8)
LAST_KIND_TEST = 0x19d8

# The two sprite bitmaps the price plates are drawn into: plain RAM between test_stage.py's map and
# the scroll buffers at $44000, clear of both.
PRICE_SPRITE_A = 0x41000
PRICE_SPRITE_B = 0x41400
PRICE_SPRITE_LEN = 0x100
# ...and the seven map pointers the bank entries a case does NOT choose are given. They step DOWN
# from test_stage.py's MAP so that none of them can collide with its RAW_TILE_BANK above it, and the
# lowest is still well clear of the program's own end.
UNCHOSEN_MAP_STEP = 0x1000

A2, A5 = 2, 5
D1, D4, D5, D6, D7 = 1, 4, 5, 6, 7
ILLEGAL = leaf.opcode(0x4afc)


def move_l_an_push(an):
    """`move.l An,-(a7)` — the tree's first instruction, and the a0 its three arms pop back."""
    return opcode(0x2000 | (7 << 9) | (4 << 6) | (1 << 3) | an)


def movea_l_postinc(destination, source):
    """`movea.l (As)+,Ad` — how each arm takes the map and the tile bank out of one bank entry."""
    return opcode(0x2058 | (destination << 9) | source)


def move_b_postinc_ind(source, destination):
    """`move.b (As)+,(Ad)` — the glyph stamp's whole inner step.

    ALSO IN test_stage.py, whose banner plotter spells the same byte move — second copy, and the two
    DISAGREED ABOUT ARGUMENT ORDER while sharing a body and a name: `move_b_postinc_ind(A0, A1)`
    assembled `move.b (a0)+,(a1)` there and `move.b (a1)+,(a0)` here. Both batteries were green
    because neither imported the other's, which is the `adda_w_dn_an` class a fourth time. SOURCE
    FIRST wins — it is the 68000 mnemonic's own order and `move_w_d16_d16`'s and
    `move_w_postinc_d16`'s in leaf.py — so this file's call site is the one that moved. Hoist on the
    third copy."""
    return opcode(0x1000 | (destination << 9) | (2 << 6) | (3 << 3) | source)


def move_w_an_dn(reg, an):
    """`move.w An,Dn` — the glyph stamp's parity test reads its own cursor this way.

    ALSO IN test_stage.py — second copy, and that pair AGREES, body and order alike. Registered
    rather than changed: the NAME reads source-first (`an_dn`) while the parameters are
    destination-first, which is a wart both copies share and no call site can trip over. Hoist on
    the third, in leaf.py's order."""
    return opcode(0x3008 | (reg << 9) | an)


def move_l_ind_abs_l(source, addr):
    """`move.l (An),<abs>.l` — the speech script's pointer planted in its cursor."""
    return opcode(0x23d0 | source) + longword(addr)


def move_b_ind_abs_l(source, addr):
    """`move.b (An),<abs>.l` — the id under the cursor posted into WB_TEXT_REQUEST."""
    return opcode(0x13d0 | source) + longword(addr)


def addq_l_abs_l(amount, addr):
    """`addq.l #n,<abs>.l` — the speech cursor is a LONGWORD and is advanced as one."""
    return opcode(0x5080 | leaf.quick_field(amount) | 0x39) + longword(addr)


def bcc_s_to(condition, here, target):
    """A SHORT conditional branch, as the two later gates spell their jump to the first one's `rts`.
    The displacement counts from the extension position exactly as the word form's does.

    ALSO IN test_sound.py as `_branch_s_to` — second copy, and it carries that one's ASSERT rather
    than a bare mask: a displacement byte of 0 selects the `.w` form and one of $ff the `.l` form,
    so neither is a short branch at all and emitting one would assemble a two-word instruction that
    swallows the next. Masking hides that; refusing it does not. Hoist on the third."""
    displacement = target - (here + leaf.BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0x80 and displacement not in (0, -1), (
        f"{displacement} is not a legal short-branch displacement")
    return opcode(condition | (displacement & 0xff))


def dbf_w_to(reg, here, target):
    """`dbf Dn,<target>` — the glyph stamp's row loop."""
    return opcode(leaf.DBF_DN | reg) + word(target - (here + leaf.BRANCH_EXTENSION))


def spawn_gate_body(entry, keep, branch):
    """One gate, whole. The three differ ONLY in the byte compared and in how the match jumps to the
    first one's `rts`, which is what `branch` supplies — so a fourth spelling would fail here."""
    return (cmpi_b_abs_l(keep, HUD_SLOT_BBC8) + branch
            + move_b_imm_ind(A1, SPAWN_GATE_REFUSED_SCRIPT)
            + move_w_imm_d16(A1, 0, 1) + RTS)


GATE_1_ENTRY, GATE_3_ENTRY, GATE_4_ENTRY = 0xe43e, 0xe456, 0xe46c
GATE_SHARED_RTS = 0xe454

# $1d1e, whole — the mask word skipped, four plane bytes two apart, the row step, and the two
# rewinds, each of which is GLYPH_SPAN less the cell step its parity selects.
GLYPH_STAMP_ENTRY = 0x1d1e
GLYPH_ROW_LOOP = 0x1d26
GLYPH_ODD_ARM = 0x1d4c
GLYPH_STAMP_BYTES = (
    lea_d16(A0, GLYPH_MASK_BYTES, A0)
    + move_w_imm_dn(D7, DIGIT_ROWS - 1)
    + b"".join(move_b_postinc_ind(A1, A0) + (addq_l_an(GLYPH_PLANE_STEP, A0) if plane + 1 < PLANES
                                             else b"")
               for plane in range(PLANES))
    + lea_d16(A0, GLYPH_ROW_SKIP, A0)
    + dbf_w_to(D7, 0x1d38, GLYPH_ROW_LOOP)
    + move_w_an_dn(D7, A0) + btst_imm_dn(0, D7)
    + branch_w_to(BNE_W, 0x1d42, GLYPH_ODD_ARM)
    + lea_d16(A0, -(GLYPH_SPAN - GLYPH_NEXT_EVEN) & 0xffff, A0) + RTS
    + lea_d16(A0, -(GLYPH_SPAN - GLYPH_NEXT_ODD) & 0xffff, A0) + RTS)

SPAWN_ENTRY_BYTES = {
    # $19ac: the two pointers and the free marker over slot 1, before any arm is chosen.
    "scene_spawn_from_script": (0x19ac, move_l_an_push(A0) + movea_l_abs_l(A1, DESCRIPTOR_PTR)
                                + movea_l_abs_l(A6, MARKER_CELL_PTR)
                                + move_w_imm_abs_l(FREE_MARKER, SPAWN_GATE_SLOT)),
    # ...and the kind ladder, which is THREE tests and then a bare `rts`: a descriptor naming kind 3
    # leaves having written only that marker.
    "spawn kind ladder": (0x19c2, lea_d16(A1, SCENE_KIND, A1) + move_w_postinc_dn(D0, A1)
                          + cmp_w_imm_dn(D0, KIND_SPEECH) + branch_w_to(BEQ_W, 0x19cc, 0x19e2)
                          + cmp_w_imm_dn(D0, KIND_SHOP) + branch_w_to(BEQ_W, 0x19d4, 0x1bb4)
                          + cmp_w_imm_dn(D0, KIND_BOSS) + branch_w_to(BEQ_W, 0x19dc, 0x1ea8) + RTS),
    # The FOURTH dispatch table, and the READ-AFTER-STORE with it: the `moveq/move.b` at $1a7c
    # fetches the speech index AFTER the `jsr (a0)` that may have overwritten it.
    "spawn gate dispatch": (0x1a66, moveq_0_dn(D0) + move_b_postinc_dn(D0, A1)
                            + branch_w_to(BEQ_W, 0x1a6a, 0x1a7c) + lsl_w_imm_dn(2, D0)
                            + lea_abs_l(A0, SPAWN_GATE_TABLE) + movea_l_indexed(A0, A0, D0)
                            + jsr_ind(A0)
                            + moveq_0_dn(D0) + move_b_postinc_dn(D0, A1)),
    # The speech post, whose lifetime is the INFINITE one and not the $32 every $dbc0 arm uses.
    "spawn speech post": (0x1a80, lsl_w_imm_dn(2, D0) + lea_abs_l(A0, SCRIPT_TABLE)
                          + lea_indexed(A0, D0) + move_l_ind_abs_l(A0, SCRIPT_CURSOR)
                          + movea_l_abs_l(A0, SCRIPT_CURSOR)
                          + move_b_ind_abs_l(A0, TEXT_REQUEST)
                          + move_w_imm_abs_l(SPEECH_LIFETIME_HELD, TEXT_LIFETIME_REQUEST)
                          + addq_l_abs_l(1, SCRIPT_CURSOR)),
    # $1ab4, the shared tail: the bank index off a RE-READ descriptor pointer, both longwords, and
    # only then the freeze.
    "spawn stage tail": (0x1ab4, movea_l_abs_l(A1, DESCRIPTOR_PTR) + moveq_0_dn(D0)
                         + move_w_ind_dn(D0, A1, MAP_BANK_INDEX) + lsl_w_imm_dn(3, D0)
                         + lea_abs_l(A1, MAP_BANK_TABLE) + lea_indexed(A1, D0)
                         + movea_l_postinc(A0, A1) + movea_l_postinc(A6, A1)
                         + move_w_imm_abs_w(FROZEN_SET, SCROLL_FOLLOW_FROZEN)
                         + lea_abs_l(A1, STAGE_START_RECORDS
                                     + START_RECORD_SPEECH * START_RECORD_LEN)),
    # The two price plates, which is where "d7 is a sprite and d6 a price field" is read off.
    "shop price plates": (0x1ca4, move_w_imm_dn(D7, DISPLAY_PRICE1_SPRITE)
                          + move_w_imm_dn(D6, ITEM1_PRICE) + bsr_w(0x1cac, 0x1cc0)
                          + move_w_imm_dn(D7, DISPLAY_PRICE2_SPRITE)
                          + move_w_imm_dn(D6, ITEM2_PRICE) + bsr_w(0x1cb8, 0x1cc0)),
    # $1cc0: the resource fetch and the price read, and nothing else claimed for it.
    "shop_render_price_digits": (0x1cc0, clr_w_dn(D4)
                                 + leaf.mulu_w_imm_dn(D7, RESOURCE_RECORD_BYTES)
                                 + lea_abs_l(A0, RESOURCE_TABLE)
                                 + lea_indexed(A1, D7, source=A0) + movea_l_ind(A0, A1)
                                 + movea_l_abs_l(A1, SHOP_RECORD_PTR)
                                 + leaf.move_w_indexed_dn(D0, A1, D6)),
    # ...and $1d1e, whole.
    "glyph_stamp_8_rows": (GLYPH_STAMP_ENTRY, GLYPH_STAMP_BYTES),
    # The three gates, whole: they are the only routines the dispatch above can reach.
    "spawn_gate_unless_bbc8_eq1": (GATE_1_ENTRY, spawn_gate_body(
        GATE_1_ENTRY, 1, branch_w_to(BEQ_W, 0xe446, GATE_SHARED_RTS))),
    "spawn_gate_unless_bbc8_eq3": (GATE_3_ENTRY, spawn_gate_body(
        GATE_3_ENTRY, 3, bcc_s_to(BEQ_W, 0xe45e, GATE_SHARED_RTS))),
    "spawn_gate_unless_bbc8_eq4": (GATE_4_ENTRY, spawn_gate_body(
        GATE_4_ENTRY, 4, bcc_s_to(BEQ_W, 0xe474, GATE_SHARED_RTS))),
    # The shop tail's refusal gate: the sign sprite AND a SIGNED purse compare.
    "shop refusal gate": (0x1d52, movea_l_abs_l(A0, SHOP_RECORD_PTR)
                          + cmpi_w_d16(A0, SHOP_SIGN_SPRITE_INTRO, SHOP_SIGN_SPRITE)
                          + branch_w_to(BNE_W, 0x1d5e, 0x1de0)
                          + move_w_abs_l_dn(D0, BCD_COUNTER)
                          + move_w_ind_dn(D1, A0, ITEM2_PRICE)
                          + cmp_w_dn_dn(D0, D1) + branch_w_to(BGT_W, 0x1d6e, 0x1de0)),
    # ...and the ORIGINAL's own ending, three instructions on from it.
    "shop refusal illegal": (0x1d86, cmp_w_imm_dn(D0, 2) + branch_w_to(BEQ_W, 0x1d8a, 0x1db8)
                             + ILLEGAL),
    # The boss arm's override: the shift is DEAD, the index is always this offset.
    "boss bank override": (0x1efa, lsl_w_imm_dn(3, D0) + lea_abs_l(A1, MAP_BANK_TABLE)
                           + move_w_imm_dn(D0, BOSS_MAP_BANK_OFFSET) + lea_indexed(A1, D0)),
}
ENTRY_BYTES.update(SPAWN_ENTRY_BYTES)
RECORDED_PINS += len(SPAWN_ENTRY_BYTES)
SPAWN_RECORDED_PINS = 14


@pytest.mark.parametrize("label", sorted(SPAWN_ENTRY_BYTES))
def test_each_spawn_tree_instruction_is_the_one_reconstructed(label):
    """The tree's own pins, and A SECOND TEST rather than more rows in the one above.

    `@pytest.mark.parametrize` evaluates its argument list when the DECORATOR RUNS, which is when
    the module is imported and the `def` above is reached — so a table extended BELOW that point
    adds rows the parametrization never sees. This section's first draft did exactly that:
    fourteen pins went into `ENTRY_BYTES`, `assert_batch_is_complete` stayed green because it reads
    the dict at RUN time, and not one of the fourteen was ever compared against the image. The
    tell was arithmetic — the battery's case count did not move when the pins were added.
    """
    assert_pinned_instruction(label)


def test_the_spawn_trees_pin_table_still_holds_what_it_was_written_for():
    """`assert_batch_is_complete` for this section alone, so a pin dropped from the tree's own
    table shrinks it loudly instead of hiding inside the battery's total."""
    leaf.assert_batch_is_complete(SPAWN_ENTRY_BYTES, SPAWN_RECORDED_PINS)


# --- the tables, before any of them is followed --------------------------------------------------

def gate_table_entry(index):
    return int.from_bytes(harness.BASE_IMAGE[SPAWN_GATE_TABLE + index * LONGWORD_BYTES:][
        :LONGWORD_BYTES], "big")


@pytest.mark.parametrize("index, name", [(1, "spawn_gate_unless_bbc8_eq1"),
                                         (2, "spawn_gate_unless_bbc8_eq3"),
                                         (3, "spawn_gate_unless_bbc8_eq4")])
def test_each_spawn_gate_table_entry_is_the_routine_names_txt_names(index, name):
    """The dispatch src/scene.c's SPAWN_GATES array stands for, entry by entry against the image."""
    assert gate_table_entry(index) == leaf.entry_of(name), (
        f"spawn gate {index} is {gate_table_entry(index):#x}, not {name}")


def test_the_spawn_gate_table_entry_zero_is_not_an_address():
    """Slot 0 is the reason the dispatcher returns on a script byte of zero BEFORE it scales one:
    the longword there is data, and following it would run the image at $2140202."""
    assert gate_table_entry(0) == SPAWN_GATE_ENTRY_0, (
        f"entry 0 is {gate_table_entry(0):#x}, not the {SPAWN_GATE_ENTRY_0:#x} src/scene.c's NULL "
        f"stands for")
    assert not loader.LOAD_BASE <= gate_table_entry(0) < loader.PROGRAM_END, (
        "entry 0 names an address inside the program after all")


def test_the_spawn_gate_table_is_bounded_by_its_own_first_target():
    """FOUR entries and not five: the table ends exactly where $e43e, the first thing it names,
    begins — the same self-bounding reading the other three dispatch tables get."""
    assert SPAWN_GATE_TABLE + SPAWN_GATE_COUNT * LONGWORD_BYTES == leaf.entry_of(
        "spawn_gate_unless_bbc8_eq1")


def test_the_battery_refuses_a_gate_index_outside_the_table():
    """The refusal src/scene.c makes, stated — the same shape as
    `test_the_battery_refuses_an_exit_action_offset_outside_the_table` one table over, and named as
    a COVERAGE HOLE for the same reason. An index of 4 or more makes the original `jsr` through a
    longword outside the four entries; there is no C for calling that, so it is an input this file
    declines, and batch 41 phase B's sweep duly turned the port's `>=` into a `>` and nothing here
    caught it, because nothing here can.

    WHAT IS DIFFERENT FROM THAT ONE, and it is why this table needed no offset arithmetic: the
    index is a script BYTE, so `lsl.w #2` tops out at 1020 and the sign-extended offset can never
    wrap back into the table. The aliasing that gives WB_SCENE_EXIT_ACTION_TABLE 24 extra live
    indices has no analogue here — asserted rather than asserted-by-omission.
    """
    assert 0xff * LONGWORD_BYTES < 0x8000, (
        "a byte index times four could reach a NEGATIVE sign-extended offset after all, so the "
        "port's guard would need the exit-action table's offset arithmetic")
    past = int.from_bytes(harness.BASE_IMAGE[SPAWN_GATE_TABLE
                                             + SPAWN_GATE_COUNT * LONGWORD_BYTES:][:LONGWORD_BYTES],
                          "big")
    assert not any(past == leaf.entry_of(name) for name in
                   ("spawn_gate_unless_bbc8_eq1", "spawn_gate_unless_bbc8_eq3",
                    "spawn_gate_unless_bbc8_eq4")), (
        f"{past:#x} past the table IS one of the three targets, so the bound would be wrong")


def test_the_three_gates_are_reachable_only_through_the_table():
    """A whole-image scan of both absolute JSR/JMP encodings and of every word-displacement branch
    finds NO instruction naming any of the three — so the dispatch is their only entrance, which is
    what makes closing the table close the routines."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    for name in ("spawn_gate_unless_bbc8_eq1", "spawn_gate_unless_bbc8_eq3",
                 "spawn_gate_unless_bbc8_eq4"):
        target = leaf.entry_of(name)
        for at in range(loader.LOAD_BASE, loader.PROGRAM_END - LONGWORD_BYTES, 2):
            head = int.from_bytes(program[at:at + WORD_BYTES], "big")
            operand = int.from_bytes(program[at + WORD_BYTES:at + WORD_BYTES + LONGWORD_BYTES],
                                     "big")
            assert not (head in (leaf.JSR_ABS_L, leaf.JMP_ABS_L)
                        and operand == target), (
                f"{name} is reached by a direct call at {at:#x}, not only through the table")
            if 0x6000 <= head <= 0x6fff and (head & 0xff) == 0:
                displacement = s16(int.from_bytes(program[at + WORD_BYTES:at + 2 * WORD_BYTES],
                                                  "big"))
                assert at + WORD_BYTES + displacement != target, (
                    f"{name} is branched to at {at:#x}, not only reached through the table")


def test_the_map_bank_table_is_bounded_and_ships_its_own_entries():
    """SEVEN entries and not eight, which is a correction this battery MADE rather than checked: the
    table ends exactly where WB_RECORD_PTR_10420 begins, and an eighth entry would BE that pointer
    and the copy beside it. Unlike the descriptor and shop tables this one's contents are in the
    .PRG, and all seven are live."""
    assert MAP_BANK_TABLE + MAP_BANK_COUNT * MAP_BANK_BYTES == DESCRIPTOR_PTR
    assert DESCRIPTOR_PTR + 2 * LONGWORD_BYTES == SHOP_RECORD_TABLE
    entries = [(int.from_bytes(harness.BASE_IMAGE[MAP_BANK_TABLE + i * MAP_BANK_BYTES:][:4], "big"),
                int.from_bytes(harness.BASE_IMAGE[MAP_BANK_TABLE + i * MAP_BANK_BYTES
                                                  + MAP_BANK_TILES:][:4], "big"))
               for i in range(MAP_BANK_COUNT)]
    assert all(0 < m < loader.PROGRAM_END and t == m + SHIPPED_BANK_SPAN for m, t in entries), (
        f"the shipped bank entries are not (map, map + $a4) pairs inside the program: {entries}")
    assert BOSS_MAP_BANK_OFFSET % MAP_BANK_BYTES == 0 and (
        BOSS_MAP_BANK_OFFSET // MAP_BANK_BYTES) < MAP_BANK_COUNT, (
        "the boss arm's hard-coded offset does not name one of the seven entries")


def test_the_a30_table_ends_in_the_terminator_the_free_loop_stops_on():
    """`cmpi.l #$ffffffff,(a2)` is the free loop's ONLY exit, and the longword it stops on is
    shipped: WB_ACTOR_TABLE_A30 plus its nineteen records lands exactly on it, four bytes below
    WB_ACTOR_TABLE_A32. That is also why every case below re-plants it — this battery's own
    address-keyed bands reach over it."""
    assert TABLE_A30_END == TABLE_A32 - LONGWORD_BYTES
    assert int.from_bytes(harness.BASE_IMAGE[TABLE_A30_END:TABLE_A30_END + LONGWORD_BYTES],
                          "big") == ACTOR_TABLE_END


def test_the_glyph_row_is_two_masked_groups():
    """WB_GLYPH_STAMP_ROW_BYTES is a literal in the header (test/layout.py scrapes plain integers
    only), so the derivation it claims is asserted here instead: three plane steps and the row skip.
    The two rewinds follow from it, and the pin above compares both against the image's own `lea`s."""
    assert GLYPH_ROW_BYTES == (PLANES - 1) * GLYPH_PLANE_STEP + GLYPH_ROW_SKIP
    assert GLYPH_NEXT_ODD - GLYPH_NEXT_EVEN == GLYPH_ROW_BYTES // 2 - GLYPH_PLANE_STEP, (
        "the odd cursor's step does not land on the next 10-byte group's even byte")


def test_the_start_records_the_three_arms_name_are_the_shipped_ones():
    """Each arm `lea`s a literal, and this is what says which of WB_STAGE_START_RECORDS' five it
    is — including the speech arm's, whose tune byte is the NEGATIVE one, so entering a speech scene
    STOPS the sound module where the other two arms start a song."""
    for index, expected in ((START_RECORD_BOSS, 0x1d40c), (START_RECORD_SHOP, 0x1d416),
                            (START_RECORD_SHOP_ALT, 0x1d420), (START_RECORD_SPEECH, 0x1d42a)):
        assert STAGE_START_RECORDS + index * START_RECORD_LEN == expected
    speech_tune = harness.BASE_IMAGE[STAGE_START_RECORDS
                                     + START_RECORD_SPEECH * START_RECORD_LEN + START_TUNE]
    assert speech_tune & 0x80, "the speech arm's record no longer stops the sound module"
    for index in (START_RECORD_BOSS, START_RECORD_SHOP, START_RECORD_SHOP_ALT):
        tune = harness.BASE_IMAGE[STAGE_START_RECORDS + index * START_RECORD_LEN + START_TUNE]
        assert not tune & 0x80, f"start record {index} no longer starts a song"


# --- $e43e / $e456 / $e46c: the three gates, entered directly ------------------------------------

GATE_INSN_CAP = 8                 # five instructions on the writing arm, plus the runner's sentinel
_GATES = {name: leaf.register_glue(name, [ctypes.c_uint32])
          for name in ("spawn_gate_unless_bbc8_eq1", "spawn_gate_unless_bbc8_eq3",
                       "spawn_gate_unless_bbc8_eq4")}
# The cursor is the descriptor byte the caller has just consumed, so it is ODD — which is what puts
# the gate's word write at 1(a1) on an even address.
GATE_CURSOR = DESCRIPTOR + wb("SCENE_GATE_INDEX") + 1
GATE_KEEP = {"spawn_gate_unless_bbc8_eq1": 1, "spawn_gate_unless_bbc8_eq3": 3,
             "spawn_gate_unless_bbc8_eq4": 4}


def gate_pokes(case, bbc8):
    """The descriptor band the gate writes into, plus the icon byte it compares."""
    salt = case_salt(case)
    return {DESCRIPTOR: keyed_block(DESCRIPTOR, RECORD_BYTES, salt),
            HUD_SLOT_BBC8: bytes([bbc8])}


@pytest.mark.parametrize("name", sorted(GATE_KEEP))
def test_a_gate_whose_icon_matches_writes_nothing(name):
    """`cmpi.b #n,$bbc8.l / beq` — the arm that leaves the descriptor's script alone."""
    case = f"{name} matched"
    info = leaf.run(name, _GATES[name](GATE_CURSOR), (), case,
                    regs={"a1": GATE_CURSOR, "_pokes": gate_pokes(case, GATE_KEEP[name])},
                    max_insns=GATE_INSN_CAP)
    assert not leaf.program_writes(info), f"{case}: the matching arm wrote {leaf.program_writes(info)}"


@pytest.mark.parametrize("name", sorted(GATE_KEEP))
@pytest.mark.parametrize("bbc8", (0, 2, 5, 0xff))
def test_a_gate_whose_icon_does_not_match_rewrites_the_script(name, bbc8):
    """The three bytes the mismatch leaves: WB_SPAWN_GATE_REFUSED_SCRIPT over the speech index the
    caller reads next, and a zero word over WB_SCENE_EXIT_ACTION behind it."""
    if bbc8 == GATE_KEEP[name]:
        pytest.skip("that byte is this gate's own")
    case = f"{name} against {bbc8:#04x}"
    info = leaf.run(name, _GATES[name](GATE_CURSOR), [(GATE_CURSOR, 3)], case,
                    regs={"a1": GATE_CURSOR, "_pokes": gate_pokes(case, bbc8)},
                    max_insns=GATE_INSN_CAP)
    leaf.assert_written_is(info, {GATE_CURSOR: bytes([SPAWN_GATE_REFUSED_SCRIPT]),
                                  GATE_CURSOR + 1: word(0)}, case)


def test_the_gate_writes_the_descriptors_own_exit_action_word():
    """The word at 1(a1) is not an anonymous neighbour: the cursor is WB_SCENE_GATE_INDEX + 1, so
    the two bytes behind the script index are WB_SCENE_EXIT_ACTION — the word $dfbe dispatches on
    when the scene is left."""
    assert GATE_CURSOR + 1 == DESCRIPTOR + SCENE_EXIT_ACTION


# --- $1d1e: one glyph column ---------------------------------------------------------------------

GLYPH_INSN_CAP = 96               # 2 + 8 * (4 writes + 3 steps + a row step + the `dbf`) + 5 + 1
_GLYPH_STAMP = leaf.register_glue("glyph_stamp_8_rows", [ctypes.c_uint32] * 2, ctypes.c_uint32)


def glyph_write_addresses(cursor):
    """Where the eight rows of four plane bytes land, walked the way the routine walks them."""
    at = cursor + GLYPH_MASK_BYTES
    for _ in range(DIGIT_ROWS):
        for plane in range(PLANES):
            yield at
            at += GLYPH_PLANE_STEP if plane + 1 < PLANES else GLYPH_ROW_SKIP


def glyph_next_cursor(cursor):
    return cursor + (GLYPH_NEXT_ODD if cursor & 1 else GLYPH_NEXT_EVEN)


@pytest.mark.parametrize("column", range(PRICE_DIGITS))
def test_the_glyph_stamp_lays_a_column_and_returns_the_next(column):
    """One shipped glyph into a seeded sprite, at each of the four cursors a price walks — the two
    byte columns of the first 10-byte group and then of the second. The write set is stated exactly
    and the returned cursor is compared against the ORACLE's own a0, not against a model of it."""
    case = f"glyph stamp column {column}"
    cursor = PRICE_SPRITE_A + [0, 1, GLYPH_ROW_BYTES // 2, GLYPH_ROW_BYTES // 2 + 1][column]
    glyph = DIGIT_GLYPHS_ALT + column * DIGIT_GLYPH_LEN
    pokes = {PRICE_SPRITE_A: keyed_block(PRICE_SPRITE_A, PRICE_SPRITE_LEN, case_salt(case))}
    source = bytes(harness.BASE_IMAGE[glyph:glyph + DIGIT_ROWS * PLANES])

    info = leaf.run("glyph_stamp_8_rows", _GLYPH_STAMP(cursor, glyph),
                    [(PRICE_SPRITE_A, PRICE_SPRITE_LEN)], case,
                    regs={"a0": cursor, "a1": glyph, "_pokes": pokes},
                    max_insns=GLYPH_INSN_CAP)
    leaf.assert_written_is(info, {at: bytes([source[i]])
                                  for i, at in enumerate(glyph_write_addresses(cursor))}, case)
    assert info["regs"]["a0"] == glyph_next_cursor(cursor), (
        f"{case}: the original left a0 at {info['regs']['a0']:#x}")
    assert info["ret"] == info["regs"]["a0"], (
        f"{case}: the reconstruction returned {info['ret']:#x}")


def test_the_four_glyph_cursors_close_on_the_next_row_of_groups():
    """The four columns a price occupies are the two byte columns of each of the row's two groups,
    and the fourth hands back a cursor exactly WB_GLYPH_STAMP_ROW_BYTES on — which is what says the
    row is two groups and the sprite 32 pixels wide."""
    cursor = PRICE_SPRITE_A
    for _ in range(PRICE_DIGITS):
        cursor = glyph_next_cursor(cursor)
    assert cursor == PRICE_SPRITE_A + GLYPH_ROW_BYTES


# --- $1cc0: the price plates ---------------------------------------------------------------------

PRICE_INSN_CAP = 8 * PRICE_DIGITS + PRICE_DIGITS * GLYPH_INSN_CAP + 16
_PRICE = leaf.register_glue("shop_render_price_digits", [ctypes.c_uint32] * 2)


def resource_entry(index):
    return RESOURCE_TABLE + index * RESOURCE_RECORD_BYTES


def price_pokes(case, price, field, sprite=PRICE_SPRITE_A,
                resource=DISPLAY_PRICE1_SPRITE):
    """The resource record whose first longword is the sprite, the shop record the price is read
    out of, and the sprite itself. All three lie past the program and are the case's own."""
    salt = case_salt(case)
    return leaf.overlay(
        {SHOP_RECORD: keyed_block(SHOP_RECORD, SHOP_RECORD_BYTES, salt)},
        {sprite: keyed_block(sprite, PRICE_SPRITE_LEN, salt),
         resource_entry(resource): longword(sprite),
         SHOP_RECORD_PTR: longword(SHOP_RECORD),
         SHOP_RECORD + field: word(price)})


def price_glyph_sources(price):
    """The four glyphs the digits select, most significant nibble first, with a leading zero drawn
    from WB_TEXT_GLYPH_TABLE's first glyph (the SPACE) until a nonzero one has been seen."""
    significant = False
    for shift in range(PRICE_DIGITS - 1, -1, -1):
        nibble = (price >> (shift * PRICE_NIBBLE_BITS)) & 0xf
        if nibble == 0 and not significant:
            yield TEXT_GLYPH_TABLE
            continue
        significant = True
        yield DIGIT_GLYPHS_ALT + nibble * DIGIT_GLYPH_LEN


def price_plate_writes(sprite, price):
    """Every byte one price plate leaves, as {address: bytes} — the four glyph columns the digits
    select, taken from the SHIPPED fonts.

    A MODEL and not a difference helper: it is derived from `harness.BASE_IMAGE` and this battery's
    own geometry, so it states what the plate should hold independently of what either core wrote.
    Three cases walked it identically before it was extracted.
    """
    written = {}
    cursor = sprite
    for glyph in price_glyph_sources(price):
        source = bytes(harness.BASE_IMAGE[glyph:glyph + DIGIT_ROWS * PLANES])
        for i, at in enumerate(glyph_write_addresses(cursor)):
            written[at] = bytes([source[i]])
        cursor = glyph_next_cursor(cursor)
    return written


@pytest.mark.parametrize("price", (0x0000, 0x0001, 0x0100, 0x1234, 0x9999, 0xffff, 0x0f0f))
def test_the_price_plate_draws_four_digits_with_leading_zeros_blanked(price):
    """Every byte of the sprite, stated exactly: four glyph columns whose sources the leading-zero
    latch chooses. A price of zero draws four SPACES, and a price with an interior zero draws that
    one as a digit — which is the whole of what the latch is for."""
    case = f"price plate {price:#06x}"
    pokes = price_pokes(case, price, ITEM1_PRICE)
    written = price_plate_writes(PRICE_SPRITE_A, price)

    info = leaf.run("shop_render_price_digits", _PRICE(DISPLAY_PRICE1_SPRITE, ITEM1_PRICE),
                    [(PRICE_SPRITE_A, PRICE_SPRITE_LEN)], case,
                    regs={"d7": DISPLAY_PRICE1_SPRITE, "d6": ITEM1_PRICE, "_pokes": pokes},
                    max_insns=PRICE_INSN_CAP)
    leaf.assert_written_is(info, written, case)


@pytest.mark.parametrize("resource, field, sprite", [(DISPLAY_PRICE1_SPRITE, ITEM1_PRICE,
                                                      PRICE_SPRITE_A),
                                                     (DISPLAY_PRICE2_SPRITE, ITEM2_PRICE,
                                                      PRICE_SPRITE_B)])
def test_each_price_plate_reads_its_own_field_and_draws_its_own_sprite(resource, field, sprite):
    """The two call sites differ only in d7 and d6, so this is what says which resource carries
    which price: seed the OTHER field with a value that would be visible and require the run to have
    ignored it."""
    case = f"price plate resource {resource:#x}"
    pokes = leaf.overlay(price_pokes(case, 0x1234, field, sprite, resource),
                         {SHOP_RECORD + (ITEM2_PRICE if field == ITEM1_PRICE else ITEM1_PRICE):
                          word(0x5678)})
    written = price_plate_writes(sprite, 0x1234)

    info = leaf.run("shop_render_price_digits", _PRICE(resource, field), [(sprite,
                                                                           PRICE_SPRITE_LEN)], case,
                    regs={"d7": resource, "d6": field, "_pokes": pokes},
                    max_insns=PRICE_INSN_CAP)
    leaf.assert_written_is(info, written, case)


# --- $19ac, whole: the three arms end to end -----------------------------------------------------
#
# Every case here is a FULL RUN: the arm, its display records, its gate, its message, the marker
# clear, the 2x2 stamp and the whole stage reload, ending at the original's own `rts`. The one
# exception is the fourth refusal, which ends at the ORIGINAL's `illegal` and is checkpointed.

# Where the script cursor stands after each read, derived rather than restated: the head consumes
# the kind word, each arm then two triples of three words, and the two script BYTES follow them.
SPAWN_TRIPLE_WORDS = 3
SPAWN_SCRIPT_FIRST = SCENE_KIND + WORD_BYTES
GATE_INDEX_AT = SPAWN_SCRIPT_FIRST + 2 * SPAWN_TRIPLE_WORDS * WORD_BYTES
SPEECH_INDEX_AT = GATE_INDEX_AT + 1
# ...and the same two offsets as the header names them. The derivation above comes from WALKING the
# cursor and the constants come from the descriptor block, so requiring them equal is two
# independent readings of the same two bytes rather than one restated.
assert (GATE_INDEX_AT, SPEECH_INDEX_AT) == (wb("SCENE_GATE_INDEX"), wb("SCENE_SPEECH_INDEX")), (
    "the cursor walk and include/wonderboy.h disagree about where the two script bytes are")
# ...and the second triple, whose LAST TWO WORDS the boss arm reads instead — `lea 8(a0),a0` off a
# cursor it rebuilt at descriptor+4, so +12 (which it discards) and +14 (the message id).
SPAWN_TRIPLE_2 = SPAWN_SCRIPT_FIRST + SPAWN_TRIPLE_WORDS * WORD_BYTES
BOSS_DEAD_WORD_AT = SPAWN_TRIPLE_2 + WORD_BYTES
BOSS_MESSAGE_AT = SPAWN_TRIPLE_2 + 2 * WORD_BYTES

SPAWN_CAP = LOAD_WINDOW_INSN_CAP + 512
SPAWN_SHOP_CAP = LOAD_WINDOW_INSN_CAP + 2 * PRICE_DIGITS * GLYPH_INSN_CAP + 512
_SPAWN = leaf.image_glue("scene_spawn_from_script", ctypes.c_uint32)

# Every byte the tree itself may touch, as a BOUND: the stray check is what catches a write outside
# it, and the byte-for-byte diff is what pins the values. WB_SCENE_MAP_BANK_TABLE and the resource
# records are read-only here and deliberately absent.
SPAWN_OWN_BYTES = (
    set(range(TABLE_A30, TABLE_A30_END))
    | set(range(TABLE_A32, TABLE_A32 + TABLE_A30_SLOTS * RECORD_BYTES))
    | set(range(SPAWN_GATE_SLOT, SPAWN_GATE_SLOT + WORD_BYTES))
    | set(range(SCROLL_FOLLOW_FROZEN, SCROLL_FOLLOW_FROZEN + WORD_BYTES))
    | set(range(FLAG_A30, STATE_FLAG_A34 + WORD_BYTES))
    | set(range(PANEL_FRAME_HOLD, PANEL_FRAME_HOLD + WORD_BYTES))
    | set(range(MESSAGE_PENDING, MARKER_CELL_PTR + LONGWORD_BYTES))
    | set(range(TEXT_REQUEST, TEXT_LIFETIME_REQUEST + WORD_BYTES))
    | set(range(SCRIPT_CURSOR, SCRIPT_CURSOR + LONGWORD_BYTES))
    | set(range(SHOP_RECORD_PTR, SHOP_RECORD_PTR + LONGWORD_BYTES))
    | set(range(DESCRIPTOR, DESCRIPTOR + RECORD_BYTES))
    | set(range(SHOP_RECORD, SHOP_RECORD + SHOP_RECORD_BYTES))
    | set(range(MAP_ROW_STRIDE, MAP_ROW_STRIDE + MAP_BAND_LEN))
    | set(range(MARKER_CELL - 1, MARKER_CELL + 2))
    | set(range(PRICE_SPRITE_A, PRICE_SPRITE_A + PRICE_SPRITE_LEN))
    | set(range(PRICE_SPRITE_B, PRICE_SPRITE_B + PRICE_SPRITE_LEN)))

_LOAD_WINDOW_BYTES = {}


def load_window_bytes(start):
    """Every address `stage_load_window` writes for one start record, out of test_stage.py's own
    model. Cached per record because the ADDRESSES do not depend on a case's salt — only the values
    do, and this set is only ever used as a bound."""
    if start not in _LOAD_WINDOW_BYTES:
        seeds = load_window_pokes(f"spawn bands {start:#x}", start, RAW_TILE_BANK, True,
                                  LATCH_UNMATCHED)
        image = harness.make_image(seeds)
        _LOAD_WINDOW_BYTES[start] = leaf.seeded_bytes(
            model_load_window(image, start, RAW_TILE_BANK, True, LATCH_UNMATCHED))
    return _LOAD_WINDOW_BYTES[start]


def spawn_start_record(index):
    return STAGE_START_RECORDS + index * START_RECORD_LEN


def bank_pokes(chosen):
    """All seven entries, and only the CHOSEN one names the map this case seeds — so an arm that
    indexed the table wrongly would load a different (unseeded, all-zero) map and diverge. The other
    six step DOWN from it, clear of test_stage.py's tile bank above."""
    return {MAP_BANK_TABLE + i * MAP_BANK_BYTES:
            longword(STAGE_MAP if i == chosen else STAGE_MAP - (i + 1) * UNCHOSEN_MAP_STEP)
            + longword(RAW_TILE_BANK)
            for i in range(MAP_BANK_COUNT)}


def spawn_pokes(case, start, *, bank=0, bbc8=0, stage=0, words=(), bytes_=()):
    """The scene battery's own bands, test_stage.py's whole stage-reload seed, and the tables the
    tree reads on top of both.

    THE A30 TABLE'S TERMINATOR IS RE-PLANTED LAST, and it has to be: this battery's address-keyed
    band around WB_ACTOR_TABLE_A32 reaches back over the shipped $ffffffff four bytes below it, and
    without the terminator the free loop has no exit at all.
    """
    salt = case_salt(case)
    scene = pokes(case, words=words, bytes_=tuple(bytes_) + ((HUD_SLOT_BBC8, bbc8),))
    window = load_window_pokes(case, start, RAW_TILE_BANK, False, LATCH_UNMATCHED)
    tables = dict(bank_pokes(bank))
    tables.update({
        resource_entry(DISPLAY_PRICE1_SPRITE): longword(PRICE_SPRITE_A),
        resource_entry(DISPLAY_PRICE2_SPRITE): longword(PRICE_SPRITE_B),
        PRICE_SPRITE_A: keyed_block(PRICE_SPRITE_A, PRICE_SPRITE_LEN, salt),
        PRICE_SPRITE_B: keyed_block(PRICE_SPRITE_B, PRICE_SPRITE_LEN, salt),
        STAGE_NUMBER: word(stage),
        SPAWN_GATE_SLOT: word(~FREE_MARKER & WORD_MASK),
        # ...and every FIXED word the tree writes, seeded with something no arm can leave. Without
        # this a store of ZERO over a shipped zero is invisible, and batch 41 phase B's sweep proved
        # it: `a34-not-cleared` survived until these went in. It is the same substitute for the
        # attribution pass that `pokes` makes with SEED_TEXT_REQUEST, one tier up.
        FLAG_A30: word(0), FLAG_A32: word(0), STATE_FLAG_A34: word(SEED_UNEXPECTED),
        PANEL_FRAME_HOLD: word(SEED_UNEXPECTED),
        MESSAGE_PENDING: word(0), ACK_WAIT: word(0),
        GREET_COUNTDOWN: word(SEED_UNEXPECTED),
        SCRIPT_CURSOR: longword(SEED_UNEXPECTED),
        TABLE_A30: keyed_block(TABLE_A30, TABLE_A30_END - TABLE_A30, salt),
        TABLE_A30_END: longword(ACTOR_TABLE_END),
    })
    return leaf.overlay(scene, window, tables)


def run_spawn(case, seeds, start, expected_exit=EXIT_RETURN, cap=SPAWN_CAP, reaches_hinge=True,
              visited=(), not_visited=(), extra_allowed=frozenset()):
    """One `scene_spawn_from_script` case. Poison is off for `run_frame`'s reason: the tree's own
    outputs include the pointers the hinge then reads its start record and its map back through.

    THE TWO ENDINGS THAT ARE NOT RETURNS take a NEGATIVE witness rather than `run_reaching`'s
    positive one, and the README's rule is why: each stands for an instruction with nothing below it
    on its own path, and the instruction above it runs on a path that RETURNS as well. So the case
    names an instruction only the returning path reaches and requires it NOT to have run, which with
    the checkpoint is exact; ``visited`` carries the positive half where there is one.
    """
    allowed = merge_bands(SPAWN_OWN_BYTES | set(extra_allowed)
                          | (load_window_bytes(start) if reaches_hinge else set()))
    how = dict(regs={"_pokes": seeds}, max_insns=cap, poison=False,
               stop_pc=STOP_PC_FOR.get(expected_exit, 0),
               psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    if not visited and not_visited == ():
        # The bitset costs a write per instruction and most cases ask it nothing; the two endings
        # that are not returns are the ones that do.
        info = leaf.run("scene_spawn_from_script", _SPAWN, allowed, case, **how)
    else:
        with leaf.pc_coverage():
            info = leaf.run("scene_spawn_from_script", _SPAWN, allowed, case, **how)
            for at in visited:
                assert emu.cov_visited(at), f"{case}: the run never executed {at:#x}"
            for at in not_visited:
                assert not emu.cov_visited(at), (
                    f"{case}: the run executed {at:#x}, so it did not take the ending this case "
                    f"names")
    assert info["ret"] == expected_exit, (
        f"{case}: the reconstruction reported exit {info['ret']}")
    return info


def spawn_record(info, slot, table=None):
    """One display record's (x, y, type, sprite), read back out of the ORACLE's write set — so a
    field the original never wrote fails outright rather than reading as the seed."""
    at = (TABLE_A30 if table is None else table) + slot * RECORD_BYTES
    return tuple(leaf.read_int(info, at + off, WORD_BYTES, f"slot {slot}")
                 for off in (ACTOR_X, wb("ACTOR_Y"), ACTOR_TYPE, ACTOR_SPRITE))


@pytest.mark.parametrize("kind", (0, 3, KIND_BOSS + 1, 0xffff))
def test_a_kind_the_ladder_does_not_name_falls_through_its_own_rts(kind):
    """The head marks WB_SCENE_SPAWN_GATE_SLOT free whichever arm runs, so an unnamed kind leaves
    that word and nothing else — AND THEN RETURNS THROUGH THE SAVED a0, which is what this case
    exists to state. The three arms each end in `movea.l (a7)+,a0`; the ladder's fall-through does
    not, so the `rts` at $19e0 takes the longword the FIRST instruction pushed.

    THE ORACLE IS WHAT FOUND IT: the first draft of this case expected a plain return and the run
    went 686,638 instructions without reaching one.
    """
    case = f"spawn kind {kind:#x}"
    start = spawn_start_record(START_RECORD_SPEECH)
    seeds = spawn_pokes(case, start, words=((DESCRIPTOR + SCENE_KIND, kind),))
    info = run_spawn(case, seeds, start,
                     expected_exit=EXIT_WILD_RETURN, reaches_hinge=False,
                     visited=(LAST_KIND_TEST,), not_visited=SPAWN_ARMS)
    leaf.assert_written_is(info, {SPAWN_GATE_SLOT: word(FREE_MARKER)}, case)


def test_only_the_three_arms_pop_the_a0_the_head_pushed():
    """The defect above, read off the bytes rather than off the run: `move.l a0,-(a7)` at the entry,
    exactly THREE `movea.l (a7)+,a0` in the whole tree — one per arm — and the `rts` at $19e0 is not
    behind any of them."""
    pops = [at for at in range(0x19ac, 0x1f36, 2)
            if bytes(harness.BASE_IMAGE[at:at + WORD_BYTES]) == movea_l_postinc(A0, 7)]
    assert pops == [0x1aec, 0x1ea4, 0x1f30], f"the tree's stack pops moved: {[hex(a) for a in pops]}"
    assert bytes(harness.BASE_IMAGE[WILD_RETURN_PC:WILD_RETURN_PC + WORD_BYTES]) == RTS


# --- kind 1: the speech scene --------------------------------------------------------------------

# The two triples of descriptor words the arm builds its three records out of. Plain numbers, in the
# order the cursor reads them: sprite, then x, then y.
SPEECH_TRIPLE_1 = (0x120, 0x0044, 0x0028)
SPEECH_TRIPLE_2 = (0x131, 0x00a0, 0x0030)
GATE_ICON = {1: 1, 2: 3, 3: 4}    # which WB_HUD_SLOT_BBC8 value each table entry keeps the script for


def effective_speech_index(gate, speech, bbc8):
    """Which speech script actually runs: the descriptor's own byte unless a dispatched gate found
    the wrong icon, in which case WB_SPAWN_GATE_REFUSED_SCRIPT has replaced it BEFORE the read."""
    if gate in GATE_ICON and bbc8 != GATE_ICON[gate]:
        return SPAWN_GATE_REFUSED_SCRIPT
    return speech


def shipped_script(index):
    """(pointer, first id) of one of the eight shipped speech scripts — the game's own bytes."""
    pointer = int.from_bytes(harness.BASE_IMAGE[SCRIPT_TABLE + index * LONGWORD_BYTES:][
        :LONGWORD_BYTES], "big")
    return pointer, harness.BASE_IMAGE[pointer]


def speech_seeds(case, *, gate=0, speech=0, bbc8=0, stage=0, bank=0,
                 triple=SPEECH_TRIPLE_1, triple2=SPEECH_TRIPLE_2):
    words = ((DESCRIPTOR + SCENE_KIND, KIND_SPEECH), (DESCRIPTOR + MAP_BANK_INDEX, bank))
    words += tuple((DESCRIPTOR + SPAWN_SCRIPT_FIRST + i * WORD_BYTES, value)
                   for i, value in enumerate(triple))
    words += tuple((DESCRIPTOR + SPAWN_TRIPLE_2 + i * WORD_BYTES, value)
                   for i, value in enumerate(triple2))
    start = spawn_start_record(START_RECORD_SPEECH)
    # (seeds, start) like `shop_seeds`, so a case cannot pair one arm's seeds with another arm's
    # start record — the model `run_spawn` derives its allowed bands from is keyed on that record.
    return spawn_pokes(case, start, bank=bank, bbc8=bbc8, stage=stage, words=words,
                       bytes_=((DESCRIPTOR + GATE_INDEX_AT, gate),
                               (DESCRIPTOR + SPEECH_INDEX_AT, speech))), start


def assert_speech_records(info, case, triple, triple2, late):
    """The three records, and the pair mechanism inside the first two: one sprite and one x apart."""
    sprite, x, y = triple
    first = LATE_STAGE_SPRITE if late else sprite
    assert spawn_record(info, 0) == (x, y, 0, first), case
    assert spawn_record(info, 1) == ((x + SPAWN_PAIR_DX) & WORD_MASK, y, 0,
                                     (first + 1) & WORD_MASK), case
    assert spawn_record(info, 2) == (triple2[1], triple2[2], 0, triple2[0]), case


def assert_rest_of_table_is_free(info, case, first_slot):
    """Every slot from `first_slot` up to the terminator marked free AGAIN, after the records."""
    for slot in range(first_slot, TABLE_A30_SLOTS):
        at = TABLE_A30 + slot * RECORD_BYTES + ACTOR_X
        assert leaf.read_int(info, at, WORD_BYTES, case) == FREE_MARKER, (
            f"{case}: slot {slot} is not free")


@pytest.mark.parametrize("speech", range(SCRIPT_COUNT))
def test_the_speech_arm_posts_the_shipped_script_its_byte_names(speech):
    """Each of the eight scripts the .PRG carries, driven through the whole arm: three records, the
    rest of the table freed, the id posted with the INFINITE lifetime, the cursor advanced past it,
    and the stage reloaded. Nothing here seeds a script — these are the game's own bytes."""
    case = f"speech script {speech}"
    seeds, start = speech_seeds(case, speech=speech)
    info = run_spawn(case, seeds, start)
    pointer, first_id = shipped_script(speech)
    assert_speech_records(info, case, SPEECH_TRIPLE_1, SPEECH_TRIPLE_2, late=False)
    assert_rest_of_table_is_free(info, case, 3)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == first_id, case
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, case) == SPEECH_LIFETIME_HELD
    assert leaf.read_int(info, SCRIPT_CURSOR, LONGWORD_BYTES, case) == pointer + 1, case
    assert leaf.read_int(info, SPAWN_GATE_SLOT, WORD_BYTES, case) == FREE_MARKER
    assert leaf.read_int(info, FLAG_A30, WORD_BYTES, case) == STATE_FLAG_SET
    assert leaf.read_int(info, SCROLL_FOLLOW_FROZEN, WORD_BYTES, case) == FROZEN_SET


# Two records past where the table's terminator ships, so the free loop walks past everything
# `actor_table_reset` covered. $9e30 itself has to stop being the terminator for that to happen.
MOVED_TERMINATOR = TABLE_A30_END + 2 * RECORD_BYTES


def test_the_free_loop_runs_past_what_the_reset_covered():
    """THE LOOP IS INVISIBLE WHILE THE TERMINATOR SITS WHERE IT SHIPS, and this case is what makes
    it visible. `actor_table_reset` has already written WB_ACTOR_FREE_MARKER over every slot from 3
    up to $9e30, so the arm's second pass re-writes the same word at the same addresses and deleting
    it changes nothing a differential can see — batch 41 phase B's sweep duly reported
    `free-loop-skipped` as a survivor, and that is a property of the ORIGINAL rather than a gap in
    the port.

    Move the terminator two records further out and the loop writes two records the reset never
    touched. What that pins is the loop's EXISTENCE and its EXTENT; its stride is pinned by the
    ordinary cases, because a wrong stride lands mid-record inside the three the arm just built.
    """
    case = "free loop past the reset"
    base, start = speech_seeds(case)
    seeds = leaf.overlay(base,
                         {TABLE_A30_END: keyed_block(TABLE_A30_END, RECORD_BYTES,
                                                     case_salt(case)),
                          MOVED_TERMINATOR: longword(ACTOR_TABLE_END)})
    assert int.from_bytes(harness.make_image(seeds)[TABLE_A30_END:][:LONGWORD_BYTES],
                          "big") != ACTOR_TABLE_END, (
        "the seeded band happens to spell the terminator, so the loop would stop where it always "
        "does and this case would be testing nothing")
    info = run_spawn(case, seeds, start,
                     extra_allowed=set(range(TABLE_A30_END,
                                             MOVED_TERMINATOR + LONGWORD_BYTES)))
    for at in (TABLE_A30_END, TABLE_A30_END + RECORD_BYTES):
        assert leaf.read_int(info, at + ACTOR_X, WORD_BYTES, case) == FREE_MARKER, (
            f"{case}: the slot at {at:#x} was not freed, so the loop stopped at the old terminator")


def test_the_speech_lifetime_is_the_infinite_one_and_not_the_drivers():
    """WB_SCENE_SPEECH_LIFETIME_HELD is what makes this arm different from every arm of $dbc0, which
    all post WB_TEXT_LIFETIME_DEFAULT — so the box the scene opens with waits for the player."""
    assert SPEECH_LIFETIME_HELD != TEXT_LIFETIME_DEFAULT


@pytest.mark.parametrize("gate", sorted(GATE_ICON))
@pytest.mark.parametrize("matched", (True, False))
def test_a_dispatched_gate_is_read_back_before_the_speech_index(gate, matched):
    """THE READ-AFTER-STORE, driven both ways. The gate writes the descriptor byte the very next
    instruction reads, so a mismatched icon runs script WB_SPAWN_GATE_REFUSED_SCRIPT instead of the
    descriptor's own — and clears WB_SCENE_EXIT_ACTION behind it. A port that fetched both script
    bytes before dispatching would pass the matched half of this and fail the other."""
    speech = 2
    bbc8 = GATE_ICON[gate] if matched else GATE_ICON[gate] ^ 0xff
    case = f"gate {gate} {'matched' if matched else 'refused'}"
    seeds, start = speech_seeds(case, gate=gate, speech=speech, bbc8=bbc8)
    info = run_spawn(case, seeds, start)

    index = effective_speech_index(gate, speech, bbc8)
    assert index == (speech if matched else SPAWN_GATE_REFUSED_SCRIPT)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == shipped_script(index)[1], case
    assert leaf.read_int(info, SCRIPT_CURSOR, LONGWORD_BYTES, case) == shipped_script(index)[0] + 1
    if not matched:
        assert leaf.read_int(info, DESCRIPTOR + SPEECH_INDEX_AT, 1, case) == (
            SPAWN_GATE_REFUSED_SCRIPT)
        assert leaf.read_int(info, DESCRIPTOR + SCENE_EXIT_ACTION, WORD_BYTES, case) == 0


# A cursor whose HIGH half is nonzero and whose LOW half still names a readable image byte, so the
# `clr.w` and a `clr.l` leave different addresses behind.
SEEDED_CURSOR = 0x00023456


def test_the_cursor_clear_is_a_WORD_and_script_eight_is_what_shows_it():
    """`clr.w $1017c.l` clears only the HIGH half of a LONGWORD cursor, and on every ordinary index
    that is INVISIBLE: the `move.l (a0),$1017c.l` eight instructions later overwrites the whole
    longword. Batch 41 phase B's sweep reported `speech-cursor-cleared-as-a-longword` as a survivor
    for exactly that reason.

    SCRIPT INDEX 8 IS WHERE IT SHOWS. WB_SPEECH_SCRIPT_TABLE is eight longwords BOUNDED BY THE
    CURSOR ITSELF, so index 8's offset lands on `$1017c` and the `move.l` stores the cursor over
    itself — a no-op. What survives to be followed is therefore whatever the `clr.w` left: the
    seeded cursor with its high half gone. A port that cleared the longword would follow 0 instead,
    and a port that cleared nothing would follow the whole seeded pointer.
    """
    case = "speech script eight"
    assert SCRIPT_TABLE + SCRIPT_COUNT * LONGWORD_BYTES == SCRIPT_CURSOR, (
        "index 8's offset no longer lands on the cursor, so this case is about nothing")
    base, start = speech_seeds(case)
    seeds = leaf.overlay(base, {DESCRIPTOR + SPEECH_INDEX_AT: bytes([SCRIPT_COUNT]),
                                SCRIPT_CURSOR: longword(SEEDED_CURSOR)})
    info = run_spawn(case, seeds, start)
    followed = SEEDED_CURSOR & WORD_MASK
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == harness.BASE_IMAGE[followed], case
    assert leaf.read_int(info, SCRIPT_CURSOR, LONGWORD_BYTES, case) == followed + 1, case


def test_a_gate_index_of_zero_dispatches_nothing():
    """`beq.w $1a7c` — index 0 skips the `jsr` altogether, which is why entry 0 of the table need
    not be an address. The descriptor's own script runs and its exit action survives."""
    case = "gate index zero"
    seeds, start = speech_seeds(case, gate=0, speech=5, bbc8=0)
    info = run_spawn(case, seeds, start)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == shipped_script(5)[1], case
    assert DESCRIPTOR + SCENE_EXIT_ACTION not in leaf.program_writes(info), (
        "index 0 dispatched a gate after all")


@pytest.mark.parametrize("stage", (0, LATE_STAGE_FIRST - 1, LATE_STAGE_FIRST, 0xffff))
def test_the_late_stage_sprite_replaces_the_pairs_first_and_the_signed_compare_shows(stage):
    """`cmpi.w #$5,$bd88.l / blt` is SIGNED, so WB_STAGE_NUMBER $ffff reads as -1 and takes the
    EARLY arm — which is the whole difference between this test and one that used an unsigned
    compare. Only the PAIR's sprite is replaced; the third record's own is untouched."""
    case = f"late stage {stage:#x}"
    seeds, start = speech_seeds(case, stage=stage)
    info = run_spawn(case, seeds, start)
    assert_speech_records(info, case, SPEECH_TRIPLE_1, SPEECH_TRIPLE_2,
                          late=s16(stage) >= LATE_STAGE_FIRST)


def test_the_pairs_x_and_sprite_wrap_inside_their_words():
    """`addi.w #$40,d1` and `addi.w #$1,d0` are WORD adds, so a pair whose x is near $ffff wraps
    rather than carrying anywhere."""
    case = "pair wraps"
    triple = (WORD_MASK, WORD_MASK - 0x10, 0x0030)
    seeds, start = speech_seeds(case, triple=triple)
    info = run_spawn(case, seeds, start)
    assert_speech_records(info, case, triple, SPEECH_TRIPLE_2, late=False)
    assert spawn_record(info, 1)[0] == (WORD_MASK - 0x10 + SPAWN_PAIR_DX) & WORD_MASK
    assert spawn_record(info, 1)[3] == 0


@pytest.mark.parametrize("bank", range(MAP_BANK_COUNT))
def test_the_speech_arm_loads_the_bank_entry_its_descriptor_word_names(bank):
    """Only the chosen entry names the map this case seeds, so an arm that indexed the table wrongly
    would load a different one — and the byte-for-byte diff over eight scroll buffers is what says
    it did not."""
    case = f"speech bank {bank}"
    seeds, start = speech_seeds(case, bank=bank)
    run_spawn(case, seeds, start)


def test_the_shop_index_past_the_table_reads_the_pointer_it_is_about_to_write():
    """Index 8's offset lands ON WB_SHOP_RECORD_PTR itself — the longword that BOUNDS the table —
    so `move.l (a0),$10448.l / movea.l (a0),a0` stores the pointer over itself and then follows it.

    IT IS THE ALIAS CASE FOR THIS ARM'S DOUBLE READ. The original reads `(a0)` twice with its own
    store between them, and this is the one index where those two addresses coincide: a port that
    cached the first read would agree here by luck, and one that re-read (as this one does) is
    right for the reason rather than the value. The store writes exactly what the first read
    returned, so the arm is idempotent — which is what makes the index drivable at all.
    """
    case = "shop record index past the table"
    seeds, start = shop_seeds(case, index=SHOP_RECORD_COUNT)
    assert (SHOP_RECORD_TABLE + SHOP_RECORD_COUNT * LONGWORD_BYTES) == SHOP_RECORD_PTR, (
        "index 8's offset no longer lands on the pointer, so this case is about nothing")
    info = run_shop(case, seeds, start)
    assert leaf.read_int(info, SHOP_RECORD_PTR, LONGWORD_BYTES, case) == SHOP_RECORD, case
    assert leaf.read_int(info, SHOP_RECORD + SHOP_ENTER_COUNT, WORD_BYTES, case) == 1, case


# THE TWO ALIAS CASES FOR THIS ARM'S READ-AFTER-STORE ORDERING, and both need a record the arm's
# own stores can reach. Index 8's offset lands ON WB_SHOP_RECORD_PTR (the table's bound), so the
# pointer the arm follows is whatever a case seeds THERE — which is how a record can be put anywhere.
#
# The display build reads each record's sprite field AFTER storing that record's xy and type, so a
# record placed WB_SHOP_ITEM1_SPRITE below the table makes field 54 the very word slot 0's xy store
# has just written.
# THREE placements, because ONE pins only the record it touches: the sweep's
# `display-second-field-read-before-the-stores` and `sign-field-read-before-the-stores` both
# survived a case that aliased slot 0 alone. Each entry is (what the field lands on, where the
# record goes, the (slot, sprite) pairs that alias proves), and together they cover the item pair
# and the sign — the three shapes the arm has.
DISPLAY_ALIAS_PLACEMENTS = (
    ("slot 0's x, read for record 0's own sprite", TABLE_A30 - SHOP_ITEM1_SPRITE, True,
     ((0, DISPLAY_ITEM1_XY >> 16), (1, DISPLAY_ITEM1_XY & WORD_MASK))),
    ("slot 1's x, read for record 1's own sprite",
     TABLE_A30 + RECORD_BYTES - SHOP_ITEM2_SPRITE, True, ((1, DISPLAY_ITEM2_XY >> 16),)),
    # ...and the sign pair, whose sprite field IS the aliased word, so this one cannot seed it.
    # IT HAS TO ALIAS THE X WORD AND NOT THE TYPE WORD: `actor_table_reset` has already zeroed every
    # type, so a read before the store and a read after it both see 0 and the mutant lives. The x
    # word the reset leaves is WB_ACTOR_FREE_MARKER, which the sign's own store then replaces — so
    # THAT is the byte where "before" and "after" differ. (The sign's xy comes from a field the
    # reset has zeroed, so the store writes 0 and the sprite reads back 0.)
    ("slot 2's x, read for the sign's own sprite",
     TABLE_A30 + 2 * RECORD_BYTES + ACTOR_X - SHOP_SIGN_SPRITE, False, ((2, 0), (3, 1))),
)
ALIASED_DISPLAY_RECORD = TABLE_A30 - SHOP_ITEM1_SPRITE
# ...and the refusal's `addq.w #1,42(a0)` re-reads its count AFTER the message post, so a record
# placed WB_SHOP_REFUSED_COUNT below WB_TEXT_REQUEST makes field 42 the word that post rewrites.
ALIASED_REFUSAL_RECORD = TEXT_REQUEST - REFUSED_COUNT


@pytest.mark.parametrize("what, record, seed_sign, expected", DISPLAY_ALIAS_PLACEMENTS)
def test_a_display_records_sprite_is_read_after_its_own_xy_and_type_stores(what, record, seed_sign,
                                                                           expected):
    """`move.l #imm,(a1)+ / move.w #imm,(a1)+ / move.w 54(a0),(a1)+` — the field read is the THIRD
    instruction, not the first, and these three placements are what make the difference visible.

    Put the record so that its sprite FIELD lands on a word the build has just written, and the
    sprite that comes back is that word. A port that evaluated the field read as a call ARGUMENT —
    before the stores, which is what C's unspecified argument order gives you — reads the seed
    instead. ONE placement was not enough: it pins only the record whose store it aliases, and the
    sweep duly kept `display-second-field-read-before-the-stores` and
    `sign-field-read-before-the-stores` alive until the other two went in.
    """
    case = f"shop display alias on {what}"
    seeds, start = shop_seeds(case, index=SHOP_RECORD_COUNT)
    layer = {
        record: keyed_block(record, SHOP_RECORD_BYTES, case_salt(case)),
        SHOP_RECORD_PTR: longword(record),
        record + SHOP_ENTER_COUNT: word(0),
        record + SHOP_ENTER_MSG_FIRST: word(0x0021),
    }
    if seed_sign:
        # not WB_SHOP_SIGN_SPRITE_INTRO, so the tail takes the ordinary entry greeting
        layer[record + SHOP_SIGN_SPRITE] = word(SHOP_SIGN_SPRITE_INTRO + 1)
    info = run_shop(case, leaf.overlay(seeds, layer), start,
                    extra_allowed=set(range(record, record + SHOP_RECORD_BYTES)))
    assert leaf.read_int(info, SHOP_RECORD_PTR, LONGWORD_BYTES, case) == record
    for slot, sprite in expected:
        assert spawn_record(info, slot)[3] == sprite, (
            f"{case}: slot {slot}'s sprite is {spawn_record(info, slot)[3]:#x}, not the {sprite:#x} "
            f"the store it aliases had just written")


def test_the_refusal_count_bump_re_reads_after_the_message_is_posted():
    """`addq.w #1,42(a0)` is a MEMORY read-modify-write and it runs AFTER the post and after
    WB_SCENE_MESSAGE_PENDING, so the value it increments is whatever those stores left.

    With the record 42 bytes below WB_TEXT_REQUEST, field 42 IS the word the post rewrites: it reads
    zero on the way in (so the arm takes WB_SHOP_BROKE_MSG_FIRST), the post puts $11 in its high
    byte, and the bump therefore leaves $1101. A port that incremented the count it had CACHED for
    the message select leaves $0001 — and with it a WB_TEXT_REQUEST of zero instead of the id it
    just posted.
    """
    case = "shop refusal count alias"
    seeds, start = shop_seeds(case, index=SHOP_RECORD_COUNT, purse=SHOP_PURSE_BROKE)
    band = set(range(ALIASED_REFUSAL_RECORD, ALIASED_REFUSAL_RECORD + SHOP_RECORD_BYTES))
    seeds = leaf.overlay(seeds, {
        ALIASED_REFUSAL_RECORD: keyed_block(ALIASED_REFUSAL_RECORD, SHOP_RECORD_BYTES,
                                            case_salt(case)),
        SHOP_RECORD_PTR: longword(ALIASED_REFUSAL_RECORD),
        ALIASED_REFUSAL_RECORD + SHOP_SIGN_SPRITE: word(SHOP_SIGN_SPRITE_INTRO),
        ALIASED_REFUSAL_RECORD + ITEM2_PRICE: word(SHOP_PURSE_BROKE + 1),
        ALIASED_REFUSAL_RECORD + SHOP_ENTER_COUNT: word(0),
        # field 42 IS this word, and it has to read ZERO for the arm to pick the first id
        TEXT_REQUEST: word(0),
    })
    info = run_shop(case, seeds, start, extra_allowed=band)
    posted_then_bumped = (BROKE_MSG_FIRST << 8) | 1
    assert leaf.read_int(info, ALIASED_REFUSAL_RECORD + REFUSED_COUNT, WORD_BYTES,
                         case) == posted_then_bumped, (
        f"{case}: the bump did not re-read the word the post had just changed")
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == BROKE_MSG_FIRST, (
        f"{case}: the posted id did not survive the bump")


# --- kind 4: the boss scene ----------------------------------------------------------------------

BOSS_MESSAGE = 0x0037             # the descriptor word at +14, posted as its LOW byte
BOSS_DEAD_WORD = 0x1234           # ...and the one at +12, which nothing spends
BOSS_FOLLOW_SLOT = (BOSS_FOLLOW - TABLE_A32) // RECORD_BYTES


def boss_seeds(case, *, bank=BOSS_MAP_BANK_OFFSET // MAP_BANK_BYTES, index=5,
               message=BOSS_MESSAGE):
    """The boss arm's descriptor. ``index`` is the word at WB_SCENE_MAP_BANK_INDEX and is
    deliberately NOT ``bank``: this arm overwrites the index it just shifted, so a case that seeded
    the two equal could not tell an arm that honoured the descriptor from one that did not."""
    start = spawn_start_record(START_RECORD_BOSS)
    return spawn_pokes(case, start, bank=bank,
                       words=((DESCRIPTOR + SCENE_KIND, KIND_BOSS),
                              (DESCRIPTOR + MAP_BANK_INDEX, index),
                              (DESCRIPTOR + BOSS_DEAD_WORD_AT, BOSS_DEAD_WORD),
                              (DESCRIPTOR + BOSS_MESSAGE_AT, message))), start


@pytest.mark.parametrize("index", (0, 1, 3, MAP_BANK_COUNT - 1))
def test_the_boss_arm_ignores_the_descriptors_bank_index(index):
    """`lsl.w #3,d0` and then `move.w #$10,d0` two instructions later: the shift is DEAD and the arm
    always takes WB_SCENE_BOSS_MAP_BANK_OFFSET. Only that entry names the map this case seeds, so an
    arm that followed the descriptor would load an unseeded one and the eight scroll buffers would
    diverge."""
    case = f"boss bank index {index}"
    seeds, start = boss_seeds(case, index=index)
    run_spawn(case, seeds, start)


def test_the_boss_arm_arms_the_followed_record_as_the_players_own_type():
    """One record and not three: WB_ACTOR_FOLLOWED_A32 given a fixed position, a fixed pair of sizes
    and WB_SCENE_BOSS_FOLLOW_TYPE — which is behaviour slot 1, the PLAYER's."""
    case = "boss followed record"
    seeds, start = boss_seeds(case)
    info = run_spawn(case, seeds, start)
    assert spawn_record(info, BOSS_FOLLOW_SLOT, TABLE_A32) == (
        BOSS_FOLLOW_XY >> 16, BOSS_FOLLOW_XY & WORD_MASK, BOSS_FOLLOW_TYPE, 0), case
    assert leaf.read_int(info, BOSS_FOLLOW + ACTOR_HALF_WIDTH, LONGWORD_BYTES,
                         case) == BOSS_FOLLOW_SIZES
    for slot in range(TABLE_A30_SLOTS):
        if slot == BOSS_FOLLOW_SLOT:
            continue
        assert leaf.read_int(info, TABLE_A32 + slot * RECORD_BYTES + ACTOR_X, WORD_BYTES,
                             case) == FREE_MARKER, f"{case}: A32 slot {slot} is not free"


@pytest.mark.parametrize("message", (0, 1, BOSS_MESSAGE, 0x12ff, WORD_MASK))
def test_the_boss_arm_posts_the_low_byte_of_its_descriptor_word(message):
    """`move.b d1,$c030.l` — the id is the word's LOW byte, and the lifetime is the ordinary $32
    rather than the speech arm's infinite one. The word BELOW it is read into d0 and never spent."""
    case = f"boss message {message:#06x}"
    seeds, start = boss_seeds(case, message=message)
    info = run_spawn(case, seeds, start)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == (message & 0xff), case
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, case) == TEXT_LIFETIME_DEFAULT
    assert leaf.read_int(info, PANEL_FRAME_HOLD, WORD_BYTES, case) == 0
    assert leaf.read_int(info, FLAG_A32, WORD_BYTES, case) == STATE_FLAG_SET
    assert leaf.read_int(info, STATE_FLAG_A34, WORD_BYTES, case) == 0


# --- kind 2: the shop counter --------------------------------------------------------------------

# One shop record's fields, as plain numbers. The two prices are what the price plates draw, the two
# item sprites what stands at each cursor position, and the sign is the pair.
SHOP_SEED = {SHOP_ITEM1_SPRITE: 0x0141, SHOP_ITEM2_SPRITE: 0x0142,
             SHOP_SIGN_SPRITE: 0x0150, ITEM1_PRICE: 0x0120, ITEM2_PRICE: 0x0340,
             SHOP_ENTER_MSG_FIRST: 0x0021, SHOP_ENTER_MSG_SECOND: 0x0022,
             SHOP_ENTER_MSG_LATER: 0x0023}
SHOP_SIGN_AT = 0x00600018         # the longword at WB_SHOP_SIGN_XY: x $60, y $18
SHOP_PURSE_RICH = 0x0999          # packed BCD, above WB_SHOP_ITEM2_PRICE
SHOP_PURSE_BROKE = 0x0100         # ...and below it
SHOP_TAIL_RETURN = 0x1e42         # `addq.w #1,38(a0)` — reached by BOTH returning paths


def shop_seeds(case, *, index=0, count=0, refused=0, sign_sprite=None,
               purse=SHOP_PURSE_RICH, stage=0, bank=0, fields=()):
    """The descriptor, the shop record the tree plants, and the purse the tail compares.

    ONE SEED, TWO READINGS: WB_SCENE_VARIANT is both the WB_SHOP_RECORD_TABLE index the arm walks in
    and the word the tail tests to pick its start record, so a case cannot set the two apart —
    index 0 is exactly the case that takes WB_SCENE_START_RECORD_SHOP_ALT.
    """
    record = dict(SHOP_SEED)
    record.update(fields)
    if sign_sprite is not None:
        record[SHOP_SIGN_SPRITE] = sign_sprite
    record[SHOP_ENTER_COUNT] = count
    record[REFUSED_COUNT] = refused
    words = ((DESCRIPTOR + SCENE_KIND, KIND_SHOP), (DESCRIPTOR + MAP_BANK_INDEX, bank),
             (DESCRIPTOR + SCENE_VARIANT, index), (BCD_COUNTER, purse))
    words += tuple((SHOP_RECORD + off, value) for off, value in sorted(record.items()))
    start = spawn_start_record(START_RECORD_SHOP if index else START_RECORD_SHOP_ALT)
    return spawn_pokes(case, start, bank=bank, stage=stage, words=words), start


def shop_expected_records(image, late):
    """The eight display records, in the order the arm writes them."""
    sign_xy = int.from_bytes(bytes(image[SHOP_RECORD + SHOP_SIGN_XY:][:LONGWORD_BYTES]), "big")
    sign = LATE_STAGE_SPRITE if late else leaf.u16(image, SHOP_RECORD + SHOP_SIGN_SPRITE)
    paired = (sign_xy + (SPAWN_PAIR_DX << 16)) & 0xffffffff
    return [
        (DISPLAY_ITEM1_XY >> 16, DISPLAY_ITEM1_XY & WORD_MASK, 0,
         leaf.u16(image, SHOP_RECORD + SHOP_ITEM1_SPRITE)),
        (DISPLAY_ITEM2_XY >> 16, DISPLAY_ITEM2_XY & WORD_MASK, 0,
         leaf.u16(image, SHOP_RECORD + SHOP_ITEM2_SPRITE)),
        (sign_xy >> 16, sign_xy & WORD_MASK, 0, sign),
        (paired >> 16, paired & WORD_MASK, 0, (sign + 1) & WORD_MASK),
        (DISPLAY_LEAVE_XY >> 16, DISPLAY_LEAVE_XY & WORD_MASK, 0, DISPLAY_LEAVE_SPRITE),
        (DISPLAY_PRICE1_XY >> 16, DISPLAY_PRICE1_XY & WORD_MASK, 0, DISPLAY_PRICE1_SPRITE),
        (DISPLAY_PRICE2_XY >> 16, DISPLAY_PRICE2_XY & WORD_MASK, 0, DISPLAY_PRICE2_SPRITE),
        (DISPLAY_EXTRA_XY >> 16, DISPLAY_EXTRA_XY & WORD_MASK, DISPLAY_EXTRA_TYPE,
         DISPLAY_EXTRA_SPRITE),
    ]


def assert_price_plate(info, case, sprite, price):
    """Every byte of one price plate, out of the shipped fonts — which is what says the tree handed
    shop_render_price_digits the resource and the field this plate is drawn from."""
    for at, expected in price_plate_writes(sprite, price).items():
        assert leaf.read_int(info, at, 1, case) == expected[0], (
            f"{case}: the plate at {sprite:#x} differs at {at:#x}")


def run_shop(case, seeds, start, **kwargs):
    return run_spawn(case, seeds, start, cap=SPAWN_SHOP_CAP, **kwargs)


@pytest.mark.parametrize("stage", (0, LATE_STAGE_FIRST))
def test_the_shop_arm_builds_its_eight_records_and_both_price_plates(stage):
    """The counter, whole: eight display records out of the record the descriptor's index names, the
    rest of the table freed, and the two price plates drawn from WB_SHOP_ITEM1_PRICE and
    WB_SHOP_ITEM2_PRICE into the sprites the records beside them show."""
    case = f"shop build stage {stage}"
    seeds, start = shop_seeds(case, stage=stage)
    image = harness.make_image(seeds)
    info = run_shop(case, seeds, start)
    for slot, expected in enumerate(shop_expected_records(image, stage >= LATE_STAGE_FIRST)):
        assert spawn_record(info, slot) == expected, f"{case}: slot {slot}"
    assert_rest_of_table_is_free(info, case, SHOP_DISPLAY_COUNT)
    assert_price_plate(info, case, PRICE_SPRITE_A, SHOP_SEED[ITEM1_PRICE])
    assert_price_plate(info, case, PRICE_SPRITE_B, SHOP_SEED[ITEM2_PRICE])
    assert leaf.read_int(info, SHOP_RECORD_PTR, LONGWORD_BYTES, case) == SHOP_RECORD


@pytest.mark.parametrize("sign_xy", (SHOP_SIGN_AT, 0xffd00018, 0x0060ffff, 0xffffffff))
def test_the_sign_pair_is_one_longword_add_and_one_word_bump(sign_xy):
    """The pair's second half: `move.l 50(a0),(a1) / addi.l #$400000,(a1)+` and then
    `addq.w #1,(a1)+` on the sprite. The longword add is what makes a sign at x $ffd0 wrap into
    $0010 and DROP the carry instead of disturbing y; $0060ffff is the case where a WORD add on the
    y half would have carried into x and this one does not.

    AND A WORD ADD ON THE X HALF IS EQUIVALENT, which is worth writing down because batch 41 phase
    B's sweep tried exactly that and the mutant SURVIVED. WB_SCENE_SPAWN_PAIR_DX enters the longword
    shifted 16, so the constant's low word is zero: the add can never carry out of y into x, and the
    carry out of x leaves the longword under both spellings. No seed can separate them — this is an
    equivalent mutant and not a hole, and the case that WOULD separate them needs a constant whose
    low word is nonzero, which this instruction's is not."""
    case = f"shop sign {sign_xy:#010x}"
    seeds, start = shop_seeds(case)
    seeds = leaf.overlay(seeds, {SHOP_RECORD + SHOP_SIGN_XY: longword(sign_xy)})
    image = harness.make_image(seeds)
    info = run_shop(case, seeds, start)
    expected = shop_expected_records(image, late=False)
    assert spawn_record(info, 2) == expected[2], case
    assert spawn_record(info, 3) == expected[3], case


@pytest.mark.parametrize("count, field", [(0, SHOP_ENTER_MSG_FIRST), (1, SHOP_ENTER_MSG_SECOND),
                                          (2, SHOP_ENTER_MSG_LATER), (3, SHOP_ENTER_MSG_FIRST),
                                          (0x1000, SHOP_ENTER_MSG_FIRST)])
def test_the_entry_greeting_posts_the_id_its_count_names_and_has_a_default(count, field):
    """`cmpi.w #$2,38(a0) / beq` and then a FALL-THROUGH to the first arm, so a count of 3 or more
    posts WB_SHOP_ENTER_MSG_FIRST again — the contrast with the refusal ladder below, whose fourth
    value reaches an `illegal`."""
    case = f"shop entry count {count:#x}"
    seeds, start = shop_seeds(case, count=count)
    info = run_shop(case, seeds, start)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == (SHOP_SEED[field] & 0xff), case
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_BYTES, case) == TEXT_LIFETIME_DEFAULT
    assert leaf.read_int(info, SHOP_RECORD + SHOP_ENTER_COUNT, WORD_BYTES,
                         case) == (count + 1) & WORD_MASK
    assert leaf.read_int(info, ACK_WAIT, WORD_BYTES, case) == MESSAGE_PENDING_SET
    assert leaf.read_int(info, GREET_COUNTDOWN, WORD_BYTES, case) == GREET_COUNTDOWN_RESET
    assert leaf.read_int(info, PANEL_FRAME_HOLD, WORD_BYTES, case) == wb("PANEL_FRAME_HOLD_SET")


@pytest.mark.parametrize("refused, expected", [(0, BROKE_MSG_FIRST), (1, BROKE_MSG_SECOND),
                                               (2, BROKE_MSG_THIRD)])
def test_a_broke_player_is_refused_and_the_refusal_is_counted(refused, expected):
    """The arm the sign sprite WB_SHOP_SIGN_SPRITE_INTRO opens: three escalating messages by
    WB_SHOP_REFUSED_COUNT, the count bumped, and BOTH the pending and the acknowledge words raised —
    where the entry greeting raises only the second."""
    case = f"shop refusal {refused}"
    seeds, start = shop_seeds(case, refused=refused, purse=SHOP_PURSE_BROKE,
                              sign_sprite=SHOP_SIGN_SPRITE_INTRO)
    info = run_shop(case, seeds, start)
    assert leaf.read_int(info, TEXT_REQUEST, 1, case) == expected, case
    assert leaf.read_int(info, SHOP_RECORD + REFUSED_COUNT, WORD_BYTES, case) == refused + 1
    assert leaf.read_int(info, MESSAGE_PENDING, WORD_BYTES, case) == MESSAGE_PENDING_SET
    assert leaf.read_int(info, ACK_WAIT, WORD_BYTES, case) == MESSAGE_PENDING_SET
    # ...and WB_SHOP_ENTER_COUNT is bumped on this path too, which is what "a refusal counts as an
    # entry" means.
    assert leaf.read_int(info, SHOP_RECORD + SHOP_ENTER_COUNT, WORD_BYTES, case) == 1


def test_a_fourth_refusal_reaches_the_originals_own_illegal_instruction():
    """AN ORIGINAL DEFECT, and the one ending in this tree that is not an `rts`: nothing resets
    WB_SHOP_REFUSED_COUNT, so a counter that has turned the player away three times executes the
    `illegal` at $1d8e on the fourth. The port reports WB_SCENE_EXIT_ILLEGAL and the case diffs the
    whole image at the instant control arrives there.

    THE WITNESS IS NEGATIVE: `cmpi.w #$2,d0` above the `illegal` runs on the count-2 path as well,
    and there is no instruction below it on this one — so what separates them is that the returning
    paths all reach `addq.w #1,38(a0)` and this one never does."""
    case = "shop fourth refusal"
    seeds, start = shop_seeds(case, refused=3, purse=SHOP_PURSE_BROKE,
                              sign_sprite=SHOP_SIGN_SPRITE_INTRO)
    run_shop(case, seeds, start, expected_exit=EXIT_ILLEGAL, reaches_hinge=False,
             visited=(transfer_at("shop refusal illegal"),), not_visited=(SHOP_TAIL_RETURN,))


@pytest.mark.parametrize("purse, sign_sprite, refused_expected", [
    (SHOP_PURSE_BROKE, SHOP_SIGN_SPRITE_INTRO, True),
    (SHOP_PURSE_RICH, SHOP_SIGN_SPRITE_INTRO, False),
    (SHOP_PURSE_BROKE, SHOP_SIGN_SPRITE_INTRO + 1, False),
    (SHOP_SEED[ITEM2_PRICE], SHOP_SIGN_SPRITE_INTRO, True),
    (0x8000, SHOP_SIGN_SPRITE_INTRO, True),
])
def test_the_refusal_needs_both_the_sign_and_a_signed_purse_compare(purse, sign_sprite,
                                                                    refused_expected):
    """Two conditions and a SIGNED compare. `cmp.w d1,d0 / bgt` reads WB_BCD_COUNTER against
    WB_SHOP_ITEM2_PRICE as signed words, so a purse of $8000 — four packed-BCD digits the panel draws
    as 8000 — is NEGATIVE and refused however rich the player looks; and a purse EQUAL to the price
    is refused too, because the branch away is `bgt` and not `bge`."""
    case = f"shop refusal gate {purse:#06x}/{sign_sprite:#x}"
    seeds, start = shop_seeds(case, purse=purse, sign_sprite=sign_sprite)
    info = run_shop(case, seeds, start)
    posted = leaf.read_int(info, TEXT_REQUEST, 1, case)
    assert (posted == BROKE_MSG_FIRST) == refused_expected, (
        f"{case}: posted {posted:#x}")
    assert (MESSAGE_PENDING in leaf.program_writes(info)) == refused_expected, case


@pytest.mark.parametrize("index", range(1, SHOP_RECORD_COUNT))
def test_the_shop_index_plants_the_pointer_its_table_entry_names(index):
    """WB_SCENE_VARIANT scaled by four indexes WB_SHOP_RECORD_TABLE, and the pointer is planted in
    WB_SHOP_RECORD_PTR before it is followed. Every entry is shipped, so nothing here seeds the
    table; index 8, whose offset leaves it, is the case below."""
    case = f"shop record index {index}"
    expected = int.from_bytes(harness.BASE_IMAGE[SHOP_RECORD_TABLE + index * LONGWORD_BYTES:][
        :LONGWORD_BYTES], "big")
    seeds, start = shop_seeds(case, index=index)
    # The record the index names is not the one this battery seeds, so the arm reads zeros out of
    # it — which is fine, both cores read the same zeros — but it WRITES its entry count, so that
    # record's own band has to be allowed as well.
    info = run_shop(case, seeds, start,
                    extra_allowed=set(range(expected, expected + SHOP_RECORD_BYTES)))
    assert leaf.read_int(info, SHOP_RECORD_PTR, LONGWORD_BYTES, case) == expected, case
