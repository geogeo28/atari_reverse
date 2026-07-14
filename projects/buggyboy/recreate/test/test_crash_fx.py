"""Differential test for draw_crash_fx @ 0x15872 (crash / game-over HUD effect; A6 = draw buffer).

Once the crash gate is set, it drains bonus time / units into the score (add_score + stop_music_chk),
rolls a score-digit table over, arms the abort countdown, then redraws the score number (draw_num)
and the gauge bars (draw_hud_bar). All sub-draws are already verified; this whole-image diff checks
the timer/score/rollover/abort logic and the sub-call args (dst offsets, fill, strings). The digit
string + bar strings are staged with valid glyphs, buf_c holds the num-sprite arena, add_score's
score bytes are staged, and mzflag is set so stop_music_chk bails. Fuzzed over the branch conditions.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x15872

A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_CRASH_ACTIVE, A_CRASH_FRAME, A_TIME_LEFT, A_CRASH_LAP = 0x18c7a, 0x18c78, 0x18cfc, 0x18c4a
A_CRASH_BARS, A_ABORT_FLAG, A_GAME_OVER, A_MZFLAG = 0x18d00, 0x18c4e, 0x18c34, 0x1b07a
STR_NUM, STR_BAR1, STR_BAR2 = 0x18172, 0x1817a, 0x181cc

BUFFER = 0x8000
BUF_C = 0x30000
NUM_ARENA = BUF_C + 0xbb80      # draw_num digit-sprite arena
NUM_SPAN = 0xe000
HUD_LO, HUD_HI = 0x18160, 0x18260   # HUD strings + score bytes + rollover table

harness._lib.g_draw_crash_fx.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_crash_fx.restype = None


def _pokes(seed, active, frame, time_left, lap, bars):
    rng = random.Random(seed)
    p = {
        BUFFER: bytes(rng.randrange(256) for _ in range(0x8000)),
        NUM_ARENA: bytes(rng.randrange(256) for _ in range(NUM_SPAN)),
        HUD_LO: bytes(rng.randrange(256) for _ in range(HUD_HI - HUD_LO)),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: BUFFER.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_CRASH_ACTIVE: (active & 0xffff).to_bytes(2, "big"),
        A_CRASH_FRAME: (frame & 0xffff).to_bytes(2, "big"),
        A_TIME_LEFT: (time_left & 0xffff).to_bytes(2, "big"),
        A_CRASH_LAP: (lap & 0xffff).to_bytes(2, "big"),
        A_CRASH_BARS: (bars & 0xffff).to_bytes(2, "big"),
        A_ABORT_FLAG: (0).to_bytes(2, "big"),
        A_GAME_OVER: (0).to_bytes(2, "big"),
        A_MZFLAG: bytes([1]),                        # stop_music_chk bails
        STR_NUM: bytes([1, 2, 3, 0]),                # valid draw_num digits
        # The bars chain A3 through one buffer: one 0-terminated pair per bar. STR_BAR1 (0x1817a)
        # feeds up to 6 bars and stays clear of the rollover table at 0x1818e; STR_BAR2 (0x181cc)
        # feeds up to 4 and stays clear of the lap digit at 0x181da.
        STR_BAR1: bytes([1, 2, 0] * 6),
        STR_BAR2: bytes([3, 4, 0] * 4),
    }
    return p


def _check(seed, active=1, frame=0x20, time_left=0, lap=0, bars=0):
    regs = {"a6": BUFFER, "_pokes": _pokes(seed, active, frame, time_left, lap, bars)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_crash_fx(b, BUFFER), poison=True)
    assert not diffs, (f"active={active} frame={frame} time={time_left} lap={lap} bars={bars}\n"
                       f"{report(diffs[:16])}")


def test_gate_off():
    _check(seed=1, active=0)                          # early abort_flag = 0xffff


def test_pre_threshold():
    for bars in range(6):                             # frame < 0xa: skip body, still draws
        _check(seed=bars, active=1, frame=5, bars=bars)


def test_time_drain():
    for bars in range(6):
        _check(seed=10 + bars, frame=0x20, time_left=100, bars=bars)


def test_lap_drain():
    for bars in range(6):
        _check(seed=20 + bars, frame=0x20, time_left=0, lap=7, bars=bars)


def test_rollover_and_abort():
    # time=lap=0 -> the digit-rollover loop / abort arming, across bar counts and frame phases.
    for frame in (0x20, 0x21, 0x27):
        for bars in range(6):
            _check(seed=frame * 8 + bars, frame=frame, time_left=0, lap=0, bars=bars)
