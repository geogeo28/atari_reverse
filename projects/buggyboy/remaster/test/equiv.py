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
import types

import adapter
import bench_frame                                # recreate's realistic mid-race staging


# recreate render pipeline stages that draw the pre-HUD frame (background the HUD overlays).
PRE_HUD_PIPELINE = ("g_render_road", "g_blit_road_scroll", "g_draw_game_objects")


def _lib():
    lib = ctypes.CDLL(str(adapter.LIBREMASTER))
    lib.rm_draw_hud.argtypes = [ctypes.POINTER(adapter.HudState),
                                ctypes.POINTER(adapter.HudAssets),
                                ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_draw_hud.restype = None
    lib.rm_render_road.argtypes = [ctypes.POINTER(adapter.RoadInput),
                                   ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_render_road.restype = None
    lib.rm_build_road_geometry.argtypes = [ctypes.POINTER(adapter.RoadPose),
                                           ctypes.POINTER(adapter.RoadSource),
                                           ctypes.POINTER(adapter.CourseRing),
                                           ctypes.POINTER(ctypes.c_uint8),
                                           ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_build_road_geometry.restype = None
    lib.rm_blit_road_scroll.argtypes = [ctypes.POINTER(adapter.ScrollState),
                                        ctypes.POINTER(ctypes.c_uint8),
                                        ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_blit_road_scroll.restype = None
    lib.rm_scroll_prebuild.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_scroll_prebuild.restype = None
    lib.rm_road_course_advance.argtypes = [ctypes.POINTER(adapter.RoadPose),
                                           ctypes.POINTER(adapter.CourseState),
                                           ctypes.POINTER(adapter.CourseRing),
                                           ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_road_course_advance.restype = None
    for fn in (lib.rm_draw_fg_sprite, lib.rm_draw_buggy):
        fn.argtypes = [ctypes.POINTER(adapter.SpriteState),
                       ctypes.POINTER(adapter.SpriteAssets),
                       ctypes.POINTER(adapter.Framebuffer)]
        fn.restype = None
    lib.rm_draw_ground.argtypes = [ctypes.POINTER(adapter.GroundState),
                                   ctypes.POINTER(adapter.GroundAssets),
                                   ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_draw_ground.restype = None
    lib.rm_draw_object.argtypes = [ctypes.POINTER(adapter.ObjectInput),
                                   ctypes.POINTER(adapter.Framebuffer)]
    lib.rm_draw_object.restype = None
    u8p = ctypes.POINTER(ctypes.c_uint8)
    lib.rm_blit_objshift.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32,
                                     ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16,
                                     ctypes.c_int16, u8p, ctypes.c_int]
    lib.rm_blit_objshift.restype = None
    lib.rm_blit_objshift2.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32,
                                      ctypes.c_uint16, ctypes.c_uint16, ctypes.c_int]
    lib.rm_blit_objshift2.restype = None
    lib.rm_objsprite.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32,
                                 ctypes.c_uint16, ctypes.c_uint16, ctypes.c_int]
    lib.rm_objsprite.restype = None
    lib.rm_objsprite_alt.argtypes = [u8p, ctypes.c_uint32, u8p, ctypes.c_uint32,
                                     ctypes.c_uint16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint16]
    lib.rm_objsprite_alt.restype = None
    lib.rm_draw_object_list.argtypes = [ctypes.POINTER(adapter.ObjListCtx),
                                        u8p, ctypes.c_uint32, u8p, ctypes.c_uint32,
                                        ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16]
    lib.rm_draw_object_list.restype = None
    lib.rm_gobj_prefix.argtypes = [ctypes.POINTER(adapter.GobjPrefixState),
                                   ctypes.POINTER(adapter.GobjPrefixAssets)]
    lib.rm_gobj_prefix.restype = None
    ectx = ctypes.POINTER(adapter.RmEventCtx)
    lib.rm_player_update.argtypes = [ctypes.POINTER(adapter.PlayerState),
                                     ctypes.POINTER(adapter.PlayerAssets),
                                     ctypes.POINTER(ctypes.c_uint8), ectx]
    lib.rm_player_update.restype = None
    lib.rm_event_dispatch.argtypes = [ectx, ctypes.c_uint16, ctypes.c_uint16,
                                      ctypes.c_uint16, ctypes.c_uint16]
    lib.rm_event_dispatch.restype = None
    lib.rm_course_events.argtypes = [ectx]
    lib.rm_course_events.restype = None
    lib.rm_course_probe.argtypes = [ectx]
    lib.rm_course_probe.restype = None
    lib.rm_crash_fx_update.argtypes = [ectx]
    lib.rm_crash_fx_update.restype = None
    lib.rm_event_classify.argtypes = [ctypes.c_uint16]
    lib.rm_event_classify.restype = ctypes.c_uint32
    P = ctypes.POINTER
    lib.rm_init_leg.argtypes = [
        P(adapter.PlayerState), P(adapter.CourseState), P(adapter.RoadPose),
        P(adapter.ScrollState), P(adapter.CourseRing), P(adapter.EventState),
        P(adapter.GobjPrefixState), P(adapter.SpriteState), P(ctypes.c_uint8),
        P(ctypes.c_int16), P(ctypes.c_uint16), P(adapter.RmInitAssets), ctypes.c_uint16]
    lib.rm_init_leg.restype = None
    return lib


def _bind(name):
    fn = getattr(bench_frame.harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    return fn


# g_draw_crash_fx(image, draw buffer): recreate's HUD phase-8 tally, bound once here (it is called per
# tally frame by _ref_crash_fx / the leg drive, so the signature is not rebound at each call site).
_g_draw_crash_fx = bench_frame.harness._lib.g_draw_crash_fx
_g_draw_crash_fx.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
_g_draw_crash_fx.restype = None


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
    """Run remaster's rm_build_road_geometry on `image`'s pose/sources/ring; return (ctrl_bytes, pose)."""
    pose = adapter.road_pose(image)
    source, _keep = adapter.road_source(image)
    ring = adapter.course_ring(image)
    ctrl = (ctypes.c_uint8 * adapter.RM_CTRL_ALLOC_BYTES)()
    scan = (ctypes.c_uint8 * adapter.RM_SCANLINE_BYTES)()
    lib.rm_build_road_geometry(ctypes.byref(pose), ctypes.byref(source), ctypes.byref(ring), ctrl, scan)
    return bytes(ctrl)[:adapter.RM_CTRL_BYTES], pose


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
    shifted = (ctypes.c_uint8 * (adapter.RM_SCROLL_SHIFTS * adapter.RM_SCROLL_WINDOW))()
    lib.rm_scroll_prebuild(playfield, shifted)       # the perf path: pre-rotate once, then copy
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_blit_road_scroll(ctypes.byref(scroll), shifted, ctypes.byref(fb))
    cand_fb = bytes(fb.px)
    cand_scalars = (scroll.hscroll_pos & 0xffff, scroll.hscroll_step2 & 0xffff)

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    return diff, (cand_scalars == ref_scalars)


def _seg_data(state):
    return [_r16(state, adapter.A_road_seg_data + i * 2) for i in range(13)]


def compare_course_drive(lib, image, frames=24):
    """Drive `frames` course-advance steps and check the remaster course-advance tracks recreate's
    game_update. Each frame: seed a native pose/course-state from the current image, run remaster's
    rm_road_course_advance, then advance the reference image one frame via recreate's g_game_update
    (forced into the section-12 course advance), and compare the road segment window + row_ctr /
    read_pos. A match means the road geometry the renderer consumes evolves identically while driving.
    Returns the count of mismatching frames (0 = perfect)."""
    state = bytearray(image)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    bench_frame.harness._lib.g_game_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    bench_frame.harness._lib.g_game_update.restype = None

    mismatches = 0
    for _ in range(frames):
        pose = adapter.road_pose(state)
        cs = adapter.course_state(state)
        stream, _keep = adapter.course_stream(state)
        ring = adapter.course_ring(state)
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), ctypes.byref(ring), stream)
        cand_seg = [pose.seg_data[i] & 0xffff for i in range(13)]
        cand = (cand_seg, cs.row_ctr & 0xffff, cs.read_pos & 0xffff)

        bench_frame._force_advance(state)
        bench_frame.harness._lib.g_game_update(buf)
        ref = (_seg_data(state), _r16(state, adapter.A_course_row_ctr),
               _r16(state, adapter.A_course_read_pos))
        if cand != ref:
            mismatches += 1
    return mismatches


# recreate render pipeline stages that draw the pre-sprite frame (background the buggy/fg overlay).
PRE_SPRITE_PIPELINE = ("g_render_road", "g_blit_road_scroll", "g_draw_ground")


def sprite_background(leg=0, warmup=60, pokes=None):
    """A mid-race image with the pre-object frame drawn into the framebuffer (road + ground) — the
    background the buggy/foreground sprites overlay. Returns the image bytearray."""
    state = bench_frame.mid_race_state(leg, warmup)
    _run_pipeline(state, PRE_SPRITE_PIPELINE)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)
    return state


def compare_sprite(lib, image, ref_fn, rm_fn, state_fn):
    """Run a recreate sprite draw (`ref_fn`, e.g. g_draw_fg_sprite) as the reference and the matching
    remaster core (`rm_fn`) on the same background, then diff the whole framebuffer. `state_fn` builds
    the native SpriteState from the image (== adapter.sprite_state). Returns diff_bytes (0 = exact)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    ref = bytearray(image)
    _run_pipeline(ref, (ref_fn,))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    s = state_fn(image)
    assets, _keep = adapter.sprite_assets(image)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    rm_fn(ctypes.byref(s), ctypes.byref(assets), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    return sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])


def ground_background(leg=0, warmup=60, entry=None, marker=None, view=None):
    """A mid-race image with the road drawn (the frame draw_ground fills over) and, optionally, a
    draw marker poked into descriptor `entry` so draw_ground actually fires (the staged frames usually
    carry none). Returns the image bytearray."""
    state = bench_frame.mid_race_state(leg, warmup)
    _run_pipeline(state, ("g_render_road", "g_blit_road_scroll"))
    if entry is not None and marker is not None:
        state[adapter.A_ground_scan_tbl + entry * adapter.GROUND_SCAN_STRIDE
              + adapter.GROUND_MARKER_OFF] = marker
    if view is not None:
        _w16(state, adapter.A_ground_view_off, view & 0xffff)
    return state


def compare_ground(lib, image):
    """Run recreate's g_draw_ground (reference) and remaster's rm_draw_ground (candidate) on the same
    background and diff the whole framebuffer. Returns (diff_bytes, footprint)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    # g_draw_ground(image, buffer) takes the draw buffer explicitly; derive it from flip_idx/physbase
    # (== SCREEN_BASE in the staged frames) and bind the two-arg signature.
    ref = bytearray(image)
    flip = _r16(ref, adapter.A_flip_idx)
    buffer = int.from_bytes(ref[adapter.A_physbase_tbl + flip:adapter.A_physbase_tbl + flip + 4], "big")
    fn = bench_frame.harness._lib.g_draw_ground
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref), buffer)
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    s = adapter.ground_state(image)
    assets, _keep = adapter.ground_assets(image)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_draw_ground(ctypes.byref(s), ctypes.byref(assets), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


def object_background(leg=0, warmup=60):
    """A mid-race image with the pre-object frame drawn (road + ground + foreground sprite) — the
    background draw_object's one scaled roadside object overlays. Returns the image bytearray."""
    state = bench_frame.mid_race_state(leg, warmup)
    _run_pipeline(state, ("g_render_road", "g_blit_road_scroll", "g_draw_ground", "g_draw_fg_sprite"))
    return state


def compare_object(lib, image):
    """Run recreate's g_draw_object (reference) and remaster's rm_draw_object (candidate) on the same
    background and diff the whole framebuffer. g_draw_object(image, buffer) takes the draw buffer
    explicitly (derived from flip_idx/physbase). Returns (diff_bytes, footprint)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    ref = bytearray(image)
    flip = _r16(ref, adapter.A_flip_idx)
    buffer = int.from_bytes(ref[adapter.A_physbase_tbl + flip:adapter.A_physbase_tbl + flip + 4], "big")
    fn = bench_frame.harness._lib.g_draw_object
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref), buffer)
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    inp, _keep = adapter.object_input(image)
    fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))
    lib.rm_draw_object(ctypes.byref(inp), ctypes.byref(fb))
    cand_fb = bytes(fb.px)

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


# ---- leaf fine-x blit engines (blit_objshift / blit_objshift2) ----
# These write raw memory offsets (no framebuffer struct); recreate's fuzz stages a flat image and
# calls the g_ entry with image addresses. We drive both sides from one flat staged buffer: recreate's
# g_ engine (image-address ABI) as the reference, then the remaster engine on a fresh copy with the
# SAME buffer as both dst and src (dst_off/src_off = the staged absolute addresses). A byte diff over
# the whole buffer proves equivalence including the "draws nothing" clip cases.
A_color_pairs = adapter.A_color_pairs


def _flat_image():
    return bytearray(bench_frame.IMAGE_SIZE)


def _stage_noise(state, rng, spans):
    for addr, n in spans:
        state[addr:addr + n] = bytes(rng.randrange(256) for _ in range(n))


def compare_objshift(lib, ref_name, remaster_call, regs, spans, seed):
    """Differential for a leaf fine-x blit engine. `ref_name` is recreate's g_ entry; `regs` the
    image-address arguments to call it with; `remaster_call(lib, buf_ptr)` invokes the remaster engine
    on the ctypes buffer. `spans` = [(addr, nbytes)] noise regions to stage identically on both sides.
    Returns the count of bytes that differ across the whole image."""
    import random
    rng = random.Random(seed)
    base = _flat_image()
    _stage_noise(base, rng, spans)

    ref = bytearray(base)
    fn = getattr(bench_frame.harness._lib, ref_name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * len(regs)
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref), *regs)

    cand = bytearray(base)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(cand)
    remaster_call(lib, buf)

    return _diff_over_spans(ref, cand, spans)


def _diff_over_spans(ref, cand, spans):
    """Count differing bytes only within the staged regions (the engines write inside the dst noise
    span; scanning the whole 1 MB image per case is needlessly slow under xdist)."""
    total = 0
    for addr, n in spans:
        for i in range(addr, addr + n):
            if ref[i] != cand[i]:
                total += 1
    return total


# ---- roadside-object display-list dispatcher (draw_object_list) ----
# draw_object_list reads many arenas at absolute image offsets and WRITES only the draw buffer. To
# validate the pointer-independent remaster port against recreate's flat-image g_draw_object_list, we
# drive the remaster dispatcher on a ctypes VIEW of the same image: every arena pointer is the image
# base (so its absolute offsets index identically) and draw_buf is the absolute draw-buffer address.
# We replicate draw_game_objects' three real passes (the sprite passes split at `count`, then the
# fixed-object pass) so the exact per-frame streams/records are exercised.

def _objlist_ctx(lib, img_arr, draw_buf):
    """Build an ObjListCtx that drives the remaster dispatcher on a VIEW of recreate's flat image:
    each arena pointer is offset so `pointer + <recreate offset>` lands on the same absolute address
    recreate reads. px is the image base (writes go to draw_buf-relative offsets); buf_a/buf_c are the
    real arena addresses stored in the image; the STATIC tables sit at their fixed bases."""
    def at(addr):
        return ctypes.cast(ctypes.byref(img_arr, addr), ctypes.POINTER(ctypes.c_uint8))

    base = ctypes.cast(img_arr, ctypes.POINTER(ctypes.c_uint8))
    buf_a = int.from_bytes(bytes(img_arr[adapter.A_buf_a:adapter.A_buf_a + 4]), "big")
    buf_c = int.from_bytes(bytes(img_arr[adapter.A_buf_c:adapter.A_buf_c + 4]), "big")
    return adapter.ObjListCtx(
        base, draw_buf, at(buf_a), at(buf_c), at(adapter.A_color_pairs),
        at(adapter.A_obj_view_xform), at(adapter.A_objsh2p_tbl), at(adapter.A_obj_type_jumptable),
        at(adapter.A_obj_xoff_tbl),
        _r16(img_arr, adapter.A_view_flags), _r16(img_arr, adapter.A_view_parity),
        _r16(img_arr, adapter.A_bonus_timer), _s16(img_arr, adapter.A_obj_scan_off),
        img_arr[adapter.A_p24_flag])


def _s16(state, addr):
    v = (state[addr] << 8) | state[addr + 1]
    return v - 0x10000 if v & 0x8000 else v


def _objlist_passes(state):
    """The three draw_object_list invocations draw_game_objects makes, as positional slots:
    (pass1, pass2, fixed) — pass1/pass2 are None when their gate is off. pass1 (the `count` active
    sprite rows) runs BEFORE draw_object; pass2 (the remaining rows) runs AFTER it; the fixed-object
    pass runs last (ordered against the buggy by the view). Each slot is a
    (list_off, flags_off, outer_rows_m1, rec_off, colour) tuple."""
    count = 0
    if _s16(state, adapter.A_sprite_list_base) >= 0:
        slot = adapter.A_sprite_list_base + adapter.GOBJ_MARKER_STRIDE
        for _ in range(adapter.GOBJ_SPRITE_SLOTS + 1):
            if _s16(state, slot) < 0:
                break
            count += 1
            slot += adapter.GOBJ_MARKER_STRIDE
    pass1 = None
    if count - 1 >= 0:
        pass1 = (adapter.A_obj_sprite_disp, adapter.A_obj_sprite_flags,
                 (count - 1) & 0xffff, adapter.GOBJ_D6_INIT, count & 0xffff)
    pass2 = None
    if adapter.GOBJ_SPRITE_LAST - count >= 0:
        pass2 = (adapter.A_obj_sprite_disp + ((count * adapter.GOBJ_ROW_A5_STRIDE) & 0xffff),
                 adapter.A_obj_sprite_flags + ((count * adapter.GOBJ_ROW_A3_STRIDE) & 0xffff),
                 (adapter.GOBJ_SPRITE_LAST - count) & 0xffff,
                 (adapter.GOBJ_D6_INIT - count * adapter.GOBJ_D6_ROW_STEP) & 0xffff, 0)
    fixed = (adapter.A_obj_list_base, adapter.A_obj_flags, 0, 0, 0)
    return count, (pass1, pass2, fixed)


def compare_object_list(lib, image):
    """Run recreate's g_draw_object_list (reference) and remaster's rm_draw_object_list (candidate) on
    the same background for each of draw_game_objects' real passes, and diff the whole framebuffer.
    Returns (diff_bytes, footprint)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]
    flip = _r16(image, adapter.A_flip_idx)
    draw_buf = int.from_bytes(image[adapter.A_physbase_tbl + flip:adapter.A_physbase_tbl + flip + 4], "big")
    _count, slots = _objlist_passes(image)
    passes = [p for p in slots if p is not None]

    # reference: recreate's g_ entry, all passes in order on one image.
    ref = bytearray(image)
    fn = bench_frame.harness._lib.g_draw_object_list
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
    fn.restype = None
    ref_buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref)
    for list_off, flags_off, outer, rec_off, colour in passes:
        fn(ref_buf, list_off, flags_off, draw_buf, outer, rec_off, colour)
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    # candidate: remaster's dispatcher on a fresh image view, same passes in order.
    cand = bytearray(image)
    cand_buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(cand)
    ctx = _objlist_ctx(lib, cand_buf, draw_buf)
    for list_off, flags_off, outer, rec_off, colour in passes:
        lib.rm_draw_object_list(ctypes.byref(ctx), cand_buf, list_off, cand_buf, flags_off,
                                outer, rec_off, colour)
    cand_fb = cand[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


# ---- gobj_prefix (draw_game_objects state advance, off-frame) ----
# The prefix writes no pixels; it advances counters + mutates two arenas (the marker-decay records
# and the buf_a anim-word mirrors) and the animated colour. We drive recreate's g_draw_game_objects_
# prefix (reference) and the remaster rm_gobj_prefix on the same poked image, then compare every state
# location each writes: the scalar globals, the animated colour longs, the marker records, and the
# buf_a mirrors.

def _gobj_prefix_state(image):
    return adapter.GobjPrefixState(
        _r16(image, adapter.A_marker_decay), _s16(image, adapter.A_marker_decay + 2),
        _s16(image, adapter.A_marker_decay + 4), _r16(image, adapter.A_view_parity),
        _r16(image, adapter.A_anim_counter), _r16(image, adapter.A_anim_word),
        _r16(image, adapter.A_bonus_timer), _r16(image, adapter.A_dsp_color_scroll),
        _r16(image, adapter.A_flag_seq_off), _s16(image, adapter.A_flag_seq_count))


def compare_gobj_prefix(lib, image):
    """Run recreate's g_draw_game_objects_prefix and remaster's rm_gobj_prefix on the same image and
    compare every state location the prefix writes. Returns a list of (name, ref, cand) mismatches."""
    buf_a = int.from_bytes(image[adapter.A_buf_a:adapter.A_buf_a + 4], "big")

    ref = bytearray(image)
    fn = bench_frame.harness._lib.g_draw_game_objects_prefix
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))

    cand = bytearray(image)
    cbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(cand)
    s = _gobj_prefix_state(image)

    def at(addr):
        return ctypes.cast(ctypes.byref(cbuf, addr), ctypes.POINTER(ctypes.c_uint8))

    assets = adapter.GobjPrefixAssets(
        at(adapter.A_anim_word_tbl), at(adapter.A_anim_coloridx_tbl), at(adapter.A_color_pairs),
        at(adapter.A_marker_decay_base), at(adapter.A_anim_color),
        at(buf_a + adapter.GOBJ_ANIM_BUF_OFF1), at(buf_a + adapter.GOBJ_ANIM_BUF_OFF2))
    lib.rm_gobj_prefix(ctypes.byref(s), ctypes.byref(assets))

    # Write the remaster state scalars back into `cand` so we can compare regions uniformly.
    _w16(cand, adapter.A_marker_decay, s.marker_active & 0xffff)
    _w16(cand, adapter.A_marker_decay + 2, s.marker_off & 0xffff)
    _w16(cand, adapter.A_marker_decay + 4, s.marker_countdown & 0xffff)
    _w16(cand, adapter.A_view_parity, s.view_parity & 0xffff)
    _w16(cand, adapter.A_anim_counter, s.anim_counter & 0xffff)
    _w16(cand, adapter.A_anim_word, s.anim_word & 0xffff)
    _w16(cand, adapter.A_bonus_timer, s.bonus_timer & 0xffff)
    _w16(cand, adapter.A_dsp_color_scroll, s.dsp_color_scroll & 0xffff)
    _w16(cand, adapter.A_flag_seq_off, s.flag_seq_off & 0xffff)
    _w16(cand, adapter.A_flag_seq_count, s.flag_seq_count & 0xffff)

    checks = {
        "marker_decay": (adapter.A_marker_decay, 6),
        "view_parity": (adapter.A_view_parity, 2),
        "anim_counter": (adapter.A_anim_counter, 2),
        "anim_word": (adapter.A_anim_word, 2),
        "anim_color": (adapter.A_anim_color, 8),
        "bonus_timer": (adapter.A_bonus_timer, 2),
        "dsp_color_scroll": (adapter.A_dsp_color_scroll, 2),
        "flag_seq_off": (adapter.A_flag_seq_off, 2),
        "flag_seq_count": (adapter.A_flag_seq_count, 2),
        "marker_recs": (adapter.A_marker_decay_base, adapter.MARKER_RECS_BYTES),
        "anim_mirror1": (buf_a + adapter.GOBJ_ANIM_BUF_OFF1, 2),
        "anim_mirror2": (buf_a + adapter.GOBJ_ANIM_BUF_OFF2, 2),
    }
    bad = []
    for name, (addr, n) in checks.items():
        if ref[addr:addr + n] != cand[addr:addr + n]:
            bad.append((name, bytes(ref[addr:addr + n]), bytes(cand[addr:addr + n])))
    return bad


