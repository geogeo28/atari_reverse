"""Differential test for THE SPINE's two key routines (src/game.c): `game_key_actions` @ $53e and
`game_unpause_on_key_release` @ $638 — game_main_loop's two leading `bsr`s.

WHAT MAKES THIS BATTERY DIFFERENT FROM EVERY OTHER ONE HERE: both routines BUSY-WAIT on
`key_last_scancode`, a byte no instruction in either of them writes. The IKBD ACIA handler stores it,
and nothing changes memory while a differential run is in flight — so before the kit's scheduled-write
model (tools/recreate_kit/TRAP_MODEL.md, "Phase 8") neither core could leave the loop and the payload
behind it was unreachable. `$638` sat REGISTERED-AND-REJECTED in ../names.txt from batch 12 with
exactly that trigger written into its plate.

Each case that drives a wait therefore declares the store the interrupt makes:

    schedule=[{"pc": UNPAUSE_WAIT_PC, "nth": 3, "addr": KEY_LAST_SCANCODE,
               "width": 1, "value": KEY_SCANCODE_P_RELEASE}]

`nth` is which arrival at the wait's own compare the release lands before, and the reconstruction
reads that byte through `sched_poll8` once per iteration — so the oracle's arrivals and the
candidate's polls are the same count, and the harness compares them. **Every wait is driven at more
than one `nth`**, because the kit's own suite measures a port that polls TWICE per iteration to be
INVISIBLE at an `nth` that is a multiple of its polling rate.

THREE OF `game_key_actions`' ENDINGS ARE NOT RETURNS. They pop game_main_loop's return address and
`jmp` into the boot chain, so the reconstruction reports which one it reached (WB_KEY_ACTIONS_* in
include/game.h) and each such case sets the kit's `stop_pc` to that `jmp` and requires the oracle's
executed-PC coverage to hold the arm's own instruction — `leaf.run_reaching`, the arrangement
test_scene.py describes.

KNOWINGLY NOT PINNED
  * WHERE the three unwinds go. `$e5ba` and `$e494` are the boot chain, which this port has not
    reconstructed; what is pinned is that control arrives at the `jmp`, with the image the original
    left at that instant.
  * THAT the interrupt really stores the release code at the iteration a case names. The schedule is
    the case's claim about the ACIA, exactly as a `hw_seed` is a case's claim about the machine —
    explicit and shared instead of implicit. What the counts pin is that both sides run the same
    wait for the same number of iterations.
  * WHAT bit 3 of `effect_state_bd6a` buys. The Help action flips it; nothing here reads it.
"""
import ctypes
import re

import pytest

import harness
import leaf
import emu       # noqa: E402  (harness puts the kit's oracle on sys.path)
import loader    # noqa: E402  (...and its loader, for the image's own base and extent)
from leaf import (A0, A7, BCHG_IMM, D0, D1, RTS, addq_l_an, addq_w_abs_l, asm, bcc, bcc_abs, bcc_s,
                  bit_op_abs_l, brief_extension_word, bsr_w, clr_b_abs_l, clr_w_abs_l,
                  cmp_b_abs_l_dn, cmp_b_imm_dn, cmpi_b_abs_l, jmp_abs_l, jsr_abs_l,
                  jsr_d16_an, lab,
                  lea_abs_l, move_b_imm_abs_l, move_w_abs_l_dn, move_w_imm_abs_l, opcode, place,
                  tst_w_abs_l, word)
from layout import wb
from test_actor import BEQ_W, BNE_S, BNE_W

# --- the image the two routines read and write ----------------------------------------------------
KEY_LAST_SCANCODE = wb("KEY_LAST_SCANCODE")
KEY_SEQUENCE_MATCHED = wb("KEY_SEQUENCE_MATCHED")
KEY_SEQUENCE_MATCHED_SET = wb("KEY_SEQUENCE_MATCHED_SET")
KEY_SEQUENCE_CURSOR = wb("KEY_SEQUENCE_CURSOR")
KEY_SEQUENCE_SCANCODES = wb("KEY_SEQUENCE_SCANCODES")
KEY_SEQUENCE_TERMINATOR = wb("KEY_SEQUENCE_TERMINATOR")
GAME_PAUSED = wb("GAME_PAUSED")
GAME_PAUSED_SET = wb("GAME_PAUSED_SET")
ROUND_END_RELOAD_REQUEST = wb("ROUND_END_RELOAD_REQUEST")
TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_REQUEST_DISMISS = wb("TEXT_REQUEST_DISMISS")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
PAUSE_MESSAGE_ID = wb("PAUSE_MESSAGE_ID")
EFFECT_STATE_BD6A_LOW = wb("EFFECT_STATE_BD6A_LOW")
EFFECT_STATE_BD6A_CHEAT_BIT = wb("EFFECT_STATE_BD6A_CHEAT_BIT")
FADE_RATE = wb("SND_FADE_RATE")
FADE_COUNTDOWN = wb("SND_FADE_COUNTDOWN")
FADE_START = wb("SND_FADE_START")

KEY_SCANCODE_P = wb("KEY_SCANCODE_P")
KEY_SCANCODE_P_RELEASE = wb("KEY_SCANCODE_P_RELEASE")
KEY_SCANCODE_N = wb("KEY_SCANCODE_N")
KEY_SCANCODE_ESC = wb("KEY_SCANCODE_ESC")
KEY_SCANCODE_HELP = wb("KEY_SCANCODE_HELP")
KEY_SCANCODE_HELP_RELEASE = wb("KEY_SCANCODE_HELP_RELEASE")
KEY_RELEASE_BIT = wb("KEY_RELEASE_BIT")

RETURNED = wb("KEY_ACTIONS_RETURNED")
ROUND_END = wb("KEY_ACTIONS_ROUND_END")
LEVEL_SKIP = wb("KEY_ACTIONS_LEVEL_SKIP")
QUIT = wb("KEY_ACTIONS_QUIT")

WORD = leaf.WORD_BYTES
BYTE = 1
SEQUENCE_LENGTH = 5           # 61 30 13 1e ff — four scancodes and the terminator

# The two addresses the unwind arms `jmp` to. Both are in the BOOT CHAIN, which this port has not
# reconstructed — `$e494` is show_data_disk_prompt and `$e5ba` is stage_sequence_advance, the latter
# named from call context only (../names.txt tags it `# ctx`). Taken from the name map rather than
# written as literals, so a rename there fails at collection; the body pin below then checks that
# the arms really transfer to them.
RELOAD_CHAIN = leaf.entry_of("stage_sequence_advance")
QUIT_CHAIN = leaf.entry_of("show_data_disk_prompt")

# The sound module's entry vector, and the slot the ESC arm calls. The stubs sit at a 14-byte pitch
# (test_sound.py pins the table's shape), so 84 is the seventh; `test_the_esc_arm_calls_the_stub_that
# _reaches_the_fade_trigger` is what says this offset is snd_start_fadeout's rather than a neighbour's.
SND_STUB_00 = leaf.entry_of("snd_stub_00")
SND_STUB_FADEOUT = 84
MOVE_L_A3_PREDEC = 0x2f0b     # the fade stub's own register save, its first instruction


# --- the one encoding this battery needs that leaf.py has not got --------------------------------
def move_b_indexed_dn(destination, base, index):
    """`move.b (An,Dn.w),Dm` — the sequence walk's one indexed read, and the byte-sized sibling of
    `leaf.move_w_indexed_dn`. The index is a WORD and the 68000 SIGN-EXTENDS it, which is what makes
    a cursor above $7fff read BELOW the table — the property two cases below turn on. (A third size
    of one instruction now exists across the batteries; collapsing them is in ../STATUS.md's queue.)
    """
    return opcode(0x1030 | (destination << 9) | base) + brief_extension_word(index)


KEY_ACTIONS_ENTRY = leaf.entry_of("game_key_actions")
UNPAUSE_ENTRY = leaf.entry_of("game_unpause_on_key_release")

# The routine's code ends at the DATA block — the cheat enable, the walk's cursor and the five
# sequence bytes, with one byte of padding to the even address the arm must start at — and the arm
# the pause test branches to resumes past it. Derived rather than transcribed, and
# `test_the_pause_arm_sits_past_the_sequence_data_and_ends_where_the_unpause_begins` is what checks
# the arithmetic against the image on both sides.
SEQUENCE_DATA_START = KEY_SEQUENCE_MATCHED
SEQUENCE_DATA_PAD = 1
PAUSE_ARM_ENTRY = SEQUENCE_DATA_START + WORD + WORD + SEQUENCE_LENGTH + SEQUENCE_DATA_PAD

# --- the three bodies, assembled --------------------------------------------------------------------
# Both are pinned WHOLE rather than at their entry alone, because this battery's constants include
# two PROGRAM COUNTERS — the addresses the waits RE-READ their byte at — and a schedule at the wrong one
# would not fire at the iteration a case names. The labels below are where those PCs come from, so
# nothing here transcribes an address out of a disassembly.

def _key_actions_pieces():
    return [
        tst_w_abs_l(ROUND_END_RELOAD_REQUEST),                  # $53e
        bcc(BEQ_W, "level_skip_test"),
        clr_w_abs_l(ROUND_END_RELOAD_REQUEST),                  # $548
        lab("round_end_unwind"),
        addq_l_an(4, A7),                                       # $54e — pop game_main_loop's frame
        lab("round_end_jmp"),
        jmp_abs_l(RELOAD_CHAIN),                                # $550
        lab("level_skip_test"),
        tst_w_abs_l(KEY_SEQUENCE_MATCHED),                      # $556
        bcc(BEQ_W, "pause_test"),
        cmpi_b_abs_l(KEY_SCANCODE_N, KEY_LAST_SCANCODE),        # $560
        bcc(BNE_W, "pause_test"),
        lab("level_skip_unwind"),
        addq_l_an(4, A7),                                       # $56c
        lab("level_skip_jmp"),
        jmp_abs_l(RELOAD_CHAIN),                                # $56e
        lab("pause_test"),
        cmpi_b_abs_l(KEY_SCANCODE_P, KEY_LAST_SCANCODE),        # $574
        bcc_abs(BEQ_W, PAUSE_ARM_ENTRY),                        # $57c -> the arm past the data
        cmpi_b_abs_l(KEY_SCANCODE_ESC, KEY_LAST_SCANCODE),      # $580
        bcc(BNE_W, "walk_test"),
        addq_l_an(4, A7),                                       # $58c
        lea_abs_l(A0, SND_STUB_00),                             # $58e
        lab("quit_call"),
        jsr_d16_an(A0, SND_STUB_FADEOUT),                       # $594
        lab("quit_jmp"),
        jmp_abs_l(QUIT_CHAIN),                                  # $598
        lab("walk_test"),
        tst_w_abs_l(KEY_SEQUENCE_MATCHED),                      # $59e
        bcc(BNE_W, "help_test"),
        lea_abs_l(A0, KEY_SEQUENCE_SCANCODES),                  # $5a8
        move_w_abs_l_dn(D0, KEY_SEQUENCE_CURSOR),               # $5ae
        move_b_indexed_dn(D1, A0, D0),                          # $5b4
        cmp_b_imm_dn(D1, KEY_SEQUENCE_TERMINATOR),              # $5b8
        bcc(BEQ_W, "sequence_matched"),
        cmp_b_abs_l_dn(D1, KEY_LAST_SCANCODE),                  # $5c0
        bcc(BNE_W, "help_test"),
        addq_w_abs_l(1, KEY_SEQUENCE_CURSOR),                   # $5ca
        lab("help_test"),
        tst_w_abs_l(KEY_SEQUENCE_MATCHED),                      # $5d0
        bcc(BEQ_W, "out"),
        cmpi_b_abs_l(KEY_SCANCODE_HELP, KEY_LAST_SCANCODE),     # $5da
        bcc(BNE_W, "out"),
        lab("help_wait"),
        cmpi_b_abs_l(KEY_SCANCODE_HELP_RELEASE, KEY_LAST_SCANCODE),   # $5e6
        bcc_s(BNE_S, "help_wait"),
        bit_op_abs_l(BCHG_IMM, EFFECT_STATE_BD6A_CHEAT_BIT, EFFECT_STATE_BD6A_LOW),  # $5f0
        lab("out"),
        RTS,                                                    # $5f8
        lab("sequence_matched"),
        move_w_imm_abs_l(KEY_SEQUENCE_MATCHED_SET, KEY_SEQUENCE_MATCHED),     # $5fa
        RTS,                                                    # $602
    ]


def _pause_arm_pieces():
    """$60e — the arm the pause test branches to, reached by nothing else. It is separated from the
    body above by the ten DATA bytes at $604 (the cheat enable, the cursor and the five scancodes),
    which is why the routine is pinned as two blocks and the gap as bytes."""
    return [
        lab("pause_wait"),
        cmpi_b_abs_l(KEY_SCANCODE_P_RELEASE, KEY_LAST_SCANCODE),    # $60e
        bcc_s(BNE_S, "pause_wait"),
        clr_b_abs_l(KEY_LAST_SCANCODE),                             # $618
        move_w_imm_abs_l(GAME_PAUSED_SET, GAME_PAUSED),             # $61e
        move_b_imm_abs_l(PAUSE_MESSAGE_ID, TEXT_REQUEST),           # $626
        # A BYTE store over a WORD: it clears only WB_TEXT_LIFETIME_REQUEST's high byte.
        move_b_imm_abs_l(0, TEXT_LIFETIME_REQUEST),                 # $62e
        RTS,                                                        # $636
    ]


def _unpause_pieces():
    return [
        tst_w_abs_l(GAME_PAUSED),                               # $638
        bcc(BEQ_W, "out"),
        cmpi_b_abs_l(KEY_SCANCODE_P, KEY_LAST_SCANCODE),        # $642 — the PRESS, not a poll
        bcc(BNE_W, "out"),
        lab("unpause_wait"),
        cmpi_b_abs_l(KEY_SCANCODE_P_RELEASE, KEY_LAST_SCANCODE),  # $64e
        bcc_s(BNE_S, "unpause_wait"),
        clr_b_abs_l(KEY_LAST_SCANCODE),                         # $658
        clr_w_abs_l(GAME_PAUSED),                               # $65e
        move_b_imm_abs_l(TEXT_REQUEST_DISMISS, TEXT_REQUEST),   # $664
        lab("out"),
        RTS,                                                    # $66c
    ]


_KEY_ACTIONS_LABELS = place(KEY_ACTIONS_ENTRY, _key_actions_pieces())
_PAUSE_LABELS = place(PAUSE_ARM_ENTRY, _pause_arm_pieces())
_UNPAUSE_LABELS = place(UNPAUSE_ENTRY, _unpause_pieces())

# THE THREE PROGRAM COUNTERS THE SCHEDULES NAME, out of the layout rather than out of a listing.
PAUSE_WAIT_PC = _PAUSE_LABELS["pause_wait"]
HELP_WAIT_PC = _KEY_ACTIONS_LABELS["help_wait"]
UNPAUSE_WAIT_PC = _UNPAUSE_LABELS["unpause_wait"]
# ...and the checkpoints and witnesses of the three unwind arms.
ROUND_END_JMP = _KEY_ACTIONS_LABELS["round_end_jmp"]
ROUND_END_UNWIND = _KEY_ACTIONS_LABELS["round_end_unwind"]
LEVEL_SKIP_JMP = _KEY_ACTIONS_LABELS["level_skip_jmp"]
LEVEL_SKIP_UNWIND = _KEY_ACTIONS_LABELS["level_skip_unwind"]
QUIT_JMP = _KEY_ACTIONS_LABELS["quit_jmp"]
QUIT_CALL = _KEY_ACTIONS_LABELS["quit_call"]

# --- flip_screen's body, and the two PROGRAM COUNTERS inside it ---------------------------------
FLIP_ENTRY = leaf.entry_of("flip_screen")

# The buffers the swap moves, and the ones the frame draws into. Two of the game's own screen
# addresses (leaf.SCREEN_BUFFERS), so the published bytes are the ones the shifter really takes —
# and they differ in BOTH published bytes, which would make a port that published the pre-swap
# pointer separable... except that nothing observes the publish at all. See the honestly-unpinned
# note on the flash case.
FRONT_AT_ENTRY, BACK_AT_ENTRY = leaf.SCREEN_BUFFERS
SCREEN_BUFFER_BYTES = 0x8000          # the spacing of the two, and what one frame may fill

VBL_COUNTER = wb("VBL_COUNTER")           # ...which vbl_handler raises, further down this file
SCREEN_FRONT = wb("SCREEN_FRONT")
SCREEN_BACK = wb("SCREEN_BACK")
# The two bytes of the front-buffer longword the shifter is handed: bits 16-23 and 8-15. Derived
# here rather than read from the header, because `layout.wb` scrapes plain-integer #defines and
# these are expressions over WB_SCREEN_FRONT. The body pin below is what says the image's operands
# really are $74d and $74e.
SCREEN_FRONT_BITS_16_23 = SCREEN_FRONT + 1
SCREEN_FRONT_BITS_8_15 = SCREEN_FRONT + 2
FRAME_TOGGLE = wb("FRAME_TOGGLE")
FLASH_TIMER = wb("FLASH_TIMER")
VBL_COUNTER_READY = wb("VBL_COUNTER_READY")
FLIP_READY_WAIT_PC = wb("FLIP_READY_WAIT_PC")
FLIP_TICK_WAIT_PC = wb("FLIP_TICK_WAIT_PC")
SHIFTER_SCREEN_BASE_HIGH = wb("SHIFTER_SCREEN_BASE_HIGH")
SHIFTER_SCREEN_BASE_MID = wb("SHIFTER_SCREEN_BASE_MID")
SHIFTER_PALETTE = wb("SHIFTER_PALETTE")
FLASH_COLOUR_WHITE = wb("FLASH_COLOUR_WHITE")

LONG = leaf.LONGWORD_BYTES


# --- the encodings this routine needs that leaf.py has not got ------------------------------------
def move_l_abs_l_dn(reg, addr):
    """`move.l <abs>.l,Dn` — the swap's first instruction, which is what keeps the OLD front."""
    return opcode(0x2039 | (reg << 9)) + leaf.longword(addr)


def move_l_dn_abs_l(reg, addr):
    """`move.l Dn,<abs>.l` — ...and its last."""
    return opcode(0x23c0 | reg) + leaf.longword(addr)


def move_size_abs_l_abs_l(size_opcode, source, destination):
    """`move.<size> <abs>.l,<abs>.l` — memory to memory, both operands absolute long. The swap's
    middle instruction is the longword form and the two screen-base publishes are the byte one."""
    return opcode(size_opcode) + leaf.longword(source) + leaf.longword(destination)


MOVE_L_ABS_L_ABS_L = 0x23f9
MOVE_B_ABS_L_ABS_L = 0x13f9


def cmpi_w_imm_dn(reg, value):
    """`cmpi.w #imm,Dn` — the first wait's SIGNED threshold."""
    return opcode(0x0c40 | reg) + word(value)


def cmp_w_abs_l_dn(reg, addr):
    """`cmp.w <abs>.l,Dn` — the second wait's compare against the copy taken above it."""
    return opcode(0xb079 | (reg << 9)) + leaf.longword(addr)


def not_w_abs_l(addr):
    """`not.w <abs>.l` — WB_FRAME_TOGGLE's 0 <-> $ffff toggle, and not a decrement."""
    return opcode(0x4679) + leaf.longword(addr)


def subq_w_abs_l(amount, addr):
    """`subq.w #n,<abs>.l` — leaf.addq_w_abs_l's counterpart; the two differ in one bit."""
    return opcode(0x5179 | ((amount & 7) << 9)) + leaf.longword(addr)


BLT_S = 0x6d00
BEQ_S = 0x6700


def _flip_pieces():
    return [
        move_l_abs_l_dn(D0, SCREEN_FRONT),                              # $694
        move_size_abs_l_abs_l(MOVE_L_ABS_L_ABS_L, SCREEN_BACK, SCREEN_FRONT),
        move_l_dn_abs_l(D0, SCREEN_BACK),                               # $6a4
        lab("ready_wait"),
        move_w_abs_l_dn(D0, VBL_COUNTER),                               # $6aa — THE SITE: the read
        lab("ready_test"),
        cmpi_w_imm_dn(D0, VBL_COUNTER_READY),                           # $6b0
        lab("ready_branch"),
        bcc_s(BLT_S, "ready_wait"),                                     # $6b4
        move_size_abs_l_abs_l(MOVE_B_ABS_L_ABS_L, SCREEN_FRONT_BITS_16_23,
                              SHIFTER_SCREEN_BASE_HIGH),                # $6b6
        move_size_abs_l_abs_l(MOVE_B_ABS_L_ABS_L, SCREEN_FRONT_BITS_8_15,
                              SHIFTER_SCREEN_BASE_MID),                 # $6c0
        move_w_abs_l_dn(D0, VBL_COUNTER),                               # $6ca — the copy, ONCE
        lab("tick_wait"),
        cmp_w_abs_l_dn(D0, VBL_COUNTER),                                # $6d0
        bcc_s(BEQ_S, "tick_wait"),                                      # $6d6
        clr_w_abs_l(VBL_COUNTER),                                       # $6d8
        not_w_abs_l(FRAME_TOGGLE),                                      # $6de
        tst_w_abs_l(FLASH_TIMER),                                       # $6e4
        bcc(BEQ_W, "no_flash"),                                         # $6ea
        subq_w_abs_l(1, FLASH_TIMER),                                   # $6ee
        bcc(BEQ_W, "flash_ends"),                                       # $6f4
        move_w_imm_abs_l(FLASH_COLOUR_WHITE, SHIFTER_PALETTE),          # $6f8
        RTS,                                                            # $700
        lab("flash_ends"),
        clr_w_abs_l(SHIFTER_PALETTE),                                   # $702
        lab("no_flash"),
        RTS,                                                            # $708
    ]


_FLIP_LABELS = place(FLIP_ENTRY, _flip_pieces())


# THE WHOLE-BODY PINS, and they cover the two routines batch 42 phase A ported and no more. Phase B
# added seven and did not assemble their bodies; saying so is the point of the second table.
ENTRY_BYTES = {
    "game_key_actions": asm(KEY_ACTIONS_ENTRY, _key_actions_pieces()),
    "game_unpause_on_key_release": asm(UNPAUSE_ENTRY, _unpause_pieces()),
    # ...and phase C's, whose two wait SITES are program counters this battery and `src/game.c` both
    # spell as constants — the same argument phase A made for the two above.
    "flip_screen": asm(FLIP_ENTRY, _flip_pieces()),
}
BODY_PINNED_COUNT = 3

