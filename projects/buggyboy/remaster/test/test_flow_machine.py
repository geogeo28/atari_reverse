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


# ---- composed: the FLOW COMPOSITION driver (slice D) vs the oracle + a structural mirror ----
# The between-legs driver hoisted into src/flow.c (rm_flow_intermission_cycle / rm_flow_intermission /
# rm_flow_leg_select / rm_flow_game_over) is run on the host with recording FlowOps callbacks. Two
# guarantees, kept distinct:
#   - the counter VALUES route through the verified in-image oracle slices (g_int_stepA / g_int_phaseB_leg
#     / g_int_stepD_counter / g_check_abort / g_init_playfield_*): every flow counter at each callback is
#     compared against them, so a counter-arithmetic divergence fails hard;
#   - the SEQUENCING (draw / palette / show order, the phase-loop structure, the event emission) is pinned
#     against a HAND-WRITTEN Python structural mirror (_mirror_int_cycle / _mirror_leg_select) — NOT against
#     g_intermission itself. It catches a ONE-SIDED mutation (four were demonstrated caught below), but an
#     ordering error authored identically into both the C driver and the mirror would pass.
# Of the four correctness bugs that historically escaped, only the idle-hang and Esc/Q-unreachable classes
# live in this now-lockstepped driver code. The leg-start marker reseed (start_leg -> op_start_demo_leg,
# a host stub here) and the menu-race palette (set in main() after rm_flow_leg_select returns) are NOT in
# the driver and remain guarded only by the on-target GAME_FLOW_AUTO flow trace + the frame-0 golden.

# A HARNESS-ONLY shortened tuning: the seeds are chosen purely for test speed (Phase A breaks in ~6
# frames, Phase C is 6 demo frames, the leg-select idle is short — a whole cycle runs in-test), NOT the
# on-target debug knobs. It is distinct from BOTH the shipping RM_FLOW_TUNING_DEFAULT (the real attract
# timing — see _default_tuning) and game_main's GAME_FLOW_FAST ({scroll=1, frame=0, timer=0x4b, idle=8}).
def _fast_tuning(**over):
    base = dict(prologue_scroll=4, prologue_frame=1, prologue_timer=adapter.INT_TIMER_WRAP,
                phase_c_frames=6, idle_init=0x40, flash_frames=3)   # 3 flash frames: enough to pin the count
    base.update(over)
    return adapter.FlowTuning(**base)


# The SHIPPING attract tuning (include/flow.h RM_FLOW_TUNING_DEFAULT), built from the pinned adapter
# constants (test_python_constants_match_the_c pins each equal to its C #define) — no hand-copied literal.
def _default_tuning():
    return adapter.FlowTuning(prologue_scroll=adapter.INT_SCROLL_INIT, prologue_frame=adapter.INT_FRAME_INIT,
                              prologue_timer=adapter.INT_TIMER_INIT, phase_c_frames=adapter.INT_C_FRAMES,
                              idle_init=adapter.IP_IDLE_INIT, flash_frames=adapter.IP_FLASH_FRAMES)


def _bg():
    return equiv.flow_background(leg=0, warmup=60)


EVT = adapter  # RM_FLOW_EVT_* live on adapter
# The attract cycle's phase-event fingerprint: prologue, Phase-A break, Phase B pick, Phase C done, then
# the Phase-D carousel advancing through legs 1..4 and restarting (== the on-target flow trace).
CYCLE_EVENTS = [
    EVT.RM_FLOW_EVT_INT_PROLOGUE, EVT.RM_FLOW_EVT_INT_PHASEA_BREAK, EVT.RM_FLOW_EVT_INT_PHASEB,
    EVT.RM_FLOW_EVT_INT_PHASEC_DONE, EVT.RM_FLOW_EVT_INT_PHASED_ADVANCE, EVT.RM_FLOW_EVT_INT_PHASED_ADVANCE,
    EVT.RM_FLOW_EVT_INT_PHASED_ADVANCE, EVT.RM_FLOW_EVT_INT_PHASED_ADVANCE, EVT.RM_FLOW_EVT_INT_PHASED_RESTART,
]


