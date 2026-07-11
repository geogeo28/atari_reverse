"""Differential tests for the score subsystem (add_score @ 0x1580a)."""
import ctypes
import random

import harness
from harness import differential, report

ENTRY_ADD_SCORE = 0x1580a
DELTA_PTR = 0x1e000                       # scratch for the 6-byte delta A1 points at (below stack guard)

harness._lib.g_add_score.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_add_score.restype = None


def _case(score, delta, game_over):
    """One add_score case: 6 score digit-bytes, 6 delta bytes, game_over flag (word)."""
    pokes = {
        0x1824c: bytes(score),                                # score_bcd + counter (6 contiguous)
        0x18c34: (1 if game_over else 0).to_bytes(2, "big"),  # game_over_flag
        DELTA_PTR: bytes(delta),
    }
    regs = {"a1": DELTA_PTR, "_pokes": pokes}
    diffs, _ = differential(ENTRY_ADD_SCORE, regs,
                            lambda lib, buf: lib.g_add_score(buf, DELTA_PTR))
    assert not diffs, f"score={score} delta={delta} over={game_over}\n{report(diffs)}"


def test_edge_cases():
    ascii_digits = lambda s: [ord(c) for c in s]
    _case(ascii_digits("000000"), [0, 0, 0, 0, 0, 5], False)      # simple add
    _case(ascii_digits("999999"), [0, 0, 0, 0, 0, 1], False)      # full carry cascade
    _case(ascii_digits("000000"), [0, 0, 0, 0, 0, 0], False)      # all-zero leading-blank walk
    _case(ascii_digits("012345"), [0, 0, 0, 0, 0, 9], False)      # leading-zero blanking
    _case(ascii_digits("123456"), [0, 0, 0, 9, 0, 0], False)      # mid-field carry
    _case(ascii_digits("555555"), [0, 0, 0, 0, 0, 7], True)       # game over -> no change


def test_fuzz():
    rng = random.Random(12)               # fixed seed (dataset seed convention)
    for _ in range(2000):
        score = [ord("0") + rng.randint(0, 9) for _ in range(6)]
        delta = [rng.randint(0, 9) for _ in range(6)]
        _case(score, delta, rng.random() < 0.1)