# ...AND EVERY ROUTINE THIS FILE RECONSTRUCTS, against the pin it actually has. The tripwire above
# guards its own table; this one guards the FILE, and it is here because phase B left the count at
# two while the module grew to nine — so `assert_batch_is_complete`'s "N routines are reconstructed
# here" had quietly become false and six routines had left its cover without a case failing.
#
# The value is the pin, and "none" is recorded rather than hidden: a whole-body `asm()` for the
# seven is the honest next step and is in ../STATUS.md's queue, not done here.
GAME_ROUTINE_PINS = {
    "game_key_actions": "entry-bytes",              # the assembled whole-body table above
    "game_unpause_on_key_release": "entry-bytes",
    "game_latch_input_and_step_actors": "body",     # test_the_body_is_the_two_calls_and_nothing_else
    "vbl_handler": "terminator",                    # ...and its one `rte`, from the walk
    "game_snap_follow_cursor": "none",
    "round_bonus_setup": "none",
    "round_bonus_run_frame": "none",
    "psg_set_drive_select": "none",
    "floppy_deselect_drives": "none",
    "flip_screen": "entry-bytes",                   # phase C, assembled whole
    "game_main_loop": "none",                       # phase C — a COMPOSITION; see its own section
}

# --- caps ------------------------------------------------------------------------------------------
# Each arm's own instruction count plus the instruction osh_run counts past the `rts`
# (leaf.RUNNER_SENTINEL_INSN), and — for a wait — two more per iteration, since one iteration is the
# compare and the branch back. Stated from the bodies above so a cap stays a cap.
WAIT_INSNS_PER_ITERATION = 2
ARM_INSN_CAP = 24                     # the longest non-waiting path: the walk, plus its guards


def wait_cap(nth, base=ARM_INSN_CAP):
    return base + WAIT_INSNS_PER_ITERATION * nth + leaf.RUNNER_SENTINEL_INSN


# The fade stub the ESC arm calls is not a leaf: it saves a3, `bsr`s and restores. Its three
# instructions plus snd_start_fadeout's four ride on top of the arm's own.
QUIT_INSN_CAP = ARM_INSN_CAP + 3 + 4 + leaf.RUNNER_SENTINEL_INSN

# --- glue --------------------------------------------------------------------------------------
_key_actions = leaf.image_glue("game_key_actions", ctypes.c_uint32)
_unpause = leaf.image_glue("game_unpause_on_key_release")


def release(wait_pc, code, nth):
    """The store the IKBD interrupt makes, as the case declares it: `code` lands in
    WB_KEY_LAST_SCANCODE just before the `nth` execution of the wait's own compare."""
    return [{"pc": wait_pc, "nth": nth, "addr": KEY_LAST_SCANCODE, "width": BYTE, "value": code}]


# How many iterations each wait is driven for. THREE VALUES, NOT ONE, and 1 and 2 are both here on
# purpose: the kit's suite measures a port that polls twice per iteration to be invisible at an `nth`
# that is a multiple of its polling rate, so a sweep of even numbers alone would not separate one.
WAIT_ITERATIONS = (1, 2, 3, 5)


# --- the pins ------------------------------------------------------------------------------------
def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, BODY_PINNED_COUNT)


def test_every_routine_this_file_reconstructs_is_accounted_for_by_a_pin_or_by_none():
    """THE FILE's scope, not the pin table's — and the two came apart in batch 42 phase B.

    Every `src/game.c` routine the candidate defines must appear in GAME_ROUTINE_PINS, and every
    row claiming a body pin must be in ENTRY_BYTES. A routine added to the module without a row
    here fails loudly; a row claiming a pin it has not got fails too.
    """
    # ANCHORED TO THE LEDGER, not to itself. A first draft compared the table against a set it
    # DERIVED from the table, so a deleted row shrank both sides and the sweep's
    # `a-routine-loses-its-row` mutant survived. SPINE_PORTED_FROM_THE_INVENTORY is the independent
    # list — every row of it re-measured against the image by the cases above.
    assert set(GAME_ROUTINE_PINS) == {name for _addr, name, _size in SPINE_PORTED_FROM_THE_INVENTORY}, (
        "the pin table and the spine ledger name different sets of routines")
    defined = leaf._defined_symbols()
    assert set(GAME_ROUTINE_PINS) <= defined, (
        f"{sorted(set(GAME_ROUTINE_PINS) - defined)} is in the pin table but the candidate does "
        f"not define it")
    assert {n for n, pin in GAME_ROUTINE_PINS.items() if pin == "entry-bytes"} == set(ENTRY_BYTES), (
        "a row claims a place in the assembled body table that ENTRY_BYTES does not carry, or the "
        "reverse")
    assert set(GAME_ROUTINE_PINS.values()) <= {"entry-bytes", "body", "terminator", "none"}, (
        "a row carries a pin kind this case does not know how to check")


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_a_body_is_the_code_this_battery_reconstructs(name):
    """WHOLE bodies, not entry instructions: every address, immediate, branch displacement and
    operand size in one assert — including the two compares the schedules below aim at."""
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


def test_the_pause_arm_sits_past_the_sequence_data_and_ends_where_the_unpause_begins():
    """The arm at $60e is the second half of `game_key_actions`, and what separates the halves is
    DATA — so this pins both the gap's contents and the arm's own code, and then that the arm's `rts`
    is the last byte before `game_unpause_on_key_release`."""
    arm = asm(PAUSE_ARM_ENTRY, _pause_arm_pieces())
    actual = bytes(harness.BASE_IMAGE[PAUSE_ARM_ENTRY:PAUSE_ARM_ENTRY + len(arm)])
    assert actual == arm, f"the pause arm at {PAUSE_ARM_ENTRY:#x} is {actual.hex()}, not {arm.hex()}"
    assert PAUSE_ARM_ENTRY + len(arm) == UNPAUSE_ENTRY, (
        "the pause arm does not end where game_unpause_on_key_release starts")
    body = bytes(harness.BASE_IMAGE[KEY_ACTIONS_ENTRY:KEY_ACTIONS_ENTRY + len(ENTRY_BYTES[
        "game_key_actions"])])
    assert KEY_ACTIONS_ENTRY + len(body) == SEQUENCE_DATA_START, (
        "the assembled body does not end where the sequence data begins")


def test_the_sequence_the_walk_matches_is_the_four_scancodes_and_its_terminator():
    """The data between the two halves, read off the image. UNDO, B, R, A — ../names.txt's reading
    of the cheat — and the $ff the walk's terminator arm tests for."""
    sequence = bytes(harness.BASE_IMAGE[KEY_SEQUENCE_SCANCODES:
                                        KEY_SEQUENCE_SCANCODES + SEQUENCE_LENGTH])
    assert sequence == bytes([0x61, 0x30, 0x13, 0x1e, KEY_SEQUENCE_TERMINATOR]), sequence.hex()


def test_the_esc_arm_calls_the_stub_that_reaches_the_fade_trigger():
    """SND_STUB_FADEOUT is an offset into a table of seven look-alike stubs, so the body pin above
    only says the arm calls stub +84. This says +84 is snd_start_fadeout's."""
    stub = SND_STUB_00 + SND_STUB_FADEOUT
    save = bytes(harness.BASE_IMAGE[stub:stub + 2])
    call = bytes(harness.BASE_IMAGE[stub + 2:stub + 6])
    assert save == opcode(MOVE_L_A3_PREDEC), f"stub +{SND_STUB_FADEOUT} opens with {save.hex()}"
    assert call == bsr_w(stub + 2, leaf.entry_of("snd_start_fadeout")), (
        f"stub +{SND_STUB_FADEOUT} does not `bsr` to snd_start_fadeout")


def test_the_release_codes_are_their_press_codes_with_the_ikbd_release_bit_set():
    """Stated independently of both implementations: the IKBD sets bit 7 on release, so each waited
    key's two constants must differ by exactly that bit. A typo in either would otherwise make a wait
    that can never end look like one that simply was not driven."""
    assert KEY_SCANCODE_P_RELEASE == KEY_SCANCODE_P | KEY_RELEASE_BIT
    assert KEY_SCANCODE_HELP_RELEASE == KEY_SCANCODE_HELP | KEY_RELEASE_BIT


# --- game_unpause_on_key_release ------------------------------------------------------------------
# The two silent arms. Each is an image the payload must NOT run over, and the second of them holds
# the pause key so that only the paused test can be what stopped it.
UNPAUSE_SILENT = (
    (0, KEY_SCANCODE_P, "not paused, and the pause key held — only the $66e test stops this"),
    (0, 0, "not paused and no key"),
    (GAME_PAUSED_SET, 0, "paused, no key held: the press test stops it"),
    (GAME_PAUSED_SET, KEY_SCANCODE_P_RELEASE, "paused, but the key is already RELEASED — the press "
                                              "test reads the same byte the wait would and refuses"),
    (GAME_PAUSED_SET, KEY_SCANCODE_N, "paused, a different key held"),
)


@pytest.mark.parametrize("paused,scancode,why", UNPAUSE_SILENT,
                         ids=[f"{c[0]:04x}_{c[1]:02x}" for c in UNPAUSE_SILENT])
def test_the_unpause_returns_without_writing_unless_the_pause_key_is_still_held(paused, scancode,
                                                                                why):
    pokes = {GAME_PAUSED: word(paused), KEY_LAST_SCANCODE: bytes([scancode]),
             TEXT_REQUEST: bytes([PAUSE_MESSAGE_ID])}
    leaf.run("game_unpause_on_key_release", _unpause, [], why, regs={"_pokes": pokes})


@pytest.mark.parametrize("nth", WAIT_ITERATIONS)
def test_the_unpause_waits_for_the_release_then_lifts_the_pause(nth):
    """THE ROUTINE THIS BATTERY EXISTS FOR, and the one that could not be run at all before Phase 8.

    NO ATTRIBUTION PASS, and the reason is the schedule rather than a preference: the payload's
    `clr.b $879.l` lands on the very byte the entry guard at $642 branches on, so the poisoned re-run
    takes the early arm, never reaches the wait's compare, and the declared store never comes due —
    which `emu.run` correctly refuses. Each of the three written bytes is instead seeded to a value
    the routine cannot leave, which is what the pass would have bought.
    """
    pokes = {GAME_PAUSED: word(GAME_PAUSED_SET),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P]),
             TEXT_REQUEST: bytes([PAUSE_MESSAGE_ID])}     # not DISMISS: the payload must change it
    what = f"the unpause released before arrival {nth} at {UNPAUSE_WAIT_PC:#x}"
    info = leaf.run("game_unpause_on_key_release", _unpause,
                    [(KEY_LAST_SCANCODE, BYTE), (GAME_PAUSED, WORD), (TEXT_REQUEST, BYTE)], what,
                    regs={"_pokes": pokes}, poison=False, max_insns=wait_cap(nth),
                    schedule=release(UNPAUSE_WAIT_PC, KEY_SCANCODE_P_RELEASE, nth))
    written = info["writes"]
    assert written[KEY_LAST_SCANCODE] == 0, f"{what}: the scancode was not forgotten"
    assert written[TEXT_REQUEST] == TEXT_REQUEST_DISMISS, f"{what}: the box was not dismissed"
    assert leaf.read_int(info, GAME_PAUSED, WORD, what) == 0, f"{what}: still paused"
    assert info["regs"]["sched_arrivals"] == nth, (
        f"{what}: the original executed its compare {info['regs']['sched_arrivals']} time(s)")


# --- game_key_actions: the three unwinds ----------------------------------------------------------
@pytest.mark.parametrize("request_word", (0xffff, 0x0001, 0x8000),
                         ids=lambda v: f"request_{v:04x}")
def test_the_round_end_request_clears_itself_and_unwinds_out_of_the_frame_loop(request_word):
    """Arm 1, and it outranks every key: the case holds a key that would otherwise pause."""
    pokes = {ROUND_END_RELOAD_REQUEST: word(request_word),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P])}
    what = f"the round-end request {request_word:#06x}"
    info = leaf.run_reaching("game_key_actions", _key_actions, [(ROUND_END_RELOAD_REQUEST, WORD)],
                             what, ROUND_END_UNWIND, regs={"_pokes": pokes},
                             stop_pc=ROUND_END_JMP, max_insns=ARM_INSN_CAP)
    assert info["ret"] == ROUND_END, f"{what}: reported {info['ret']}"
    assert leaf.read_int(info, ROUND_END_RELOAD_REQUEST, WORD, what) == 0, (
        f"{what}: the request was not consumed")


def test_the_cheats_level_skip_takes_the_same_tail_and_leaves_the_request_alone():
    """Arm 2. It writes NOTHING — the whole difference from arm 1 — so the report and the executed
    transfer are the entire surface, which is why both are asserted."""
    pokes = {KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_N])}
    info = leaf.run_reaching("game_key_actions", _key_actions, [], "N with the cheat enabled",
                             LEVEL_SKIP_UNWIND, regs={"_pokes": pokes}, stop_pc=LEVEL_SKIP_JMP,
                             max_insns=ARM_INSN_CAP)
    assert info["ret"] == LEVEL_SKIP


def test_n_without_the_cheat_does_not_skip_the_level():
    """The guard on the arm above: the same key, the cheat off. It falls through to the walk, whose
    first sequence byte is not N, so nothing is written at all."""
    pokes = {KEY_SEQUENCE_MATCHED: word(0), KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_N]),
             KEY_SEQUENCE_CURSOR: word(0)}
    info = leaf.run("game_key_actions", _key_actions, [], "N with the cheat OFF",
                    regs={"_pokes": pokes})
    assert info["ret"] == RETURNED


def test_escape_starts_the_music_fade_and_unwinds_to_the_disk_prompt():
    """Arm 4, and the only one that calls anything: `jsr 84(a0)` on the sound module's stub table,
    which reaches snd_start_fadeout. The two fade bytes are seeded away from what it writes.

    IT WRITES THE RUNNER'S OWN RETURN SLOT, and that is the arm's doing rather than an accident: it
    pops game_main_loop's frame FIRST (`addq.l #4,a7` at $58c), so the `jsr`'s return address lands
    exactly on the longword at STACK_TOP that leaf.on_machine_stack deliberately does not excuse.
    The slot is listed here for that reason and for no other — the sub-routine's own `rts` pops it
    straight back off.
    """
    pokes = {KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_ESC]),
             FADE_COUNTDOWN: bytes([0]), FADE_RATE: bytes([0xff])}
    info = leaf.run_reaching("game_key_actions", _key_actions,
                             [(FADE_COUNTDOWN, BYTE), (FADE_RATE, BYTE),
                              (emu.STACK_TOP, leaf.LONGWORD_BYTES)], "ESC", QUIT_CALL,
                             regs={"_pokes": pokes}, stop_pc=QUIT_JMP, max_insns=QUIT_INSN_CAP)
    assert info["ret"] == QUIT
    assert info["writes"][FADE_COUNTDOWN] == FADE_START
    assert info["writes"][FADE_RATE] == FADE_START


# --- game_key_actions: the pause arm --------------------------------------------------------------
@pytest.mark.parametrize("nth", WAIT_ITERATIONS)
def test_the_pause_arm_waits_for_the_release_then_raises_the_pause(nth):
    """The mirror of the unpause, and the other half of the pair batch 12 registered.

    ITS LIFETIME STORE IS A BYTE OVER A WORD. `move.b #$0,$c034.l` clears only the high half of
    WB_TEXT_LIFETIME_REQUEST, so the low byte comes out of the seed unchanged — a port that wrote a
    word would leave $0000 and is caught here rather than by the image diff alone, since a seed of
    zero would agree either way. `poison=False` for the unpause's reason: the payload clears the
    byte the entry guard reads.
    """
    pokes = {KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P]), GAME_PAUSED: word(0),
             TEXT_REQUEST: bytes([TEXT_REQUEST_DISMISS]),
             TEXT_LIFETIME_REQUEST: word(0x1234)}   # both halves non-zero, so a word store shows
    what = f"the pause arm released before arrival {nth} at {PAUSE_WAIT_PC:#x}"
    info = leaf.run("game_key_actions", _key_actions,
                    [(KEY_LAST_SCANCODE, BYTE), (GAME_PAUSED, WORD), (TEXT_REQUEST, BYTE),
                     (TEXT_LIFETIME_REQUEST, BYTE)], what,
                    regs={"_pokes": pokes}, poison=False, max_insns=wait_cap(nth),
                    schedule=release(PAUSE_WAIT_PC, KEY_SCANCODE_P_RELEASE, nth))
    assert info["ret"] == RETURNED, "the pause arm ends in the routine's own `rts`"
    assert info["writes"][KEY_LAST_SCANCODE] == 0
    assert info["writes"][TEXT_REQUEST] == PAUSE_MESSAGE_ID
    assert leaf.read_int(info, GAME_PAUSED, WORD, what) == GAME_PAUSED_SET
    assert info["writes"][TEXT_LIFETIME_REQUEST] == 0, f"{what}: the lifetime's high byte"
    assert TEXT_LIFETIME_REQUEST + 1 not in info["writes"], (
        f"{what}: the byte store reached the lifetime's LOW half, which a word store would and a "
        f"byte store cannot")
    assert info["regs"]["sched_arrivals"] == nth


# --- game_key_actions: the cheat sequence walk ----------------------------------------------------
# (cursor, the scancode held, what the step should do). The sequence is UNDO B R A; the walk steps
# only when the byte at the cursor matches, and raises the cheat at the terminator.
WALK_CASES = (
    (0, 0x61, True, "the first byte matches — UNDO"),
    (0, 0x30, False, "the SECOND byte held while the cursor is at the first"),
    (1, 0x30, True, "mid-sequence, matching"),
    (3, 0x1e, True, "the last real byte"),
    (2, 0x00, False, "no key at all"),
    (0, 0x00, False, "no key at the start"),
)


@pytest.mark.parametrize("cursor,scancode,steps,why", WALK_CASES,
                         ids=[f"at{c[0]}_{c[1]:02x}" for c in WALK_CASES])
def test_the_sequence_walk_steps_only_on_the_byte_it_is_waiting_for(cursor, scancode, steps, why):
    pokes = {KEY_SEQUENCE_MATCHED: word(0), KEY_SEQUENCE_CURSOR: word(cursor),
             KEY_LAST_SCANCODE: bytes([scancode])}
    allowed = [(KEY_SEQUENCE_CURSOR, WORD)] if steps else []
    info = leaf.run("game_key_actions", _key_actions, allowed, why, regs={"_pokes": pokes})
    assert info["ret"] == RETURNED
    if steps:
        assert leaf.read_int(info, KEY_SEQUENCE_CURSOR, WORD, why) == cursor + 1
    else:
        assert KEY_SEQUENCE_CURSOR not in info["writes"], f"{why}: the walk stepped anyway"
    assert KEY_SEQUENCE_MATCHED not in info["writes"], f"{why}: the cheat was raised"


def test_the_terminator_raises_the_cheat_and_returns_before_the_help_action():
    """The walk's own ending, and the ordering it buys: the frame that COMPLETES the sequence returns
    at $602 rather than falling into the Help block, so a Help key held on that same frame does
    nothing. Driving it with Help held is what makes the claim a measurement."""
    pokes = {KEY_SEQUENCE_MATCHED: word(0),
             KEY_SEQUENCE_CURSOR: word(SEQUENCE_LENGTH - 1),   # the $ff
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_HELP])}
    what = "the sequence's terminator, with Help held"
    info = leaf.run("game_key_actions", _key_actions, [(KEY_SEQUENCE_MATCHED, WORD)], what,
                    regs={"_pokes": pokes})
    assert info["ret"] == RETURNED
    assert leaf.read_int(info, KEY_SEQUENCE_MATCHED, WORD, what) == KEY_SEQUENCE_MATCHED_SET
    assert EFFECT_STATE_BD6A_LOW not in info["writes"], (
        f"{what}: the Help action ran on the frame the sequence completed")


def test_a_wrapped_cursor_indexes_BELOW_the_sequence_and_raises_the_cheat_by_itself():
    """`move.b (a0,d0.w),d1` SIGN-EXTENDS the cursor, so a wrapped one reads below the table.

    A DECLARED FABRICATION, and the first draft of this docstring got it wrong: it claimed the state
    was reachable because nothing resets the cursor and `addq.w` wraps. It is not. The walk steps the
    cursor only while the byte at it MATCHES, and the byte at index 4 is the $ff terminator, which
    raises WB_KEY_SEQUENCE_MATCHED and returns WITHOUT stepping — after which a raised cheat word
    short-circuits the walk for ever. So the cursor's reachable range is 0..4 and no path takes it
    past that.

    The seed is kept anyway, in the canon's declared-fabricated form: what it pins is the operand's
    SIGN, which no reachable cursor can exercise (0..4 are all positive), and a port that read the
    index unsigned would address $10607 instead of $607 and see a different byte. The oracle agrees
    with the reconstruction on the fabricated input, which is what makes it a comparison rather than
    an invention — but it is a statement about the INSTRUCTION and not about a state the game
    reaches.
    """
    cursor = 0xffff
    what = f"a cursor of {cursor:#06x}, which indexes the cursor's own low byte"
    pokes = {KEY_SEQUENCE_MATCHED: word(0), KEY_SEQUENCE_CURSOR: word(cursor),
             KEY_LAST_SCANCODE: bytes([0])}
    info = leaf.run("game_key_actions", _key_actions, [(KEY_SEQUENCE_MATCHED, WORD)], what,
                    regs={"_pokes": pokes})
    assert info["ret"] == RETURNED
    assert leaf.read_int(info, KEY_SEQUENCE_MATCHED, WORD, what) == KEY_SEQUENCE_MATCHED_SET, (
        f"{what}: the byte at $607 is the terminator, so the walk should have raised the cheat")
    assert KEY_SEQUENCE_CURSOR not in info["writes"], f"{what}: the terminator arm does not step"


def test_a_cursor_that_indexes_OUTSIDE_the_image_reads_the_zero_both_cores_answer():
    """The far end of the same sign-extension, and FABRICATED for the same reason as above: no
    reachable cursor exceeds 4.

    $8000 indexes $ff8608 on the 24-bit bus, outside the 1 MiB image. The shim answers an unmapped
    read 0 and `bus_read_byte` answers 0 for the same address, so the two agree — and 0 is neither
    the terminator nor (here) the held key, so the walk does nothing at all. What this pins is that
    both sides fold the address the same way, which is a property of the two BUSES rather than of
    the game.
    """
    what = "a cursor of 0x8000, whose index leaves the image"
    pokes = {KEY_SEQUENCE_MATCHED: word(0), KEY_SEQUENCE_CURSOR: word(0x8000),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_N])}
    info = leaf.run("game_key_actions", _key_actions, [], what, regs={"_pokes": pokes})
    assert info["ret"] == RETURNED
    assert not leaf.program_writes(info), f"{what}: it wrote {sorted(info['writes'])}"


# --- game_key_actions: the cheat's Help action ----------------------------------------------------
@pytest.mark.parametrize("nth", WAIT_ITERATIONS)
@pytest.mark.parametrize("state", (0x00, 0x08, 0xff),
                         ids=lambda v: f"state_{v:02x}")
