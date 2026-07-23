"""test_flow_machine.py — the between-legs FLOW state machine (slice B) vs recreate.

The host-side attract / leg-select flow that sequences slice A's draw surfaces around the race
pipeline. Each piece is differential-pinned against recreate's verified g_* export:

  check_abort          the attract abort poll                    (return-value fuzz)
  int_stepA / phaseB_leg / stepD_counter   the phase-counter arithmetic   (over the counter ranges)
  update_highscore     the ranking / row shift / insert          (directed score sets + fuzz)
  init_playfield_nav / _fire   the leg-select joystick nav        (leg x delays x dir x refill fuzz)

Then two composed checks: an attract CYCLE (phases A->D lockstep against the oracle slices) and a
GAME-FLOW drive (a leg times out -> update_highscore -> game_over++ -> intermission entry).

The name-entry tail of update_highscore is DEFERRED exactly as recreate defers it (IKBD-driven,
never runs to completion under the oracle). The Vsync / xbios_setpalette / flip / sound are off-image
seams (see flow.h).
"""
import random

import adapter
import equiv
import pytest


# ---- check_abort ----
def test_check_abort():
    lib = equiv._lib()
    rng = random.Random(2)
    cases = [(0x00, 0x00), (0x05, 0x05), (0x05, 0x00), (0x00, 0x42), (0x80, 0x01)]
    cases += [(rng.randint(0, 0xff), rng.randint(0, 0xff)) for _ in range(40)]
    for live, baseline in cases:
        # the high byte is noise — check_abort tests only the low byte (cmp.b).
        input_state = (rng.randint(0, 0xff) << 8) | live
        input_prev = (rng.randint(0, 0xff) << 8) | baseline
        cand, ref = equiv.compare_check_abort(lib, input_state, input_prev)
        assert cand == ref, f"live={live:#04x} baseline={baseline:#04x}: cand={cand:#x} ref={ref:#x}"


# ---- intermission phase-counter arithmetic ----
# Reuse one staged image (the oracle's stepA draws, so it needs the full intermission staging); each
# case copies it and re-pokes the counters.
_INT_BASE = None


def _int_image(**counters):
    global _INT_BASE
    if _INT_BASE is None:
        _INT_BASE = equiv.flow_background(leg=0, warmup=60)
    state = bytearray(_INT_BASE)
    for name, val in counters.items():
        equiv._w16(state, equiv._FLOW_FIELD[name][0], val & 0xffff)
    return state


# (timer, scroll, frame, expected ret) — recreate's Phase-A branch cases (abort staged by default).
STEPA_CASES = (
    (0x20, 0x30, 5, adapter.RM_INT_A_ABORT),   # below the gate: no scroll change
    (0x50, 0x30, 5, adapter.RM_INT_A_ABORT),   # in the gate: scroll advances
    (0x00, 0x30, 5, adapter.RM_INT_A_ABORT),   # timer underflow -> wrap to 0x5c (>= gate)
    (0x50, 0x00, 5, adapter.RM_INT_A_ABORT),   # scroll underflow -> dwell ticks (no break)
    (0x50, 0x00, 0, adapter.RM_INT_A_BREAK),   # scroll + dwell underflow -> break to Phase B
)


def test_int_stepA_branches():
    lib = equiv._lib()
    for timer, scroll, frame, expect in STEPA_CASES:
        # BREAK is decided before the abort check; for the others stage an abort so the return is
        # deterministic (input_state low byte present and != input_prev).
        img = _int_image(int_timer=timer, int_scroll=scroll, int_frame=frame,
                         input_state=0x01, input_prev=0x00)
        bad, ret_c, ret_r = equiv.compare_int_stepA(lib, img)
        assert not bad, f"timer={timer:#x} scroll={scroll:#x} frame={frame}: {bad}"
        assert ret_c == ret_r == expect, f"timer={timer:#x}: ret cand={ret_c} ref={ret_r} exp={expect}"


def test_int_stepA_no_abort():
    """CONTINUE when input matches the baseline (no fresh input): counters advance, no abort."""
    lib = equiv._lib()
    img = _int_image(int_timer=0x50, int_scroll=0x30, int_frame=5, input_state=0x07, input_prev=0x07)
    bad, ret_c, ret_r = equiv.compare_int_stepA(lib, img)
    assert not bad, str(bad)
    assert ret_c == ret_r == adapter.RM_INT_A_CONTINUE, f"ret cand={ret_c} ref={ret_r}"


