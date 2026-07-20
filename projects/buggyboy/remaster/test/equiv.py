"""equiv.py — the remaster equivalence harness (candidate vs recreate reference, per subsystem).

Phase A validates each remaster renderer to be pixel-identical to the verified recreate cores.
This drives both sides from ONE captured mid-race image and diffs the framebuffer:

  reference = recreate's g_draw_hud run on the image  (ground truth, verified vs the Musashi oracle)
  candidate = remaster's rm_draw_hud run on the same background, via the adapter's native structs

Because recreate only exports the whole g_draw_hud (not per-phase), we report FOOTPRINT COVERAGE:
the fraction of the bytes draw_hud changes that the candidate reproduces. A partially-ported HUD
scores <100%; the invariant a green test enforces is stronger and always honest —

  the candidate draws NO WRONG pixel: every byte it changes equals recreate's output there.

So coverage rises toward 100% as phases land, and the test fails the instant the candidate paints a
pixel recreate doesn't. Unported phases are neutralised via their skip inputs where possible (phase
3 via dsp_toggle, phase 8 via crash gates); phase 7 always draws, so it shows up as missing coverage.
"""
import ctypes

import adapter
import bench_frame                                # recreate's realistic mid-race staging

LIBREMASTER = adapter.REMASTER / "build" / "libremaster.so"

# recreate render pipeline stages that draw the pre-HUD frame (background the HUD overlays).
PRE_HUD_PIPELINE = ("g_render_road", "g_blit_road_scroll", "g_draw_game_objects")