def test_help_flips_bit_three_once_the_key_is_released(nth, state):
    """`bchg` is a FLIP, not a set: a state that already carries the bit comes back without it, which
    is what the three seeds separate. The wait is the battery's second one, on the same byte and a
    different code."""
    pokes = {KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_HELP]),
             EFFECT_STATE_BD6A_LOW: bytes([state])}
    what = f"Help over a state of {state:#04x}, released before arrival {nth}"
    info = leaf.run("game_key_actions", _key_actions, [(EFFECT_STATE_BD6A_LOW, BYTE)], what,
                    regs={"_pokes": pokes}, max_insns=wait_cap(nth),
                    schedule=release(HELP_WAIT_PC, KEY_SCANCODE_HELP_RELEASE, nth))
    assert info["ret"] == RETURNED
    assert info["writes"][EFFECT_STATE_BD6A_LOW] == state ^ (1 << EFFECT_STATE_BD6A_CHEAT_BIT), what
    assert info["regs"]["sched_arrivals"] == nth


def test_help_does_nothing_without_the_cheat():
    """The guard: the same key, the cheat off. The walk runs instead (Help is not its next byte, so
    it writes nothing) and the Help block's own test then refuses."""
    pokes = {KEY_SEQUENCE_MATCHED: word(0), KEY_SEQUENCE_CURSOR: word(0),
             KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_HELP])}
    info = leaf.run("game_key_actions", _key_actions, [], "Help with the cheat OFF",
                    regs={"_pokes": pokes})
    assert info["ret"] == RETURNED


@pytest.mark.parametrize("cursor,scancode,why", (
    (2, KEY_SCANCODE_HELP_RELEASE, "a key neither test wants"),
    # THE ONE THAT SEPARATES THE SHORT-CIRCUIT, and it is the case the first mutation sweep found
    # missing: the key held is the very byte at the cursor, so a port that ran the walk anyway would
    # STEP it. With the key merely unhandled (above) the walk writes nothing either way and the
    # missing `tst.w` is invisible.
    (0, 0x61, "the key the walk is waiting for — and the walk must NOT run"),
    (3, 0x1e, "...the same, mid-sequence"),
))
def test_the_cheat_being_ON_short_circuits_the_walk(cursor, scancode, why):
    """`tst.w $604.l / bne.w $5d0` at $59e: once the cheat is enabled the sequence is never walked
    again, so the cursor stops wherever it stopped."""
    pokes = {KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET),
             KEY_SEQUENCE_CURSOR: word(cursor),
             KEY_LAST_SCANCODE: bytes([scancode])}
    info = leaf.run("game_key_actions", _key_actions, [], why, regs={"_pokes": pokes})
    assert info["ret"] == RETURNED
    assert KEY_SEQUENCE_CURSOR not in info["writes"], (
        f"{why}: the walk ran although the cheat is already enabled")


def test_two_entries_on_this_routines_two_waits_are_counted_at_their_own_sites():
    """`game_key_actions` has two waits, on the SAME byte, at $5e6 and $60e — and that pair is what
    made a per-ADDRESS counter the wrong remedy: the address says nothing about which wait polled.

    A differential used to refuse this schedule outright, because `nth` counted arrivals AT A PC on
    the oracle and POLLS over the whole run on the candidate, so two waits could not be told apart.
    Batch 42 phase C keys both counters by the wait SITE, and the two entries below are ordinary.
    What the case asserts is the encoder's arithmetic rather than a run: no ONE run of this routine
    reaches both arms (the pause arm at $574 returns, and the Help block below it is only reached
    when the pause test fails), so the pair is declarable and only one of the two ever fires.
    """
    schedule = [{"pc": HELP_WAIT_PC, "nth": 1, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                 "value": KEY_SCANCODE_HELP_RELEASE},
                {"pc": PAUSE_WAIT_PC, "nth": 1, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                 "value": KEY_SCANCODE_P_RELEASE}]
    assert emu.wait_site_pcs(schedule, None) == (HELP_WAIT_PC, PAUSE_WAIT_PC), (
        "the two triggers are two sites, in the order the schedule names them")
    assert emu.wait_site_pcs(schedule, [PAUSE_WAIT_PC, HELP_WAIT_PC]) \
        == (PAUSE_WAIT_PC, HELP_WAIT_PC), "...and a case may declare them in its own order"


def test_a_wait_site_declared_twice_is_refused():
    """Two counters keyed the same way cannot be compared, and the second would silently shadow the
    first: every poll naming that PC would land in slot 0 and slot 1 would read 0 against the
    oracle's own 0. `os_sched_site_index` returns the FIRST match on both shores, so the duplicate
    is not a divergence — it is a counter nobody can read, which is why it is refused at the encoder.
    """
    with pytest.raises(ValueError, match="names the same PC twice"):
        emu.wait_site_pcs(None, [PAUSE_WAIT_PC, PAUSE_WAIT_PC])


@pytest.mark.parametrize("pc,why", (
    (PAUSE_WAIT_PC + 1, "odd — a 68000 fetches no instruction there"),
    (-2, "negative, which ctypes would carry across as 0xfffffffe"),
    (harness.IMAGE_SIZE, "past the top of the image"),
))
def test_a_schedule_whose_trigger_could_never_be_a_pc_is_refused_at_the_encoder(pc, why):
    """Without this the entry reaches the oracle, no arrival ever matches, and the run dies at the
    instruction cap with a message about the wait loop — pointing at the routine rather than at the
    typo. Refused where the value is, which is what the encoder's docstring promises for every other
    field."""
    with pytest.raises(ValueError, match="even address inside"):
        emu.schedule_entries([{"pc": pc, "nth": 1, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                               "value": KEY_SCANCODE_P_RELEASE}])


def test_a_poisoned_attribution_pass_over_a_scheduled_byte_is_refused():
    """The pass poisons every oracle-written byte; the agent's store lands on both sides from the
    same list and overwrites the canary, so a candidate that never made the function's own store
    would match anyway. Both of this battery's wait cases pass `poison=False` for that reason — this
    is what stops the next one doing it by accident."""
    pokes = {GAME_PAUSED: word(GAME_PAUSED_SET), KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P]),
             TEXT_REQUEST: bytes([PAUSE_MESSAGE_ID])}
    with pytest.raises(AssertionError, match="attribution pass would poison"):
        harness.differential(UNPAUSE_ENTRY, {"_pokes": pokes}, _unpause, poison=True,
                             max_insns=wait_cap(2),
                             schedule=release(UNPAUSE_WAIT_PC, KEY_SCANCODE_P_RELEASE, 2))


def test_a_differential_refuses_an_instruction_index_trigger():
    """The kit's `insn` trigger has no candidate equivalent — this side counts POLLS — so a
    differential that carried one would make the store on the ORACLE alone and spin the candidate
    for ever. `harness._vet_schedule_is_runnable` refuses it before either core runs, and without a
    case the refusal is code no run reaches: the whole suite declares `pc` triggers.
    """
    schedule = [{"insn": 5, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                 "value": KEY_SCANCODE_P_RELEASE}]
    pokes = {GAME_PAUSED: word(GAME_PAUSED_SET), KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P])}
    with pytest.raises(AssertionError, match="`insn` trigger"):
        harness.differential(UNPAUSE_ENTRY, {"_pokes": pokes}, _unpause, schedule=schedule)


# ==================================================================================================
# THE SPINE'S INVENTORY, walked from the bytes
# ==================================================================================================
#
# ../STATUS.md's batch 42 phase A publishes what the frame loop reaches and what of it is ported. A
# table in a document is a claim about a SET, and this project's standing lesson is that such a claim
# is enumerated or it is guesswork — so it is enumerated HERE, out of the LOADED image, and the
# document's numbers are pinned against these cases.
#
# THE WALK'S RULES, which are the image's own idiom rather than a convention:
#   * `bsr`/`jsr` to an absolute address is a CALL — a new routine, followed transitively.
#   * `bra`/`Bcc`/`dbcc` stay inside the body.
#   * `jmp` to an absolute address LEAVES the body: recorded as an edge, never followed. THREE of the
#     four in this closure are `game_key_actions`' stack-unwinding endings into the boot chain; the
#     fourth is `$deb0`'s `jmp $1ab4.w`, which is not an unwind at all — it is
#     `scene_spend_visit_budget` tail-jumping into `scene_spawn_speech_tail`, a routine this port
#     HAS (scene.h records the one-level unwind it leaves behind).
#   * a register transfer (`jmp (an)`, `jsr d16(an)`) is opaque to a byte walk: not followed. There
#     are TWELVE, not the three a first reading of the diff suggested, and the tuple below names
#     every one — which is what makes the walk a tripwire rather than a measurement taken once.
import prg_dis     # noqa: E402  (test/harness.py puts reverse/tools on sys.path)

SPINE_ROOTS = ("game_main_loop", "vbl_handler", "flip_screen")

# `prg_dis.decode` reads a .PRG's FILE bytes and maps a file offset to a runtime address by
# subtracting the header. The harness holds the LOADED image instead, so this is that image's text
# behind a header-sized pad — the one shape the decoder's own address arithmetic gets right, and it
# is the RELOCATED bytes rather than the file's, which is what a run executes.
PRG_HEADER_BYTES = 28
_TEXT = bytes(PRG_HEADER_BYTES) + bytes(harness.BASE_IMAGE[loader.LOAD_BASE:loader.PROGRAM_END])

_ABS_CALL = re.compile(r"^(?:bsr|jsr)\S*\s+\$([0-9a-f]+)(?:\.[wl])?$")
_BRANCH = re.compile(r"^(?:bra|b(?:hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le))\S*\s+\$([0-9a-f]+)$")
_DBCC = re.compile(r"^db\S+\s+d\d,\$([0-9a-f]+)$")
_ABS_JMP = re.compile(r"^jmp\S*\s+\$([0-9a-f]+)(?:\.[wl])?$")
_RETURNS = ("rts", "rte", "rtr")


def _decode(addr):
    """One instruction at a RUNTIME address, through the workspace's own decoder."""
    return prg_dis.decode(_TEXT, addr - loader.LOAD_BASE + PRG_HEADER_BYTES, loader.LOAD_BASE)


def _walk_body(entry, opaque=None, tails=None):
    """(the instruction addresses the routine at ``entry`` reaches, its absolute call targets).

    ``opaque`` and ``tails`` are optional accumulators: every transfer the walk cannot follow lands
    in one of them, which is what lets a case assert the SET rather than trust that the regexes
    matched everything they should have.
    """
    seen, calls, work = set(), set(), [entry]
    while work:
        at = work.pop()
        if at in seen or not (loader.LOAD_BASE <= at < loader.PROGRAM_END):
            continue
        seen.add(at)
        length, text = _decode(at)
        instruction = text.split(";")[0].strip()
        call = _ABS_CALL.match(instruction)
        branch = _BRANCH.match(instruction) or _DBCC.match(instruction)
        if call:
            calls.add(int(call.group(1), 16))
            work.append(at + length)
        elif branch:
            work.append(int(branch.group(1), 16))
            if not instruction.startswith("bra"):
                work.append(at + length)          # a conditional branch keeps the fallthrough
        elif _ABS_JMP.match(instruction):
            if tails is not None:
                tails.add((at, int(_ABS_JMP.match(instruction).group(1), 16)))
        elif instruction.startswith(("jmp", "jsr", "bsr")):
            # A transfer the regexes above did not match: a register indirect today, and equally a
            # pc-relative spelling tomorrow. Collected, never followed — and never DROPPED.
            if opaque is not None:
                opaque.add((at, instruction))
            # An opaque CALL still RETURNS, so the body continues past it; an opaque `jmp` does not.
            if not instruction.startswith("jmp"):
                work.append(at + length)
        elif instruction.split()[0] not in _RETURNS:
            work.append(at + length)
    return seen, calls


def _extent(entry):
    """First instruction to past the last one — the routine's bytes as the table counts them."""
    body, _calls = _walk_body(entry)
    last = max(body)
    return last + _decode(last)[0] - min(body)


# THE INVENTORY'S UNPORTED ROWS: `(address, name or None, bytes)`. Stated, and checked by the walk —
# a table that derived its own contents would agree with any walk, a broken one included.
# EMPTY, as of batch 42 phase C: THE SPINE IS WHOLE. The tuple stays, and so does every case over
# it — the ledger is a TRIPWIRE, not a progress bar. A routine the walk starts reaching that this
# port does not define lands here and fails
# `test_the_spine_reaches_exactly_the_routines_the_status_table_accounts_for` on the next run.
SPINE_UNPORTED = ()
SPINE_UNPORTED_BYTES = 0
SPINE_ROUTINES = 86                     # what the three roots reach, ported and not

# ...AND THE ROWS THE INVENTORY HAS SINCE LOST, which is the other half of the same ledger. The
# eleven rows batch 42 phase A enumerated came to SPINE_INVENTORY_BYTES; the two lists below must
# still account for exactly that, so a routine that left the unported table has to arrive HERE
# rather than merely vanish. Without it the phase's own arithmetic would be a sentence in a
# document, which is the thing this file exists to stop.
SPINE_PORTED_FROM_THE_INVENTORY = (
    (0x50a, "game_snap_follow_cursor", 52),             # phase B
    (0x53e, "game_key_actions", 240),                   # phase A — CODE, not its 250-byte SPAN
    (0x638, "game_unpause_on_key_release", 54),         # phase A
    (0x716, "vbl_handler", 52),                         # phase B
    (0x882, "game_latch_input_and_step_actors", 10),    # phase B
    (0x624c, "psg_set_drive_select", 28),               # phase B
    (0x6268, "floppy_deselect_drives", 16),             # phase B
    (0xe032, "round_bonus_run_frame", 118),             # phase B
    (0xe0a8, "round_bonus_setup", 104),                 # phase B
    (0x694, "flip_screen", 118),                        # phase C
    (0x4a0, "game_main_loop", 106),                     # phase C — THE LAST ROW
)
SPINE_INVENTORY_BYTES = 898             # the eleven rows as phase A enumerated them

# EVERY TRANSFER THE WALK CANNOT FOLLOW, enumerated from the bytes and pinned as a set.
#
# This is the walk's tripwire and the reason the inventory can be trusted between batches. The
# regexes above match the absolute forms; anything else — a register indirect, and equally a
# pc-relative `jsr` spelling nothing in this closure uses TODAY — falls through to the opaque arm and
# is DROPPED. Dropped silently, if nobody counts them: the routine behind it would simply not appear
# in the table, and the byte total would agree with itself. So the walk collects them and this says
# what the set is.
#
# Each is covered by a battery of its own, which is why not following them costs nothing here:
OPAQUE_TRANSFERS = (
    (0x594, "jsr 84(a0)"),      # game_key_actions -> snd_stub_00 +84 (snd_start_fadeout)
    (0x726, "jsr 14(a0)"),      # vbl_handler -> stub +14 (snd_music_tick), test_sound.py
    (0x936, "jmp (a1)"),        # actor_dispatch_behavior's 62-row table, test_behavior.py
    (0x8350, "jmp (a2)"),       # bg_scroll_blit's two variant tails, test_scroll.py
    (0x8364, "jmp (a2)"),
    (0x8fbc, "jsr (a2)"),       # sprite_draw_pass -> the twelve blitters, test_blit.py
    (0xbca2, "jsr 56(a1)"),     # panel_frame_timers -> stub +56, test_hud.py
    (0xddfe, "jsr (a0)"),       # scene_run_frame's three dispatches, test_scene.py
    (0xde74, "jsr (a0)"),
    (0xdfd6, "jsr (a6)"),
    (0xfa1e, "jsr (a1)"),       # stage_load_window's two, test_stage.py
    (0xfa28, "jsr 28(a1)"),
)
# ...and the absolute `jmp`s, which the walk records as edges and does not follow. Three are
# game_key_actions' unwinds; the fourth is not an unwind (see the header comment).
ABSOLUTE_TAILS = ((0x550, 0xe5ba), (0x56e, 0xe5ba), (0x598, 0xe494), (0xdeb0, 0x1ab4))


def _reachable():
    """``({entry: call targets}, the opaque transfers, the absolute tails)`` for the whole closure."""
    reached, opaque, tails = {}, set(), set()
    queue = [leaf.entry_of(name) for name in SPINE_ROOTS]
    while queue:
        entry = queue.pop(0)
        if entry in reached:
            continue
        _body, calls = _walk_body(entry, opaque, tails)
        reached[entry] = calls
        queue += sorted(calls)
    return reached, opaque, tails


def test_the_ported_set_counts_only_symbols_the_candidate_itself_DEFINES():
    """The guard under the inventory above, and it is not hypothetical.

    A `ctypes.CDLL` handle resolves through the whole process's symbol namespace, so a membership
    test written as `hasattr(_lib, name)` answers TRUE for `rand` and `printf`. Nothing in
    ../names.txt collides with libc today; the day one does, an unported routine would count as
    ported and the spine's table would shrink with no case failing. `leaf.ported_entries` reads the
    library's own defined symbols instead, and this is what says so.
    """
    defined = leaf._defined_symbols()
    assert "printf" not in defined and "rand" not in defined, (
        "the candidate's symbol set has picked up libc — ported_entries would over-count")
    assert "game_key_actions" in defined, "...and it still holds the reconstruction's own"
    assert hasattr(harness._lib, "rand"), (
        "the hazard this guards is that a ctypes handle DOES resolve libc; if this ever stops being "
        "true the case above has stopped testing anything")


def test_the_spine_reaches_exactly_the_routines_the_status_table_accounts_for():
    """The SET, enumerated from the image rather than from a reading of the disassembly.

    A routine the loop calls that no row names is what a hand-written table loses, and it is the whole
    reason ../STATUS.md's count can be trusted. The ported side is not listed here — 75 rows would be
    a second copy of the src/ tree — so what this asserts is the count and the unported remainder.
    """
    reached, _opaque, _tails = _reachable()
    assert len(reached) == SPINE_ROUTINES, (
        f"the frame loop reaches {len(reached)} routines, not the {SPINE_ROUTINES} the table counts")
    unported = set(reached) - set(leaf.ported_entries())
    assert unported == {row[0] for row in SPINE_UNPORTED}, (
        f"the spine's unported set is {sorted(hex(a) for a in unported)}, not the table's rows")


def test_every_transfer_the_walk_cannot_follow_is_one_the_table_accounts_for():
    """THE WALK'S TRIPWIRE, and the reason the inventory holds between batches.

    A routine reached only through a transfer the regexes do not match never appears in the table,
    and the byte total agrees with itself — the walk would be wrong and silent. So every unfollowed
    transfer is collected and the SET is pinned. It catches three things at once: a new register
    dispatch in code the loop reaches, a spelling the walk does not decode (a pc-relative `jsr`, of
    which this closure has none TODAY), and an absolute tail into a routine nobody has read.
    """
    _reached, opaque, tails = _reachable()
    assert tuple(sorted(opaque)) == OPAQUE_TRANSFERS, (
        f"the closure's register transfers are {sorted((hex(a), t) for a, t in opaque)}")
    assert tuple(sorted(tails)) == ABSOLUTE_TAILS, (
        f"the closure's absolute tails are {sorted((hex(a), hex(t)) for a, t in tails)}")


def test_every_unported_row_is_the_number_of_bytes_the_status_table_states():
    for entry, name, size in SPINE_UNPORTED:
        measured = _extent(entry)
        assert measured == size, f"{name or hex(entry)} is {measured} bytes, not the table's {size}"
    assert sum(row[2] for row in SPINE_UNPORTED) == SPINE_UNPORTED_BYTES


# `game_key_actions`' row is its CODE and not its SPAN, and it is the one row of the eleven where
# the two differ: $53e..$637 is 250 bytes, ten of which are the DATA between its two halves (the
# cheat enable at $604, the cursor at $606, the five sequence scancodes and one byte of padding).
# `_extent` measures the span, so this row alone is measured from its two code runs.
_KEY_ACTIONS_ROW = 0x53e


def _inventory_row_bytes(entry):
    if entry != _KEY_ACTIONS_ROW:
        return _extent(entry)
    return (SEQUENCE_DATA_START - KEY_ACTIONS_ENTRY) + (UNPAUSE_ENTRY - PAUSE_ARM_ENTRY)


def test_every_ported_row_still_measures_what_the_inventory_credited_it_with():
    """The ledger's other side, and the reason the running total below can be trusted.

    A row that leaves SPINE_UNPORTED has to arrive in SPINE_PORTED_FROM_THE_INVENTORY carrying the
    SAME byte count the inventory gave it, measured from the image the same way. A phase that
    credited itself with a routine's span where the table counted its code — the one row where
    those differ — would otherwise balance its own arithmetic against a number it had just moved.
    """
    for entry, name, size in SPINE_PORTED_FROM_THE_INVENTORY:
        measured = _inventory_row_bytes(entry)
        assert measured == size, f"{name} is {measured} bytes, not the {size} it was credited with"
        assert leaf.entry_of(name) == entry, f"{name} is not the routine at {entry:#x}"


def test_the_ported_rows_and_the_unported_ones_still_add_up_to_the_whole_inventory():
    """THE RUNNING LEDGER, AND IT NOW READS ZERO: 898 bytes of unported spine when phase A
    enumerated it, and every byte since accounted for as taken. Phase A took 294 (`game_key_actions`'
    240 of code and `game_unpause_on_key_release`' 54), leaving 604; phase B took 380 more, leaving
    224; phase C took the last two rows, `flip_screen`'s 118 and `game_main_loop`'s 106.
    """
    taken = sum(row[2] for row in SPINE_PORTED_FROM_THE_INVENTORY)
    assert taken + SPINE_UNPORTED_BYTES == SPINE_INVENTORY_BYTES
    # ...and the SPLIT, not only the sum: without it a phase could delete a row and decrement the
    # historical SPINE_INVENTORY_BYTES to match, and the sum above would still balance.
    assert taken == SPINE_INVENTORY_BYTES, (
        "the spine's whole inventory is ported, so the taken half IS the whole 898 — a row that "
        "left the table would balance this by shrinking both sides, which is what the disjointness "
        "and per-row re-measurement above are for")


def test_no_row_is_in_both_halves_of_the_ledger():
    """The guard that makes the sum above mean anything: a routine counted as ported AND as
    outstanding would balance the arithmetic twice over while the spine had not moved at all."""
    unported = {row[0] for row in SPINE_UNPORTED}
    ported = {row[0] for row in SPINE_PORTED_FROM_THE_INVENTORY}
    assert not unported & ported, f"{sorted(hex(a) for a in unported & ported)} is in both lists"
    assert ported <= set(leaf.ported_entries()), (
        "a row the ledger calls ported has no symbol of that name in the candidate")
    # ...AND EVERY PORTED ROW IS STILL SOMETHING THE SPINE REACHES, which the unported half gets for
    # free from `test_the_spine_reaches_exactly_the_routines_the_status_table_accounts_for` and this
    # half would otherwise lose. Without it a decoder regression that dropped a row from the walk's
    # closure would leave every other assertion here balancing: the count still matches, the
    # remainder still matches, and the sizes come from `_extent` rather than from the closure.
    reached, _opaque, _tails = _reachable()
    assert ported <= set(reached), (
        f"{sorted(hex(a) for a in ported - set(reached))} is credited to the spine's inventory but "
        f"the walk no longer reaches it")


