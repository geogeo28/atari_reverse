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
