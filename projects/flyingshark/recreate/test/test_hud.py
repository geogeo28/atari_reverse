"""Differential tests for the score, the hall of fame and the readouts they feed (src/hud.c).

WHAT THESE ROUTINES ANSWER WITH, and why the cases are shaped the way they are. Almost everything in
this subsystem writes its answer into the image — packed BCD, glyph runs, six-byte display-list
slots — so the plain byte diff is the check and a case only has to stage the inputs. Three do not,
and each needs a stub from `abi.py` to make its answer visible:

  * `digits6_compare` @ 0x108f8 answers in D0 and advances A5/A6 — `register_call_pokes`;
  * `build_text_display_list` @ 0x10698 answers in A1/D1/D2 and WALKS A0, so A0 cannot be the result
    cursor either — `register_dump_pokes`;
  * `format_5_digits` @ 0x14a76 writes its digits into the image but leaves A0 where it stopped, and
    walks A0 to get there — `register_dump_pokes` again.

...and `score_add_bcd` @ 0x10bec answers in memory but READS the 68000's X flag, which no register
and no poke can set. Every score case therefore enters through `abi.extend_call_pokes`, which
borrows into X before the `jsr` and leaves the X the routine produced in D1 for the case to compare.

THE GLYPH ALPHABET is the game's own — 0xab..0xc4 = 'A'..'Z', 0xc5..0xce = '0'..'9', 0xcf = space —
so a "score" in these cases is six bytes from 0xc5 up, and a byte outside that run is what the
signed compares below turn on.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

MIRROR_HEADER = "include/hud.h"

# ---- entry points, as `fn` lines in ../names.txt ------------------------------------------------
ENTRY_BUILD_TEXT_DISPLAY_LIST = 0x10698
ENTRY_HISCORE_SHOW_ENTRY_SCREEN = 0x106f2
ENTRY_GAME_OVER_HISCORE_CHECK = 0x10724
ENTRY_HISCORE_INSERT_SCORE_AT_RANK = 0x1079c   # its tail, entered on its own so a case can
                                               # poke a rank the walk could never leave
ENTRY_HISCORE_SHIFT_ENTRY_DOWN = 0x108aa
ENTRY_HISCORE_RESET_LAST_DIGIT = 0x108c0
ENTRY_DIGITS6_COMPARE = 0x108f8
ENTRY_HUD_BUILD_LABELS = 0x10a02
ENTRY_CHECK_BEAT_HISCORE = 0x10a2a
ENTRY_HUD_BUILD_SCORE_DIGITS = 0x10a50
ENTRY_HUD_PUBLISH_DIGIT_ROW = 0x10a90
ENTRY_HUD_BLANK_LEADING_ZEROS = 0x10ab4
ENTRY_HUD_BLANK_LEADING_ZEROS_ROW = 0x10ac8
ENTRY_SCORES_BCD_TO_CHARS = 0x10ae4
ENTRY_BCD3_TO_DIGITS = 0x10b04
ENTRY_SCORE_ADD_50 = 0x10b28
ENTRY_SCORE_ADD_100 = 0x10b3c
ENTRY_SCORE_ADD_200 = 0x10b50
ENTRY_SCORE_ADD_250 = 0x10b64
ENTRY_SCORE_ADD_500 = 0x10b78
ENTRY_SCORE_ADD_1000 = 0x10b8c
ENTRY_SCORE_ADD_3000 = 0x10ba0
ENTRY_SCORE_ADD_5000 = 0x10bb4
ENTRY_SCORE_ADD_10000 = 0x10bd8
ENTRY_SCORE_ADD_BCD = 0x10bec
ENTRY_CHECK_CHEAT_NAME = 0x10d92
ENTRY_CHEAT_HSC_INVULNERABLE = 0x10e30
ENTRY_CHEAT_KDJ_INFINITE_LIVES = 0x10e4c
ENTRY_CHEAT_JGL_INFINITE_BOMBS = 0x10e56
ENTRY_CHEAT_GCC_ALT_GLYPH = 0x10e60
ENTRY_CHEAT_JH_MAX_WEAPON = 0x10e72
ENTRY_AWARD_EXTRA_LIFE = 0x110d4
ENTRY_DEBUG_PRINT_WORD_BINARY = 0x11570
ENTRY_CONSOLE_PUTC = 0x1159c
ENTRY_CLEAR_DISPLAY_LIST = 0x115a8
ENTRY_CLEAR_PLAYER_DISPLAY_SLOTS = 0x115c2
ENTRY_SCORE_RESET = 0x11616
ENTRY_CLEAR_3_BYTES = 0x1162e
ENTRY_HUD_PUBLISH_BOMB_AND_LIFE_ICONS = 0x123d8
ENTRY_DEBUG_SHOW_COUNTERS = 0x14960
ENTRY_CONSOLE_SHOW_MESSAGE = 0x14996
ENTRY_FORMAT_5_DIGITS = 0x14a76

# ---- the checkpoints the routines that never `rts` are diffed at --------------------------------
# `hiscore_show_entry_screen` ends `bra.w $10916`, falling into `hiscore_name_entry` (deferred).
STOP_HISCORE_NAME_ENTRY = 0x10916
# `award_extra_life`'s award arm ends `bra.w $121e6`, the sound module's sfx wrapper — an exit, so
# every byte it writes is already written when the checkpoint is reached.
STOP_SFX_EXTRA_LIFE = 0x121e6
# `debug_show_counters` FALLS THROUGH into `console_show_message`, whose own entry this is.
STOP_CONSOLE_SHOW_MESSAGE = 0x14996
# Both arms of `game_over_hiscore_check` end `bra.w $15754` — `main` past its two init calls.
STOP_MAIN_REENTRY = 0x15754

# ---- mirrors of include/hud.h -------------------------------------------------------------------
A_score_bcd = 0x15a2a
A_hiscore_bcd = 0x15a2d
SCORE_BCD_BYTES = 3
A_score_digits = 0x159f4
A_hiscore_digits = 0x159fa
SCORE_DIGITS = 6
A_score_award_values = 0x15a30
SCORE_AWARDS = 9
A_bonus_life_thresholds = 0x15a00
A_bonus_life_awarded_0 = 0x176c6
BONUS_LIFE_THRESHOLDS = 7
BONUS_LIFE_FLAG_BYTES = 2
A_lives = 0x17712
A_bombs = 0x17710
A_hiscore_table = 0x161dd
HISCORE_ENTRIES = 6
HISCORE_STRIDE = 22
HISCORE_NAME = 11
HISCORE_NAME_CHARS = 3
HISCORE_SCORE = 16
HISCORE_SHIFT_FROM = 9
HISCORE_SHIFT_BYTES = 13
HISCORE_LAST_DIGIT = 21
HISCORE_LOWEST_RANK = 5
SCORE_TIE_BREAK_GLYPH = 0xf0
A_hard_mode = 0x177cc
A_name_entry_done = 0x176dc
A_name_entry_timeout = 0x176de
A_hiscore_rank = 0x176e0
A_hiscore_beaten = 0x176e4
A_new_hiscore_pending = 0x176e8
A_const_words_0123 = 0x176ac
DIGITS_COMPARE_LOWER_OR_EQUAL = 0xffff
DIGITS_COMPARE_HIGHER = 0x0001
GLYPH_A = 0xab
GLYPH_ZERO = 0xc5
GLYPH_SPACE = 0xcf
DISPLAY_REC_BYTES = 6
DISPLAY_REC_FRAME = 4
DISPLAY_REC_ACTIVE = 5
A_hud_label_slots = 0x17ca8
A_hud_score_slots = 0x17cb4
A_hud_hiscore_slots = 0x17cd8
A_dl_bomb_icons = 0x17c36
A_dl_life_icons = 0x17c60
A_dl_player_shadow = 0x17cfc
HUD_DIGIT_SLOTS = 6
HUD_BLANKABLE_SLOTS = 5
HUD_ICON_SLOTS_CLEARED = 7
HUD_LIVES_SHOWN_MAX = 7
A_player = 0x190a4
PLAYER_MODE = 6
PLAYER_MODE_GAMEOVER = 4
A_cheat_handler_table = 0x191cc
A_cheat_name_table = 0x191e4
CHEAT_ROW_BYTES = 4
CHEAT_TABLE_END = 0x64
CHEAT_ARM_SPINS = 0x1389
CHEAT_ARM_KEY_BIT = 0
CHEAT_ARM_WAIT_PC = 0x10d9a
A_key_bits = 0x17780
A_cheat_used_flag = 0x176d4
A_title_word_easy = 0x16132
A_title_word_spam = 0x16136
TITLE_WORD_GLYPHS = 4
A_invuln_flag = 0x177c6
A_infinite_lives_flag = 0x177c7
A_infinite_bombs_flag = 0x177c8
A_alt_bullet_glyph_flag = 0x177c9
A_max_weapon_flag = 0x177ca
A_player_hit = 0x17706
LOW_MEMORY_INDENT_WORD = 0x40
A_text_hall_of_fame = 0x161ce
A_text_enter_your_name = 0x16262
TEXT_OP_SPACE = 0x00
TEXT_OP_TAB = 0x04
TEXT_OP_NEWLINE = 0x05
TEXT_OP_INDENT = 0x06
TEXT_OP_END = 0x09
TEXT_GLYPH_WIDTH = 8
TEXT_LINE_HEIGHT = 8
TEXT_TAB_WIDTH = 0x40
A_joy1_state = 0x1777f
JOY_FIRE_BIT = 7
FIRE_RELEASE_WAIT_PC = 0x149f0
FORMAT_DIGITS = 5
FORMAT_RADIX = 10
ASCII_ZERO = 0x30
ASCII_ONE = 0x31
ASCII_CR = 0x0d
BINARY_DUMP_BITS = 0x10
A_debug_map_advance_field = 0x14a05
A_debug_scroll_pos_field = 0x14a11
A_debug_scroll_fine_field = 0x14a1e
A_map_row_ptr = 0x16402
A_map_row_ptr_reset = 0x163fe
A_scroll_pos = 0x17758
A_scroll_fine = 0x16430
A_display_list = 0x177ce
A_display_list_end = 0x17d08
CONSOLE_TEXT_END = 0x80

# ---- the candidate's ABI ------------------------------------------------------------------------
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
_U32 = ctypes.c_uint32


def _declare(name, args, restype=None):
    fn = getattr(harness._lib, name)
    fn.argtypes = [_IMAGE, *args]
    fn.restype = restype
    return fn


SCORE_AWARD_GLUE = tuple(
    _declare(f"g_score_add_{value}", [_U32], _U32)
    for value in (50, 100, 200, 250, 500, 1000, 3000, 5000, 10000))
SCORE_AWARD_ENTRIES = (ENTRY_SCORE_ADD_50, ENTRY_SCORE_ADD_100, ENTRY_SCORE_ADD_200,
                       ENTRY_SCORE_ADD_250, ENTRY_SCORE_ADD_500, ENTRY_SCORE_ADD_1000,
                       ENTRY_SCORE_ADD_3000, ENTRY_SCORE_ADD_5000, ENTRY_SCORE_ADD_10000)

g_score_add_bcd = _declare("g_score_add_bcd", [_U32, _U32], _U32)
g_bcd3_to_digits = _declare("g_bcd3_to_digits", [_U32, _U32])
g_scores_bcd_to_chars = _declare("g_scores_bcd_to_chars", [])
g_score_reset = _declare("g_score_reset", [])
g_clear_3_bytes = _declare("g_clear_3_bytes", [_U32])
g_format_5_digits = _declare("g_format_5_digits", [_U32, _U32, _U32])
g_digits6_compare = _declare("g_digits6_compare", [_U32, _U32, _U32, _U32])
g_check_beat_hiscore = _declare("g_check_beat_hiscore", [])
g_award_extra_life = _declare("g_award_extra_life", [], _U32)
g_hud_publish_digit_row = _declare("g_hud_publish_digit_row", [_U32, _U32, _U32, _U32])
g_hud_build_score_digits = _declare("g_hud_build_score_digits", [])
g_hud_blank_leading_zeros_row = _declare("g_hud_blank_leading_zeros_row", [_U32])
g_hud_blank_leading_zeros = _declare("g_hud_blank_leading_zeros", [])
g_hud_build_labels = _declare("g_hud_build_labels", [])
g_hud_publish_bomb_and_life_icons = _declare("g_hud_publish_bomb_and_life_icons", [])
g_clear_display_list = _declare("g_clear_display_list", [])
g_clear_player_display_slots = _declare("g_clear_player_display_slots", [])
g_build_text_display_list = _declare("g_build_text_display_list", [_U32, _U32, _U32, _U32, _U32])
g_hiscore_shift_entry_down = _declare("g_hiscore_shift_entry_down", [_U32])
g_hiscore_reset_last_digit = _declare("g_hiscore_reset_last_digit", [])
g_hiscore_show_entry_screen = _declare("g_hiscore_show_entry_screen", [])
g_game_over_hiscore_check = _declare("g_game_over_hiscore_check", [])
g_hiscore_insert_score_at_rank = _declare("g_hiscore_insert_score_at_rank", [])
g_check_cheat_name = _declare("g_check_cheat_name", [_U32])
g_cheat_hsc_invulnerable = _declare("g_cheat_hsc_invulnerable", [])
g_cheat_kdj_infinite_lives = _declare("g_cheat_kdj_infinite_lives", [])
g_cheat_jgl_infinite_bombs = _declare("g_cheat_jgl_infinite_bombs", [])
g_cheat_gcc_alt_glyph = _declare("g_cheat_gcc_alt_glyph", [])
g_cheat_jh_max_weapon = _declare("g_cheat_jh_max_weapon", [])
g_console_putc = _declare("g_console_putc", [_U32])
g_debug_print_word_binary = _declare("g_debug_print_word_binary", [_U32])
g_console_show_message = _declare("g_console_show_message", [_U32])
g_debug_show_counters = _declare("g_debug_show_counters", [])

FUZZ_CHUNKS = 4
# A byte pattern the routines under test never write, poked over `abi.RESULT` so that a candidate
# which stored nothing there differs from an oracle whose stub did.
RESULT_CANARY = 0xa5
RESULT_LONGWORDS = 4


def _result_canary():
    return {abi.RESULT: bytes([RESULT_CANARY] * (RESULT_LONGWORDS * 4))}


def _run(entry, glue, pokes=None, regs=None, note="", **kwargs):
    """One differential case: stage `pokes`, enter at `entry`, and demand an empty diff."""
    run_regs = dict(regs or {})
    run_regs["_pokes"] = dict(pokes or {})
    diffs, info = differential(entry, run_regs, glue, **kwargs)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


# =================================================================================================
# score_add_bcd @ 0x10bec, and the nine wrappers @ 0x10b28 .. 0x10bd8
# =================================================================================================
#
# Every case here enters through `abi.extend_call_pokes`, whose stub sets X before the `jsr` (when
# asked) and leaves the X the routine produced in D1. So the ENTRY of the run is `abi.STUB` and the
# routine's own address is the stub's operand — which is also why these cases pin the wrappers'
# addresses rather than passing them as entries.

# The nine awards, as the three BCD bytes each `lea` selects, read straight out of the .PRG's data.
AWARD_VALUES = (0x000050, 0x000100, 0x000200, 0x000250, 0x000500,
                0x001000, 0x003000, 0x005000, 0x010000)


def _bcd3(value):
    """A 6-digit decimal as the three packed-BCD bytes the game stores."""
    return bytes(((value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff))


def _award_case(index, score, extend_in, poison=False):
    """One award wrapper, with X driven in and the X it left compared against the oracle's.

    The candidate's answer is captured from inside the glue with `setdefault`, so a poison pass —
    which runs the glue a second time — reports the FIRST run's flag rather than the poisoned one's.
    """
    entry = SCORE_AWARD_ENTRIES[index]
    pokes = {A_score_bcd: score, **abi.extend_call_pokes(entry, extend_in)}
    reported = {}
    info = _run(abi.STUB,
                lambda lib, buf: reported.setdefault("x", SCORE_AWARD_GLUE[index](buf, extend_in)),
                pokes=pokes, poison=poison,
                note=f"award={AWARD_VALUES[index]} score={score.hex()} X={extend_in}")
    assert reported["x"] == abi.oracle_extend(info), (
        f"award={AWARD_VALUES[index]} score={score.hex()} X_in={extend_in}: the oracle left "
        f"X={abi.oracle_extend(info)} and the reconstruction {reported['x']}")


@pytest.mark.parametrize("index", range(SCORE_AWARDS))
@pytest.mark.parametrize("extend_in", abi.BOTH_EXTENDS)
def test_every_award_from_a_fresh_score(index, extend_in):
    """Each of the nine wrappers picks its own value, and each is a different `lea`.

    Driven from zero, which is the score `score_reset` leaves and therefore the one every game
    starts on, and with X both ways because the first `abcd` adds it.
    """
    _award_case(index, _bcd3(0), extend_in)


@pytest.mark.parametrize("index", range(SCORE_AWARDS))
def test_every_award_carries_out_of_999999(index):
    """THE SCORE WRAPS. The carry out of the top BCD byte is dropped, so 999999 plus any award rolls
    over rather than saturating — which is the behaviour, not a bug to repair."""
    _award_case(index, _bcd3(0x999999), abi.EXTEND_CLEAR)


@pytest.mark.parametrize("score", (0x000000, 0x000050, 0x000099, 0x009950, 0x999950, 0x099999))
def test_the_carry_walks_up_the_three_bytes(score):
    """A carry out of the low byte has to reach the middle byte and then the top one, and these are
    the scores where each boundary is the next award's business."""
    _award_case(0, _bcd3(score), abi.EXTEND_CLEAR)


