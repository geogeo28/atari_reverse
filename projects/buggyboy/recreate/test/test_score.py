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


# Bytes straddling the decisions add_score makes: the per-digit carry is a *signed* `cmp.b`/`bpl`
# against '9' (0x39) — verified: no BCD/decimal-adjust op is used — so the sign bit of (0x39 - digit)
# must be modelled for every byte, not just 0x30..0x39. These land on both sides of that flip
# (0x39/0x3a), the int8 sign boundary (0x7f/0x80), the blank-walk char (0x30), and the extremes.
_BOUNDARY_BYTES = (0x00, 0x2f, 0x30, 0x38, 0x39, 0x3a, 0x7f, 0x80, 0x81, 0x99, 0xff)


def test_boundary_bytes():
    # Each boundary byte at each digit position, isolated with a zero delta, pins the signed
    # carry decision (cmp.b/bpl) at that byte — the edge the 0..9 fuzz never reaches.
    for b in _BOUNDARY_BYTES:
        for pos in range(6):
            score = [0x30] * 6
            score[pos] = b
            _case(score, [0] * 6, False)
    # add.l / add.w wraparound and a maxed carry cascade.
    _case([0xff] * 6, [0xff] * 6, False)          # both adds overflow their field
    _case([0x39] * 6, [0, 0, 0, 0, 0, 0xff], False)   # cascade from a large low-word delta
    _case([0x30] * 6, [0xff] * 6, False)


def test_fuzz():
    # Full-range bytes (not just ASCII digits): the port must match the asm's signed cmp.b/bpl
    # carry and its add.l/.w wraparound for every input — score/delta sit in fixed 6-byte
    # buffers, so any byte value is memory-safe.
    rng = random.Random(12)               # fixed seed (dataset seed convention)
    for _ in range(3000):
        score = [rng.randint(0, 255) for _ in range(6)]
        delta = [rng.randint(0, 255) for _ in range(6)]
        _case(score, delta, rng.random() < 0.1)