# ---- draw_game_objects composite (the full per-frame object/scene draw) ----
# The strongest check: run the remaster sub-draws in draw_game_objects' exact order on one frame and
# diff the whole framebuffer against recreate's g_draw_game_objects. In the staged frames draw_buf ==
# SCREEN_BASE, so a Framebuffer overlaid on the image at SCREEN_BASE (the struct-based sprite/ground/
# object draws) and the dispatcher (writing image + draw_buf) share the SAME bytes.

def compare_game_objects(lib, image):
    """Sequence the remaster object sub-draws in draw_game_objects' exact order and diff the whole
    framebuffer vs recreate's g_draw_game_objects. Order: prefix, ground, fg sprite, sprite-pass 1,
    draw_object, sprite-pass 2, then the fixed-object pass + the buggy ordered by the view. Returns
    (diff_bytes, footprint)."""
    base = image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]
    flip = _r16(image, adapter.A_flip_idx)
    draw_buf = int.from_bytes(image[adapter.A_physbase_tbl + flip:adapter.A_physbase_tbl + flip + 4], "big")

    ref = bytearray(image)
    _run_pipeline(ref, ("g_draw_game_objects",))
    ref_fb = ref[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]

    cand = bytearray(image)
    cbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(cand)

    # The prefix runs first and advances view_parity (read by the dispatcher), so run it before
    # snapshotting the native states from `cand`. It writes no pixels; drive recreate's prefix on the
    # candidate image so the downstream reads see the same advanced state as the reference.
    pf = _bind("g_draw_game_objects_prefix")
    pf(cbuf)

    fb = adapter.Framebuffer.from_buffer(cand, adapter.SCREEN_BASE)   # overlay -> shares cand bytes
    sp_state = adapter.sprite_state(cand)
    sp_assets, _spk = adapter.sprite_assets(cand)
    gr_state = adapter.ground_state(cand)
    gr_assets, _grk = adapter.ground_assets(cand)
    obj_in, _ok = adapter.object_input(cand)
    ctx = _objlist_ctx(lib, cbuf, draw_buf)
    _count, (pass1, pass2, fixed) = _objlist_passes(cand)
    view_rear = (_r16(cand, adapter.A_view_flags) & adapter.GOBJ_VIEW_REAR) != 0

    def objlist(p):
        if p is None:
            return
        lo, fo, outer, rec, col = p
        lib.rm_draw_object_list(ctypes.byref(ctx), cbuf, lo, cbuf, fo, outer, rec, col)

    lib.rm_draw_ground(ctypes.byref(gr_state), ctypes.byref(gr_assets), ctypes.byref(fb))
    lib.rm_draw_fg_sprite(ctypes.byref(sp_state), ctypes.byref(sp_assets), ctypes.byref(fb))
    objlist(pass1)                                    # active sprite rows (before draw_object)
    lib.rm_draw_object(ctypes.byref(obj_in), ctypes.byref(fb))
    objlist(pass2)                                    # remaining sprite rows (after draw_object)
    if not view_rear:
        objlist(fixed)
        lib.rm_draw_buggy(ctypes.byref(sp_state), ctypes.byref(sp_assets), ctypes.byref(fb))
    else:
        lib.rm_draw_buggy(ctypes.byref(sp_state), ctypes.byref(sp_assets), ctypes.byref(fb))
        objlist(fixed)

    del fb                                            # drop the overlay before reading cand
    cand_fb = cand[adapter.SCREEN_BASE:adapter.SCREEN_BASE + adapter.SCREEN_BYTES]
    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