# ==================================================================================================
# BATCH 42 PHASE B: the rest of the spine, less the frame loop and the flip
# ==================================================================================================
#
# Seven routines, ported callee-clean — every one of them calls only code this port already has, so
# a case enters at the routine's own address and leaves at its own `rts`. The two that did NOT were
# `game_main_loop` and `flip_screen`, and what stopped the second was not that the model refused it
# but that it ACCEPTED it: `flip_screen` waits twice on WB_VBL_COUNTER, the natural one-trigger
# schedule passed `harness.py`'s vetting, and the candidate's run-total poll count and the oracle's
# arrival count then cancelled to agree while the two sides ran different iteration counts — the
# mutant that deletes the first wait survived it.
#
# BATCH 42 PHASE C CLOSED BOTH, and the shape it took is NOT the one this comment used to prescribe:
# the counters are now kept per WAIT SITE on both shores, which makes two waits in one run separable,
# so the $6ca split that was required under run totals is discharged rather than performed. The
# width needed no new capability either — `sched_poll16` is one `sched_poll8` plus a full-width read,
# and what it adds is the cap. ../names.txt's `cmt 0x694` and ../STATUS.md's batch 42 phase C carry
# the measurement, and this file's own flip_screen and game_main_loop sections are below.
#
# WHAT THIS SECTION IMPORTS RATHER THAN RESTATES. `game_latch_input_and_step_actors` runs the whole
# behaviour pass and `vbl_handler` runs the whole music tick — both already have batteries that
# model them byte for byte, and a second model here could disagree with the first while both stayed
# green. So the walk's pokes come from test_behavior.py and the tick's model from test_sound.py, and
# what these cases add is the arithmetic of the SPINE routine on top.
from test_behavior import (ACTOR_X, ACTOR_Y, JOY1_RIGHT_BIT,               # noqa: E402
                           SCENE_ACK_WAIT, SCENE_MESSAGE_PENDING, SHOP_RECORD_AT,
                           SHOP_RECORD_PTR, SHOP_REQUEST, TABLE_DEFAULT, TYPE34_ITEM1_X,
                           TYPE34_MIDDLE_X, TYPE34_MIDDLE_Y, WALK_INSN_PER_RECORD, _record,
                           _walk_pokes)
from test_sound import (PSG_REG_MIXER, TEMPO_MACHINES, TICK_MIXER,         # noqa: E402
                        WHOLE_TICK_INSN_CAP, _Memory, _Psg, _poked_image, _tick_pokes,
                        _tempo_hw_events, _whole_tick_model, assert_written, write_bands)
from test_stage import (BCD_ADDEND, BCD_SCORE, BCD_SCORE_LEN,              # noqa: E402
                        HUD_METER_MAX, HUD_METER_VALUE, LOAD_WINDOW_INSN_CAP, ROUND_INSN_CAP)

JOY1_STATE = wb("JOY1_STATE")
JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")

SCROLL_FOLLOW_X = wb("SCROLL_FOLLOW_X")
SCROLL_FOLLOW_Y = wb("SCROLL_FOLLOW_Y")
SCROLL_FOLLOW_EVEN_MASK = wb("SCROLL_FOLLOW_EVEN_MASK")
SCROLL_FOLLOW_SNAP_UP = wb("SCROLL_FOLLOW_SNAP_UP")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
ACTOR_FLAG_SIDE_BIT = wb("ACTOR_FLAG_SIDE_BIT")
ACTOR_FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
ACTOR_FOLLOWED_A32 = wb("ACTOR_FOLLOWED_A32")
ACTOR_TABLE_A30 = wb("ACTOR_TABLE_A30")
STATE_FLAG_A30 = wb("STATE_FLAG_A30")
STATE_FLAG_A32 = wb("STATE_FLAG_A32")
STATE_FLAG_SET = wb("STATE_FLAG_SET")

PSG_REG_PORT_A = wb("PSG_REG_PORT_A")
PSG_PORT_A_KEEP = wb("PSG_PORT_A_KEEP")
PSG_DRIVES_DESELECTED = wb("PSG_DRIVES_DESELECTED")

FLOPPY_IDLE_TIMER = wb("FLOPPY_IDLE_TIMER")

EVENT_FINISHED_E1BE = wb("EVENT_FINISHED_E1BE")
ROUND_BONUS_ACTIVE = wb("ROUND_BONUS_ACTIVE")
ROUND_BONUS_ACTIVE_SET = wb("ROUND_BONUS_ACTIVE_SET")
ROUND_BONUS_METER_TARGET = wb("ROUND_BONUS_METER_TARGET")
ROUND_BONUS_REFILLING = wb("ROUND_BONUS_REFILLING")
ROUND_BONUS_REFILLING_SET = wb("ROUND_BONUS_REFILLING_SET")
ROUND_BONUS_SCORE = wb("ROUND_BONUS_SCORE")
ROUND_BONUS_METER_BUMP = wb("ROUND_BONUS_METER_BUMP")
ROUND_BONUS_MAP_BANK = wb("ROUND_BONUS_MAP_BANK")
ROUND_BONUS_START_RECORD = wb("ROUND_BONUS_START_RECORD")
ROUND_END_RELOAD_REQUEST_SET = wb("ROUND_END_RELOAD_REQUEST_SET")
SCENE_MAP_BANK_TABLE = wb("SCENE_MAP_BANK_TABLE")
SCENE_MAP_BANK_BYTES = wb("SCENE_MAP_BANK_BYTES")
STAGE_MAP_PTR = wb("STAGE_MAP_PTR")
STAGE_START_PTR = wb("STAGE_START_PTR")

WORD_MASK = leaf.WORD_MASK
program_writes = leaf.program_writes
merge_bands = leaf.merge_bands
keyed_block = leaf.keyed_block
PSG_EVENT_READ = harness.OS_PSG_EVENT_READ
PSG_EVENT_WRITE = harness.OS_PSG_EVENT_WRITE


# --- $882: joy1_latch_edge then actor_behavior_pass ----------------------------------------------

_LATCH_AND_STEP = leaf.image_glue("game_latch_input_and_step_actors")
LATCH_AND_STEP_ENTRY = leaf.entry_of("game_latch_input_and_step_actors")


def _latch_and_step_pokes(salt, types, joystick):
    """The behaviour walk's own pokes, plus the three bytes of the joystick pipeline.

    `_walk_pokes` is test_behavior.py's and is imported rather than rebuilt: it seeds the table, the
    published table pointer and WB_STATE_FLAG_A34, and a second copy of that here could describe a
    different table while both batteries passed.
    """
    pokes = dict(_walk_pokes(salt, types))
    pokes.update({JOY1_STATE: bytes([joystick[0]]), JOY1_CURRENT: bytes([joystick[1]]),
                  JOY1_PREV: bytes([joystick[2]])})
    return pokes


def test_the_body_is_the_two_calls_and_nothing_else():
    """THE ORDER IS PINNED FROM THE BYTES, and it has to be: over a table of null handlers the two
    calls COMMUTE — the pass reads the joystick edge only through a behaviour that consumes it, and
    no slot the walk cases use does. So a port that latched AFTER the pass would leave the identical
    image on every case below, and what separates the two readings is the original's own encoding.
    """
    body = bytes(harness.BASE_IMAGE[LATCH_AND_STEP_ENTRY:][:10])
    assert body == (bsr_w(LATCH_AND_STEP_ENTRY, leaf.entry_of("joy1_latch_edge"))
                    + bsr_w(LATCH_AND_STEP_ENTRY + 4, leaf.entry_of("actor_behavior_pass"))
                    + RTS), (
        "$882 is not `bsr joy1_latch_edge / bsr actor_behavior_pass / rts`")


@pytest.mark.parametrize("case,types", [("empty", []), ("one-live", [0]), ("one-free", [None]),
                                        ("alternating", [0, None, 0])])
def test_the_frame_latches_the_stick_and_then_walks_the_actors(case, types):
    """Both halves in one run: the joystick byte comes down the pipeline a stage and the pass walks
    the table to its terminator. The pass itself writes nothing (test_behavior.py's own cases say
    so and the write set here is what re-states it), so every byte written is the latch's."""
    what = f"game_latch_input_and_step_actors {case}"
    salt = leaf.case_salt(what)
    # THE THREE STAGES MUST DIFFER, or the shift is invisible: a latch that copied the wrong stage,
    # or copied nothing, would leave the same byte where the right one was going. Keyed on the
    # ADDRESS so each is wrong for its neighbour's slot, and forced distinct.
    joystick = tuple((leaf.keyed_byte(addr, salt) & 0x0f) | (index + 1) << 4
                     for index, addr in enumerate((JOY1_STATE, JOY1_CURRENT, JOY1_PREV)))
    pokes = _latch_and_step_pokes(salt, types, joystick)

    info = leaf.run("game_latch_input_and_step_actors", _LATCH_AND_STEP,
                    [(JOY1_PREV, 1), (JOY1_CURRENT, 1)], what, regs={"_pokes": pokes},
                    max_insns=WALK_INSN_PER_RECORD * (len(types) + 1) + leaf.LEAF_INSN_CAP)

    assert program_writes(info) == {JOY1_PREV: joystick[1], JOY1_CURRENT: joystick[0]}, (
        f"{what}: the pipeline did not shift exactly one stage")
    assert info["regs"]["a0"] == _record(TABLE_DEFAULT, len(types)), (
        f"{what}: the walk stopped at {info['regs']['a0']:#x}, not on the terminator")


# THE CASE THAT MAKES BOTH CALLS OBSERVABLE, and it took a behaviour that does something.
#
# The rows above dispatch NULL handlers, which write nothing — so a port that dropped the pass
# outright left the identical image and the sweep said so. Slot 34, the shop's item cursor, is the
# one cheap handler that both WRITES (it plants its new x and y as one longword) and READS THE
# JOYSTICK EDGE (`bsr $682`, then `btst` on bits 2, 3 and 7). That makes it the case for the pass
# AND for the ORDER: the edge is `current & ~prev`, so with the stick newly pushed RIGHT —
#
#   latched first:  prev := current ($00), current := state (RIGHT)  ->  edge = RIGHT, cursor moves
#   passed first:   edge = current ($00) & ~prev ($00) = nothing     ->  cursor stands still
#
# — the two orders leave different memory, and a port with either defect reds here.
CURSOR_WALK_INSN_CAP = 4096


def _cursor_walk_pokes(salt, joystick_state, current=0, prev=0):
    """A one-record table holding the shop cursor at the LEFT item, both scene gates down, and the
    joystick pipeline seeded stage by stage so the EDGE depends on which call ran first."""
    record = _record(TABLE_DEFAULT, 0)
    return _walk_pokes(salt, [34], {
        record + ACTOR_X: leaf.word(TYPE34_ITEM1_X), record + ACTOR_Y: leaf.word(0),
        SCENE_MESSAGE_PENDING: leaf.word(0), SCENE_ACK_WAIT: leaf.word(0),
        SHOP_RECORD_PTR: leaf.longword(SHOP_RECORD_AT), SHOP_REQUEST: leaf.word(0),
        TEXT_REQUEST: bytes([0]), TEXT_LIFETIME_REQUEST: leaf.word(0),
        JOY1_STATE: bytes([joystick_state]), JOY1_CURRENT: bytes([current]),
        JOY1_PREV: bytes([prev])})


def test_the_pass_spends_the_edge_the_latch_has_just_produced():
    """THE ORDER, measured rather than argued — and the pass's own existence with it.

    The stick is newly RIGHT this frame and the pipeline's two live stages are clear, so the edge
    exists only AFTER the latch has run. The cursor therefore walks from the left item to the middle
    and the handler plants ($78, $30) over the record's x and y as one `move.l`. A port that ran the
    pass first sees no edge and moves nothing; a port that dropped the pass moves nothing either.
    """
    what = "game_latch_input_and_step_actors the cursor spends the new edge"
    pushed = 1 << JOY1_RIGHT_BIT
    pokes = _cursor_walk_pokes(leaf.case_salt(what), joystick_state=pushed)

    info = leaf.run("game_latch_input_and_step_actors", _LATCH_AND_STEP,
                    [(JOY1_PREV, 1), (JOY1_CURRENT, 1), (_record(TABLE_DEFAULT, 0) + ACTOR_X,
                                                         leaf.LONGWORD_BYTES),
                     (TEXT_REQUEST, 1), (TEXT_LIFETIME_REQUEST, WORD), (SHOP_REQUEST, WORD)], what,
                    regs={"_pokes": pokes}, max_insns=CURSOR_WALK_INSN_CAP)

    record = _record(TABLE_DEFAULT, 0)
    assert leaf.read_int(info, record + ACTOR_X, WORD, what) == TYPE34_MIDDLE_X, (
        f"{what}: the cursor did not walk, so the pass never saw the edge the latch made")
    assert leaf.read_int(info, record + ACTOR_Y, WORD, what) == TYPE34_MIDDLE_Y
    assert program_writes(info)[JOY1_CURRENT] == pushed, "the latch did not run at all"


def test_the_same_frame_with_the_stick_already_held_moves_nothing():
    """The control beside it, and what makes the case above about the EDGE rather than the level:
    the same stick position, but held since last frame, produces no edge in EITHER order — so the
    cursor stands and the only writes are the latch's own two bytes."""
    what = "game_latch_input_and_step_actors the cursor ignores a held stick"
    pushed = 1 << JOY1_RIGHT_BIT
    pokes = _cursor_walk_pokes(leaf.case_salt(what), joystick_state=pushed, current=pushed,
                               prev=pushed)

    info = leaf.run("game_latch_input_and_step_actors", _LATCH_AND_STEP,
                    [(JOY1_PREV, 1), (JOY1_CURRENT, 1)], what,
                    regs={"_pokes": pokes}, max_insns=CURSOR_WALK_INSN_CAP)

    # The record's x/y longword is outside `allowed`: a held stick makes no edge, so the cursor
    # must not move, and a run that moved it reds as a stray write.


# --- $50a: the follow cursor, snapped to an even pixel -------------------------------------------
#
# THE ROUTINE HAS TWO INPUTS AND THEY ARE READ THROUGH DIFFERENT ROUTES. The pair itself is a
# LONGWORD at WB_SCROLL_FOLLOW_X; the side flag is a byte at offset 8 of whichever record
# `followed_actor_record` names, and WHICH record that is depends on WB_STATE_FLAG_A32. Both of that
# routine's arms are driven below, because the flag byte the `btst` reads lives at a different
# address in each and a port that hardcoded either would pass on the other.

_SNAP = leaf.image_glue("game_snap_follow_cursor")
SNAP_INSN_CAP = 64          # nine instructions here plus followed_actor_record's four


def _snap_expected(x, y, side):
    """The pair the original leaves, stated as the two half-words rather than as the mask.

    An INDEPENDENT statement of `andi.l #$fffefffe` and the conditional `addq.w #2`: y always loses
    its low bit, and x loses its low bit unless the side flag is set AND that bit was there, in
    which case it gains the step instead. Written as "round down / round up" because that is the
    reading, and a model spelt as the same mask the C uses would agree with a wrong C.
    """
    snapped_y = y & ~1 & WORD_MASK
    if side and x & 1:
        snapped_x = (x + 1) & WORD_MASK
    else:
        snapped_x = x & ~1 & WORD_MASK
    return snapped_x, snapped_y


def _run_snap(case, x, y, side, a32):
    what = f"game_snap_follow_cursor {case}"
    record = ACTOR_FOLLOWED_A32 if a32 else ACTOR_FOLLOWED_DEFAULT
    salt = leaf.case_salt(what)
    flags = leaf.keyed_byte(record + ACTOR_FLAGS, salt)
    flags = (flags | 1 << ACTOR_FLAG_SIDE_BIT) if side else (flags & ~(1 << ACTOR_FLAG_SIDE_BIT))

    # THE OTHER RECORD IS SEEDED WITH THE OPPOSITE FLAG, which is what makes the a32 arm testable:
    # with both records holding the same byte, a port that read the wrong one would agree.
    other = ACTOR_FOLLOWED_DEFAULT if a32 else ACTOR_FOLLOWED_A32
    pokes = {SCROLL_FOLLOW_X: leaf.word(x) + leaf.word(y),
             STATE_FLAG_A32: leaf.word(STATE_FLAG_SET if a32 else 0),
             record + ACTOR_FLAGS: bytes([flags & 0xff]),
             other + ACTOR_FLAGS: bytes([(flags ^ 1 << ACTOR_FLAG_SIDE_BIT) & 0xff])}

    info = leaf.run("game_snap_follow_cursor", _SNAP,
                    [(SCROLL_FOLLOW_X, leaf.LONGWORD_BYTES)], what,
                    regs={"_pokes": pokes}, max_insns=SNAP_INSN_CAP)

    expected_x, expected_y = _snap_expected(x, y, side)
    assert leaf.read_int(info, SCROLL_FOLLOW_X, WORD, what) == expected_x, (
        f"{what}: x is not {expected_x:#06x}")
    assert leaf.read_int(info, SCROLL_FOLLOW_Y, WORD, what) == expected_y, (
        f"{what}: y is not {expected_y:#06x}")
    return info


# THE ASYMMETRY IS THE ROUTINE and the sweep is where it is pinned: the `addq.w #2` sits between two
# `swap`s, so it reaches the HIGH half of the longword and nothing reaches the low one. The two
# both-odd rows with the flag set and clear are what say so — a port that applied the bias to y as
# well leaves y one step high on either of them. (An earlier draft repeated those two seeds in a
# case of their own, which could not fail unless the sweep row it duplicated failed first.)
SNAP_CASES = [
    # (case, x, y, side) — every combination of the two parities against the flag, plus a pair whose
    # halves would be confused by a port that snapped the WRONG one (odd x, even y and the reverse).
    ("both-odd-side-clear", 0x0121, 0x00b7, False),
    ("both-odd-side-set", 0x0121, 0x00b7, True),
    ("both-even-side-clear", 0x0120, 0x00b6, False),
    ("both-even-side-set", 0x0120, 0x00b6, True),
    ("odd-x-even-y-side-set", 0x0121, 0x00b6, True),
    ("even-x-odd-y-side-set", 0x0120, 0x00b7, True),
]


@pytest.mark.parametrize("case,x,y,side", SNAP_CASES, ids=[c[0] for c in SNAP_CASES])
@pytest.mark.parametrize("a32", [False, True], ids=["default-record", "a32-record"])
def test_the_pair_is_snapped_even_and_only_x_can_round_up(case, x, y, side, a32):
    _run_snap(f"{case} {'a32' if a32 else 'default'}", x, y, side, a32)


def test_an_x_at_the_words_top_wraps_rather_than_carrying_into_y():
    """`addq.w #2` is a WORD add on the swapped longword, so an x of $ffff snaps down to $fffe and
    then UP to $0000 — it cannot carry into the half that is y at the time. The seed is declared
    fabricated: nothing in the game drives the camera to $ffff, and what this pins is the operand
    SIZE, which every ordinary seed leaves free."""
    info = _run_snap("x at the top of the word (FABRICATED)", 0xffff, 0x00b7, True, False)
    assert leaf.read_int(info, SCROLL_FOLLOW_X, WORD, "x") == 0x0000
    assert leaf.read_int(info, SCROLL_FOLLOW_Y, WORD, "y") == 0x00b6


# --- $624c / $6268: the floppy's drive-select lines ----------------------------------------------
#
# NOT SOUND, DESPITE THE CHIP. The YM2149's port A carries the floppy's side and drive-select lines
# in its low three bits and four other peripherals' in the rest, which is what makes the write a
# READ-MODIFY-WRITE and the register's prior contents an INPUT of the run. Neither surface is in the
# image: a port that drove the wrong register, or wrote without reading first, leaves memory exactly
# as this one does — so every case here asserts the ordered access ledger and the register file, and
# `psg_seed` is what declares the five bits the routine must preserve.

_DRIVE_SELECT = leaf.register_glue("psg_set_drive_select", [ctypes.c_uint32])
_DESELECT = leaf.image_glue("floppy_deselect_drives")
PSG_INSN_CAP = 32


def _run_drive_select(name, what, glue, held, bits, regs=None):
    """One read-modify-write of port A, against the byte the case declares the chip held.

    ``regs`` carries the ENTRY REGISTER for $624c, whose `bits` is the original's d0 — the oracle
    would otherwise enter on whatever the runner left, and every case with a non-zero `bits` would
    compare a reconstruction that was told the value against an original that was not.
    """
    seed = {PSG_REG_PORT_A: held}
    expected = (held & PSG_PORT_A_KEEP) | bits
    info = leaf.run(name, glue, [], what, regs={**(regs or {}), "_pokes": {}},
                    max_insns=PSG_INSN_CAP, psg_seed=seed)

    assert not program_writes(info), f"{what}: it wrote memory, which it does not"
    # THE CHIP MODEL IS test_sound.py's, not a third copy of it: `_Psg` is the same class
    # `_whole_tick_model` returns and `_vbl_model` drives sixty lines below.
    chip = _Psg(seed)
    chip.write(PSG_REG_PORT_A, expected)
    values, known = chip.values, chip.known
    leaf.assert_psg_surfaces(info, [(PSG_EVENT_READ, PSG_REG_PORT_A, held),
                                    (PSG_EVENT_WRITE, PSG_REG_PORT_A, expected)],
                             values, known, what)
    return expected, info


# The bytes the chip is declared to have held. $ff and $00 bracket it; the middle two are chosen so
# that the KEPT bits and the REPLACED ones disagree — a port that masked with the complement, or
# that skipped the mask, lands on a different byte for each.
HELD_BYTES = (0x00, 0xff, 0xf8, 0x07, 0xa5, 0x5a)
# ...and the values handed in d0. THE LAST TWO ARE ABOVE THE THREE FLOPPY LINES, and they are what
# say the `or.b d0,d1` takes the WHOLE low byte: the routine does not mask its argument, so a caller
# with rubbish in bits 3-7 SETS bits the `andi.b #$f8` above it had just preserved. The game itself
# produces only 5 and 7 — $6268 passes 7, and $6242 falls THROUGH into the routine with 5 — so
# nothing in the image reaches these two; they pin the instruction's width, which every in-range
# value leaves free, and the sweep's `the-bits-are-masked-before-the-or` mutant is invisible
# without them.
# 5 AND 7 ARE THE REACHABLE PAIR and both must be here: 7 is what $6268 calls with, and 5 is what
# $6242 FALLS THROUGH with — every drive-A disk read in the game. An earlier draft of this tuple
# pinned $18 and $ff, which no path reaches, and left 5 out; a mutant special-casing `bits == 5`
# survived the whole suite twice. Unreachable values pin the instruction's WIDTH and reachable ones
# pin what the game does, and a sweep of the first kind does not substitute for the second.
DRIVE_BITS = (0, 1, 2, 4, 5, 7, 0x18, 0xff)


