"""The VDI's ARITHMETIC helpers (`src/vdi/helpers.c`): vec_len, sort_words, smul_div, isin and icos.

Each is entered as its callers enter it — the Alcyon calls by `jsr` with their word arguments on the
stack (`test/vdi_helpers.py`), `sort_words` with D0/A0 — and compared against its C core over the
snapshot. The boundaries are the point: the ROM's answers are 68000 word arithmetic, and each case
below sits where the obvious C would part from it (a sign, a wrap, an overflowing divide, the ends of
the sine table).
"""
import math
import pytest

from harness import BASE_IMAGE, addrs

import case
import vdi
import vdi_helpers
from vdi_helpers import answer, run_call

WORD_BYTES = vdi_helpers.WORD_BYTES


# ---- vec_len, $fc9ffc ------------------------------------------------------------------------------

def vec_len(dx, dy):
    return run_call("VDI_ROM_VEC_LEN", case.word_args(dx, dy), (dx, dy))


# Zero; the exact squares; roots that round down; both halves of the log search (a sum under $10000
# and one at or over it, $10000 itself included); negative legs; and the two sums of 2^30 or more,
# whose high bound $10000 is taken back to $ffff.
VEC_LEN_LEGS = ((0, 0), (1, 0), (0, 1), (1, 1), (3, 4), (2, 1), (-3, -4), (-5, 12), (255, 0), (256, 0),
                (255, 255), (181, 181), (1000, 1), (12345, -6789), (23170, 23170), (32767, 32767),
                (-32768, -32768), (-32768, 0))


@pytest.mark.parametrize("dx,dy", VEC_LEN_LEGS)
def test_vec_len_is_the_root_rounded_down(dx, dy):
    assert answer(vec_len(dx, dy)) & 0xFFFF == math.isqrt(dx * dx + dy * dy) & 0xFFFF


# ---- sort_words, $fca164 ---------------------------------------------------------------------------
SORT = "VDI_ROM_SORT_WORDS"
SORT_AT = vdi_helpers.SORT_AT
SORT_ROOM_WORDS = 16
# D0's high word, which the ROM never reads: `subq.w #2` and the two `dbf`s are word operations.
COUNT_HIGH = 0xABCD_0000


def sort_pokes(words, room=SORT_ROOM_WORDS):
    """`words` at SORT_AT, the rest of the room filled so a word written past the count shows."""
    staged = vdi.pack_words(*words) + bytes([vdi.FILL]) * (WORD_BYTES * (room - len(words)))
    return {SORT_AT: staged}


def sort_words(words, count=None):
    count = len(words) if count is None else count
    return vdi.run_primitive(SORT, {"d0": COUNT_HIGH | count, "a0": SORT_AT}, sort_pokes(words))


@pytest.mark.parametrize("words", (
    (), (7,), (2, 1), (1, 2), (5, 5), (9, 8, 7, 6, 5, 4, 3, 2), (1, 2, 3, 4, 5, 6),
    (-1, 1, 0, 0x7FFF, -0x8000, 3, 3, -2), (4, 4, 4, 4), (0, -1)))
def test_sort_words_sorts_signed_ascending(words):
    result = sort_words(words)
    assert [vdi.signed_word(w) for w in result.words(SORT_AT, len(words))] == sorted(words)


def test_sort_words_touches_nothing_past_its_count():
    """Five words staged and three counted: the last two stay as they were, out of order or not."""
    words = (3, 2, 1, 9, 0)
    result = sort_words(words, count=3)
    assert [vdi.signed_word(w) for w in result.words(SORT_AT, 5)] == [1, 2, 3, 9, 0]


def test_sort_words_counts_in_a_word():
    """A count of $10001 is 1 to `subq.w #2`: no pass."""
    words = (2, 1)
    result = vdi.run_primitive(SORT, {"d0": 0x1_0001, "a0": SORT_AT}, sort_pokes(words))
    assert result.words(SORT_AT, 2) == [2, 1]


# ---- smul_div, $fca186 -----------------------------------------------------------------------------

