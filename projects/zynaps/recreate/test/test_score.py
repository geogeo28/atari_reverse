"""Differential tests for the packed-BCD score and the extra life it awards (src/score.c).

`score_add_bcd` writes four longwords, a lives byte and a panel-redraw bit, and — on the awarding
arm — everything `sound_start` writes into a voice record. All of that is image memory, so a plain
differential sees the whole routine; nothing here needs a stub.

THE AWARDING ARM IS DRIVEN FROM REAL DATA WHERE IT CAN BE. The four awards, the threshold and the
step are the .PRG's own bytes, and a case that wants a score near the threshold pokes the SCORE
rather than inventing a threshold — the shipped 10000/20000 pair is then what the compare and the
step both run on.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_SCORE_ADD_BCD = 0x12df6

# mirrors of include/score.h
A_EXTRA_LIFE_THRESHOLD_BCD = 0x195d8
A_EXTRA_LIFE_THRESHOLD_STEP_BCD = 0x195dc
A_PLAYER_SCORE_BCD = 0x195e0
A_SCORE_AWARD_TABLE_BCD = 0x195e4
SCORE_BCD_BYTES = 4
SCORE_AWARDS = 4
EXTRA_LIFE_SOUND = 0x10

# mirrors of include/hud.h
A_LIVES = 0x1991a
A_PANEL_REDRAW_MASK = 0x19904
PANEL_REDRAW_LIVES_BIT = 4

# A caller passes A1 = one past the four-byte value it wants added, so a synthetic award needs four
# bytes of its own somewhere the routine may read; the case points A1 past them.
AWARD_SCRATCH = abi.SCRATCH

harness._lib.g_score_add_bcd.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_score_add_bcd.restype = None

FUZZ_CHUNKS = 4
FUZZ_CASES = 256


def _bcd(value):
    """The four bytes of `value` as the image holds them."""
    return value.to_bytes(SCORE_BCD_BYTES, "big")


def _case(award_end, pokes=None, poison=False):
    regs = {"a1": award_end, "_pokes": dict(pokes or {})}
    diffs, _ = differential(
        ENTRY_SCORE_ADD_BCD, regs,
        lambda lib, buf: lib.g_score_add_bcd(buf, award_end), poison=poison)
    assert not diffs, f"award_end={award_end:#x} pokes={pokes}\n{report(diffs)}"


def _synthetic_award(award, score=None, threshold=None, step=None, lives=None, mask=None):
    """A1 pointing one past four bytes of this battery's own, with the state a case wants."""
    pokes = {AWARD_SCRATCH: _bcd(award)}
    for addr, value in ((A_PLAYER_SCORE_BCD, score),
                        (A_EXTRA_LIFE_THRESHOLD_BCD, threshold),
                        (A_EXTRA_LIFE_THRESHOLD_STEP_BCD, step)):
        if value is not None:
            pokes[addr] = _bcd(value)
    if lives is not None:
        pokes[A_LIVES] = bytes([lives])
    if mask is not None:
        pokes[A_PANEL_REDRAW_MASK] = bytes([mask])
    return AWARD_SCRATCH + SCORE_BCD_BYTES, pokes


@pytest.mark.parametrize("award", range(SCORE_AWARDS))
def test_every_shipped_award(award):
    """Each of the four awards the game hands out, added to the score the .PRG boots with.

    A1 is one past the entry, which is what every call site passes, so the pointer arithmetic is
    driven from the game's own table rather than from a synthetic address.
    """
    _case(A_SCORE_AWARD_TABLE_BCD + (award + 1) * SCORE_BCD_BYTES)


@pytest.mark.parametrize("score,award", (
    (0x00000000, 0x00000001),   # the smallest step there is
    (0x00000009, 0x00000001),   # ...carrying out of the low nibble
    (0x00000099, 0x00000001),   # ...and out of the low byte
    (0x00009999, 0x00000001),   # ...and across the word
    (0x00999999, 0x00000001),   # ...and into the top byte
    (0x00099999, 0x00000001),   # a carry that stops one nibble short of the top
    (0x00001234, 0x00005678),   # nothing carries at all
    (0x00005555, 0x00005555),   # every nibble carries at once
))
def test_bcd_carry_walks_up(score, award):
    """The four `abcd`s run LOW BYTE FIRST and hand the carry upwards, which is only visible when a
    digit overflows: a candidate adding the bytes in address order would agree on 1234 + 5678 and
    disagree the moment 99 + 01 has to carry into the byte above it.

    The threshold is left at the shipped 10000 so these stay on the non-awarding arm; the arm itself
    has its own cases below.
    """
    end, pokes = _synthetic_award(award, score=score)
    _case(end, pokes)


@pytest.mark.parametrize("score", (0x00009999, 0x00009998, 0x00010000, 0x00010001, 0x00020000))
def test_threshold_edges(score):
    """Either side of the shipped 10000 threshold, and one clear of it.

    `bgt` is the branch, so equality AWARDS — the score that exactly reaches the threshold is the
    one a `bge` reconstruction would get wrong, and 9999 + 1 is the case that lands on it.
    """
    end, pokes = _synthetic_award(1, score=score)
    _case(end, pokes)


