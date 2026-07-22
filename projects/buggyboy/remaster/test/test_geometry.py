"""test_geometry.py — remaster build_road_geometry equivalence vs recreate's g_build_road_geometry.

The builder turns the pose (road curvature = steering, view selector, horizon, segment slopes) into
the per-scanline control-long table render_road consumes. Since the on-target demo steers by poking
`road_curve` (and friends), the port must be byte-exact for ARBITRARY input, not just captured
values — so each case perturbs the steering inputs and asserts:
  1. the 106-long control table matches recreate byte-for-byte (compare_geometry), and
  2. the resulting rendered road is whole-framebuffer identical (compare_road_live).
"""
import ctypes

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


@pytest.mark.parametrize("view_bank", [0, 2, 4, 6])
def test_stamp_spill_stays_within_alloc(view_bank, capsys):
    """Pin RM_CTRL_STAMP_SPILL to the stamp loop's real write extent. Stage 4 legitimately writes
    past the RM_CTRL_BYTES table (faithful to the original), so every ctrl buffer is allocated at
    RM_CTRL_ALLOC_BYTES — but no ctrl comparison can see an under-sized pad (they all stop at
    RM_CTRL_BYTES); getting it wrong is silent ctypes heap corruption. Two poison passes so a write
    that happens to equal one canary can't hide; the union is the true touched set."""
    lib = equiv._lib()
    image = equiv.road_background(leg=0, warmup=60)
    source, _keep = adapter.road_source(image)
    guard = 16
    size = adapter.RM_CTRL_ALLOC_BYTES + guard

    touched = set()
    for canary in (0x5A, 0xA5):
        pose = adapter.road_pose(image)
        pose.view_flags = view_bank
        ring = adapter.course_ring(image)
        buf = (ctypes.c_uint8 * size)(*([canary] * size))
        scan = (ctypes.c_uint8 * adapter.RM_SCANLINE_BYTES)()
        lib.rm_build_road_geometry(ctypes.byref(pose), ctypes.byref(source), ctypes.byref(ring), buf, scan)
        touched |= {i for i in range(adapter.RM_CTRL_BYTES, size) if buf[i] != canary}

    with capsys.disabled():
        extent = max(touched) + 1 - adapter.RM_CTRL_BYTES if touched else 0
        print(f"  view_bank={view_bank}: spill extent {extent} of {adapter.RM_CTRL_STAMP_SPILL} pad bytes")
    assert touched, "the stamp never wrote past the table — the ALLOC pad is dead paper, remove it"
    assert max(touched) < adapter.RM_CTRL_ALLOC_BYTES, (
        f"stamp wrote {max(touched) + 1 - adapter.RM_CTRL_ALLOC_BYTES} bytes past RM_CTRL_ALLOC_BYTES "
        f"(view_bank={view_bank}) — the spill pad is too small")
