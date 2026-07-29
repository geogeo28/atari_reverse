#!/usr/bin/env python3
"""Render the workspace README's images straight from the verified C reconstruction.

Every picture here is *drawn by the reconstruction*, not screenshotted from the original
program. In-race frames reuse the staging the remaster equivalence harness trusts
(`recreate/tools/bench_frame.py`'s real mid-race image + `remaster/test/capture_ref.py`'s
render pipeline); the static screens, track maps and buggy come from
`recreate/render/render_screen.py`; the sprite pages come from the same RLE decode
`g_unpack_graphics` performs.

Output goes to the tracked `<workspace>/assets/` — a small curated set for the README.
`gen_assets.py`'s much larger `docs/assets/` (the function-graph explorer's media) stays
gitignored and reproducible. Re-run:

    python3 gen_readme_assets.py
"""
import ctypes
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RECREATE = HERE / "recreate"
for sub in ("test", "render", "tools"):               # the oracle now lives in tools/recreate_kit,
    sys.path.insert(0, str(RECREATE / sub))           # put on sys.path by test/harness.py's bind
sys.path.insert(0, str(HERE / "remaster" / "test"))   # capture_ref (drives recreate's .so only)

import render_screen as rs      # noqa: E402  loads libbuggyboy.so; buffer layout + PNG writer
import bench_frame              # noqa: E402  authentic mid-race staging (oracle init_leg + warmups)
import capture_ref              # noqa: E402  the in-race render pipeline, in draw order
import extract_graphics as xg   # noqa: E402  GRAPHICS.GRA RLE decode
import gen_assets               # noqa: E402  shared staging/palette helpers + atlas constants

OUT = WORKSPACE / "assets"

IN_ACCEL = 0x01                 # input_state's throttle bit (see recreate/include/addrs.h)

# One in-race frame per leg shown, with how many frames to drive before capturing — chosen so the
# car is up to speed and the course has streamed to a stretch with roadside objects in view.
RACE_SHOTS = ((0, 220), (1, 300), (4, 380))
ATLAS_PAGES = (3, 4)            # GRAPHICS.GRA pages worth showing: gates/score markers, scenery
LEGMAPS = (0, 3)


def _write_png(name, rows, pal):
    path = OUT / name
    rs.write_png(str(path), rs.W, rs.H, rows, pal)
    print("  wrote", path.relative_to(WORKSPACE))


def _write_screen(name, image, pal_addr=rs.PALETTE_ADDR, black_bg=False):
    """Decode the ST framebuffer inside `image` and write it as a PNG with the game's own palette."""
    pal = rs.read_palette(image, pal_addr)
    if black_bg:
        pal[0] = (0, 0, 0)      # scenery "empty" fill -> black, so the subject reads on its own
    _write_png(name, rs._decode_interleaved(image, rs.SCREEN_BASE), pal)


def _build_dash_map(state):
    """Build the HUD's course-map graphic for the staged leg.

    `draw_hud` blits the map every frame via `draw_dashboard`, but the graphic itself is built once
    per leg by `init_leg_dash`, which copies the leg's outline out of COURSES.DAT through the
    `mem_base` pointer. bench_frame's staging targets the render benchmark and sets neither, so
    without this the map panel renders empty.
    """
    state[rs.A_MEM_BASE:rs.A_MEM_BASE + 4] = rs.MEM_BASE.to_bytes(4, "big")
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    capture_ref._bind("g_init_leg_dash")(buf)


def _drive(state, frames):
    """Drive the staged leg for `frames` frames with the throttle held, through the verified
    `g_game_update` — the car accelerates, the course streams, the dashboard marker walks."""
    step = capture_ref._bind("g_game_update")
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    for _ in range(frames):
        bench_frame._w16(state, bench_frame.A_INPUT_STATE, IN_ACCEL)
        step(buf)


def render_race_frames():
    """A rendered in-race frame per leg: real course data staged, oracle `init_leg`, then a real
    drive, then the verified road/scroll/objects/HUD pipeline draws the frame.

    We drive the leg ourselves rather than reuse bench_frame's warmup: that warmup forces a course
    advance by zeroing `input_state` and pinning `engine_rpm` every frame, which suits the render
    benchmark but never lets the car off the start line (the speedometer stays at 0).
    """
    for leg, frames in RACE_SHOTS:
        state = bench_frame.mid_race_state(leg, 0)      # post-init_leg image, no forced warmup
        _build_dash_map(state)
        _drive(state, frames)
        capture_ref._render_into(state)
        _write_screen("race-leg%d.png" % leg, state, gen_assets.A_RACE_PAL)


def render_screens():
    """The non-race screens and the per-leg track maps, each drawn by its verified function."""
    _write_screen("screen-credits.png", rs.render_intermission())
    _write_screen("screen-leg-select.png", rs.render_leg_results(0))
    _write_screen("screen-highscore.png", rs.render_highscore_screen(0))
    for leg in LEGMAPS:
        _write_screen("course-legmap-%d.png" % leg, rs.render_legmap(leg), rs.GAMEPLAY_PALETTE,
                      black_bg=True)


def render_atlas_pages():
    """Pages of the GRAPHICS.GRA sprite atlas, via the RLE decode `g_unpack_graphics` runs."""
    packed = (HERE / "bin" / "GRAPHICS.GRA").read_bytes()[gen_assets.GFX_HEADER:]
    decoded = xg.rle_decode(packed)
    pal = gen_assets._leg_pal(gen_assets._staged_leg(0)[0])
    for page in ATLAS_PAGES:
        rows = xg.render_indices(decoded, page * gen_assets.SHEET_BYTES)
        _write_png("sprites-page%d.png" % page, rows, pal)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    render_race_frames()
    render_screens()
    render_atlas_pages()


if __name__ == "__main__":
    main()