@pytest.mark.parametrize("extend_in", abi.BOTH_EXTENDS)
@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_random_scores_against_random_awards(chunk, extend_in):
    """Random three-byte accumulators against every award, sharded so `-n auto` spreads them.

    THE BYTES ARE NOT CONSTRAINED TO VALID BCD. A nibble above 9 is exactly where `abcd`'s correction
    order shows, and the oracle rather than src/hud.c's comment is the authority on what the
    instruction does with one — so the fuzz drives them and the reconstruction has to agree.
    """
    rng = random.Random(0x5c04e + chunk)
    for _ in range(24):
        score = bytes(rng.randrange(0x100) for _ in range(SCORE_BCD_BYTES))
        _award_case(rng.randrange(SCORE_AWARDS), score, extend_in)


@pytest.mark.parametrize("index", (0, SCORE_AWARDS - 1))
def test_award_attribution(index):
    """Poison the three score bytes: a candidate that wrote none of them would stay canary."""
    _award_case(index, _bcd3(0x012345), abi.EXTEND_CLEAR, poison=True)


def _add_bcd_case(score, addend, extend_in=abi.EXTEND_CLEAR):
    """The leaf itself, with A1 pointing one past a value the case put in scratch — the contract the
    nine wrappers use, and what lets a case choose an ADDEND the award table does not contain."""
    pokes = {A_score_bcd: bytes(score), abi.SCRATCH: bytes(addend),
             **abi.extend_call_pokes(ENTRY_SCORE_ADD_BCD, extend_in)}
    addend_end = abi.SCRATCH + len(addend)
    reported = {}
    info = _run(abi.STUB,
                lambda lib, buf: reported.setdefault("x", g_score_add_bcd(buf, addend_end,
                                                                         extend_in)),
                pokes=pokes, regs={"a1": addend_end},
                note=f"score={bytes(score).hex()} addend={bytes(addend).hex()} X={extend_in}")
    assert reported["x"] == abi.oracle_extend(info), (
        f"score={bytes(score).hex()} addend={bytes(addend).hex()} X_in={extend_in}: the oracle left "
        f"X={abi.oracle_extend(info)} and the reconstruction {reported['x']}")


@pytest.mark.parametrize("extend_in", abi.BOTH_EXTENDS)
def test_score_add_bcd_takes_its_addend_from_anywhere(extend_in):
    _add_bcd_case(_bcd3(0x098765), [0x12, 0x34, 0x56], extend_in)


# The byte pairs where `abcd`'s WRAP TEST is decided, which the nine fixed awards cannot reach: the
# corrected sum has to land exactly on 0x99 or 0xa0 for one comparison to differ from its neighbour,
# and on 0x9a for a `> 0x99` to differ from a `> 0x9a`. That needs a low-nibble pair summing past 9
# with high nibbles summing to 0x80, which no award in the table supplies (they are 0x00 and 0x01).
ABCD_WRAP_PAIRS = (
    (0x8a, 0x0a),   # low 10+10 -> +6 = 26; 26 + 0x80 = 0x9a: carries, and leaves 0xfa
    (0x4b, 0x49),   # the same 0x9a by another route
    (0x50, 0x49),   # 0x99 exactly: the largest sum that does NOT carry
    (0x50, 0x50),   # 0xa0 exactly: the smallest that does, and leaves 0x00
    (0x99, 0x01),   # valid BCD either side, and the carry the game's own awards produce
    (0x0f, 0x0f),   # both nibbles past 9 with nothing in the high half
    (0xff, 0xff),   # ...and both halves past 9 at once
)


@pytest.mark.parametrize("augend,addend", ABCD_WRAP_PAIRS)
@pytest.mark.parametrize("extend_in", abi.BOTH_EXTENDS)
def test_the_abcd_wrap_boundary(augend, addend, extend_in):
    """One `abcd` at a time, on the LOW byte, at each sum where the instruction's own thresholds are
    decided. Driven through the leaf because the award table has no byte that reaches them."""
    _add_bcd_case([0x00, 0x00, augend], [0x00, 0x00, addend], extend_in)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_random_addends_against_random_scores(chunk):
    """Both operands random over the whole byte range, sharded — which the wrapper fuzz above cannot
    do, its addends being the nine values in the .PRG's own table."""
    rng = random.Random(0xadde + chunk)
    for _ in range(24):
        _add_bcd_case([rng.randrange(0x100) for _ in range(SCORE_BCD_BYTES)],
                      [rng.randrange(0x100) for _ in range(SCORE_BCD_BYTES)],
                      rng.choice(abi.BOTH_EXTENDS))