# The player-physics state rm_player_update owns, paired with the recreate global it must match.
# (native PlayerState field, image address, signed)
PLAYER_FIELDS = (
    ("engine_rpm", adapter.A_engine_rpm, False),
    ("rpm_cap", adapter.A_leg_flags_c90, False),
    ("rpm_add", adapter.A_leg_flags_c90 + 2, False),
    ("speed_raw", adapter.A_speed_raw, False),
    ("speed", adapter.A_speed, False),
    ("speed_jitter_ph", adapter.A_speed_jitter_ph, False),
    ("scroll_phase", adapter.A_scroll_phase, False),
    ("scroll_speed", adapter.A_scroll_speed, True),
    ("view_flags", adapter.A_view_flags, False),
    ("view_bank", adapter.A_view_bank, False),
    ("ground_view_off", adapter.A_ground_view_off, True),
    ("road_edge_sel", adapter.A_road_edge_sel, True),
    ("wheel_pos", adapter.A_wheel_pos, False),
    ("steer_hold", adapter.A_steer_hold, False),
    ("lean_phase", adapter.A_lean_phase, False),
    ("lean", adapter.A_lean_state, False),
    ("buggy_draw_flag", adapter.A_buggy_draw_flag, False),
    ("road_curve", adapter.A_road_curve, True),
    ("skid", adapter.A_buggy_skid_off, True),
    ("crash_disp", adapter.A_crash_disp, True),
    ("fire_hold", adapter.A_fire_hold, False),
    ("dsp_variant_idx", adapter.A_dsp_variant_idx, False),
    ("leg_flags_sel", adapter.A_leg_flags_sel, False),
    ("time_subctr", adapter.A_time_subctr, False),
    ("time_left", adapter.A_time_left, True),
    ("hud_crash_timer", adapter.A_hud_crash_timer, True),
)