@pytest.mark.parametrize("held", HELD_BYTES)
@pytest.mark.parametrize("bits", DRIVE_BITS)
def test_the_drive_select_keeps_five_bits_and_replaces_three(held, bits):
    _run_drive_select("psg_set_drive_select",
                      f"psg_set_drive_select held={held:#04x} bits={bits}",
                      _DRIVE_SELECT(bits), held, bits, regs={"d0": bits})[0]


def test_the_kept_bits_really_come_from_the_chip_and_not_from_a_constant():
    """The guard on the sweep above: two seeds that differ ONLY in the bits the mask preserves must
    produce two different writes. A port that wrote `bits` alone — no read, no mask — passes every
    case whose held byte happens to have those bits clear, and this is what it cannot pass."""
    written = []
    for held in (0x08, 0xf0):
        info = _run_drive_select("psg_set_drive_select",
                                 f"psg_set_drive_select preserved {held:#04x}",
                                 _DRIVE_SELECT(0), held, 0, regs={"d0": 0})[1]
        written.append(info["regs"]["psg_events"][-1][2])
    # READ OFF THE CHIP'S LEDGER, not off the expectation this case computed — `(held & $f8) | 0`
    # is arithmetic on two literals and could not fail.
    assert written == [0x08, 0xf0], (
        f"the chip was given {[hex(v) for v in written]}: the preserved bits did not come from the "
        f"seed, so the read-modify-write is reading nothing")


@pytest.mark.parametrize("held", HELD_BYTES)
def test_the_idle_timer_deselects_every_drive(held):
    """$6268 — `move.b #$7,d0 / bsr psg_set_drive_select`: side select and both drive selects HIGH,
    and all three are ACTIVE LOW, so this is every drive off and the motor stopped."""
    what = f"floppy_deselect_drives held={held:#04x}"
    info = _run_drive_select("floppy_deselect_drives", what, _DESELECT, held,
                             PSG_DRIVES_DESELECTED)[1]
    # ASKED OF THE LEDGER, not of the expectation this case computed: asserting on the returned
    # value would be true by construction for every `held` and could not fail.
    kind, register, value = info["regs"]["psg_events"][-1]
    assert (kind, register) == (PSG_EVENT_WRITE, PSG_REG_PORT_A), f"{what}: the last access was not"
    assert value & PSG_DRIVES_DESELECTED == PSG_DRIVES_DESELECTED, (
        f"{what}: the byte the chip was given, {value:#04x}, leaves a floppy line low")


def test_an_undeclared_port_a_sinks_the_run_rather_than_inventing_the_bits():
    """The refusal this battery rests on. The five bits the routine preserves belong to the printer,
    the RS-232 lines and the monitor's GPO; served a fabricated 0 both cores would keep nothing,
    write the same byte and agree — green, and wrong on every machine. An undeclared PSG read-back
    sinks `emu.run` itself, so this arrives as a RuntimeError rather than as a differential."""
    with pytest.raises(RuntimeError, match=r"psg_seed=\{14: <byte>\}"):
        leaf.run("floppy_deselect_drives", _DESELECT, [], "no declared port A",
                 regs={"_pokes": {}}, max_insns=PSG_INSN_CAP)


# --- $e032 / $e0a8: THE ROUND BONUS ---------------------------------------------------------------
#
# The sequence WB_EVENT_FINISHED_E1BE has been waiting for since batch 41 phase C named that word
# and could not say what read it. Two phases of one unit of WB_HUD_METER_VALUE a frame: drain it to
# zero for WB_ROUND_BONUS_SCORE a unit, then refill it to WB_ROUND_BONUS_METER_TARGET and ask
# `game_key_actions` for the reload.
#
# THREE OF THE FOUR ARMS ARE LIGHT and are driven whole below. The fourth is the SETUP, which runs
# `actor_table_reset`, the whole stage-transition hinge and the round banner — every one of them a
# routine with a battery of its own — and it has its own section further down.

_RUN_FRAME = leaf.image_glue("round_bonus_run_frame")
_SETUP = leaf.image_glue("round_bonus_setup")
RUN_FRAME_INSN_CAP = 4096       # the drain arm's own dozen plus bcd_add_score_bd70's loop


def _bonus_pokes(salt, finished, active, refilling, meter, target=0, maximum=0x14,
                 score=b"\x00\x12\x34\x56"):
    """The state machine's four words plus the meter and the score, address-keyed where they are
    not the case's subject."""
    return {EVENT_FINISHED_E1BE: leaf.word(finished) + leaf.word(active),
            ROUND_BONUS_METER_TARGET: leaf.word(target) + leaf.word(refilling),
            HUD_METER_MAX: leaf.word(maximum) + leaf.word(meter),
            BCD_SCORE: score,
            BCD_ADDEND: leaf.keyed_block(BCD_ADDEND, BCD_SCORE_LEN, salt)}


# A NOTE ON "THIS ARM DOES NOT WRITE X", which six cases below claim: the claim is carried by the
# `allowed` list each one passes to `leaf.run`, and by nothing else. An earlier draft of this section
# also called an `_assert_untouched(info, addr, ...)` helper afterwards, and the gate showed every
# one of those calls to be unreachable — `leaf.run` asserts `stray_writes(info["writes"], allowed)`
# BEFORE returning, and every address they named was outside its own case's `allowed`, so the run
# raised first in every instance. Worse, `info["writes"]` is the ORACLE's set, so the helper's
# message blamed the port for something only the original was checked for. Leaving an address OUT of
# `allowed` is the pin; a second assertion after the fact was not one.


def test_the_four_state_words_are_two_adjacent_pairs():
    """The pokes above write four words with two longword-shaped entries, which is only correct if
    the addresses really are adjacent in that order — and the routine's two `clr.l`s depend on the
    same fact. Asserted rather than assumed, because a constant retyped in the header would
    otherwise make every case below seed a different word than it names."""
    assert ROUND_BONUS_ACTIVE == EVENT_FINISHED_E1BE + WORD
    assert ROUND_BONUS_REFILLING == ROUND_BONUS_METER_TARGET + WORD
    assert HUD_METER_VALUE == HUD_METER_MAX + WORD


def test_a_frame_with_no_finished_event_writes_nothing_at_all():
    """The first arm, and the one that runs on every ordinary frame of the game: `tst.w $e1be.l /
    beq` returns before reading anything else. Seeded with the count MID-FLIGHT so that a port whose
    guard was missing would drain the meter and be caught, rather than finding nothing to do."""
    what = "round_bonus_run_frame no finished event"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=0, active=ROUND_BONUS_ACTIVE_SET,
                         refilling=0, meter=0x10)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME, [], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)
    assert not program_writes(info), f"{what}: it wrote memory, which this arm does not"


@pytest.mark.parametrize("meter", [0x14, 0x10, 2])
def test_the_drain_spends_one_unit_a_frame_and_scores_for_it(meter):
    """The third arm above zero: `subq.w #1,$b6fa.l` then WB_ROUND_BONUS_SCORE into the packed-BCD
    score, and the phase does NOT switch while the meter is still standing."""
    what = f"round_bonus_run_frame drain from {meter}"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=0, meter=meter)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME,
                    [(HUD_METER_VALUE, WORD), (BCD_SCORE, BCD_SCORE_LEN),
                     (BCD_ADDEND, BCD_SCORE_LEN)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == meter - 1
    # THE RE-READ IS AN EQUIVALENCE, and this says only the weak half of why. `tst.w $b6fa.l` at
    # $e068 reads the meter back AFTER the score and src/game.c reproduces that; the two spellings
    # can differ only if something between them writes that word, and the only thing between them is
    # `bcd_add_score_bd70`. What CANNOT be asked here is "how many times was the meter written":
    # `info["writes"]` is address-keyed, so a second store to the same word overwrites the entry and
    # leaves no trace. This asserts the reachable thing — that the meter's own bytes were written —
    # and the PREMISE is carried by round two's `control/the-score-adder-also-writes-the-meter`,
    # which breaks it deliberately and is CAUGHT (../STATUS.md, batch 42 phase B).
    assert all(addr in info["writes"] for addr in (HUD_METER_VALUE, HUD_METER_VALUE + 1)), (
        f"{what}: the drain did not write both bytes of the meter word")
    expected = leaf.bcd_expected(0x00123456, ROUND_BONUS_SCORE, BCD_SCORE_LEN, subtract=False)
    assert leaf.read_int(info, BCD_SCORE, BCD_SCORE_LEN, what) == expected.value
    # ROUND_BONUS_REFILLING is deliberately outside `allowed` above: the phase must NOT switch
    # while the meter is still standing, and a run that switched it reds as a stray write.


def test_the_last_drained_unit_switches_the_phase():
    """`tst.w $b6fa.l / bne` — the meter is re-read AFTER the score, so the switch happens on the
    frame the decrement lands on zero and not the frame after."""
    what = "round_bonus_run_frame the last unit"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=0, meter=1)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME,
                    [(HUD_METER_VALUE, WORD), (ROUND_BONUS_REFILLING, WORD),
                     (BCD_SCORE, BCD_SCORE_LEN), (BCD_ADDEND, BCD_SCORE_LEN)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == 0
    assert leaf.read_int(info, ROUND_BONUS_REFILLING, WORD, what) == ROUND_BONUS_REFILLING_SET


def test_a_meter_already_empty_wraps_and_rides_its_borrow_into_the_score():
    """THE THREADED X, and the reason this site is pinned rather than assumed clear.

    `subq.w #1,$b6fa.l` is the instruction immediately above `move.l #$410,d0 / bsr
    bcd_add_score_bd70`, and a `move.l` of an immediate is X-silent — so the extend the packed-BCD
    add folds in is that decrement's own BORROW. On a meter already at zero the word wraps to $ffff
    and the borrow is SET, so the score rises by one more than the addend; and the `tst.w` below
    then sees a non-zero word, so the drain does not end. Both consequences are required here: a
    port that hard-coded the extend clear differs by exactly one unit in the last digit.

    Reachable state, not a fabricated one — nothing stops another routine emptying the meter between
    the setup and this frame — but no case can reach it through the sequence's own arithmetic, which
    is why it is seeded directly and said so.
    """
    what = "round_bonus_run_frame an already-empty meter"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=0, meter=0)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME,
                    [(HUD_METER_VALUE, WORD), (BCD_SCORE, BCD_SCORE_LEN),
                     (BCD_ADDEND, BCD_SCORE_LEN)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == WORD_MASK
    with_borrow = leaf.bcd_expected(0x00123456, ROUND_BONUS_SCORE, BCD_SCORE_LEN,
                                    subtract=False, extend=1)
    without = leaf.bcd_expected(0x00123456, ROUND_BONUS_SCORE, BCD_SCORE_LEN, subtract=False)
    assert with_borrow.value != without.value, "the two extends are indistinguishable on this seed"
    assert leaf.read_int(info, BCD_SCORE, BCD_SCORE_LEN, what) == with_borrow.value
    # ...and it is outside `allowed` here for the sharper reason: the wrapped meter must NOT end
    # the drain, because the `tst.w` below the score reads $ffff and not zero.


@pytest.mark.parametrize("meter,target", [(0x10, 0x14), (0, 0x14), (0x12, 0x14)])
def test_the_refill_raises_the_meter_until_it_reaches_the_target(meter, target):
    """The fourth arm short of its target: `addq.w #1,$b6fa.l / cmp.w $e1c2.l,d0 / bne` and nothing
    else — the four words stand and no reload is asked for."""
    what = f"round_bonus_run_frame refill {meter} toward {target}"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=ROUND_BONUS_REFILLING_SET,
                         meter=meter, target=target)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME, [(HUD_METER_VALUE, WORD)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert program_writes(info).keys() <= {HUD_METER_VALUE, HUD_METER_VALUE + 1}
    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == meter + 1


def test_reaching_the_target_clears_all_four_words_and_asks_for_the_reload():
    """THE ENDING, and the two `clr.l`s that make it four words in two instructions: $e092 clears
    WB_EVENT_FINISHED_E1BE together with WB_ROUND_BONUS_ACTIVE, and $e098 the target together with
    the phase flag. A census of the WORD forms at either pair's low half finds no writer, which is
    why WB_EVENT_FINISHED_E1BE's plate carried a smaller operand count than the image supports until
    this batch."""
    what = "round_bonus_run_frame the last refilled unit"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=ROUND_BONUS_REFILLING_SET,
                         meter=0x13, target=0x14)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME,
                    [(HUD_METER_VALUE, WORD), (EVENT_FINISHED_E1BE, leaf.LONGWORD_BYTES),
                     (ROUND_BONUS_METER_TARGET, leaf.LONGWORD_BYTES),
                     (ROUND_END_RELOAD_REQUEST, WORD)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == 0x14
    for addr, name in ((EVENT_FINISHED_E1BE, "finished"), (ROUND_BONUS_ACTIVE, "active"),
                       (ROUND_BONUS_METER_TARGET, "target"), (ROUND_BONUS_REFILLING, "refilling")):
        assert leaf.read_int(info, addr, WORD, what) == 0, f"{what}: {name} survived the clear"
    assert leaf.read_int(info, ROUND_END_RELOAD_REQUEST, WORD, what) \
        == ROUND_END_RELOAD_REQUEST_SET


def test_the_refill_compares_for_equality_so_a_meter_past_the_target_runs_away():
    """`cmp.w $e1c2.l,d0 / bne` is EQUALITY alone, exactly as `bg_plot_round_banner`'s test on the
    same two words is. A meter that starts ABOVE its target therefore steps past it and the sequence
    never ends — one frame of that runaway is what this pins, and the ending's own case above is
    what says equality does fire when it is reached."""
    what = "round_bonus_run_frame a meter past its target"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET,
                         active=ROUND_BONUS_ACTIVE_SET, refilling=ROUND_BONUS_REFILLING_SET,
                         meter=0x20, target=0x14)
    info = leaf.run("round_bonus_run_frame", _RUN_FRAME, [(HUD_METER_VALUE, WORD)], what,
                    regs={"_pokes": pokes}, max_insns=RUN_FRAME_INSN_CAP)

    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == 0x21
    # ROUND_END_RELOAD_REQUEST is outside `allowed`: a meter that stepped PAST its target never
    # equalled it, so the ending must not fire and a run that fired it reds as a stray write.


# --- $e0a8: the round bonus's setup arm ------------------------------------------------------------
#
# THE HEAVIEST ROUTINE THIS BATTERY DRIVES, and the only one whose write set is not stated byte by
# byte here. It runs `actor_table_reset` over the A30 table, the whole stage-transition hinge
# (`stage_load_window`, which is the three background builders, the scroll publish, the palette and
# the sound module's start/stop) and `bg_plot_round_banner` — 181,189 bytes across 37 bands, every
# one of them already modelled byte for byte by the battery that owns it (test_actor.py,
# test_stage.py). A second model of all three here could disagree with the first while both stayed
# green, which is the reason this file imports rather than restates everywhere else.
#
# SO WHAT THIS SECTION CLAIMS, EXACTLY. The strong pin is the differential itself: both cores run on
# one image and the harness requires them to agree over every byte of it, so a port that skipped a
# callee or passed one the wrong argument reds on the image. On top
# of that the cases below state (a) this routine's OWN four words, byte for byte, and (b) that every
# other byte it writes falls inside a REGION one of the three callees owns. What is NOT claimed here
# is the content of those regions — that is the callees' own batteries' job, and saying so is the
# point of the region table rather than a longer band list.

# The regions, each named for the callee that owns it. Bases are the header's own constants wherever
# one exists, so a retyped constant fails as a mismatched base rather than drifting; the spans are
# stated, and `test_the_setup_regions_start_where_their_owners_do` pins every base that has a name.
# $18359 is WB_SND_PSG_SHADOW + 7, i.e. the mixer shadow onward — the module's second mutable band
# and the only region base below without a name of its own.
WB_SND_SHADOW_MUTABLE_AT = 7

SETUP_REGIONS = (
    (STATE_FLAG_A30, WORD, "the mode this routine switches into"),
    (wb("BG_PRESHIFT_CARRY"), 0x83b6 - wb("BG_PRESHIFT_CARRY"),
     "the scroll/build state block stage_load_window publishes"),
    (SCROLL_FOLLOW_X, leaf.LONGWORD_BYTES, "recomputed from the new start record"),
    (ACTOR_FOLLOWED_DEFAULT, leaf.LONGWORD_BYTES,
     "the followed record's position, copied from the start record"),
    (ACTOR_TABLE_A30, wb("ACTOR_SCREEN_RECORD_COUNT") * wb("ACTOR_RECORD_BYTES"),
     "all nineteen records, marked free and zeroed"),
    (ROUND_BONUS_ACTIVE, 3 * WORD, "this routine's own three words: active, target, refilling"),
    (wb("COPYLOCK_FLAG_A"), 4, "the copylock flags stage_load_window's tail clears"),
    (wb("STAGE_TUNE_LATCH"), 1, "the sound module's de-duplication byte"),
    (wb("BG_BUILD_CARRY"), 0xfe1e - wb("BG_BUILD_CARRY"),
     "bg_build_carry and the two pointers the hinge latches"),
    (wb("SND_MUSIC_CHANNEL_STATE"), 0x17c6c - wb("SND_MUSIC_CHANNEL_STATE"),
     "the sound module's channel states and globals"),
    (wb("SND_PSG_SHADOW") + WB_SND_SHADOW_MUTABLE_AT, 4, "...and its second mutable band"),
    (wb("BG_BUFFER_BASE"), 0x70000 - wb("BG_BUFFER_BASE"),
     "the eight background buffer copies"),
    # ...and the two the PERFECT arm alone reaches. `bg_plot_round_banner` scores its bonus when the
    # meter EQUALS its maximum, so only the `already-full` case below writes these — which is why
    # that case is the one that asserts they were written and every other asserts they were not.
    (BCD_SCORE, BCD_SCORE_LEN, "the perfect bonus, when the meter came in full"),
    (BCD_ADDEND, BCD_SCORE_LEN, "...and the addend the adder stages before folding it in"),
)
# COMPOSED, not rounded: the stage hinge's own cap (the three builders over eight buffers, the
# publish, the palette and the song), the banner's, and the table reset's nineteen records. A flat
# round number would have been ~5x this and would have de-tuned the runaway pin, which is the cost
# batch 32 recorded for a global cap raise.
TABLE_RESET_INSN_CAP = wb("ACTOR_SCREEN_RECORD_COUNT") * 16 + leaf.LEAF_INSN_CAP
SETUP_INSN_CAP = LOAD_WINDOW_INSN_CAP + ROUND_INSN_CAP + TABLE_RESET_INSN_CAP


def _run_setup(what, pokes, glue=_SETUP, name="round_bonus_setup", **kwargs):
    """One whole setup, on the machine and chip a case declares.

    POISON IS OFF for the stage battery's reason: the bytes this run writes include the two POINTERS
    the hinge then reads the start record back through, so inverting them does not re-run this
    function — it runs a different one.

    WHAT THESE CASES DO NOT PIN IS THE CALL ORDER. `actor_table_reset` writes WB_ACTOR_TABLE_A30 and
    `stage_load_window` writes bands disjoint from it, so swapping the two leaves the same image —
    the same commuting problem $882 has, and here it is stated rather than solved: that routine
    could be pinned with a behaviour that spends the other's output, and this one has no such lever.
    """
    return leaf.run(name, glue, [(base, length) for base, length, _why in SETUP_REGIONS], what,
                    regs={"_pokes": pokes}, max_insns=SETUP_INSN_CAP, poison=False,
                    psg_seed={PSG_REG_MIXER: TICK_MIXER}, hw_seed=leaf.hw_declared(), **kwargs)


# (meter, maximum) — and THE MAXIMUM VARIES, which it did not in the first draft of this sweep.
# Every row seeded $14 and `round_bonus_setup` reads the threshold out of WB_HUD_METER_MAX, so a
# port that hard-coded `0x14` passed the whole battery; the gate is what found it. The rows: the sum
# arm (bumped BELOW the maximum), the exact clamp point, one clamped, the PERFECT arm (meter ==
# maximum, which is also what makes the banner score), and one whose maximum is not $14.
#
# NO ROW SEPARATES `blt` FROM `ble`, AND NONE CAN. The two differ only when d1 == d0, and there they
# store the same number — so the strict/non-strict boundary is value-equivalent at $e0f4 whatever
# the seed. Said here rather than implied by a row that looks like it brackets it.
SETUP_CLAMP_CASES = [
    ("under-the-clamp", 0x00, 0x14),       # 0 + 4 = 4 < $14 — the SUM arm
    ("exactly-at-the-clamp", 0x10, 0x14),  # $10 + 4 == $14 — `blt` false, stores the sum
    ("over-the-clamp", 0x11, 0x14),        # $11 + 4 = $15 > $14 — clamped
    ("meter-full", 0x14, 0x14),            # ...and the PERFECT arm with it
    ("a-binding-different-maximum", 0x08, 0x0a),  # $08 + 4 = $0c > $0a, so the maximum BINDS and
]                                                 #   the answer is $0a — which a port holding the
                                                  #   other rows' $14 could not produce. The first
                                                  #   draft of this row used $0c, the clamp POINT,
                                                  #   where a hard-coded $14 gives the same sum and
                                                  #   the mutant survived.


@pytest.mark.parametrize("case,meter,maximum", SETUP_CLAMP_CASES,
                         ids=[row[0] for row in SETUP_CLAMP_CASES])
def test_the_setup_arms_the_count_and_clamps_its_target_to_the_maximum(case, meter, maximum):
    """WB_ROUND_BONUS_METER_TARGET is min(value + 4, maximum), SIGNED, and the threshold comes out
    of WB_HUD_METER_MAX rather than out of a constant — which is what the last row says."""
    what = f"round_bonus_setup {case} ({meter}/{maximum})"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET, active=0, refilling=0,
                         meter=meter, maximum=maximum)
    info = _run_setup(what, pokes)

    expected = min(maximum, meter + ROUND_BONUS_METER_BUMP)
    assert leaf.read_int(info, ROUND_BONUS_METER_TARGET, WORD, what) == expected
    assert leaf.read_int(info, ROUND_BONUS_ACTIVE, WORD, what) == ROUND_BONUS_ACTIVE_SET
    assert leaf.read_int(info, ROUND_BONUS_REFILLING, WORD, what) == 0
    assert leaf.read_int(info, STATE_FLAG_A30, WORD, what) == STATE_FLAG_SET

    # THE BANNER'S PERFECT ARM IS REACHED THROUGH THIS ROUTINE, on the one row where the meter comes
    # in full — `bg_plot_round_banner` tests the same two words for EQUALITY. Asserted both ways, so
    # the rows that must not score are as much a case as the row that must.
    scored = any(addr in info["writes"] for addr in range(BCD_SCORE, BCD_SCORE + BCD_SCORE_LEN))
    assert scored == (meter == maximum), (
        f"{what}: the score was {'' if scored else 'not '}touched and the meter came in "
        f"{'full' if meter == maximum else 'short'}")