# =================================================================================================
# bcd3_to_digits @ 0x10b04 / scores_bcd_to_chars @ 0x10ae4 / score_reset @ 0x11616
# =================================================================================================

BCD_SOURCE = abi.SCRATCH
BCD_DEST = abi.SCRATCH + 0x100


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_bcd3_to_digits_over_random_bytes(chunk):
    """Three arbitrary bytes to six glyphs, sharded. A nibble above 9 lands past '9' in the alphabet
    rather than being clamped, which is what `addi.b #$c5` does and what this pins."""
    rng = random.Random(0xbcd0 + chunk)
    cases = [bytes([0, 0, 0]), bytes([0x99, 0x99, 0x99]), bytes([0xff, 0xff, 0xff])]
    cases += [bytes(rng.randrange(0x100) for _ in range(SCORE_BCD_BYTES)) for _ in range(16)]
    for packed in cases[chunk::FUZZ_CHUNKS]:
        pokes = {BCD_SOURCE: packed, BCD_DEST: bytes([RESULT_CANARY] * SCORE_DIGITS)}
        _run(ENTRY_BCD3_TO_DIGITS,
             lambda lib, buf: g_bcd3_to_digits(buf, BCD_SOURCE, BCD_DEST),
             pokes=pokes, regs={"a0": BCD_SOURCE, "a1": BCD_DEST},
             note=f"packed={packed.hex()}")


@pytest.mark.parametrize("score,hiscore", (
    (0x000000, 0x250000), (0x123456, 0x000000), (0x999999, 0x999999), (0xabcdef, 0x0f0f0f)))
def test_scores_bcd_to_chars_does_both_readouts(score, hiscore):
    """Both conversions in one call, into the two adjacent glyph runs."""
    _run(ENTRY_SCORES_BCD_TO_CHARS, lambda lib, buf: g_scores_bcd_to_chars(buf),
         pokes={A_score_bcd: _bcd3(score) + _bcd3(hiscore)},
         note=f"score={score:#08x} hiscore={hiscore:#08x}")


def test_scores_bcd_to_chars_attribution():
    """Poison all twelve glyphs: a candidate that converted only the score stays canary on six."""
    _run(ENTRY_SCORES_BCD_TO_CHARS, lambda lib, buf: g_scores_bcd_to_chars(buf),
         pokes={A_score_bcd: _bcd3(0x135790) + _bcd3(0x246800)}, poison=True)


def test_score_reset_zeroes_the_bcd_and_leaves_one_digit_showing():
    """The five leading glyphs are deliberately NOT reset — only the sixth, which is what
    `hud_blank_leading_zeros` stops at."""
    _run(ENTRY_SCORE_RESET, lambda lib, buf: g_score_reset(buf),
         pokes={A_score_bcd: _bcd3(0x987654),
                A_score_digits: bytes([RESULT_CANARY] * SCORE_DIGITS)})


def test_clear_3_bytes_clears_exactly_three():
    """`score_reset`'s leaf, driven on scratch with a guard byte either side."""
    guarded = bytes([RESULT_CANARY] * 5)
    _run(ENTRY_CLEAR_3_BYTES, lambda lib, buf: g_clear_3_bytes(buf, BCD_SOURCE + 1),
         pokes={BCD_SOURCE: guarded}, regs={"a0": BCD_SOURCE + 1})


# =================================================================================================
# digits6_compare @ 0x108f8
# =================================================================================================

COMPARE_ENTRY = abi.SCRATCH + 0x200      # an "entry", whose score field is +16
COMPARE_SCORE = abi.SCRATCH + 0x300
# `move.w #$ffff,d0` leaves the caller's high half alone, so a case seeds one to prove it survives.
COMPARE_D0_HIGH = 0x1234


def _compare_case(entry_digits, score_digits, poison=False):
    pokes = {COMPARE_ENTRY + HISCORE_SCORE: bytes(entry_digits),
             COMPARE_SCORE: bytes(score_digits),
             **_result_canary(),
             **abi.register_call_pokes(ENTRY_DIGITS6_COMPARE, ("d0", "a5", "a6"))}
    d0 = COMPARE_D0_HIGH << 16
    _run(abi.STUB,
         lambda lib, buf: g_digits6_compare(buf, COMPARE_ENTRY, COMPARE_SCORE, d0, abi.RESULT),
         pokes=pokes,
         regs={"a0": abi.RESULT, "a5": COMPARE_ENTRY, "a6": COMPARE_SCORE, "d0": d0},
         poison=poison,
         note=f"entry={bytes(entry_digits).hex()} score={bytes(score_digits).hex()}")


def _digits(*values):
    return [GLYPH_ZERO + v for v in values]


def test_equal_scores_compare_as_lower():
    """ALL SIX EQUAL falls out of the `dbf` into the same `move.w #$ffff,d0` a LOWER digit takes, so
    a tie does not beat the table — which is what makes `game_over_hiscore_check`'s dead tie-break
    store matter, and what makes its absence cost the tie."""
    _compare_case(_digits(1, 2, 3, 4, 5, 6), _digits(1, 2, 3, 4, 5, 6))


@pytest.mark.parametrize("position", range(SCORE_DIGITS))
@pytest.mark.parametrize("direction", (-1, +1))
def test_the_first_differing_digit_decides(position, direction):
    """One digit apart at each of the six positions, each way. Every digit after the differing one is
    made to disagree the OTHER way, so a routine that kept walking would answer differently."""
    base = _digits(5, 5, 5, 5, 5, 5)
    score = list(base)
    score[position] += direction
    for later in range(position + 1, SCORE_DIGITS):
        score[later] -= direction
    _compare_case(base, score)


def test_the_compare_is_signed():
    """`blt`/`bgt` read the byte as two's complement. Every digit glyph is negative, so a POSITIVE
    byte in the entry — which is what the front end's text below the hall-of-fame table is made of —
    makes the score read as LOWER. That is what stops `game_over_hiscore_check`'s rank walk one step
    after it falls off the bottom of the table."""
    _compare_case([0x00] * SCORE_DIGITS, _digits(9, 9, 9, 9, 9, 9))
    _compare_case([0x7f] * SCORE_DIGITS, _digits(0, 0, 0, 0, 0, 0))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_compare_over_random_digit_pairs(chunk):
    """Random glyph runs on both sides, sharded — including bytes outside the digit run, where the
    signed compare is the whole answer."""
    rng = random.Random(0xc0117 + chunk)

    def six_bytes():
        """Six bytes, half of them real digit glyphs and half anything at all."""
        return [rng.randrange(GLYPH_ZERO, GLYPH_ZERO + 10) if rng.random() < 0.5
                else rng.randrange(0x100) for _ in range(SCORE_DIGITS)]

    for _ in range(12):
        _compare_case(six_bytes(), six_bytes())


def test_compare_attribution():
    """Poison the three longwords the stub stores: a candidate that recorded none stays canary."""
    _compare_case(_digits(1, 1, 1, 1, 1, 1), _digits(2, 2, 2, 2, 2, 2), poison=True)


# =================================================================================================
# check_beat_hiscore @ 0x10a2a
# =================================================================================================

def _beat_case(score, hiscore, beaten=0, poison=False):
    pokes = {A_score_digits: bytes(score) + bytes(hiscore),
             A_hiscore_beaten: beaten.to_bytes(2, "big")}
    _run(ENTRY_CHECK_BEAT_HISCORE, lambda lib, buf: g_check_beat_hiscore(buf), pokes=pokes,
         poison=poison,
         note=f"score={bytes(score).hex()} hiscore={bytes(hiscore).hex()} beaten={beaten:#06x}")


@pytest.mark.parametrize("position", range(SCORE_DIGITS))
def test_a_higher_digit_anywhere_raises_the_flag(position):
    base = _digits(4, 4, 4, 4, 4, 4)
    score = list(base)
    score[position] += 1
    _beat_case(score, base)


@pytest.mark.parametrize("position", range(SCORE_DIGITS))
def test_a_lower_digit_anywhere_leaves_the_flag(position):
    base = _digits(4, 4, 4, 4, 4, 4)
    score = list(base)
    score[position] -= 1
    _beat_case(score, base)


def test_a_tie_leaves_the_flag_alone():
    _beat_case(_digits(7, 7, 7, 7, 7, 7), _digits(7, 7, 7, 7, 7, 7))


def test_the_flag_is_a_byte_store_into_a_word():
    """`st $176e4` writes ONE byte, and `hud_build_score_digits` reads the WORD — so the low byte of
    `hiscore_beaten` keeps whatever was there. Seeded non-zero to prove the reconstruction leaves it
    rather than clearing the word."""
    _beat_case(_digits(9, 0, 0, 0, 0, 0), _digits(0, 0, 0, 0, 0, 0), beaten=0x0042)


def test_beat_hiscore_attribution():
    _beat_case(_digits(9, 9, 9, 9, 9, 9), _digits(0, 0, 0, 0, 0, 0), poison=True)


# =================================================================================================
# award_extra_life @ 0x110d4
# =================================================================================================
#
# TWO CHECKPOINT SHAPES, because the routine has two exits: an `rts` when nothing is awarded, and a
# `bra.w $121e6` into the sound module when something is. A case says which it expects, and the glue
# returns the same answer — so an arm taken on one side and not the other fails by shape rather than
# by bytes.

# The seven thresholds, as ../out/prg_dis.txt's data and ../notes/frontend.md both give them.
BONUS_LIFE_SCORES = (50000, 200000, 350000, 500000, 650000, 800000, 950000)


def _bcd_of_decimal(value):
    return _bcd3(int(f"{value:06d}", 16))


def _extra_life_case(score, flags, lives=3, expect_award=True, poison=False):
    pokes = {A_score_bcd: _bcd_of_decimal(score),
             A_bonus_life_awarded_0: b"".join(f.to_bytes(BONUS_LIFE_FLAG_BYTES, "big")
                                              for f in flags),
             A_lives: lives.to_bytes(2, "big")}
    info = _run(ENTRY_AWARD_EXTRA_LIFE, lambda lib, buf: g_award_extra_life(buf), pokes=pokes,
                stop_pc=STOP_SFX_EXTRA_LIFE if expect_award else 0, poison=poison,
                note=f"score={score} flags={flags} lives={lives}")
    assert bool(info["ret"]) == expect_award, (
        f"score={score} flags={flags}: the reconstruction says the sound tail-call "
        f"{'happens' if info['ret'] else 'does not happen'} and the case expected the other")


