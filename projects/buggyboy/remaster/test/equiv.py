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
    lib.rm_player_update.argtypes = [ctypes.POINTER(adapter.PlayerState),
                                     ctypes.POINTER(adapter.PlayerAssets),
                                     ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_player_update.restype = None
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
        lib.rm_road_course_advance(ctypes.byref(pose), ctypes.byref(cs), stream)
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
    for frame, in_bits in enumerate(inputs):
        p = adapter.player_state(state, in_bits)
        assets, _keep = adapter.player_assets(state)
        ctrl, _keep_ctrl = adapter.road_ctrl(state)
        lib.rm_player_update(ctypes.byref(p), ctypes.byref(assets), ctrl)

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