# The globals that put the original into its crash / auto-steer script — the part of game_update this
# slice does not port (see game.h's PRECONDITION). Driving far enough always trips one: the horizon
# events the course dispatches arm a crash after ~40 frames. So the drive CLEARS them after each
# reference frame, staging every frame back inside the regime the ported slice covers, and counts how
# often it had to. crash_phase is left alone: the original only tests it for sign, so any
# non-negative value (a staged image carries 3) leaves the ported path unchanged.
PLAYER_CRASH_GLOBALS = (adapter.A_collision_lock, adapter.A_event_pending, adapter.A_curve_freeze,
                        adapter.A_turn_flags, adapter.A_spin_reset, adapter.A_spin_reset + 2)


# The crash / auto-steer script's own outputs (game_update §6). The script poses the body and kicks
# the curve; these are the fields only it writes, so they are what proves the playout tracked.
PLAYER_SCRIPT_FIELDS = (
    ("steer_delta", adapter.A_steer_delta, True),
    ("buggy_pitch_off", adapter.A_buggy_pitch_off, True),
)

# ...and the two the script writes as single BYTES, which need a byte read rather than a word one.
# Nothing downstream in the physics reads either, so they are invisible unless compared directly:
# without this, transposing their two record offsets in player.c leaves the whole suite green while
# the crash picks the wrong sprite frame and raises the wrong marker effect.
PLAYER_SCRIPT_BYTE_FIELDS = (
    ("anim_frame_sel", adapter.A_anim_frame + 1),
    ("marker_pending", adapter.A_marker_pending),
)

# The globals the course-event engine OWNS: section 12's collision probe, the fx block rebuilt from
# obj_flags, and the horizon-event dispatch are what arm these. That engine is now ported and wired in
# (the leg drive runs it on the candidate too), so these are compared strictly like any other field,
# free-running with no handover — the candidate arms its own crashes and a divergence fails the drive.
PLAYER_EVENT_FIELDS = (
    ("collision_lock", adapter.A_collision_lock, False),
    ("crash_phase", adapter.A_crash_phase, True),
    ("turn_flags", adapter.A_turn_flags, False),
    ("event_pending", adapter.A_event_pending, False),
    ("spin_reset", adapter.A_spin_reset, False),
    ("spin_word2", adapter.A_spin_reset + 2, False),
    ("curve_window_lo", adapter.A_curve_window, False),
    ("curve_window_hi", adapter.A_curve_window + 2, False),
    ("curve_freeze", adapter.A_curve_freeze, False),
)

COURSE_FIELDS = (("row_ctr", adapter.A_course_row_ctr), ("read_pos", adapter.A_course_read_pos))


def player_background(leg=0, warmup=60, pokes=None):
    """A mid-race image ready to drive. Two staging artefacts have to be cleared first or the buggy
    never moves: view_flags is left at the section-12 trigger value 0x10 (not a real 0/2/4/6 view),
    and hud_crash_timer is left armed, which pins the throttle off and forces the brake every frame
    (section 6). `pokes` sets further globals (e.g. a short time_left to reach the time-out)."""
    state = bench_frame.mid_race_state(leg, warmup)
    _w16(state, adapter.A_view_flags, 0)
    _w16(state, adapter.A_hud_crash_timer, 0)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)
    return state


def leg_start_background(leg=0):
    """The image the player actually starts a leg in: the oracle's init_leg with NO warmup frames. It
    needs none of player_background's staging fixups — those clear artefacts the warmup drive leaves
    behind (an armed hud_crash_timer, view_flags parked at the section-12 trigger), and a leg start
    has neither."""
    return bench_frame.mid_race_state(leg, 0)


def leg_start_pre_init(leg=0):
    """The image a leg is initialised FROM (buffers + graphics staged, unpack run, init_leg NOT). Feed
    it to _Candidate(native_init_pre=...) so the candidate's leg-start state comes from rm_init_leg run
    natively rather than the oracle's init_leg — proving the native init is drive-equivalent."""
    import render_screen as R
    img, _buf = R._prepared_image({adapter.A_leg_index: leg.to_bytes(2, "big")})
    return bytearray(img)


def run_init_leg(lib, pre, leg=None):
    """Seed the eight leg-start owner structs from a pre-init image and run rm_init_leg over them.
    Returns a namespace with every mutated struct (player/course/pose/scroll/ring/ev/gobj/sprite),
    the two output scalars (obj_shade/screen_offset) and the HUD-text buffer — plus `keepalive`, the
    RmInitAssets backing arrays that must outlive the struct. Shared by _Candidate._native_init (the
    drive-equivalence path) and test_init_leg (the exact differential) so the seed cannot drift."""
    r = types.SimpleNamespace()
    r.player = adapter.player_state(pre, 0)
    r.course = adapter.course_state(pre)
    r.pose = adapter.road_pose(pre)
    r.scroll = adapter.scroll_state(pre)
    r.ring = adapter.course_ring(pre)
    r.ev = adapter.event_state(pre)
    r.gobj = adapter._gobj_state(pre)
    r.sprite = adapter.sprite_state(pre)
    r.hud_text = (ctypes.c_uint8 * adapter.HUD_TEXT_BYTES).from_buffer_copy(
        pre[adapter.A_hud_text:adapter.A_hud_text + adapter.HUD_TEXT_BYTES])
    r.obj_shade = ctypes.c_int16()
    r.screen_offset = ctypes.c_uint16()
    r.assets, r.keepalive = adapter.init_assets(pre)
    if leg is None:
        leg = _r16(pre, adapter.A_leg_index)
    lib.rm_init_leg(ctypes.byref(r.player), ctypes.byref(r.course), ctypes.byref(r.pose),
                    ctypes.byref(r.scroll), ctypes.byref(r.ring), ctypes.byref(r.ev),
                    ctypes.byref(r.gobj), ctypes.byref(r.sprite), r.hud_text,
                    ctypes.byref(r.obj_shade), ctypes.byref(r.screen_offset),
                    ctypes.byref(r.assets), leg)
    return r


def _staged_ctx(state):
    """A minimal RmEventCtx for callers that drive frames OUTSIDE the §6 event regime
    (compare_player_drive / compare_spin_arming clear the event globals every frame, so the event path
    is never taken — but rm_player_update needs a valid ctx pointer regardless). Built ONCE per drive
    and returned as the whole bundle (its ctypes buffers are the keepalive): the bundle's ev / ring /
    gfx views stay image-fresh from the seed frame and never advance, which is fine precisely because
    the frames that WOULD dispatch through them are excluded from the comparison in both callers. Only
    ctx.player must track the current frame's PlayerState — the caller repoints it each frame before
    the call (ctx.player = ctypes.pointer(p)), which also keeps player/ctx consistent on the rare
    excluded frame that does dispatch."""
    return adapter.event_ctx(state, 0)


def compare_spin_arming(lib, image, pokes, inputs):
    """Directed comparison of §10's spin arming, which no leg drive can reach.

    The arming needs a spin override held (only the unported event system arms one) AND a steering
    lock held past STEER_HOLD_SPIN — a combination the leg drives never produce, because the drives
    that get an override handed to them do not steer and the ones that steer never get an override.
    So this stages the combination instead: `pokes` is re-applied to the reference image BEFORE every
    frame, which both arms the override and makes each frame an independent arming decision (the
    arming consumes the override, so without re-poking only frame 0 would test anything).

    Compares the fields the arming decides — collision_lock, turn_flags and the spin pair — against
    recreate's, so the direction of the spin (which lock throws you and which one settles you, the
    one thing the reference's nested branch encodes) is pinned rather than assumed.

    Returns (mismatches, stats); stats counts the two outcomes so a run that decides nothing is
    visible instead of passing vacuously."""
    state = bytearray(image)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    game_update = _bind("g_game_update")

    mismatches = []
    stats = dict(frames=len(inputs), spun=0, settled=0, events=0)
    ctx_bundle = _staged_ctx(state)   # built once; ev/ring/gfx stay image-fresh (dispatch frames excluded)
    for frame, in_bits in enumerate(inputs):
        for addr, val in pokes.items():
            _w16(state, addr, val & 0xffff)

        p = adapter.player_state(state, in_bits)
        assets, _keep = adapter.player_assets(state)
        ctrl, _keep_ctrl = adapter.road_ctrl(state)
        ctx_bundle.ctx.player = ctypes.pointer(p)
        lib.rm_player_update(ctypes.byref(p), ctypes.byref(assets), ctrl, ctypes.byref(ctx_bundle.ctx))

        _w16(state, adapter.A_input_state, in_bits)
        game_update(buf)

        # A long enough run also trips the unported event system, which arms a collision rather than a
        # spin. It always stamps crash_phase; §10's spin arming never touches it, so that is an exact
        # discriminator — skip those frames and count them (the candidate is re-seeded from the
        # reference every frame, so the run recovers by itself).
        if _r16(state, adapter.A_crash_phase) != 0:
            stats["events"] += 1
            continue

        stats["spun"] += p.collision_lock != 0
        stats["settled"] += p.collision_lock == 0 and p.spin_reset == 0 and p.spin_word2 == 0
        for name, addr, signed in PLAYER_EVENT_FIELDS:
            ref = _i16s(state, addr) if signed else _r16(state, addr)
            if getattr(p, name) != ref:
                mismatches.append((frame, name, getattr(p, name), ref))
    return mismatches, stats


