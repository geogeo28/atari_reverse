"""BLACK ICE key art - two in-game mockups and a title screen, all rendered from the assets.

The mockups are not paintings.  `render_window` is a real grid raycaster (DDA, perpendicular
distance, per-column texture sampling, a depth buffer for billboards) writing into the same
160x80 chunky buffer the STE renderer will write into, and shading through `shade_table`.
If a texture reads badly here, it reads badly in the game.

Nothing in this module is allowed to invent a colour: every pixel comes from textures.py,
sprites.py, hud.py or the palette.
"""

import math
from collections import namedtuple

import numpy as np

import drawlib
import font
import hud
import palette
import pixelio
import sprites
import textures
from drawlib import Canvas

WINDOW_WIDTH = hud.WINDOW_CHUNKY_WIDTH
WINDOW_HEIGHT = hud.WINDOW_CHUNKY_HEIGHT
HORIZON = WINDOW_HEIGHT // 2
TEX_SIZE = textures.TEX_SIZE
#: 60-degree horizontal field of view: plane length = tan(fov/2).
FOV_SCALE = 0.577
#: One depth band every 3 cells; a north/south face costs one extra band ("band + side").
BAND_DISTANCE = 3.0
FAR_CLIP = BAND_DISTANCE * palette.DEPTH_BANDS
EMPTY_CELL = "."

MAP_LEGEND = {
    "#": "circuit_lattice", "B": "bus_trunk", "H": "hex_mesh", "L": "glyph_column",
    "F": "firewall_chevron", "C": "corrupted_sector", "A": "anchor_pylon",
    "G": "exit_gate", "D": "door", "K": "sector_key_panel",
}


#: A thing standing in the world.  `height` is in grid cells; 1.0 is floor-to-ceiling.
Billboard = namedtuple("Billboard", "name x y height")


class Scene:
    """A grid map, a camera and a billboard list - everything render_window needs."""

    def __init__(self, rows, position, facing_degrees, billboards):
        self.rows = rows
        self.position = position
        self.facing = math.radians(facing_degrees)
        self.billboards = billboards
        self.tiles = {name: array for name, array in textures.build_all().items()}

    def cell(self, x, y):
        if not (0 <= y < len(self.rows) and 0 <= x < len(self.rows[y])):
            return EMPTY_CELL
        return self.rows[y][x]

    def texture_at(self, x, y):
        return self.tiles[MAP_LEGEND[self.cell(x, y)]]


def _cast_ray(scene, origin, direction):
    """DDA through the grid.  Returns (perpendicular distance, map cell, side, wall fraction)."""
    map_x, map_y = int(origin[0]), int(origin[1])
    delta = [abs(1.0 / direction[0]) if direction[0] else math.inf,
             abs(1.0 / direction[1]) if direction[1] else math.inf]
    step = [1 if direction[0] >= 0 else -1, 1 if direction[1] >= 0 else -1]
    side_dist = [(map_x + 1 - origin[0]) * delta[0] if step[0] > 0 else (origin[0] - map_x) * delta[0],
                 (map_y + 1 - origin[1]) * delta[1] if step[1] > 0 else (origin[1] - map_y) * delta[1]]
    side = 0
    for _ in range(int(FAR_CLIP * 4)):
        side = 0 if side_dist[0] < side_dist[1] else 1
        side_dist[side] += delta[side]
        if side == 0:
            map_x += step[0]
        else:
            map_y += step[1]
        if scene.cell(map_x, map_y) != EMPTY_CELL:
            distance = side_dist[side] - delta[side]
            hit = origin[1 - side] + distance * direction[1 - side]
            return distance, (map_x, map_y), side, hit - math.floor(hit)
    return math.inf, None, side, 0.0


def depth_band(distance, side):
    """The critique's endorsed shading: one add of `band + is_north_south_face`."""
    return min(int(distance / BAND_DISTANCE) + side, palette.DEPTH_BANDS - 1)


