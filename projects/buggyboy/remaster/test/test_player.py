"""test_player.py — remaster player-physics equivalence vs recreate's game_update (§3,4,5,7,8,9,10).

This is the driving model: throttle -> engine rpm -> speed, speed -> the road-scroll rate and the
view advance that times the course, steering -> wheel position, body lean and road curvature, and
the road-edge clamp that pushes you back when you run wide. Each drive scripts a per-frame input
mask and asserts every scalar rm_player_update owns stays identical to recreate's, frame for frame —
so a demo driven by it accelerates, steers and runs off the road exactly like the original.

The scripts reach the branches: the rev limiter (held throttle), the brake and the coast-down, both
steering locks plus the recentre, the edge clamp and the off-road push (leg 4 has shoulders the
recentre line runs onto), the fire-triggered dashboard animation, and the bonus-time-out. Each drive
also asserts the behaviour it was written to exercise actually happened, so a drive that degenerates
into a stationary buggy fails instead of passing vacuously.
"""
import adapter
import equiv
import pytest

ACCEL, BRAKE, LEFT, RIGHT, FIRE = 0x01, 0x02, 0x04, 0x08, 0x80
FRAMES = 240

# name -> (per-frame input masks, extra image pokes, the stats key this drive must exercise)
DRIVES = {
    "throttle": ([ACCEL] * FRAMES, {}, "wraps"),                     # rev up, hit the limiter, cruise
    "brake":    ([ACCEL] * 80 + [BRAKE] * 80 + [0] * 80, {}, "wraps"),
    "slalom":   ([ACCEL | (LEFT if (f // 20) % 2 else RIGHT) for f in range(FRAMES)], {}, "wraps"),
    "hard_left":  ([ACCEL | LEFT] * FRAMES, {}, "clamp"),            # full lock: runs wide, clamps
    "hard_right": ([ACCEL | RIGHT] * FRAMES, {}, "clamp"),
    "recentre": ([ACCEL | (LEFT if f % 40 < 10 else RIGHT if 20 <= f % 40 < 30 else 0)
                  for f in range(FRAMES)], {}, "wraps"),
    "fire":     ([ACCEL | (FIRE if f % 30 < 3 else 0) for f in range(FRAMES)], {}, "fire"),
    "timeout":  ([ACCEL] * FRAMES, {adapter.A_time_left: 2}, "timeout"),   # clock runs out -> braking
}


@pytest.mark.parametrize("leg", [0, 1, 4])
@pytest.mark.parametrize("drive", sorted(DRIVES))
def test_player_physics_tracks_recreate(leg, drive, capsys):
    inputs, pokes, must_exercise = DRIVES[drive]
    lib = equiv._lib()
    image = equiv.player_background(leg=leg, warmup=30, pokes=pokes)
    mismatches, stats = equiv.compare_player_drive(lib, image, inputs)
    with capsys.disabled():
        print(f"  leg={leg} {drive}: {len(mismatches)} mismatches / {stats}")
    assert not mismatches, "player physics diverged from recreate: " + "; ".join(
        f"frame {f} {name}: candidate {c} != recreate {r}" for f, name, c, r in mismatches[:8])
    assert stats[must_exercise] > 0, f"{drive} never exercised {must_exercise}: {stats}"


def test_offroad_push_is_reached():
    """The off-road push (§10) needs a shoulder to plough onto, which only some legs and lines have —
    pin down one drive that reaches it, so the branch is not silently untested everywhere."""
    lib = equiv._lib()
    image = equiv.player_background(leg=4, warmup=30)
    mismatches, stats = equiv.compare_player_drive(lib, image, DRIVES["recentre"][0])
    assert not mismatches
    assert stats["offroad"] > 0, f"no off-road push reached: {stats}"


# The two sites that carry the original's `rev_reload` poke, as (name, pokes). §1 fires on a leg-start
# frame as it stands (speed 0, no crash). §6 needs the crash script to hold the controls on a record
# whose rpm-override byte is non-negative: crash_anim_tbl + 0x90 is one (lean 0x2a, rpm 0x00), and it is
# a real entry point (the finish-display record arms exactly this cursor). Its `speed` poke keeps §1's
# idle branch OUT of the frame, so a raised flag can only have come from the script.
REV_RELOAD_SITES = {
    "s1_engine_idle": {},
    "s6_script_rpm_override": {adapter.A_collision_lock: 0x90, adapter.A_speed: 0x40},
}


@pytest.mark.parametrize("leg", [0, 1, 4])
@pytest.mark.parametrize("site", sorted(REV_RELOAD_SITES))
def test_rev_reload_poke_restarts_the_lean_overlay(leg, site):
    """The original's `rev_reload` poke, at BOTH its sites. 0x18d12 is ONE global under two names —
    rev_reload and lean_frame — so each poke restarts the lean-overlay animation the buggy draw reads.
    The reference stamps lean_frame; the candidate must land on the same value through
    PlayerState.lean_frame_reload -> rm_apply_player -> SpriteState.lean_frame.

    Directly diffed because no other test can see it: the composed-frame differential re-seeds the
    sprite's draw-internal cursors (lean_frame / lean_accum / variant) from the reference every frame by
    design, so dropping the fan there passes. Both sides are seeded with a NON-reload lean_frame first,
    and `raised` is asserted, so a frame where the poke never fires fails instead of passing vacuously.
    Mutation-verified at both sites: deleting either raise reddens its case only."""
    lib = equiv._lib()
    cand, ref, raised = equiv.compare_lean_frame_reload(lib, equiv.leg_start_background(leg),
                                                        pokes=REV_RELOAD_SITES[site])
    assert raised, f"{site}: the poke never fired — the case went unexercised"
    assert ref != equiv.LEAN_FRAME_SEED, f"{site}: the reference never wrote lean_frame — test is vacuous"
    assert cand == ref, f"{site}: lean_frame after the rev_reload poke: candidate {cand} != recreate {ref}"
