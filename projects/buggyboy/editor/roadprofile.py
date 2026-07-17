"""roadprofile.py — decode the road geometry we drive, from a leg's record stream.

What is (and isn't) in COURSES.DAT, established empirically (see the editor README):
  - the road's ELEVATION is here: each record sets a segment slope = (control & 7) - 3,
    which game_update writes to road_seg_data[12] (the new far segment) and feeds to the
    verified build_road_geometry. Held for `rows` = (control & 0xf8) >> 3 scanlines.
    Accumulating slope*rows down the leg gives the hill/crest profile.
  - the roadside OBJECT layout is here: the 15 mask-gated payload slots hold object-type
    codes (0 = empty), dispatched by game_update's object jump table.
  - the horizontal CURVE is NOT here: road_curve is runtime steering state, so we don't
    fabricate it. This module decodes only what the file actually encodes.

Editing a segment's slope is set_control(leg, k, rows, slope) on the CourseFile (the slope
is that call's `decay` argument), so the road profile is editable and persists to the file.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import course_format as cf


@dataclass
class RoadSeg:
    index: int          # play-order record index
    rows: int           # segment length in scanlines ((control & 0xf8) >> 3)
    slope: int          # elevation slope this segment, (control & 7) - 3  (-3..+4)
    dist0: int          # cumulative distance (rows) at the segment start
    elev0: int          # cumulative elevation at the segment start
    elev1: int          # cumulative elevation at the segment end
    marker: int         # +6 marker word (event / continuous feature; bit15 = active)
    objects: list[int] = field(default_factory=list)   # nonzero object-type slots


def road_profile(data: bytes, leg: int, count: int = 256) -> list[RoadSeg]:
    """Decode the leg's segments (elevation + objects) in play order."""
    anchor = cf.leg_stream_anchor(leg)
    low_bound = anchor - cf.LEG_STRIDE
    slots = [0] * cf.SELECT_BITS
    segs: list[RoadSeg] = []
    dist = elev = 0
    for k in range(1, count + 1):
        off = anchor - cf.RECORD_BYTES * k
        if off < low_bound or off < 0:
            break
        mask = cf.be16(data, off)
        ctl = data[off + 2]
        marker = cf.be16(data, off + 6)
        # apply this record's mask-gated payload to the persistent object slots
        src = off + 3
        for i, bit in enumerate(range(cf.SELECT_BITS - 1, -1, -1)):
            if mask & (1 << bit):
                slots[i] = data[src]
                src += 1
        rows = (ctl & 0xF8) >> 3
        slope = (ctl & 7) - 3
        step = max(rows, 1)                 # rows==0 still advances one step
        elev0 = elev
        elev += slope * step
        segs.append(RoadSeg(k - 1, rows, slope, dist, elev0, elev, marker,
                            [s for s in slots if s]))
        dist += step
    return segs


def render_profile(segs: list[RoadSeg], width: int, height: int,
                   x0: int = 0, cursor: int | None = None) -> list[str]:
    """Side-view elevation chart: X = segment index window [x0, x0+width), Y = elevation.

    Track profile drawn with '#', baseline (elevation 0) as '-', the cursor column as '|'.
    Elevation is auto-scaled to the pane height across the *visible* window.
    """
    view = segs[x0:x0 + width]
    if not view or height < 3:
        return [""]
    los = [s.elev1 for s in view] + [s.elev0 for s in view] + [0]
    lo, hi = min(los), max(los)
    span = max(1, hi - lo)

    def y_of(e: int) -> int:                # elevation -> row (0 = top)
        return (height - 1) - round((e - lo) / span * (height - 1))

    grid = [[" "] * len(view) for _ in range(height)]
    base = y_of(0)
    for col in range(len(view)):
        grid[base][col] = "-"               # baseline
    for col, s in enumerate(view):
        yr = y_of(s.elev1)
        grid[yr][col] = "#"
        # vertical fill from baseline to the profile point so slopes read as a line
        for y in range(min(yr, base), max(yr, base) + 1):
            if grid[y][col] == " ":
                grid[y][col] = ":"
    if cursor is not None and x0 <= cursor < x0 + len(view):
        cc = cursor - x0
        for y in range(height):
            if grid[y][cc] == " ":
                grid[y][cc] = "|"
    return ["".join(row) for row in grid]


if __name__ == "__main__":   # headless: python roadprofile.py [leg] [count]
    import sys
    from pathlib import Path
    leg = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    data = (Path(__file__).resolve().parents[1] / "bin" / "COURSES.DAT").read_bytes()
    segs = road_profile(data, leg, count)
    print(f"leg {leg}: {len(segs)} segments, {segs[-1].dist0 + segs[-1].rows} rows, "
          f"elevation end {segs[-1].elev1}")
    for line in render_profile(segs, width=min(count, 100), height=20):
        print(line)