@pytest.mark.parametrize("row", range(BONUS_LIFE_THRESHOLDS))
def test_each_threshold_awards_once_when_its_flag_is_clear(row):
    """Row `row` is the first unclaimed one, and the score is exactly at it — which does NOT award,
    because an equal comparison answers "lower or equal". One point past it does."""
    flags = [1] * row + [0] * (BONUS_LIFE_THRESHOLDS - row)
    _extra_life_case(BONUS_LIFE_SCORES[row], flags, expect_award=False)
    _extra_life_case(BONUS_LIFE_SCORES[row] + 10, flags, expect_award=True)


@pytest.mark.parametrize("row", range(BONUS_LIFE_THRESHOLDS))
def test_a_score_below_the_first_unclaimed_threshold_awards_nothing(row):
    flags = [1] * row + [0] * (BONUS_LIFE_THRESHOLDS - row)
    _extra_life_case(BONUS_LIFE_SCORES[row] - 10, flags, expect_award=False)


def test_every_flag_set_compares_nothing_at_all():
    """With all seven claimed the routine falls off the last `tst.w` straight into its `rts`."""
    _extra_life_case(999990, [1] * BONUS_LIFE_THRESHOLDS, expect_award=False)


def test_only_the_first_unclaimed_threshold_is_ever_taken():
    """A score past several thresholds still collects ONE life, and it is the lowest unclaimed
    row's — which is why a big single award leaves the rest for later calls."""
    _extra_life_case(999990, [0] * BONUS_LIFE_THRESHOLDS, expect_award=True)


@pytest.mark.parametrize("lives", (0, 1, 7, 0x7fff, 0xffff))
def test_the_life_count_is_a_word_add_that_can_wrap(lives):
    """`addi.w #$1,$17712` with no ceiling: 0x7fff goes negative and 0xffff wraps to zero."""
    _extra_life_case(999990, [0] * BONUS_LIFE_THRESHOLDS, lives=lives, expect_award=True)


def test_extra_life_attribution():
    _extra_life_case(999990, [0] * BONUS_LIFE_THRESHOLDS, poison=True)


# =================================================================================================
# format_5_digits @ 0x14a76
# =================================================================================================

FORMAT_FIELD = abi.SCRATCH + 0x400
FORMAT_GUARD = 4


def _format_case(value, poison=False):
    pokes = {FORMAT_FIELD - FORMAT_GUARD: bytes([RESULT_CANARY] * (FORMAT_DIGITS + 2 * FORMAT_GUARD)),
             **_result_canary(),
             **abi.register_dump_pokes(ENTRY_FORMAT_5_DIGITS, ("d0", "a0"))}
    _run(abi.STUB, lambda lib, buf: g_format_5_digits(buf, FORMAT_FIELD, value, abi.RESULT),
         pokes=pokes, regs={"a0": FORMAT_FIELD, "d0": value}, poison=poison,
         note=f"value={value:#010x}")


@pytest.mark.parametrize("value", (0, 1, 9, 10, 99, 100, 9999, 10000, 65535))
def test_format_5_digits_at_every_digit_count(value):
    """Zero writes no digits at all and leaves "00000"; 65535 fills the field exactly."""
    _format_case(value)


@pytest.mark.parametrize("value", (0x00010000, 0x1234_0000, 0xffff_0000, 0xdead_beef))
def test_the_high_word_is_thrown_away_before_the_first_divide(value):
    """`swap / clr.w / swap` masks D0 to 16 bits, so a longword argument is taken modulo 65536 —
    which is what `debug_show_counters` hands it and why five digits is enough."""
    _format_case(value)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_format_5_digits_fuzz(chunk):
    rng = random.Random(0xf0f0 + chunk)
    for _ in range(20):
        _format_case(rng.randrange(1 << 32))


def test_format_5_digits_attribution():
    """Poison the field and the two dumped longwords: a candidate that filled the zeros but never
    divided would stay canary on the digits it should have overwritten."""
    _format_case(54321, poison=True)


# =================================================================================================
# The readouts: hud_publish_digit_row / hud_build_score_digits / hud_blank_leading_zeros
# =================================================================================================

ROW_GLYPHS = abi.SCRATCH + 0x500
ROW_SLOTS = abi.SCRATCH + 0x600
ROW_GUARD = DISPLAY_REC_BYTES


def _digit_row_case(glyphs, x, y, poison=False):
    pokes = {ROW_GLYPHS: bytes(glyphs),
             ROW_SLOTS - ROW_GUARD: bytes([RESULT_CANARY] * ((HUD_DIGIT_SLOTS + 2) * DISPLAY_REC_BYTES))}
    _run(ENTRY_HUD_PUBLISH_DIGIT_ROW,
         lambda lib, buf: g_hud_publish_digit_row(buf, ROW_GLYPHS, ROW_SLOTS, x, y),
         pokes=pokes, regs={"a0": ROW_GLYPHS, "a1": ROW_SLOTS, "d1": x, "d2": y}, poison=poison,
         note=f"glyphs={bytes(glyphs).hex()} x={x:#x} y={y:#x}")


def test_the_sixth_digit_slot_is_a_literal_zero():
    """The row's own sixth glyph is never published: the tail block writes '0' whatever it was, which
    is why every score on screen ends in a zero."""
    _digit_row_case(_digits(1, 2, 3, 4, 5, 6), 0x50, 0x0c)


@pytest.mark.parametrize("x", (0, 0x50, 0xc0, 0xffd0, 0xfff8))
def test_the_column_steps_by_eight_and_wraps_in_a_word(x):
    """`addi.w #$8,d1` is a WORD add, so a column near 0xffff wraps rather than carrying into the
    high half of the register the caller supplied."""
    _digit_row_case(_digits(0, 0, 0, 0, 0, 0), x, 0x0c)


@pytest.mark.parametrize("d1,d2", ((0x1234_0050, 0x5678_000c), (0xffff_0000, 0xffff_0000)))
def test_only_the_low_word_of_the_coordinates_is_published(d1, d2):
    """`move.w d1,(a1)+` writes the low word and the high half never reaches the slot."""
    _digit_row_case(_digits(9, 8, 7, 6, 5, 4), d1, d2)


def test_digit_row_attribution():
    _digit_row_case(_digits(1, 2, 3, 4, 5, 6), 0x50, 0x0c, poison=True)


def _build_score_case(score, hiscore, beaten, poison=False):
    pokes = {A_score_digits: bytes(score) + bytes(hiscore),
             A_hiscore_beaten: beaten.to_bytes(2, "big"),
             A_hud_score_slots: bytes([RESULT_CANARY] * (A_display_list_end - A_hud_score_slots))}
    _run(ENTRY_HUD_BUILD_SCORE_DIGITS, lambda lib, buf: g_hud_build_score_digits(buf), pokes=pokes,
         poison=poison, note=f"beaten={beaten:#06x}")


@pytest.mark.parametrize("beaten", (0x0000, 0x00ff, 0xff00, 0xffff, 0x0001))
def test_once_the_hiscore_is_beaten_both_readouts_show_the_score(beaten):
    """The flag is tested as a WORD although `check_beat_hiscore` only ever writes its high byte, so
    a low byte alone is enough to switch the source — which the game itself never produces and a
    stray write would."""
    _build_score_case(_digits(1, 2, 3, 4, 5, 6), _digits(9, 8, 7, 6, 5, 4), beaten)


def test_build_score_digits_attribution():
    _build_score_case(_digits(1, 2, 3, 4, 5, 6), _digits(9, 8, 7, 6, 5, 4), 0, poison=True)


def _blank_row_pokes(glyphs, slots):
    """Six slots at `slots`, enabled, carrying `glyphs`."""
    row = bytearray()
    for glyph in glyphs:
        row += (0x0050).to_bytes(2, "big") + (0x000c).to_bytes(2, "big") + bytes([glyph, 1])
    return {slots: bytes(row)}


@pytest.mark.parametrize("leading", range(HUD_DIGIT_SLOTS + 1))
def test_blanking_stops_at_the_first_non_zero_digit(leading):
    """`leading` zeros then a non-zero, at every position — including all six, where the walk runs out
    at five and leaves the sixth slot enabled."""
    glyphs = [GLYPH_ZERO] * leading + [GLYPH_ZERO + 1] * (HUD_DIGIT_SLOTS - leading)
    _run(ENTRY_HUD_BLANK_LEADING_ZEROS_ROW,
         lambda lib, buf: g_hud_blank_leading_zeros_row(buf, A_hud_score_slots),
         pokes=_blank_row_pokes(glyphs, A_hud_score_slots), regs={"a1": A_hud_score_slots},
         note=f"leading={leading}")


def test_the_blanker_never_reaches_the_sixth_slot():
    """Five is the `dbf` count, so the forced trailing '0' always stays enabled and a score of
    nothing still shows one digit."""
    pokes = _blank_row_pokes([GLYPH_ZERO] * HUD_DIGIT_SLOTS, A_hud_score_slots)
    _run(ENTRY_HUD_BLANK_LEADING_ZEROS_ROW,
         lambda lib, buf: g_hud_blank_leading_zeros_row(buf, A_hud_score_slots),
         pokes=pokes, regs={"a1": A_hud_score_slots})


@pytest.mark.parametrize("score_leading,hiscore_leading", ((0, 0), (3, 5), (5, 0), (2, 4)))
def test_blank_leading_zeros_does_both_readouts(score_leading, hiscore_leading):
    pokes = {}
    for leading, slots in ((score_leading, A_hud_score_slots),
                           (hiscore_leading, A_hud_hiscore_slots)):
        glyphs = [GLYPH_ZERO] * leading + [GLYPH_ZERO + 3] * (HUD_DIGIT_SLOTS - leading)
        pokes.update(_blank_row_pokes(glyphs, slots))
    _run(ENTRY_HUD_BLANK_LEADING_ZEROS, lambda lib, buf: g_hud_blank_leading_zeros(buf),
         pokes=pokes, note=f"{score_leading}/{hiscore_leading}")


def test_hud_build_labels():
    """Two fixed slots, written once. Poisoned, because the whole routine is eight stores and a
    candidate that made none of them would otherwise be compared against a zeroed display list."""
    _run(ENTRY_HUD_BUILD_LABELS, lambda lib, buf: g_hud_build_labels(buf),
         pokes={A_hud_label_slots: bytes([RESULT_CANARY] * (2 * DISPLAY_REC_BYTES))}, poison=True)


# =================================================================================================
# clear_display_list @ 0x115a8 / clear_player_display_slots @ 0x115c2
# =================================================================================================

def test_clear_display_list_clears_exactly_the_list():
    """0x177ce..0x17d07, with a guard slot either side that must survive."""
    guard = DISPLAY_REC_BYTES
    span = A_display_list_end - A_display_list + 2 * guard
    _run(ENTRY_CLEAR_DISPLAY_LIST, lambda lib, buf: g_clear_display_list(buf),
         pokes={A_display_list - guard: bytes([RESULT_CANARY] * span)}, poison=True)


