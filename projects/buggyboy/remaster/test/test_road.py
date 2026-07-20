"""test_road.py — remaster render_road pixel-equivalence vs recreate's verified g_render_road.

render_road is a leaf that owns the bottom 96 scanlines (rows 104..199). Each case stages a realistic
mid-race frame (real road geometry built by game_update), runs recreate's g_render_road as the
reference and remaster's rm_render_road on the same background, and asserts the whole framebuffer is
byte-identical — the strictest form of the equivalence contract (README.md).
"""
import equiv
import pytest

# A spread of legs (and warmup depths) to exercise different road curvature / width configurations,
# so the flag-driven band variants (splits, wide/solid centres, const strips, off-screen fills) fire.
CASES = [(0, 60), (0, 90), (1, 60), (2, 60), (2, 120), (3, 75), (4, 60)]


@pytest.mark.parametrize("leg,warmup", CASES)
def test_render_road_whole_framebuffer_exact(leg, warmup, capsys):
    lib = equiv._lib()
    image = equiv.road_background(leg=leg, warmup=warmup)
    diff, footprint = equiv.compare_road(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup}: footprint={footprint} diff_bytes={diff}")
    assert diff == 0, f"render_road differs from recreate in {diff} bytes (leg={leg}, warmup={warmup})"
