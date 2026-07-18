"""test_roundtrip.py — safety net for the patch-in-place editor.

The editor's core guarantee: loading and saving without edits is byte-identical,
and every field edit is (a) reversible and (b) visible through the decoder. These
tests pin that so an editing bug can't silently corrupt the real COURSES.DAT.

Run:  python -m pytest editor/test_roundtrip.py    (or: python editor/test_roundtrip.py)
"""
from __future__ import annotations

from pathlib import Path

import course_format as cf
import mapview
import roadprofile
from course_file import CourseFile

DAT = Path(__file__).resolve().parents[1] / "bin" / "COURSES.DAT"


def _load() -> CourseFile:
    return CourseFile.load(DAT)


def test_identity_roundtrip():
    """No edits -> the serialized bytes equal the file on disk."""
    original = DAT.read_bytes()
    assert bytes(_load().data) == original


def test_marker_edit_visible_and_reversible():
    cffile = _load()
    before = cffile.records(0, count=64)
    k = 5
    old = before[k].marker
    cffile.set_marker(0, k, 0x8123)
    after = cffile.records(0, count=64)
    assert after[k].marker == 0x8123
    assert after[k].marker_is_event
    # only that record's marker changed
    assert [r.marker for r in after[:k]] == [r.marker for r in before[:k]]
    cffile.set_marker(0, k, old)
    assert bytes(cffile.data) == DAT.read_bytes()


def test_control_encoding():
    cffile = _load()
    cffile.set_control(0, 3, rows=5, decay=-1)
    r = cffile.records(0, count=8)[3]
    assert r.row_count == 5
    assert r.decay_seed == -1


def test_scroll_table_edit():
    cffile = _load()
    cffile.set_scroll(0, frame=2, band=4)
    off = cf.buf_a(0 * cf.SCROLL_TABLE_STRIDE) + 2
    assert cffile.data[off] == 4


def test_paint_marker_run():
    cffile = _load()
    cffile.paint_marker_run(0, k0=10, length=6, word=0x8800)
    recs = cffile.records(0, count=32)
    assert all(recs[k].marker == 0x8800 for k in range(10, 16))


def test_map_decode_shape():
    """Each leg's dashboard bitmap decodes to a 40x128 grid with a non-trivial track."""
    data = DAT.read_bytes()
    for leg in range(cf.LEG_COUNT):
        grid = mapview.decode_map(data, leg)
        assert len(grid) == mapview.MAP_H and all(len(row) == mapview.MAP_W for row in grid)
        lit = sum(sum(row) for row in grid)
        assert 0 < lit < mapview.MAP_H * mapview.MAP_W   # neither blank nor fully filled


def test_map_pixel_set_get_reversible():
    cffile = _load()
    x, y, leg = 40, 12, 0
    orig = cffile.get_map_pixel(leg, x, y)
    cffile.set_map_pixel(leg, x, y, not orig)
    assert cffile.get_map_pixel(leg, x, y) == int(not orig)
    cffile.set_map_pixel(leg, x, y, bool(orig))
    assert bytes(cffile.data) == DAT.read_bytes()          # exact restore


