"""roadview.py — draw the third-person road for a leg, through the VERIFIED renderer.

This renders the road the way the game does: it stages the reconstruction's image (via
recreate/render/render_screen.py), feeds the leg's real elevation slopes into road_seg_data,
sets the curve/view/horizon, then calls the verified g_build_road_geometry + g_render_road and
de-interleaves the resulting ST framebuffer to a PNG (or ASCII).

What's authentic vs. supplied:
  - the RASTERIZER is the verified render_road (byte-for-byte vs the 68000), so the perspective,
    edges and shoulders are the game's own;
  - the HILLS come from the leg's stream (segment slope = (control & 7) - 3, decoded by roadprofile);
  - the CURVE is a parameter (road_curve is runtime steering state, not in COURSES.DAT — see the
    editor README), default straight;
  - the road-WIDTH taper is a supplied default (road_width_src is runtime state, zero in a cold
    image), so the road has a sensible near->far taper to render into.

Needs the built recreate/build/libbuggyboy.so (run `make` in recreate/ once).

    python roadview.py --leg 0 --seg 40 --curve 0x300         # -> out/render/road_leg0.png
    python roadview.py --leg 2 --ascii                        # terminal preview
"""
from __future__ import annotations

import sys
from pathlib import Path

import course_format as cf
import roadprofile

HERE = Path(__file__).resolve().parent
RECREATE = HERE.parent / "recreate"
for p in (RECREATE / "render", RECREATE / "oracle", RECREATE / "test", HERE.parents[2] / "tools"):
    sys.path.insert(0, str(p))

import ctypes                       # noqa: E402
import render_screen as rs          # noqa: E402  (staging + de-interleave + PNG)
import harness                      # noqa: E402  (the candidate .so)

# ---- road-geometry input addresses (mirror addrs.h) ----
A_ROAD_SEG_DATA = 0x18D1C   # 13 segment slopes (words); road_seg_data[12] is the far/new segment
A_ROAD_CURVE    = 0x18C6A   # signed curvature (runtime steering; a parameter here)
A_VIEW_FLAGS    = 0x18C56   # 0/2/4/6 view selector
A_HORIZON       = 0x1905E   # horizon input (build_road_geometry clamps it to a scanline)
A_ROAD_EDGE_SEL = 0x18C5A   # signed word into render_road's edge table (init_leg uses 0xc0)
A_ROAD_WIDTH_SRC = 0x18D5A  # 14 half-width source values (stride 0x20)

SEG_SLOTS = 13              # road_seg_data words build_road_geometry reads
# Supplied near->far half-width taper (road_width_src is runtime state; this gives a road to draw).
WIDTH_TAPER = [8, 16, 24, 32, 44, 56, 70, 84, 100, 116, 132, 148, 160, 160]
DEFAULTS = dict(curve=0, view=2, horizon=0x600, edge_sel=0xC0)

_GLYPHS = " .:-=+*#%@123456"     # palette-index -> ASCII ramp for the terminal preview


