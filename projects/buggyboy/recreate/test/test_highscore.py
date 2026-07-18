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


# --- name-entry tail slices (made-the-table path) -----------------------------------------------
# The interactive initials screen never returns under the oracle (it waits on the IKBD / mzflag), so
# its two deterministic per-frame pieces are diffed as slices, mirroring init_playfield's nav/fire.

CD_ENTRY, CD_STOP, CD_TIMEOUT_STOP = 0x12472, 0x124b4, 0x1257c   # countdown tick body / render / timeout
A_CD_SUB, A_CD_TIMER = 0x18264, 0x18262
CS_ENTRY, CS_STOP = 0x124ea, 0x12542                             # char-select body (before the fire check)
A_DEC_DELAY, A_INC_DELAY, A_IN = 0x18c62, 0x18c64, 0x18c44
NAME_ADDR = 0x18400                                              # scratch image byte holding the current initial

harness._lib.g_hiscore_countdown.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_hiscore_countdown.restype = ctypes.c_int
harness._lib.g_hiscore_charstep.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_hiscore_charstep.restype = None


def test_name_countdown():
    """countdown_sub advance + 'TIME nn' render; timeout when the timer underflows (0x2472..0x24b4)."""
    for sub in (0, 1, 0x10, 0x11, 0x12, 0x20):
        for timer in (0, 1, 5, 9, 10, 11, 20, 30):
            pokes = {A_CD_SUB: (sub & 0xffff).to_bytes(2, "big"),
                     A_CD_TIMER: (timer & 0xffff).to_bytes(2, "big")}
            timeout = (sub + 1) >= 0x12 and timer == 0           # sub reaches 0x12 and the timer hits -1
            stop = CD_TIMEOUT_STOP if timeout else CD_STOP
            diffs, info = differential(CD_ENTRY, {"_pokes": pokes},
                                       lambda l, b: l.g_hiscore_countdown(b), stop_pc=stop)
            assert not diffs, f"sub={sub:#x} timer={timer}\n{report(diffs[:8])}"
            assert (info["ret"] != 0) == timeout, f"sub={sub:#x} timer={timer}: ret={info['ret']} timeout={timeout}"


# up=1, left=4 step the initial down; down=2, right=8 step it up; fire 0x80 not exercised here.
CS_INPUTS = (0, 1, 4, 2, 8, 1 | 2, 0x80, 0x80 | 1)


def test_name_charstep():
    """Per-frame initials selection: up/left steps down (wraps 'A'->'`'), down/right steps up
    (wraps 'a'->'A'), each gated by its auto-repeat delay (0x24ea..0x2542)."""
    for ch in (0x41, 0x42, 0x5a, 0x5f, 0x60, 0x4d):              # 'A','B','Z','_','`', mid-range
        for dec in (0, 1):                                      # 0 -> fires this frame, 1 -> not yet
            for inc in (0, 1):
                for dirs in CS_INPUTS:
                    pokes = {NAME_ADDR: bytes([ch]),
                             A_DEC_DELAY: (dec & 0xffff).to_bytes(2, "big"),
                             A_INC_DELAY: (inc & 0xffff).to_bytes(2, "big"),
                             A_IN: (dirs & 0xffff).to_bytes(2, "big")}
                    diffs, _ = differential(CS_ENTRY, {"a0": NAME_ADDR, "_pokes": pokes},
                                            lambda l, b: l.g_hiscore_charstep(b, NAME_ADDR), stop_pc=CS_STOP)
                    assert not diffs, (f"ch={ch:#x} dec={dec} inc={inc} dirs={dirs:#x}\n{report(diffs[:8])}")
