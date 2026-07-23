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
    lib.rm_road_course_advance.restype = ctypes.c_bool
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
    lib.rm_course_mode_event.argtypes = [ectx, ctypes.POINTER(ctypes.c_int16),
                                         ctypes.POINTER(ctypes.c_uint16),
                                         ctypes.POINTER(ctypes.c_uint8),
                                         ctypes.POINTER(adapter.RmPaletteWrite)]
    lib.rm_course_mode_event.restype = None
    lib.rm_crash_fx_update.argtypes = [ectx]
    lib.rm_crash_fx_update.restype = None
    lib.rm_event_classify.argtypes = [ctypes.c_uint16]
    lib.rm_event_classify.restype = ctypes.c_uint32
    P = ctypes.POINTER
    lib.rm_init_leg.argtypes = [
        P(adapter.PlayerState), P(adapter.CourseState), P(adapter.RoadPose),
        P(adapter.ScrollState), P(adapter.CourseRing), P(adapter.EventState),
        P(adapter.GobjPrefixState), P(adapter.SpriteState), P(ctypes.c_uint8),
        P(ctypes.c_int16), P(ctypes.c_uint16), P(ctypes.c_uint8),
        P(adapter.RmInitAssets), ctypes.c_uint16]
    lib.rm_init_leg.restype = None
    lib.rm_apply_player.argtypes = [
        P(adapter.PlayerState), P(adapter.EventState), P(adapter.RoadPose), P(adapter.ScrollState),
        P(adapter.SpriteState), P(adapter.GroundState), P(adapter.ObjListCtx), P(adapter.HudState),
        P(adapter.RoadInput), u8p]
    lib.rm_apply_player.restype = None
    lib.rm_intermission_poll.argtypes = [ctypes.POINTER(adapter.Framebuffer), u8p, u8p]
    lib.rm_intermission_poll.restype = None
    lib.rm_draw_intermission.argtypes = [ctypes.POINTER(adapter.Framebuffer),
                                         ctypes.POINTER(adapter.RmIntermissionAssets), ctypes.c_int16]
    lib.rm_draw_intermission.restype = None
    lib.rm_fade_step.argtypes = [ctypes.POINTER(adapter.Framebuffer),
                                 ctypes.POINTER(adapter.RmIntermissionAssets), ctypes.c_int16]
    lib.rm_fade_step.restype = None
    lib.rm_draw_leg_results.argtypes = [ctypes.POINTER(adapter.Framebuffer),
                                        ctypes.POINTER(adapter.RmResultsAssets), ctypes.c_uint16]
    lib.rm_draw_leg_results.restype = None
    lib.rm_draw_divider.argtypes = [ctypes.POINTER(adapter.Framebuffer), u8p]
    lib.rm_draw_divider.restype = None
    lib.rm_draw_panel5.argtypes = [ctypes.POINTER(adapter.Framebuffer),
                                   ctypes.POINTER(adapter.RmResultsAssets)]
    lib.rm_draw_panel5.restype = None
    # ---- flow state machine (slice B) ----
    fsp = ctypes.POINTER(adapter.FlowState)
    lib.rm_check_abort.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
    lib.rm_check_abort.restype = ctypes.c_uint32
    for fn in (lib.rm_int_stepA, lib.rm_int_stepD_counter):
        fn.argtypes = [fsp]
        fn.restype = ctypes.c_int
    lib.rm_int_phaseB_leg.argtypes = [fsp]
    lib.rm_int_phaseB_leg.restype = None
    lib.rm_update_highscore.argtypes = [fsp, u8p, u8p]
    lib.rm_update_highscore.restype = None
    lib.rm_draw_results_screen.argtypes = [ctypes.POINTER(adapter.Framebuffer),
                                           ctypes.POINTER(adapter.RmResultsScreenAssets),
                                           ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16]
    lib.rm_draw_results_screen.restype = None
    lib.rm_hiscore_countdown.argtypes = [fsp, u8p]
    lib.rm_hiscore_countdown.restype = ctypes.c_int
    lib.rm_hiscore_charstep.argtypes = [fsp, u8p]
    lib.rm_hiscore_charstep.restype = None
    lib.rm_init_playfield_nav.argtypes = [fsp]
    lib.rm_init_playfield_nav.restype = None
    lib.rm_init_playfield_fire.argtypes = [fsp]
    lib.rm_init_playfield_fire.restype = ctypes.c_bool
    # ---- flow COMPOSITION driver (slice D) ----
    opsp = ctypes.POINTER(adapter.FlowOps)
    tunp = ctypes.POINTER(adapter.FlowTuning)
    for fn in (lib.rm_flow_intermission_cycle, lib.rm_flow_intermission, lib.rm_flow_game_over,
               lib.rm_flow_leg_select):
        fn.argtypes = [fsp, opsp, ctypes.c_void_p, tunp]
        fn.restype = ctypes.c_int
    lib.rm_flow_name_entry.argtypes = [fsp, opsp, ctypes.c_void_p, tunp, u8p, u8p]
    lib.rm_flow_name_entry.restype = ctypes.c_int
    lib.rm_flow_game_over_tail.argtypes = [fsp, opsp, ctypes.c_void_p]
    lib.rm_flow_game_over_tail.restype = ctypes.c_int
    lib.rm_flow_score_tail.argtypes = [fsp, opsp, ctypes.c_void_p, tunp, u8p, u8p]
    lib.rm_flow_score_tail.restype = ctypes.c_int
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

    return _coverage_fb(cand_fb, base, ref_fb)


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


# ACCEL bit (game.h RM_IN_ACCEL / input.c) — throttle drives the view-wraps that pull course records.
_RM_IN_ACCEL = 0x01


