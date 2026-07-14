"""Differential test for init_scoretable @ 0x1047a (default high-score table).

Run-to-rts, no register args. Writes 5 legs x 9 rows of 0xe-byte records into highscore_table:
"/" + two default score digits (from the fixed A_default_scores string) + "000\\0\\0" + "...\\0" +
a rank char + \\0, with a 2-byte separator per leg (0x80 stride). The only input is that image
string, so the output is constant; the test stages the table region with noise across a few seeds
and diffs the whole image, poison-checked for write attribution.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1047a

A_HIGHSCORE_TABLE = 0x18266
TABLE_BYTES = 5 * 0x80          # 5 legs * (9 rows * 0xe + 2 separator); ends at A_default_scores

harness._lib.g_init_scoretable.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_init_scoretable.restype = None


def test_init_scoretable():
    for seed in range(6):
        rng = random.Random(seed)
        pokes = {A_HIGHSCORE_TABLE: bytes(rng.randrange(256) for _ in range(TABLE_BYTES))}
        diffs, _ = differential(ENTRY, {"_pokes": pokes},
                                lambda l, b: l.g_init_scoretable(b), poison=True)
        assert not diffs, f"seed={seed}\n{report(diffs[:12])}"
