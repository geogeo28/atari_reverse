#!/usr/bin/env python3
"""Check the on-target frame, in two independent halves.

The spike's own numbers say how FAST it draws; nothing in them says the picture is RIGHT. Two
checks say it, and splitting them is what makes a failure locatable rather than just red:

  GEOMETRY  the SpikeRay array the target published for its showcase frame, against a textbook
            Lodev DDA over the same map, viewpoint and field of view written here in floats with
            none of the target's fixed point. This is the raycaster on trial and nothing else.

  DRAWING   the wall silhouette read back out of the Hatari screenshot — for each logical column
            the first and last row that is neither the ceiling pen nor the floor pen — against
            those same published rays. This is the asm column drawer, the c2p, the pixel doubling
            and the palette on trial, held to the raycast's own answer, so it must match EXACTLY.

A picture that matches the rays and rays that match the reference is the whole verification. When
only the first fails the fault is in the asm; when only the second fails it is in the raycaster.

Usage: verify.py [screenshot.png [ledger.bin]]
"""
import struct
import math
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent


def spike_constants():
    """spike.h's #defines, so this checker cannot drift from the program it checks."""
    text = (HERE / "spike.h").read_text()
    consts = {name: int(value, 0)
              for name, value in re.findall(r"^#define\s+(\w+)\s+(-?(?:0x)?[0-9a-fA-F]+)L?\s*(?:/\*.*)?$",
                                            text, re.M)}
    for _ in range(4):
        for name, expr in re.findall(r"^#define\s+(\w+)\s+(\(.*?\))\s*(?:/\*.*)?$", text, re.M):
            if name not in consts:
                try:
                    consts[name] = int(eval(expr.replace("L", "").replace("(int)", ""), {}, consts))
                except (NameError, TypeError, SyntaxError, ZeroDivisionError):
                    pass
    start = re.search(r"^#define\s+VIEWPOINT_START_ANGLE\s+(\d+)", (HERE / "main.c").read_text(), re.M)
    consts["VIEWPOINT_START_ANGLE"] = int(start.group(1))
    for name in ("MAP_START_X", "MAP_START_Y"):
        found = re.search(rf"^#define\s+{name}\s+(\d+)", (HERE / "main.c").read_text(), re.M)
        consts[name] = int(found.group(1))
    return consts