def compare_player_drive(lib, image, inputs):
    """Drive one frame per entry of `inputs` (input_state bit masks) and check remaster's player
    physics tracks recreate's game_update scalar for scalar. Each frame: build a native PlayerState
    from the current image, run rm_player_update against the image's road control table, then advance
    the reference image one frame via g_game_update with the same input and compare every field in
    PLAYER_FIELDS. The candidate is re-seeded from the reference each frame, so a divergence is
    reported where it happens instead of smearing over the rest of the drive.

    A course-advance frame can dispatch a horizon event, which is the out-of-scope system: it kicks
    road_curve, drops rpm, arms the crash script. Such a frame is EXCLUDED from the comparison and
    the physics globals are rolled back to what the ported slice produced, so the drive continues
    inside the regime instead of ending at the first event.

    Returns (mismatches, stats) — mismatches is a list of (frame, field, candidate, reference); stats
    counts the frames reaching each branch worth knowing was exercised, so a drive that degenerates
    (a buggy that never moves, a clamp never hit) is visible instead of silently passing.
    """
    state = bytearray(image)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    game_update = _bind("g_game_update")

    mismatches = []
    stats = dict(frames=len(inputs), wraps=0, events=0, clamp=0, offroad=0, fire=0, timeout=0)
    ctx_bundle = _staged_ctx(state)   # built once; ev/ring/gfx stay image-fresh (dispatch frames excluded)
    for frame, in_bits in enumerate(inputs):
        p = adapter.player_state(state, in_bits)
        assets, _keep = adapter.player_assets(state)
        ctrl, _keep_ctrl = adapter.road_ctrl(state)
        ctx_bundle.ctx.player = ctypes.pointer(p)
        lib.rm_player_update(ctypes.byref(p), ctypes.byref(assets), ctrl, ctypes.byref(ctx_bundle.ctx))

        _w16(state, adapter.A_input_state, in_bits)
        game_update(buf)
        stats["wraps"] += _r16(state, adapter.A_view_wrap_flag) != 0

        if _event_engaged(state):
            stats["events"] += 1
            _restage_player(state, p)
            continue

        stats["clamp"] += bool(p.curve_clamp)
        stats["offroad"] += p.skid != 0
        stats["fire"] += p.fire_hold != 0
        stats["timeout"] += p.hud_crash_timer != 0

        for name, addr, signed in PLAYER_FIELDS:
            ref = _i16s(state, addr) if signed else _r16(state, addr)
            cand = getattr(p, name)
            if cand != ref:
                mismatches.append((frame, name, cand, ref))
        if (_r16(state, adapter.A_view_wrap_flag) != 0) != bool(p.view_wrapped):
            mismatches.append((frame, "view_wrapped", bool(p.view_wrapped),
                               _r16(state, adapter.A_view_wrap_flag) != 0))
    return mismatches, stats


def _event_engaged(state):
    """True if this frame's game_update handed control to the crash / event script (see game.h's
    PRECONDITION). crash_phase is a signed gate the original only tests for sign — an event drives it
    negative, a staged image's positive value is inert."""
    return (any(_r16(state, addr) for addr in PLAYER_CRASH_GLOBALS)
            or _i16s(state, adapter.A_crash_phase) < 0)


def _restage_player(state, p):
    """Roll the reference image's physics state back to what rm_player_update produced, and disarm the
    crash script — so the next frame starts inside the ported slice's regime."""
    for name, addr, _signed in PLAYER_FIELDS:
        _w16(state, addr, getattr(p, name) & 0xffff)
    _w16(state, adapter.A_sprite_suppress, p.skid & 0xffff)   # the dual-use skid carrier (see game.h)
    for addr in PLAYER_CRASH_GLOBALS:
        _w16(state, addr, 0)
    _w16(state, adapter.A_crash_phase, 0)


def _i16s(state, addr):
    v = _r16(state, addr)
    return v - 0x10000 if v & 0x8000 else v


def _ref_crash_fx(state):
    """Reference side of HUD phase 8 (recreate hud.c:323-330): once armed, hud_crash_timer decays each
    frame and — once negative — g_draw_crash_fx runs the leg-end tally (drain -> score, arm abort_flag).
    The leg-drive harness omits the render, so this drives the crash-fx STATE side explicitly, exactly
    as draw_hud would after game_update. The candidate's counterpart is rm_crash_fx_update (in step)."""
    t = _i16s(state, adapter.A_hud_crash_timer)
    if t == 0:
        return
    if t < 0:
        flip = _r16(state, adapter.A_flip_idx)
        buffer = int.from_bytes(
            state[adapter.A_physbase_tbl + flip:adapter.A_physbase_tbl + flip + 4], "big")
        _g_draw_crash_fx((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state), buffer)
    else:
        _w16(state, adapter.A_hud_crash_timer, (t - adapter.RM_HUD_CRASH_DECAY) & 0xffff)


RING_ANIM_CODES = frozenset({0x0d, 0x10, 0x13, 0x16})   # each implies its two successors
RING_ECHOED_CODE = 0x2e          # slot 1 carrying this is echoed into slot 13
RING_ECHO_FROM, RING_ECHO_TO = 1, 13
EDGE_ANY = 0x1000 | 0x2000 | 0x4000      # EDGE_OPEN | EDGE_LEFT | EDGE_RIGHT (mirror include/game.h)


RING_REC_SELECT_OFF, RING_REC_CODES_OFF, RING_REC_MARKER_OFF = 0, 3, 6   # mirror src/course.c
RING_MARKER_RAW_FLAG = 0x8000
RING_MARKER_KIND_MASK, RING_MARKER_KIND_RIGHT = 0xf01e, 0xf012


def _course_record(state, read_pos):
    """Address of the packed course record at `read_pos` in the image's current leg."""
    buf_a = int.from_bytes(state[adapter.A_buf_a:adapter.A_buf_a + 4], "big")
    leg = _r16(state, adapter.A_leg_index)
    base = buf_a + leg * adapter.COURSE_LEG_STRIDE + adapter.COURSE_STREAM_OFF
    return base - read_pos


def _anim_expansion_is_visible(state, read_pos):
    """Would this record's animation expansion leave a mark the comparison can see?

    It usually would not, and that is the whole point of measuring it. In 525 of the 554 animation
    codes across the five legs, the two slots the expansion writes are re-selected by the very same
    record and overwritten with exactly the bytes the expansion would have put there — so removing
    the expansion entirely changes nothing. Only 29 records leave one of those slots unselected.
    Counting "a successor code appeared in the band" therefore proves nothing: the data supplies
    those codes itself. This replays the record's slot selection and reports only the case that
    actually discriminates."""
    rec = _course_record(state, read_pos)
    select = (state[rec + RING_REC_SELECT_OFF] << 8) | state[rec + RING_REC_SELECT_OFF + 1]

    code_at, src = {}, rec + RING_REC_CODES_OFF
    for slot in range(adapter.RM_RING_SLOTS):
        if select & (1 << (adapter.RM_RING_SLOTS - 1 - slot)):
            code_at[slot] = state[src]
            src += 1
    return any(code in RING_ANIM_CODES and (slot + 1 not in code_at or slot + 2 not in code_at)
               for slot, code in code_at.items())


def _record_selects_slot(state, read_pos, want_slot):
    """Did this record's select mask supply `want_slot` itself? Used to tell a slot the unpack DERIVED
    from a slot the data simply provided."""
    rec = _course_record(state, read_pos)
    select = (state[rec + RING_REC_SELECT_OFF] << 8) | state[rec + RING_REC_SELECT_OFF + 1]
    return bool(select & (1 << (adapter.RM_RING_SLOTS - 1 - want_slot)))


def _echo_is_visible(state, read_pos):
    """Would the slot-1 -> slot-13 echo leave a mark the comparison can see? Only if the record does
    NOT select slot 13 itself — 16 records across the five legs supply that 0x2e directly and just 2
    actually need the echo, so counting "slot 13 holds 0x2e" credits the branch on records that would
    look identical with the echo deleted (verified by mutation)."""
    return (_record_selects_slot(state, read_pos, RING_ECHO_FROM)
            and not _record_selects_slot(state, read_pos, RING_ECHO_TO))


def _marker_is_kind_right(state, read_pos):
    """Does this record's marker word take the 'right shoulder only' fixup branch? 25 records across
    the five legs do; none at all take the 'both shoulders' branch, which is why that one is ported
    faithfully but cannot be pinned from this game's data (see test_course_ring)."""
    rec = _course_record(state, read_pos)
    raw = (state[rec + RING_REC_MARKER_OFF] << 8) | state[rec + RING_REC_MARKER_OFF + 1]
    return bool(raw & RING_MARKER_RAW_FLAG) and (raw & RING_MARKER_KIND_MASK) == RING_MARKER_KIND_RIGHT