def smul_div(a, b, c):
    return answer(run_call("VDI_ROM_SMUL_DIV", case.word_args(a, b, c), (a, b, c)))


@pytest.mark.parametrize("a,b,c,expected", (
    (6, 4, 3, 8),               # exact
    (5, 1, 2, 3),               # a half rounds away from zero...
    (4, 1, 3, 1),               # ...less than a half does not
    (-5, 1, 2, -2),             # a negative REMAINDER over a nonzero quotient word is read as |r| - 1
    (-11, 1, 7, -1),            # (`neg.l` of the whole register), so -2.5 and even -1.57 round TOWARD 0
    (11, 1, 7, 2),              # ...where the positive twin rounds up
    (-4, 1, 7, -1),             # over a ZERO quotient word |r| is read whole, and -0.57 rounds to -1
    (5, 1, -2, -3),             # a negative divisor turns the step round
    (-5, 1, -2, 2),             # ...and its remainder is negative too: 2.5 rounds down
    (1, 1, -0x8000, -1),        # -(-32768) is still negative, so ANY remainder rounds
    (0, 1234, 3, 0),
    (0x7FFF, 0x7FFF, 1, 2),     # overflow: divs.w leaves the product, whose words are then read
    (1000, 320, 640, 500),
    (-32768, 1, 1, -32768),
))
def test_smul_div_rounds_as_the_rom_does(a, b, c, expected):
    assert smul_div(a, b, c) == expected


def test_smul_div_by_zero_is_refused_by_name_on_the_host():
    """The ROM's `divs.w` by 0 takes vector 5. No case can run that on the oracle's side to a
    comparable end, so the claim here is the HOST's half: the core refuses by name and aborts, rather
    than raising a SIGFPE that names nothing (`vdi/helpers.h`)."""
    returncode, stderr = vdi_helpers.refusal("vdi_smul_div", ["ctypes.c_int16"] * 3, "1, 1, 0")
    assert returncode != 0
    assert "not reconstructed: divs.w by zero" in stderr


# ---- isin, $fcab68, and icos, $fcac4c --------------------------------------------------------------
SINE_ENTRIES = 92                      # 0..90 degrees and a repeated last entry for the interpolation
FULL_SCALE = 32767


def isin(angle):
    return answer(run_call("VDI_ROM_ISIN", case.word_arg(angle), (angle,)))


def icos(angle):
    return answer(run_call("VDI_ROM_ICOS", case.word_arg(angle), (angle,)))


def test_the_sine_table_runs_zero_to_full_scale_and_repeats_its_end():
    table = [case.word_in(BASE_IMAGE, vdi.VDI_SINE_TABLE + WORD_BYTES * i) for i in range(SINE_ENTRIES)]
    assert table[0] == 0 and table[90] == table[91] == FULL_SCALE
    assert all(abs(table[d] - round(FULL_SCALE * math.sin(math.radians(d)))) <= 1 for d in range(91))


def test_the_switch_table_holds_isin_s_five_arms():
    """Quadrants 0..4 of the C switch, read out of the ROM: the fold each arm makes is pinned by the
    cases below, and this pins that there are five and where the table is."""
    arms = [case.long_in(BASE_IMAGE, vdi.VDI_ISIN_SWITCH + 4 * q) for q in range(5)]
    assert all(addrs.VDI_ROM_ISIN < arm < addrs.VDI_ROM_ICOS for arm in arms) and len(set(arms)) == 5


# Every arm of the fold (quadrants 0..4 — 3600 itself is the fifth), the table's first and last
# entries, interpolated tenths on both sides of each, an angle brought down by whole turns, and
# NEGATIVE angles: a small one folds nowhere and interpolates with a negative remainder, a large one
# misses every arm and reads the ROM below the table.
ISIN_ANGLES = (0, 1, 5, 9, 10, 455, 899, 900, 901, 1234, 1799, 1800, 1801, 2250, 2699, 2700, 2701, 3599,
               3600, 3601, 7200, 32767, -1, -9, -10, -455, -899, -900, -3600, -32768)