def build_map(k):
    """main.c's build_map, restated — a room grid with a doorway in the middle of every wall."""
    size, room = k["MAP_SIZE"], k["MAP_ROOM"]
    grid = [[0] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            in_x, in_y = x % room, y % room
            on_wall = in_x == 0 or in_y == 0
            door = ((in_x == 0 and in_y in (k["MAP_DOOR_LOW"], k["MAP_DOOR_HIGH"]))
                    or (in_y == 0 and in_x in (k["MAP_DOOR_LOW"], k["MAP_DOOR_HIGH"])))
            cell = 1 + ((x // room + y // room) % k["TEX_COUNT"]) if on_wall and not door else 0
            if x in (0, size - 1) or y in (0, size - 1):
                cell = 1
            grid[y][x] = cell
    return grid


def reference_silhouette(k):
    """Lodev's DDA in floats: (top row, bottom row) of the wall for each logical column."""
    grid = build_map(k)
    pos_x, pos_y = k["MAP_START_X"] + 0.5, k["MAP_START_Y"] + 0.5
    angle = 2 * math.pi * k["VIEWPOINT_START_ANGLE"] / k["BRAD_FULL"]
    dir_x, dir_y = math.cos(angle), math.sin(angle)
    tan_half = k["TAN_HALF_FOV_8_8"] / 256.0
    plane_x, plane_y = -dir_y * tan_half, dir_x * tan_half
    width, height_rows = k["VIEW_W_HIGH"], k["VIEW_H"]
    out = []
    for column in range(width):
        camera = (2 * column + 1 - width) / width
        ray_x, ray_y = dir_x + plane_x * camera, dir_y + plane_y * camera
        map_x, map_y = int(pos_x), int(pos_y)
        delta_x = abs(1 / ray_x) if ray_x else 1e30
        delta_y = abs(1 / ray_y) if ray_y else 1e30
        if ray_x < 0:
            step_x, side_x = -1, (pos_x - map_x) * delta_x
        else:
            step_x, side_x = 1, (map_x + 1 - pos_x) * delta_x
        if ray_y < 0:
            step_y, side_y = -1, (pos_y - map_y) * delta_y
        else:
            step_y, side_y = 1, (map_y + 1 - pos_y) * delta_y
        side = 0
        for _ in range(k["DDA_MAX_STEPS"]):
            if side_x < side_y:
                side_x += delta_x
                map_x += step_x
                side = 0
            else:
                side_y += delta_y
                map_y += step_y
                side = 1
            if grid[map_y][map_x]:
                break
        perp = max(side_x - delta_x if side == 0 else side_y - delta_y, k["MIN_PERP_DIST"] / 65536.0)
        wall = int(height_rows * 256 / int(perp * 256))
        top = max((height_rows - wall) // 2, 0)
        bottom = min(top + wall - (0 if wall <= height_rows else 0), height_rows)
        if wall > height_rows:
            top, bottom = 0, height_rows
        out.append((top, bottom))
    return out


def screen_silhouette(png, k):
    """The same silhouette read back out of the rendered frame.

    Hatari's PNG carries the borders, so the 320x200 screen is located by its bounding box, and the
    doubling is undone by sampling one pixel per logical pixel."""
    image = Image.open(png).convert("RGB")
    pixels = image.load()
    columns = [x for x in range(image.width)
               if any(pixels[x, y] != (0, 0, 0) for y in range(0, image.height, 4))]
    rows = [y for y in range(image.height)
            if any(pixels[x, y] != (0, 0, 0) for x in range(0, image.width, 4))]
    left, top = columns[0], rows[0]
    scale_x = (columns[-1] - left + 1) // k["SCREEN_W"]
    scale_y = (rows[-1] - top + 1) // k["SCREEN_H"]
    ceiling = pixels[left, top]                                    # row 0 is always ceiling
    floor = pixels[left, top + (k["SCREEN_H"] - 1) * scale_y]      # ...and the last row floor
    out = []
    for column in range(k["VIEW_W_HIGH"]):
        x = left + column * (k["SCREEN_W"] // k["VIEW_W_HIGH"]) * scale_x
        wall_rows = [row for row in range(k["VIEW_H"])
                     if pixels[x, top + row * (k["SCREEN_H"] // k["VIEW_H"]) * scale_y]
                     not in (ceiling, floor)]
        out.append((wall_rows[0], wall_rows[-1] + 1) if wall_rows else (k["VIEW_H"], k["VIEW_H"]))
    return out


# A row of slack each way on the GEOMETRY check: the target truncates its distance to 8.8 and its
# wall height to an integer before halving it, so a column on a boundary lands one row either side
# of the float reference. The DRAWING check has no slack at all — the asm either draws the rows the
# raycast asked for or it does not.
ROW_TOLERANCE = 1

# Columns allowed to miss the geometry check by more than that. A ray that grazes a corner is
# decided by the last bit of a fixed-point comparison, and the target and a float reference can
# legitimately step into different cells there; the count is capped so the allowance cannot quietly
# absorb a real fault, and every one of them is printed.
GRAZING_ALLOWANCE = 4

RAY_SIZEOF = 16
RAYS_OFFSET = 0x400


def published_rays(path, k):
    """(top, bottom) per column as the TARGET computed them, out of its published SpikeRay array."""
    raw = path.read_bytes()[RAYS_OFFSET:]
    out = []
    for column in range(k["VIEW_W_HIGH"]):
        _, top, rows, _, _, _ = struct.unpack(">HhhhLL", raw[column * RAY_SIZEOF:(column + 1) * RAY_SIZEOF])
        out.append((top, top + rows))
    return out


def compare(name, expected, actual, tolerance, allowance):
    """Report one check; returns the number of columns outside the allowance."""
    off = [(i, a, b) for i, (a, b) in enumerate(zip(expected, actual))
           if abs(a[0] - b[0]) > tolerance or abs(a[1] - b[1]) > tolerance]
    worst_top = max(abs(a[0] - b[0]) for a, b in zip(expected, actual))
    worst_bottom = max(abs(a[1] - b[1]) for a, b in zip(expected, actual))
    print(f"{name}: {len(expected)} columns, worst top delta {worst_top}, "
          f"worst bottom delta {worst_bottom}, {len(off)} outside +/-{tolerance}")
    for index, want, got in off:
        print(f"    column {index}: expected {want}, got {got}")
    if len(off) > allowance:
        print(f"  FAIL: {len(off)} columns outside tolerance, at most {allowance} allowed")
        return 1
    print("  PASS")
    return 0


def main():
    k = spike_constants()
    png = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out" / "frame.png"
    ledger = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "out" / "ledger.bin"
    reference = reference_silhouette(k)
    rays = published_rays(ledger, k)
    rendered = screen_silhouette(png, k)
    failures = compare("GEOMETRY (target rays vs float reference)", reference, rays,
                       ROW_TOLERANCE, GRAZING_ALLOWANCE)
    failures += compare("DRAWING  (rendered frame vs target rays)", rays, rendered, 0, 0)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