def test_the_setup_clears_a_phase_flag_the_last_bonus_left_standing():
    """`clr.w $e1c4.l` at $e108, and the seed is what makes it a case at all.

    Every other row here comes in with the phase flag already down, so the clear writes 0 over 0 and
    a port that dropped it leaves the identical image — the sweep's
    `e0a8/the-phase-flag-is-left-as-it-was` survived exactly that, and `poison=False` (which these
    rows need, because the run writes pointers it then reads back through) means the attribution
    pass cannot cover for it either. So this row comes in with the flag STANDING and requires the
    setup to take it down: a bonus that began with a stale flag would otherwise start in its REFILL
    phase and count a meter it had never drained.
    """
    what = "round_bonus_setup a stale phase flag"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET, active=0,
                         refilling=ROUND_BONUS_REFILLING_SET, meter=0x10, maximum=0x14)
    info = _run_setup(what, pokes)
    assert leaf.read_int(info, ROUND_BONUS_REFILLING, WORD, what) == 0, (
        f"{what}: the setup left the phase flag standing, so the count would start refilling")


def test_the_bump_is_a_signed_word_and_a_meter_near_the_top_takes_the_sum():
    """`addi.w #$4,d0 / cmp.w d0,d1 / blt` compares two 16-bit SIGNED words, so a meter at $7ffe
    bumps to $8002, reads as NEGATIVE, and the clamp does not fire — the target becomes the sum and
    not the maximum. FABRICATED: no meter the game produces is anywhere near $7fff, and what this
    pins is the compare's signedness, which every ordinary seed leaves free."""
    what = "round_bonus_setup a meter at the top of the signed word (FABRICATED)"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET, active=0, refilling=0,
                         meter=0x7ffe, maximum=0x14)
    info = _run_setup(what, pokes)
    assert leaf.read_int(info, ROUND_BONUS_METER_TARGET, WORD, what) == 0x8002, (
        "the clamp fired on a bumped meter that reads negative, so the compare is unsigned here")


def test_the_setup_loads_entry_three_of_the_bank_table_and_a_literal_start_record():
    """WHICH stage the bonus loads, which no other case here asks.

    `move.w #$18,d0 / lea $103e8.l,a1 / lea (a1,d0.w),a1` names entry $18 / WB_SCENE_MAP_BANK_BYTES
    == 3 of the table's seven, and its two longwords are the hinge's `map` and `tiles`. Then a1 is
    OVERWRITTEN by `lea $1d434.l,a1`, so the start record is a literal and not a table read — which
    is the asymmetry worth a case, because the obvious reading is that all three come from the entry.

    Read back off WB_STAGE_MAP_PTR and WB_STAGE_START_PTR, the two longwords `stage_load_window`
    latches its a0 and a1 into: a setup that indexed the wrong entry, or took the start record from
    the table, lands a different pointer in one of them.
    """
    what = "round_bonus_setup the bank entry it loads"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET, active=0, refilling=0,
                         meter=0x10, maximum=0x14)
    info = _run_setup(what, pokes)

    entry = SCENE_MAP_BANK_TABLE + ROUND_BONUS_MAP_BANK
    assert ROUND_BONUS_MAP_BANK == 3 * SCENE_MAP_BANK_BYTES, (
        "the byte offset the original spells is not entry 3 of the table")
    expected_map = int.from_bytes(harness.BASE_IMAGE[entry:entry + leaf.LONGWORD_BYTES], "big")
    assert leaf.read_int(info, STAGE_MAP_PTR, leaf.LONGWORD_BYTES, what) == expected_map, (
        f"{what}: the map latched is not entry 3's first longword")
    assert leaf.read_int(info, STAGE_START_PTR, leaf.LONGWORD_BYTES, what) \
        == ROUND_BONUS_START_RECORD, (
        f"{what}: the start record latched is not the literal $1d434 — a port that took a1 from the "
        f"table entry rather than from the `lea` below it lands here")


def test_the_setup_is_reached_through_the_run_frame_and_not_only_directly():
    """$e032's SECOND arm, driven whole: the setup is a `bsr` and not an arm, so a case that only
    ever entered at $e0a8 would leave the call itself unexercised. Runs the same clamp arithmetic
    through the caller and requires the caller's own guard word to be the thing that selected it."""
    what = "round_bonus_run_frame reaching the setup"
    pokes = _bonus_pokes(leaf.case_salt(what), finished=STATE_FLAG_SET, active=0, refilling=0,
                         meter=0x10, maximum=0x14)
    info = _run_setup(what, pokes, glue=_RUN_FRAME, name="round_bonus_run_frame")

    assert leaf.read_int(info, ROUND_BONUS_METER_TARGET, WORD, what) == 0x14
    assert leaf.read_int(info, ROUND_BONUS_ACTIVE, WORD, what) == ROUND_BONUS_ACTIVE_SET
    # HUD_METER_VALUE is outside SETUP_REGIONS: the frame that runs the setup must not also
    # drain, and a run that drained it reds as a stray write.


# ==================================================================================================
# $716: THE VERTICAL-BLANK HANDLER, and the convention this project had to invent for it
# ==================================================================================================
#
# The program's ONE periodic tick — MFP timers A and B are masked off at boot — installed at the
# level-4 autovector by hw_init_vectors and again at $e506. Everything else in this reconstruction
# is CALLED; this is called by the machine, and it ends in `rte`.
#
# NO ROUTINE IN ANY OF THE THREE PORTS HAD EVER ENDED IN ONE. Neither BuggyBoy nor Joust contains a
# single `rte` instruction, so there was no convention to copy and the one below is designed here.
# include/game.h carries the reasoning; these are the cases that hold it up:
#
#   * `_run_vbl` checkpoints the `rte` ITSELF, which is the kit's documented answer for a run that
#     cannot reach an `rts`. The runner plants a 4-byte sentinel AT a7 and stops when the PC reaches
#     it; an `rte` pops a 6-byte EXCEPTION frame — SR from (a7), PC from 2(a7) — so it reads the
#     sentinel's high word as a status register and assembles a PC out of its low word and whatever
#     follows. `test_the_handler_cannot_reach_the_runners_sentinel_on_its_own` is that, measured.
#   * Nothing is lost by stopping one instruction early: the `rte` restores a7 and the SR and writes
#     no image byte, and the `movem` pair has already put back every register the body saved.
#   * AND THE CHECKPOINT IS SELF-WITNESSING, unlike the scene driver's. A `stop_pc` run stops at
#     EITHER the checkpoint or an `rts`, which is why `leaf.run_reaching` exists; this handler HAS no
#     `rts` (`test_the_handler_has_exactly_one_terminator_and_it_is_the_rte` says so from the bytes),
#     so the checkpoint is the only stop and `emu.run` raises when a run reaches neither.

_VBL = leaf.image_glue("vbl_handler")
VBL_ENTRY = leaf.entry_of("vbl_handler")
VBL_RTE = VBL_ENTRY + _extent(VBL_ENTRY) - len(RTS)     # $748 — the handler's last instruction
VBL_MOVEM_RESTORE = VBL_RTE - 4                         # `movem.l (a7)+,#$7fff`, the one above it
VBL_INSN_CAP = WHOLE_TICK_INSN_CAP + 64


_VBL_PSG_SEED = {PSG_REG_MIXER: TICK_MIXER, PSG_REG_PORT_A: 0xf9}


def _vbl_pokes(salt, idle, counter=0x0100):
    """The music tick's own pokes — test_sound.py's, so the tick runs on the state its battery
    seeds — plus the handler's two words."""
    pokes = dict(_tick_pokes(salt))
    pokes[VBL_COUNTER] = leaf.word(counter)
    pokes[FLOPPY_IDLE_TIMER] = leaf.word(idle)
    return pokes


def test_the_handler_has_exactly_one_terminator_and_it_is_the_rte():
    """THE PREMISE THE CHECKPOINT RESTS ON, taken from the image rather than from a reading.

    `_run_vbl` sets `stop_pc` and asserts nothing about WHICH stop fired, which is only sound while
    the `rte` is the sole way out — an `rts` anywhere in the body would give the run a second
    ending, and a port that returned early would stop at it and pass. So the walk is asked: every
    instruction the handler reaches, and exactly one of them terminates.
    """
    body, _calls = _walk_body(VBL_ENTRY)
    terminators = {at: _decode(at)[1].split(";")[0].strip() for at in sorted(body)
                   if _decode(at)[1].split(";")[0].strip().split()[0] in _RETURNS}
    assert terminators == {VBL_RTE: "rte"}, (
        f"the handler's terminators are {[(hex(a), t) for a, t in terminators.items()]}")
    assert VBL_MOVEM_RESTORE in body and _decode(VBL_MOVEM_RESTORE)[1].startswith("movem"), (
        "the instruction above the `rte` is not the register restore")


def test_the_handler_cannot_reach_the_runners_sentinel_on_its_own():
    """THE NEGATIVE CONTROL, and the measurement behind the whole convention.

    Without the checkpoint the run does not end: the `rte` pops a 6-byte exception frame off a stack
    the runner set up for a 4-byte `rts`, so the PC it assembles is not the sentinel. This is what
    makes `stop_pc` load-bearing here rather than decorative — a reader is owed the failing run, not
    the argument. It is also why no poke fixes it: the runner overwrites the frame's first longword
    after every poke lands, so the SR word and the PC's high half are not the case's to choose.
    """
    what = "vbl_handler with no checkpoint"
    pokes = _vbl_pokes(leaf.case_salt(what), idle=0)
    with pytest.raises(RuntimeError, match="did not reach rts"):
        leaf.run("vbl_handler", _VBL, [], what, regs={"_pokes": pokes},
                 max_insns=VBL_INSN_CAP, psg_seed=_VBL_PSG_SEED,
                 hw_seed=TEMPO_MACHINES["colour_50hz"])


def _vbl_model(memory, psg_seed, hw_seed):
    """The image and the chip the handler leaves: the counter, then the WHOLE music tick, then the
    floppy countdown.

    THE TICK'S MODEL IS test_sound.py's AND IS NOT RESTATED. `_whole_tick_model` is the same
    function that battery compares $17c74 against, so a divergence between the two is impossible by
    construction rather than by review — which is the rule this file follows everywhere. What is
    added here is the arithmetic either side of it, in the order the handler does it.
    """
    memory.word(VBL_COUNTER, (memory.read_word(VBL_COUNTER) + 1) & WORD_MASK)
    psg = _whole_tick_model(hw_seed)(memory, psg_seed)

    idle = memory.read_word(FLOPPY_IDLE_TIMER)
    if idle:
        idle = (idle - 1) & WORD_MASK
        memory.word(FLOPPY_IDLE_TIMER, idle)
        if idle == 0:
            kept = psg.read(PSG_REG_PORT_A) & PSG_PORT_A_KEEP
            psg.write(PSG_REG_PORT_A, kept | PSG_DRIVES_DESELECTED)
    return psg


def _run_vbl(what, idle, counter=0x0100, machine="colour_50hz"):
    hw_seed = TEMPO_MACHINES[machine]
    pokes = _vbl_pokes(leaf.case_salt(what), idle, counter)
    memory = _Memory(_poked_image(pokes))
    psg = _vbl_model(memory, _VBL_PSG_SEED, hw_seed)

    info = leaf.run("vbl_handler", _VBL, write_bands(memory.written), what,
                    regs={"_pokes": pokes}, max_insns=VBL_INSN_CAP, stop_pc=VBL_RTE,
                    psg_seed=_VBL_PSG_SEED, hw_seed=hw_seed)

    assert_written(info, memory.written, what)
    leaf.assert_psg_surfaces(info, psg.events, psg.values, psg.known, what)
    assert info["regs"]["hw_events"] == list(_tempo_hw_events(hw_seed)), (
        f"{what}: the tick's hardware reads were {info['regs']['hw_events']}")
    return info


@pytest.mark.parametrize("counter", [0, 1, 0x0100, WORD_MASK])
def test_every_frame_raises_the_counter_flip_screen_waits_on(counter):
    """`addq.w #1,$74a.l`, and the $ffff row is the wrap: the counter is the word `flip_screen`
    blocks on twice, and it is raised HERE and nowhere else in the image."""
    what = f"vbl_handler counter {counter:#06x}"
    info = _run_vbl(what, idle=0, counter=counter)
    assert leaf.read_int(info, VBL_COUNTER, WORD, what) == (counter + 1) & WORD_MASK


def test_an_idle_timer_at_rest_is_not_decremented_below_zero():
    """`tst.w $64f2.l / beq` — the countdown is guarded, so a drive already deselected stays that
    way rather than wrapping the timer to $ffff and deselecting again 65,535 frames later."""
    what = "vbl_handler idle timer at rest"
    info = _run_vbl(what, idle=0)
    # The timer is absent from the model's write set and so from `allowed`: the `tst.w` guard
    # means a resting timer is not decremented, and a run that wrote it reds as a stray write.


@pytest.mark.parametrize("idle", [0x96, 3, 2])
def test_a_running_idle_timer_counts_down_without_touching_the_drives(idle):
    """`subq.w #1,$64f2.l / bne` — every frame but the last one. $96 is what floppy_unwind_return
    arms it with, and 2 is the frame before the deselect."""
    what = f"vbl_handler idle timer {idle}"
    info = _run_vbl(what, idle=idle)
    assert leaf.read_int(info, FLOPPY_IDLE_TIMER, WORD, what) == idle - 1
    assert all(event[1] != PSG_REG_PORT_A for event in info["regs"]["psg_events"]), (
        f"{what}: port A was touched on a frame the timer had not expired")


def test_the_frame_the_timer_expires_stops_the_drives():
    """The handler's one call, and the only path in the image that reaches
    `floppy_deselect_drives`: the timer lands on zero and every drive-select line goes high."""
    what = "vbl_handler the frame the idle timer expires"
    info = _run_vbl(what, idle=1)
    assert leaf.read_int(info, FLOPPY_IDLE_TIMER, WORD, what) == 0
    assert info["regs"]["psg_events"][-2:] == [
        (PSG_EVENT_READ, PSG_REG_PORT_A, _VBL_PSG_SEED[PSG_REG_PORT_A]),
        (PSG_EVENT_WRITE, PSG_REG_PORT_A,
         (_VBL_PSG_SEED[PSG_REG_PORT_A] & PSG_PORT_A_KEEP) | PSG_DRIVES_DESELECTED)], (
        f"{what}: the run's last two chip accesses are not the deselect's read and write")


@pytest.mark.parametrize("machine", sorted(TEMPO_MACHINES))
def test_the_tick_runs_on_the_machine_the_case_declares(machine):
    """The handler's `jsr 14(a0)` really reaches `snd_music_tick`, and the tick really branches on
    the two hardware bytes: three machines, three drop values, and the ordered read stream each
    implies. A port that dropped the call writes none of the tick's bytes and reds on the image."""
    _run_vbl(f"vbl_handler tick on {machine}", idle=0, machine=machine)


# ==================================================================================================
# BATCH 42 PHASE C: flip_screen, and the two waits that kept it out for two phases
# ==================================================================================================
#
# `flip_screen` ($694) busy-waits TWICE on WB_VBL_COUNTER, at $6aa and $6d0. Batch 42 phase B
# registered the boundary and its gate found the sharp half: the model did not REFUSE the natural
# one-run case, it ACCEPTED it, and then balanced its counters by an off-by-one that cancelled — a
# port that had deleted the whole first wait passed. Phase A's registered remedy was a per-ADDRESS
# poll counter and phase B corrected it to per-SITE, because both of `game_key_actions`' waits are on
# the SAME byte.
#
# THE KIT NOW COUNTS PER WAIT SITE (os.h, "WAIT SITES"), on both shores, keyed by the address of the
# instruction at which the ORIGINAL's wait RE-READS its byte. So a case declares `wait_sites=` and the harness
# compares arrivals against polls wait by wait. Two consequences for the cases below:
#
#   * A RUN MUST DECLARE EVERY SITE IT POLLS AT, including one no entry stores on — the first wait
#     falls through in a single poll when the counter is seeded ready, and that poll still has to be
#     counted or it is the hole itself. `sched_poll8` refuses an undeclared site.
#   * THE $6ca SPLIT THE PHASE-B PLATE CALLED REQUIRED IS NOT PERFORMED, and the reason is that the
#     remedy discharges it rather than that it was wrong. One wait per run was required while the
#     counters were run TOTALS; per site, the two waits in one run are separable, and the mutant the
#     split existed to catch is caught HERE, in the composite (see the two deleted-wait cases). The
#     kit pins the same contrast on a planted routine of its own
#     (tools/recreate_kit/test/test_sched_model.py).
_flip = leaf.image_glue("flip_screen")


def test_the_two_wait_sites_are_where_the_original_RE_READS_the_counter():
    """THE CROSS-PIN, and it is the point of assembling the body above.

    `src/game.c` names WB_FLIP_READY_WAIT_PC and WB_FLIP_TICK_WAIT_PC at its two `sched_poll16`
    calls, and every case below declares the same two as its `wait_sites`. Both would agree with each
    other while naming an address the original never re-reads the counter at — they come from one
    header. What breaks that circle is the LABELS, which are where the assembled body puts each
    instruction, and the case above requires that body to be the image's own bytes.

    IT IS THE READ AND NOT THE TEST, which the first wait is what shows: `ready_wait` labels the
    `move.w $74a.l,d0`, and the `cmpi.w #$1,d0` that decides the loop is two instructions BELOW it.
    The model applies a due store just before the site's instruction on both shores, so a site
    naming the compare would land it after the read it was meant to change.
    """
    assert FLIP_READY_WAIT_PC == _FLIP_LABELS["ready_wait"], (
        "WB_FLIP_READY_WAIT_PC is not where the first wait re-reads the counter")
    assert FLIP_TICK_WAIT_PC == _FLIP_LABELS["tick_wait"], (
        "WB_FLIP_TICK_WAIT_PC is not where the second wait re-reads the counter")
    # ...AND THE FIRST WAIT'S READ REALLY IS ABOVE ITS TEST, which is what makes the distinction
    # above a fact about this routine rather than a general caution.
    assert FLIP_READY_WAIT_PC < _FLIP_LABELS["ready_test"] < _FLIP_LABELS["ready_branch"], (
        "the first wait reads, tests and branches at three addresses; the SITE is the first")


def test_the_three_key_wait_sites_are_where_the_original_RE_READS_the_scancode():
    """The same cross-pin for the byte waits, whose sites moved into include/wonderboy.h this phase.

    They were derived from these very labels before `src/game.c` needed them as constants; now that
    both sides read the header, this is what keeps the header honest against the image.
    """
    assert wb("KEY_HELP_WAIT_PC") == HELP_WAIT_PC
    assert wb("KEY_PAUSE_WAIT_PC") == PAUSE_WAIT_PC
    assert wb("KEY_UNPAUSE_WAIT_PC") == UNPAUSE_WAIT_PC


# --- driving the two waits ------------------------------------------------------------------------
# THE SITES A flip_screen RUN DECLARES. Both, always: the run polls at each of them, and a poll the
# model is not counting is refused rather than served.
FLIP_SITES = (FLIP_READY_WAIT_PC, FLIP_TICK_WAIT_PC)


# One iteration of either wait is its compare and its branch back; the first also re-reads the word.
FLIP_READY_INSNS_PER_ITERATION = 3
FLIP_TICK_INSNS_PER_ITERATION = 2
FLIP_STRAIGHT_INSNS = 14          # the swap, the copy, the tail and its three branches


def flip_cap(ready_polls, tick_polls):
    return (FLIP_STRAIGHT_INSNS
            + FLIP_READY_INSNS_PER_ITERATION * ready_polls
            + FLIP_TICK_INSNS_PER_ITERATION * tick_polls
            + leaf.RUNNER_SENTINEL_INSN)


def flip_pokes(counter, toggle=0, flash=0):
    return {SCREEN_FRONT: leaf.longword(FRONT_AT_ENTRY),
            SCREEN_BACK: leaf.longword(BACK_AT_ENTRY),
            VBL_COUNTER: word(counter),
            FRAME_TOGGLE: word(toggle),
            FLASH_TIMER: word(flash)}


def vbl_bump(site, nth, value):
    """The store the VBL interrupt makes, as a case declares it: WB_VBL_COUNTER takes `value` just
    before the `nth` arrival at `site`. It is a WORD store, which is what the compares read."""
    return {"pc": site, "nth": nth, "addr": VBL_COUNTER, "width": WORD, "value": value}


FLIP_WRITES = [(SCREEN_FRONT, LONG), (SCREEN_BACK, LONG), (VBL_COUNTER, WORD),
               (FRAME_TOGGLE, WORD), (FLASH_TIMER, WORD)]


def _assert_flip_swapped_and_ticked(info, what, toggle_at_entry):
    """Every image byte the routine leaves, on the arms that reach its tail."""
    assert leaf.read_int(info, SCREEN_FRONT, LONG, what) == BACK_AT_ENTRY, (
        f"{what}: the buffer being displayed is not the one that was being drawn into")
    assert leaf.read_int(info, SCREEN_BACK, LONG, what) == FRONT_AT_ENTRY
    assert leaf.read_int(info, VBL_COUNTER, WORD, what) == 0, f"{what}: the counter was not cleared"
    assert leaf.read_int(info, FRAME_TOGGLE, WORD, what) == (~toggle_at_entry & WORD_MASK), (
        f"{what}: WB_FRAME_TOGGLE was not INVERTED — a decrement leaves the same byte on the "
        f"$0001 seed and a different one on every other")


