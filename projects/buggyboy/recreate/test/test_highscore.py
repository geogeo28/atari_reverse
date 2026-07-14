"""Differential test for update_highscore @ 0x1238e (high-score table insert).

Verified to a CHECKPOINT, since the tail of the real function is the interactive name-entry loop
(busy-polls the IKBD, Vsyncs, waits on MZFLAG) which can't run to rts under the oracle. The
reconstruction implements only the deterministic prefix — EGOFF, leading-zero blank, ranking, row
shift, score/name insert — and the oracle is stopped at the matching prefix exit:
  made the table -> 0x12450 (after the insert, before play_event_tune)
  didn't make it -> 0x123e6 (after results_mode=2 / hiscore_pos=0)
The whole image is diffed at that PC (the machine-stack writes sit in the excluded guard band).

The test stages the new 12-byte score record, a random per-leg table, and the leg index, computes
which exit the score takes (mirroring the byte-wise ranking), and checkpoints there.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1238e
CKPT_MADE = 0x12450        # made the table: after the insert
CKPT_MISS = 0x123e6        # didn't: after results_mode=2 / hiscore_pos=0

A_SCORE = 0x1824c          # 12-byte score+name record (6 ASCII digits, then name/pad)
A_LEG_INDEX = 0x18c38
A_TABLE = 0x18266
LEG_STRIDE, ROW, ROWS = 0x80, 0xe, 9
A_EG_FLAG, A_MUSIC_BYTE = 0x1b07c, 0x1b063   # EGOFF clears these -> stage nonzero to observe the call

harness._lib.g_update_highscore.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_update_highscore.restype = None


def _blanked(score6):
    b = bytearray(score6)
    if b[0] == ord('0'):
        b[0] = ord('/')            # update_highscore blanks a leading zero before ranking
    return bytes(b)


def _rank(rows, score6):
    """0-based insertion row, or None if the score beats no row. Mirrors outranks_row."""
    for r in range(ROWS):
        base = r * ROW
        verdict = 0
        for i in range(6):
            if ((rows[base + i] - score6[i]) & 0xff) & 0x80:   # row < new -> insert here
                verdict = 1
                break
            if rows[base + i] != score6[i]:                    # row > new -> next row
                break
        if verdict:
            return r
    return None


def _run(score, rows, leg):
    table = A_TABLE + leg * LEG_STRIDE
    pokes = {
        A_SCORE: bytes(score),
        table: bytes(rows),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        A_EG_FLAG: b"\x20", A_MUSIC_BYTE: b"\x07",
    }
    rank = _rank(rows, _blanked(score[:6]))
    stop = CKPT_MISS if rank is None else CKPT_MADE
    diffs, _ = differential(ENTRY, {"_pokes": pokes},
                            lambda l, b: l.g_update_highscore(b), stop_pc=stop)
    assert not diffs, f"leg={leg} rank={rank} score={bytes(score[:6])}\n{report(diffs[:12])}"


def _digits(s):
    return bytes(s.encode())


def test_edge_cases():
    name = bytes(range(6))                       # arbitrary name/pad bytes
    for leg in (0, 4):
        rows = (_digits("500000") + b"\0" * 8) * ROWS
        _run(_digits("900000") + name, rows, leg)                 # beats row 0 (rank 0, shift 8)
        _run(_digits("100000") + name, rows, leg)                 # beats nothing (path B)
        _run(_digits("500000") + name, rows, leg)                 # ties every row -> path B
        # beats only the last row (rank 8, zero-iteration shift)
        rows8 = (_digits("900000") + b"\0" * 8) * (ROWS - 1) + _digits("100000") + b"\0" * 8
        _run(_digits("500000") + name, rows8, leg)
        _run(_digits("050000") + name, rows, leg)                 # leading-zero blanked to '/'


def test_fuzz():
    for seed in range(60):
        rng = random.Random(seed)
        score = bytes(rng.randrange(0x2f, 0x3a) for _ in range(6)) + bytes(rng.randrange(256) for _ in range(6))
        rows = bytearray()
        for _ in range(ROWS):
            rows += bytes(rng.randrange(0x2f, 0x3a) for _ in range(6)) + bytes(rng.randrange(256) for _ in range(8))
        _run(score, rows, seed % 5)
