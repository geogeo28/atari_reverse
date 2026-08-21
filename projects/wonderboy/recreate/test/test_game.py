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
                  cmp_b_abs_l_dn, cmp_b_imm_dn, cmpi_b_abs_l, jmp_abs_l, jsr_d16_an, lab,
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

# --- the two bodies, assembled ---------------------------------------------------------------------
# Both are pinned WHOLE rather than at their entry alone, because this battery's constants include
# two PROGRAM COUNTERS — the addresses the waits re-execute — and a schedule aimed at the wrong one
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

ENTRY_BYTES = {
    "game_key_actions": asm(KEY_ACTIONS_ENTRY, _key_actions_pieces()),
    "game_unpause_on_key_release": asm(UNPAUSE_ENTRY, _unpause_pieces()),
}
GAME_ROUTINE_COUNT = 2

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
    leaf.assert_batch_is_complete(ENTRY_BYTES, GAME_ROUTINE_COUNT)


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


def test_a_differential_refuses_a_schedule_naming_TWO_trigger_pcs():
    """`game_key_actions` has two waits, on the SAME byte, at $5e6 and $60e — so this routine is
    exactly where a case would reach for two entries, and the model cannot carry them.

    `nth` counts arrivals AT A PC on the oracle and POLLS on the candidate, which has no program
    counter; the two are the same event only while one wait is in play. With two, an entry aimed at
    the second wait fires on a poll of the first, and because both counters are run TOTALS the
    arrival/poll comparison can still agree. Refused before either core runs.
    """
    schedule = [{"pc": HELP_WAIT_PC, "nth": 1, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                 "value": KEY_SCANCODE_HELP_RELEASE},
                {"pc": PAUSE_WAIT_PC, "nth": 1, "addr": KEY_LAST_SCANCODE, "width": BYTE,
                 "value": KEY_SCANCODE_P_RELEASE}]
    with pytest.raises(AssertionError, match="different trigger PCs"):
        harness.differential(KEY_ACTIONS_ENTRY, {}, _key_actions, schedule=schedule)


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
SPINE_UNPORTED = (
    (0x4a0, "game_main_loop", 106),
    (0x50a, None, 52),                  # the follow-cursor fixup between $82f8 and $8f02
    (0x694, "flip_screen", 118),
    (0x716, "vbl_handler", 52),
    (0x882, None, 10),                  # `bsr joy1_latch_edge / bsr actor_behavior_pass / rts`
    (0x624c, "psg_set_drive_select", 28),
    (0x6268, "floppy_deselect_drives", 16),
    (0xe032, None, 118),                # the round-end sequence: the reader of $e1be
    (0xe0a8, None, 104),                # ...and its setup arm
)
SPINE_UNPORTED_BYTES = 604
SPINE_ROUTINES = 86                     # what the three roots reach, ported and not

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


def test_the_two_routines_this_phase_ported_left_the_unported_rows():
    """The phase's own arithmetic: 898 unported bytes before it, 604 after, and the difference is
    `game_key_actions`' 240 bytes of CODE plus `game_unpause_on_key_release`' 54 — not the 250-byte
    SPAN of the first, ten of which are the data block between its two halves."""
    key_actions_code = (SEQUENCE_DATA_START - KEY_ACTIONS_ENTRY) + (UNPAUSE_ENTRY - PAUSE_ARM_ENTRY)
    unpause_code = _extent(UNPAUSE_ENTRY)
    assert (key_actions_code, unpause_code) == (240, 54)
    assert SPINE_UNPORTED_BYTES + key_actions_code + unpause_code == 898
    for name in ("game_key_actions", "game_unpause_on_key_release"):
        assert leaf.entry_of(name) not in {row[0] for row in SPINE_UNPORTED}