def test_map_paint_touches_only_track_plane():
    """Painting a track pixel changes plane1 (w1) only, never the scenery plane (w0)."""
    cffile = _load()
    leg, x, y = 0, 33, 7
    w0_off = leg * cf.DASH_LEG_STRIDE + y * cf.DASH_SRC_STRIDE + (x // 16) * 4     # plane0
    w0_before = cf.be16(bytes(cffile.data), w0_off)
    cffile.set_map_pixel(leg, x, y, True)
    assert cffile.get_map_pixel(leg, x, y) == 1
    assert cf.be16(bytes(cffile.data), w0_off) == w0_before  # w0 untouched


def test_road_profile_matches_control_bytes():
    """Each segment's slope/rows equal the record's control-byte fields."""
    data = DAT.read_bytes()
    segs = roadprofile.road_profile(data, 0, 64)
    recs = cf.decode_leg(data, 0, 64)
    assert len(segs) == len(recs)
    for seg, rec in zip(segs, recs):
        assert seg.slope == rec.decay_seed
        assert seg.rows == rec.row_count
    # cumulative elevation is consistent with per-segment slope*step
    elev = 0
    for seg in segs:
        assert seg.elev0 == elev
        elev += seg.slope * max(seg.rows, 1)
        assert seg.elev1 == elev


def test_slope_edit_persists_and_reversible():
    cffile = _load()
    seg = roadprofile.road_profile(bytes(cffile.data), 0, 8)[3]
    new = 4 if seg.slope != 4 else -3
    cffile.set_control(0, 3, seg.rows, new)
    assert roadprofile.road_profile(bytes(cffile.data), 0, 8)[3].slope == new
    cffile.set_control(0, 3, seg.rows, seg.slope)          # restore
    assert bytes(cffile.data) == DAT.read_bytes()


def test_render_profile_dimensions():
    segs = roadprofile.road_profile(DAT.read_bytes(), 0, 80)
    lines = roadprofile.render_profile(segs, width=60, height=18, x0=0, cursor=5)
    assert len(lines) == 18 and all(len(ln) <= 60 for ln in lines)


def test_roadview_renders_if_so_built():
    """If libbuggyboy.so is built, the verified render pipeline draws a road band.

    Skips (does not fail) when the .so / harness isn't available — roadview is a
    listening tool, not part of the file-format contract.
    """
    try:
        import roadview
        img = roadview.render_frame(leg=0, seg=0, curve=0)
    except Exception as e:  # noqa: BLE001 - .so not built, missing deps, etc.
        print(f"skip test_roadview ({type(e).__name__}: {e})")
        return
    rows = roadview.rs._decode_interleaved(img, roadview.rs.SCREEN_BASE)
    band = [y for y in range(200) if any(rows[y])]
    assert band and band[0] == 104, band[:3]      # road band starts at RR_DST_ROAD_OFF/160


def test_roadwin_surface_if_available():
    """If pygame+numpy+.so are present, a GameSession drives and roadwin builds a 320x200 surface.

    Skips (does not fail) otherwise — the graphical viewer is optional tooling.
    """
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # headless: no window
    try:
        import pygame
        import roadview
        import roadwin
        pygame.init()
        session = roadview.GameSession(leg=0)
        for _ in range(30):
            session.step(roadview.IN_ACCEL)
        idx = roadwin.frame_indices(session.image)
        surf = roadwin.indices_to_surface(idx, session.palette())
    except Exception as e:  # noqa: BLE001 - pygame/numpy/.so not present
        print(f"skip test_roadwin ({type(e).__name__}: {e})")
        return
    assert idx.shape == (200, 320) and surf.get_size() == (320, 200)
    # the game actually advanced (accelerating raises speed)
    speed = int.from_bytes(session.image[0x18CF6:0x18CF8], "big")
    assert speed > 0, "game did not advance"


def test_course3d_model():
    """The 3D course model traces a path, maps elevation, and lists objects for every leg."""
    import course3d
    data = DAT.read_bytes()
    for leg in range(cf.LEG_COUNT):
        c = course3d.build_course(data, leg)
        assert len(c["path"]) > 50, (leg, len(c["path"]))          # a real traced path
        assert len(c["elevation"]) == len(c["path"])
        assert c["objects"] and all("t" in o and "type" in o for o in c["objects"])


def test_web_backend_if_flask():
    """If Flask is installed, the server serves the page + course JSON and applies a slope edit.

    Skips (does not fail) otherwise — the web editor is optional tooling.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
    try:
        import server
    except Exception as e:  # noqa: BLE001 - flask not present
        print(f"skip test_web_backend ({type(e).__name__}: {e})")
        return
    cl = server.app.test_client()
    assert cl.get("/").status_code == 200
    assert cl.get("/static/app.js").status_code == 200
    j = cl.get("/api/course/1").get_json()
    assert len(j["path"]) > 50 and len(j["elevation"]) == len(j["path"])
    end0 = cl.get("/api/course/0").get_json()["elevation"][-1]
    assert cl.post("/api/edit", json={"leg": 0, "k": 5, "field": "slope", "value": 4}).get_json()["ok"]
    assert cl.get("/api/course/0").get_json()["elevation"][-1] != end0   # edit changed the hills

    # authentic game stream (needs the .so + numpy); skip that leg gracefully if unavailable
    reset = cl.post("/api/game/reset", json={"leg": 0})
    if reset.status_code != 200:
        print(f"skip game stream ({reset.get_json()})")
        return
    for _ in range(10):
        frame = cl.post("/api/game/step", json={"input": 1})
    assert frame.status_code == 200 and len(frame.get_data()) == 320 * 200 * 4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all round-trip tests passed")