def _bind(name):
    fn = getattr(harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    return fn


def render_frame(leg=0, seg=0, curve=None, view=None, horizon=None, edge_sel=None):
    """Stage + render one road frame from the on-disk COURSES.DAT."""
    courses = (harness.PRG.parent / "COURSES.DAT").read_bytes()
    return render_frame_from_bytes(courses, leg, seg, curve, view, horizon, edge_sel)


def render_frame_from_bytes(courses, leg=0, seg=0, curve=None, view=None,
                            horizon=None, edge_sel=None):
    """Stage + render one road frame from an in-memory COURSES.DAT (reflects edits).

    Returns the flat image (the draw buffer sits at rs.SCREEN_BASE).
    """
    d = DEFAULTS
    curve = d["curve"] if curve is None else curve
    view = d["view"] if view is None else view
    horizon = d["horizon"] if horizon is None else horizon
    edge_sel = d["edge_sel"] if edge_sel is None else edge_sel

    segs = roadprofile.road_profile(courses, leg, seg + SEG_SLOTS + 1)
    slopes = [segs[min(seg + i, len(segs) - 1)].slope for i in range(SEG_SLOTS)]

    pokes = {}
    for i, s in enumerate(slopes):
        pokes[A_ROAD_SEG_DATA + i * 2] = (s & 0xFFFF).to_bytes(2, "big")
    for i, w in enumerate(WIDTH_TAPER):
        pokes[A_ROAD_WIDTH_SRC + i * 0x20] = (w & 0xFFFF).to_bytes(2, "big")
    pokes[A_ROAD_CURVE] = (curve & 0xFFFF).to_bytes(2, "big")
    pokes[A_VIEW_FLAGS] = (view & 0xFFFF).to_bytes(2, "big")
    pokes[A_HORIZON] = (horizon & 0xFFFF).to_bytes(2, "big")
    pokes[A_ROAD_EDGE_SEL] = (edge_sel & 0xFFFF).to_bytes(2, "big")

    image, buf = rs._prepared_image(pokes)
    _bind("g_build_road_geometry")(buf)
    _bind("g_render_road")(buf)
    return image


def default_out():
    d = RECREATE.parent / "out" / "render"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---- live game session: drive the VERIFIED init_leg + game_update + draw_frame ----
A_LEG_INDEX = 0x18C38
A_INPUT_STATE = 0x18C44     # joystick/key bits: up/accel 1, down/brake 2, left 4, right 8, fire 0x80
GAME_WARMUP = 2             # frames to advance on reset so geometry/objects populate

# input_state bit masks (mirror input.c)
IN_ACCEL, IN_BRAKE, IN_LEFT, IN_RIGHT, IN_FIRE = 0x01, 0x02, 0x04, 0x08, 0x80


class GameSession:
    """A running game: stage once, then step (game_update + draw_frame) per frame.

    Everything is the game's own verified code — the road, roadside object sprites, the buggy
    and the HUD are all rendered authentically by draw_frame. Input is injected via input_state
    (read_input keeps it when any bit is set). The framebuffer is at rs.SCREEN_BASE.
    """
    def __init__(self, leg=0, courses=None):
        self._init = _bind("g_init_leg")
        self._update = _bind("g_game_update")
        self._frame = _bind("g_draw_frame")
        self.reset(leg, courses)

    def reset(self, leg=0, courses=None):
        """Stage a fresh leg. If `courses` is given (edited COURSES.DAT bytes) it is staged at
        MEM_BASE so edits are driven; otherwise render_screen stages the on-disk file."""
        self.leg = leg
        state = {A_LEG_INDEX: leg.to_bytes(2, "big")}
        if courses is not None:
            state[rs.MEM_BASE] = bytes(courses)
        self.image, self.buf = rs._prepared_image(state)
        self._init(self.buf)
        for _ in range(GAME_WARMUP):
            self.step(IN_ACCEL)

    def step(self, input_bits):
        """Advance one frame with the given input_state bits; returns the flat image."""
        self.image[A_INPUT_STATE:A_INPUT_STATE + 2] = (input_bits & 0xFFFF).to_bytes(2, "big")
        self._update(self.buf)
        self._frame(self.buf)
        return self.image

    def palette(self):
        pal = rs.read_palette(self.image, rs.GAMEPLAY_PALETTE)
        pal[0] = (0, 0, 0)
        return pal


def to_ascii(image, step=3, y0=104, y1=200):
    rows = rs._decode_interleaved(image, rs.SCREEN_BASE)
    return [
        "".join(_GLYPHS[rows[y][x] & 0xF] for x in range(0, rs.W, step))
        for y in range(y0, y1)
    ]


def to_ascii_fit(image, cols, lines, y0=0, y1=200):
    """De-interleave and downsample the framebuffer to fit a (cols x lines) terminal pane.

    y0=0 shows the whole 320x200 screen (black sky above, road in the lower half) so it reads
    like the game; pass y0=104 for just the road band.
    """
    src = rs._decode_interleaved(image, rs.SCREEN_BASE)
    xs = max(1, -(-rs.W // max(1, cols)))          # ceil(W/cols)
    ys = max(1, -(-(y1 - y0) // max(1, lines)))    # ceil(band/lines)
    out = []
    for y in range(y0, y1, ys):
        out.append("".join(_GLYPHS[src[y][x] & 0xF] for x in range(0, rs.W, xs)))
    return out


def write_png(image, path):
    rows = rs._decode_interleaved(image, rs.SCREEN_BASE)
    pal = rs.read_palette(image, rs.GAMEPLAY_PALETTE)   # per-leg scenery palette
    pal[0] = (0, 0, 0)
    rs.write_png(str(path), rs.W, rs.H, rows, pal)


def _arg(argv, name, default, conv=int):
    if name in argv:
        v = argv[argv.index(name) + 1]
        return conv(v, 0) if conv is int else conv(v)
    return default


def main(argv):
    leg = _arg(argv, "--leg", 0)
    seg = _arg(argv, "--seg", 0)
    curve = _arg(argv, "--curve", DEFAULTS["curve"])
    view = _arg(argv, "--view", DEFAULTS["view"])
    horizon = _arg(argv, "--horizon", DEFAULTS["horizon"])
    image = render_frame(leg, seg, curve=curve, view=view, horizon=horizon)
    if "--ascii" in argv:
        for line in to_ascii(image):
            print(line)
        return 0
    outdir = Path(_arg(argv, "--out", default_out(), conv=Path))
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"road_leg{leg}_seg{seg}.png"
    write_png(image, path)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