def test_flow_driver_intermission_cycle(capsys):
    """One full attract cycle A->B->C->D locksteps vs the oracle: 0 divergences, the phase-event
    sequence and the palette order match, every drawn frame is flipped (draws == shows), and Phase C
    runs exactly phase_c_frames demo frames."""
    lib = equiv._lib()
    tuning = _fast_tuning()
    mism, stats = equiv.compare_flow_intermission_cycle(lib, _bg(), tuning)
    with capsys.disabled():
        print(f"  intermission cycle: {stats}")
    assert not mism, f"the hoisted driver diverged from the oracle: {mism[:6]}"
    assert stats["result"] == adapter.RM_FLOW_CONTINUE, stats["result"]
    assert stats["events"] == CYCLE_EVENTS, stats["events"]
    # palette order: attract-scroll palette in the prologue, then the leg-select palette for Phase D.
    assert stats["palettes"] == [adapter.RM_FLOW_PAL_INT_A, adapter.RM_FLOW_PAL_LEG_SELECT], stats["palettes"]
    # flip parity: prologue + Phase A + Phase D draw and flip in lockstep (a dropped/extra show breaks it).
    assert stats["draws"] == stats["shows"] and stats["draws"] > 0, (stats["draws"], stats["shows"])
    assert stats["run_demo"] == tuning.phase_c_frames, (stats["run_demo"], tuning.phase_c_frames)


def test_flow_driver_intermission_cycle_default_tuning(capsys):
    """The full attract cycle under the SHIPPING RM_FLOW_TUNING_DEFAULT (the real prologue seeds, the
    0x96-frame Phase C, the real leg-select idle) locksteps vs the oracle mirror — same phase-event and
    palette fingerprint as the fast cycle. The demo-frame callbacks are host stubs so the full-length
    cycle is cheap (Phase A breaks in ~a few hundred counter steps, Phase C is INT_C_FRAMES stubbed
    frames), which is exactly the timing the shell ships but never exercises under `make test` otherwise."""
    lib = equiv._lib()
    tuning = _default_tuning()
    mism, stats = equiv.compare_flow_intermission_cycle(lib, _bg(), tuning)
    with capsys.disabled():
        print(f"  intermission cycle (default tuning): {stats}")
    assert not mism, f"the hoisted driver diverged from the oracle under the shipping tuning: {mism[:6]}"
    assert stats["result"] == adapter.RM_FLOW_CONTINUE, stats["result"]
    assert stats["events"] == CYCLE_EVENTS, stats["events"]
    assert stats["palettes"] == [adapter.RM_FLOW_PAL_INT_A, adapter.RM_FLOW_PAL_LEG_SELECT], stats["palettes"]
    assert stats["draws"] == stats["shows"] and stats["draws"] > 0, (stats["draws"], stats["shows"])
    assert stats["run_demo"] == tuning.phase_c_frames == adapter.INT_C_FRAMES, stats["run_demo"]


def test_flow_driver_intermission_multi_cycle():
    """rm_flow_intermission runs attract cycles until a quit: cycle 1 completes (RESTART), the driver
    loops back into a second prologue, then a quit unwinds it — locksteped throughout."""
    lib = equiv._lib()
    # cycle 1 quit-checks ~137 times; a quit past that lands in cycle 2, after a full first cycle.
    mism, stats = equiv.compare_flow_intermission(lib, _bg(), _fast_tuning(), quit_of=lambda i: i >= 140)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_QUIT, stats["result"]
    assert stats["events"].count(EVT.RM_FLOW_EVT_INT_PHASED_RESTART) == 1, stats["events"]
    assert stats["events"][-1] == EVT.RM_FLOW_EVT_INT_PROLOGUE, stats["events"][-1]   # into cycle 2


# (target phase, the poll index that first lands in it for _fast_tuning, the INT_ABORT aux code). Phase
# A polls at pi 0..5 (6 frames), Phase C at pi 6..10 (5 frames), Phase D from pi 11. The aux assertion
# below fails loudly if a tuning change shifts these, so the indices are self-checking.
ABORT_CASES = ((2, 0), (8, 1), (11, 2))


@pytest.mark.parametrize("poll_idx,aux", ABORT_CASES)
def test_flow_driver_abort_each_phase(poll_idx, aux):
    """A fresh input aborts the attract in each polling phase (A / C / D): the driver returns ABORT with
    the phase's INT_ABORT aux, matching the oracle's check_abort verdict frame for frame."""
    lib = equiv._lib()
    fresh = 0x05   # a low byte present and != the idle baseline (0) -> check_abort fires
    poll_of = lambda i: fresh if i == poll_idx else 0
    mism, stats = equiv.compare_flow_intermission_cycle(lib, _bg(), _fast_tuning(), poll_of=poll_of)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_ABORT, stats["result"]
    # The INT_ABORT aux code (0=Phase A, 1=Phase C, 2=Phase D) pins WHICH phase aborted; a tuning change
    # that shifted the poll index into another phase would fail here. Recover it from the driver's log.
    assert _abort_aux(lib, poll_of) == aux, f"aborted in the wrong phase (aux != {aux})"