def _count_ring_branches(state, band, read_pos, stats):
    """Tally which branches of the far band's refill actually fired, so a green ring test cannot be
    green merely because the interesting records were never reached."""
    if _anim_expansion_is_visible(state, read_pos):
        stats["ring_anim_visible"] += 1
    if _marker_is_kind_right(state, read_pos):
        stats["ring_marker_right"] += 1
    if (_echo_is_visible(state, read_pos)
            and band.slot[RING_ECHO_FROM] == RING_ECHOED_CODE
            and band.slot[RING_ECHO_TO] == RING_ECHOED_CODE):
        stats["ring_echoes"] += 1
    # An EDGE_* bit reaching a band is an output fact, not a branch: every marker_unpack path can
    # produce one. It is reported to show the shoulder flags are exercised at all, and no test
    # asserts a branch was taken from it.
    if band.marker & EDGE_ANY:
        stats["ring_edge_bands"] += 1


def _ring_mismatches(frame, cand_ring, state):
    """Compare the candidate's ring against the reference image's row grid, band by band — ALL 14
    bands whole. The horizon-event dispatch runs on the candidate now (it pokes bands 11-13's type
    codes exactly as the reference does), so there is no exempted band any more."""
    out = []
    for band in range(adapter.RM_RING_ROWS):
        row = adapter.A_ring_base + band * adapter.RING_ROW_BYTES
        for slot in range(adapter.RM_RING_SLOTS):
            ref = _r16(state, row + slot * 2)
            if cand_ring.row[band].slot[slot] != ref:
                out.append((frame, f"ring[{band}].slot[{slot}]",
                            cand_ring.row[band].slot[slot], ref))
        ref_marker = _r16(state, row + adapter.RM_RING_SLOTS * 2)
        if cand_ring.row[band].marker != ref_marker:
            out.append((frame, f"ring[{band}].marker", cand_ring.row[band].marker, ref_marker))
    return out


class _Candidate:
    """The remaster side of a leg drive: the structs a self-driving game loop owns, seeded once from
    the leg-start image and thereafter advanced only by remaster's own cores — including, now, the
    course-event engine (probe + fx/horizon dispatch), which arms its own crashes and delivers the
    checkpoint / finish events. The RmEventCtx bundles the same player/pose/ring/ctrl the loop drives,
    plus the event-only state (EventState, the GobjPrefixState bonus/flag counters, the HUD-text score
    window and the graphics arena) so the dispatch mutates exactly what the reference's globals do."""

    def __init__(self, lib, state, native_init_pre=None):
        self.lib = lib
        self.pose = adapter.road_pose(state)
        self.source, self._k_src = adapter.road_source(state)
        self.ctrl = (ctypes.c_uint8 * adapter.RM_CTRL_ALLOC_BYTES)()
        self.scan = (ctypes.c_uint8 * adapter.RM_SCANLINE_BYTES)()
        self.course = adapter.course_state(state)
        self.ring = adapter.course_ring(state)
        self.stream, self._k_stream = adapter.course_stream(state)
        self.scroll = adapter.scroll_state(state)
        playfield, self._k_play = adapter.scroll_playfield(state)
        self.shifted = (ctypes.c_uint8 * (adapter.RM_SCROLL_SHIFTS * adapter.RM_SCROLL_WINDOW))()
        lib.rm_scroll_prebuild(playfield, self.shifted)
        self.fb = adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)())
        self.assets, self._k_assets = adapter.player_assets(state)
        self.player = adapter.player_state(state, 0)
        self.input_prev = 0
        # event-engine state, seeded once and self-driven thereafter (never re-seeded).
        self.ev = adapter.event_state(state)
        self.gobj = adapter._gobj_state(state)
        self.hud_text = (ctypes.c_uint8 * adapter.HUD_TEXT_BYTES).from_buffer_copy(
            state[adapter.A_hud_text:adapter.A_hud_text + adapter.HUD_TEXT_BYTES])
        self.buf_c = int.from_bytes(state[adapter.A_buf_c:adapter.A_buf_c + 4], "big")
        self.gfx = (ctypes.c_uint8 * adapter.GFX_EVENT_BYTES).from_buffer_copy(
            state[self.buf_c:self.buf_c + adapter.GFX_EVENT_BYTES])
        self.evt_assets, self._k_evt = adapter.event_assets(state)
        self.leg = _r16(state, adapter.A_leg_index)
        self.game_over = _r16(state, adapter.A_game_over_flag) != 0
        self.reseed(state, 0)
        # Optionally REPLACE the leg-start owner structs with rm_init_leg's native output (seeded from
        # the pre-init image) instead of the oracle's init_leg (read out of `state`). Everything else —
        # the arenas, the stream, the road control table (built by geometry, not init_leg) — still
        # comes from `state`, so the drive's reference (g_game_update on the post-init image) and the
        # candidate start from the same place iff rm_init_leg reproduces init_leg (pinned by test_init_leg).
        if native_init_pre is not None:
            self._native_init(lib, native_init_pre)
        self._build_ctx()

    def _native_init(self, lib, pre):
        """Produce the leg-start owner structs (player / course / pose / scroll / ring / event / gobj /
        hud_text) by running rm_init_leg on the pre-init image, replacing the oracle-seeded ones."""
        r = run_init_leg(lib, pre, leg=self.leg)     # the drive holds no sprite; the helper makes one
        self.player, self.course, self.pose = r.player, r.course, r.pose
        self.scroll, self.ring, self.ev, self.gobj = r.scroll, r.ring, r.ev, r.gobj
        self.hud_text = r.hud_text
        self._init_assets, self._k_init = r.assets, r.keepalive
        self._init_result = r      # keeps the sprite / output scalars / hud_text buffer alive

    def _build_ctx(self):
        """The RmEventCtx pointing at THIS candidate's live structs (built after reseed so the pointers
        target the final player/pose/ring objects)."""
        self.ctx = adapter.make_event_ctx(
            player=self.player, gobj=self.gobj, ring=self.ring, pose=self.pose, road_src=self.source,
            ctrl=self.ctrl, scanline=self.scan, ev=self.ev, hud_text=self.hud_text, gfx=self.gfx,
            assets=self.evt_assets, leg=self.leg, game_over=self.game_over)

    def reseed(self, state, in_bits):
        """Take the whole driving state from the reference image — used ONCE, to seed the leg start.
        (The former per-crash handover is gone: the candidate now runs the real dispatch, so it arms
        its own crashes and every field is compared strictly, never re-seeded.)"""
        self.player = adapter.player_state(state, in_bits)
        self.pose = adapter.road_pose(state)
        self.course = adapter.course_state(state)
        self.ring = adapter.course_ring(state)
        self.scroll = adapter.scroll_state(state)
        # scroll_state zeroes hscroll_step2 as a render OUTPUT, but across frames it is also an input:
        # section 9 adds it into the curve. Carry the reference's value or the next frame drifts.
        self.scroll.hscroll_step2 = _r16(state, adapter.A_hscroll_step2)
        lo, n = adapter.A_road_curve_tbl, adapter.RM_CTRL_BYTES
        self.ctrl[:n] = state[lo:lo + n]

    def step(self, in_bits):
        """One frame of the game loop: physics (whose §6 event path dispatches through ctx), then on a
        view-wrap the course advance the original runs in section 12 — the collision-probe head, the
        ring/segment scroll, the geometry rebuild (so horizon_row is fresh), and the fx/horizon event
        tail — then the geometry + scroll whose outputs feed back into next frame's physics. Ordering
        mirrors recreate game_update.c: §12 clears event_pending (line 504) and probes before the ring
        scroll; the build inside course_advance (line 570/608) precedes fx_and_events (line 611)."""
        p = self.player
        p.input, p.input_prev = in_bits, self.input_prev
        p.hscroll_step2 = self.scroll.hscroll_step2
        self.input_prev = in_bits
        self.lib.rm_player_update(ctypes.byref(p), ctypes.byref(self.assets), self.ctrl,
                                  ctypes.byref(self.ctx))

        self.pose.curve, self.pose.view_flags = p.road_curve, p.view_flags
        self.scroll.scroll_speed = p.scroll_speed
        if p.view_wrapped:
            p.event_pending = 0                                    # game_update.c:504
            self.lib.rm_course_probe(ctypes.byref(self.ctx))       # §12 collision-probe head
            self.lib.rm_road_course_advance(ctypes.byref(self.pose), ctypes.byref(self.course),
                                            ctypes.byref(self.ring), self.stream)
        self.lib.rm_build_road_geometry(ctypes.byref(self.pose), ctypes.byref(self.source),
                                        ctypes.byref(self.ring), self.ctrl, self.scan)
        if p.view_wrapped:
            self.lib.rm_course_events(ctypes.byref(self.ctx))      # §G/§H/§I: arm crashes + deliver events
        self.scroll.seg_head = self.pose.seg_head
        self.lib.rm_blit_road_scroll(ctypes.byref(self.scroll), self.shifted, ctypes.byref(self.fb))
        # HUD phase 8 (draw_hud runs after game_update): decay the crash-arm timer, or once negative run
        # the leg-end tally that arms abort_flag. The persistent state side; the draw is not in this loop.
        self.lib.rm_crash_fx_update(ctypes.byref(self.ctx))