def test_clear_player_display_slots_clears_the_players_two_slots():
    """The address settles what the twelve bytes are: 0x17cfc is `dl_player_shadow`, so they are the
    PLAYER's own two records and not the score's — which is what ../names.txt's merged
    `clear_player_display_slots` now says, over the "score slots" the old name claimed."""
    guard = DISPLAY_REC_BYTES
    _run(ENTRY_CLEAR_PLAYER_DISPLAY_SLOTS, lambda lib, buf: g_clear_player_display_slots(buf),
         pokes={A_dl_player_shadow - guard: bytes([RESULT_CANARY] * (4 * DISPLAY_REC_BYTES))},
         poison=True)


# =================================================================================================
# hud_publish_bomb_and_life_icons @ 0x123d8
# =================================================================================================

# Where the two rows end if nothing overruns them, plus room for the overruns that do.
ICON_SPAN = A_display_list_end - A_dl_bomb_icons


# The unbounded life loop makes 0x10000 passes of a nine-instruction body, so the cases that drive it
# need a cap well past the harness default. Sized for that loop and nothing larger, so a
# reconstruction that ran away still hits a ceiling.
ICON_OVERRUN_MAX_INSNS = 1_500_000


def _icons_case(bombs, lives, mode=0, poison=False, max_insns=200_000):
    pokes = {A_bombs: bombs.to_bytes(2, "big") + lives.to_bytes(2, "big"),
             A_player + PLAYER_MODE: bytes([mode]),
             A_dl_bomb_icons: bytes([RESULT_CANARY] * ICON_SPAN)}
    _run(ENTRY_HUD_PUBLISH_BOMB_AND_LIFE_ICONS,
         lambda lib, buf: g_hud_publish_bomb_and_life_icons(buf), pokes=pokes, poison=poison,
         max_insns=max_insns, note=f"bombs={bombs} lives={lives} mode={mode}")


@pytest.mark.parametrize("bombs", range(HUD_ICON_SLOTS_CLEARED + 1))
@pytest.mark.parametrize("lives", (1, 3, HUD_ICON_SLOTS_CLEARED))
def test_the_icon_rows_at_every_count_the_game_produces(bombs, lives):
    """Zero to seven bombs against the life counts the game can hold. Zero bombs is the `bmi` arm and
    draws none; every other count fills that many slots leftward from 0x130."""
    _icons_case(bombs, lives)


# Bomb counts past the seven slots the row clears. The game's own cap is six (`item_pickup_award`
# stops the pickup AT BOMBS_FULL), so every one of these is CONTRACT COVERAGE.
BOMB_COUNTS_PAST_THE_ROW = (8, 0x20, 0x100)
# ...and the two counts that show what the row's ONE guard really tests. 0xffff decrements to -2 and
# is refused; 0x8000 decrements to 0x7fff and is NOT, so it draws 32,768 icons where a "is the count
# zero or negative" reading would draw none.
BOMB_COUNTS_EITHER_SIDE_OF_THE_GUARD = (0x8000, 0xffff)


@pytest.mark.parametrize("bombs", BOMB_COUNTS_PAST_THE_ROW)
def test_a_bomb_count_past_seven_walks_off_the_end_of_the_row(bombs):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    The bomb row clears SEVEN enable bytes and then publishes `bombs` icons with no bound of its
    own — the same missing clamp as the life row's, minus the `bmi` that saves the zero case. Any
    count above seven writes six-byte records straight on past `dl_bomb_icons` into whatever
    follows it in the display list. `item_pickup_award` @ 0x11714 stops the counter at six, so only
    a poked count reaches this, and it is the STATUS row's claim made falsifiable.
    """
    _icons_case(bombs, 3, max_insns=ICON_OVERRUN_MAX_INSNS)


@pytest.mark.parametrize("bombs", BOMB_COUNTS_EITHER_SIDE_OF_THE_GUARD)
def test_the_bomb_rows_guard_is_a_sign_test_on_the_DECREMENTED_count(bombs):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    The row's one guard is `subi.w #$1,d7 / bmi` @ 0x12414, which tests the SIGN OF THE DECREMENT
    and not the count. The two values here fall on opposite sides of that distinction: 0xffff
    decrements to -2 and draws nothing, while 0x8000 decrements to 0x7fff and draws 32,768 icons —
    where a candidate reading the guard as "zero or negative draws none" would draw none for both.
    """
    _icons_case(bombs, 3, max_insns=ICON_OVERRUN_MAX_INSNS)


@pytest.mark.parametrize("lives", (HUD_LIVES_SHOWN_MAX, 8, 0x100, 0x7fff))
def test_the_life_count_is_clamped_to_seven_and_written_back(lives):
    """`cmp.w #$7,d7 / blt` is a SIGNED compare, and the clamp is stored back into `lives` — so the
    readout does not merely draw seven, it changes the game's own counter.

    Seven itself is included for the boundary, and it is the one value at which the `>=` cannot be
    told from a `>`: the clamp stores seven over seven. STATUS.md records that mutation as
    equivalent."""
    _icons_case(4, lives)


def test_zero_lives_publishes_sixty_five_thousand_icons():
    """THE MISSING GUARD. The bomb loop has a `bmi` and the life loop does not, and `dbf` runs its
    body before it looks — so `lives = 0` makes 0x10000 passes and walks the icon row all the way up
    through the display list and out of it. The game reaches this only in the window before the
    death handler sets the game-over mode, which is what has kept it unnoticed. Reproduced."""
    _icons_case(2, 0, max_insns=ICON_OVERRUN_MAX_INSNS)


# The 0xffff extreme alone. Its sibling 0xfff9 ran the same two arms — escape the signed clamp,
# then `dbf` from 0xfffe — for 65,530 more oracle instructions and no mutation of its own; STATUS.md
# names none that only it kills. One case, and it is the one that is furthest from the clamp.
LIFE_COUNT_BELOW_THE_CLAMP = 0xffff


def test_a_negative_life_count_is_below_the_clamp_and_runs_the_long_way():
    """A negative word is BELOW seven under a signed compare, so it escapes the clamp and then makes
    almost the full 65,536 passes."""
    _icons_case(1, LIFE_COUNT_BELOW_THE_CLAMP, max_insns=ICON_OVERRUN_MAX_INSNS)


def test_the_game_over_mode_skips_both_rows():
    """Mode 4 clears the player's own two slots instead of the bombs, and then returns before the
    life row is touched at all."""
    _icons_case(5, 3, mode=PLAYER_MODE_GAMEOVER)


@pytest.mark.parametrize("mode", (0, 1, 2, 3, 5, 0xff))
def test_every_other_mode_publishes_both_rows(mode):
    _icons_case(3, 2, mode=mode)


def test_icons_attribution():
    _icons_case(3, 2, poison=True)


# =================================================================================================
# build_text_display_list @ 0x10698
# =================================================================================================

TEXT_SCRIPT = abi.SCRATCH + 0x700
TEXT_DEST = abi.SCRATCH + 0x800
TEXT_DEST_BYTES = 0x200
INDENT_WORD = 0x0018


def _text_case(script, x=0, y=0, indent=INDENT_WORD, poison=False):
    pokes = {TEXT_SCRIPT: bytes(script),
             TEXT_DEST: bytes([RESULT_CANARY] * TEXT_DEST_BYTES),
             LOW_MEMORY_INDENT_WORD: indent.to_bytes(2, "big"),
             **_result_canary(),
             **abi.register_dump_pokes(ENTRY_BUILD_TEXT_DISPLAY_LIST, ("d1", "d2", "a0", "a1"))}
    _run(abi.STUB,
         lambda lib, buf: g_build_text_display_list(buf, TEXT_SCRIPT, TEXT_DEST, x, y, abi.RESULT),
         pokes=pokes, regs={"a0": TEXT_SCRIPT, "a1": TEXT_DEST, "d1": x, "d2": y}, poison=poison,
         note=f"script={bytes(script).hex()} x={x:#x} y={y:#x} indent={indent:#x}")


def test_a_script_that_ends_immediately():
    """Two header bytes and a terminator: no slot at all, and the cursors still come back moved."""
    _text_case([0x10, 0x20, TEXT_OP_END])


def test_every_opcode_in_one_script():
    _text_case([0x08, 0x10,
                GLYPH_A, TEXT_OP_SPACE, GLYPH_A + 1, TEXT_OP_TAB, GLYPH_A + 2,
                TEXT_OP_NEWLINE, GLYPH_A + 3, TEXT_OP_INDENT, GLYPH_A + 4, TEXT_OP_END])


@pytest.mark.parametrize("indent", (0, 1, 0x0018, 0x7fff, 0x8000, 0xffff))
def test_the_indent_opcode_reads_absolute_address_0x40(indent):
    """THE BUG. Opcode 0x06 is `add.w $40.l,d1` — the 68000 vector page, not this program's data.
    Nothing in the game writes it, so a script using the opcode indents by whatever the operating
    system left there; the harness's image holds zero and this drives what a real machine would."""
    _text_case([0x00, 0x00, TEXT_OP_INDENT, GLYPH_A, TEXT_OP_END], indent=indent)


def test_the_header_bytes_land_in_the_low_byte_of_the_callers_register():
    """`move.b (a0)+,d1`, not `moveq`: the high BYTE of the caller's word survives into the slot.
    Every caller in the shipped binary clears the registers first, so this is what the instruction
    stream says rather than what the game does."""
    _text_case([0x08, 0x10, GLYPH_A, TEXT_OP_END], x=0xdead_ff00, y=0xbeef_ff00)


def test_a_newline_resets_the_column_to_zero_not_to_the_scripts_start():
    _text_case([0x40, 0x08, GLYPH_A, TEXT_OP_NEWLINE, GLYPH_A + 1, TEXT_OP_END])


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_random_scripts(chunk):
    """Random opcode streams, always terminated, sharded. Glyph bytes are drawn from the whole byte
    range because the compiler's `default` arm emits ANY byte it does not recognise as a slot."""
    rng = random.Random(0x7e47 + chunk)
    opcodes = (TEXT_OP_SPACE, TEXT_OP_TAB, TEXT_OP_NEWLINE, TEXT_OP_INDENT)
    for _ in range(10):
        body = [rng.choice(opcodes) if rng.random() < 0.3 else rng.randrange(0x100)
                for _ in range(rng.randrange(1, 24))]
        script = [rng.randrange(0x100), rng.randrange(0x100)]
        script += [b for b in body if b != TEXT_OP_END] + [TEXT_OP_END]
        _text_case(script, x=rng.randrange(1 << 16), y=rng.randrange(1 << 16),
                   indent=rng.randrange(1 << 16))


def test_text_script_attribution():
    _text_case([0x08, 0x10, GLYPH_A, GLYPH_A + 1, GLYPH_A + 2, TEXT_OP_END], poison=True)


# =================================================================================================
# The hall of fame: hiscore_shift_entry_down / hiscore_reset_last_digit / hiscore_show_entry_screen
# =================================================================================================

def _hiscore_table_pokes(fill=None):
    """The whole table, either as the .PRG ships it or filled with a recognisable pattern."""
    if fill is None:
        return {}
    return {A_hiscore_table: bytes(fill)}