def _abort_aux(lib, poll_of):
    """Run the driver alone with recording callbacks; return the aux of the INT_ABORT event it emitted."""
    fs = adapter.flow_state(_bg())
    rec = equiv._DriverRecorder(fs, equiv._FlowScript(poll_of, lambda i: 0, lambda i: -1))
    lib.rm_flow_intermission_cycle(equiv.ctypes.byref(fs), equiv.ctypes.byref(rec.ops), None,
                                   equiv.ctypes.byref(_fast_tuning()))
    for kind, args, _snap in rec.log:
        if kind == "event" and args[0] == adapter.RM_FLOW_EVT_INT_ABORT:
            return args[2]
    return None


@pytest.mark.parametrize("quit_idx", [2, 8, 11])
def test_flow_driver_quit_each_phase(quit_idx):
    """Q (quit_requested) unwinds the attract from every phase that polls it (A / C / D): the driver
    returns QUIT immediately. This is the path bug #3 (Esc/Q unreachable from menus) lived in."""
    lib = equiv._lib()
    mism, stats = equiv.compare_flow_intermission_cycle(
        lib, _bg(), _fast_tuning(), quit_of=lambda i: i == quit_idx)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_QUIT, stats["result"]


def test_flow_driver_leg_select_fire():
    """The leg-select loop starts a leg on a fresh fire press (rm_init_playfield_fire), returning START,
    locksteped vs g_init_playfield's fire edge."""
    lib = equiv._lib()
    FIRE = 0x80
    mism, stats = equiv.compare_flow_leg_select(
        lib, _bg(), _fast_tuning(), poll_of=lambda i: FIRE if i >= 2 else 0)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["events"] == [EVT.RM_FLOW_EVT_SELECT_ENTER, EVT.RM_FLOW_EVT_SELECT_FIRE], stats["events"]
    # leg select shows the results screen under the leg-select palette every frame it draws.
    assert set(stats["palettes"]) == {adapter.RM_FLOW_PAL_LEG_SELECT}, stats["palettes"]
    assert stats["draws"] == stats["shows"] and stats["draws"] > 0, (stats["draws"], stats["shows"])


def test_flow_driver_leg_select_fkey():
    """An F1..F5 direct pick starts that leg at once (SELECT_FIRE aux 1), before any nav/draw."""
    lib = equiv._lib()
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), _fast_tuning(), fkey_of=lambda i: 3 if i >= 1 else -1)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["events"] == [EVT.RM_FLOW_EVT_SELECT_ENTER, EVT.RM_FLOW_EVT_SELECT_FIRE], stats["events"]


def test_flow_driver_get_ready_flash(capsys):
    """The fire-start "get ready" (ip_start_leg): starting a leg redraws the results + the leg-name menu
    twice, adds the dashboard labels, then flashes the palette exactly tuning.flash_frames frames — all
    locksteped vs the oracle mirror. Pins draw_panel5 (leg select redraw + the two get-ready frames), the
    single draw_leg_labels, and the flash length. A dropped panel5, a dropped flash frame, or a wrong
    flash length in the driver diverges from the mirror (mutation-verified)."""
    lib = equiv._lib()
    tuning = _fast_tuning(flash_frames=5)
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), tuning, poll_of=lambda i: 0x80 if i >= 2 else 0)
    with capsys.disabled():
        print(f"  get-ready: panel5={stats['panel5']} labels={stats['leg_labels']} flash={stats['flash']}")
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["flash"] == tuning.flash_frames == 5, stats["flash"]
    assert stats["leg_labels"] == 1, stats["leg_labels"]      # ip_start_leg draws the labels once
    # panel5 is drawn on every leg-select redraw (>=1 nav frame before fire) AND twice in the get-ready.
    assert stats["panel5"] >= 3, stats["panel5"]


def test_flow_driver_leg_select_f6_preview():
    """F6 in the leg select (ip_menu @0x2b86) previews the race-end results screen, waits (a shell op), then
    redraws the leg-select screen and drops to the nav tail — SKIPPING that frame's default redraw. A later
    fire starts the leg. Locksteped vs the oracle mirror; pins the preview draw + palette + wait sequence."""
    lib = equiv._lib()
    # F6 on the first menu read, then no key; fire on the 2nd frame so the loop terminates in START.
    fkey_of = lambda i: adapter.RM_FKEY_F6 if i == 0 else adapter.RM_FKEY_NONE
    poll_of = lambda i: FIRE if i >= 1 else 0
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), _fast_tuning(), poll_of=poll_of, fkey_of=fkey_of)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["preview"] == 1 and stats["res_screen"] == 1, (stats["preview"], stats["res_screen"])
    # the preview draws the results screen under the RESULTS palette then restores the leg-select palette.
    assert adapter.RM_FLOW_PAL_RESULTS in stats["palettes"], stats["palettes"]
    # flip parity: every paint flips — the leg-select redraws (draws) AND the preview's results screen.
    assert stats["shows"] == stats["draws"] + stats["res_screen"] and stats["shows"] > 0, (stats["draws"], stats["shows"])


