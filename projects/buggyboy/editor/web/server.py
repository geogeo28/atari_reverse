"""server.py — Flask backend for the BuggyBoy course editor (three.js front-end).

Serves a 3D course model built from the decoded data (course3d) and applies edits to an
in-memory CourseFile (patch-in-place; save writes a .bak first). Single-user local tool, so
one global CourseFile is fine.

    mlenv python web/server.py            # then open http://127.0.0.1:5000

Reuses the verified reconstruction only for decoding/geometry — no browser rendering of the
game framebuffer here; the browser builds the 3D road from the JSON model.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))            # editor/ modules

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402

import numpy as np                                # noqa: E402
import course3d                                   # noqa: E402
import course_format as cf                        # noqa: E402
from course_file import CourseFile                # noqa: E402

DAT = HERE.parents[1] / "bin" / "COURSES.DAT"
STATIC = HERE / "static"
GAME_W, GAME_H = 320, 200

app = Flask(__name__, static_folder=None)
course = CourseFile.load(DAT)                     # global edit model (in-memory until /api/save)
_session = None                                   # lazily-created live GameSession (needs the .so)
_session_err = None


def _game_session():
    """The live authentic-render session (verified init_leg + game_update + draw_frame)."""
    global _session, _session_err
    if _session is None and _session_err is None:
        try:
            import roadview
            _session = roadview.GameSession(0, courses=bytes(course.data))
        except Exception as e:  # noqa: BLE001 - .so not built / deps missing
            _session_err = f"{type(e).__name__}: {e}"
    return _session


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/static/<path:name>")
def static_file(name):
    return send_from_directory(STATIC, name)


@app.route("/api/course/<int:leg>")
def api_course(leg):
    leg = max(0, min(cf.LEG_COUNT - 1, leg))
    return jsonify(course3d.build_course(bytes(course.data), leg))


@app.route("/api/edit", methods=["POST"])
def api_edit():
    """Edit one record field: {leg, k, field: slope|rows|marker, value}."""
    d = request.get_json(force=True)
    leg, k, field, value = int(d["leg"]), int(d["k"]), d["field"], int(d["value"])
    recs = course.records(leg, k + 1)
    if k >= len(recs):
        return jsonify(error="record out of range"), 400
    r = recs[k]
    if field == "slope":
        course.set_control(leg, k, r.row_count, max(-3, min(4, value)))
    elif field == "rows":
        course.set_control(leg, k, max(1, min(31, value)), r.decay_seed)
    elif field == "marker":
        course.set_marker(leg, k, value & 0xFFFF)
    else:
        return jsonify(error="unknown field"), 400
    return jsonify(ok=True)


@app.route("/api/save", methods=["POST"])
def api_save():
    dst = course.save()
    return jsonify(ok=True, path=str(dst))


# ---- authentic game stream: the verified render, real road + object sprites + buggy + HUD ----
@app.route("/api/game/reset", methods=["POST"])
def api_game_reset():
    """(Re)start the live game for a leg, staging the current (edited) COURSES.DAT bytes."""
    leg = max(0, min(cf.LEG_COUNT - 1, int(request.get_json(force=True).get("leg", 0))))
    s = _game_session()
    if s is None:
        return jsonify(error=_session_err), 503
    s.reset(leg, courses=bytes(course.data))
    return jsonify(ok=True, w=GAME_W, h=GAME_H)


@app.route("/api/game/step", methods=["POST"])
def api_game_step():
    """Advance one game frame with the given input_state bits; return the framebuffer as RGBA."""
    bits = int(request.get_json(force=True).get("input", 0))
    s = _game_session()
    if s is None:
        return jsonify(error=_session_err), 503
    import roadview
    img = s.step(bits)
    rows = roadview.rs._decode_interleaved(img, roadview.rs.SCREEN_BASE)
    idx = np.frombuffer(b"".join(bytes(r) for r in rows), dtype=np.uint8).reshape(GAME_H, GAME_W) & 0xF
    lut = np.array(s.palette(), dtype=np.uint8)          # 16 x 3
    rgba = np.dstack([lut[idx], np.full((GAME_H, GAME_W, 1), 255, np.uint8)])
    return Response(rgba.tobytes(), mimetype="application/octet-stream")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
