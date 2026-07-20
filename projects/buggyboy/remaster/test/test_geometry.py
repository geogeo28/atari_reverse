"""test_geometry.py — remaster build_road_geometry equivalence vs recreate's g_build_road_geometry.

The builder turns the pose (road curvature = steering, view selector, horizon, segment slopes) into
the per-scanline control-long table render_road consumes. Since the on-target demo steers by poking
`road_curve` (and friends), the port must be byte-exact for ARBITRARY input, not just captured
values — so each case perturbs the steering inputs and asserts:
  1. the 106-long control table matches recreate byte-for-byte (compare_geometry), and
  2. the resulting rendered road is whole-framebuffer identical (compare_road_live).
"""
import adapter
import equiv
import pytest

# (curve, view_flags, seg_data[0]): sweep the steering knobs. curve spans hard-left..hard-right, the
# four view banks, and the near-slope (crest/dip). Each poke maps to what an arrow key would nudge.
POKES = [
    {},                                                   # captured pose unchanged
    {adapter.A_road_curve: 0},                            # straight
    {adapter.A_road_curve: 0x0400},                       # gentle right
    {adapter.A_road_curve: 0xfc00},                       # gentle left (signed)
    {adapter.A_road_curve: 0x2000},                       # hard right
    {adapter.A_road_curve: 0xe000},                       # hard left
    {adapter.A_view_flags: 2}, {adapter.A_view_flags: 4}, {adapter.A_view_flags: 6},
    {adapter.A_road_seg_data: 0x0004}, {adapter.A_road_seg_data: 0xfff8},   # near-slope crest / dip
    {adapter.A_road_curve: 0x1800, adapter.A_view_flags: 4, adapter.A_road_seg_data: 0x0002},
]


@pytest.mark.parametrize("leg,warmup", [(0, 60), (2, 90), (4, 60)])
@pytest.mark.parametrize("pokes", POKES)
def test_build_road_geometry_matches(leg, warmup, pokes, capsys):
    lib = equiv._lib()
    image = equiv.road_background(leg=leg, warmup=warmup)
    ctrl_diff, scalars_ok = equiv.compare_geometry(lib, image, pokes)
    fb_diff = equiv.compare_road_live(lib, image, pokes)
    with capsys.disabled():
        print(f"  leg={leg} warmup={warmup} pokes={pokes}: "
              f"ctrl_diff={ctrl_diff} scalars_ok={scalars_ok} fb_diff={fb_diff}")
    assert ctrl_diff == 0, f"control table differs in {ctrl_diff} bytes (leg={leg}, pokes={pokes})"
    assert scalars_ok, f"seg_head/horizon outputs differ (leg={leg}, pokes={pokes})"
    assert fb_diff == 0, f"rendered road differs in {fb_diff} bytes (leg={leg}, pokes={pokes})"