def test_threshold_compare_is_signed():
    """A BCD score of 80000000 has bit 31 set, so the longword compare reads it as NEGATIVE and no
    life is awarded however large the number is in decimal. Eight digits of Zynaps score never get
    there, so this arm is driven with a poked score rather than by the game."""
    end, pokes = _synthetic_award(0x00000001, score=0x79999999, threshold=0x10000000)
    _case(end, pokes)
    end, pokes = _synthetic_award(0x00000001, score=0x89999999, threshold=0x10000000)
    _case(end, pokes)


def test_award_steps_the_threshold_and_the_lives():
    """The awarding arm's four outputs at once: the jingle `sound_start` arms (a voice record and
    the alternating-voice toggle byte, all in the image), the threshold stepped by its own BCD step,
    the lives byte incremented and bit 4 of the panel mask set.

    The mask is poked to a value with OTHER bits set, so a candidate STORING the bit instead of
    OR-ing it in differs; and the lives byte is driven at 0xff, where `addi.b #$1` wraps to 0.
    """
    for lives, mask in ((3, 0x00), (3, 0xa5), (0xff, 0xef), (0, 0x10)):
        end, pokes = _synthetic_award(0x00000001, score=0x00009999, lives=lives, mask=mask)
        _case(end, pokes)


def test_award_steps_the_threshold_in_bcd():
    """The second `abcd` chain is the first one over different addresses, so it carries the same
    way: a threshold of 99990000 stepped by 20000 has to carry across three bytes."""
    end, pokes = _synthetic_award(0x00000001, score=0x00000000, threshold=0x00000000,
                                  step=0x00019999)
    _case(end, pokes)
    end, pokes = _synthetic_award(0x00000001, score=0x00000000, threshold=0x00000000,
                                  step=0x99999999)
    _case(end, pokes)


@pytest.mark.parametrize("award,score", ((0x00007531, 0x00002468), (0x00001111, 0x00002222)))
def test_a1_is_followed_and_the_award_is_not_written(award, score):
    """A1 is a full 32-bit address the routine follows: these awards are not in the shipped table at
    all, so a candidate reading the table's own bytes differs. And `abcd -(a1),-(a0)` writes ONLY
    through A0, so the four bytes below A1 must come back unchanged — which the diff can see because
    the case put them in scratch the routine has no other reason to touch."""
    end, pokes = _synthetic_award(award, score=score)
    _case(end, pokes)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_random_scores_and_awards(chunk):
    """Random longwords in both operands, INCLUDING nibbles above 9.

    The game's own data is valid BCD, so those are the oracle's convention rather than a verified
    fact about the machine — but they are the widest thing the two implementations can be compared
    over, and the correction order in `bcd_add_byte` is exactly what they hold.
    """
    rng = random.Random(ENTRY_SCORE_ADD_BCD + chunk)
    for _ in range(FUZZ_CASES // FUZZ_CHUNKS):
        end, pokes = _synthetic_award(rng.getrandbits(32), score=rng.getrandbits(32),
                                      threshold=rng.getrandbits(32), step=rng.getrandbits(32),
                                      lives=rng.getrandbits(8), mask=rng.getrandbits(8))
        _case(end, pokes)


# NO hi-garbage CASE, deliberately: A1 is an ADDRESS and every one of its 32 bits is real — there is
# no high half for `harness.hi_garbage` to fill, the way there is for a `.w` count or column. That
# the routine follows the register rather than the table it usually points into is what
# `test_a1_is_followed_and_the_award_is_not_written` above drives, from `abi.SCRATCH`.


@pytest.mark.parametrize("score", (0x00001234, 0x00009999))
def test_attribution(score):
    """Poison both arms: the non-awarding one writes the score alone, the awarding one writes the
    threshold, the lives byte, the panel mask and the voice record too."""
    end, pokes = _synthetic_award(0x00000001, score=score)
    _case(end, pokes, poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_EXTRA_LIFE_THRESHOLD_BCD", "include/score.h", "A_extra_life_threshold_bcd"),
    ("A_EXTRA_LIFE_THRESHOLD_STEP_BCD", "include/score.h", "A_extra_life_threshold_step_bcd"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("A_SCORE_AWARD_TABLE_BCD", "include/score.h", "A_score_award_table_bcd"),
    ("SCORE_BCD_BYTES", "include/score.h", "SCORE_BCD_BYTES"),
    ("SCORE_AWARDS", "include/score.h", "SCORE_AWARDS"),
    ("EXTRA_LIFE_SOUND", "include/score.h", "EXTRA_LIFE_SOUND"),
    ("A_LIVES", "include/hud.h", "A_lives"),
    ("A_PANEL_REDRAW_MASK", "include/hud.h", "A_panel_redraw_mask"),
    ("PANEL_REDRAW_LIVES_BIT", "include/hud.h", "PANEL_REDRAW_LIVES_BIT"),
)
ENTRY_PROLOGUES = {
    "ENTRY_SCORE_ADD_BCD": "41f9000195e4c109c109",
}
