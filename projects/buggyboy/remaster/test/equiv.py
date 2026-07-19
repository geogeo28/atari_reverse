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
