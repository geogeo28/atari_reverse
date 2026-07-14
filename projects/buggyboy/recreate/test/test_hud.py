"""Differential test for draw_hud @ 0x1555e (the full in-race HUD; A6 derived from flip_idx).

draw_hud is an eight-phase renderer that writes straight into the current draw buffer:
speed/time digit strings, a dashboard-variant masked sprite (from buf_c), the flag-sequence bars,
five colour-tinted bars, the fuel/tacho gauge (or a blinking small gauge), the main gauge cluster
(draw_hud_gauge0 + five draw_hud_bars + draw_dashboard, threading A0/A3), and the crash-fx timer.

Const tables (color_pairs, font glyphs, the colour-bar mask/index tables, the fuel mask) are real
image data. The test stages the mutable state: the draw buffer + buf_c arenas (noise), a bounded
dashboard-variant record, the gauge label strings, and the branch-selecting words. It fuzzes the
speed/time formatting, the flag/colour/gauge branches, and the crash-timer arm, diffing the whole
image (poison-checked for attribution).
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1555e

# --- state words ---
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_SPEED, A_TIME_LEFT, A_GAME_OVER = 0x18cf6, 0x18cfc, 0x18c34
A_DSP_TOGGLE, A_DSP_VARIANT_IDX = 0x18c7c, 0x18c7e
A_FLAG_SEQ_COUNT, A_FLAG_SEQ_OFF, A_DSP_COLOR_SCROLL = 0x18c48, 0x18c40, 0x18d06
A_CRASH_LAP = 0x18c4a
A_GAUGE_BLINK, A_GAUGE_BLINK_ON = 0x18d02, 0x18d04
A_HUD_CRASH_TIMER, A_CRASH_ACTIVE, A_ABORT_FLAG = 0x18c4c, 0x18c7a, 0x18c4e

# --- staged tables / strings ---
HUD_DSP_TBL = 0x1854c          # record 0: {src_off:long, dst_off:word, rows-1:word}
SMALL_GAUGE_STR, GAUGE_MAIN_STR = 0x18206, 0x18218

BUFFER = 0x8000                # draw buffer (screen); noise
BUF_C = 0x30000               # buf_c; dashboard reads +0x11c20, phase-3 src reads DSP_SRC_OFF
BUF_C_LO, BUF_C_HI = BUF_C + 0x10000, BUF_C + 0x14000   # covers +0x11c20 dashboard + phase-3 src
DSP_SRC_OFF, DSP_DST_OFF, DSP_ROWS_M1 = 0x11000, 0x400, 3

harness._lib.g_draw_hud.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_hud.restype = None


def _pokes(seed, speed, time_left, game_over, dsp_toggle, flag_seq,
           lap, gauge_blink, gauge_blink_on, crash_timer):
    rng = random.Random(seed)
    return {
        BUFFER: bytes(rng.randrange(256) for _ in range(0x7d00)),
        BUF_C_LO: bytes(rng.randrange(256) for _ in range(BUF_C_HI - BUF_C_LO)),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: BUFFER.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_SPEED: (speed & 0xffff).to_bytes(2, "big"),
        A_TIME_LEFT: (time_left & 0xffff).to_bytes(2, "big"),
        A_GAME_OVER: (game_over & 0xffff).to_bytes(2, "big"),
        A_DSP_TOGGLE: (dsp_toggle & 0xffff).to_bytes(2, "big"),
        A_DSP_VARIANT_IDX: (0).to_bytes(2, "big"),
        HUD_DSP_TBL: (DSP_SRC_OFF.to_bytes(4, "big")
                      + DSP_DST_OFF.to_bytes(2, "big")
                      + DSP_ROWS_M1.to_bytes(2, "big")),
        A_FLAG_SEQ_COUNT: (flag_seq & 0xffff).to_bytes(2, "big"),
        A_FLAG_SEQ_OFF: (0).to_bytes(2, "big"),
        A_DSP_COLOR_SCROLL: (0).to_bytes(2, "big"),
        A_CRASH_LAP: (lap & 0xffff).to_bytes(2, "big"),
        A_GAUGE_BLINK: (gauge_blink & 0xffff).to_bytes(2, "big"),
        A_GAUGE_BLINK_ON: (gauge_blink_on & 0xffff).to_bytes(2, "big"),
        A_HUD_CRASH_TIMER: (crash_timer & 0xffff).to_bytes(2, "big"),
        A_CRASH_ACTIVE: (0).to_bytes(2, "big"),        # if crash_timer < 0, crash_fx just arms abort
        A_ABORT_FLAG: (0).to_bytes(2, "big"),
        SMALL_GAUGE_STR: bytes([1, 2, 0]),
        GAUGE_MAIN_STR: bytes([1, 2, 0] * 6),          # gauge0 + five bars chain one buffer
    }


def _check(seed, speed=80, time_left=42, game_over=0, dsp_toggle=0, flag_seq=0,
           lap=0, gauge_blink=0, gauge_blink_on=0, crash_timer=0):
    regs = {"_pokes": _pokes(seed, speed, time_left, game_over, dsp_toggle, flag_seq,
                             lap, gauge_blink, gauge_blink_on, crash_timer)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_hud(b), poison=True)
    assert not diffs, (f"seed={seed} speed={speed} time={time_left} go={game_over} "
                       f"dsp={dsp_toggle} flag={flag_seq} lap={lap} blink={gauge_blink}/"
                       f"{gauge_blink_on} crash={crash_timer}\n{report(diffs[:16])}")


def test_speed_digits():
    # <100 (blank tens), 100-199 ("/1"), >=200 ("/2"), and 0/boundary values.
    for speed in (0, 5, 9, 42, 99, 100, 150, 199, 200, 250, 255):
        _check(seed=speed, speed=speed)


def test_time_digits():
    for time_left, go in ((0, 0), (7, 0), (58, 0), (99, 0), (250, 0), (42, 1)):
        _check(seed=time_left + go, time_left=time_left, game_over=go)


def test_dsp_sprite():
    _check(seed=1, dsp_toggle=0)          # phase 3 runs (bounded record)
    _check(seed=2, dsp_toggle=1)          # phase 3 skipped


def test_flag_bars():
    for flag_seq in range(6):
        _check(seed=100 + flag_seq, flag_seq=flag_seq)


def test_fuel_gauge():
    for lap in range(5):                  # lap 0 -> small gauge branch; >=1 -> fuel columns
        _check(seed=200 + lap, lap=lap)


def test_small_gauge_blink():
    # lap 0 forces phase 6b: exercise blink < 0, bit1 set/clear, and the gated bar.
    for blink in (0, 1, 2, 3, 4, 6):
        for on in (0, 1):
            _check(seed=300 + blink * 2 + on, lap=0, gauge_blink=blink, gauge_blink_on=on)


def test_crash_timer():
    _check(seed=400, crash_timer=0)       # phase 8 skipped
    _check(seed=401, crash_timer=6)       # decays by 2
    _check(seed=402, crash_timer=-4)      # crash_fx (crash_active=0 -> arms abort_flag)


def test_fuzz():
    for seed in range(40):
        rng = random.Random(seed)
        _check(seed=seed,
               speed=rng.randrange(256),
               time_left=rng.randrange(300),
               game_over=rng.randrange(2),
               dsp_toggle=rng.randrange(2),
               flag_seq=rng.randrange(6),
               lap=rng.randrange(5),
               gauge_blink=rng.randrange(8),
               gauge_blink_on=rng.randrange(2),
               crash_timer=rng.choice([0, 4, 8, -2]))
