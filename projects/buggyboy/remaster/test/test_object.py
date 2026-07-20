"""test_object.py — remaster draw_object pixel-equivalence vs recreate's verified g_draw_object.

draw_object scales + positions the one scaled roadside object (the near "billboard") from the road
control table and paints it with solid scale-fills and antialiased edge cells. Each case stages a
mid-race frame at a (leg, warmup) where the object is on screen, runs recreate's g_draw_object as the
reference and remaster's rm_draw_object on the same background, and asserts the whole framebuffer is
byte-identical.

The chosen frames exercise the object descriptor's flag combinations (LEFT/RIGHT/FAR/SCALE2) and all
three shade signs (the centre/near fill pattern), plus the pre-scan road-band clear (leg 0).
"""
import equiv
import pytest

# (leg, warmup) frames where draw_object fires, spanning the flag/shade branches (probed):
#   leg 0 w90  desc 0xe81e.. SCALE2+LEFT+FAR, shade +, pre-scan clear
#   leg 1 w150 desc 0xc019.. LEFT+RIGHT,      shade 0
#   leg 2 w150 desc 0xd018.. LEFT+RIGHT+FAR,  shade -
#   leg 3 w120 desc 0xa006.. LEFT+SCALE2      (near-edge, writes from offset 0x7b)
#   leg 4 w60  desc 0xd03b.. LEFT+RIGHT+FAR,  shade 0
#   leg 4 w90  desc 0xd03b.. LEFT+RIGHT+FAR
CASES = [(0, 90), (1, 150), (2, 150), (3, 120), (3, 150), (4, 60), (4, 90)]


@pytest.mark.parametrize("leg,warmup", CASES)
def test_draw_object_matches(leg, warmup, capsys):
    lib = equiv._lib()
    image = equiv.object_background(leg=leg, warmup=warmup)
    diff, footprint = equiv.compare_object(lib, image)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup}: footprint={footprint} diff={diff}")
    assert footprint > 0, f"draw_object drew nothing (leg={leg}, warmup={warmup})"
    assert diff == 0, f"draw_object differs from recreate in {diff} bytes (leg={leg}, warmup={warmup})"
