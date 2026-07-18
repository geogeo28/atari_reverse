"""course3d.py — build a 3D course model for the web viewer from the decoded course data.

Combines two decoded sources into one drivable 3D road:
  - the horizontal PATH: the leg's dashboard track-map bitmap (mapview) traced into an ordered
    centerline (largest connected component, longest path via double-BFS diameter);
  - the ELEVATION: the record stream's per-segment slope (roadprofile), accumulated into hills;
  - roadside OBJECTS: the record stream's object-type slots, placed along the path.

The path is authentic to the leg's map; elevation/objects are authentic to the stream. The two
are aligned by normalized position along the leg (an approximation — the map and the record
stream aren't the same length), and the road width is a fixed ribbon. This is a visualization
model, not the game's verified rasterizer.
"""
from __future__ import annotations

from collections import deque

import course_format as cf
import mapview
import roadprofile

ROAD_HALF_WIDTH = 2.2        # ribbon half-width in path-pixel units
ELEV_SCALE = 0.05           # elevation units -> world height
PROFILE_SEGS = 300          # stream segments sampled for elevation/objects along the path
MIN_COMPONENT = 20          # ignore track-map specks smaller than this (start/finish ticks)


def _neighbours(pts):
    def n(p):
        x, y = p
        return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0) and (x + dx, y + dy) in pts]
    return n


def _largest_component(pts, neigh):
    seen, best = set(), []
    for s in pts:
        if s in seen:
            continue
        q, comp = deque([s]), [s]
        seen.add(s)
        while q:
            for v in neigh(q.popleft()):
                if v not in seen:
                    seen.add(v); q.append(v); comp.append(v)
        if len(comp) > len(best):
            best = comp
    return best


def _diameter_path(comp, neigh):
    cs = set(comp)

    def bfs(src):
        par, q, last = {src: None}, deque([src]), src
        while q:
            u = q.popleft(); last = u
            for v in neigh(u):
                if v in cs and v not in par:
                    par[v] = u; q.append(v)
        return last, par

    a, _ = bfs(comp[0])
    b, par = bfs(a)
    path, c = [], b
    while c is not None:
        path.append(c); c = par[c]
    return path[::-1]


def trace_path(data: bytes, leg: int):
    """Ordered centerline [(x,y), ...] of the leg's track-map (pixel coords, 0..127 x 0..39)."""
    grid = mapview.decode_map(data, leg)
    pts = {(x, y) for y in range(mapview.MAP_H) for x in range(mapview.MAP_W) if grid[y][x]}
    if not pts:
        return []
    neigh = _neighbours(pts)
    comp = _largest_component(pts, neigh)
    if len(comp) < MIN_COMPONENT:
        return []
    return _diameter_path(comp, neigh)


def build_course(data: bytes, leg: int) -> dict:
    """A JSON-able 3D course model: centered path, per-point elevation, width, roadside objects."""
    path = trace_path(data, leg)
    segs = roadprofile.road_profile(data, leg, PROFILE_SEGS)
    n = len(path)
    m = len(segs)

    # center the path on the origin so the mesh sits around (0,0)
    cx = sum(p[0] for p in path) / n if n else 0
    cy = sum(p[1] for p in path) / n if n else 0
    pts = [[p[0] - cx, p[1] - cy] for p in path]

    # elevation: sample the stream's accumulated hill profile at each path fraction
    def seg_at(frac):
        return segs[min(m - 1, int(frac * (m - 1)))] if m else None

    elev = []
    for i in range(n):
        s = seg_at(i / (n - 1) if n > 1 else 0)
        elev.append(round(s.elev1 * ELEV_SCALE, 3) if s else 0.0)

    # objects: stream segments that carry object slots, placed by fraction along the path
    objects = []
    for j, s in enumerate(segs):
        if s.objects:
            objects.append({"t": round(j / (m - 1) if m > 1 else 0, 4),
                            "side": 1 if (j % 2 == 0) else -1,
                            "type": int(s.objects[0])})

    return {
        "leg": leg,
        "path": pts,
        "elevation": elev,
        "halfWidth": ROAD_HALF_WIDTH,
        "objects": objects,
        "mapW": mapview.MAP_W,
        "mapH": mapview.MAP_H,
        "segments": [{"i": s.index, "rows": s.rows, "slope": s.slope} for s in segs[:64]],
    }
