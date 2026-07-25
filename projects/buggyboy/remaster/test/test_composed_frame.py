"""test_composed_frame.py — the COMPOSED-FRAME differential.

The scalar leg drive (test_leg_drive) verifies every STATE transition differentially and every DRAW
STAGE byte-exact, but with the draw inputs staged FROM the reference image — it never runs the shell's
actual per-frame COMPOSITION (state -> the rm_apply_player / rm_gobj_hud_view fan-outs -> the
rm_draw_frame stage sequence) end-to-end. Any missing wire BETWEEN two individually-verified pieces is
therefore invisible: the two play-test-only bugs that shipped green this session (the jump-animation
anim_frame fan and the flag-bars HUD fan) were both exactly that.

This closes the hole. On the sampled frames of each drive the candidate runs its OWN full composition —
rm_apply_player then rm_draw_frame, from its live owned state, via equiv._ComposedScene — into its own
framebuffer, while the reference runs recreate's g_draw_frame on the image, and the two framebuffers
are byte-compared (STRICT — no persistent-diff allowlist). Every wiring gap with a visible effect then
fails a drive. Mutation-verified (equiv.compare_leg_drive's compose path): dropping the anim_frame fan,
dropping rm_gobj_hud_view, dropping a stage (the fg sprite), and swapping two ordered stages (the fg
sprite vs the ground) each fail here.

SAMPLING RULE (a full frame pair is ~1.7 ms host-side — too much for every frame of every 600-frame
drive without blowing the suite budget): compose on every EVENT frame (a view-wrap, a crash arm, or a
leg-end frame — where fan/composition wiring bugs bite) PLUS every SAMPLE_EVERY-th frame (a regular
cadence so a wiring bug on a quiet frame is still caught). Each drive is its own xdist work unit, so the
set stays fast under -n auto.

DRIVE SET: a free flat-out drive per leg 0-4 (crashes fire on every leg -> the crash-script anim_frame
fan is exercised), plus the directed mechanism drives the free drives cannot reach eventfully: a flag
capture (leg 2 -> the flag-sequence HUD fan), and a slalom crash drive (legs 2/4), and the bonus-clock time-out that ends a leg (legs 0/1).
"""
import adapter
import equiv
import pytest

ACCEL, BRAKE, LEFT, RIGHT = 0x01, 0x02, 0x04, 0x08
FRAMES = 600
SAMPLE_EVERY = 15          # compose on every event frame + every Nth frame (see the module docstring)
BONUS_WINDOW_FRAMES = 0x3c   # events.c FLAG_BONUS_FRAMES — the window a 5-flag run opens
BONUS_DRIVE_FRAMES = 90      # enough sampled frames (incl. event frames) to cover the clamp broadly


def _sampler(frame, is_event):
    return is_event or frame % SAMPLE_EVERY == 0


def _composed(mismatches):
    """The composed-frame diffs among a drive's mismatches (5-tuples: frame, field, cand, ref, diff)."""
    return [m for m in mismatches if isinstance(m[1], str) and m[1].startswith("composed_fb")]


def _report(mismatches, stats):
    comp = _composed(mismatches)
    detail = "; ".join(f"frame {m[0]} {m[1]}: cand {m[2]} != rec {m[3]} ({m[4]} bytes)" for m in comp[:6])
    return comp, (f"composed-frame differential diverged from recreate g_draw_frame: {detail}"
                  f"  [checked={stats['composed_checked']} diffs={stats['composed_diffs']}]")


@pytest.mark.parametrize("leg", [0, 1, 2, 3, 4])
def test_composed_free_drive(leg, capsys):
    """One free flat-out drive per leg: the candidate composes its own frame on the sampled frames and
    it is byte-identical to recreate's g_draw_frame. Crashes fire on every leg, so the crash-script
    anim_frame / spin fan-out (the jump-animation seam) is exercised on real crash frames."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * FRAMES, compose=_sampler)
    comp, msg = _report(mismatches, stats)
    with capsys.disabled():
        print(f"  leg={leg} flat_out: composed checked={stats['composed_checked']} "
              f"diffs={stats['composed_diffs']} crashes={stats['armed']} wraps={stats['wraps']}")
    assert not comp, msg
    assert not [m for m in mismatches if m not in comp], "scalar drive also diverged"
    assert stats["composed_checked"] > 0, "no composed frame was checked (sampling reached nothing)"
    assert stats["armed"] > 0, "no crash fired — the crash-script fan-out went unexercised"


@pytest.mark.parametrize("leg,drive", [(2, "slalom"), (4, "slalom")])
def test_composed_crash_drive(leg, drive, capsys):
    """A slalom drive (extra crash variety) composed on the sampled frames — the crash script takes the
    controls and poses the buggy (anim_frame / lower-body suppress), so these frames stress the sprite
    fan-out the free drives touch only glancingly."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    inputs = [ACCEL | (LEFT if (f // 50) % 2 else RIGHT) for f in range(FRAMES)]
    mismatches, stats = equiv.compare_leg_drive(lib, image, inputs, compose=_sampler)
    comp, msg = _report(mismatches, stats)
    with capsys.disabled():
        print(f"  leg={leg} {drive}: composed checked={stats['composed_checked']} "
              f"diffs={stats['composed_diffs']} crashes={stats['armed']}")
    assert not comp, msg
    assert stats["armed"] > 0, "no crash fired — the crash-script fan-out went unexercised"