def test_int_stepA_counter_sweep():
    """Sweep the timer across the gate edge and the scroll/frame across their underflows."""
    lib = equiv._lib()
    for timer in (0x48, 0x49, 0x4a, 0x5c, 0x00, 0x3b):
        for scroll in (0, 1, 0x40, 0x63):
            for frame in (0, 1, 0x14):
                img = _int_image(int_timer=timer, int_scroll=scroll, int_frame=frame,
                                 input_state=0x07, input_prev=0x07)   # no abort -> isolate arithmetic
                bad, ret_c, ret_r = equiv.compare_int_stepA(lib, img)
                assert not bad, f"timer={timer:#x} scroll={scroll:#x} frame={frame}: {bad}"
                assert ret_c == ret_r, f"timer={timer:#x} scroll={scroll:#x}: {ret_c} != {ret_r}"


def test_int_phaseB_leg():
    lib = equiv._lib()
    for sel in range(6):
        img = _int_image(leg_select=sel)
        bad = equiv.compare_int_phaseB_leg(lib, img)
        assert not bad, f"leg_select={sel}: {bad}"


# (int_frame_hi, leg_index, expected ret)
STEPD_CASES = (
    (0, 0, adapter.RM_INT_D_DRAW),        # dwell not elapsed
    (1, 0, adapter.RM_INT_D_DRAW),
    (0x18, 2, adapter.RM_INT_D_DRAW),     # hi+1 = 0x19 < 0x1a -> still draw
    (0x19, 2, adapter.RM_INT_D_ADVANCE),  # dwell elapsed, legs remain -> advance (init_leg_dash seam)
    (0x19, 4, adapter.RM_INT_D_RESTART),  # dwell elapsed, last leg -> restart
)


def test_int_stepD_counter():
    lib = equiv._lib()
    for hi, leg, expect in STEPD_CASES:
        img = _int_image(int_frame_hi=hi, leg_index=leg)
        bad, ret_c, ret_r = equiv.compare_int_stepD_counter(lib, img)
        assert not bad, f"hi={hi:#x} leg={leg}: {bad}"
        assert ret_c == ret_r == expect, f"hi={hi:#x} leg={leg}: ret cand={ret_c} ref={ret_r} exp={expect}"


# ---- update_highscore ----
_HS_BASE = None


def _hs_image(leg, score12, rows):
    global _HS_BASE
    if _HS_BASE is None:
        _HS_BASE = equiv.flow_background(leg=0, warmup=60)
    state = bytearray(_HS_BASE)
    equiv._w16(state, adapter.A_leg_index, leg)
    lo = adapter.A_hud_text + adapter.HS_SCORE_REC_OFF
    state[lo:lo + adapter.HS_SCORE_REC_BYTES] = bytes(score12)
    table = adapter.A_highscore_table + leg * adapter.HIGHSCORE_LEG_STRIDE
    state[table:table + len(rows)] = bytes(rows)
    return state


def _digits(s):
    return s.encode()


def test_update_highscore_directed():
    """New high / mid insert / no insert / full-table shift / last-row insert / leading-zero blank."""
    lib = equiv._lib()
    name = bytes(range(6))
    for leg in (0, 2, 4):
        rows = (_digits("500000") + b"\0" * 8) * adapter.HIGHSCORE_ROWS
        for score in ("900000", "100000", "500000", "050000"):
            bad = equiv.compare_update_highscore(lib, _hs_image(leg, _digits(score) + name, rows))
            assert not bad, f"leg={leg} score={score}: {bad}"
        # mid insert: rank 4 (beats rows 4..8, which are 100000)
        mid = (_digits("900000") + b"\0" * 8) * 4 + (_digits("100000") + b"\0" * 8) * 5
        bad = equiv.compare_update_highscore(lib, _hs_image(leg, _digits("500000") + name, mid))
        assert not bad, f"leg={leg} mid-insert: {bad}"
        # last-row insert (rank 8, zero-iteration shift)
        rows8 = (_digits("900000") + b"\0" * 8) * (adapter.HIGHSCORE_ROWS - 1) + _digits("100000") + b"\0" * 8
        bad = equiv.compare_update_highscore(lib, _hs_image(leg, _digits("500000") + name, rows8))
        assert not bad, f"leg={leg} last-row: {bad}"
        # top insert with 9 DISTINCT descending rows: the 8-row shift moves distinct records, so a
        # dropped/short shift is caught here (identical rows make a shift a visual no-op).
        distinct = bytearray()
        for r in range(adapter.HIGHSCORE_ROWS):
            distinct += _digits(f"{90 - r * 10:02d}0000") + bytes([r + 1] + [0] * 7)
        bad = equiv.compare_update_highscore(lib, _hs_image(leg, _digits("990000") + name, bytes(distinct)))
        assert not bad, f"leg={leg} distinct-shift: {bad}"


