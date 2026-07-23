"""test_init_leg.py — the leg-start state reset (rm_init_leg) vs recreate's g_init_leg.

A leg STARTS natively rather than from a baked snapshot. rm_init_leg reproduces g_init_leg's eleven
phases across the native owner structs (Player/Course/Pose/Scroll/Ring/Event/GobjPrefix/Sprite) plus
the two output scalars (obj_shade, screen_offset) and the shared HUD-text region. Each case runs
g_init_leg (the verified reference) on a pre-init image and rm_init_leg on native structs seeded from
the SAME pre-init image, then compares every surface rm_init_leg owns:

  - the physics / course / event / pose / scroll scalars (the 0x6d-word clear + the scalar defaults),
  - the course object/marker ring, band by band AND its serialized ST mirror (rm_ring_store_st),
  - the buggy-sprite leg-start pose,
  - the HUD bonus-time / score strings (the whole HUD-text region, bytes),
  - the scaled-object shade and the road-scroll offset.

Two scenarios per leg pin both directions the flow uses:
  - FRESH  : a clean pre-init image (_prepared_image) — a leg started from scratch.
  - RE-INIT: a warmed mid-race image (mid_race_state) — the RESTART path after a leg ends, whose
             non-zero game_over / timeout_gate / anim_counter / flag_seq_off / dash-marker values pin
             that rm_init_leg PRESERVES exactly the fields g_init_leg leaves below/above its clear.
"""
import ctypes

import adapter
import bench_frame
import equiv
import harness
import pytest


def _lib():
    lib = equiv._lib()                              # already registers rm_init_leg's argtypes
    P = ctypes.POINTER
    lib.rm_ring_store_st.argtypes = [P(adapter.CourseRing), P(ctypes.c_uint8)]
    lib.rm_ring_store_st.restype = None
    return lib


def _oracle(pre):
    """recreate's verified g_init_leg on a copy of the pre-init image (the reference leg-start image)."""
    ref = bytearray(pre)
    fn = harness._lib.g_init_leg
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    return ref


def _struct_fields(name, cand, expected):
    """Every field of two same-typed ctypes structs that differ, as (label, cand, ref) tuples."""
    out = []
    for field, _ctype in cand._fields_:
        cv, rv = getattr(cand, field), getattr(expected, field)
        # nested arrays (CourseRing.row / CourseRow.slot) compare element-wise via bytes.
        if hasattr(cv, "_length_"):
            if bytes(cv) != bytes(rv):
                out.append((f"{name}.{field}", "arr", "arr"))
        elif cv != rv:
            out.append((f"{name}.{field}", cv, rv))
    return out


def _mismatches(lib, pre):
    """Compare rm_init_leg's output against g_init_leg on the same pre-init image, over every owned
    surface. Returns the list of (label, candidate, reference) differences (empty == identical)."""
    ref = _oracle(pre)
    c = equiv.run_init_leg(lib, pre)                 # the shared 8-struct-seed + rm_init_leg call
    bad = []

    bad += _struct_fields("player", c.player, adapter.player_state(ref, 0))
    bad += _struct_fields("course", c.course, adapter.course_state(ref))
    bad += _struct_fields("pose", c.pose, adapter.road_pose(ref))
    bad += _struct_fields("scroll", c.scroll, adapter.scroll_state(ref))
    bad += _struct_fields("ring", c.ring, adapter.course_ring(ref))
    bad += _struct_fields("event", c.ev, adapter.event_state(ref))
    bad += _struct_fields("gobj", c.gobj, adapter._gobj_state(ref))
    bad += _struct_fields("sprite", c.sprite, adapter.sprite_state(ref))

    # The ring's serialized ST mirror (what the object-list dispatcher walks) vs the image row grid.
    mirror = (ctypes.c_uint8 * (adapter.RM_RING_ROWS * adapter.RING_ROW_BYTES))()
    lib.rm_ring_store_st(ctypes.byref(c.ring), mirror)
    ref_grid = bytes(ref[adapter.A_ring_base:adapter.A_ring_base
                         + adapter.RM_RING_ROWS * adapter.RING_ROW_BYTES])
    if bytes(mirror) != ref_grid:
        bad.append(("ring_st_mirror", "bytes", "bytes"))

    # The whole HUD-text region (bonus-time strings, score template + reset).
    if bytes(c.hud_text) != bytes(ref[adapter.A_hud_text:adapter.A_hud_text + adapter.HUD_TEXT_BYTES]):
        bad.append(("hud_text", "bytes", "bytes"))

    # The two output scalars with no owning struct field.
    if c.obj_shade.value != equiv._i16s(ref, adapter.A_obj_shade):
        bad.append(("obj_shade", c.obj_shade.value, equiv._i16s(ref, adapter.A_obj_shade)))
    if c.screen_offset.value != equiv._r16(ref, adapter.A_screen_offset):
        bad.append(("screen_offset", c.screen_offset.value, equiv._r16(ref, adapter.A_screen_offset)))
    return bad


@pytest.mark.parametrize("leg", range(5))
def test_init_leg_fresh(leg):
    """A leg started from scratch matches g_init_leg on every owned surface."""
    lib = _lib()
    bad = _mismatches(lib, equiv.leg_start_pre_init(leg))
    assert not bad, bad


REINIT_WARMUP = 45      # a warmed frame (non-zero preserved fields, an armed dash marker); one is
                        # enough — the mutation-verified differential holds the preserved-field copy honest


@pytest.mark.parametrize("leg", range(5))
def test_init_leg_reinit(leg):
    """The RESTART path: re-initialising a warmed mid-race image (non-zero preserved fields, an armed
    dash marker) still matches g_init_leg re-init exactly — the second-leg-start / leg-restart case."""
    lib = _lib()
    bad = _mismatches(lib, bytearray(bench_frame.mid_race_state(leg, REINIT_WARMUP)))
    assert not bad, bad