@pytest.mark.parametrize("leg", [0, 2])
def test_composed_bonus_window_clamps_low_object_types(leg, capsys):
    """The 5-flag BONUS WINDOW, composed. While bonus_timer is open the object dispatcher clamps every
    object type below OBJ_BONUS_MIN_TYPE up to it, so the roadside scenery changes for the window's
    length — and bonus_timer is a LIVE global the dispatcher reloads every frame, not a leg-start
    capture (the shell froze it at the leg-start 0 once, so the clamp never fired at all).

    Directed because no free drive opens the window: it needs five flags matched in a row, or the §I
    collision-marker frame, neither of which a flat-out drive reaches. Seeding the leg-start image's
    bonus_timer opens it on BOTH sides — the reference's g_draw_frame reads the same global.
    Mutation-verified: freezing objlist->bonus_timer at 0 in rm_draw_frame fails this (32 of 37 composed
    frames diverge).

    Coverage limit, stated honestly: the window stays OPEN for the whole drive. Only rm_gobj_prefix
    decrements bonus_timer, and it runs inside the compose — which both sides discard (the candidate
    advances a per-frame snapshot of its gobj state, the reference draws into a copy), so the seeded
    0x3c is still 0x3c at frame 90 (measured). This therefore pins the clamp-OPEN path; the window's
    CLOSE path and the flag-sequence step at bonus_timer == 0x28 are left to test_gobj_prefix, which
    drives the prefix directly."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    equiv._w16(image, adapter.A_bonus_timer, BONUS_WINDOW_FRAMES)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * BONUS_DRIVE_FRAMES,
                                                compose=_sampler)
    comp, msg = _report(mismatches, stats)
    with capsys.disabled():
        print(f"  leg={leg} bonus window: composed checked={stats['composed_checked']} "
              f"diffs={stats['composed_diffs']}")
    assert not comp, msg
    assert stats["composed_checked"] > 0, "no composed frame was checked"


def test_composed_flag_capture(capsys):
    """A leg-2 flat-out drive captures a flag; the flag-sequence HUD bars (phase 4/5) are fanned in by
    rm_gobj_hud_view inside rm_draw_frame. This is the drive that pins that fan in the composed frame —
    dropping rm_gobj_hud_view fails here (mutation-verified: 111 of 127 composed frames diff)."""
    lib = equiv._lib()
    image = equiv.leg_start_background(2)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [ACCEL] * 400, compose=_sampler)
    comp, msg = _report(mismatches, stats)
    with capsys.disabled():
        print(f"  leg=2 flag capture: composed checked={stats['composed_checked']} "
              f"diffs={stats['composed_diffs']}")
    assert not comp, msg
    assert stats["composed_checked"] > 0, "no composed frame was checked"


@pytest.mark.parametrize("leg", [0, 1])
def test_composed_timeout_leg_end(leg, capsys):
    """An idle drive with the bonus clock shortened (time_left = 6, as test_leg_ends_on_timeout does)
    runs the clock out and ends the leg — the leg-end frames (abort_flag < 0) are event frames, so the
    composed differential covers the crash-fx tally's HUD state on the frames where a leg ends."""
    lib = equiv._lib()
    image = equiv.leg_start_background(leg)
    equiv._w16(image, adapter.A_time_left, 6)
    mismatches, stats = equiv.compare_leg_drive(lib, image, [0] * 140, compose=_sampler)
    comp, msg = _report(mismatches, stats)
    with capsys.disabled():
        print(f"  leg={leg} time-out: composed checked={stats['composed_checked']} "
              f"diffs={stats['composed_diffs']} leg_over={stats['leg_over']}")
    assert not comp, msg
    assert stats["leg_over"] > 0, "the leg never ended — the leg-end frames went uncovered"