def _draw_wall_column(window, column, distance, texture, side, wall_fraction):
    """One 1-px-wide wall slice, texture-sampled and shaded by its depth band."""
    height = int(WINDOW_HEIGHT / distance)
    top = HORIZON - height // 2
    texture_x = int(wall_fraction * TEX_SIZE) % TEX_SIZE
    shaded = drawlib.shade(texture[:, texture_x], depth_band(distance, side))
    first = max(top, 0)
    last = min(top + height, WINDOW_HEIGHT)
    if last <= first:
        return
    rows = ((np.arange(first, last) - top) * TEX_SIZE // max(height, 1)).clip(0, TEX_SIZE - 1)
    window[first:last, column] = shaded[rows]


def _draw_billboard(window, depths, scene, sprite_array, billboard, direction, plane):
    """Project one floor-standing billboard, z-tested per column against the wall depths."""
    relative = (billboard.x - scene.position[0], billboard.y - scene.position[1])
    determinant = 1.0 / (plane[0] * direction[1] - direction[0] * plane[1])
    camera_x = determinant * (direction[1] * relative[0] - direction[0] * relative[1])
    camera_depth = determinant * (-plane[1] * relative[0] + plane[0] * relative[1])
    if camera_depth <= 0.1:
        return
    cell_height = WINDOW_HEIGHT / camera_depth
    size = max(int(cell_height * billboard.height), 1)
    screen_x = int(WINDOW_WIDTH / 2 * (1 + camera_x / camera_depth))
    floor_row = HORIZON + int(cell_height / 2)
    top = floor_row - size
    shaded = drawlib.shade_sprite(sprite_array, min(int(camera_depth / BAND_DISTANCE),
                                                   palette.DEPTH_BANDS - 1), sprites.KEY)
    source_height, source_width = sprite_array.shape
    for offset in range(size):
        column = screen_x - size // 2 + offset
        if not 0 <= column < WINDOW_WIDTH or camera_depth >= depths[column]:
            continue
        texture_x = offset * source_width // size
        for row_offset in range(size):
            row = top + row_offset
            if not 0 <= row < WINDOW_HEIGHT:
                continue
            texel = shaded[row_offset * source_height // size, texture_x]
            if texel != sprites.KEY:
                window[row, column] = texel


def render_window(scene):
    """The 160x80 chunky buffer: void floor and ceiling, textured walls, then billboards."""
    window = np.full((WINDOW_HEIGHT, WINDOW_WIDTH), palette.VOID, dtype=np.uint8)
    depths = np.full(WINDOW_WIDTH, math.inf)
    direction = (math.cos(scene.facing), math.sin(scene.facing))
    plane = (-math.sin(scene.facing) * FOV_SCALE, math.cos(scene.facing) * FOV_SCALE)
    for column in range(WINDOW_WIDTH):
        camera_x = 2.0 * column / WINDOW_WIDTH - 1.0
        ray = (direction[0] + plane[0] * camera_x, direction[1] + plane[1] * camera_x)
        distance, cell, side, wall_fraction = _cast_ray(scene, scene.position, ray)
        if cell is None or distance <= 0:
            continue
        depths[column] = distance
        _draw_wall_column(window, column, distance, scene.texture_at(*cell), side, wall_fraction)
    ordered = sorted(scene.billboards,
                     key=lambda item: -((item.x - scene.position[0]) ** 2
                                        + (item.y - scene.position[1]) ** 2))
    built = sprites.build_all()
    for billboard in ordered:
        _draw_billboard(window, depths, scene, built[billboard.name], billboard, direction, plane)
    return window


def _overlay_weapon(window, weapon_name):
    """The weapon is a sprite drawn into the chunky buffer, bottom-centre of the window."""
    art = sprites.build_all()[weapon_name]
    x = (WINDOW_WIDTH - art.shape[1]) // 2
    y = WINDOW_HEIGHT - art.shape[0]
    canvas = Canvas.from_array(window)
    canvas.blit(art, x, y, key=sprites.KEY)
    return canvas.array


# --- the two mockups ----------------------------------------------------------------------------
THE_LEDGER_MAP = (
    "#############",
    "#############",
    "##B###B###B##",
    "#..........##",
    "##B#D#L###B##",
    "#############",
    "#############",
)
THE_LEDGER_STATE = hud.HudState(sector_name="SECTOR 2: THE LEDGER", run_clock="01:12",
                               integrity=84, cycles=112, trace=31, tokens=(True, False, False),
                               weapon="buster")

# THE SHEAR, drawn rather than described: the sector was written twice and the second copy
# landed one cell out, so the north wall's pylons and firewalls sit one cell along from the
# south wall's and the two halves never line up.  A single-cell corridor also keeps the near
# walls full height, which is what stops the shot being a starburst in an empty black frame.
THE_KERNEL_MAP = (
    "CCCCCCCCCCCCC",
    "CCCCCCCCCCCCC",
    "CACCFCCACCFCC",
    "C..........AC",
    "CCACCFCCACCFC",
    "CCCCCCCCCCCCC",
    "CCCCCCCCCCCCC",
)
THE_KERNEL_STATE = hud.HudState(sector_name="SECTOR 8: THE KERNEL", run_clock="02:41",
                                   integrity=29, cycles=48, trace=88, tokens=(True, True, False),
                                   weapon="spike")


def mockup_the_ledger():
    """Shot 1: SECTOR 2, THE LEDGER.  Two wall textures, a door, a Watchdog and a Sentry."""
    scene = Scene(THE_LEDGER_MAP, position=(1.5, 3.5), facing_degrees=0,
                  billboards=(Billboard("watchdog", 4.8, 3.80, 0.85),
                              Billboard("sentry", 3.6, 3.22, 0.9),
                              Billboard("cycles_cell", 2.9, 3.85, 0.35)))
    window = _overlay_weapon(render_window(scene), "buster_idle")
    return hud.compose_screen(window, THE_LEDGER_STATE)


def mockup_the_kernel():
    """Shot 2: SECTOR 8, THE KERNEL.  Terminal corruption, Black ICE, Spike firing at 88%."""
    scene = Scene(THE_KERNEL_MAP, position=(1.5, 3.5), facing_degrees=0,
                  billboards=(Billboard("black_ice", 5.0, 3.62, 1.0),
                              Billboard("tracer", 2.9, 3.22, 0.75),
                              Billboard("access_token", 3.8, 3.78, 0.35)))
    window = _overlay_weapon(render_window(scene), "spike_firing")
    return hud.compose_screen(window, THE_KERNEL_STATE)


# --- title screen -------------------------------------------------------------------------------
TITLE_SCALE = 4
#: Stacked top to bottom: machine line, strapline, wordmark, then the figure standing on the
#: grid.  Nothing overlaps the letters - a logo fighting a silhouette loses to the silhouette.
MACHINE_LINE_Y = 0
STRAPLINE_Y = 9
TITLE_Y = 20
FIGURE_TOP = 50
GRID_HORIZON = 100
BOTTOM_BLOCK_TOP = 176
PROMPT_Y = 179
PUBLISHER_Y = 189
PYLON_LAMPS = 3
GRID_VANISH_X = hud.SCREEN_WIDTH // 2
GRID_RAY_SPACING = 24
GRID_ROW_STEPS = (2, 6, 12, 21, 34, 54, 84)
GLOW_LAYERS = ((3, palette.MAG_5), (2, palette.MAG_4), (1, palette.MAG_2))
WORDMARK_LEFT, WORDMARK_RIGHT = "BLACK ", "ICE"
TITLE_STRAPLINE = "BREAK IN.  STRIP IT.  GET OUT."
TITLE_MACHINE = "8 SECTORS - 22 MINUTES - ATARI STE"
TITLE_PROMPT = "PRESS FIRE TO BREAK IN"
TITLE_PUBLISHER = "OSSUARY ROW SOFTWARE   (C) 1987"
TEXT_BAR_PAD = 3


def _corner_pylons(canvas):
    """Two anchor pylons receding into the grid.  Without them the lower corners are dead void,
    and dead corners are the difference between a product shot and a renderer screenshot."""
    for near_x, far_x in ((0, 54), (hud.SCREEN_WIDTH - 1, hud.SCREEN_WIDTH - 55)):
        canvas.polygon([(near_x, GRID_HORIZON - 18), (far_x, GRID_HORIZON + 4),
                        (far_x, GRID_HORIZON + 48), (near_x, hud.SCREEN_HEIGHT)], palette.CYAN_5)
        canvas.polygon([(near_x, GRID_HORIZON - 18), (far_x, GRID_HORIZON + 4),
                        (far_x, GRID_HORIZON + 12), (near_x, GRID_HORIZON + 4)], palette.GRID)
        canvas.polyline([(far_x, GRID_HORIZON + 4), (far_x, GRID_HORIZON + 48)],
                        palette.CYAN_4, width=2)
        inward = 1 if near_x == 0 else -1
        for lamp in range(PYLON_LAMPS):
            lamp_x = near_x + inward * (12 + lamp * 15)
            lamp_y = GRID_HORIZON + 20 + lamp * 22
            size = 9 - lamp * 2
            left, right = sorted((lamp_x, lamp_x + inward * size))
            canvas.rect(left, lamp_y, right, lamp_y + size, palette.CYAN_5)
            canvas.rect(left + 1, lamp_y + 1, right - 1, lamp_y + size - 1, palette.MAG_2)


def _perspective_grid(canvas):
    """The void has a floor after all: a receding grid, the oldest trick in the 1987 book."""
    for step in GRID_ROW_STEPS:
        y = GRID_HORIZON + step
        canvas.hline(y, 0, hud.SCREEN_WIDTH - 1, palette.CYAN_5, thickness=2)
    for offset in range(-hud.SCREEN_WIDTH, hud.SCREEN_WIDTH * 2, GRID_RAY_SPACING):
        canvas.line(GRID_VANISH_X, GRID_HORIZON, offset, hud.SCREEN_HEIGHT - 1,
                    palette.CYAN_5, width=2)
    canvas.hline(GRID_HORIZON, 0, hud.SCREEN_WIDTH - 1, palette.GRID, thickness=2)


def _glow_text(canvas, x, y, text, ink, scale):
    """Chunky glow: the same word stamped in receding ramp entries before the lit pass."""
    for offset, shade in GLOW_LAYERS:
        for dx, dy in ((-offset, 0), (offset, 0), (0, -offset), (0, offset)):
            hud.draw_text(canvas, x + dx, y + dy, text, shade, scale=scale)
    hud.draw_text(canvas, x, y, text, ink, scale=scale)


def title_screen():
    """The first screen: the boss rising out of the grid under a wordmark it cannot reach."""
    canvas = Canvas(hud.SCREEN_WIDTH, hud.SCREEN_HEIGHT, palette.VOID)
    _perspective_grid(canvas)
    _corner_pylons(canvas)
    boss = drawlib.upscale(drawlib.shade_sprite(sprites.build_all()["black_ice"], 1, sprites.KEY), 2)
    canvas.blit(boss, (hud.SCREEN_WIDTH - boss.shape[1]) // 2, FIGURE_TOP, key=sprites.KEY)
    _centred(canvas, MACHINE_LINE_Y, TITLE_MACHINE, palette.CYAN_3)
    _centred(canvas, STRAPLINE_Y, TITLE_STRAPLINE, palette.DATA)
    wordmark_width = font.text_width(WORDMARK_LEFT + WORDMARK_RIGHT) * TITLE_SCALE
    left_x = (hud.SCREEN_WIDTH - wordmark_width) // 2
    _glow_text(canvas, left_x, TITLE_Y, WORDMARK_LEFT, palette.CYAN_1, TITLE_SCALE)
    _glow_text(canvas, left_x + font.text_width(WORDMARK_LEFT) * TITLE_SCALE, TITLE_Y,
               WORDMARK_RIGHT, palette.MAG_1, TITLE_SCALE)
    canvas.rect(0, BOTTOM_BLOCK_TOP, hud.SCREEN_WIDTH - 1, hud.SCREEN_HEIGHT - 1, palette.GRID)
    canvas.hline(BOTTOM_BLOCK_TOP, 0, hud.SCREEN_WIDTH - 1, palette.CYAN_3, thickness=1)
    _centred(canvas, PROMPT_Y, TITLE_PROMPT, palette.RIM)
    _centred(canvas, PUBLISHER_Y, TITLE_PUBLISHER, palette.CYAN_2)
    return canvas.array


def _text_bar(canvas, y, text, ink, background):
    """A full-width band behind a caption, so the figure never fights the words."""
    canvas.rect(0, y - TEXT_BAR_PAD, hud.SCREEN_WIDTH - 1,
                y + font.GLYPH_HEIGHT + TEXT_BAR_PAD - 2, background)
    _centred(canvas, y, text, ink)


def _centred(canvas, y, text, ink, scale=1):
    hud.draw_text(canvas, (hud.SCREEN_WIDTH - font.text_width(text) * scale) // 2, y, text,
                  ink, scale=scale)


MOCKUPS = (
    ("mockup_the_ledger", mockup_the_ledger),
    ("mockup_the_kernel", mockup_the_kernel),
    ("title_screen", title_screen),
)


def main():
    pixelio.ensure_dirs()
    for name, builder in MOCKUPS:
        array = builder()
        native, preview = pixelio.save(array, name)
        print("%-22s %dx%d  %s" % (name, array.shape[1], array.shape[0], preview))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
