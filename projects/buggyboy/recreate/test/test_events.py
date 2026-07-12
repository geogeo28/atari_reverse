"""Differential tests for the course-event engine (evt_* / handle_marker) and the sound-driver
leaves they call (TURNOFF / INITFX / INITTUNE).

The event handlers branch on mutable game state (game_over, cur_tune_id, MZFLAG, flag_seq_count,
…) which we poke to exercise each path; const tables (the expected sequence, score deltas, the
sound parameter tables) come from the loaded image. Scoring reuses the verified add_score.
"""
import ctypes

import harness
import emu
from harness import differential, report

U8P = ctypes.POINTER(ctypes.c_uint8)
for name, argc in [("g_TURNOFF", 0), ("g_INITFX", 1), ("g_INITTUNE", 1), ("g_evt_collision", 0),
                   ("g_play_event_tune", 1), ("g_evt_flag_gate", 2), ("g_evt_score_msg", 2),
                   ("g_handle_marker", 1)]:
    fn = getattr(harness._lib, name)
    fn.argtypes = [U8P] + [ctypes.c_uint32] * argc
    fn.restype = None

# Mutable state globals (see addrs.h / names.txt).
A_collision_lock, A_engine_rpm, A_speed = 0x18c84, 0x18c8c, 0x18cf6
A_game_over, A_cur_tune, A_mzflag, A_fxflag = 0x18c34, 0x18cfa, 0x1b07a, 0x1b07b
A_flag_seq_count, A_flag_seq_off, A_bonus_timer = 0x18c48, 0x18c40, 0x18d08

# evt_flag_gate has one jump-table entry per object type (each sets D6 then joins the body).
FLAG_GATE_ENTRY = {1: 0x11ba4, 2: 0x11ba8, 3: 0x11bac, 4: 0x11bb0, 5: 0x11bb4}


def _w(addr, val):
    return {addr: (val & 0xffff).to_bytes(2, "big")}


def _merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


# ---- sound-driver leaves (run to rts; read const tables, write the voice-state block) ----

def test_turnoff():
    diffs, _ = differential(0x1b268, {}, lambda lib, buf: lib.g_TURNOFF(buf))
    assert not diffs, report(diffs[:12])


def test_initfx():
    for fx in (0, 1, 2, 5, 9):
        diffs, _ = differential(0x1b560, {"d0": fx},
                                lambda lib, buf, f=fx: lib.g_INITFX(buf, f))
        assert not diffs, f"fx={fx}\n{report(diffs[:12])}"


def test_inittune():
    for tune in (0, 1, 6, 7, 8):
        diffs, _ = differential(0x1b59c, {"d0": tune},
                                lambda lib, buf, t=tune: lib.g_INITTUNE(buf, t))
        assert not diffs, f"tune={tune}\n{report(diffs[:12])}"


# ---- event handlers ----

def test_evt_collision():
    for lock in (0, 1):
        for rpm in (0x00, 0x05, 0x10, 0x20, 0x80, 0x1234):
            pokes = _merge(_w(A_collision_lock, lock), _w(A_engine_rpm, rpm))
            diffs, _ = differential(0x11c2c, {"_pokes": pokes},
                                    lambda lib, buf: lib.g_evt_collision(buf))
            assert not diffs, f"lock={lock} rpm={rpm:#x}\n{report(diffs[:12])}"


def test_play_event_tune():
    for over in (0, 1):
        for cur in (0, 6, 8):
            for mz in (0, 0xff):
                for tune in (6, 8):
                    pokes = _merge(_w(A_game_over, over), _w(A_cur_tune, cur), {A_mzflag: bytes([mz])})
                    diffs, _ = differential(0x11c7a, {"d0": tune, "_pokes": pokes},
                                            lambda lib, buf, t=tune: lib.g_play_event_tune(buf, t))
                    assert not diffs, f"over={over} cur={cur} mz={mz:#x} tune={tune}\n{report(diffs[:12])}"


def test_evt_flag_gate():
    for d6, entry in FLAG_GATE_ENTRY.items():
        for seq in (0, 3, 4, 5):
            for bonus in (0, 0x10):
                for slot in (0, 3, 7):
                    pokes = _merge(_w(A_flag_seq_count, seq), _w(A_bonus_timer, bonus),
                                   _w(A_flag_seq_off, 0), _w(A_game_over, 0), _w(A_cur_tune, 0),
                                   {A_mzflag: bytes([0])})
                    diffs, _ = differential(entry, {"d5": slot, "_pokes": pokes},
                                            lambda lib, buf, s=slot, t=d6: lib.g_evt_flag_gate(buf, s, t))
                    assert not diffs, f"d6={d6} seq={seq} bonus={bonus} slot={slot}\n{report(diffs[:12])}"


def test_evt_score_msg():
    for d6 in (0, 1, 3):
        for d7 in (0, 1, 2):
            pokes = _merge(_w(A_game_over, 0), _w(A_cur_tune, 0), {A_mzflag: bytes([0])})
            diffs, _ = differential(0x11c5a, {"d6": d6, "d7": d7, "_pokes": pokes},
                                    lambda lib, buf, a=d6, b=d7: lib.g_evt_score_msg(buf, a, b))
            assert not diffs, f"d6={d6} d7={d7}\n{report(diffs[:12])}"


def test_handle_marker():
    for over in (0, 1):
        for cur in (0, 6, 7, 8):
            for mz in (0, 0xff):
                for fx in (0, 2):
                    pokes = _merge(_w(A_game_over, over), _w(A_cur_tune, cur), {A_mzflag: bytes([mz])})
                    diffs, _ = differential(0x11cb2, {"d0": fx, "_pokes": pokes},
                                            lambda lib, buf, f=fx: lib.g_handle_marker(buf, f))
                    assert not diffs, f"over={over} cur={cur} mz={mz:#x} fx={fx}\n{report(diffs[:12])}"