@pytest.mark.parametrize("entry", range(HISCORE_ENTRIES - 1))
def test_shifting_a_row_moves_thirteen_bytes_from_plus_nine(entry):
    """The two spaces, the three name glyphs, two more spaces and the six score glyphs — and NOT the
    leading script bytes or the rank digit at +8, which is why the rows keep numbering themselves."""
    pattern = bytes((0x40 + i) & 0xff for i in range(HISCORE_ENTRIES * HISCORE_STRIDE))
    address = A_hiscore_table + entry * HISCORE_STRIDE
    _run(ENTRY_HISCORE_SHIFT_ENTRY_DOWN,
         lambda lib, buf: g_hiscore_shift_entry_down(buf, address),
         pokes=_hiscore_table_pokes(pattern), regs={"a0": address}, poison=True,
         note=f"entry={entry}")


def test_reset_last_digit_stamps_every_row():
    pattern = bytes([RESULT_CANARY] * (HISCORE_ENTRIES * HISCORE_STRIDE))
    _run(ENTRY_HISCORE_RESET_LAST_DIGIT, lambda lib, buf: g_hiscore_reset_last_digit(buf),
         pokes=_hiscore_table_pokes(pattern), poison=True)


@pytest.mark.parametrize("name_entry_done", (0, 1, 0xffff))
def test_the_hall_of_fame_page_compiles_both_scripts(name_entry_done):
    """The SLICE [0x106f2, 0x10916). With `name_entry_done` clear the "ENTER YOUR NAME" script is
    compiled straight on to the end of the first one, which is the whole reason
    `build_text_display_list` returns its cursors."""
    pokes = {A_name_entry_done: name_entry_done.to_bytes(2, "big"),
             A_display_list: bytes([RESULT_CANARY] * (A_display_list_end - A_display_list))}
    _run(ENTRY_HISCORE_SHOW_ENTRY_SCREEN, lambda lib, buf: g_hiscore_show_entry_screen(buf),
         pokes=pokes, stop_pc=STOP_HISCORE_NAME_ENTRY, note=f"done={name_entry_done:#x}")


# =================================================================================================
# game_over_hiscore_check @ 0x10724
# =================================================================================================

# The six glyphs 22 bytes BELOW the table, which are `text_hall_of_fame`'s own script bytes and
# which the rank walk reads when it runs off the bottom. A case that wants the walk to keep going
# pokes them; every other case leaves the script alone.
A_below_the_table = A_hiscore_table - HISCORE_STRIDE + HISCORE_SCORE


def _game_over_case(score, table=None, below=None, note=""):
    """The SLICE [0x10724, 0x15754): both arms end by re-entering `main`, so that is the checkpoint.

    `hard_mode` is seeded NON-ZERO in every case, because the routine's first instruction clears it
    and the byte is zero in the post-load image — a candidate that dropped the store would otherwise
    be compared against a zero it never had to write.
    """
    pokes = {A_score_bcd: _bcd_of_decimal(score), A_hard_mode: b"\xff"}
    if table is not None:
        pokes[A_hiscore_table] = bytes(table)
    if below is not None:
        pokes[A_below_the_table] = bytes(below)
    _run(ENTRY_GAME_OVER_HISCORE_CHECK, lambda lib, buf: g_game_over_hiscore_check(buf),
         pokes=pokes, stop_pc=STOP_MAIN_REENTRY, note=note or f"score={score}")


# Ranks the dispatch at 0x1079c has to answer for, one arm each plus the fall-through. Its caller
# can only reach 5 and below (it writes 5 and its walk decrements), so 6 and 7 are CONTRACT COVERAGE:
# they exist to separate the original's five-way `cmp.w`/`beq` chain from a `rank < 5` guard.
HISCORE_DISPATCH_RANKS = (-1, 0, 1, 2, 3, 4, 5, 6, 7)


@pytest.mark.parametrize("rank", HISCORE_DISPATCH_RANKS)
def test_the_hiscore_rank_dispatch_shifts_five_rows_for_every_rank_it_has_no_arm_for(rank):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, for ranks 6 and 7, and ../STATUS.md says so.

    The insert is a DISPATCH: `cmp.w #$5,d4 / beq` and four more @ 0x1079c..0x107c4, then a plain
    `bra` @ 0x107c6. Rank 5 shifts nothing, each lower rank one more row — and the fall-through arm
    takes everything the five `cmp.w`s missed, which is rank 0 and below AND rank 6 and above, and
    shifts all five rows. A `rank < 5` guard agrees on every rank the caller can produce and
    disagrees above 5, which is what these two extra ranks are here for.

    The score digits are seeded away from the shipped table's, so a row the insert did or did not
    move shows as a difference rather than as bytes that already matched.
    """
    pokes = {A_hiscore_rank: rank.to_bytes(2, "big", signed=True),
             A_score_digits: bytes(GLYPH_ZERO + 1 + digit for digit in range(SCORE_DIGITS))}
    _run(ENTRY_HISCORE_INSERT_SCORE_AT_RANK,
         lambda lib, buf: g_hiscore_insert_score_at_rank(buf),
         pokes=pokes, stop_pc=STOP_MAIN_REENTRY, note=f"rank={rank}")


# The shipped table's six scores, ../notes/frontend.md §5: HSC 250000 down to R P 050000.
SHIPPED_HISCORES = (250000, 200000, 175000, 150000, 100000, 50000)


@pytest.mark.parametrize("score", (0, 10, 49990, 50000))
def test_a_score_at_or_below_the_last_row_takes_nothing(score):
    """Equal to the lowest entry counts as BELOW it — `digits6_compare` answers "lower or equal" on a
    tie — so a tying score clears `new_hiscore_pending` and leaves the table alone."""
    _game_over_case(score)


@pytest.mark.parametrize("rank", range(HISCORE_ENTRIES))
def test_a_score_that_lands_at_each_rank(rank):
    """One award above the entry at `rank`, so the walk stops there and the rows below it are pushed
    down one at a time. Rank 0 is the case that also runs the missing floor, below."""
    _game_over_case(SHIPPED_HISCORES[rank] + 10, note=f"rank={rank}")


def test_the_rank_walk_runs_off_the_bottom_of_the_table():
    """THE MISSING FLOOR. A score above the leading entry leaves the rank at 0 and the loop then
    compares against "entry -1" — 22 bytes BELOW the table, which is the tail of
    `text_hall_of_fame`'s own script. The SIGNED byte compare is what stops it after that one step:
    the script's bytes are small and positive, and a digit glyph is negative."""
    _game_over_case(999990)