@pytest.mark.parametrize("angle", ISIN_ANGLES)
def test_isin(angle):
    sine = isin(angle)
    if 0 <= angle:
        assert abs(sine - FULL_SCALE * math.sin(math.radians(angle / 10))) <= 3


@pytest.mark.parametrize("angle", (0, 900, 1800, 2699, 2700, 2701, 3600, -900, -1000, 32767, 31867))
def test_icos(angle):
    """2701 + 900 is over a turn and comes down once; 32767 + 900 WRAPS negative, and 31867 lands at
    exactly 32767."""
    cosine = icos(angle)
    if 0 <= angle <= 3600:
        assert abs(cosine - FULL_SCALE * math.cos(math.radians(angle / 10))) <= 3


# ---- the transcriptions (`src/vdi/helpers.S`), over the same shapes ---------------------------------
SORT_TRANSCRIBED = ((), (7,), (2, 1), (5, 5), (9, 8, 7, 6, 5, 4, 3, 2), (-1, 1, 0, 0x7FFF, -0x8000, 3, 3, -2))


@pytest.mark.parametrize("words", SORT_TRANSCRIBED)
def test_sort_words_transcription_behaves_as_the_rom(words):
    vdi_helpers.run_transcription(SORT, sort_pokes(words), {"d0": COUNT_HIGH | len(words), "a0": SORT_AT})


@pytest.mark.parametrize("a,b,c", ((6, 4, 3), (5, 1, 2), (-11, 1, 7), (-4, 1, 7), (5, 1, -2), (1, 1, -0x8000),
                                   (0x7FFF, 0x7FFF, 1), (0, 1234, 3)))
def test_smul_div_transcription_behaves_as_the_rom(a, b, c):
    vdi_helpers.run_transcription("VDI_ROM_SMUL_DIV", {}, frame=case.word_args(a, b, c))


# ---- the rows Tier 3 prices ------------------------------------------------------------------------
vdi.register("vdi_vec_len, a root found by bisection", addrs.VDI_ROM_VEC_LEN, case.word_args(12345, -6789))
vdi.register("vdi_vec_len, an exact square", addrs.VDI_ROM_VEC_LEN, case.word_args(3, 4))
vdi.register("vdi_sort_words, eight words reversed", addrs.VDI_ROM_SORT_WORDS, sort_pokes((9, 8, 7, 6, 5, 4, 3, 2)),
             regs={"d0": COUNT_HIGH | 8, "a0": SORT_AT})
vdi.register("vdi_sort_words, two words in order", addrs.VDI_ROM_SORT_WORDS, sort_pokes((1, 2)),
             regs={"d0": COUNT_HIGH | 2, "a0": SORT_AT})
vdi.register("vdi_smul_div, rounded up", addrs.VDI_ROM_SMUL_DIV, case.word_args(1000, 321, 640))
vdi.register("vdi_smul_div, negative over a negative divisor", addrs.VDI_ROM_SMUL_DIV, case.word_args(-5, 1, -2))
vdi.register("vdi_isin, interpolated in the second quadrant", addrs.VDI_ROM_ISIN, case.word_arg(1234))
vdi.register("vdi_isin, a whole degree", addrs.VDI_ROM_ISIN, case.word_arg(450))
vdi.register("vdi_icos, interpolated", addrs.VDI_ROM_ICOS, case.word_arg(2701))
# ...and the same rows for the `.S` the target build ships.
vdi_helpers.register_transcription(SORT, "eight words reversed", sort_pokes((9, 8, 7, 6, 5, 4, 3, 2)),
                                   {"d0": COUNT_HIGH | 8, "a0": SORT_AT})
vdi_helpers.register_transcription(SORT, "two words in order", sort_pokes((1, 2)), {"d0": COUNT_HIGH | 2, "a0": SORT_AT})
vdi_helpers.register_transcription("VDI_ROM_SMUL_DIV", "rounded up", {}, frame=case.word_args(1000, 321, 640))
vdi_helpers.register_transcription("VDI_ROM_SMUL_DIV", "negative over a negative divisor", {},
                                   frame=case.word_args(-5, 1, -2))