def compare_leg_drive(lib, image, inputs, native_init_pre=None):
    """Drive a leg free-running on both sides and check remaster tracks recreate scalar for scalar.

    Unlike compare_player_drive, the candidate is NOT re-seeded per frame: it is seeded once from the
    leg-start image and then drives itself — physics, the collision probe, the course advance, the
    geometry rebuild, the horizon-event dispatch, and the scroll — so any drift accumulates and shows
    up instead of being erased every frame. The reference runs the same cores recreate's own frame
    does (g_game_update, whole, including §12's probe/advance/build/fx-and-events; then
    g_blit_road_scroll, whose hscroll_step2 feeds back into the curve).

    NOTHING is handed over any more. The candidate runs the real event engine, so it ARMS ITS OWN
    crashes and delivers its own checkpoint / finish / bonus events; a divergence — the reference
    arming something the candidate did not, or vice versa — surfaces as a strict mismatch in the
    event-owned PlayerState fields (collision_lock / crash_phase / the spin pair / curve_window /
    event_pending) and fails the drive loudly, rather than being reseeded away.

    Every owned surface is compared, all of it now a RESULT rather than an input:

    - The course object/marker ring, ALL 14 bands whole (the dispatch pokes bands 11-13's type codes
      on the candidate exactly as on the reference — the old bands-12/13 exemption is gone).
    - The road control table (its per-band widths come from the ring's marker column, and a bonus
      display record rebuilds it inside the dispatch).
    - EventState (crash_bars / crash_active / crash_lap / gauge_blink[_on] / ckpt_scroll / spin_state,
      the dashboard progress marker and the collision-probe bit cursor), the GobjPrefixState bonus /
      flag-sequence / marker-decay counters the dispatch bumps, and the score digits in the shared
      HUD-text window.

    Returns (mismatches, stats): mismatches is a list of (frame, field, candidate, reference); stats
    counts the frames worth knowing were reached — including crashes the CANDIDATE armed, checkpoints
    reached, and any leg-end — so a drive that never crashes, never recovers or never moves is visible
    rather than vacuously green."""
    state = bytearray(image)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    game_update = _bind("g_game_update")
    cand = _Candidate(lib, state, native_init_pre=native_init_pre)

    stats = dict(frames=len(inputs), wraps=0, armed=0, crash_frames=0, handoffs=0, checkpoints=0,
                 leg_end=0, abort_armed=0, leg_over=0, clamp=0, offroad=0, ring_checked=0,
                 ring_refills=0, ring_ages=0,
                 ring_anim_visible=0, ring_marker_right=0, ring_echoes=0, ring_edge_bands=0)
    mismatches = []
    for frame, in_bits in enumerate(inputs):
        was_locked = cand.player.collision_lock
        crash_bars_before = cand.ev.crash_bars
        read_pos_before = cand.course.read_pos
        cand.step(in_bits)
        refilled = cand.player.view_wrapped and cand.course.read_pos != read_pos_before
        aged = cand.player.view_wrapped and not refilled

        _w16(state, adapter.A_input_state, in_bits)
        game_update(buf)
        _run_pipeline(state, ("g_blit_road_scroll",))
        _ref_crash_fx(state)                                      # HUD phase 8 (mirrors cand.step's tail)

        # Stats reflect what the CANDIDATE (running the real event engine) did, not a handover.
        stats["wraps"] += _r16(state, adapter.A_view_wrap_flag) != 0
        abort = cand.ev.abort_flag - 0x10000 if cand.ev.abort_flag & 0x8000 else cand.ev.abort_flag
        stats["abort_armed"] += cand.ev.abort_flag != 0
        stats["leg_over"] += abort < 0                             # abort_flag negative -> leg ends
        stats["armed"] += was_locked == 0 and cand.player.collision_lock != 0   # candidate armed a crash
        stats["crash_frames"] += cand.player.collision_lock != 0
        stats["handoffs"] += was_locked != 0 and cand.player.collision_lock == 0
        stats["checkpoints"] += cand.ev.crash_bars != crash_bars_before          # checkpoint marker fired
        stats["leg_end"] += cand.player.hud_crash_timer == adapter.RM_HUD_TIMER_LEG_END  # leg-complete arm
        stats["clamp"] += bool(cand.player.curve_clamp)
        stats["offroad"] += cand.player.skid != 0
        stats["ring_refills"] += refilled
        stats["ring_ages"] += aged
        if refilled:
            _count_ring_branches(state, cand.ring.row[0], cand.course.read_pos, stats)

        lo, n = adapter.A_road_curve_tbl, adapter.RM_CTRL_BYTES
        d = _first_diff("ctrl", bytes(cand.ctrl)[:n], bytes(state[lo:lo + n]))
        if d:
            mismatches.append((frame,) + d)
        mismatches.extend(_ring_mismatches(frame, cand.ring, state))
        stats["ring_checked"] += 1

        for name, addr, signed in PLAYER_FIELDS + PLAYER_SCRIPT_FIELDS + PLAYER_EVENT_FIELDS:
            ref = _i16s(state, addr) if signed else _r16(state, addr)
            cand_val = getattr(cand.player, name)
            if cand_val != ref:
                mismatches.append((frame, name, cand_val, ref))
        for name, addr in PLAYER_SCRIPT_BYTE_FIELDS:
            if getattr(cand.player, name) != state[addr]:
                mismatches.append((frame, name, getattr(cand.player, name), state[addr]))
        for name, addr in COURSE_FIELDS:
            ref = _r16(state, addr)
            if getattr(cand.course, name) != ref:
                mismatches.append((frame, name, getattr(cand.course, name), ref))
        if (_r16(state, adapter.A_view_wrap_flag) != 0) != bool(cand.player.view_wrapped):
            mismatches.append((frame, "view_wrapped", bool(cand.player.view_wrapped),
                               _r16(state, adapter.A_view_wrap_flag) != 0))

        # The event surfaces the dispatch now runs on the candidate too (EventState scalars + the
        # dashboard marker + the flag-bit cursor; the GobjPrefixState bonus / flag / marker-decay
        # counters; the score digits in the shared HUD-text window) — the same portion the directed
        # dispatch / course-events checks compare, via the shared _event_state_mismatches helper.
        mismatches.extend((frame,) + m for m in _event_state_mismatches(cand, state))
    return mismatches, stats


# ---- course-event engine (game_update §12 tail + the jump-table dispatch) ----
# rm_event_dispatch / rm_course_events / rm_course_probe run on native structs the adapter builds
# from a staged image; the recreate references (g_gu_dispatch_event / g_game_update_fx_and_events /
# g_probe_collision) run in-image. We compare every state location the engine owns: the crash-script
# PlayerState fields, the EventState counters, the GobjPrefixState bonus/flag fields, ring rows 11-13
# (the bands the obj_active pokes and the horizon dispatch land in), the shared HUD-text window (the
# score digits), the road control table (disp_bonus rebuilds it), and the graphics arena (the
# dashboard / banner bitmaps the checkpoint path writes).

# (native field, image addr, signed) grouped by owning struct.
EVENT_PLAYER_FIELDS = (
    ("collision_lock", adapter.A_collision_lock, False),
    ("crash_phase", adapter.A_crash_phase, True),
    ("turn_flags", adapter.A_turn_flags, False),
    ("event_pending", adapter.A_event_pending, False),
    ("spin_reset", adapter.A_spin_reset, False),
    ("spin_word2", adapter.A_spin_reset + 2, False),
    ("curve_window_lo", adapter.A_curve_window, False),
    ("curve_window_hi", adapter.A_curve_window + 2, False),
    ("curve_freeze", adapter.A_curve_freeze, False),
    ("engine_rpm", adapter.A_engine_rpm, False),
    ("speed", adapter.A_speed, False),
    ("road_curve", adapter.A_road_curve, True),
    ("hud_crash_timer", adapter.A_hud_crash_timer, True),
    ("time_left", adapter.A_time_left, True),
)
EVENT_EV_FIELDS = (
    ("crash_bars", adapter.A_crash_bars, False),
    ("crash_active", adapter.A_crash_active, False),
    ("crash_lap", adapter.A_crash_lap, False),
    ("gauge_blink", adapter.A_gauge_blink, False),
    ("gauge_blink_on", adapter.A_gauge_blink_on, False),
    ("ckpt_scroll", adapter.A_ckpt_scroll, False),
    ("spin_state", adapter.A_spin_state, False),
    ("crash_frame", adapter.A_crash_frame, False),   # crash-fx tally counter (rm_crash_fx_update)
    ("abort_flag", adapter.A_abort_flag, False),      # leg/game-over countdown (< 0 ends the leg)
)
EVENT_GOBJ_FIELDS = (
    ("flag_seq_count", adapter.A_flag_seq_count, True),
    ("bonus_timer", adapter.A_bonus_timer, False),
    ("marker_active", adapter.A_marker_decay, False),
    ("marker_off", adapter.A_marker_decay + 2, True),
    ("marker_countdown", adapter.A_marker_decay + 4, True),
    ("flag_seq_off", adapter.A_flag_seq_off, False),
)
EVENT_RING_BANDS = (11, 12, 13)   # obj_active pokes + the horizon dispatch land here


def _gu_dispatch_fn():
    fn = bench_frame.harness._lib.g_gu_dispatch_event
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
    fn.restype = None
    return fn


def _ref_read(ref, addr, signed):
    return _i16s(ref, addr) if signed else _r16(ref, addr)


def _first_diff(name, cand, ref):
    """(f'{name}[i]', cand[i], ref[i]) for the first differing byte of two equal-length byte strings,
    or None if they match. The reusable form of the four buffer scans the event checks share."""
    if cand == ref:
        return None
    i = next(k for k in range(len(cand)) if cand[k] != ref[k])
    return (f"{name}[{i:#x}]", cand[i], ref[i])


