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

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import course3d                                  # noqa: E402
import course_format as cf                        # noqa: E402
from course_file import CourseFile                # noqa: E402

DAT = HERE.parents[1] / "bin" / "COURSES.DAT"
STATIC = HERE / "static"

app = Flask(__name__, static_folder=None)
course = CourseFile.load(DAT)                     # global edit model (in-memory until /api/save)


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