def compare_mode2_scroll(lib, image, read_pos, frames=90):
    """Verify the mode-2 re-prebuilt scroll PIXELS, not just the screen_offset scalar.

    A mode-2 screen-offset event moves screen_offset, and the shell re-runs rm_scroll_prebuild from the
    new offset before the next blit (game_main.c course_mode_event). test_course_mode_event pins the
    screen_offset scalar; this pins the pixels that scalar selects. Drive the reference (g_game_update,
    ACCEL) from a read_pos staged so the first view-wrap pulls a mode-2 record, until screen_offset
    moves, then re-prebuild from the NEW offset and blit and compare the whole framebuffer byte-exact vs
    recreate's g_blit_road_scroll at that state (compare_scroll's path — the same offset feeds both
    sides). Returns (fired, diff, scalars_ok)."""
    state = bytearray(image)
    _w16(state, adapter.A_course_read_pos, read_pos - 8)   # +8 on the first pull -> read_pos
    _w16(state, adapter.A_course_row_ctr, 0)               # underflow on the first wrap -> pull
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    game_update = _bind("g_game_update")
    screen_off_before = _r16(state, adapter.A_screen_offset)
    fired = False
    for _ in range(frames):
        _w16(state, adapter.A_input_state, _RM_IN_ACCEL)
        game_update(buf)
        if _r16(state, adapter.A_screen_offset) != screen_off_before:
            fired = True
            break
    diff, scalars_ok = compare_scroll(lib, state)          # prebuild + blit from the NEW screen_offset
    return fired, diff, scalars_ok


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
    # The in-race palette phase 11 stages into: seed from the image's baked race palette (0x17fa2), as
    # the shell seeds it from fixture_palette; phase 11 overlays regs 5-11 (RM_PAL_STAGE_*).
    r.race_pal = (ctypes.c_uint8 * adapter.RACE_PAL_BYTES).from_buffer_copy(
        pre[adapter.A_race_palette:adapter.A_race_palette + adapter.RACE_PAL_BYTES])
    r.assets, r.keepalive = adapter.init_assets(pre)
    if leg is None:
        leg = _r16(pre, adapter.A_leg_index)
    lib.rm_init_leg(ctypes.byref(r.player), ctypes.byref(r.course), ctypes.byref(r.pose),
                    ctypes.byref(r.scroll), ctypes.byref(r.ring), ctypes.byref(r.ev),
                    ctypes.byref(r.gobj), ctypes.byref(r.sprite), r.hud_text,
                    ctypes.byref(r.obj_shade), ctypes.byref(r.screen_offset), r.race_pal,
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
        # mode-2/4/6 course-event outputs the shell owns: obj_shade (draw_object), screen_offset (scroll
        # source) and the in-race palette phase 11 / mode 4 stage into. Seeded from the image, then
        # advanced only by rm_course_mode_event (fired on a record pull), like the reference's globals.
        self.obj_shade = ctypes.c_int16(_i16s(state, adapter.A_obj_shade))
        self.screen_offset = ctypes.c_uint16(_r16(state, adapter.A_screen_offset))
        self.race_pal = (ctypes.c_uint8 * adapter.RACE_PAL_BYTES).from_buffer_copy(
            state[adapter.A_race_palette:adapter.A_race_palette + adapter.RACE_PAL_BYTES])
        self._pw = adapter.RmPaletteWrite()
        # The mode-2/4/6 selector the course-event dispatch acted on THIS frame (None on a frame with no
        # record pull), surfaced for the drive stats so the mode-fired counts read the event's own signal
        # rather than inferring it from which EventState scalar moved (see compare_leg_drive).
        self._mode_fired = None
        self.reseed(state, 0)
        # Optionally REPLACE the leg-start owner structs with rm_init_leg's native output (seeded from
        # the pre-init image) instead of the oracle's init_leg (read out of `state`). Everything else —
        # the arenas, the stream, the road control table (built by geometry, not init_leg) — still
        # comes from `state`, so the drive's reference (g_game_update on the post-init image) and the
        # candidate start from the same place iff rm_init_leg reproduces init_leg (pinned by test_init_leg).
        if native_init_pre is not None:
            self._native_init(lib, native_init_pre)
        self._build_ctx()

        # The draw-struct fan-out the shell runs after each frame (game_main.c apply_player, hoisted to
        # rm_apply_player). self.sprite carries the four crash/spin-script fields the fg / lower-body
        # draws READ but that no owner struct field used to reach — the seam this closes. The scratch
        # views catch the fan-out's other outputs (not pinned here); _edge_base is a never-dereferenced
        # base for road->edge_tbl (the fan-out only stores base+sel, it does not read through it).
        self.sprite = adapter.SpriteState()
        self._fanout_views = (adapter.RoadPose(), adapter.ScrollState(), adapter.GroundState(),
                              adapter.ObjListCtx(), adapter.HudState(), adapter.RoadInput())
        self._edge_base = (ctypes.c_uint8 * adapter.ROAD_EDGE_ALL_BANKS_BYTES)()

    def _native_init(self, lib, pre):
        """Produce the leg-start owner structs (player / course / pose / scroll / ring / event / gobj /
        hud_text) by running rm_init_leg on the pre-init image, replacing the oracle-seeded ones."""
        r = run_init_leg(lib, pre, leg=self.leg)     # the drive holds no sprite; the helper makes one
        self.player, self.course, self.pose = r.player, r.course, r.pose
        self.scroll, self.ring, self.ev, self.gobj = r.scroll, r.ring, r.ev, r.gobj
        self.hud_text = r.hud_text
        self.obj_shade, self.screen_offset, self.race_pal = r.obj_shade, r.screen_offset, r.race_pal
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
        self._mode_fired = None                                    # set below iff a record is pulled this frame
        self.lib.rm_player_update(ctypes.byref(p), ctypes.byref(self.assets), self.ctrl,
                                  ctypes.byref(self.ctx))

        self.pose.curve, self.pose.view_flags = p.road_curve, p.view_flags
        self.scroll.scroll_speed = p.scroll_speed
        if p.view_wrapped:
            p.event_pending = 0                                    # game_update.c:504
            self.lib.rm_course_probe(ctypes.byref(self.ctx))       # §12 collision-probe head
            self._pulled = self.lib.rm_road_course_advance(ctypes.byref(self.pose), ctypes.byref(self.course),
                                                           ctypes.byref(self.ring), self.stream)
        self.lib.rm_build_road_geometry(ctypes.byref(self.pose), ctypes.byref(self.source),
                                        ctypes.byref(self.ring), self.ctrl, self.scan)
        if p.view_wrapped:
            if self._pulled:                                       # mode-2/4/6 event (record pulled)
                # The dispatch's OWN selector (ring row-0 marker high byte & mask), read exactly as
                # rm_course_mode_event reads it — the writer-independent signal the stats key off.
                self._mode_fired = (self.ring.row[0].marker >> 8) & adapter.RM_MODE_MASK
                self.lib.rm_course_mode_event(ctypes.byref(self.ctx), ctypes.byref(self.obj_shade),
                                              ctypes.byref(self.screen_offset), self.race_pal,
                                              ctypes.byref(self._pw))
            self.lib.rm_course_events(ctypes.byref(self.ctx))      # §G/§H/§I: arm crashes + deliver events
        self.scroll.seg_head = self.pose.seg_head
        self.lib.rm_blit_road_scroll(ctypes.byref(self.scroll), self.shifted, ctypes.byref(self.fb))
        # HUD phase 8 (draw_hud runs after game_update): decay the crash-arm timer, or once negative run
        # the leg-end tally that arms abort_flag. The persistent state side; the draw is not in this loop.
        self.lib.rm_crash_fx_update(ctypes.byref(self.ctx))
        # Fan the frame's outputs to the render structs, exactly as the shell does after the physics/
        # events tail (game_update_step -> apply_player). Only self.sprite's four crash/spin fields are
        # pinned (against the recreate image) in _fanout_mismatches; the rest land in scratch views.
        self._apply_fanout()

    def _apply_fanout(self):
        pose, scroll, ground, objlist, hud, road = self._fanout_views
        self.lib.rm_apply_player(
            ctypes.byref(self.player), ctypes.byref(self.ev), ctypes.byref(pose),
            ctypes.byref(scroll), ctypes.byref(self.sprite), ctypes.byref(ground),
            ctypes.byref(objlist), ctypes.byref(hud), ctypes.byref(road), self._edge_base)


def _abort_signed(abort_flag):
    """Sign-extend the 16-bit abort_flag word (negative arms the leg-end)."""
    return abort_flag - 0x10000 if abort_flag & 0x8000 else abort_flag


def _drive_frame(cand, state, buf, game_update, in_bits):
    """One free-running drive frame in lockstep: advance the candidate, then run the same cores
    recreate's frame runs (g_game_update + the road-scroll blit + HUD phase-8 crash-fx) on the reference
    image. Shared by compare_leg_drive and compare_game_flow."""
    cand.step(in_bits)
    _w16(state, adapter.A_input_state, in_bits)
    game_update(buf)
    _run_pipeline(state, ("g_blit_road_scroll",))
    _ref_crash_fx(state)                                  # HUD phase 8 (mirrors cand.step's tail)


# The draw-struct fan-out (rm_apply_player): the four SpriteState fields the fg / lower-body sprite
# draws READ but that no owner struct field used to reach — the seam apply_player MISSED (dirt/wheel
# sprite stuck on the road during a jump). Each is pinned against the recreate image byte(s)
# g_game_update writes, so the fan-out reproduces the original's aliasing (byte width + which byte)
# exactly, not a guess: anim_frame is the word at 0x18d0c (hi byte 0, low = the script's rec[5]);
# spin_state is the hi byte of the fx<<8 word at 0x18caa; spin_reset is the long at 0x18cc8; and
# collision_lock is the word at 0x18c84.
def _fanout_mismatches(frame, cand, state):
    s = cand.sprite
    checks = (
        ("fanout_anim_frame", s.anim_frame & 0xffff, _r16(state, adapter.A_anim_frame)),
        ("fanout_spin_state", s.spin_state & 0xff, state[adapter.A_spin_state]),
        ("fanout_spin_reset", s.spin_reset & 0xffffffff,
         int.from_bytes(state[adapter.A_spin_reset:adapter.A_spin_reset + 4], "big")),
        ("fanout_collision_lock", s.collision_lock & 0xffff, _r16(state, adapter.A_collision_lock)),
    )
    return [(frame, name, c, r) for name, c, r in checks if c != r]


# The mode-2/4/6 course-event outputs the shell owns (rm_course_mode_event): obj_shade (draw_object's
# fill selector) and screen_offset (the scroll source) plus the four palette pieces mode 4 / init phase
# 11 stage. race_pal mirrors image 0x17fa2..; only the WRITTEN pieces are pinned (the rest never moves).
_PAL_STAGE_PIECES = ((0x17fac, 2), (0x17fb0, 2), (0x17fb2, 4), (0x17fb6, 4))


def staged_palette_mismatches(race_pal, ref):
    """Compare the four palette pieces phase 11 / mode 4 stage over regs 5-11 (`race_pal`) against the
    reference image's in-race palette window (`ref` at A_race_palette). Only the WRITTEN pieces move (the
    rest of the palette is an off-image Setpalette seam that never changes), so exactly those are checked.
    Returns [(label, cand_hex, ref_hex)] for each differing piece; the caller prepends any frame column.
    Shared by _mode_event_mismatches (the leg drive) and test_init_leg (the exact init differential)."""
    pal = bytes(race_pal)
    out = []
    for addr, n in _PAL_STAGE_PIECES:
        off = addr - adapter.A_race_palette
        c, r = pal[off:off + n].hex(), bytes(ref[addr:addr + n]).hex()
        if c != r:
            out.append(("race_pal@%#x" % addr, c, r))
    return out


def _mode_event_mismatches(frame, cand, state):
    out = []
    if cand.obj_shade.value != _i16s(state, adapter.A_obj_shade):
        out.append((frame, "obj_shade", cand.obj_shade.value, _i16s(state, adapter.A_obj_shade)))
    if cand.screen_offset.value != _r16(state, adapter.A_screen_offset):
        out.append((frame, "screen_offset", cand.screen_offset.value, _r16(state, adapter.A_screen_offset)))
    for label, c, r in staged_palette_mismatches(cand.race_pal, state):
        out.append((frame, label, c, r))
    return out


def _drive_mismatches(frame, cand, state):
    """Every owned surface compared for one free-running drive frame: the road control table, the course
    ring, the PlayerState / CourseState scalars, the view-wrap flag, the event-owned state (EventState +
    GobjPrefixState + the HUD-text score digits), the mode-2/4/6 course-event outputs (obj_shade /
    screen_offset / the staged palette), and the draw-struct fan-out (four SpriteState crash/spin
    fields). Returns [(frame, field, cand, ref)]."""
    out = []
    lo, n = adapter.A_road_curve_tbl, adapter.RM_CTRL_BYTES
    d = _first_diff("ctrl", bytes(cand.ctrl)[:n], bytes(state[lo:lo + n]))
    if d:
        out.append((frame,) + d)
    out.extend(_ring_mismatches(frame, cand.ring, state))
    for name, addr, signed in PLAYER_FIELDS + PLAYER_SCRIPT_FIELDS + PLAYER_EVENT_FIELDS:
        ref = _i16s(state, addr) if signed else _r16(state, addr)
        cand_val = getattr(cand.player, name)
        if cand_val != ref:
            out.append((frame, name, cand_val, ref))
    for name, addr in PLAYER_SCRIPT_BYTE_FIELDS:
        if getattr(cand.player, name) != state[addr]:
            out.append((frame, name, getattr(cand.player, name), state[addr]))
    for name, addr in COURSE_FIELDS:
        ref = _r16(state, addr)
        if getattr(cand.course, name) != ref:
            out.append((frame, name, getattr(cand.course, name), ref))
    if (_r16(state, adapter.A_view_wrap_flag) != 0) != bool(cand.player.view_wrapped):
        out.append((frame, "view_wrapped", bool(cand.player.view_wrapped),
                    _r16(state, adapter.A_view_wrap_flag) != 0))
    out.extend((frame,) + m for m in _event_state_mismatches(cand, state))
    out.extend(_mode_event_mismatches(frame, cand, state))
    out.extend(_fanout_mismatches(frame, cand, state))
    return out


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
                 ring_anim_visible=0, ring_marker_right=0, ring_echoes=0, ring_edge_bands=0,
                 mode2=0, mode4=0, mode6=0,
                 fanout_anim_nz=0, fanout_spin_state_nz=0, fanout_collision_nz=0, fanout_spin_reset_nz=0)
    mismatches = []
    for frame, in_bits in enumerate(inputs):
        was_locked = cand.player.collision_lock
        crash_bars_before = cand.ev.crash_bars
        read_pos_before = cand.course.read_pos
        _drive_frame(cand, state, buf, game_update, in_bits)
        # Which mode-2/4/6 event fired, from the dispatch's OWN outputs rather than inferred from which
        # EventState scalar moved: pw.kind is the palette event's declared kind (mode 4 = SETPALETTE,
        # mode 6 = POKE_REG — counted even when reg_sel == 0 leaves palette_toggle unmoved), and the
        # ring-marker selector distinguishes mode 2 (screen offset, no palette kind) from a no-op pull.
        # rm_course_mode_event resets pw.kind on every pull, so gating on "a record fired this frame"
        # (cand._mode_fired is not None) keeps a stale kind from an earlier frame out. Writer-independent:
        # immune to a second writer of the scroll_frame / palette_cursor / palette_toggle fields.
        if cand._mode_fired is not None:
            if cand._pw.kind == adapter.PAL_SETPALETTE:
                stats["mode4"] += 1
            elif cand._pw.kind == adapter.PAL_POKE_REG:
                stats["mode6"] += 1
            elif cand._mode_fired == adapter.RM_MODE_SCREEN_OFFSET:
                stats["mode2"] += 1
        refilled = cand.player.view_wrapped and cand.course.read_pos != read_pos_before
        aged = cand.player.view_wrapped and not refilled

        # Stats reflect what the CANDIDATE (running the real event engine) did, not a handover.
        stats["wraps"] += _r16(state, adapter.A_view_wrap_flag) != 0
        abort = _abort_signed(cand.ev.abort_flag)
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

        stats["ring_checked"] += 1
        # Fan-out nonzero coverage: the crash/spin script drives these off zero, so a green run that
        # never leaves zero would pin the aliasing only against 0==0. Counted so the nonzero test above
        # (test_fanout_*) can prove the fields actually moved.
        stats["fanout_anim_nz"] += cand.sprite.anim_frame != 0
        stats["fanout_spin_state_nz"] += (cand.sprite.spin_state & 0xff) != 0
        stats["fanout_collision_nz"] += cand.sprite.collision_lock != 0
        stats["fanout_spin_reset_nz"] += cand.sprite.spin_reset != 0
        # Every owned surface: the ctrl table, the ring, the player/course scalars, the view-wrap flag,
        # and the event-owned state (the same portion the directed dispatch / course-events checks
        # compare, via the shared _event_state_mismatches helper). Shared with compare_game_flow.
        mismatches.extend(_drive_mismatches(frame, cand, state))
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
    ("scroll_frame", adapter.A_scroll_frame, False),   # mode-2 course event (rm_course_mode_event)
    ("palette_cursor", adapter.A_palette_cursor, False),  # mode-4 course event
    ("palette_toggle", adapter.A_palette_toggle, False),  # mode-4/6 course event
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


