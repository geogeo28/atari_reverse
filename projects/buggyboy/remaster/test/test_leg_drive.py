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


def test_leg_drive_from_native_init(capsys):
    """The same free-running drive, but the candidate's leg-start state comes from rm_init_leg run
    natively (native_init_pre) instead of the oracle's init_leg seed. Staying strict-green proves the
    native leg START is drive-equivalent — a leg begun by rm_init_leg evolves identically to one begun
    by the oracle. The reference is still g_game_update on the oracle's leg-start image.

    ONE representative (leg, drive) is enough here: this is the end-to-end WIRING pin (rm_init_leg feeds
    a real drive). The per-leg leg-start equivalence itself is pinned exactly, over all legs 0-4 and
    both fresh/re-init, by test_init_leg's differential vs g_init_leg."""
    leg, drive = 1, "slalom"
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    pre = equiv.leg_start_pre_init(leg)
    mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES[drive], native_init_pre=pre)
    with capsys.disabled():
        print(f"  leg={leg} {drive} (native init): {len(mismatches)} mismatches / {stats}")
    assert not mismatches, "native-init leg drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["wraps"] > 0, f"the buggy never moved: {stats}"


def test_attract_demo_is_silent(capsys):
    """The attract demo runs a leg with game_over SET — the original brackets the intermission with
    game_over_flag != 0 (main @0x10100:314), and the shell's op_start_demo_leg raises the demo player's
    game_over to match. Every in-race sound trigger then bails on game_over and §1's engine-sound enable
    goes to EGOFF, so the demo is SILENT: no engine EG armed, no idle Dosound, no INITFX on a demo crash.

    Stage game_over on BOTH sides (the image's A_game_over_flag, read into the reference's g_game_update
    AND the candidate's p->game_over / ctx->game_over) and drive: the SND_STATE + VBL enable + cur_tune
    track reset-identical (a strict-green drive) and both Dosound ledgers stay EMPTY. Re-zeroing the demo
    game_over would arm the EG / log Dosound(idle) / INITFX on a crash and diverge this (mutation-caught)."""
    lib = equiv._lib()
    image = equiv.leg_start_background(0)
    equiv._w16(image, adapter.A_game_over_flag, 1)          # the game-over-bracketed attract demo
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * 200)
    with capsys.disabled():
        print(f"  demo-silence: {len(mismatches)} mismatches / {stats}")
    assert not mismatches, "game-over demo drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    cand_led, ref_led = equiv._dosound_streams(lib)
    assert cand_led == ref_led == [], f"the game-over demo emitted Dosounds: cand={cand_led} ref={ref_led}"


# Directed record-driven mode-2/4/6 course events (game_update §12's tail, rm_course_mode_event). The
# free drives above reach mode 4 (legs 0/1) and mode 6 (legs 0/4) organically — see the mode2/4/6 stats
# — but read_pos advances too slowly (the buggy keeps crashing) to reach mode 2, whose earliest record
# is deep in every leg's stream. Each case pokes course_read_pos so the FIRST view-wrap pulls the chosen
# mode's earliest record, then drives ACCEL long enough to fire and COMPARE it against recreate's
# g_game_update (the drive already pins scroll_frame / palette_cursor / palette_toggle / obj_shade /
# screen_offset / the staged palette). Read positions from the leg-stream mode scan.
MODE_CASES = {
    "mode2_leg3": (3, 1360, "mode2"),   # screen-offset event (mutates screen_offset, a render surface)
    "mode2_leg4": (4, 1056, "mode2"),
    "mode4_leg0": (0, 376, "mode4"),    # palette stage + obj_shade
    "mode6_leg0": (0, 336, "mode6"),    # tunnel per-register poke (palette_toggle flip)
    "mode6_leg4": (4, 304, "mode6"),
}


@pytest.mark.parametrize("case", sorted(MODE_CASES))
def test_course_mode_event_matches_recreate(case, capsys):
    leg, read_pos, mode = MODE_CASES[case]
    lib = equiv._lib()
    image = bytearray(equiv.leg_start_background(leg))
    equiv._w16(image, adapter.A_course_read_pos, read_pos - 8)   # +8 on the first pull -> read_pos
    equiv._w16(image, adapter.A_course_row_ctr, 0)               # underflow on the first wrap -> pull
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * 90)
    with capsys.disabled():
        counts = {k: stats[k] for k in ("mode2", "mode4", "mode6")}
        print(f"  {case}: {len(mismatches)} mismatches / mode-counts {counts}")
    assert not mismatches, "mode-event drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats[mode] >= 1, f"{case} never fired {mode} (nothing pinned): {stats}"