@pytest.mark.parametrize("ready_nth", WAIT_ITERATIONS)
def test_the_first_wait_spins_until_the_vbl_raises_the_counter(ready_nth):
    """THE FIRST WAIT, DRIVEN FOR REAL, which is what the phase-B case could not do.

    The counter comes in at 0, so `cmpi.w #$1,d0 / blt.s` spins; the case declares the VBL's bump at
    the `ready_nth` arrival at $6aa, and a SECOND entry releases the tick wait below it. Two trigger
    PCs in one run — refused outright until this phase, and sound now only because the counters are
    per site.

    `poison=False`: the tail's `clr.w $74a.l` lands on the very word both entries store, and the
    attribution pass is refused over a scheduled byte. The seeds are what separate the writes
    instead — WB_FRAME_TOGGLE comes in $0001 so an inversion and a decrement differ, and the two
    buffers are distinct so the swap cannot pass by leaving them alone.
    """
    tick_nth = 2
    what = f"flip_screen, the ready wait released at arrival {ready_nth}"
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=0, toggle=1)}, poison=False,
                    max_insns=flip_cap(ready_nth, tick_nth),
                    schedule=[vbl_bump(FLIP_READY_WAIT_PC, ready_nth, VBL_COUNTER_READY),
                              vbl_bump(FLIP_TICK_WAIT_PC, tick_nth, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)
    _assert_flip_swapped_and_ticked(info, what, toggle_at_entry=1)
    assert info["regs"]["sched_site_arrivals"] == (ready_nth, tick_nth), (
        f"{what}: the original's two waits ran {info['regs']['sched_site_arrivals']} iterations")


@pytest.mark.parametrize("tick_nth", WAIT_ITERATIONS)
def test_the_second_wait_spins_until_the_counter_CHANGES(tick_nth):
    """THE SECOND WAIT, and the arrangement the whole remedy is about.

    The counter is seeded ALREADY READY, so the first wait falls through in ONE poll and only the
    second is declared — which is exactly the composite phase B showed to be a false-green machine
    under run totals. It is a true case now: the first wait's single poll is counted at ITS OWN site
    and compared there.

    The tick wait cannot be seeded past. `move.w $74a.l,d0` at $6ca takes a copy and `cmp.w $74a.l,d0`
    compares against it one instruction later, so the first comparison always holds however the case
    seeds the word — every run of this routine spins here at least once.
    """
    what = f"flip_screen, the tick wait released at arrival {tick_nth}"
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=VBL_COUNTER_READY, toggle=1)}, poison=False,
                    max_insns=flip_cap(1, tick_nth),
                    schedule=[vbl_bump(FLIP_TICK_WAIT_PC, tick_nth, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)
    _assert_flip_swapped_and_ticked(info, what, toggle_at_entry=1)
    assert info["regs"]["sched_site_arrivals"] == (1, tick_nth), (
        f"{what}: the ready wait fell through in one arrival and the tick wait ran {tick_nth}")


@pytest.mark.parametrize("counter", [VBL_COUNTER_READY, 2, 0x7fff])
def test_a_counter_already_at_or_above_the_threshold_falls_through_in_one_poll(counter):
    """The ready wait's THRESHOLD, from below and from the top of the signed range."""
    what = f"flip_screen, the counter already at {counter:#06x}"
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=counter)}, poison=False,
                    max_insns=flip_cap(1, 1),
                    schedule=[vbl_bump(FLIP_TICK_WAIT_PC, 1, counter + 1)],
                    wait_sites=FLIP_SITES)
    assert info["regs"]["sched_site_arrivals"][0] == 1, f"{what}: the ready wait spun"