# ---- between-legs flow draw surfaces (intermission / results, slice A) ----
# These draw into physbase_tbl[flip_idx] (NOT necessarily SCREEN_BASE), so the reference/candidate
# framebuffer is the region at that draw-buffer address. recreate exports each g_ as a leaf taking the
# image; the candidate runs the remaster core on the same background via the adapter's native structs.

def flow_background(leg=0, warmup=60, scroll=None, flip=0):
    """A mid-race image staged for the between-legs draw surfaces: run init_scoretable (populate the
    hi-score table draw_intermission scrolls — the prepared image leaves it zero), optionally select
    the flip=4 draw buffer, and poke int_scroll. Returns the image bytearray."""
    base = _EVENT_BASE_CACHE.get((leg, warmup))
    if base is None:
        base = bytes(bench_frame.mid_race_state(leg, warmup))
        _EVENT_BASE_CACHE[(leg, warmup)] = base
    state = bytearray(base)
    _bind("g_init_scoretable")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state))
    if flip == 4:
        state[adapter.A_physbase_tbl + 4:adapter.A_physbase_tbl + 8] = \
            adapter.FLOW_DRAW_BUF_ALT.to_bytes(4, "big")
        _w16(state, adapter.A_flip_idx, 4)
    else:
        _w16(state, adapter.A_flip_idx, 0)
    if scroll is not None:
        _w16(state, adapter.A_int_scroll, scroll & 0xffff)
    return state