def _lib():
    lib = ctypes.CDLL(str(LIBREMASTER))
    lib.rm_draw_hud.argtypes = [ctypes.POINTER(adapter.HudState),
                                ctypes.POINTER(adapter.HudAssets),
                                ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_draw_hud.restype = None
    lib.rm_render_road.argtypes = [ctypes.POINTER(adapter.RoadInput),
                                   ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_render_road.restype = None
    lib.rm_build_road_geometry.argtypes = [ctypes.POINTER(adapter.RoadPose),
                                           ctypes.POINTER(adapter.RoadSource),
                                           ctypes.POINTER(ctypes.c_uint8),
                                           ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_build_road_geometry.restype = None
    lib.rm_blit_road_scroll.argtypes = [ctypes.POINTER(adapter.ScrollState),
                                        ctypes.POINTER(ctypes.c_uint8),
                                        ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_blit_road_scroll.restype = None
    return lib


def _bind(name):
    fn = getattr(bench_frame.harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    return fn


def _run_pipeline(state, names):
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    for name in names:
        _bind(name)(buf)


def _w16(state, addr, val):
    state[addr], state[addr + 1] = (val >> 8) & 0xff, val & 0xff


def _r16(state, addr):
    return (state[addr] << 8) | state[addr + 1]


def hud_background(leg=0, warmup=60, controls=None):
    """A mid-race image with the pre-HUD frame drawn into SCREEN_BASE and the HUD control scalars
    poked (to activate the ported phases and skip the unported ones). Returns the image bytearray."""
    state = bench_frame.mid_race_state(leg, warmup)
    _run_pipeline(state, PRE_HUD_PIPELINE)
    # Neutralise the phases not yet ported so the reference footprint is (mostly) the ported phases.
    _w16(state, adapter.A_dsp_toggle, 0)          # phase 3 (dashboard-variant sprite) now ported -> on
    _w16(state, adapter.A_crash_active, 0)        # phase 8 draws nothing
    _w16(state, adapter.A_hud_crash_timer, 0)
    for addr, val in (controls or {}).items():
        _w16(state, addr, val & 0xffff)
    return state


def compare_hud(lib, image):
    """Run recreate's g_draw_hud (reference) and remaster's rm_draw_hud (candidate) on `image`, and
    diff the framebuffer. Returns (coverage, wrong_bytes): coverage in [0,1] over draw_hud's
    footprint; wrong_bytes = count of bytes the candidate changed to a value recreate didn't."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    ref = bytearray(image)
    _run_pipeline(ref, ("g_draw_hud",))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    state = adapter.hud_state(image)
    assets, _keep = adapter.hud_assets(image)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_draw_hud(ctypes.byref(state), ctypes.byref(assets), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    footprint = [i for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i]]
    matched = sum(1 for i in footprint if cand_fb[i] == ref_fb[i])
    wrong = sum(1 for i in range(adapter.SCREEN_BYTES)
                if cand_fb[i] != base[i] and cand_fb[i] != ref_fb[i])
    coverage = matched / len(footprint) if footprint else 1.0
    return coverage, wrong


def road_background(leg=0, warmup=60):
    """A mid-race image with real road geometry built (game_update warmup) but render_road not yet
    applied — the background render_road draws over. Returns the image bytearray."""
    return bench_frame.mid_race_state(leg, warmup)


def compare_road(lib, image):
    """Run recreate's g_render_road (reference) and remaster's rm_render_road (candidate) on the same
    background and diff the whole framebuffer. render_road owns the bottom 96 rows and the rest is
    untouched on both sides, so this is a strict whole-framebuffer exact check. Returns
    (diff_bytes, footprint) — footprint = bytes render_road changes (for a scale reference)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    ref = bytearray(image)
    _run_pipeline(ref, ("g_render_road",))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    inp, _keep = adapter.road_input(image)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_render_road(ctypes.byref(inp), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


def _build_candidate_ctrl(lib, image):
    """Run remaster's rm_build_road_geometry on `image`'s pose/sources; return (ctrl_bytes, pose)."""
    pose = adapter.road_pose(image)
    source, _keep = adapter.road_source(image)
    ctrl = (ctypes.c_uint8 * adapter.RM_CTRL_BYTES)()
    scan = (ctypes.c_uint8 * adapter.RM_SCANLINE_BYTES)()
    lib.rm_build_road_geometry(ctypes.byref(pose), ctypes.byref(source), ctrl, scan)
    return bytes(ctrl), pose


def compare_geometry(lib, image, pokes=None):
    """Poke the pose scalars (curve/view_flags/horizon), then run recreate's g_build_road_geometry
    (reference) and remaster's rm_build_road_geometry (candidate) on the same inputs. Returns
    (ctrl_diff, scalars_ok): ctrl_diff = differing bytes in the 106-long control table render_road
    reads; scalars_ok = the seg_head/horizon_row/horizon_frac outputs also match."""
    state = bytearray(image)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)

    ref = bytearray(state)
    _run_pipeline(ref, ("g_build_road_geometry",))
    lo, n = adapter.A_road_curve_tbl, adapter.RM_CTRL_BYTES
    ref_ctrl = bytes(ref[lo:lo + n])
    ref_scalars = (_r16(ref, adapter.A_road_seg_head), _r16(ref, adapter.A_horizon_row),
                   _r16(ref, adapter.A_horizon_frac))

    cand_ctrl, pose = _build_candidate_ctrl(lib, state)
    cand_scalars = (pose.seg_head & 0xffff, pose.horizon_row & 0xffff, pose.horizon_frac & 0xffff)

    ctrl_diff = sum(1 for a, b in zip(cand_ctrl, ref_ctrl) if a != b)
    return ctrl_diff, (cand_scalars == ref_scalars)


def compare_road_live(lib, image, pokes=None):
    """End-to-end: build the geometry natively (remaster), splice it into the control-table region,
    and render — vs recreate building + rendering the same poked frame. Returns whole-framebuffer
    diff_bytes. This proves the ported builder + renderer are pixel-identical for arbitrary steering."""
    state = bytearray(image)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)

    ref = bytearray(state)
    _run_pipeline(ref, ("g_build_road_geometry", "g_render_road"))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    cand_ctrl, _pose = _build_candidate_ctrl(lib, state)
    cand_img = bytearray(state)
    cand_img[adapter.A_road_curve_tbl:adapter.A_road_curve_tbl + adapter.RM_CTRL_BYTES] = cand_ctrl
    base = cand_img[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]
    inp, _keep = adapter.road_input(cand_img)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_render_road(ctypes.byref(inp), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    return sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])


def compare_scroll(lib, image, pokes=None):
    """Poke the scroll scalars (scroll_speed / hscroll_pos), then run recreate's g_blit_road_scroll
    (reference) and remaster's rm_blit_road_scroll (candidate) on the same background. Returns
    (diff_bytes, scalars_ok): diff over the whole framebuffer, and whether the updated hscroll_pos /
    hscroll_step2 match. blit_road_scroll owns rows 0..103 (disjoint from render_road), so a candidate
    starting from the same background gives a strict whole-framebuffer check."""
    state = bytearray(image)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)
    base = state[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    ref = bytearray(state)
    _run_pipeline(ref, ("g_blit_road_scroll",))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]
    ref_scalars = (_r16(ref, adapter.A_hscroll_pos), _r16(ref, adapter.A_hscroll_step2))

    scroll = adapter.scroll_state(state)
    playfield, _keep = adapter.scroll_playfield(state)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_blit_road_scroll(ctypes.byref(scroll), playfield, ctypes.byref(fb))
    cand_fb = bytes(fb.px)
    cand_scalars = (scroll.hscroll_pos & 0xffff, scroll.hscroll_step2 & 0xffff)

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    return diff, (cand_scalars == ref_scalars)
