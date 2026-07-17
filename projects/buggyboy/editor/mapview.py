"""mapview.py — decode a leg's dashboard track-map bitmap into an ASCII preview.

The map is a real game asset: init_leg_dash (src/results.c) copies a 40-row x 0x20-byte
block from mem_base + leg*0x500 into buf_c as a 4-plane graphic. Per 4-byte source unit
the planes are [w0, w1, w1, w1]; probe_collision (which walks the dashboard progress
marker) tests plane1 & plane3 == w1. So:

  - plane1 (w1) is the TRACK LINE — the winding course shape the marker follows;
  - plane0 (w0) is the complementary scenery fill.

The course shape *is* w1, so that's what we decode and render (16 px/unit, 8 units =>
128 x 40). Painting the course toggles w1 only (course_file.set_map_pixel), leaving the
scenery plane untouched, so the marker path always matches what you see.

Pure functions, no curses — testable and reusable by the TUI and any headless dump.
"""
from __future__ import annotations

import course_format as cf

MAP_W = 128          # 8 units x 16 px
MAP_H = cf.DASH_ROWS  # 40

TRACK_CH = "█"       # a track (w1) pixel
FIELD_CH = " "       # scenery / off-track


def decode_map(data: bytes, leg: int) -> list[list[int]]:
    """Return a 40x128 grid of 0/1 TRACK pixels (plane1/w1) for the leg's dashboard map."""
    base = leg * cf.DASH_LEG_STRIDE
    grid: list[list[int]] = []
    for row in range(MAP_H):
        s = base + row * cf.DASH_SRC_STRIDE
        pixels: list[int] = []
        for unit in range(8):
            w1 = cf.be16(data, s + unit * 4 + 2)   # +2 = plane1 = track
            for bit in range(15, -1, -1):
                pixels.append((w1 >> bit) & 1)
        grid.append(pixels)
    return grid


def render_ascii(grid: list[list[int]], scale: int = 2,
                 on: str = TRACK_CH, off: str = FIELD_CH) -> list[str]:
    """Downsample horizontally by `scale` and render (track drawn, field blank)."""
    lines: list[str] = []
    for pixels in grid:
        chars = [on if any(pixels[x:x + scale]) else off for x in range(0, MAP_W, scale)]
        lines.append("".join(chars))
    return lines


def window(grid: list[list[int]], x0: int, y0: int, w: int, h: int,
           cursor: tuple[int, int] | None = None) -> list[str]:
    """A full-resolution sub-window [x0:x0+w, y0:y0+h] with an optional cursor char.

    Used by the paint mode so 1 char == 1 pixel. The cursor cell is drawn as '+' (on
    track) or 'x' (off) so it's visible against either background; the TUI reverses it.
    """
    out: list[str] = []
    for y in range(y0, min(y0 + h, MAP_H)):
        row = []
        for x in range(x0, min(x0 + w, MAP_W)):
            on = grid[y][x]
            if cursor == (x, y):
                row.append("+" if on else "x")
            else:
                row.append(TRACK_CH if on else FIELD_CH)
        out.append("".join(row))
    return out


if __name__ == "__main__":  # headless preview: python mapview.py [leg]
    import sys
    from pathlib import Path
    leg = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    data = (Path(__file__).resolve().parents[1] / "bin" / "COURSES.DAT").read_bytes()
    for line in render_ascii(decode_map(data, leg)):
        print(line)