def test_flow_driver_leg_select_f10_reload():
    """F10 + RETURN (ip_menu @0x2b36) draws the reload prompt (panel3), takes a blocking confirm, and on
    RETURN reloads the assets (panel2 ×2 + reload_assets) then falls to the default redraw. Locksteped vs
    the oracle mirror."""
    lib = equiv._lib()
    fkey_of = lambda i: adapter.RM_FKEY_F10 if i == 0 else adapter.RM_FKEY_NONE
    confirm_of = lambda i: adapter.RM_FKEY_RETURN            # RETURN confirms the reload
    poll_of = lambda i: FIRE if i >= 1 else 0            # fire on the next frame to end the loop
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), _fast_tuning(),
                                                poll_of=poll_of, fkey_of=fkey_of, confirm_of=confirm_of)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["reload"] == 1, stats["reload"]            # the reload ran exactly once
    assert stats["panel3"] == 1 and stats["panel2"] == 2, (stats["panel3"], stats["panel2"])


def test_flow_driver_leg_select_f10_declined_falls_through_to_fkey():
    """F10 then a non-RETURN key falls through to the F-key test (ip_menu @0x2b7c): F10 then F3 (code 2)
    starts leg 2, with NO reload. Locksteped vs the oracle mirror, and the started leg is read directly."""
    lib = equiv._lib()
    F3_CODE = 2                                             # F3 -> leg index 2 (scancode - F1)
    fkey_of = lambda i: adapter.RM_FKEY_F10 if i == 0 else adapter.RM_FKEY_NONE
    confirm_of = lambda i: F3_CODE                          # the reload prompt read returns F3, not RETURN
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), _fast_tuning(),
                                                fkey_of=fkey_of, confirm_of=confirm_of)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]
    assert stats["reload"] == 0 and stats["panel2"] == 0, (stats["reload"], stats["panel2"])
    assert stats["panel3"] == 1, stats["panel3"]           # the prompt drew, but the reload declined
    assert stats["events"] == [EVT.RM_FLOW_EVT_SELECT_ENTER, EVT.RM_FLOW_EVT_SELECT_FIRE], stats["events"]
    # Directly pin that the fall-through started leg 2 (run the driver alone and read fs->leg_index).
    assert _leg_select_started_leg(lib, fkey_of, confirm_of) == F3_CODE


def _leg_select_started_leg(lib, fkey_of, confirm_of):
    """Run rm_flow_leg_select alone with recording callbacks; return the leg it started (fs->leg_index)."""
    img = _bg()
    fs = adapter.flow_state(img)
    snd = adapter.sound_driver(img)
    rec = equiv._DriverRecorder(fs, equiv._FlowScript(lambda i: 0, lambda i: 0, fkey_of, confirm_of))
    lib.rm_flow_leg_select(equiv.ctypes.byref(fs), equiv.ctypes.byref(rec.ops), None,
                           equiv.ctypes.byref(_fast_tuning()), equiv.ctypes.byref(snd))
    return fs.leg_index


def test_flow_driver_leg_select_nav():
    """Holding a direction steps leg_index through g_init_playfield_nav (auto-repeat delays + reload),
    then fire starts the navigated-to leg — the whole nav trajectory locksteped vs the oracle."""
    lib = equiv._lib()
    RIGHT, FIRE = 0x08, 0x80
    def poll(i):
        if i < 12:
            return RIGHT      # step toward later legs (auto-repeat)
        return 0 if i == 12 else FIRE   # release then a fresh fire edge
    mism, stats = equiv.compare_flow_leg_select(lib, _bg(), _fast_tuning(), poll_of=poll)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_START, stats["result"]


def test_flow_driver_leg_select_idle_intermission():
    """Idling past the countdown runs one GAME-OVER-BRACKETED attract cycle (game_over_flag 0->1 around
    the intermission, then 0), then Q unwinds the whole thing. Pins the leg-select -> attract path
    and the enter/exit bracket, locksteped against the oracle (incl. game_over_flag in the snapshot)."""
    lib = equiv._lib()
    # idle_init=8 -> the leg select idles 9 frames (9 quit-checks, qi 0..8) then enters the intermission;
    # a quit at qi>=9 lands in the intermission's Phase A and unwinds through the game-over exit.
    mism, stats = equiv.compare_flow_leg_select(
        lib, _bg(), _fast_tuning(idle_init=8), quit_of=lambda i: i >= 9)
    assert not mism, mism[:6]
    assert stats["result"] == adapter.RM_FLOW_QUIT, stats["result"]
    assert stats["events"][:3] == [EVT.RM_FLOW_EVT_SELECT_ENTER, EVT.RM_FLOW_EVT_SELECT_IDLE,
                                   EVT.RM_FLOW_EVT_INT_PROLOGUE], stats["events"]