@pytest.mark.parametrize("below", (0xc0, 0xc4, 0x80))
def test_the_rank_walk_goes_NEGATIVE_when_what_is_below_the_table_loses_too(below):
    """...and it does not stop at rank 0 either. With the script bytes below the table replaced by
    glyphs the score also beats, the walk runs on to rank -1 and addresses 44 bytes below the table —
    which is where `muls.w`'s SIGN EXTENSION is the whole difference between reading the front end's
    text and reading 1.4 MB past the end of the image."""
    _game_over_case(999990, below=[below] * SCORE_DIGITS, note=f"below={below:#x}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_game_over_against_random_tables(chunk):
    """Random score fields in every row, so the walk stops at a rank the shipped data cannot produce
    — including tables whose rows are not in descending order, which the routine never checks."""
    rng = random.Random(0x9a3e + chunk)
    for _ in range(6):
        table = bytearray(harness.BASE_IMAGE[A_hiscore_table:
                                             A_hiscore_table + HISCORE_ENTRIES * HISCORE_STRIDE])
        for entry in range(HISCORE_ENTRIES):
            digits = bytes(GLYPH_ZERO + rng.randrange(10) for _ in range(SCORE_DIGITS))
            start = entry * HISCORE_STRIDE + HISCORE_SCORE
            table[start:start + SCORE_DIGITS] = digits
        _game_over_case(rng.randrange(1000000) // 10 * 10, table=table, note=f"chunk={chunk}")


def test_the_tie_the_dead_store_was_meant_to_win_is_lost():
    """`move.b #$f0,5(a1)` @ 0x1073e stamps a glyph above every digit into the score's LAST character
    so that a tying score would compare HIGH — and the very next instruction calls `bcd3_to_digits`,
    which rewrites all six characters including that one. So the store has no effect at all, and the
    tie it was written to win is lost.

    WHAT IS PINNED HERE IS THE OUTCOME, not the store. Dropping the store from the reconstruction is
    an EQUIVALENT MUTATION and no case can catch it — the byte is unconditionally overwritten one
    instruction later, on every path, so the two programs have identical memory everywhere. What a
    case can pin is that a score equal to the lowest row takes nothing, which is the consequence.
    STATUS.md records the mutation as equivalent rather than as a coverage hole.
    """
    _game_over_case(SHIPPED_HISCORES[-1])


# =================================================================================================
# The cheats: check_cheat_name @ 0x10d92 and the five reachable handlers
# =================================================================================================

CHEAT_NAME = abi.SCRATCH + 0x900        # where a case puts the three initials
# The six names, in the game's own alphabet, as ../notes/frontend.md §6 reads them.
CHEAT_NAMES = {
    "HSC": (0xb2, 0xbd, 0xad),
    "KDJ": (0xb5, 0xae, 0xb4),
    "JGL": (0xb4, 0xb1, 0xb6),
    "GCC": (0xb1, 0xad, 0xad),
    "J H": (0xb4, 0xcf, 0xb2),
}
CHEAT_JML = (0xb4, 0xb7, 0xb6)          # row 4 — the `jsr 0` booby trap, never driven


def _cheat_case(name, armed_at=1, invuln=0, poison=False):
    """One name, with the arm key ARRIVING at the `armed_at`th read of `key_bits`.

    EVERY CASE CARRIES A SCHEDULE, for `console_show_message`'s reason one section down: the arm spin
    reads a byte only the ACIA interrupt writes, so the reconstruction reads it through `sched_poll8`
    and the harness compares its polls against the oracle's arrivals at the same PC — which is the
    only thing that can see the ITERATION COUNT at all, the memory being identical either way. The
    oracle counts those arrivals only while the run carries a schedule, so "the key is already down"
    is expressed as `armed_at = 1`: the store lands before the first read.
    """
    pokes = {CHEAT_NAME: bytes(name), A_key_bits: b"\x00", A_invuln_flag: bytes([invuln])}
    last = CHEAT_NAME + HISCORE_NAME_CHARS - 1
    # `armed_at = None` is the key that never comes down. It is still a REAL entry rather than no
    # schedule, because an entry that never came due is refused by the oracle and no schedule at all
    # would leave the arrivals uncounted: the ACIA reports, at the first read, that the key is up.
    arrival, value = (1, 0) if armed_at is None else (armed_at, 1 << CHEAT_ARM_KEY_BIT)
    _run(ENTRY_CHECK_CHEAT_NAME, lambda lib, buf: g_check_cheat_name(buf, last), pokes=pokes,
         regs={"a0": last}, poison=poison,
         schedule=[{"pc": CHEAT_ARM_WAIT_PC, "nth": arrival, "addr": A_key_bits,
                    "width": 1, "value": value}],
         note=f"name={bytes(name).hex()} armed_at={armed_at} invuln={invuln}")


@pytest.mark.parametrize("name", sorted(CHEAT_NAMES))
def test_every_reachable_cheat_name_fires_its_handler(name):
    """Five of the six rows. `JML` is row 4 and is `movea.l #0,a0 / jsr (a0)` — a booby trap that
    calls address zero — so it is recorded in STATUS.md and never executed here."""
    _cheat_case(CHEAT_NAMES[name])


def test_the_cheat_only_arms_while_the_key_is_held():
    """With the key never arriving, the routine spins its full 5001 times and returns having written
    nothing at all — not even `cheat_used_flag`."""
    _cheat_case(CHEAT_NAMES["HSC"], armed_at=None)


@pytest.mark.parametrize("armed_at", (1, 2, CHEAT_ARM_SPINS - 1, CHEAT_ARM_SPINS, None))
def test_the_arm_spin_runs_exactly_five_thousand_and_one_times(armed_at):
    """`move.w #$1388,d7` + `dbf` is 5001 passes, not 5000, and both ends are driven: a key that
    arrives at the 5001st read still arms the cheat, and a key that never comes down leaves the loop
    to run every one of those passes.

    THE COUNT IS WHAT IS PINNED, not just the outcome. The harness compares the ORACLE's arrivals at
    0x10d9a against the candidate's polls, so a reconstruction that spun 5000 times fails the
    never-armed case even though its memory is identical.
    """
    _cheat_case(CHEAT_NAMES["KDJ"], armed_at=armed_at)


@pytest.mark.parametrize("name", ((GLYPH_A, GLYPH_A, GLYPH_A), (GLYPH_SPACE,) * 3,
                                  (0x00, 0x00, 0x00), (0xff, 0xff, 0xff)))
def test_a_name_that_matches_nothing_walks_the_table_to_its_terminator(name):
    _cheat_case(name)


@pytest.mark.parametrize("second", (0xb1, 0xb7, 0xcf, GLYPH_A))
def test_a_partial_match_rewinds_the_name_cursor_by_one_not_by_two(second):
    """THE OFF-BY-ONE. Three rows begin with 'J' (0xb4), so a name starting "J?" really does reach
    the third arm's `suba.w #$1,a0` — which backs the cursor up one where two glyphs were consumed,
    leaving every later row matched against name[1] and name[2]. Reproduced."""
    _cheat_case((0xb4, second, GLYPH_A))


def test_the_rewind_bug_can_fire_a_cheat_the_name_does_not_spell():
    """THE ONE NAME THAT SEPARATES THE BUG FROM ITS FIX, found by walking both matchers over every
    name built from the table's own glyphs: `J G C` followed by a fourth byte of 'C'.

    "JG?" matches `JGL`'s first two glyphs and fails on the third; the one-glyph rewind then leaves
    the cursor on 'G', which matches `GCC`'s first glyph, and the match runs off the END OF THE NAME
    into the fourth byte to confirm it. So the GCC cheat fires for a name that does not spell GCC.
    A rewind of two — the "correct" one — matches nothing at all.

    The fourth byte is the hall-of-fame row's own +14 on a real machine, a space, so the game cannot
    reach this; the instruction sequence can, and it is what is being reproduced.
    """
    _cheat_case((0xb4, 0xb1, 0xad, 0xad))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_random_names_against_the_shipped_table(chunk):
    """Random three-glyph names, sharded. The alphabet is weighted towards the letters the table's
    own rows use, so partial matches — and the rewind bug behind them — come up often. A name that
    would reach row 4 (`JML`) is dropped: its handler calls address zero."""
    rng = random.Random(0xc4ea7 + chunk)
    letters = sorted({glyph for name in CHEAT_NAMES.values() for glyph in name})
    for _ in range(20):
        name = tuple(rng.choice(letters) if rng.random() < 0.8 else rng.randrange(0x100)
                     for _ in range(HISCORE_NAME_CHARS))
        if name == CHEAT_JML:
            continue
        _cheat_case(name)


def test_the_hsc_cheat_kills_you_the_second_time():
    """Its arm is chosen by the flag its first use set, so entering it twice sets `player_hit`
    instead of clearing anything."""
    _cheat_case(CHEAT_NAMES["HSC"], invuln=0)
    _cheat_case(CHEAT_NAMES["HSC"], invuln=1)


def test_cheat_match_attribution():
    """Poison every byte the match writes: `cheat_used_flag`, the handler's own flag and the four
    glyphs of "SPAM" copied over "EASY"."""
    _cheat_case(CHEAT_NAMES["GCC"], poison=True)


CHEAT_HANDLERS = (
    (ENTRY_CHEAT_KDJ_INFINITE_LIVES, "g_cheat_kdj_infinite_lives"),
    (ENTRY_CHEAT_JGL_INFINITE_BOMBS, "g_cheat_jgl_infinite_bombs"),
    (ENTRY_CHEAT_GCC_ALT_GLYPH, "g_cheat_gcc_alt_glyph"),
    (ENTRY_CHEAT_JH_MAX_WEAPON, "g_cheat_jh_max_weapon"),
)


@pytest.mark.parametrize("entry,glue", CHEAT_HANDLERS)
def test_each_one_line_cheat_handler(entry, glue):
    """Each writes 1 — not 0xff — into its own flag byte, and nothing else."""
    _run(entry, lambda lib, buf: getattr(lib, glue)(buf),
         pokes={A_invuln_flag: bytes([RESULT_CANARY] * 5)}, poison=True, note=glue)


@pytest.mark.parametrize("invuln", (0, 1, 0xff))
def test_the_hsc_handler_on_its_own(invuln):
    _run(ENTRY_CHEAT_HSC_INVULNERABLE, lambda lib, buf: g_cheat_hsc_invulnerable(buf),
         pokes={A_invuln_flag: bytes([invuln]), A_player_hit: b"\x5a\x5a"}, poison=invuln != 0,
         note=f"invuln={invuln:#x}")


# =================================================================================================
# The console leftovers
# =================================================================================================

CONSOLE_TEXT = abi.SCRATCH + 0xa00


@pytest.mark.parametrize("ch", (0, ASCII_ZERO, 0x7f, 0xff, 0x1234))
def test_console_putc_is_one_cconout(ch):
    """The byte reaches the OS event ledger and nothing else moves — which is the only way the
    differential can see a Cconout at all."""
    _run(ENTRY_CONSOLE_PUTC, lambda lib, buf: g_console_putc(buf, ch), regs={"d0": ch},
         note=f"ch={ch:#x}")


@pytest.mark.parametrize("value", (0, 1, 0x8000, 0xffff, 0x5555, 0xaaaa, 0x1234_5678))
def test_debug_print_word_binary(value):
    """Sixteen bits most-significant first, then a carriage return. `lsl.w` shifts the WORD, so the
    high half of D4 never reaches the output."""
    _run(ENTRY_DEBUG_PRINT_WORD_BINARY, lambda lib, buf: g_debug_print_word_binary(buf, value),
         regs={"d4": value}, note=f"value={value:#010x}")


def _console_case(message, released_at=1):
    """One message, with the joystick's fire button HELD on entry and released by the ACIA at the
    `released_at`th poll of the wait.

    EVERY CASE CARRIES A SCHEDULE, and not for want of a shorter one. The routine's last act is a
    spin on `joy1_state` bit 7, a byte only the ACIA interrupt ever clears, so a candidate that read
    it straight out of the image would never leave — `sched_poll8` is what makes the wait runnable
    off target, and its polls are compared against the ORACLE's arrivals at the same PC. The oracle
    counts those arrivals only while the run carries a schedule (oracle/shim.c's `sched_fire` is
    called under `g_sched_n`), so a case that merely declared the site and let the button be up on
    entry would compare one poll against zero arrivals. `released_at = 1` IS that case, expressed so
    that both sides count it: the release lands before the first poll reads the byte.
    """
    pokes = {CONSOLE_TEXT: message, A_joy1_state: bytes([0xff])}
    _run(ENTRY_CONSOLE_SHOW_MESSAGE, lambda lib, buf: g_console_show_message(buf, CONSOLE_TEXT),
         pokes=pokes, regs={"a6": CONSOLE_TEXT},
         schedule=[{"pc": FIRE_RELEASE_WAIT_PC, "nth": released_at, "addr": A_joy1_state,
                    "width": 1, "value": 0x00}],
         note=f"message={message.hex()} released at poll {released_at}")


@pytest.mark.parametrize("message", (b"\xff", b"AB\xff", b"\x00\x01\x02\x80",
                                     bytes(range(0x20, 0x40)) + b"\xfe"))
def test_console_show_message(message):
    """Setscreen, the four VT52 cursor bytes, then the message — which ends at the first byte with
    bit 7 SET rather than at a NUL, so `b"\xff"` alone prints nothing at all."""
    _console_case(message)


@pytest.mark.parametrize("released_at", (1, 2, 5, 40))
def test_console_show_message_waits_for_fire_to_be_released(released_at):
    """The spin itself: the harness compares the oracle's arrivals at the compare against the
    candidate's polls, which is what says the two ran the same loop rather than merely ending in the
    same memory."""
    _console_case(b"X\xff", released_at=released_at)


# The map cursor's RESET value, and its low word is deliberately non-zero. `format_5_digits` masks
# its argument to 16 bits, so a reset of 0x20000 would make `map_row_ptr - reset` and `map_row_ptr`
# print the same five digits and a candidate that dropped the subtraction would pass.
DEBUG_MAP_RESET = 0x0002_1234


@pytest.mark.parametrize("map_advance,scroll_pos,scroll_fine", (
    (0, 0, 0), (1, 1, 1), (99999, 0xffff, 0xffff), (0x1_0000, 0x8000, 2), (12345, 678, 90)))
def test_debug_show_counters(map_advance, scroll_pos, scroll_fine):
    """The SLICE [0x14960, 0x14996): the original FALLS THROUGH into `console_show_message` without
    loading A6 with the string it just patched, so the slice ends at that fall-through and what the
    console would have printed is the caller's register rather than this routine's work."""
    reset = DEBUG_MAP_RESET
    pokes = {A_map_row_ptr_reset: reset.to_bytes(4, "big"),
             A_map_row_ptr: ((reset + map_advance) & 0xffffffff).to_bytes(4, "big"),
             A_scroll_pos: scroll_pos.to_bytes(2, "big"),
             A_scroll_fine: scroll_fine.to_bytes(2, "big")}
    _run(ENTRY_DEBUG_SHOW_COUNTERS, lambda lib, buf: g_debug_show_counters(buf), pokes=pokes,
         stop_pc=STOP_CONSOLE_SHOW_MESSAGE,
         note=f"advance={map_advance} pos={scroll_pos} fine={scroll_fine}")


# =================================================================================================
# The pins (README.md, "Adding a function", step 4)
# =================================================================================================

# The bytes at the two sites this battery schedules an external write to arrive at. A wait site one
# instruction off would count arrivals the original never makes, and the case's poll count would
# then disagree for a reason nothing in the case names — the same argument as `test_sprite.py`'s
# `test_the_vbl_wait_site_is_the_instruction_that_re_reads_the_counter`.
CHEAT_ARM_WAIT_PROLOGUE = "083900000001"        # `btst #0,$17780.l` — the key-bit poll
FIRE_RELEASE_WAIT_PROLOGUE = "083900070001"     # `btst #7,$1777f.l` — the joystick-fire poll


@pytest.mark.parametrize("pc,prologue,what", (
    (CHEAT_ARM_WAIT_PC, CHEAT_ARM_WAIT_PROLOGUE, "`btst #0,$17780.l`, the cheat arm's key poll"),
    (FIRE_RELEASE_WAIT_PC, FIRE_RELEASE_WAIT_PROLOGUE,
     "`btst #7,$1777f.l`, the fire-release poll"),
))
def test_each_wait_site_is_the_instruction_that_re_reads_its_input(pc, prologue, what):
    """Both waits spin on a byte only an interrupt moves, so the case supplies the arrival through
    the kit's SCHEDULED WRITE model keyed on this PC. Nothing else checks the PC is the poll."""
    bytes_there = bytes(harness.BASE_IMAGE[pc:pc + len(prologue) // 2])
    assert bytes_there == bytes.fromhex(prologue), (
        f"{pc:#x} holds {bytes_there.hex()}, not {what}")


MIRRORS = (
    "A_score_bcd", "A_hiscore_bcd", "SCORE_BCD_BYTES", "A_score_digits", "A_hiscore_digits",
    "SCORE_DIGITS", "A_score_award_values", "SCORE_AWARDS", "A_bonus_life_thresholds",
    "A_bonus_life_awarded_0", "BONUS_LIFE_THRESHOLDS", "BONUS_LIFE_FLAG_BYTES",
    "A_hiscore_table", "HISCORE_ENTRIES", "HISCORE_STRIDE", "HISCORE_NAME",
    "HISCORE_NAME_CHARS", "HISCORE_SCORE", "HISCORE_SHIFT_FROM", "HISCORE_SHIFT_BYTES",
    "HISCORE_LAST_DIGIT", "HISCORE_LOWEST_RANK", "SCORE_TIE_BREAK_GLYPH", "A_hard_mode",
    "A_name_entry_done", "A_name_entry_timeout", "A_hiscore_rank", "A_hiscore_beaten",
    "A_new_hiscore_pending", "A_const_words_0123", "DIGITS_COMPARE_LOWER_OR_EQUAL",
    "DIGITS_COMPARE_HIGHER", "GLYPH_A", "GLYPH_ZERO", "GLYPH_SPACE",
    # ...and the rows that come from another subsystem's header, spelt in full because the default
    # is `include/hud.h`: the display-list RECORD is frozen in `include/display_list.h` and the
    # scroll cursors the debug overlay formats belong to `include/sprite.h`.
    ("DISPLAY_REC_BYTES", "include/display_list.h", "DISPLAY_REC_BYTES"),
    ("DISPLAY_REC_FRAME", "include/display_list.h", "DISPLAY_REC_FRAME"),
    ("DISPLAY_REC_ACTIVE", "include/display_list.h", "DISPLAY_REC_ACTIVE"),
    ("A_display_list", "include/display_list.h", "A_display_list"),
    ("A_display_list_end", "include/display_list.h", "A_display_list_end"),
    "A_hud_label_slots",
    "A_hud_score_slots", "A_hud_hiscore_slots", "A_dl_bomb_icons", "A_dl_life_icons",
    "HUD_DIGIT_SLOTS", "HUD_BLANKABLE_SLOTS", "HUD_ICON_SLOTS_CLEARED",
    "HUD_LIVES_SHOWN_MAX",
    # ...and the player record this subsystem draws from, which went home to include/player.h
    # when that subsystem landed (STATUS.md, "Borrowed globals").
    ("A_player", "include/player.h", "A_player"),
    ("PLAYER_MODE", "include/player.h", "PLAYER_MODE"),
    ("PLAYER_MODE_GAMEOVER", "include/player.h", "PLAYER_MODE_GAMEOVER"),
    ("A_lives", "include/player.h", "A_lives"),
    ("A_bombs", "include/player.h", "A_bombs"),
    ("A_player_hit", "include/player.h", "A_player_hit"),
    ("A_dl_player_shadow", "include/player.h", "A_dl_player_shadow"),
    "A_cheat_handler_table", "A_cheat_name_table", "CHEAT_ROW_BYTES", "CHEAT_TABLE_END",
    "CHEAT_ARM_SPINS", "CHEAT_ARM_KEY_BIT", "CHEAT_ARM_WAIT_PC", "A_key_bits",
    "A_cheat_used_flag", "A_title_word_easy", "A_title_word_spam",
    "TITLE_WORD_GLYPHS", "A_invuln_flag", "A_infinite_lives_flag", "A_infinite_bombs_flag",
    "A_alt_bullet_glyph_flag", "A_max_weapon_flag", "LOW_MEMORY_INDENT_WORD",
    "A_text_hall_of_fame", "A_text_enter_your_name", "TEXT_OP_SPACE", "TEXT_OP_TAB",
    "TEXT_OP_NEWLINE", "TEXT_OP_INDENT", "TEXT_OP_END", "TEXT_GLYPH_WIDTH", "TEXT_LINE_HEIGHT",
    "TEXT_TAB_WIDTH", "A_joy1_state", "JOY_FIRE_BIT", "FIRE_RELEASE_WAIT_PC", "FORMAT_DIGITS",
    "FORMAT_RADIX", "ASCII_ZERO", "ASCII_ONE", "ASCII_CR", "BINARY_DUMP_BITS",
    "A_debug_map_advance_field", "A_debug_scroll_pos_field", "A_debug_scroll_fine_field",
    ("A_map_row_ptr", "include/sprite.h", "A_map_row_ptr"),
    ("A_map_row_ptr_reset", "include/sprite.h", "A_map_row_ptr_reset"),
    ("A_scroll_fine", "include/sprite.h", "A_scroll_fine"), "A_scroll_pos", "CONSOLE_TEXT_END",
)

ENTRY_PROLOGUES = {
    "ENTRY_BUILD_TEXT_DISPLAY_LIST": "121814181018b03c00006602",
    "ENTRY_HISCORE_SHOW_ENTRY_SCREEN": "610001cc42804281428241f9",
    "ENTRY_GAME_OVER_HISCORE_CHECK": "4239000177cc33fc00050001",
    "ENTRY_HISCORE_INSERT_SCORE_AT_RANK": "3839000176e0b87c00056720b87c0004",
    "ENTRY_HISCORE_SHIFT_ENTRY_DOWN": "3e3c000c41e80009224843e9",
    "ENTRY_HISCORE_RESET_LAST_DIGIT": "48e7fffe41f9000161dd3e3c",
    "ENTRY_DIGITS6_COMPARE": "3e3c00054bed0010bd0d6d06",
    "ENTRY_HUD_BUILD_LABELS": "41f900017ca830fc005c30fc",
    "ENTRY_CHECK_BEAT_HISCORE": "41f9000159f443f9000159fa",
    "ENTRY_HUD_BUILD_SCORE_DIGITS": "41f9000159f443f900017cb4",
    "ENTRY_HUD_PUBLISH_DIGIT_ROW": "3e3c000432c132c212d812fc",
    "ENTRY_HUD_BLANK_LEADING_ZEROS": "43f900017cb46100000c43f9",
    "ENTRY_HUD_BLANK_LEADING_ZEROS_ROW": "3e3c00040c2900c500046702",
    "ENTRY_SCORES_BCD_TO_CHARS": "41f900015a2a43f9000159f4",
    "ENTRY_BCD3_TO_DIGITS": "3e3c00024280428110181200",
    "ENTRY_SCORE_ADD_50": "48e700c043f900015a336100",
    "ENTRY_SCORE_ADD_100": "48e700c043f900015a366100",
    "ENTRY_SCORE_ADD_200": "48e700c043f900015a396100",
    "ENTRY_SCORE_ADD_250": "48e700c043f900015a3c6100",
    "ENTRY_SCORE_ADD_500": "48e700c043f900015a3f6100",
    "ENTRY_SCORE_ADD_1000": "48e700c043f900015a426100",
    "ENTRY_SCORE_ADD_3000": "48e700c043f900015a456100",
    "ENTRY_SCORE_ADD_5000": "48e700c043f900015a486100",
    "ENTRY_SCORE_ADD_10000": "48e700c043f900015a4b6100",
    "ENTRY_SCORE_ADD_BCD": "41f900015a2dc109c109c109",
    "ENTRY_CHECK_CHEAT_NAME": "48e7fffe3e3c138808390000",
    "ENTRY_CHEAT_HSC_INVULNERABLE": "4a39000177c6670a33fc0001",
    "ENTRY_CHEAT_KDJ_INFINITE_LIVES": "13fc0001000177c74e7513fc",
    "ENTRY_CHEAT_JGL_INFINITE_BOMBS": "13fc0001000177c84e7513fc",
    "ENTRY_CHEAT_GCC_ALT_GLYPH": "13fc0001000177c94e75207c",
    "ENTRY_CHEAT_JH_MAX_WEAPON": "13fc0001000177ca4e754a79",
    "ENTRY_AWARD_EXTRA_LIFE": "41f900015a2a43f9000159f4",
    "ENTRY_DEBUG_PRINT_WORD_BINARY": "48e7fffe3a3c0010e34c641a",
    "ENTRY_CONSOLE_PUTC": "3f003f3c00024e41588f4e75",
    "ENTRY_CLEAR_DISPLAY_LIST": "48e7fffe41f9000177ce4218",
    "ENTRY_CLEAR_PLAYER_DISPLAY_SLOTS": "48e7fffe41f900017cfc4258",
    "ENTRY_SCORE_RESET": "41f900015a2a6100001041f9",
    "ENTRY_CLEAR_3_BYTES": "4218421842104e7548e7fffe",
    "ENTRY_HUD_PUBLISH_BOMB_AND_LIFE_ICONS": "41f9000190a40c2800040006",
    "ENTRY_DEBUG_SHOW_COUNTERS": "41f900014a05203900016402",
    "ENTRY_CONSOLE_SHOW_MESSAGE": "20790001641a3f3cffff2f3c",
    "ENTRY_FORMAT_5_DIGITS": "10fc003010fc003010fc0030",
}

STOP_PROLOGUES = {
    "STOP_HISCORE_NAME_ENTRY": "4a79000176dc660000b441f9",
    "STOP_SFX_EXTRA_LIFE": "48e7fffe41f900058944303c",
    # The same address as ENTRY_CONSOLE_SHOW_MESSAGE, and deliberately named twice: it is where
    # `debug_show_counters`' slice stops AND where the routine it falls into begins.
    "STOP_CONSOLE_SHOW_MESSAGE": "20790001641a3f3cffff2f3c",
    "STOP_MAIN_REENTRY": "6100bba46100bc406100bef6",
}