def _flow_ref(image, gname):
    """Run recreate's g_<name>(image) and return (base, ref_fb) — the draw-buffer region (at the
    flip-selected physbase) before and after the reference draw."""
    draw_buf = adapter.draw_buffer_addr(image)
    base = bytes(image[draw_buf:draw_buf + adapter.SCREEN_BYTES])
    ref = bytearray(image)
    _bind(gname)((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    ref_fb = bytes(ref[draw_buf:draw_buf + adapter.SCREEN_BYTES])
    return base, ref_fb


def _flow_fb(base):
    return adapter.Framebuffer((ctypes.c_uint8 * adapter.SCREEN_BYTES)(*base))


def _whole_fb(cand_fb, base, ref_fb):
    diff = sum(1 for i in range(adapter.SCREEN_BYTES) if cand_fb[i] != ref_fb[i])
    footprint = sum(1 for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i])
    return diff, footprint


def _coverage_fb(cand_fb, base, ref_fb):
    """Footprint coverage + no-wrong-pixel over a draw buffer: coverage in [0,1] of the bytes the
    reference changed that the candidate reproduces, and the count of bytes the candidate changed to a
    value the reference did not. Shared by the composite-draw comparisons (compare_hud,
    compare_draw_intermission) that report partial coverage rather than a strict whole-buffer diff."""
    footprint = [i for i in range(adapter.SCREEN_BYTES) if ref_fb[i] != base[i]]
    matched = sum(1 for i in footprint if cand_fb[i] == ref_fb[i])
    wrong = sum(1 for i in range(adapter.SCREEN_BYTES)
                if cand_fb[i] != base[i] and cand_fb[i] != ref_fb[i])
    coverage = matched / len(footprint) if footprint else 1.0
    return coverage, wrong


def compare_intermission_poll(lib, image):
    """recreate g_intermission_poll vs remaster rm_intermission_poll on the same background; whole
    draw-buffer diff (the block copy is a leaf). Returns (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_intermission_poll")
    a, _keep = adapter.intermission_assets(image)
    fb = _flow_fb(base)
    lib.rm_intermission_poll(ctypes.byref(fb), a.poll_src, a.poll_blits)
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_leg_results(lib, image):
    """recreate g_draw_leg_results vs remaster rm_draw_leg_results; whole draw-buffer diff (the fills +
    panels + dashboard leave the rest untouched on both sides). Returns (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_draw_leg_results")
    leg = _r16(image, adapter.A_leg_index)
    a, _keep = adapter.results_assets(image)
    fb = _flow_fb(base)
    lib.rm_draw_leg_results(ctypes.byref(fb), ctypes.byref(a), leg)
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_divider(lib, image):
    """recreate g_draw_divider vs remaster rm_draw_divider; whole draw-buffer diff (a rectangle + two
    vertical lines, all in the draw buffer). Returns (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_draw_divider")
    color_pairs = adapter._u8buf(image, adapter.A_color_pairs, adapter.COLOR_PAIRS_BYTES)
    fb = _flow_fb(base)
    lib.rm_draw_divider(ctypes.byref(fb),
                        ctypes.cast(color_pairs, ctypes.POINTER(ctypes.c_uint8)))
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_panel5(lib, image):
    """recreate g_draw_panel5 vs remaster rm_draw_panel5; whole draw-buffer diff (divider + five labels).
    Returns (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_draw_panel5")
    a, _keep = adapter.results_assets(image)
    fb = _flow_fb(base)
    lib.rm_draw_panel5(ctypes.byref(fb), ctypes.byref(a))
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_results_screen(lib, image):
    """recreate g_draw_results_screen vs remaster rm_draw_results_screen on the same background; whole
    draw-buffer diff (the RACE-END / name-entry screen). mode/pos/leg are read from the poked image
    (A_results_mode / A_hiscore_pos / A_leg_index) and passed to the candidate. Returns
    (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_draw_results_screen")
    mode = _r16(image, adapter.A_results_mode)
    pos = _r16(image, adapter.A_hiscore_pos)
    leg = _r16(image, adapter.A_leg_index)
    a, _keep = adapter.results_screen_assets(image)
    fb = _flow_fb(base)
    lib.rm_draw_results_screen(ctypes.byref(fb), ctypes.byref(a), mode, pos, leg)
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_fade_step(lib, image):
    """recreate g_fade_step vs remaster rm_fade_step; whole draw-buffer diff (fade_step fills the whole
    screen then overlays). Returns (diff_bytes, footprint)."""
    base, ref_fb = _flow_ref(image, "g_fade_step")
    scroll = adapter._i16(image, adapter.A_int_scroll)
    a, _keep = adapter.intermission_assets(image)
    fb = _flow_fb(base)
    lib.rm_fade_step(ctypes.byref(fb), ctypes.byref(a), scroll)
    return _whole_fb(bytes(fb.px), base, ref_fb)


def compare_draw_intermission(lib, image):
    """recreate g_draw_intermission vs remaster rm_draw_intermission on the same background. Reported
    as FOOTPRINT COVERAGE + no-wrong-pixel (the composite scrolls three ported sections): coverage in
    [0,1] over the bytes draw_intermission changes; wrong = bytes the candidate changed to a value
    recreate did not. Returns (coverage, wrong)."""
    base, ref_fb = _flow_ref(image, "g_draw_intermission")
    scroll = adapter._i16(image, adapter.A_int_scroll)
    a, _keep = adapter.intermission_assets(image)
    fb = _flow_fb(base)
    lib.rm_draw_intermission(ctypes.byref(fb), ctypes.byref(a), scroll)
    return _coverage_fb(bytes(fb.px), base, ref_fb)


# ---- between-legs FLOW state machine (slice B) ----
# The flow's LOGIC (phase-counter arithmetic, the abort poll, the high-score insert, the leg-select
# nav) is native C over FlowState; the recreate references are the verified g_int_* / g_check_abort /
# g_update_highscore / g_init_playfield_* exports, run in-image. The compared surface is the flow's
# scalar counters (and, for update_highscore, the 0x280 table + the mutated score record).

_FLOW_FIELD = {name: (addr, signed) for name, addr, signed in adapter.FLOW_FIELDS}


def _flow_mismatches(fs, ref, names):
    """Compare the named FlowState fields against the reference image. Returns [(name, cand, ref)]."""
    out = []
    for name in names:
        addr, signed = _FLOW_FIELD[name]
        r = _i16s(ref, addr) if signed else _r16(ref, addr)
        c = getattr(fs, name)
        if not signed:
            c &= 0xffff
        if c != r:
            out.append((name, c, r))
    return out


def _bind_ret(name, restype, nargs=0):
    """Bind a recreate g_ export taking the image (+ nargs uint32 extra args) with a return type."""
    fn = getattr(bench_frame.harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * nargs
    fn.restype = restype
    return fn


_BLANK_IMAGE = None


def _stage_input_ref(gname, restype, input_state, input_prev):
    """Stage the two input words into the shared blank image and run recreate's g_<gname>(image) — the
    common prologue of the abort / fire leaf comparisons (both read only input_state/input_prev). Returns
    the reference return value."""
    global _BLANK_IMAGE
    if _BLANK_IMAGE is None:
        _BLANK_IMAGE = bytearray(bench_frame.IMAGE_SIZE)
    state = _BLANK_IMAGE
    _w16(state, adapter.A_input_state, input_state & 0xffff)
    _w16(state, adapter.A_input_prev, input_prev & 0xffff)
    return _bind_ret(gname, restype)((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state))


def compare_check_abort(lib, input_state, input_prev):
    """recreate g_check_abort vs remaster rm_check_abort over one (input_state, input_prev) pair.
    Returns (candidate, reference) — both the 32-bit d0 value (abort code / swapped console read)."""
    ref = _stage_input_ref("g_check_abort", ctypes.c_uint32, input_state, input_prev)
    cand = lib.rm_check_abort(input_state & 0xffff, input_prev & 0xffff)
    return cand & 0xffffffff, ref & 0xffffffff


def compare_int_stepA(lib, image):
    """recreate g_int_stepA vs remaster rm_int_stepA on the same staged counters. Compares the three
    Phase-A counter words + the 3-way return code (the oracle's draw is a seam we don't diff). Returns
    (mismatches, ret_cand, ret_ref)."""
    ref = bytearray(image)
    ret_r = _bind_ret("g_int_stepA", ctypes.c_int)(
        (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    fs = adapter.flow_state(image)
    ret_c = lib.rm_int_stepA(ctypes.byref(fs))
    bad = _flow_mismatches(fs, ref, ("int_timer", "int_scroll", "int_frame"))
    return bad, ret_c, ret_r


def compare_int_phaseB_leg(lib, image):
    """recreate g_int_phaseB_leg vs remaster rm_int_phaseB_leg. Compares leg_select + leg_index."""
    ref = bytearray(image)
    _bind("g_int_phaseB_leg")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    fs = adapter.flow_state(image)
    lib.rm_int_phaseB_leg(ctypes.byref(fs))
    return _flow_mismatches(fs, ref, ("leg_select", "leg_index"))


def compare_int_stepD_counter(lib, image):
    """recreate g_int_stepD_counter vs remaster rm_int_stepD_counter. Compares int_frame_hi +
    leg_index + the 3-way return (the oracle's init_leg_dash on ADVANCE is the host's seam, not diffed).
    Returns (mismatches, ret_cand, ret_ref)."""
    ref = bytearray(image)
    ret_r = _bind_ret("g_int_stepD_counter", ctypes.c_int)(
        (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    fs = adapter.flow_state(image)
    ret_c = lib.rm_int_stepD_counter(ctypes.byref(fs))
    bad = _flow_mismatches(fs, ref, ("int_frame_hi", "leg_index"))
    return bad, ret_c, ret_r


def compare_update_highscore(lib, image):
    """recreate g_update_highscore (prefix checkpoint) vs remaster rm_update_highscore on a pre-staged
    image (score record + leg table + leg_index poked by the caller). Compares the whole 0x280 table,
    the mutated 12-byte score record, and results_mode / hiscore_pos / countdown_timer / countdown_sub.
    Returns a list of (name, candidate, reference)."""
    ref = bytearray(image)
    _bind("g_update_highscore")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))

    fs = adapter.flow_state(image)
    hs = adapter.highscore_buffer(image)
    score = adapter.score_record(image)
    lib.rm_update_highscore(ctypes.byref(fs), hs, score)

    out = []
    d = _first_diff("table", bytes(hs),
                    bytes(ref[adapter.A_highscore_table:adapter.A_highscore_table
                              + adapter.FLOW_HIGHSCORE_BYTES]))
    if d:
        out.append(d)
    rec_lo = adapter.A_hud_text + adapter.HS_SCORE_REC_OFF
    d = _first_diff("score", bytes(score), bytes(ref[rec_lo:rec_lo + adapter.HS_SCORE_REC_BYTES]))
    if d:
        out.append(d)
    out.extend(_flow_mismatches(fs, ref,
               ("results_mode", "hiscore_pos", "countdown_timer", "countdown_sub")))
    return out


# ---- name-entry per-frame slices (highscore.c g_hiscore_countdown / g_hiscore_charstep) ----
# The two deterministic pieces of the interactive initials screen, diffed against the oracle exactly as
# recreate's test_highscore slices them (the surrounding loop never returns under the oracle). The time
# digits the countdown writes land in a small `score_line` buffer (image 0x1825e/0x1825f); the countdown
# scalars stay in FlowState (compared against image 0x18262/0x18264 via _flow_mismatches).

def compare_hiscore_countdown(lib, image):
    """recreate g_hiscore_countdown vs remaster rm_hiscore_countdown on the same staged countdown.
    Compares countdown_timer / countdown_sub, the two 'TIME nn' digits, and the timeout return.
    Returns (mismatches, ret_cand, ret_ref)."""
    ref = bytearray(image)
    ret_r = _bind_ret("g_hiscore_countdown", ctypes.c_int)(
        (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))

    fs = adapter.flow_state(image)
    score_line = (ctypes.c_uint8 * adapter.FLOW_SCORE_LINE_BYTES).from_buffer_copy(
        bytes(image[adapter.A_score_line:adapter.A_score_line + adapter.FLOW_SCORE_LINE_BYTES]))
    ret_c = lib.rm_hiscore_countdown(ctypes.byref(fs), score_line)

    bad = _flow_mismatches(fs, ref, ("countdown_timer", "countdown_sub"))
    # only the two time digits are written here (not the countdown scalars, which overlap this window).
    hi = adapter.HS_TIME_HI_OFF
    d = _first_diff("time_digits", bytes(score_line[hi:hi + 2]),
                    bytes(ref[adapter.A_time_digit_hi:adapter.A_time_digit_hi + 2]))
    if d:
        bad.append(d)
    return bad, ret_c, ret_r


CS_NAME_ADDR = 0x18400   # scratch image byte holding the current initial (== recreate's test)


def compare_hiscore_charstep(lib, image):
    """recreate g_hiscore_charstep vs remaster rm_hiscore_charstep on the same staged input + char.
    Compares leg_dec_delay / leg_inc_delay and the mutated initial byte. Returns the mismatches."""
    ref = bytearray(image)
    fn = getattr(bench_frame.harness._lib, "g_hiscore_charstep")
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    fn.restype = None
    fn((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref), CS_NAME_ADDR)

    fs = adapter.flow_state(image)
    cand = bytearray(image)
    cbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(cand)
    name_ptr = ctypes.cast(ctypes.byref(cbuf, CS_NAME_ADDR), ctypes.POINTER(ctypes.c_uint8))
    lib.rm_hiscore_charstep(ctypes.byref(fs), name_ptr)

    bad = _flow_mismatches(fs, ref, ("leg_dec_delay", "leg_inc_delay"))
    if cand[CS_NAME_ADDR] != ref[CS_NAME_ADDR]:
        bad.append(("name", cand[CS_NAME_ADDR], ref[CS_NAME_ADDR]))
    return bad


# ---- composed: the interactive name-entry loop (rm_flow_name_entry) ----
# The loop that sequences the per-frame slices is a FlowOps driver, run here with recording ops + a
# scripted joystick over a MUTABLE highscore + score_line. Honest about what each half pins: the per-frame
# countdown/charstep are ALREADY oracle-diffed above; this pins the SEQUENCING (the prime/terminal draws,
# the per-frame draw/flash/show/poll order) STRUCTURALLY (a recording log), and the loop's own bookkeeping
# (the initials written into row+8, the confirm/backspace/timeout termination, the rank cleared) directly.

def _name_field_off(fs):
    return (fs.leg_index * adapter.HIGHSCORE_LEG_STRIDE
            + (fs.hiscore_pos - 1) * adapter.HIGHSCORE_ROW + adapter.HS_NAME_FIELD_OFF)


# A short terminal-hold count for the recording drives, so the log carries a handful of hold_frame
# markers (enough to pin the count) rather than the 121-frame shipping default. The default itself is
# pinned == HS_HOLD_FRAMES by test_course_ring's constants test.
NAME_ENTRY_HOLD_FRAMES = 3


def _name_entry_tuning(hold_frames=NAME_ENTRY_HOLD_FRAMES):
    """A FlowTuning carrying only what the name-entry tail reads (t->hold_frames); the attract knobs are
    unused here, so they stay 0."""
    return adapter.FlowTuning(hold_frames=hold_frames)


def drive_name_entry(lib, image, poll_of, seed_char=0x41, hold_frames=NAME_ENTRY_HOLD_FRAMES):
    """Drive rm_flow_name_entry with recording ops + a scripted joystick over a mutable highscore +
    score_line seeded from `image` (leg_index / hiscore_pos / results_mode / countdown_* come from the
    poked FlowState). The winning row's initial byte is seeded to `seed_char` (0x41 non-DEL confirms it;
    0x60 = the '`' delete sentinel exercises the backspace arm). `hold_frames` is the terminal-hold count
    the driver runs. Returns (result, log, highscore_bytes, fs)."""
    fs = adapter.flow_state(image)
    rec = _DriverRecorder(fs, _FlowScript(poll_of, lambda i: 0, lambda i: -1))
    tuning = _name_entry_tuning(hold_frames)
    highscore = (ctypes.c_uint8 * adapter.FLOW_HIGHSCORE_BYTES).from_buffer_copy(
        bytes(image[adapter.A_highscore_table:adapter.A_highscore_table + adapter.FLOW_HIGHSCORE_BYTES]))
    highscore[_name_field_off(fs)] = seed_char
    score_line = (ctypes.c_uint8 * adapter.FLOW_SCORE_LINE_BYTES).from_buffer_copy(
        bytes(image[adapter.A_score_line:adapter.A_score_line + adapter.FLOW_SCORE_LINE_BYTES]))
    result = lib.rm_flow_name_entry(ctypes.byref(fs), ctypes.byref(rec.ops), None,
                                    ctypes.byref(tuning), highscore, score_line)
    return result, rec.log, bytes(highscore), fs


def drive_game_over_tail(lib, image):
    """Drive rm_flow_game_over_tail with recording ops (the missed-the-table path). Returns (result, log)."""
    fs = adapter.flow_state(image)
    rec = _DriverRecorder(fs, _FlowScript(lambda i: 0, lambda i: 0, lambda i: -1))
    result = lib.rm_flow_game_over_tail(ctypes.byref(fs), ctypes.byref(rec.ops), None)
    return result, rec.log


def drive_score_tail(lib, image, poll_of=lambda i: 0, hold_frames=NAME_ENTRY_HOLD_FRAMES):
    """Drive rm_flow_score_tail (the made/missed dispatch) with recording ops. results_mode in `image`
    selects the branch: 0 -> name entry, 2 -> the game-over redraw. Returns (result, log, highscore_bytes,
    fs)."""
    fs = adapter.flow_state(image)
    rec = _DriverRecorder(fs, _FlowScript(poll_of, lambda i: 0, lambda i: -1))
    tuning = _name_entry_tuning(hold_frames)
    highscore = (ctypes.c_uint8 * adapter.FLOW_HIGHSCORE_BYTES).from_buffer_copy(
        bytes(image[adapter.A_highscore_table:adapter.A_highscore_table + adapter.FLOW_HIGHSCORE_BYTES]))
    if fs.results_mode == 0:                       # made the table: seed the winning row's first initial
        highscore[_name_field_off(fs)] = 0x41
    score_line = (ctypes.c_uint8 * adapter.FLOW_SCORE_LINE_BYTES).from_buffer_copy(
        bytes(image[adapter.A_score_line:adapter.A_score_line + adapter.FLOW_SCORE_LINE_BYTES]))
    result = lib.rm_flow_score_tail(ctypes.byref(fs), ctypes.byref(rec.ops), None,
                                    ctypes.byref(tuning), highscore, score_line)
    return result, rec.log, bytes(highscore), fs


def compare_init_playfield_nav(lib, image):
    """recreate g_init_playfield_nav vs remaster rm_init_playfield_nav. Compares leg_index, the two
    auto-repeat delays and the idle countdown (the input-change reload)."""
    ref = bytearray(image)
    _bind("g_init_playfield_nav")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref))
    fs = adapter.flow_state(image)
    lib.rm_init_playfield_nav(ctypes.byref(fs))
    return _flow_mismatches(fs, ref,
                            ("leg_index", "leg_dec_delay", "leg_inc_delay", "idle_countdown"))


def compare_init_playfield_fire(lib, input_state, input_prev):
    """recreate g_init_playfield_fire vs remaster rm_init_playfield_fire. Returns (candidate, reference)
    as 0/1 (the fresh-fire-press verdict)."""
    ref = _stage_input_ref("g_init_playfield_fire", ctypes.c_int, input_state, input_prev)
    fs = adapter.FlowState()
    fs.input_state, fs.input_prev = input_state & 0xffff, input_prev & 0xffff
    cand = lib.rm_init_playfield_fire(ctypes.byref(fs))
    return int(bool(cand)), int(bool(ref))


# ---- composed attract cycle (intermission phases A -> D, host-driven vs the oracle slices) ----
# g_intermission never returns (it loops forever except on abort), so the whole loop cannot run to
# rts — exactly as recreate's own test enters each PC. The composed differential instead DRIVES the
# candidate FlowState through g_intermission's control structure (prologue -> Phase A break -> Phase B
# pick -> Phase C's frame count -> Phase D carousel -> restart).
#
# What each phase actually pins, stated honestly:
#   Phases A / B / D are ORACLE-LOCKSTEPPED: every rm phase step (rm_int_stepA / _phaseB_leg /
#     _stepD_counter) runs beside the matching g_int_* slice on a reference image and the counters +
#     return code are compared. Phase A's full ~9000-frame scroll-out is not run (each frame draws); a
#     handful of lockstep frames pin the loop body, then the counters jump to the break edge where BOTH
#     must produce RM_INT_A_BREAK. Phase D locksteps the whole carousel.
#   Phase C is a BOUNDARY-COUNT ONLY, not an oracle diff: the block is a pure-Python mirror of
#     g_intermission's inline 0x96-frame count, run identically on both "sides", so it cannot itself
#     fail — its only guard is that the 0x96 magic is the pinned INT_C_FRAMES constant (pinned equal to
#     the C #define by test_course_ring.test_python_constants_match_the_c). The demo pipeline Phase C
#     runs is pinned SEPARATELY and for real by the leg drives (compare_leg_drive / test_leg_drive);
#     this cycle does not re-verify it.
# The Vsync/palette/flip/sound are off-image seams (see flow.h).

def compare_attract_cycle(lib, image, phaseA_frames=24):
    """Drive one full attract cycle's flow-counter trajectory, candidate (rm_int_*) vs oracle
    (g_int_*), and return (mismatches, stats)."""
    ref = bytearray(image)
    _w16(ref, adapter.A_input_state, 0)            # no abort during the scroll (input == prev)
    _w16(ref, adapter.A_input_prev, 0)
    stepA = _bind_ret("g_int_stepA", ctypes.c_int)
    stepD = _bind_ret("g_int_stepD_counter", ctypes.c_int)
    phaseB = _bind("g_int_phaseB_leg")
    rbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref)

    fs = adapter.flow_state(ref)
    mism, stats = [], dict(phaseA=0, breakA=0, phaseD=0, advances=0, restart=0)

    def prologue():
        for tgt, val in (("int_frame", adapter.INT_FRAME_INIT), ("int_timer", adapter.INT_TIMER_INIT),
                         ("int_scroll", adapter.INT_SCROLL_INIT)):
            setattr(fs, tgt, val)
            _w16(ref, _FLOW_FIELD[tgt][0], val)

    # Prologue (0x27a0).
    prologue()

    # Phase A (0x27cc): lockstep a handful of scroll frames, then jump to the break edge.
    for _ in range(phaseA_frames):
        ret_r = stepA(rbuf)
        ret_c = lib.rm_int_stepA(ctypes.byref(fs))
        stats["phaseA"] += 1
        if ret_c != ret_r:
            mism.append(("phaseA.ret", ret_c, ret_r))
        mism.extend(("phaseA." + n, c, r)
                    for n, c, r in _flow_mismatches(fs, ref, ("int_timer", "int_scroll", "int_frame")))
        assert ret_r != adapter.RM_INT_A_BREAK, "phase A broke before the frame cap (unexpected)"
    # Jump both counters to the break edge: scroll underflow + dwell exhausted, timer in the gate.
    for tgt, val in (("int_scroll", 0), ("int_frame", 0), ("int_timer", 0x50)):
        setattr(fs, tgt, val)
        _w16(ref, _FLOW_FIELD[tgt][0], val)
    ret_r, ret_c = stepA(rbuf), lib.rm_int_stepA(ctypes.byref(fs))
    stats["breakA"] = int(ret_c == adapter.RM_INT_A_BREAK)
    if not (ret_c == ret_r == adapter.RM_INT_A_BREAK):
        mism.append(("phaseA.break_ret", ret_c, ret_r))
    mism.extend(("phaseA.break." + n, c, r)
                for n, c, r in _flow_mismatches(fs, ref, ("int_scroll", "int_frame")))

    # Phase B (0x27fe): pick the demo leg.
    phaseB(rbuf)
    lib.rm_int_phaseB_leg(ctypes.byref(fs))
    mism.extend(("phaseB." + n, c, r) for n, c, r in _flow_mismatches(fs, ref, ("leg_select", "leg_index")))

    # Phase C (0x285e): the demo runs INT_C_FRAMES frames, ticking int_frame from 0 (the clr.l zeroes
    # the int_frame_hi/int_frame pair). This is a BOUNDARY-COUNT ONLY — a pure-Python mirror of
    # g_intermission's inline count run identically on both "sides", so it cannot fail on its own; its
    # value is that the 0x96 boundary lives in the pinned INT_C_FRAMES constant (== the C #define, see
    # test_python_constants_match_the_c). The demo pipeline itself is pinned separately by the leg drives.
    fs.int_frame_hi = fs.int_frame = 0
    _w16(ref, adapter.A_int_frame_hi, 0)
    _w16(ref, adapter.A_int_frame, 0)
    c_frames = 0
    while c_frames <= adapter.INT_C_FRAMES + 4:
        fs.int_frame = (fs.int_frame + 1) & 0xffff
        _w16(ref, adapter.A_int_frame, (_r16(ref, adapter.A_int_frame) + 1) & 0xffff)
        c_frames += 1
        if fs.int_frame >= adapter.INT_C_FRAMES:       # (int16)(f - 0x96) >= 0; f stays small here
            break
    if c_frames != adapter.INT_C_FRAMES or fs.int_frame != _r16(ref, adapter.A_int_frame):
        mism.append(("phaseC.frames", c_frames, adapter.INT_C_FRAMES))

    # Phase D (0x2894): the results carousel — leg_index starts 0, dwell src/flow.c's INT_D_DWELL frames per leg,
    # advancing until every leg has shown, then RESTART. Lockstep the counter slice over the whole
    # carousel (cheap; the oracle's init_leg_dash on ADVANCE is fully staged by flow_background).
    fs.int_frame_hi = fs.leg_index = 0
    _w16(ref, adapter.A_int_frame_hi, 0)
    _w16(ref, adapter.A_leg_index, 0)
    for _ in range(adapter.INT_C_FRAMES + adapter.RM_INT_D_RESTART):   # generous cap
        ret_r = stepD(rbuf)
        ret_c = lib.rm_int_stepD_counter(ctypes.byref(fs))
        stats["phaseD"] += 1
        stats["advances"] += int(ret_c == adapter.RM_INT_D_ADVANCE)
        if ret_c != ret_r:
            mism.append(("phaseD.ret", ret_c, ret_r))
        mism.extend(("phaseD." + n, c, r)
                    for n, c, r in _flow_mismatches(fs, ref, ("int_frame_hi", "leg_index")))
        if ret_c == adapter.RM_INT_D_RESTART:
            stats["restart"] = 1
            break
    return mism, stats


# ---- end-to-end game-flow drive (leg end -> update_highscore -> game_over++ -> intermission entry) ----
# The sequence main takes when the race loop breaks (decomp.c main @0x10100:286-317): a leg ends
# (abort_flag < 0), then update_highscore ranks the score, game_over_flag is bumped, and intermission
# runs. This drives an idle leg to time-out on both sides (the pinned tally arms abort_flag), then
# applies that break sequence and compares the surfaces it touches: the 0x280 hi-score table, the
# mutated score record, results_mode / hiscore_pos, and game_over_flag. (The intermission the flow
# enters next is pinned separately by compare_attract_cycle.)

def compare_game_flow(lib, leg, frames=140, time_left=6):
    """Drive leg `leg` to a time-out leg-end, run the main-loop break sequence on both sides, and
    return (mismatches, stats)."""
    image = leg_start_background(leg)
    _bind("g_init_scoretable")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(image))
    _w16(image, adapter.A_time_left, time_left)
    seeded = bytearray(image)                       # the table + score before the drive
    state = bytearray(image)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    game_update = _bind("g_game_update")
    cand = _Candidate(lib, state)

    ref_end = cand_end = -1
    stats = dict(frames=0, ref_end=-1, cand_end=-1)
    mism = []
    for f in range(frames):
        # Same free-running drive as compare_leg_drive, checked scalar-for-scalar every frame so a
        # divergence on the run-up to the leg-end surfaces here, not just in the break sequence.
        _drive_frame(cand, state, buf, game_update, 0)
        stats["frames"] += 1
        mism.extend(_drive_mismatches(f, cand, state))
        if _i16s(state, adapter.A_abort_flag) < 0 and ref_end < 0:
            ref_end = f
        if _abort_signed(cand.ev.abort_flag) < 0 and cand_end < 0:
            cand_end = f
        if ref_end >= 0 and cand_end >= 0:
            break
    stats["ref_end"], stats["cand_end"] = ref_end, cand_end

    if ref_end != cand_end:
        mism.append(("leg_end_frame", cand_end, ref_end))

    # --- the break sequence (main 286-317) ---
    # Reference: update_highscore ranks the evolved score into the seeded table, then game_over++.
    _bind("g_update_highscore")((ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state))
    _w16(state, adapter.A_game_over_flag, (_r16(state, adapter.A_game_over_flag) + 1) & 0xffff)

    # Candidate: rm_update_highscore over the seeded table + the candidate's own evolved score digits.
    fs = adapter.flow_state(seeded)
    fs.leg_index = cand.leg
    hs = adapter.highscore_buffer(seeded)
    score = (ctypes.c_uint8 * adapter.HS_SCORE_REC_BYTES)(
        *bytes(cand.hud_text)[adapter.HS_SCORE_REC_OFF:adapter.HS_SCORE_REC_OFF + adapter.HS_SCORE_REC_BYTES])
    lib.rm_update_highscore(ctypes.byref(fs), hs, score)
    lib.rm_flow_game_over_enter(ctypes.byref(fs))   # the real C owner of main's game_over_flag++
    # (The intermission the flow enters next — its prologue seeds + phases A-D — is pinned by
    # compare_attract_cycle; here the surfaces are the ones this break sequence itself writes.)

    d = _first_diff("table", bytes(hs),
                    bytes(state[adapter.A_highscore_table:adapter.A_highscore_table
                                + adapter.FLOW_HIGHSCORE_BYTES]))
    if d:
        mism.append(d)
    rec_lo = adapter.A_hud_text + adapter.HS_SCORE_REC_OFF
    d = _first_diff("score", bytes(score), bytes(state[rec_lo:rec_lo + adapter.HS_SCORE_REC_BYTES]))
    if d:
        mism.append(d)
    for name in ("results_mode", "hiscore_pos", "game_over_flag"):
        r = _r16(state, _FLOW_FIELD[name][0])
        if (getattr(fs, name) & 0xffff) != r:
            mism.append((name, getattr(fs, name) & 0xffff, r))
    return mism, stats

# ---- flow COMPOSITION driver (slice D): host lockstep vs the oracle slices ----
# The between-legs driver hoisted into src/flow.c (rm_flow_intermission_cycle / rm_flow_leg_select /
# rm_flow_game_over — the prologue + phase A/B/C/D loop, the leg-select loop, the game-over bracket) is
# run HERE on the host with RECORDING FlowOps callbacks. Its trajectory of platform-effect calls (draws,
# flips, palettes, phase events, the demo-leg pipeline stubs) plus a snapshot of every flow counter at
# each callback is compared, step for step, against a Python MIRROR of recreate's g_intermission /
# g_init_playfield structure whose counter values come from the VERIFIED g_int_* / g_init_playfield_* /
# g_check_abort oracle slices (run in-image). A divergence in the callback order, an argument, a return
# code, or any flow counter fails the comparison. This closes the "Known structural gap" (STATUS): the
# sequencing driver, previously only smoke-tested on-target, is now differentially locksteped host-side.


def _to_s16(v):
    """Sign-extend a 16-bit word (the flow mirror's subq/dbf arithmetic). One source of truth with the
    leg-drive's abort_flag sign-extend."""
    return _abort_signed(v & 0xffff)


def _shift_ref_input(ref, inp):
    """Advance the reference image's input HISTORY by one frame, exactly as flow_poll does on the
    candidate FlowState: baseline = last frame's live bits, live = this frame's. The oracle slices read
    A_input_state/prev. (Distinct from _stage_input_ref, which stages ONE fixed (state, prev) pair into a
    blank image for the single-shot abort/fire leaf comparisons — no history shift.)"""
    _w16(ref, adapter.A_input_prev, _r16(ref, adapter.A_input_state))
    _w16(ref, adapter.A_input_state, inp & 0xffff)


class _FlowScript:
    """Scripted, index-addressed input/quit/fkey providers, consumed in call order. The candidate run and
    the oracle mirror each hold one; identical control flow keeps their indices in lockstep."""
    def __init__(self, poll_of, quit_of, fkey_of):
        self._poll, self._quit, self._fkey = poll_of, quit_of, fkey_of
        self.pi = self.qi = self.fi = 0
        self.log = []

    def poll(self):
        v = self._poll(self.pi) & 0xffff
        self.pi += 1
        return v

    def quit(self):
        v = 1 if self._quit(self.qi) else 0
        self.qi += 1
        return v

    def fkey(self):
        v = int(self._fkey(self.fi))
        self.fi += 1
        return v


class _DriverRecorder:
    """Builds a FlowOps table of recording stubs over a candidate FlowState. Each callback appends
    (kind, args, counter-snapshot) to the log; the input callbacks pull from the script. The demo-leg
    pipeline (rebuild_dash / start_demo_leg / run_demo_frame) is a no-op stub — its render is a seam
    pinned by the leg drives; here we record only that (and in which order) the driver invoked it."""
    def __init__(self, fs, script):
        self.fs, self.script = fs, script
        self.log = []
        self.ops, self._keep = self._build()

    def _rec(self, kind, args=()):
        self.log.append((kind, args, adapter.flow_snapshot_fs(self.fs)))

    def _build(self):
        def poll(_ctx):
            v = self.script.poll()
            self._rec("poll", (v,))
            return v

        def quit_(_ctx):
            v = self.script.quit()
            self._rec("quit", (v,))
            return v

        def fkey(_ctx):
            v = self.script.fkey()
            self._rec("fkey", (v,))
            return v

        def draw_fade(_ctx, scroll):
            self._rec("draw_fade", (scroll,))

        def draw_int(_ctx, scroll):
            self._rec("draw_int", (scroll,))

        def draw_res(_ctx, leg):
            self._rec("draw_res", (leg,))

        def draw_res_screen(_ctx, mode, pos, leg):
            self._rec("draw_res_screen", (mode, pos, leg))

        def draw_panel5(_ctx):
            self._rec("draw_panel5")

        def set_pal(_ctx, which):
            self._rec("palette", (which,))

        def show(_ctx):
            self._rec("show")

        def rebuild(_ctx, leg):
            self._rec("rebuild_dash", (leg,))

        def leg_labels(_ctx, leg):
            self._rec("draw_leg_labels", (leg,))

        def start_demo(_ctx, leg):
            self._rec("start_demo_leg", (leg,))

        def run_demo(_ctx):
            self._rec("run_demo_frame")

        def flash(_ctx):
            self._rec("flash_frame")

        def name_flash(_ctx):
            self._rec("name_flash")

        def hold_frame(_ctx):
            self._rec("hold_frame")

        def event(_ctx, tag, leg, aux):
            self._rec("event", (tag, leg, aux))

        keep = [adapter._CB_POLL_INPUT(poll), adapter._CB_QUIT(quit_), adapter._CB_FKEY(fkey),
                adapter._CB_DRAW_SCROLL(draw_fade), adapter._CB_DRAW_SCROLL(draw_int),
                adapter._CB_DRAW_LEG(draw_res), adapter._CB_DRAW_RESULTS_SCREEN(draw_res_screen),
                adapter._CB_VOID(draw_panel5),
                adapter._CB_SET_PALETTE(set_pal), adapter._CB_VOID(show),
                adapter._CB_DRAW_LEG(rebuild), adapter._CB_DRAW_LEG(leg_labels),
                adapter._CB_DRAW_LEG(start_demo), adapter._CB_VOID(run_demo),
                adapter._CB_VOID(flash), adapter._CB_VOID(name_flash), adapter._CB_VOID(hold_frame),
                adapter._CB_EVENT(event)]
        return adapter.FlowOps(*keep), keep


class _MirrorRecorder:
    """The oracle side: records (kind, args, snapshot) from a reference image, stepping the verified
    g_* slices for every counter change. Structure-for-structure with rm_flow_* / recreate's
    g_intermission / g_init_playfield (see the mirrors below)."""
    def __init__(self, ref, script):
        self.ref = ref
        self.rbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(ref)
        self.script = script
        self.log = []
        self._stepA = _bind_ret("g_int_stepA", ctypes.c_int)
        self._stepD = _bind_ret("g_int_stepD_counter", ctypes.c_int)
        self._phaseB = _bind("g_int_phaseB_leg")
        self._abort = _bind_ret("g_check_abort", ctypes.c_uint32)
        self._nav = _bind("g_init_playfield_nav")
        self._fire = _bind_ret("g_init_playfield_fire", ctypes.c_int)

    def _rec(self, kind, args=()):
        self.log.append((kind, args, adapter.flow_snapshot_image(self.ref)))

    def _leg(self):
        return _r16(self.ref, adapter.A_leg_index)


def _mirror_int_cycle(m, tuning):
    """Oracle mirror of rm_flow_intermission_cycle (g_intermission's for-body @0x127a0)."""
    ref, rbuf, sc = m.ref, m.rbuf, m.script
    # prologue (0x27a0)
    _w16(ref, adapter.A_int_scroll, tuning.prologue_scroll & 0xffff)
    _w16(ref, adapter.A_int_frame, tuning.prologue_frame & 0xffff)
    _w16(ref, adapter.A_int_timer, tuning.prologue_timer & 0xffff)
    m._rec("event", (adapter.RM_FLOW_EVT_INT_PROLOGUE, m._leg(), _r16(ref, adapter.A_int_scroll)))
    m._rec("draw_fade", (_i16s(ref, adapter.A_int_scroll),))
    m._rec("palette", (adapter.RM_FLOW_PAL_INT_A,))
    m._rec("show")
    m._rec("draw_fade", (_i16s(ref, adapter.A_int_scroll),))
    m._rec("show")
    # Phase A (0x27cc)
    while True:
        q = sc.quit()
        m._rec("quit", (q,))
        if q:
            return adapter.RM_FLOW_QUIT
        inp = sc.poll()
        m._rec("poll", (inp,))
        _shift_ref_input(ref, inp)
        a = m._stepA(rbuf)
        if a == adapter.RM_INT_A_BREAK:
            break
        m._rec("draw_int", (_i16s(ref, adapter.A_int_scroll),))
        m._rec("show")
        if a == adapter.RM_INT_A_ABORT:
            m._rec("event", (adapter.RM_FLOW_EVT_INT_ABORT, m._leg(), 0))
            return adapter.RM_FLOW_ABORT
    m._rec("event", (adapter.RM_FLOW_EVT_INT_PHASEA_BREAK, m._leg(), _r16(ref, adapter.A_int_frame)))
    # Phase B (0x27fe)
    m._phaseB(rbuf)
    m._rec("event", (adapter.RM_FLOW_EVT_INT_PHASEB, m._leg(), 0))
    m._rec("start_demo_leg", (m._leg(),))
    # Phase C (0x285e)
    _w16(ref, adapter.A_int_frame_hi, 0)
    _w16(ref, adapter.A_int_frame, 0)
    while True:
        m._rec("run_demo_frame")
        f = (_r16(ref, adapter.A_int_frame) + 1) & 0xffff
        _w16(ref, adapter.A_int_frame, f)
        if _to_s16(f - tuning.phase_c_frames) >= 0:
            break
        q = sc.quit()
        m._rec("quit", (q,))
        if q:
            return adapter.RM_FLOW_QUIT
        inp = sc.poll()
        m._rec("poll", (inp,))
        _shift_ref_input(ref, inp)
        if m._abort(rbuf):
            m._rec("event", (adapter.RM_FLOW_EVT_INT_ABORT, m._leg(), 1))
            return adapter.RM_FLOW_ABORT
    m._rec("event", (adapter.RM_FLOW_EVT_INT_PHASEC_DONE, m._leg(), tuning.phase_c_frames & 0xffff))
    # Phase D (0x2894)
    _w16(ref, adapter.A_leg_index, 0)
    m._rec("rebuild_dash", (0,))
    m._rec("draw_res", (0,))
    m._rec("palette", (adapter.RM_FLOW_PAL_LEG_SELECT,))
    m._rec("show")
    while True:
        d = m._stepD(rbuf)
        if d == adapter.RM_INT_D_RESTART:
            m._rec("event", (adapter.RM_FLOW_EVT_INT_PHASED_RESTART, m._leg(), 0))
            break
        if d == adapter.RM_INT_D_ADVANCE:
            m._rec("rebuild_dash", (m._leg(),))
            m._rec("event", (adapter.RM_FLOW_EVT_INT_PHASED_ADVANCE, m._leg(), 0))
        m._rec("draw_res", (m._leg(),))
        m._rec("show")
        q = sc.quit()
        m._rec("quit", (q,))
        if q:
            return adapter.RM_FLOW_QUIT
        inp = sc.poll()
        m._rec("poll", (inp,))
        _shift_ref_input(ref, inp)
        if m._abort(rbuf):
            m._rec("event", (adapter.RM_FLOW_EVT_INT_ABORT, m._leg(), 2))
            return adapter.RM_FLOW_ABORT
    return adapter.RM_FLOW_CONTINUE


def _mirror_intermission(m, tuning):
    """Oracle mirror of rm_flow_intermission: run cycles until an abort/quit."""
    while True:
        r = _mirror_int_cycle(m, tuning)
        if r != adapter.RM_FLOW_CONTINUE:
            return r


def _mirror_game_over(m, tuning):
    """Oracle mirror of rm_flow_game_over: bump game_over_flag, run the intermission, reset it."""
    _w16(m.ref, adapter.A_game_over_flag, (_r16(m.ref, adapter.A_game_over_flag) + 1) & 0xffff)
    r = _mirror_intermission(m, tuning)
    _w16(m.ref, adapter.A_game_over_flag, 0)
    return r


def _mirror_start_leg(m, tuning, fire_aux):
    """Oracle mirror of flow_start_leg (ip_start_leg's "get ready": announce the fire, redraw the
    results + leg-name menu twice, add the dashboard labels, then flash the leg-start palette for
    tuning.flash_frames frames). The counters do not change here, so every snapshot matches."""
    leg = m._leg()
    m._rec("event", (adapter.RM_FLOW_EVT_SELECT_FIRE, leg, fire_aux))
    m._rec("rebuild_dash", (leg,))
    m._rec("draw_res", (leg,))
    m._rec("draw_panel5")
    m._rec("show")
    m._rec("draw_res", (leg,))
    m._rec("draw_panel5")
    m._rec("show")
    m._rec("draw_leg_labels", (leg,))
    for _ in range(tuning.flash_frames):
        m._rec("flash_frame")
    return adapter.RM_FLOW_START


def _mirror_leg_select(m, tuning):
    """Oracle mirror of rm_flow_leg_select (g_init_playfield's leg-select loop @0x2af6). The nav + reload
    and the fire edge come from g_init_playfield_nav / g_init_playfield_fire; the idle-countdown loop and
    the dash-rebuild gate are the driver's directed structure (the countdown constant is the tuning)."""
    ref, rbuf, sc = m.ref, m.rbuf, m.script
    m._rec("event", (adapter.RM_FLOW_EVT_SELECT_ENTER, m._leg(), 0))
    while True:
        drawn_leg = 0xffff
        _w16(ref, adapter.A_idle_countdown, tuning.idle_init & 0xffff)
        # leg-select palette at the OUTER-loop entry (0x2af6), BEFORE the F-key branch — mirrors flow.c's
        # move of set_palette out of the inner redraw, so an F-key pick's get-ready is not under a stale
        # palette. The original loads it once here and not in the inner default redraw (0x2b9e).
        m._rec("palette", (adapter.RM_FLOW_PAL_LEG_SELECT,))
        while True:
            fk = sc.fkey()
            m._rec("fkey", (fk,))
            if fk >= 0:
                _w16(ref, adapter.A_leg_index, fk & 0xffff)
                return _mirror_start_leg(m, tuning, 1)
            if m._leg() != drawn_leg:
                drawn_leg = m._leg()
                m._rec("rebuild_dash", (drawn_leg,))
            m._rec("draw_res", (m._leg(),))
            m._rec("draw_panel5")
            m._rec("show")
            inp = sc.poll()
            m._rec("poll", (inp,))
            _shift_ref_input(ref, inp)
            m._nav(rbuf)
            if m._fire(rbuf):
                return _mirror_start_leg(m, tuning, 0)
            q = sc.quit()
            m._rec("quit", (q,))
            if q:
                return adapter.RM_FLOW_QUIT
            nxt = _to_s16(_r16(ref, adapter.A_idle_countdown) - 1)
            if nxt < 0:
                break
            _w16(ref, adapter.A_idle_countdown, nxt & 0xffff)
        m._rec("event", (adapter.RM_FLOW_EVT_SELECT_IDLE, m._leg(), 0))
        if _mirror_game_over(m, tuning) == adapter.RM_FLOW_QUIT:
            return adapter.RM_FLOW_QUIT


def _diff_trajectory(actual, expected, cand_result, ref_result):
    """Compare the candidate driver's recorded trajectory against the oracle mirror's, step for step.
    Returns (mismatches, stats). A mismatch is (index, actual_record, expected_record) or a result diff."""
    mism = []
    if cand_result != ref_result:
        mism.append(("result", cand_result, ref_result))
    for i in range(max(len(actual), len(expected))):
        a = actual[i] if i < len(actual) else None
        e = expected[i] if i < len(expected) else None
        if a != e:
            mism.append((i, a, e))
            if len(mism) > 10:
                break
    events = [rec[1][0] for rec in actual if rec[0] == "event"]
    stats = dict(steps=len(actual), result=cand_result,
                 draws=sum(1 for rec in actual if rec[0] in ("draw_fade", "draw_int", "draw_res")),
                 shows=sum(1 for rec in actual if rec[0] == "show"),
                 run_demo=sum(1 for rec in actual if rec[0] == "run_demo_frame"),
                 panel5=sum(1 for rec in actual if rec[0] == "draw_panel5"),
                 leg_labels=sum(1 for rec in actual if rec[0] == "draw_leg_labels"),
                 flash=sum(1 for rec in actual if rec[0] == "flash_frame"),
                 palettes=[rec[1][0] for rec in actual if rec[0] == "palette"],
                 events=events)
    return mism, stats


def _run_flow_driver(image, driver_fn, mirror_fn, tuning, poll_of, quit_of, fkey_of):
    """Run the hoisted C `driver_fn` with recording callbacks on a candidate FlowState seeded from
    `image`, run `mirror_fn` (the oracle) on a copy, and diff the two trajectories."""
    poll_of = poll_of or (lambda i: 0)
    quit_of = quit_of or (lambda i: 0)
    fkey_of = fkey_of or (lambda i: -1)

    fs = adapter.flow_state(image)
    rec = _DriverRecorder(fs, _FlowScript(poll_of, quit_of, fkey_of))
    cand_result = driver_fn(ctypes.byref(fs), ctypes.byref(rec.ops), None, ctypes.byref(tuning))

    ref = bytearray(image)
    mir = _MirrorRecorder(ref, _FlowScript(poll_of, quit_of, fkey_of))
    ref_result = mirror_fn(mir, tuning)
    return _diff_trajectory(rec.log, mir.log, cand_result, ref_result)


def compare_flow_intermission_cycle(lib, image, tuning, poll_of=None, quit_of=None, fkey_of=None):
    """Lockstep one attract cycle (rm_flow_intermission_cycle) vs the oracle mirror. (mismatches, stats)."""
    return _run_flow_driver(image, lib.rm_flow_intermission_cycle, _mirror_int_cycle,
                            tuning, poll_of, quit_of, fkey_of)


def compare_flow_intermission(lib, image, tuning, poll_of=None, quit_of=None, fkey_of=None):
    """Lockstep the whole attract loop (rm_flow_intermission: cycles until abort/quit) vs the oracle."""
    return _run_flow_driver(image, lib.rm_flow_intermission, _mirror_intermission,
                            tuning, poll_of, quit_of, fkey_of)


def compare_flow_leg_select(lib, image, tuning, poll_of=None, quit_of=None, fkey_of=None):
    """Lockstep the leg-select loop (rm_flow_leg_select, incl. its idle -> game-over-bracketed attract
    cycle) vs the oracle mirror of g_init_playfield. (mismatches, stats)."""
    return _run_flow_driver(image, lib.rm_flow_leg_select, _mirror_leg_select,
                            tuning, poll_of, quit_of, fkey_of)