def test_update_highscore_fuzz():
    lib = equiv._lib()
    for seed in range(60):
        rng = random.Random(seed)
        score = bytes(rng.randrange(0x2f, 0x3a) for _ in range(6)) + bytes(rng.randrange(256) for _ in range(6))
        rows = bytearray()
        for _ in range(adapter.HIGHSCORE_ROWS):
            rows += bytes(rng.randrange(0x2f, 0x3a) for _ in range(6)) + bytes(rng.randrange(256) for _ in range(8))
        leg = seed % 5
        bad = equiv.compare_update_highscore(lib, _hs_image(leg, score, rows))
        assert not bad, f"seed={seed} leg={leg}: {bad}"


# ---- init_playfield leg-select ----
NAV_DIRS = (0, 1, 2, 4, 8, 1 | 8, 2 | 4)     # none / each direction / conflicting combos
NAV_DELAYS = (0, 1)                           # 0 -> expires (steps), 1 -> not yet


def _nav_image(leg, dec, inc, dirs, prev):
    # A minimal image suffices: nav reads/writes only the nav globals (read_joystick is a seam).
    state = bytearray(equiv.bench_frame.IMAGE_SIZE)
    equiv._w16(state, adapter.A_leg_index, leg)
    equiv._w16(state, adapter.A_leg_dec_delay, dec)
    equiv._w16(state, adapter.A_leg_inc_delay, inc)
    equiv._w16(state, adapter.A_input_state, dirs)
    equiv._w16(state, adapter.A_input_prev, prev)
    equiv._w16(state, adapter.A_idle_countdown, 0x100)   # distinct from the refill so a reload shows
    return state


def test_init_playfield_nav():
    lib = equiv._lib()
    for leg in range(5):
        for dec in NAV_DELAYS:
            for inc in NAV_DELAYS:
                for dirs in NAV_DIRS:
                    for prev in (dirs, dirs ^ 1):    # equal (no refill) and differing (refill)
                        bad = equiv.compare_init_playfield_nav(lib, _nav_image(leg, dec, inc, dirs, prev))
                        assert not bad, (f"leg={leg} dec={dec} inc={inc} dirs={dirs:#x} prev={prev:#x}: {bad}")


FIRE = 0x80
FIRE_CASES = (
    (0x00, FIRE, 1),          # fresh press -> start
    (FIRE, FIRE, 0),          # held -> keep waiting
    (FIRE, 0x00, 0),          # released -> keep waiting
    (0x00, 0x00, 0),          # no fire -> keep waiting
    (0x00, FIRE | 4, 1),      # fresh press with a direction also held -> start
)


def test_init_playfield_fire():
    lib = equiv._lib()
    for prev, state, expect in FIRE_CASES:
        cand, ref = equiv.compare_init_playfield_fire(lib, state, prev)
        assert cand == ref == expect, f"prev={prev:#x} state={state:#x}: cand={cand} ref={ref} exp={expect}"


# ---- composed: the attract cycle (phases A -> D) ----
def test_attract_cycle(capsys):
    lib = equiv._lib()
    image = equiv.flow_background(leg=0, warmup=60)
    mism, stats = equiv.compare_attract_cycle(lib, image)
    with capsys.disabled():
        print(f"  attract cycle: {stats}")
    assert not mism, f"attract cycle diverged from the oracle slices: {mism[:12]}"
    assert stats["breakA"] == 1, f"Phase A never broke to B: {stats}"
    # Phase D shows legs 0..4: leg 0 is drawn first, then 4 ADVANCEs (to 1,2,3,4), then RESTART.
    assert stats["advances"] == 4, f"Phase D carousel did not advance through all 5 legs: {stats}"
    assert stats["restart"] == 1, f"Phase D never restarted the cycle: {stats}"


# ---- composed: the end-to-end game flow (leg end -> highscore -> game_over -> intermission entry) ----
@pytest.mark.parametrize("leg", [0, 1])
def test_game_flow(leg, capsys):
    lib = equiv._lib()
    mism, stats = equiv.compare_game_flow(lib, leg)
    with capsys.disabled():
        print(f"  game flow leg={leg}: {stats}")
    assert stats["ref_end"] >= 0 and stats["cand_end"] >= 0, f"the leg never ended: {stats}"
    assert not mism, f"game flow diverged from the oracle break sequence (leg={leg}): {mism[:12]}"
