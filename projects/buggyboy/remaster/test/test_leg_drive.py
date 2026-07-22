"""test_leg_drive.py — free-running leg drive: remaster's own game loop vs recreate's, from the start.

Where test_player.py re-seeds the candidate from the reference every frame (so it measures one frame
of physics at a time), this drives a leg the way the game does: the candidate is seeded ONCE from the
leg-start image and thereafter advances itself — physics, the course advance its view-wrap triggers,
the road geometry and the scroll whose hscroll_step2 feeds back into the curve. Drift therefore
accumulates instead of being erased, which is the only way a self-driving remaster gets proven.

The drives run from `init_leg` with no warmup, i.e. the state the player actually starts a leg in.
They are long enough to crash: every script here reaches the roadside-object collisions the course
dispatches, so the ported §6 crash / auto-steer script plays out and hands the controls back under
comparison. Nothing is handed over: the candidate runs the real event engine, so it arms its own
crashes and every frame is compared strictly, free-running — see equiv.compare_leg_drive.
"""
import adapter
import equiv
import pytest

ACCEL, BRAKE, LEFT, RIGHT, FIRE = 0x01, 0x02, 0x04, 0x08, 0x80
FRAMES = 600

# name -> per-frame input masks. Each has to survive crashes, so each exercises the crash script.
DRIVES = {
    "flat_out": [ACCEL] * FRAMES,
    "slalom": [ACCEL | (LEFT if (f // 50) % 2 else RIGHT) for f in range(FRAMES)],
    "lift_and_brake": [ACCEL if f % 90 < 60 else BRAKE if f % 90 < 75 else 0 for f in range(FRAMES)],
    "hard_left": [ACCEL | LEFT] * FRAMES,
}


@pytest.mark.parametrize("leg", [0, 1, 4])
@pytest.mark.parametrize("drive", sorted(DRIVES))
def test_leg_drive_tracks_recreate(leg, drive, capsys):
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES[drive])
    with capsys.disabled():
        print(f"  leg={leg} {drive}: {len(mismatches)} mismatches / {stats}")
    assert not mismatches, "leg drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["wraps"] > 0, f"the buggy never moved: {stats}"


SPIN_FRAMES = 40
LOCK_LEFT = [ACCEL | LEFT] * SPIN_FRAMES
LOCK_RIGHT = [ACCEL | RIGHT] * SPIN_FRAMES

# (name, which override is armed, held lock) -> the reference decides spin vs settle from the pair.
# Holding one lock against spin_reset throws the buggy into the canned spin; the other settles it,
# and swapping the two overrides swaps which lock does which. All four combinations are pinned.
SPIN_CASES = {
    "reset_left": ({adapter.A_spin_reset: 0x19}, LOCK_LEFT),
    "reset_right": ({adapter.A_spin_reset: 0x19}, LOCK_RIGHT),
    "word2_left": ({adapter.A_spin_reset + 2: 0x19}, LOCK_LEFT),
    "word2_right": ({adapter.A_spin_reset + 2: 0x19}, LOCK_RIGHT),
}


@pytest.mark.parametrize("case", sorted(SPIN_CASES))
@pytest.mark.parametrize("leg", [0, 1])
def test_spin_arming_matches_recreate(leg, case, capsys):
    """§10's spin arming, which the leg drives cannot reach — an armed override and a held lock never
    coincide there. Staged directly so the direction of the spin is pinned against recreate rather
    than assumed; without this, swapping spin_lock/settle_lock leaves the whole suite green."""
    override, inputs = SPIN_CASES[case]
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    # steer_hold starts past the threshold so the very first frame is already a decision.
    pokes = dict(override)
    pokes[adapter.A_steer_hold] = 0x20
    mismatches, stats = equiv.compare_spin_arming(lib, image, pokes, inputs)
    with capsys.disabled():
        print(f"  leg={leg} {case}: {len(mismatches)} mismatches / {stats}")
    assert not mismatches, "spin arming diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["spun"] + stats["settled"] > 0, f"{case} never reached a decision at all: {stats}"


def test_spin_arming_reaches_both_outcomes(capsys):
    """The four cases together must produce BOTH outcomes — if every case merely settled, the arming
    body would still be dead code and the per-case test above would pass vacuously."""
    lib = equiv._lib()
    image = equiv.leg_start_background(1)
    totals = {"spun": 0, "settled": 0}
    for case, (override, inputs) in sorted(SPIN_CASES.items()):
        pokes = dict(override)
        pokes[adapter.A_steer_hold] = 0x20
        mismatches, stats = equiv.compare_spin_arming(lib, image, pokes, inputs)
        assert not mismatches, f"{case} diverged"
        for k in totals:
            totals[k] += stats[k]
    with capsys.disabled():
        print(f"  totals across the four cases: {totals}")
    assert totals["spun"] > 0, f"no case ever armed the spin — arming body still untested: {totals}"
    assert totals["settled"] > 0, f"no case ever settled — the settle branch is untested: {totals}"


# A leg that idles to the bonus-clock time-out, then ends. The clock is shortened (a leg really starts
# at 0x46, one unit per 0xb frames — measured, not guessed) so the drive is quick; the input idles (no
# throttle) so nothing moves and the time-out is the only thing that fires. The slower (bonus-tally)
# path reaches leg end by ~124 frames (the timeout path by ~71); 140 clears both with a small margin.
LEG_END_FRAMES = 140


@pytest.mark.parametrize("leg", [0, 1])
def test_leg_ends_on_timeout(leg, capsys):
    """The first organic leg END: idle until §4 arms hud_crash_timer (0x5b) at the time-out, HUD phase
    8 decays it, and once negative the crash-fx tally — with no crash active — arms abort_flag = 0xffff,
    which the frame loop reads as the leg's end. Driven free-running on both sides; the candidate arms
    abort on the same frame the reference does (abort_flag / crash_frame compared every frame)."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    equiv._w16(image, adapter.A_time_left, 6)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [0] * LEG_END_FRAMES)
    with capsys.disabled():
        print(f"  leg={leg}: {stats}")
    assert not mismatches, "leg-end timeout drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["abort_armed"] > 0, f"abort_flag never armed — the tally never ran: {stats}"
    assert stats["leg_over"] > 0, f"the leg never ended (abort_flag never went negative): {stats}"


@pytest.mark.parametrize("leg", [0, 1])
def test_leg_ends_via_bonus_tally(leg, capsys):
    """The bonus-tally path to leg end: same time-out, but with a crash tally active. Once the timer
    goes negative the tally drains what little is left, arms the 0x33 abort countdown, and decays it
    past zero to end the leg — the drain -> 0x33 -> countdown branch, free-running under strict
    comparison every frame."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    equiv._w16(image, adapter.A_time_left, 3)
    equiv._w16(image, adapter.A_crash_active, 1)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [0] * LEG_END_FRAMES)
    with capsys.disabled():
        print(f"  leg={leg}: {stats}")
    assert not mismatches, "bonus-tally leg-end drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["abort_armed"] > 0, f"abort_flag never armed — the tally never ran: {stats}"
    assert stats["leg_over"] > 0, f"the leg never ended (abort_flag never went negative): {stats}"


@pytest.mark.parametrize("leg", [0, 1])
def test_section1_clears_pending_marker(leg, capsys):
    """§1's marker gate closes the raise/consume loop: a marker the crash script raised one frame must
    be CONSUMED (marker_pending cleared) the next. Staged by poking marker_pending nonzero at a leg
    start and idling (so §6 never re-arms it): recreate's §1 zeroes it, and the candidate must too —
    without apply_marker_gate the candidate keeps the stale marker while the reference clears it, a
    mismatch this drive fails on (mutation-verified). The leg drives above never organically hit the
    raise-then-idle sequence, so this pins the branch they leave dead."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    assert image[adapter.A_marker_pending] == 0, "expected a clean leg start"
    image[adapter.A_marker_pending] = 0x05                     # a raised marker awaiting §1's consume
    mismatches, _stats = equiv.compare_leg_drive(lib, image, [0] * 4)
    with capsys.disabled():
        print(f"  leg={leg}: {len(mismatches)} mismatches")
    assert not mismatches, "the pending-marker gate diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])


@pytest.mark.parametrize("leg", [0, 1, 4])
def test_crash_script_plays_out_and_returns_control(leg, capsys):
    """The point of §6: a crash the course threw at us must play out frame for frame and then GIVE THE
    CONTROLS BACK. Asserting the handoff is what stops a script that merely freezes from passing."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES["slalom"])
    with capsys.disabled():
        print(f"  leg={leg}: {stats}")
    assert not mismatches
    assert stats["armed"] > 0, f"no crash was ever armed, so §6 went untested: {stats}"
    assert stats["crash_frames"] > stats["armed"], f"the script never ran past its first frame: {stats}"
    assert stats["handoffs"] > 0, f"the script never handed the controls back: {stats}"