@pytest.mark.parametrize("counter", [0x8000, WORD_MASK])
def test_a_counter_ABOVE_the_signed_range_is_not_ready(counter):
    """`blt.s` is SIGNED, so a counter with its top bit set reads as BELOW 1 and the wait spins.

    DECLARED FABRICATED. `vbl_handler` raises the counter one at a time and `flip_screen` clears it
    every frame, so 32,768 frames would have to pass with no flip for the game to reach here — but
    the signedness is the instruction's, and a port that wrote `>=` on unsigned words would agree
    with the original on every reachable seed and disagree here.
    """
    what = f"flip_screen, the counter at {counter:#06x} (fabricated: signed-range top)"
    ready_nth = 2
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=counter)}, poison=False,
                    max_insns=flip_cap(ready_nth, 1),
                    schedule=[vbl_bump(FLIP_READY_WAIT_PC, ready_nth, VBL_COUNTER_READY),
                              vbl_bump(FLIP_TICK_WAIT_PC, 1, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)
    assert info["regs"]["sched_site_arrivals"][0] == ready_nth, (
        f"{what}: the wait fell through, so the compare is not signed")


@pytest.mark.parametrize("flash,expected", [(0, None), (1, 0), (2, 1), (0x8000, 0x7fff)])
def test_the_flash_countdown_is_decremented_only_while_it_runs(flash, expected):
    """`tst.w $714.l / beq` then `subq.w #1 / beq`: three arms, and the two that WRITE colour 0 are
    exclusive. 1 is the frame the flash ends on and 2 the frame before it.

    WHAT THE COLOUR WRITES DO IS NOT PINNED AND CANNOT BE. $ffff8240 is off the 68000's 24-bit bus
    as far as the loaded image goes: the oracle drops the two `move.w`s and `src/game.c` sinks them,
    so the white flash this routine paints is invisible to every surface the harness compares —
    exactly as set_palette's sixteen colour writes have been since batch 12. What IS pinned is the
    timer word the two arms branch on, which is in the image.
    """
    what = f"flip_screen, the flash timer at {flash:#06x}"
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=VBL_COUNTER_READY, flash=flash)},
                    poison=False, max_insns=flip_cap(1, 1),
                    schedule=[vbl_bump(FLIP_TICK_WAIT_PC, 1, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)
    if expected is None:
        # A RESTING TIMER IS NOT WRITTEN AT ALL, which is a stronger claim than "it is still zero":
        # the `tst.w` guard means the arm below it never runs, so a port that decremented and stored
        # would wrap the word to $ffff. `FLIP_WRITES` carries the timer, so a write here would pass
        # the stray-write check and has to be caught by its ABSENCE.
        assert FLASH_TIMER not in info["writes"], (
            f"{what}: a resting timer was written, so the `tst.w` guard is missing")
        return
    assert leaf.read_int(info, FLASH_TIMER, WORD, what) == expected


@pytest.mark.parametrize("toggle", [0, 1, 0xffff, 0x1234])
def test_the_frame_toggle_is_INVERTED_and_not_stepped(toggle):
    """`not.w $712.l`. The $0000/$ffff pair is what the game really holds; the other two are what
    separate an inversion from a decrement, a negation and a XOR with 1."""
    what = f"flip_screen, the frame toggle at {toggle:#06x}"
    info = leaf.run("flip_screen", _flip, FLIP_WRITES, what,
                    regs={"_pokes": flip_pokes(counter=VBL_COUNTER_READY, toggle=toggle)},
                    poison=False, max_insns=flip_cap(1, 1),
                    schedule=[vbl_bump(FLIP_TICK_WAIT_PC, 1, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)
    assert leaf.read_int(info, FRAME_TOGGLE, WORD, what) == (~toggle & WORD_MASK)


def test_a_run_that_polls_at_a_site_it_did_not_declare_is_refused():
    """THE GUARD THAT MAKES THE SITE LIST MEAN SOMETHING, and without a case it is code no run reaches.

    A `flip_screen` case that declared only the trigger's site would leave the FIRST wait's poll
    uncounted — which is precisely the arrangement that used to balance by cancellation. The kit
    refuses the poll instead of serving it, and the run reds through the shared os_* refusal tally
    with a clause naming the site list.
    """
    with pytest.raises(AssertionError, match="SITE THIS CASE DID NOT DECLARE"):
        harness.differential(FLIP_ENTRY, {"_pokes": flip_pokes(counter=VBL_COUNTER_READY)}, _flip,
                             poison=False, max_insns=flip_cap(1, 1),
                             schedule=[vbl_bump(FLIP_TICK_WAIT_PC, 1, VBL_COUNTER_READY + 1)],
                             wait_sites=[FLIP_TICK_WAIT_PC])


def test_a_schedule_trigger_that_is_not_a_declared_wait_site_is_refused():
    """The successor to the refusal batch 42 phase A shipped, which turned away a schedule naming
    two trigger PCs.

    That guard existed because both sides counted a run TOTAL, and two waits under two triggers could
    not be told apart; per-site counting makes two triggers ordinary, and the two cases above use
    them. What is refused now is narrower and stronger: an entry whose trigger is not one of the
    run's declared sites, which nothing would count and which could therefore never come due — the
    kit measures that on a planted routine of its own.
    """
    with pytest.raises(ValueError, match="not among the declared wait sites"):
        harness.differential(FLIP_ENTRY, {"_pokes": flip_pokes(counter=VBL_COUNTER_READY)}, _flip,
                             poison=False, max_insns=flip_cap(1, 1),
                             schedule=[vbl_bump(FLIP_TICK_WAIT_PC, 1, VBL_COUNTER_READY + 1)],
                             wait_sites=[FLIP_READY_WAIT_PC])


# ==================================================================================================
# BATCH 42 PHASE C: game_main_loop — THE WHOLE FRAME, AS ONE RUN
# ==================================================================================================
#
# The spine's last row, and the only one whose case is a COMPOSITION rather than a routine. `$4a0`
# makes fifteen calls and does nothing else; one iteration is the differential unit, and the
# checkpoint is the `bra.s $4a0` at $508 the loop turns round on.
#
# WHAT A CASE HERE PINS, AND WHAT IT DOES NOT.
#   * THE WHOLE IMAGE, at the instant control reaches the backward branch. That is the strong pin and
#     it is what makes a dropped call, a swapped pair or an inverted gate visible: 245,000-odd
#     instructions of fourteen reconstructed routines have to leave the same 21,000-odd bytes the
#     original does.
#   * NOT THE REGISTERS. The oracle leaves fifteen of them and this reconstruction models exactly one
#     register file — `sprite_draw_pass`' (include/blit.h), which is the loop's only callee with a
#     register interface — and four more calls run after it. So the box is an INPUT here and the
#     comparison is memory plus the reported action, which is stated rather than left implied.
#   * THE STRAY-WRITE BOUND IS A REGION TABLE, not a model. `FRAME_REGIONS` below says which band of
#     the image each of the frame's callees owns; every byte of it is already modelled by that
#     callee's own battery, and re-modelling twenty-one thousand of them here would be a second
#     statement that could disagree with the first. Same standing as `round_bonus_setup`'s regions in
#     batch 42 phase B, and it inherits that entry's queued "derive it from the callees" item.
#
# THE SEED IS A COHERENT FRAME AND NOT TWO BATTERIES STITCHED TOGETHER, which is a lesson this case
# had to learn: `test_behavior._walk_pokes` and `test_actor._spawn_pass_pokes` each seed a table the
# OTHER does not know about, and the frame itself republishes one of the two pointers mid-run —
# `panel_refresh_frame` writes WB_TABLE_PTR_21E8C at $b372, so `actor_spawn_pass` five calls later
# reads the pointer the FRAME chose and not the one the seed did. The spawn table the frame chooses
# is therefore seeded WHERE THE FRAME WILL LOOK, and the shipped bytes at that address are not a
# spawn table at all: left as they ship, the countdown walk runs 1,948 records past its own start
# before it finds a terminator. That is a property of an image whose level data has not been loaded,
# not of the game, and the seed says so by planting the terminator.
from test_actor import (SPAWN_ARMED, SPAWN_COUNTDOWN, SPAWN_HEADER_BYTES,   # noqa: E402
                        SPAWN_KILL_COUNT, SPAWN_RECORD_BYTES, SPAWN_TERMINATOR, SPAWN_TYPE,
                        SPAWN_X, SPAWN_Y, HEADER_CURSOR, HEADER_LIVE, HEADER_MAX_LIVE,
                        HEADER_WRAPPED, _spawn_pass_pokes, _armed_records, SPAWN_TABLE_SLOTS)
from test_blit import PassRegs, PASS_FIELD_BY_REG, FIELD_BY_REG, SCRATCH_REGS  # noqa: E402

LOOP_ENTRY = leaf.entry_of("game_main_loop")
LOOP_BACKWARD_BRANCH = 0x508          # `bra.s $4a0`, the instruction one iteration ends on

TABLE_PTR_21E8C = wb("TABLE_PTR_21E8C")
ACTOR_SCREEN_RECORDS = wb("ACTOR_SCREEN_RECORDS")
ACTOR_TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")
ACTOR_RECORD_BYTES = wb("ACTOR_RECORD_BYTES")
ACTOR_SCREEN_RECORD_COUNT = wb("ACTOR_SCREEN_RECORD_COUNT")
ACTOR_TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
BG_QUEUE_H_COUNT = wb("BG_QUEUE_H_COUNT")
BG_QUEUE_V_COUNT = wb("BG_QUEUE_V_COUNT")
BG_REQUEST_UP = wb("BG_REQUEST_UP")
FRAME_TICK_B39A = wb("FRAME_TICK_B39A")
DIGIT_SIGNIFICANT_SEEN = wb("DIGIT_SIGNIFICANT_SEEN")
PANEL_FRAME_DELAY = wb("PANEL_FRAME_DELAY")
PANEL_RESTORE_FLAG_DBB3 = wb("PANEL_RESTORE_FLAG_DBB3")

# WHERE panel_refresh_frame REPUBLISHES THE SPAWN TABLE. `$b372` writes WB_TABLE_PTR_21E8C with one
# of two literals, chosen on WB_STATE_FLAG_A32 (include/wonderboy.h) — this is the A32-clear one, and
# the seed below plants the frame's spawn table there so the run's two readers agree.
FRAME_SPAWN_TABLE = 0x21c60

# The busy frame's own inputs, named because each exists to make one call WRITE.
FRAME_SCROLL_STEPS = 3            # two-pixel horizontal steps for bg_scroll_run_queue to spend
FRAME_METER_VALUE = 5             # ...a meter for the round bonus's drain arm to count down
FRAME_MESSAGE_ID = 1              # ...a message for the box to run
FRAME_MESSAGE_LIFETIME = 0x40
FRAME_TICK_NTH = 2                # which arrival at $6d0 the VBL's bump lands before
HELD_RELEASE_NTH = 3              # ...and which arrival at $64e the IKBD's release lands before
SEQUENCE_FIRST_SCANCODE = 0x61    # UNDO, the first byte of the cheat sequence at $608

# The frame's write REGIONS: (base, length, which call owns it). A stray-write BOUND, in the sense
# batch 42 phase B's SETUP_REGIONS is one — every band is modelled byte for byte by the battery named
# beside it, and what this table adds is that the frame writes NOWHERE ELSE.
FRAME_REGIONS = (
    # FIVE FIELDS, NOT THEIR HULL. $712..$753 spans them, and 52 of those bytes are `vbl_handler`'s
    # OWN CODE ($716..$749) — a hull here would whitelist a self-modifying write into an instruction
    # and label it "flip_screen's", which is a stray-write bound saying the opposite of what it means.
    (FRAME_TOGGLE, WORD, "flip_screen's frame toggle"),
    (FLASH_TIMER, WORD, "...its flash countdown"),
    (VBL_COUNTER, WORD, "...the counter it waits on and clears"),
    (SCREEN_FRONT, LONG, "...the buffer pointer it publishes"),
    (SCREEN_BACK, LONG, "...and the one it swaps in"),
    (JOY1_PREV, JOY1_CURRENT + 1 - JOY1_PREV, "joy1_latch_edge's two-frame pipeline"),
    (BG_QUEUE_H_COUNT, 8, "bg_scroll_run_queue's counters"),
    (BG_REQUEST_UP, 4, "bg_scroll_run_queue's four request bytes"),
    (ACTOR_SCREEN_RECORDS, ACTOR_TABLE_DEFAULT - ACTOR_SCREEN_RECORDS,
     "project_followed_actor / project_actor_list, into the projection array"),
    (ACTOR_TABLE_DEFAULT, ACTOR_SCREEN_RECORD_COUNT * ACTOR_RECORD_BYTES,
     "actor_spawn_pass, into the record it allocates"),
    (ACTOR_TABLE_SELECTED, LONG, "...and the table pointer the projections publish"),
    (FRAME_TICK_B39A, WORD, "panel_refresh_frame's tick"),
    (DIGIT_SIGNIFICANT_SEEN, WORD, "hud_draw_score's leading-zero latch"),
    (PANEL_FRAME_DELAY, 6, "panel_frame_timers"),
    (PANEL_RESTORE_FLAG_DBB3, 1, "panel_restore_dirty_regions"),
    (TABLE_PTR_21E8C, LONG, "panel_refresh_frame republishing the spawn table"),
    (FRAME_SPAWN_TABLE - SPAWN_HEADER_BYTES, SPAWN_HEADER_BYTES + 2 * SPAWN_RECORD_BYTES,
     "actor_spawn_pass over the table the frame chose"),
    (BACK_AT_ENTRY, SCREEN_BUFFER_BYTES, "bg_scroll_blit, sprite_draw_pass, the panel and the "
                                        "message box, all into the buffer being drawn into"),
)

# ...and what the BUSY seed adds, each owned by the call the seed woke up.
BUSY_FRAME_REGIONS = FRAME_REGIONS + (
    (KEY_SEQUENCE_CURSOR, WORD, "game_key_actions stepping the cheat sequence"),
    (HUD_METER_VALUE, WORD, "round_bonus_run_frame's drain"),
    (BCD_SCORE, BCD_SCORE_LEN, "...and the packed-BCD score it adds to"),
    (BCD_ADDEND, LONG, "...through bcd_add_score_bd70's addend word"),
    (TEXT_REQUEST, WORD, "text_run_message_box consuming the request"),
)

_LOOP_FN = leaf.bind("game_main_loop", leaf.IMAGE_ARG + [ctypes.POINTER(PassRegs)], ctypes.c_uint32)


def _loop_glue(_lib, image):
    """The loop, handed a FRESH sprite-pass register file zeroed at entry.

    Fresh per call for `test_blit._regs_glue`'s reason — the attribution pass runs the candidate a
    second time and a carried box would start it from the first run's output. Zeroed because the
    oracle is entered with zeroed registers here: nothing the frame writes depends on them (the one
    field the pass reads as an input is its stack-unwind cursor, which it leaves in a register), so
    a case that varied them would be varying something no surface can see.
    """
    box = PassRegs()
    for reg in range(SCRATCH_REGS):
        box.blit.scratch[reg] = 0
    for field in FIELD_BY_REG.values():
        setattr(box.blit, field, 0)
    for field in PASS_FIELD_BY_REG.values():
        setattr(box, field, 0)
    return _LOOP_FN(image, ctypes.byref(box))


def _frame_pokes(what, paused=0, flag_a30=0, request=0, scancode=0, spawn_armed=False):
    """A whole frame's worth of state, coherent across the fifteen calls.

    The two big tables come from the batteries that own them — the behaviour walk's from
    test_behavior and the actor pool's free markers from test_actor — and this adds the frame's own
    gates plus the spawn table AT THE ADDRESS THE FRAME REPUBLISHES.
    """
    salt = leaf.case_salt(what)
    pokes = dict(_spawn_pass_pokes(salt, _armed_records([(0, 0)] * SPAWN_TABLE_SLOTS),
                                   {HEADER_MAX_LIVE: 4, HEADER_LIVE: 4,
                                    HEADER_CURSOR: 0, HEADER_WRAPPED: 0},
                                   flag_a30=flag_a30))
    pokes = leaf.overlay(pokes, _walk_pokes(salt, [None] * 8))
    header = FRAME_SPAWN_TABLE - SPAWN_HEADER_BYTES
    frame_table = {
        # The four header words. LIVE below MAX_LIVE and WRAPPED clear is the CURSOR arm, so a frame
        # with `spawn_armed` set spawns exactly one record; equal counts make the pass return after
        # its countdown walk, which is the quiet arm.
        header + HEADER_MAX_LIVE: word(4),
        header + HEADER_LIVE: word(0 if spawn_armed else 4),
        header + HEADER_CURSOR: word(0),
        header + HEADER_WRAPPED: word(0),
        FRAME_SPAWN_TABLE + SPAWN_ARMED: bytes([0xff if spawn_armed else 0]),
        FRAME_SPAWN_TABLE + SPAWN_COUNTDOWN: bytes([3]),
        FRAME_SPAWN_TABLE + SPAWN_TYPE: word(0x10),
        FRAME_SPAWN_TABLE + SPAWN_KILL_COUNT: word(0),
        FRAME_SPAWN_TABLE + SPAWN_X: word(0x0140),
        FRAME_SPAWN_TABLE + SPAWN_Y: word(0x0080),
        # ...and the terminator one record on, WITHOUT which the walk runs 1,948 records into data
        # that is not a spawn table (see this section's header).
        FRAME_SPAWN_TABLE + SPAWN_RECORD_BYTES: word(SPAWN_TERMINATOR),
        TABLE_PTR_21E8C: leaf.longword(FRAME_SPAWN_TABLE),
    }
    pokes = leaf.overlay(pokes, frame_table)
    pokes.update({GAME_PAUSED: word(paused),
                  ROUND_END_RELOAD_REQUEST: word(request),
                  KEY_LAST_SCANCODE: bytes([scancode]),
                  # THE SCROLL QUEUE'S TWO COUNTERS, STATED. `_spawn_pass_pokes` fills the tier's
                  # bands with keyed bytes, and these two words land inside one of them — so left
                  # alone they hold a salt-dependent step count, and one salt measured here ran
                  # bg_scroll_run_queue for 1.5 MILLION instructions where its neighbour ran 2,000.
                  # A cap cannot be a cap over a seed like that.
                  BG_QUEUE_H_COUNT: word(FRAME_SCROLL_STEPS),
                  BG_QUEUE_V_COUNT: word(0),
                  VBL_COUNTER: word(VBL_COUNTER_READY)})
    pokes.update(_screen_pokes(salt))
    _assert_the_screen_seed_reached_the_image(pokes, salt, what)
    return pokes


# ONE NAME FOR THE HELD FRAME'S CASE, because its salt is its seed: the premise below and the
# differential must run the SAME image, or the premise measures a frame nobody drives.
HELD_FRAME_CASE = "game_main_loop, a paused frame whose key is still held"


def _held_frame_pokes(what=HELD_FRAME_CASE):
    """The busy frame, paused, with the pause key still down — so the FIRST call waits too."""
    pokes = _busy_frame_pokes(what, paused=GAME_PAUSED_SET)
    pokes.update({KEY_LAST_SCANCODE: bytes([KEY_SCANCODE_P]),
                  TEXT_REQUEST: bytes([PAUSE_MESSAGE_ID])})
    _assert_the_screen_seed_reached_the_image(pokes, leaf.case_salt(what), what)
    return pokes


def _screen_pokes(salt):
    """The two screen pointers, and the buffer the frame DRAWS into filled with keyed bytes.

    THE FILL IS NOT DECORATION, and leaving it out cost this section its biggest surface. These cases
    run `poison=False` — the flip's tail clears the very word their schedule stores, and the
    attribution pass is refused over a scheduled byte — so a call whose writes happen to equal what
    the destination ALREADY HELD is invisible. As the image ships, the screen and the background
    buffers are BOTH ZERO: `bg_scroll_blit` copies zeros over zeros, 19,200 of them, and the mutant
    that DROPPED THE WHOLE CALL left every frame case green. Seeding the destination away from what
    the routine leaves is what the poison pass would have bought, and `sched.h`'s own contract says
    to do exactly that.

    Applied LAST by both callers, and that is load-bearing too: `test_behavior._walk_pokes` fills the
    tier's band with keyed bytes and WB_SCREEN_BACK lies inside it, so an earlier draft of this seed
    was silently overwritten and the frame drew into the buffer the image ships rather than the one
    the case named.
    """
    return {SCREEN_FRONT: leaf.longword(FRONT_AT_ENTRY),
            SCREEN_BACK: leaf.longword(BACK_AT_ENTRY),
            BACK_AT_ENTRY: keyed_block(BACK_AT_ENTRY, SCREEN_BUFFER_BYTES, salt),
            # ...and the follow cursor, for the same reason: the projection writes it, and a zeroed
            # longword is what it would write on a zeroed camera.
            SCROLL_FOLLOW_X: keyed_block(SCROLL_FOLLOW_X, LONG, salt)}


def _assert_the_screen_seed_reached_the_image(pokes, salt, what):
    """`_screen_pokes` really is what the run will see — asked of the IMAGE, not of the dict.

    THE COMMENT SAYING "applied LAST" IS NOT A GUARD, and this hazard has fired five times in this
    project's history under `leaf.overlay`'s own docstring: a later layer whose keyed BAND covers one
    of these addresses wins, the dict still lists the poke, and every case stays green because the
    seed it was relying on was never in the image. That is exactly how the 19,200-byte
    `bg_scroll_blit` hole was reopened once already.

    `leaf.assert_bands_are_seeded` is the wrong instrument here: it asks whether a band is COVERED,
    and the band is covered either way — by the wrong bytes. So this compares the built image against
    the bytes `_screen_pokes` asked for, which is the question a case actually has.
    """
    image = harness.make_image(pokes)
    for addr, wanted in _screen_pokes(salt).items():
        got = bytes(image[addr:addr + len(wanted)])
        assert got == wanted, (
            f"{what}: the screen seed at {addr:#x} did not reach the image — a later poke layer "
            f"covers it. The frame would run on {got[:8].hex()} where the case asked for "
            f"{wanted[:8].hex()}, which is how a dropped call whose writes match the destination "
            f"goes unnoticed (see _screen_pokes).")


def _busy_frame_pokes(what, **kw):
    """A frame on which ELEVEN of the fifteen calls write, which is what makes a dropped call
    visible. `_frame_pokes` alone leaves six of them silent, and a call nothing makes DO something is
    a call no differential measures — batch 42 phase B's `$882` lesson, at the loop's scale.

    What each addition buys is named beside it, and
    `test_the_busy_frame_really_makes_each_call_write` is the premise: it measures every call's own
    contribution out of the ORACLE and requires exactly the set claimed here.
    """
    salt = leaf.case_salt(what)
    pokes = _frame_pokes(what, **kw)
    # $882: the shop's item cursor, the one cheap handler that both WRITES and reads the joystick
    # edge — test_behavior's record, through this file's own `_cursor_walk_pokes`.
    pokes = leaf.overlay(pokes, _cursor_walk_pokes(salt, joystick_state=1 << JOY1_RIGHT_BIT))
    pokes.update({
        # $53e: the cheat sequence's FIRST step, which writes the cursor and waits for nothing.
        KEY_SEQUENCE_MATCHED: word(0),
        KEY_SEQUENCE_CURSOR: word(0),
        KEY_LAST_SCANCODE: bytes([SEQUENCE_FIRST_SCANCODE]),
        # $e032: the DRAIN arm — the bonus active, not yet refilling, and a meter to spend.
        EVENT_FINISHED_E1BE: word(0xffff),
        ROUND_BONUS_ACTIVE: word(ROUND_BONUS_ACTIVE_SET),
        ROUND_BONUS_REFILLING: word(0),
        HUD_METER_VALUE: word(FRAME_METER_VALUE),
        # $bd8a: a message box with a lifetime to tick.
        TEXT_REQUEST: bytes([FRAME_MESSAGE_ID]),
        TEXT_LIFETIME_REQUEST: word(FRAME_MESSAGE_LIFETIME),
        VBL_COUNTER: word(VBL_COUNTER_READY),
    })
    pokes.update(_screen_pokes(salt))     # LAST: the walk's keyed band covers WB_SCREEN_BACK
    _assert_the_screen_seed_reached_the_image(pokes, salt, what)
    return pokes


# The frame is ~245,000 instructions on the oracle and its cost is dominated by two callees whose own
# batteries cap them individually. Stated as a round bound with the measured figure beside it rather
# than derived: no geometry here predicts a whole frame, and a cap that tracked the measurement would
# stop being a cap.
FRAME_INSN_CAP = 700_000          # measured: 245k quiet, 532k with a spawn, 556k paused


def _bands(regions):
    return [(base, length) for base, length, _owner in regions]


def _run_frame(what, pokes, tick_nth=2, regions=FRAME_REGIONS):
    """One iteration, checkpointed at the backward branch, with the VBL's bump declared."""
    allowed = _bands(regions)
    return leaf.run("game_main_loop", _loop_glue, allowed, what,
                    regs={"_pokes": pokes}, poison=False, max_insns=FRAME_INSN_CAP,
                    stop_pc=LOOP_BACKWARD_BRANCH,
                    schedule=[vbl_bump(FLIP_TICK_WAIT_PC, tick_nth, VBL_COUNTER_READY + 1)],
                    wait_sites=FLIP_SITES)


@pytest.mark.parametrize("spawn_armed", [False, True], ids=["quiet-spawn-pass", "one-spawn"])
def test_a_whole_unpaused_frame_runs_the_fifteen_calls(spawn_armed):
    """THE SPINE'S CLOSING CASE: 245,000 instructions of fourteen reconstructed routines and the
    flip, entered at $4a0 and compared at $508.

    `poison=False` for `flip_screen`'s reason — the tail's `clr.w $74a.l` lands on the word the run's
    own schedule stores, and the attribution pass is refused over a scheduled byte.

    The `one-spawn` row is what makes the twelfth call measurable: with LIVE below MAX_LIVE and one
    armed template the pass takes its cursor arm and turns a template into an actor, so a port that
    dropped `jsr $ff42` leaves a different image. The quiet row is the same frame with the pass
    returning after its countdown walk, which is what most frames do.
    """
    what = f"game_main_loop, an unpaused frame ({'one spawn' if spawn_armed else 'no spawn'})"
    info = _run_frame(what, _frame_pokes(what, spawn_armed=spawn_armed))
    assert info["ret"] == RETURNED, f"{what}: the iteration did not reach its backward branch"
    assert info["regs"]["sched_site_arrivals"] == (1, 2), (
        f"{what}: flip_screen's two waits ran {info['regs']['sched_site_arrivals']}")
    assert leaf.read_int(info, SCREEN_FRONT, LONG, what) != leaf.read_int(
        info, SCREEN_BACK, LONG, what), f"{what}: the frame did not end with the buffers swapped"


def test_a_PAUSED_frame_skips_four_calls_and_still_flips():
    """THE $66e GATE, and what it does NOT stop. Four calls are skipped — the round bonus, the panel
    refresh, the scene driver and the input-and-actors pair — and the other eleven still run, so the
    screen still flips and the message box still ticks. A port that gated the whole body, or none of
    it, leaves a different image either way.
    """
    what = "game_main_loop, a paused frame"
    info = _run_frame(what, _frame_pokes(what, paused=GAME_PAUSED_SET))
    assert info["ret"] == RETURNED
    # The four gated calls are exactly the ones that write these: a paused frame must touch none of
    # them, and must still leave flip_screen's own words.
    for addr, name in ((FRAME_TICK_B39A, "panel_refresh_frame's tick"),
                       (PANEL_RESTORE_FLAG_DBB3, "panel_restore_dirty_regions"),
                       (JOY1_PREV, "joy1_latch_edge")):
        assert addr not in info["writes"], f"{what}: {name} ran on a paused frame"
    assert leaf.read_int(info, VBL_COUNTER, WORD, what) == 0, f"{what}: the frame did not flip"


@pytest.mark.parametrize("flag", [0xffff, 0x0001])
def test_the_A30_gate_skips_the_spawn_pass(flag):
    """`tst.w $a30.l / bne.w $4fc` at $4ec — the loop's SECOND gate, and the one whose arm is a
    single call. The A30 mode is the round-bonus stage, which spawns nothing.

    The flag is read by four of the frame's other calls as well, so this is not a case about
    `actor_spawn_pass` in isolation; what it pins here is that the loop's own `tst.w` steers, which
    the image says by the spawn's writes being absent.
    """
    what = f"game_main_loop, the A30 flag at {flag:#06x}"
    info = _run_frame(what, _frame_pokes(what, flag_a30=flag, spawn_armed=True))
    assert info["ret"] == RETURNED
    assert FRAME_SPAWN_TABLE + SPAWN_COUNTDOWN not in info["writes"], (
        f"{what}: the spawn pass ran although the A30 flag is set")


def test_a_frame_whose_key_actions_UNWIND_never_reaches_the_backward_branch():
    """THE OTHER WAY OUT OF ONE ITERATION, and a case that assumed $508 was the only one would HANG
    rather than fail.

    `game_key_actions`' first arm pops this routine's return address and `jmp $e5ba`s into the boot
    chain, so a frame entered with the round-end request raised leaves through the loop's SECOND
    `bsr` and runs none of the thirteen calls below it. The checkpoint is that `jmp`, and the witness
    that the arm really fired is its own instruction — `leaf.run_reaching`.
    """
    what = "game_main_loop, a frame the round-end request unwinds"
    pokes = _frame_pokes(what, request=0xffff)
    info = leaf.run_reaching("game_main_loop", _loop_glue,
                             [(ROUND_END_RELOAD_REQUEST, WORD)], what, ROUND_END_UNWIND,
                             regs={"_pokes": pokes}, poison=False, max_insns=ARM_INSN_CAP,
                             stop_pc=ROUND_END_JMP)
    assert info["ret"] == ROUND_END, (
        f"{what}: the loop reported {info['ret']} rather than the unwind it took")
    assert FRAME_TICK_B39A not in info["writes"], f"{what}: the frame ran on past the unwind"


# --- the busy frame, the premise under it, and the frame that runs THREE waits ---------------------
# WHICH OF THE FIFTEEN CALLS WRITES, on each frame this section drives. The claim is the coverage the
# drop-a-call mutants rest on, and `test_the_busy_frame_really_makes_each_call_write` measures it out
# of the ORACLE rather than taking it on trust: a seed that stopped making a call do something would
# otherwise leave that call's mutant surviving with nothing failing.
#
# TWO CALLS ARE SILENT ON EVERY FRAME HERE and they are stated rather than hidden — see
# ../STATUS.md's honestly-unpinned list. `scene_run_frame` writes only in the A30/A32 modes, whose
# descriptor and actor table are a frame of their own; `sprite_draw_pass` writes only for a projected
# record whose sprite the descriptor table gives a bitmap, which the composition's actor table has
# not got.
# The EIGHT every frame here writes through, whatever else it is doing.
FRAME_CALLS_ALWAYS_WRITING = (
    "panel_refresh_frame", "game_latch_input_and_step_actors", "project_followed_actor",
    "bg_scroll_run_queue", "project_actor_list", "bg_scroll_blit", "game_snap_follow_cursor",
    "flip_screen",
)
# ...and what each frame adds. THE SPAWN IS THE PLAIN FRAME'S, deliberately: on the busy frame the
# actor table's slots are taken by the shop cursor and its terminator, the allocator hands back a
# record the pool does not have, and `spawn_one` writes through it into the 68000's VECTOR PAGE. That
# is the original's own arithmetic on a state the game cannot reach, and this battery declines to
# bring it inside a region table — the plain frame's `one-spawn` row is where the twelfth call is
# measured instead.
PLAIN_FRAME_EXTRA_WRITERS = ("actor_spawn_pass",)                                   # nine in all
BUSY_FRAME_EXTRA_WRITERS = ("game_key_actions", "round_bonus_run_frame",            # eleven
                            "text_run_message_box")
# THE HELD FRAME IS NOT THE BUSY ONE PLUS THE UNPAUSE, and the measurement is what says so:
# `game_key_actions` writes nothing there. The unpause runs FIRST and its payload FORGETS the
# scancode, so the keyboard routine two instructions later reads a zero and its cheat-sequence walk
# steps over nothing — a frame that lifts the pause spends the key that lifted it. Eleven again, and
# a different eleven.
HELD_FRAME_EXTRA_WRITERS = ("game_unpause_on_key_release", "round_bonus_run_frame",
                            "text_run_message_box")
# TWO CALLS NO FRAME HERE MEASURES, and they are named rather than left to a survivor nobody read.
FRAME_CALLS_NO_SEED_HERE_REACHES = ("scene_run_frame", "sprite_draw_pass")

# Each call, as (the checkpoint above it, the checkpoint below it, its name). The addresses are the
# loop's own call sites; `test_the_flip_is_the_body_this_battery_reconstructs` is not what pins them
# — `test_every_call_site_this_section_brackets_is_a_call` below is.
FRAME_CALL_SITES = (
    (0x4a0, 0x4a4, "game_unpause_on_key_release"),
    (0x4a4, 0x4a8, "game_key_actions"),
    (0x4b2, 0x4b8, "round_bonus_run_frame"),
    (0x4b8, 0x4be, "panel_refresh_frame"),
    (0x4be, 0x4c4, "scene_run_frame"),
    (0x4c4, 0x4ca, "game_latch_input_and_step_actors"),
    (0x4ca, 0x4d0, "project_followed_actor"),
    (0x4d0, 0x4d6, "bg_scroll_run_queue"),
    (0x4d6, 0x4dc, "project_actor_list"),
    (0x4dc, 0x4e2, "bg_scroll_blit"),
    (0x4e2, 0x4e6, "game_snap_follow_cursor"),
    (0x4e6, 0x4ec, "sprite_draw_pass"),
    (0x4f6, 0x4fc, "actor_spawn_pass"),
    (0x4fc, 0x502, "text_run_message_box"),
    (0x502, 0x508, "flip_screen"),
)


def test_no_frame_region_whitelists_a_routine_the_spine_RUNS():
    """A STRAY-WRITE BOUND MUST NOT COVER CODE, and the first draft of `FRAME_REGIONS` did.

    Its opening row was the HULL of `flip_screen`'s five data words, $712..$753 — and $716..$749 of
    that is `vbl_handler`'s own body. A band like that says "the frame may write here" over fifty-two
    bytes of instructions: a reconstruction that scribbled into one would pass the bound, and the
    owner column would blame the wrong routine for it.

    So every band is required to be disjoint from every routine the spine's own walk reaches. The
    entry addresses come from that walk rather than from a list, so a band that grows over a routine
    added later fails too. (`BACK_AT_ENTRY` and the spawn table are DATA and hold no entry point,
    which is what makes this checkable rather than merely careful.)
    """
    reached, _opaque, _tails = _reachable()
    for base, length, owner in FRAME_REGIONS + BUSY_FRAME_REGIONS:
        covered = sorted(entry for entry in reached if base <= entry < base + length)
        assert not covered, (
            f"the region at {base:#x}+{length} ({owner}) covers the entry point(s) "
            f"{[hex(a) for a in covered]} — a stray-write bound over CODE")


def test_every_call_site_this_section_brackets_is_a_call():
    """The bracket table above names fifteen ADDRESS PAIRS, and a pair that had drifted off the
    instruction it names would measure a different call's contribution — or none. So every `before`
    is required to hold a `bsr.w`/`jsr <abs>.l` to the routine the row names, and every `after` to be
    the instruction past it.
    """
    for before, after, name in FRAME_CALL_SITES:
        target = leaf.entry_of(name)
        encoded = bytes(harness.BASE_IMAGE[before:after])
        assert encoded in (bsr_w(before, target), jsr_abs_l(target)), (
            f"{before:#x} is not a call to {name} @ {target:#x} ending at {after:#x}, but "
            f"{encoded.hex()}")
    assert len(FRAME_CALL_SITES) == LOOP_CALL_COUNT, (
        f"the loop makes {LOOP_CALL_COUNT} calls and this table brackets {len(FRAME_CALL_SITES)}")


LOOP_CALL_COUNT = 15


LOOP_UNPAUSE_CALL = 0x4a0         # `bsr.w $638`, whose body waits on the held frame...
LOOP_FLIP_CALL = 0x502            # ...and `jsr $694.l`, whose body waits on every frame


def _schedule_up_to(checkpoint, held):
    """The (schedule, wait_sites) a run stopping at `checkpoint` needs, and no more.

    An entry that never comes due SINKS the run (`emu.run` says so by name), so a prefix that stops
    above a wait must not carry that wait's store — and a prefix that runs THROUGH one must. The two
    waits a frame can hold are the flip's, on every frame, and `game_unpause_on_key_release`'s, on
    the held frame alone.

    The SITES are declared for both regardless: a site is a counter, not a store, and declaring one
    the run never reaches costs an arrival count of zero.
    """
    entries, sites = [], list(FLIP_SITES)
    if held:
        sites = [UNPAUSE_WAIT_PC] + sites
        if checkpoint > LOOP_UNPAUSE_CALL:
            entries.append(release(UNPAUSE_WAIT_PC, KEY_SCANCODE_P_RELEASE, HELD_RELEASE_NTH)[0])
    if checkpoint > LOOP_FLIP_CALL:
        entries.append(vbl_bump(FLIP_TICK_WAIT_PC, FRAME_TICK_NTH, VBL_COUNTER_READY + 1))
    return dict(schedule=entries, wait_sites=sites) if entries else {}


def _call_contributions(pokes, held=False):
    """{call name: how many PROGRAM bytes it changed}, measured on the ORACLE alone.

    Two runs per call, checkpointed either side of it, and the difference between their write sets.
    The MACHINE STACK is left out (`leaf.program_writes`' band): every `bsr` pushes a return address,
    so counting it would report every call as writing four bytes and the premise would be vacuous —
    which is exactly what the first draft of this did.
    """
    image = harness.make_image(pokes)
    contributed = {}
    for before, after, name in FRAME_CALL_SITES:
        prefix = _oracle_writes_to(image, before, held)
        whole = _oracle_writes_to(image, after, held)
        contributed[name] = len({a for a in set(prefix) | set(whole)
                                 if prefix.get(a) != whole.get(a)})
    return contributed


def _oracle_writes_to(image, checkpoint, held):
    writes = emu.run(image, LOOP_ENTRY, {}, stop_pc=checkpoint, max_insns=FRAME_INSN_CAP,
                     **_schedule_up_to(checkpoint, held))[1]
    return {addr: value for addr, value in writes.items() if not leaf.on_machine_stack(addr)}


@pytest.mark.parametrize("frame,extra", [
    ("plain", PLAIN_FRAME_EXTRA_WRITERS),
    ("busy", BUSY_FRAME_EXTRA_WRITERS),
    ("held", HELD_FRAME_EXTRA_WRITERS),
], ids=["plain", "busy", "held"])
def test_each_frame_really_makes_the_calls_it_claims_WRITE(frame, extra):
    """THE PREMISE UNDER THE DROP-A-CALL COVERAGE, and it is a measurement rather than a claim.

    A call is only measured by an input that makes the callee DO something — batch 42 phase B's `$882`
    lesson, and the sweep proved it again at the loop's scale: on the plain frame SIX of the fifteen
    wrote nothing and every one of their drop-a-call mutants survived. This runs the oracle either
    side of each call and requires the writing set to be exactly the one claimed, so a seed that went
    quiet fails HERE instead of leaving a mutant unremarked six months later.
    """
    if frame == "held":
        # THE HELD FRAME'S SEED IS ITS CASE'S OWN, not a premise-shaped copy: the writer set claimed
        # below is the one the differential runs on, and a second salt would measure a second frame.
        pokes, what = _held_frame_pokes(), HELD_FRAME_CASE
    else:
        what = f"the {frame} frame's premise"
        pokes = (_frame_pokes(what, spawn_armed=True) if frame == "plain"
                 else _busy_frame_pokes(what))
    contributed = _call_contributions(pokes, held=(frame == "held"))
    wrote = {name for name, count in contributed.items() if count}
    assert wrote == set(FRAME_CALLS_ALWAYS_WRITING) | set(extra), (
        f"the {frame} frame's writing calls are {sorted(wrote)}, not the ones it claims")
    assert set(FRAME_CALLS_NO_SEED_HERE_REACHES) <= set(contributed) - wrote, (
        "a call this battery records as unreached by any seed has started writing — which is good "
        "news and a table to update")


def test_a_BUSY_frame_runs_the_fifteen_calls_with_eleven_of_them_writing():
    """The frame the drop-a-call sweep is measured against: same composition, a seed that makes each
    call do something. `poison=False` for `flip_screen`'s reason."""
    what = "game_main_loop, a busy frame"
    info = _run_frame(what, _busy_frame_pokes(what), regions=BUSY_FRAME_REGIONS)
    assert info["ret"] == RETURNED
    assert info["regs"]["sched_site_arrivals"] == (1, 2)
    assert leaf.read_int(info, KEY_SEQUENCE_CURSOR, WORD, what) == 1, (
        f"{what}: game_key_actions did not step the cheat sequence")
    assert leaf.read_int(info, HUD_METER_VALUE, WORD, what) == FRAME_METER_VALUE - 1, (
        f"{what}: the round bonus did not drain a unit")


def test_a_PAUSED_frame_whose_key_is_still_held_runs_THREE_WAITS_IN_ONE_RUN():
    """THE REMEDY'S SHOWPIECE, and the case the model could not carry at all before this phase.

    The game is paused and the pause key is still down, so `game_unpause_on_key_release` spins on
    WB_KEY_LAST_SCANCODE at $64e until the IKBD stores the release — and then the SAME frame goes on
    to `flip_screen`, which spins twice more on WB_VBL_COUNTER. Three waits, three sites, two
    interrupts, one run. Under run TOTALS this could not be written: two trigger PCs were refused
    outright, and lifting that refusal without keying the counters would have let the three balance
    against each other.

    It also retires one of the sweep's drop-a-call survivors: with the unpause's payload in the frame,
    a port that dropped the loop's FIRST `bsr` leaves FOUR bytes unwritten — the scancode it forgets,
    the pause word it clears and the text request it posts. That count is measured rather than
    guessed, by the premise case above.
    """
    what = HELD_FRAME_CASE
    pokes = _held_frame_pokes(what)
    release_nth, tick_nth = HELD_RELEASE_NTH, FRAME_TICK_NTH
    info = leaf.run("game_main_loop", _loop_glue,
                    _bands(BUSY_FRAME_REGIONS) + [(KEY_LAST_SCANCODE, BYTE), (GAME_PAUSED, WORD)],
                    what, regs={"_pokes": pokes}, poison=False, max_insns=FRAME_INSN_CAP,
                    stop_pc=LOOP_BACKWARD_BRANCH,
                    schedule=[release(UNPAUSE_WAIT_PC, KEY_SCANCODE_P_RELEASE, release_nth)[0],
                              vbl_bump(FLIP_TICK_WAIT_PC, tick_nth, VBL_COUNTER_READY + 1)],
                    wait_sites=(UNPAUSE_WAIT_PC,) + FLIP_SITES)
    assert info["ret"] == RETURNED
    assert info["regs"]["sched_site_arrivals"] == (release_nth, 1, tick_nth), (
        f"{what}: the run's three waits ran {info['regs']['sched_site_arrivals']} iterations")
    assert leaf.read_int(info, GAME_PAUSED, WORD, what) == 0, f"{what}: the pause was not lifted"
    assert info["writes"][KEY_LAST_SCANCODE] == 0, f"{what}: the scancode was not forgotten"
    # ...AND THE FRAME RAN ON. A paused frame skips four calls; this one lifted the pause FIRST, so
    # the $66e test below the unpause reads the word the unpause has just cleared and all fifteen run.
    assert FRAME_TICK_B39A in info["writes"], (
        f"{what}: the gated block was skipped, so the unpause's clear did not reach the $66e test")
