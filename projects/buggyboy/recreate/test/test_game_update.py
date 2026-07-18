"""Differential test for game_update @ 0x1110e — the per-frame in-race game-logic driver.

game_update has two paths: the COMMON per-frame path (sections 1-11: input, fire, time, lean,
steering, engine/speed, scroll, wheel, road-curve, edge/crash) which ends in build_road_geometry +
return; and the COURSE-ADVANCE path (section 12), taken only on the periodic frame where view_flags
wraps. This test exercises the common path (view forced not to wrap) — the bulk of the per-frame
logic — via a run-to-rts whole-image diff vs the Musashi oracle. No OS traps; the const tables
(0x173xx/0x174xx) are real image data. read_input keeps a nonzero staged input_state, so `in` is
controlled by staging input_state + last_key.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1110e

# RAM state game_update reads (all others default to BSS 0).
A = dict(
    game_over=0x18c34, input_state=0x18c44, input_prev=0x18c42, last_key=0x18c46,
    crash_phase=0x18c86, crash_frame=0x18c78, speed=0x18cf6, marker_pending=0x18d14,
    event_pending=0x18c82, fire_hold=0x18c98, dsp_variant=0x18c7e, leg_flags_sel=0x18c96,
    leg_flags_c90=0x18c90, hud_crash_timer=0x18c4c, time_left=0x18cfc, time_subctr=0x18cfe,
    timeout_gate=0x18c3e, lean_phase=0x18cce, engine_rpm=0x18c8c, spin_reset=0x18cc8,
    spin_word2=0x18cca, collision_lock=0x18c84, turn_flags=0x18c80, curve_window=0x18c88,
    curve_clamp=0x18d1a, speed_raw=0x18cf8, speed_jitter_ph=0x18c94, scroll_phase=0x18c8e,
    scroll_speed=0x18cb4, view_flags=0x18c56, view_bank=0x18c54, steer_hold=0x18ccc,
    wheel_pos=0x18cc0, sprite_suppress=0x18cd0, curve_freeze=0x18d16, road_edge_flags=0x1905c,
    road_geom_hi=0x19094, road_curve=0x18c6a, steer_delta=0x18cae, lean_state=0x18cc2,
    buggy_skid=0x18cbc, crash_disp=0x18c68, hscroll_step2=0x18cac,
)


def _w(v): return (v & 0xffff).to_bytes(2, "big")
def _l(v): return (v & 0xffffffff).to_bytes(4, "big")


def _pokes(st):
    p = {}
    for k, v in st.items():
        if k == "leg_flags_c90":
            p[A[k]] = _l(v)
        elif k == "curve_window":
            p[A[k]] = _l(v)
        else:
            p[A[k]] = _w(v)
    return p


def _check(label, **st):
    st.setdefault("engine_rpm", 0xf)                # min rpm -> speed 0 -> scroll 0 -> no view wrap
    st.setdefault("scroll_phase", 0xe)              # +2 & 0xe -> 0
    st.setdefault("view_flags", 0)
    st.setdefault("leg_flags_c90", 0x00500002)      # cap=0x50, add=2
    regs = {"_pokes": _pokes(st)}
    diffs, info = differential(ENTRY, regs, lambda lib, buf: lib.g_game_update(buf),
                               max_insns=1_000_000)
    return diffs, info


harness._lib.g_game_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_update.restype = None

harness._lib.g_gu_dispatch_event.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_gu_dispatch_event.restype = None


def test_event_pending_dispatch():
    # event_pending 1..64 (collision_lock 0) fires the section-6 jump-table dispatch (d6=1,d7=0,d5=0):
    # flag_gate (1-11), score-message events (13-21), checkpoint counters (22-24), and the object/spin/
    # bonus/finish spawns (25-64). Whole-frame diff vs the oracle for every reachable jump-table index.
    for ev in range(1, 65):
        diffs, _ = _check(f"ev{ev}", input_state=0, event_pending=ev, collision_lock=0)
        assert not diffs, f"event_pending={ev}\n{report(diffs[:24])}"


# ---- per-handler isolation: enter the oracle at the handler PC and run to rts (like the evt_* tests),
# so every jump-table target 22-64 is verified under all d6/d7 gates and its state preconditions,
# independent of the surrounding frame. idx -> resolved target (one representative idx per target). ----
_EVT_TARGETS = {
    22: 0x11d12, 23: 0x11d1a, 24: 0x11d2e, 26: 0x11d38, 30: 0x11d3a, 31: 0x11d62,
    32: 0x11d64, 34: 0x11d8e, 35: 0x11dcc, 38: 0x11de2, 25: 0x11e16, 61: 0x11e4e,
    62: 0x11e5c, 41: 0x11e8e, 63: 0x11e96, 42: 0x11e92, 64: 0x11eaa,
}
_HA = dict(collision_lock=0x18c84, speed=0x18cf6, engine_rpm=0x18c8c, spin_state=0x18caa,
           road_curve=0x18c6a, crash_phase=0x18c86, game_over=0x18c34, cur_tune=0x18cfa)
A_MZFLAG = 0x1b07a   # gates stop_music / play_event_tune (kept 0 so those callees run)


def test_event_handler_isolation():
    rng = random.Random(0xE7A0)
    for idx, target in _EVT_TARGETS.items():
        for _ in range(40):
            d5 = rng.choice([0, 3, 0x20])
            d6 = rng.choice([0, 1])
            d7 = rng.choice([0, 1, 0xff])
            p = {
                _HA["collision_lock"]: _w(rng.choice([0, 0, 8, 0x3e8])),
                _HA["speed"]:          _w(rng.choice([0, 0x1e, 0x64, 0x120])),
                _HA["engine_rpm"]:     _w(rng.choice([0xf, 0x40, 0x88, 0x1ff])),
                _HA["road_curve"]:     _w(rng.choice([0, 0x100, -0x100 & 0xffff])),
                _HA["crash_phase"]:    _w(rng.choice([0, 2, -1 & 0xffff])),
                _HA["spin_state"]:     bytes([rng.choice([0, 0x20, 0x80])]),
                _HA["game_over"]:      _w(0),
                _HA["cur_tune"]:       _w(0),
                A_MZFLAG:              bytes([0]),
            }
            regs = {"d5": d5, "d6": d6, "d7": d7, "_pokes": p}
            diffs, _ = differential(
                target, regs,
                lambda lib, buf, i=idx, a=d5, b=d6, c=d7: lib.g_gu_dispatch_event(buf, i, a, b, c),
                max_insns=3_000_000)
            assert not diffs, (f"idx={idx} target={target:#x} d5={d5} d6={d6} d7={d7:#x}\n"
                               f"{report(diffs[:24])}")



# Inputs WITHOUT the throttle bit (1): throttle raises rpm -> scroll_speed -> view wrap (section 12).
# Brake/steer/fire keep rpm floored at 0xf, so the frame stays on the common path.
_IN_NO_THROTTLE = [0, 2, 4, 8, 0x80, 0x82, 0x84, 0x88, 0xc, 0x8c]


def test_common_path_fuzz():
    rng = random.Random(0x6A00)
    for i in range(400):
        st = dict(
            input_state=rng.choice(_IN_NO_THROTTLE),
            input_prev=rng.choice([0, 0x80]),
            wheel_pos=rng.randrange(0, 5),
            road_curve=rng.choice([0, 0x40, -0x40 & 0xffff, 0x100, -0x100 & 0xffff,
                                   0x160, -0x160 & 0xffff, rng.randrange(0x10000)]),
            road_edge_flags=rng.choice([0, 0x8000, 0xf000, 0xd000, 0xb000, 0x9000,
                                        rng.randrange(0x10000)]),
            road_geom_hi=rng.choice([0, 0xffff, 0x8000]),
            hud_crash_timer=rng.choice([0, 1, 5, -1 & 0xffff]),
            crash_phase=rng.choice([0, 1, 3, -1 & 0xffff]),
            game_over=rng.choice([0, 0, 1]),
            steer_hold=rng.choice([0, 9, 10, 0x20]),
            spin_reset=rng.choice([0, 0, 0x20]),
            spin_word2=rng.choice([0, 0, 0x18]),
            curve_freeze=rng.choice([0, 0, 1]),
            sprite_suppress=rng.choice([0, 8, -8 & 0xffff]),
            hscroll_step2=rng.choice([0, 4, -4 & 0xffff]),
            curve_window=rng.choice([0, 0x30004000, 0x40005000]),
            fire_hold=rng.choice([0, 0, 3]),
            time_left=rng.choice([0, 1, 0x40]),
            time_subctr=rng.choice([0, 0xb, 5]),
            timeout_gate=rng.choice([0, 0, 1]),
            dsp_variant=rng.randrange(0, 0x40),
            leg_flags_sel=rng.choice([0, 4]),
        )
        diffs, _ = _check(f"fuzz{i}", **st)
        assert not diffs, f"seed={i} {st}\n{report(diffs[:24])}"


# ---- course-advance path (section 12): force a view wrap (view_flags high, rpm=0xf so scroll=0). ----
A_BUF_A_PTR = 0x18c00
BUF_A = 0x60000
# course-advance state globals (all default 0 unless staged)
AC = dict(crash_bars=0x18d00, course_flag_bit=0x18c70, course_row_ctr=0x18c52,
          course_read_pos=0x18c50, marker_slope_src=0x18d32, horizon_row=0x18c6c,
          horizon_frac=0x18c6e, event_type=0x18eca, palette_cursor=0x18cba,
          palette_toggle=0x18c5c, obj_shade=0x18c5e, scroll_frame=0x18cb2)


def _course_pokes(seed, extra):
    import random as _r
    rng = _r.Random(seed)
    p = {A_BUF_A_PTR: _l(BUF_A),
         BUF_A: bytes(rng.randrange(256) for _ in range(0x8000))}     # collision masks + course stream
    # road-geometry RAM the shuffles move (road_seg_data 0x18d1c, course ring 0x18ebc..0x190ac).
    p[0x18d1c] = bytes(rng.randrange(256) for _ in range(0x20))       # road_seg_data (8 longs)
    p[0x18ebc] = bytes(rng.randrange(256) for _ in range(0x220))      # obj_flags + ring + road_curve_tbl
    return p


def _check_course(label, seed, **st):
    st["view_flags"] = 0x10                    # forces the view-flags wrap -> section 12 (any rpm)
    st.setdefault("engine_rpm", 0xf)
    st.setdefault("scroll_phase", 0xe)
    st.setdefault("leg_flags_c90", 0x00500002)
    st.setdefault("input_state", 0)
    st.setdefault("course_row_ctr", 0x40)
    p = _pokes({k: v for k, v in st.items() if k in A})
    p.update(_course_pokes(seed, st))
    for k, v in st.items():                    # course-advance scalars
        if k in AC:
            p[AC[k]] = _w(v)
    # If pulling a record (course_row_ctr low), pin its marker word (rec+6) so the sprite-mode
    # dispatch is controlled. mode != 0 needs a negative marker (the cleanup zeroes it otherwise):
    # 0=none, 0x8200=scroll(2), 0x8400=palette(4). (leg_index 0 -> rec = BUF_A+0x5ce0-course_read_pos.)
    if st.get("course_row_ctr", 0x40) - 8 < 0:
        rec = BUF_A + 0x5ce0 - (st.get("course_read_pos", 0) + 8 & 0x1ff8)
        p[rec + 6] = _w(st.get("marker_w", 0))
    regs = {"_pokes": p}
    diffs, info = differential(ENTRY, regs, lambda lib, buf: lib.g_game_update(buf),
                               max_insns=2_000_000)
    return diffs, info


def test_course_else_branch():
    # No new course record (course_row_ctr high): shuffles + clear + build_road_geometry + fx + add_score.
    diffs, _ = _check_course("else", seed=1, course_row_ctr=0x40, event_type=0)
    assert not diffs, f"course-else\n{report(diffs[:24])}"


def test_course_pull_branch():
    # course_row_ctr low -> pull + unpack the next packed course record (the densest section-12 path).
    for seed in range(30):
        diffs, _ = _check_course("pull", seed=0x200 + seed, course_row_ctr=0,
                                 course_read_pos=(seed * 8) & 0x1ff8, event_type=0)
        assert not diffs, f"course-pull seed={seed}\n{report(diffs[:24])}"


def test_course_modes():
    # sprite-mode dispatch: scroll (marker 0x8200 -> mode 2) and palette (0x8400 -> mode 4).
    for mw in (0x8200, 0x8400):
        for seed in range(10):
            diffs, _ = _check_course("mode", seed=0x400 + mw + seed, course_row_ctr=0,
                                     course_read_pos=(seed * 8) & 0x1ff8, marker_w=mw, event_type=0)
            assert not diffs, f"course-mode {mw:#x} seed={seed}\n{report(diffs[:24])}"


def test_course_crash_and_input():
    # Exercise the crash-script body (collision_lock != 0, reads the real crash_anim_tbl), the
    # event_pending dispatch, and the throttle path (rpm changes) — all under the forced wrap.
    import random as _r
    rng = _r.Random(0x60CC)
    for i in range(80):
        diffs, _ = _check_course(f"ci{i}", seed=0x500 + i,
                                 engine_rpm=rng.choice([0xf, 0x20, 0x40, 0x50, 0x60]),
                                 input_state=rng.choice([0, 1, 3, 5, 9, 0x11, 0x80]),
                                 collision_lock=rng.choice([0, 0, 8, 0x10, 0x18, 0x20]),
                                 event_pending=rng.choice([0, 0, 1, 2, 3, 4, 5]),
                                 crash_phase=rng.choice([0, 1, 3]),
                                 curve_window=rng.choice([0, 0x30004000]),
                                 marker_w=rng.choice([0, 0x8200, 0x8400]),
                                 course_row_ctr=rng.choice([0, 0x40]),
                                 course_read_pos=rng.randrange(0, 0x2000) & 0x1ff8,
                                 event_type=rng.choice([0, 0x1a, 0x1d]))
        assert not diffs, f"course-crash/input seed={i}\n{report(diffs[:24])}"