@pytest.mark.parametrize("case", [c for c, v in sorted(MODE_CASES.items()) if v[2] == "mode2"])
def test_mode2_scroll_prebuild_matches_recreate(case, capsys):
    """The mode-2 event's RE-PREBUILT scroll pixels, not just its screen_offset scalar. When a mode-2
    event moves screen_offset the shell re-runs rm_scroll_prebuild from the new offset before the next
    blit (game_main.c course_mode_event); test_course_mode_event above pins only the scalar. This drives
    to the mode-2 event, then re-prebuilds from the new offset and blits, and compares the whole
    framebuffer byte-exact against recreate's g_blit_road_scroll at that state (compare_scroll's path)."""
    leg, read_pos, _mode = MODE_CASES[case]
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    fired, diff, scalars_ok = equiv.compare_mode2_scroll(lib, image, read_pos)
    with capsys.disabled():
        print(f"  {case}: fired={fired} diff={diff} scalars_ok={scalars_ok}")
    assert fired, f"{case} never fired a mode-2 event (screen_offset never moved) — nothing pinned"
    assert diff == 0, f"{case} re-prebuilt scroll differs from recreate in {diff} bytes"
    assert scalars_ok, f"{case} hscroll_pos / hscroll_step2 outputs differ from recreate"


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


def test_fanout_tracks_recreate_and_reaches_nonzero(capsys):
    """The draw-struct fan-out (rm_apply_player) the shell runs after every frame — the seam that used
    to MISS four SpriteState fields, so the dirt/wheel sprite stayed on the road during a jump. The leg
    drive now runs the fan-out each frame and pins sprite.anim_frame / spin_state / spin_reset /
    collision_lock against the recreate image bytes (folded into compare_leg_drive's per-frame check).

    This asserts the pin is NON-VACUOUS: over the crash (slalom) drives the crash/spin script drives
    anim_frame, spin_state and collision_lock off zero at some point, so the aliasing is pinned against
    real values rather than only 0==0. (spin_reset needs §10's spin override, which a free-running leg
    drive cannot arm — the same reachability limit test_spin_arming documents; it is covered by
    test_fanout_spin_reset below, and here it legitimately stays zero.)"""
    lib = equiv._lib()
    totals = {"fanout_anim_nz": 0, "fanout_spin_state_nz": 0, "fanout_collision_nz": 0}
    for leg in (1, 4):                        # legs whose slalom crashes reach a nonzero spin_state
        image = equiv.leg_start_background(leg)
        mismatches, stats = equiv.compare_leg_drive(lib, image, DRIVES["slalom"])
        assert not mismatches, f"leg {leg} fan-out diverged: " + "; ".join(
            f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
        for k in totals:
            totals[k] += stats[k]
    with capsys.disabled():
        print(f"  fan-out nonzero frames across legs 1/4 slalom: {totals}")
    assert totals["fanout_anim_nz"] > 0, f"anim_frame never left zero — aliasing untested: {totals}"
    assert totals["fanout_spin_state_nz"] > 0, f"spin_state never left zero — gate untested: {totals}"
    assert totals["fanout_collision_nz"] > 0, f"collision_lock never left zero — suppress untested: {totals}"


@pytest.mark.parametrize("leg", [0, 1])
def test_fanout_spin_reset_reaches_lower_body_suppress(leg, capsys):
    """The one fan-out field a free-running leg drive can't otherwise reach: spin_reset, the spin
    override the lower-body draw reads as a suppressor (sprite.c draw_buggy_lo). §10's spin arming is
    the only thing that leaves it nonzero at draw time, so — exactly as test_spin_arming stages the
    §10 combination — this seeds the override (spin_reset + a steer_hold past the threshold) at the leg
    start and holds the steering lock. The fan-out's spin_reset long then goes nonzero and is compared
    against recreate's 0x18cc8 long every frame (compare_leg_drive's fan-out check), pinning the
    (spin_reset<<16)|spin_word2 reconstruction. Without it, dropping the spin_reset fan-out is invisible.

    BOTH words of the long are seeded nonzero so both halves of the reconstruction are pinned: the high
    word (0x18cc8, the <<16 shift) and the low word (0x18cca / spin_word2, the | term). spin_word2 is a
    real field the reference writes 0x19 into — §10's arming stores GU_SPIN_HI there when obj_flag_b!=0
    (game_update.c gu_dispatch_event idx 32/33) — but no leg/fuzz drive makes it nonzero at draw time,
    so it is staged here directly (mirroring test_spin_arming's word2 cases). With spin_reset already
    nonzero the arming leaves the low word untouched, so it rides the long intact to the fan-out; the
    LEFT lock keeps wheel off 0/4 so the long is not cleared. Dropping either the <<16 or the |spin_word2
    then makes the candidate long diverge from recreate's — both mutations caught by this one drive."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    equiv._w16(image, adapter.A_spin_reset, 0x19)         # spin override high word -> pins the <<16 shift
    equiv._w16(image, adapter.A_spin_reset + 2, 0x19)     # spin_word2 low word -> pins the |spin_word2 term
    equiv._w16(image, adapter.A_steer_hold, 0x20)         # past the spin threshold -> frame 0 decides
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL | LEFT] * 6)
    with capsys.disabled():
        print(f"  leg={leg}: spin_reset nonzero frames={stats['fanout_spin_reset_nz']}")
    assert not mismatches, "spin_reset fan-out drive diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats["fanout_spin_reset_nz"] > 0, \
        f"spin_reset never reached the lower-body suppressor — fan-out untested: {stats}"


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