def _event_state_mismatches(b, ref):
    """The event-owned surfaces BOTH the leg drive and the directed dispatch / course-events checks
    compare: EventState scalars + the dashboard marker + the flag-bit cursor, the GobjPrefixState
    bonus / flag / marker-decay counters, and the score digits in the shared HUD-text window. `b` is
    any object exposing .ev / .gobj / .hud_text (a run event bundle or a _Candidate); `ref` is the
    reference image bytes. Returns [(name, candidate, reference), ...]; the leg-drive caller prepends
    a frame number. The ring, the ctrl table and the (broader) player field set are NOT here — the two
    callers scan those differently, so they stay at each call site."""
    out = []
    for name, addr, signed in EVENT_EV_FIELDS:
        if getattr(b.ev, name) != _ref_read(ref, addr, signed):
            out.append((name, getattr(b.ev, name), _ref_read(ref, addr, signed)))
    # dash_marker: two bytes + a word
    for name, addr in (("dash_y", adapter.A_dash_marker), ("dash_bit", adapter.A_dash_marker + 1)):
        if getattr(b.ev, name) != ref[addr]:
            out.append((name, getattr(b.ev, name), ref[addr]))
    if b.ev.dash_x != _r16(ref, adapter.A_dash_marker + 2):
        out.append(("dash_x", b.ev.dash_x, _r16(ref, adapter.A_dash_marker + 2)))
    if b.ev.course_flag_bit != ref[adapter.A_course_flag_bit]:
        out.append(("course_flag_bit", b.ev.course_flag_bit, ref[adapter.A_course_flag_bit]))
    for name, addr, signed in EVENT_GOBJ_FIELDS:
        if getattr(b.gobj, name) != _ref_read(ref, addr, signed):
            out.append((name, getattr(b.gobj, name), _ref_read(ref, addr, signed)))
    d = _first_diff("hud_text", bytes(b.hud_text),
                    bytes(ref[adapter.A_hud_text:adapter.A_hud_text + adapter.HUD_TEXT_BYTES]))
    if d:
        out.append(d)
    return out


def _event_mismatches(b, ref, check_ctrl=True, check_gfx=False):
    """Compare the run event bundle `b` against the reference image `ref`, location by location."""
    out = []
    for name, addr, signed in EVENT_PLAYER_FIELDS:
        if getattr(b.player, name) != _ref_read(ref, addr, signed):
            out.append((name, getattr(b.player, name), _ref_read(ref, addr, signed)))
    out.extend(_event_state_mismatches(b, ref))

    for band in EVENT_RING_BANDS:
        row = adapter.A_ring_base + band * adapter.RING_ROW_BYTES
        for slot in range(adapter.RM_RING_SLOTS):
            if b.ring.row[band].slot[slot] != _r16(ref, row + slot * 2):
                out.append((f"ring[{band}].slot[{slot}]", b.ring.row[band].slot[slot],
                            _r16(ref, row + slot * 2)))
        if b.ring.row[band].marker != _r16(ref, row + adapter.RM_RING_SLOTS * 2):
            out.append((f"ring[{band}].marker", b.ring.row[band].marker,
                        _r16(ref, row + adapter.RM_RING_SLOTS * 2)))

    if check_ctrl:
        n = adapter.RM_CTRL_BYTES
        d = _first_diff("ctrl", bytes(b.ctrl)[:n],
                        bytes(ref[adapter.A_road_curve_tbl:adapter.A_road_curve_tbl + n]))
        if d:
            out.append(d)

    if check_gfx:
        d = _first_diff("gfx", bytes(b.gfx), bytes(ref[b.buf_c:b.buf_c + adapter.GFX_EVENT_BYTES]))
        if d:
            out.append(d)
    return out


# The mid-race base image is deterministic per (leg, warmup) but costs an init_leg emulation plus the
# warmup game_update frames to build; the dispatch fuzz asks for the same (leg 1, warmup 40) base
# thousands of times. Cache the base bytes once per (leg, warmup) and copy per case.
_EVENT_BASE_CACHE = {}


def event_background(leg=0, warmup=60, pokes=None):
    """A realistic mid-race image with the event-engine globals optionally poked. `pokes` writes are
    16-bit words at the given image addresses (a byte field's low byte is its word's low byte)."""
    base = _EVENT_BASE_CACHE.get((leg, warmup))
    if base is None:
        base = bytes(bench_frame.mid_race_state(leg, warmup))
        _EVENT_BASE_CACHE[(leg, warmup)] = base
    state = bytearray(base)
    for addr, val in (pokes or {}).items():
        _w16(state, addr, val & 0xffff)
    return state


def compare_event_dispatch(lib, image, idx, slot, flag_a, flag_b):
    """Run recreate's g_gu_dispatch_event and remaster's rm_event_dispatch on the same staged image
    and compare every owned location. Returns a list of (name, candidate, reference)."""
    ref = bytearray(image)
    _gu_dispatch_fn()((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref),
                      idx, slot, flag_a, flag_b)
    b = adapter.event_ctx(image)
    lib.rm_event_dispatch(ctypes.byref(b.ctx), idx, slot, flag_a, flag_b)
    return _event_mismatches(b, ref, check_ctrl=True, check_gfx=False)


def compare_course_events(lib, image):
    """Run recreate's g_game_update_fx_and_events and remaster's rm_course_events on the same staged
    image and compare every owned location (incl. the graphics arena). Returns mismatches."""
    ref = bytearray(image)
    _bind("g_game_update_fx_and_events")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    b = adapter.event_ctx(image)
    lib.rm_course_events(ctypes.byref(b.ctx))
    return _event_mismatches(b, ref, check_ctrl=True, check_gfx=True)


def compare_crash_fx(lib, image):
    """Run recreate's HUD phase 8 (decay hud_crash_timer, or once negative g_draw_crash_fx's leg-end
    tally — see _ref_crash_fx) and remaster's rm_crash_fx_update on the same staged image, then compare
    every owned location: the crash-fx PlayerState scalars (hud_crash_timer / time_left), the EventState
    counters (crash_frame / crash_lap / crash_active / crash_bars / abort_flag), and the whole HUD-text
    window (the rollover records + score digits + the score/lap display lines the tally rewrites). The
    ring / ctrl / gfx / gobj surfaces are compared too (the tally must not touch them). Returns
    mismatches."""
    ref = bytearray(image)
    _ref_crash_fx(ref)
    b = adapter.event_ctx(image)
    lib.rm_crash_fx_update(ctypes.byref(b.ctx))
    return _event_mismatches(b, ref, check_ctrl=True, check_gfx=True)


def _coll_mask_base(image):
    """Image address of the current leg's collision-flag long table (crash_bars 0)."""
    buf_a = int.from_bytes(image[adapter.A_buf_a:adapter.A_buf_a + 4], "big")
    leg = _r16(image, adapter.A_leg_index)
    return buf_a + leg * adapter.COURSE_LEG_STRIDE + adapter.COURSE_MASK_OFF


def compare_course_probe(lib, image, mask, start_bit, dash=None):
    """Directed comparison of rm_course_probe. Pokes the leg-0 collision-flag long and course_flag_bit
    (and, if given, `dash` = (y, bit, x) onto the progress marker), runs the native probe head, and
    checks: (1) the flag-bit walk (increment + wrap) matches a Python mirror of the C, and (2) when the
    probed bit fires, the dashboard marker walk matches recreate's g_probe_collision on the same dash
    state + bitmap. Returns (mismatches, fired)."""
    state = bytearray(image)
    _w16(state, adapter.A_crash_bars, 0)
    state[adapter.A_course_flag_bit] = start_bit & 0xff
    if dash is not None:
        state[adapter.A_dash_marker] = dash[0] & 0xff
        state[adapter.A_dash_marker + 1] = dash[1] & 0xff
        _w16(state, adapter.A_dash_marker + 2, dash[2] & 0xffff)
    base = _coll_mask_base(state)
    state[base:base + 4] = (mask & 0xffffffff).to_bytes(4, "big")

    # Python mirror of the flag-bit walk (rm_course_probe head).
    expected_bit = (start_bit + 1) & 0xff
    byte0 = (mask >> 24) & 0xff
    if ((byte0 - expected_bit) & 0xff) & 0x80:            # (int8)(byte0 - expected) < 0
        expected_bit = 0
    fired = bool(mask & (1 << (expected_bit & 0x1f)))

    b = adapter.event_ctx(state)
    lib.rm_course_probe(ctypes.byref(b.ctx))

    out = []
    if b.ev.course_flag_bit != expected_bit:
        out.append(("course_flag_bit", b.ev.course_flag_bit, expected_bit))

    if fired:
        ref = bytearray(state)
        _bind("g_probe_collision")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
        for name, addr in (("dash_y", adapter.A_dash_marker), ("dash_bit", adapter.A_dash_marker + 1)):
            if getattr(b.ev, name) != ref[addr]:
                out.append((name, getattr(b.ev, name), ref[addr]))
        if b.ev.dash_x != _r16(ref, adapter.A_dash_marker + 2):
            out.append(("dash_x", b.ev.dash_x, _r16(ref, adapter.A_dash_marker + 2)))
        d = _first_diff("gfx", bytes(b.gfx), bytes(ref[b.buf_c:b.buf_c + adapter.GFX_EVENT_BYTES]))
        if d:
            out.append(d)
    else:
        # no fire: the marker + bitmap must be untouched.
        seed = adapter.event_state(state)
        if (b.ev.dash_y, b.ev.dash_bit, b.ev.dash_x) != (seed.dash_y, seed.dash_bit, seed.dash_x):
            out.append(("dash_marker(nofire)", (b.ev.dash_y, b.ev.dash_bit, b.ev.dash_x),
                        (seed.dash_y, seed.dash_bit, seed.dash_x)))
        if bytes(b.gfx) != bytes(state[b.buf_c:b.buf_c + adapter.GFX_EVENT_BYTES]):
            out.append(("gfx(nofire)", "changed", "unchanged"))
    return out, fired
