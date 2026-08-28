"""Generate the demo asset set: one palette, four wall textures, a billboard sprite, a HUD
icon, the font, and a 320x200 HUD backdrop -- then write every native format the engine
reads, plus PNG previews for human eyes.

WHY procedural: the BRIEF forbids an external pixel editor, so the art is reproducible
Python. A fixed seed makes every rebuild byte-identical, which is what lets the packed sizes
and the golden hashes in the tests mean anything.

Run: python3 -m stepix.demo_assets [outdir]
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from PIL import Image

from . import font
from .palette import PALETTE_SIZE, StePalette, build_ramp
from .pack import build_pak, read_pak_directory
from .planar import SCREEN_H, SCREEN_W, screen_to_planar, write_pi1
from .quantize import check_palettized, indices_to_rgb
from .sprite import (SPRITE_DIM, TRANSPARENT_INDEX, Sprite, hud_blit, hud_blit_to_c_array, pack_sprites)
from .texture import (DEFAULT_DARK_FACTOR, TEXTURE_DIM, Texture, apply_shade_table, build_shade_table,
                      pack_textures, shade_table_to_c_array, texture_to_c_array)

ART_SEED = 0x57454C46           # "WELF": fixed so every rebuild is byte-identical
PREVIEW_SCALE = 2               # PNGs are upscaled 2x nearest-neighbour so pixels stay square

# ---- palette layout -----------------------------------------------------------------
# The 16 entries are carved into named ramps once, here, and every generator below indexes
# them by name. Changing a ramp length is then a one-line edit that cannot desync the art.
BACKGROUND_RGB = (0, 0, 1)                          # near-black with a blue cast; also the border
SHADOW_INDEX = 0                                    # palette index 0 doubles as the darkest ink in wall art
BRICK_HUE, BRICK_SAT, BRICK_SHADES = 12.0, 0.72, 4
STEEL_HUE, STEEL_SAT, STEEL_SHADES = 215.0, 0.12, 4
STONE_HUE, STONE_SAT, STONE_SHADES = 45.0, 0.22, 3
WOOD_HUE, WOOD_SAT, WOOD_SHADES = 33.0, 0.80, 3
# Stone and wood get only three shades each, and all three have to work as a *surface*. With
# the default ramp floor (L* 12) the darkest shade is near-black, which read as holes punched
# in the masonry rather than as stone; these floors keep every shade a usable face colour.
STONE_LIGHTNESS_MIN = 32.0
WOOD_LIGHTNESS_MIN = 26.0
KEY_RGB = (15, 0, 15)                               # magenta: loud on purpose, see sprite.py
STEEL_LIGHTNESS_MAX = 93.0                          # the top steel shade doubles as HUD white

BRICK_BASE = 1                                      # indices 1..4
STEEL_BASE = BRICK_BASE + BRICK_SHADES              # 5..8
STONE_BASE = STEEL_BASE + STEEL_SHADES              # 9..11
WOOD_BASE = STONE_BASE + STONE_SHADES               # 12..14

BRICK_DARK, BRICK_MID, BRICK_LIT = BRICK_BASE + 1, BRICK_BASE + 2, BRICK_BASE + 3
STEEL_DARK, STEEL_MID, STEEL_LIT, STEEL_WHITE = STEEL_BASE, STEEL_BASE + 1, STEEL_BASE + 2, STEEL_BASE + 3
STONE_DARK, STONE_MID, STONE_LIT = STONE_BASE, STONE_BASE + 1, STONE_BASE + 2
WOOD_DARK, WOOD_MID, WOOD_LIT = WOOD_BASE, WOOD_BASE + 1, WOOD_BASE + 2

# The bases above are derived from the shade counts, but the named shades are hand-written
# offsets from them (brick starts at BASE+1, the others at BASE+0). Editing a count would
# slide a name onto the neighbouring ramp with nothing to notice, so the two are tied here.
NAMED_SHADES = ((BRICK_BASE, BRICK_SHADES, (BRICK_DARK, BRICK_MID, BRICK_LIT)),
                (STEEL_BASE, STEEL_SHADES, (STEEL_DARK, STEEL_MID, STEEL_LIT, STEEL_WHITE)),
                (STONE_BASE, STONE_SHADES, (STONE_DARK, STONE_MID, STONE_LIT)),
                (WOOD_BASE, WOOD_SHADES, (WOOD_DARK, WOOD_MID, WOOD_LIT)))


def _validate_named_shades() -> None:
    """Every named shade must index the ramp it is named after."""
    for base, shades, named in NAMED_SHADES:
        outside = [index for index in named if not base <= index < base + shades]
        if outside:
            raise AssertionError(f"shades {outside} fall outside the {shades}-shade ramp at index {base}")


_validate_named_shades()


def build_demo_palette() -> StePalette:
    """The demo's 16 colours: background, four ramps, and the transparency key at 15."""
    entries = (build_ramp(BRICK_HUE, BRICK_SHADES, BRICK_SAT)
               + build_ramp(STEEL_HUE, STEEL_SHADES, STEEL_SAT, lightness_max=STEEL_LIGHTNESS_MAX)
               + build_ramp(STONE_HUE, STONE_SHADES, STONE_SAT, lightness_min=STONE_LIGHTNESS_MIN)
               + build_ramp(WOOD_HUE, WOOD_SHADES, WOOD_SAT, lightness_min=WOOD_LIGHTNESS_MIN)
               + [KEY_RGB])
    palette = StePalette.build(BACKGROUND_RGB, entries)
    if len(palette.colours) != PALETTE_SIZE or palette.colours[TRANSPARENT_INDEX] != KEY_RGB:
        raise AssertionError("demo palette layout desynced from its index constants")
    return palette


# ---- small drawing helpers ----------------------------------------------------------
def _ellipse_mask(shape: tuple[int, int], centre: tuple[float, float], radii: tuple[float, float]) -> np.ndarray:
    """Boolean ellipse; used for barrel bodies, rivets and lids."""
    rows = np.arange(shape[0])[:, None] - centre[0]
    cols = np.arange(shape[1])[None, :] - centre[1]
    return (rows / radii[0]) ** 2 + (cols / radii[1]) ** 2 <= 1.0


def _speckle(shape: tuple[int, int], rng: np.random.Generator, density: float) -> np.ndarray:
    """Boolean noise mask -- surface grain, kept sparse so it survives the 4-bit palette."""
    return rng.random(shape) < density


# ---- wall textures ------------------------------------------------------------------
BRICK_COURSE_H = 16             # 4 courses in a 64-texel texture
BRICK_LEN = 32                  # two bricks per course, offset half a brick on alternate rows
BRICK_MORTAR = 2                # mortar line thickness in texels
BRICK_GRAIN = 0.10


def brick_texture(rng: np.random.Generator) -> np.ndarray:
    """Running-bond brickwork: mortar grid, per-brick colour jitter, lit top / shadowed base."""
    art = np.full((TEXTURE_DIM, TEXTURE_DIM), STEEL_DARK, dtype=np.uint8)      # mortar colour
    for course, top in enumerate(range(0, TEXTURE_DIM, BRICK_COURSE_H)):
        offset = (course % 2) * (BRICK_LEN // 2)
        for start in range(-BRICK_LEN, TEXTURE_DIM, BRICK_LEN):
            left = start + offset
            face_rows = slice(top + BRICK_MORTAR, top + BRICK_COURSE_H)
            face_cols = slice(max(left + BRICK_MORTAR, 0), min(left + BRICK_LEN, TEXTURE_DIM))
            if face_cols.start >= face_cols.stop:
                continue
            shade = int(rng.choice([BRICK_DARK, BRICK_MID, BRICK_MID, BRICK_LIT]))
            art[face_rows, face_cols] = shade
            art[face_rows.start, face_cols] = min(shade + 1, BRICK_LIT)         # lit top edge
            art[face_rows.stop - 1, face_cols] = BRICK_BASE                     # shadowed base
    grain = _speckle(art.shape, rng, BRICK_GRAIN) & (art != STEEL_DARK)
    return np.where(grain, np.maximum(art.astype(int) - 1, BRICK_BASE), art).astype(np.uint8)


METAL_BEVEL = 3                 # panel border thickness
METAL_RIVET_INSET = 7
METAL_RIVET_RADIUS = 2.6
METAL_VENT_COUNT = 4
METAL_VENT_TOP = 24
METAL_VENT_PITCH = 6
METAL_VENT_H = 3
METAL_VENT_MARGIN = 16
METAL_GRAIN = 0.045


def metal_texture(rng: np.random.Generator) -> np.ndarray:
    """A riveted steel panel: bevelled border, corner rivets, a stack of vent slots."""
    art = np.full((TEXTURE_DIM, TEXTURE_DIM), STEEL_MID, dtype=np.uint8)
    art[:METAL_BEVEL, :] = STEEL_LIT                                            # light from top-left
    art[:, :METAL_BEVEL] = STEEL_LIT
    art[-METAL_BEVEL:, :] = STEEL_DARK
    art[:, -METAL_BEVEL:] = STEEL_DARK
    art[METAL_BEVEL, METAL_BEVEL:-METAL_BEVEL] = STEEL_WHITE                    # inner highlight line

    for vent in range(METAL_VENT_COUNT):
        top = METAL_VENT_TOP + vent * METAL_VENT_PITCH
        art[top:top + METAL_VENT_H, METAL_VENT_MARGIN:TEXTURE_DIM - METAL_VENT_MARGIN] = SHADOW_INDEX
        art[top + METAL_VENT_H, METAL_VENT_MARGIN:TEXTURE_DIM - METAL_VENT_MARGIN] = STEEL_LIT

    for row in (METAL_RIVET_INSET, TEXTURE_DIM - 1 - METAL_RIVET_INSET):
        for col in (METAL_RIVET_INSET, TEXTURE_DIM - 1 - METAL_RIVET_INSET):
            head = _ellipse_mask(art.shape, (row, col), (METAL_RIVET_RADIUS, METAL_RIVET_RADIUS))
            art[head] = STEEL_LIT
            art[head & _ellipse_mask(art.shape, (row + 0.9, col + 0.9), (METAL_RIVET_RADIUS, METAL_RIVET_RADIUS))] = STEEL_DARK
            art[_ellipse_mask(art.shape, (row - 0.6, col - 0.6), (METAL_RIVET_RADIUS - 1.4, METAL_RIVET_RADIUS - 1.4))] = STEEL_WHITE
    grain = _speckle(art.shape, rng, METAL_GRAIN) & (art == STEEL_MID)
    return np.where(grain, STEEL_LIT, art).astype(np.uint8)


STONE_ROW_HEIGHTS = (14, 12, 15, 13, 10)
STONE_MIN_BLOCK = 13
STONE_MAX_BLOCK = 26
STONE_JOINT = 2
STONE_GRAIN = 0.16


def stone_texture(rng: np.random.Generator) -> np.ndarray:
    """Irregular ashlar: rows of random-width blocks with dark joints and bevelled tops."""
    art = np.full((TEXTURE_DIM, TEXTURE_DIM), SHADOW_INDEX, dtype=np.uint8)   # joint colour
    top = 0
    for height in STONE_ROW_HEIGHTS:
        if top >= TEXTURE_DIM:
            break
        bottom = min(top + height, TEXTURE_DIM)
        left = -int(rng.integers(0, STONE_MIN_BLOCK))                           # stagger the vertical joints
        while left < TEXTURE_DIM:
            width = int(rng.integers(STONE_MIN_BLOCK, STONE_MAX_BLOCK))
            cols = slice(max(left + STONE_JOINT, 0), min(left + width, TEXTURE_DIM))
            rows = slice(top + STONE_JOINT, bottom)
            if cols.start < cols.stop and rows.start < rows.stop:
                shade = int(rng.choice([STONE_DARK, STONE_MID, STONE_MID, STONE_LIT]))
                art[rows, cols] = shade
                art[rows.start, cols] = min(shade + 1, STONE_LIT)
                art[rows.stop - 1, cols] = STONE_DARK
            left += width
        top = bottom
    grain = _speckle(art.shape, rng, STONE_GRAIN) & (art != SHADOW_INDEX)
    return np.where(grain, np.maximum(art.astype(int) - 1, STONE_DARK), art).astype(np.uint8)


DOOR_FRAME = 4                  # steel frame thickness around the leaf
DOOR_BAND_TOP = 30
DOOR_BAND_H = 5
DOOR_WINDOW_TOP, DOOR_WINDOW_H = 12, 12
DOOR_WINDOW_LEFT, DOOR_WINDOW_W = 20, 24
DOOR_BAR_COUNT = 3
DOOR_HANDLE_ROW, DOOR_HANDLE_COL = 40, 46
DOOR_HANDLE_RADIUS = 3.0
DOOR_PLANK_PITCH = 8
DOOR_GRAIN = 0.05               # knots and wear; sparser than brickwork or the planks read as rotten


def door_texture(rng: np.random.Generator) -> np.ndarray:
    """A planked door in a steel frame: barred window, mid band, handle."""
    art = np.full((TEXTURE_DIM, TEXTURE_DIM), WOOD_MID, dtype=np.uint8)
    for seam in range(DOOR_PLANK_PITCH, TEXTURE_DIM, DOOR_PLANK_PITCH):         # vertical planking
        art[:, seam] = WOOD_DARK
        art[:, min(seam + 1, TEXTURE_DIM - 1)] = WOOD_LIT

    art[:DOOR_FRAME, :] = STEEL_LIT                                             # frame, lit from top-left
    art[:, :DOOR_FRAME] = STEEL_LIT
    art[-DOOR_FRAME:, :] = STEEL_DARK
    art[:, -DOOR_FRAME:] = STEEL_DARK

    art[DOOR_BAND_TOP:DOOR_BAND_TOP + DOOR_BAND_H, DOOR_FRAME:TEXTURE_DIM - DOOR_FRAME] = STEEL_MID
    art[DOOR_BAND_TOP, DOOR_FRAME:TEXTURE_DIM - DOOR_FRAME] = STEEL_WHITE
    art[DOOR_BAND_TOP + DOOR_BAND_H - 1, DOOR_FRAME:TEXTURE_DIM - DOOR_FRAME] = STEEL_DARK

    window_rows = slice(DOOR_WINDOW_TOP, DOOR_WINDOW_TOP + DOOR_WINDOW_H)
    window_cols = slice(DOOR_WINDOW_LEFT, DOOR_WINDOW_LEFT + DOOR_WINDOW_W)
    art[window_rows, window_cols] = SHADOW_INDEX                      # dark glass
    art[window_rows.start - 1, window_cols.start - 1:window_cols.stop + 1] = STEEL_DARK
    art[window_rows.stop, window_cols.start - 1:window_cols.stop + 1] = STEEL_LIT
    for bar in range(1, DOOR_BAR_COUNT + 1):
        art[window_rows, window_cols.start + bar * DOOR_WINDOW_W // (DOOR_BAR_COUNT + 1)] = STEEL_MID

    handle = _ellipse_mask(art.shape, (DOOR_HANDLE_ROW, DOOR_HANDLE_COL), (DOOR_HANDLE_RADIUS, DOOR_HANDLE_RADIUS))
    art[handle] = STEEL_LIT
    art[_ellipse_mask(art.shape, (DOOR_HANDLE_ROW - 1, DOOR_HANDLE_COL - 1), (DOOR_HANDLE_RADIUS - 1.5, DOOR_HANDLE_RADIUS - 1.5))] = STEEL_WHITE
    grain = _speckle(art.shape, rng, DOOR_GRAIN) & (art == WOOD_MID)
    return np.where(grain, WOOD_DARK, art).astype(np.uint8)


# ---- billboard sprite ---------------------------------------------------------------
BARREL_TOP, BARREL_BOTTOM = 12, 60          # rows the barrel occupies inside the 64x64 cell
BARREL_CENTRE_COL = SPRITE_DIM / 2 - 0.5
BARREL_HALF_W = 15.0                        # body half-width at the waist
BARREL_BULGE = 2.5                          # extra half-width at mid height: the barrel's belly
BARREL_LID_RY = 4.0
BARREL_HOOP_ROWS = (20, 34, 50)
BARREL_HOOP_H = 3
BARREL_SHADOW_ROW, BARREL_SHADOW_RY = 60, 3.0
BARREL_STAVE_PITCH = 7
BARREL_HIGHLIGHT_FRACTION = 0.32            # where across the body the specular band sits
BARREL_SHADE_FRACTION = 0.80
BARREL_GRAIN = 0.05             # wood grain on the lit staves only


def barrel_sprite(rng: np.random.Generator) -> np.ndarray:
    """A wooden barrel pickup: curved silhouette so the column span table earns its keep."""
    art = np.full((SPRITE_DIM, SPRITE_DIM), TRANSPARENT_INDEX, dtype=np.uint8)
    height = BARREL_BOTTOM - BARREL_TOP

    floor_shadow = _ellipse_mask(art.shape, (BARREL_SHADOW_ROW, BARREL_CENTRE_COL), (BARREL_SHADOW_RY, BARREL_HALF_W))
    art[floor_shadow] = SHADOW_INDEX

    for row in range(BARREL_TOP, BARREL_BOTTOM):
        waist = (row - BARREL_TOP) / height
        half_width = BARREL_HALF_W + BARREL_BULGE * np.sin(np.pi * waist)       # widest at mid height
        left = int(round(BARREL_CENTRE_COL - half_width))
        right = int(round(BARREL_CENTRE_COL + half_width))
        span = np.arange(left, right + 1)
        across = (span - left) / max(right - left, 1)
        shades = np.where(across < BARREL_HIGHLIGHT_FRACTION, WOOD_MID, WOOD_DARK)
        shades = np.where((across >= BARREL_HIGHLIGHT_FRACTION) & (across < BARREL_SHADE_FRACTION), WOOD_LIT, shades)
        art[row, left:right + 1] = shades
        art[row, left] = SHADOW_INDEX                                           # dark rim on both sides
        art[row, right] = SHADOW_INDEX

    for seam in range(int(BARREL_CENTRE_COL - BARREL_HALF_W), SPRITE_DIM, BARREL_STAVE_PITCH):
        column = art[BARREL_TOP:BARREL_BOTTOM, seam]
        art[BARREL_TOP:BARREL_BOTTOM, seam] = np.where(column == TRANSPARENT_INDEX, TRANSPARENT_INDEX, WOOD_DARK)

    for hoop in BARREL_HOOP_ROWS:
        band = art[hoop:hoop + BARREL_HOOP_H]
        opaque = band != TRANSPARENT_INDEX
        art[hoop:hoop + BARREL_HOOP_H] = np.where(opaque, STEEL_MID, band)
        art[hoop] = np.where(art[hoop] == STEEL_MID, STEEL_LIT, art[hoop])
        art[hoop + BARREL_HOOP_H - 1] = np.where(art[hoop + BARREL_HOOP_H - 1] == STEEL_MID, STEEL_DARK, art[hoop + BARREL_HOOP_H - 1])

    lid = _ellipse_mask(art.shape, (BARREL_TOP, BARREL_CENTRE_COL), (BARREL_LID_RY, BARREL_HALF_W))
    art[lid] = WOOD_LIT
    art[lid & _ellipse_mask(art.shape, (BARREL_TOP, BARREL_CENTRE_COL), (BARREL_LID_RY - 1.6, BARREL_HALF_W - 3.0))] = WOOD_MID
    art[_ellipse_mask(art.shape, (BARREL_TOP - 0.5, BARREL_CENTRE_COL), (BARREL_LID_RY - 3.0, BARREL_HALF_W - 8.0))] = WOOD_DARK
    grain = _speckle(art.shape, rng, BARREL_GRAIN) & (art == WOOD_LIT)
    return np.where(grain, WOOD_MID, art).astype(np.uint8)


# ---- HUD icon (fixed-position blit, no pre-shifting) --------------------------------
ICON_W, ICON_H = 32, 32                     # width is a multiple of 16: the HUD never shifts
ICON_MARGIN = 4
ICON_LID_H = 5
ICON_BAND_ROW, ICON_BAND_H = 17, 4
ICON_ROUND_SIZE = 3                         # corner texels knocked out to soften the box


def ammo_icon() -> np.ndarray:
    """A 32x32 ammo crate for the status bar: rounded corners exercise the AND mask."""
    art = np.full((ICON_H, ICON_W), TRANSPARENT_INDEX, dtype=np.uint8)
    body = (slice(ICON_MARGIN, ICON_H - ICON_MARGIN), slice(ICON_MARGIN, ICON_W - ICON_MARGIN))
    art[body] = WOOD_MID
    art[body[0].start:body[0].start + ICON_LID_H, body[1]] = WOOD_LIT           # lid catches the light
    art[body[0].start, body[1]] = STEEL_LIT
    art[body[0].stop - 1, body[1]] = SHADOW_INDEX
    art[body[0], body[1].start] = STEEL_MID
    art[body[0], body[1].stop - 1] = SHADOW_INDEX
    art[ICON_BAND_ROW:ICON_BAND_ROW + ICON_BAND_H, body[1].start + 1:body[1].stop - 1] = STEEL_MID
    art[ICON_BAND_ROW, body[1].start + 1:body[1].stop - 1] = STEEL_WHITE

    # Chamfer the four corners: a texel is cut when its Manhattan distance to the corner is
    # under ICON_ROUND_SIZE. Symmetric by construction, which a per-corner triangle was not.
    rows = np.arange(ICON_H)[:, None]
    cols = np.arange(ICON_W)[None, :]
    for corner_row in (body[0].start, body[0].stop - 1):
        for corner_col in (body[1].start, body[1].stop - 1):
            art[np.abs(rows - corner_row) + np.abs(cols - corner_col) < ICON_ROUND_SIZE] = TRANSPARENT_INDEX
    return art


# ---- 320x200 HUD backdrop -----------------------------------------------------------
VIEW_LEFT, VIEW_TOP = 8, 8
VIEW_W, VIEW_H = SCREEN_W - 2 * VIEW_LEFT, 136           # the raycaster's window inside the frame
STATUS_TOP = VIEW_TOP + VIEW_H + 8                       # 152: the status panel starts here
FRAME_BEVEL = 3
# Bands are painted top-down and each one fills to the bottom of the window, so a later band
# overwrites the earlier ones below its start: the tuples read as "from here down, this shade".
CEILING_BANDS = ((0.00, STEEL_DARK), (0.30, STEEL_MID))
FLOOR_BANDS = ((0.50, WOOD_DARK), (0.70, STONE_DARK), (0.86, STONE_MID))
STATUS_TEXT_ROW = STATUS_TOP + 12
STATUS_TEXT_COL = 88
STATUS_TEXT = "HEALTH 100  AMMO 42"
STATUS_TITLE_ROW = STATUS_TOP + 28
STATUS_TITLE_COL = 88
STATUS_TITLE = "LEVEL 1  SCORE 001280"
ICON_POS_ROW, ICON_POS_COL = STATUS_TOP + 8, 48          # column is a multiple of 16
DROP_SHADOW_OFFSET = 1                                   # the drop shadow sits one texel down-right
LOGO_TEXT = "STEPIX RAYCASTER"
LOGO_ROW, LOGO_COL = VIEW_TOP + 4, VIEW_LEFT + 8


def _draw_bevel_box(art: np.ndarray, top: int, left: int, height: int, width: int,
                    lit: int, shadow: int, fill: int) -> None:
    """Fill a box and bevel it, light from the top-left -- the whole HUD look in one helper."""
    art[top:top + height, left:left + width] = fill
    for edge in range(FRAME_BEVEL):
        art[top + edge, left + edge:left + width - edge] = lit
        art[top + edge:top + height - edge, left + edge] = lit
        art[top + height - 1 - edge, left + edge:left + width - edge] = shadow
        art[top + edge:top + height - edge, left + width - 1 - edge] = shadow


def _blit_text(art: np.ndarray, text: str, row: int, col: int, ink: int, shadow: int | None = None) -> None:
    """Stamp font pixels only where the glyph has ink, optionally with a 1px drop shadow."""
    glyphs = font.render_text(text)
    height, width = glyphs.shape
    overhang = DROP_SHADOW_OFFSET if shadow is not None else 0
    if row < 0 or col < 0 or row + height + overhang > art.shape[0] or col + width + overhang > art.shape[1]:
        raise ValueError(f"text {text!r} ({width}x{height}) at row {row}, col {col} does not fit "
                         f"the {art.shape[1]}x{art.shape[0]} art")
    ink_pixels = glyphs == font.DEFAULT_INK_INDEX
    if shadow is not None:
        shadow_rows = slice(row + DROP_SHADOW_OFFSET, row + DROP_SHADOW_OFFSET + height)
        shadow_cols = slice(col + DROP_SHADOW_OFFSET, col + DROP_SHADOW_OFFSET + width)
        art[shadow_rows, shadow_cols][ink_pixels] = shadow
    art[row:row + height, col:col + width][ink_pixels] = ink


def hud_backdrop() -> np.ndarray:
    """The 320x200 status frame: bevelled border, a ceiling/floor-graded view window, text."""
    art = np.full((SCREEN_H, SCREEN_W), SHADOW_INDEX, dtype=np.uint8)
    _draw_bevel_box(art, 0, 0, SCREEN_H, SCREEN_W, STEEL_MID, STEEL_DARK, SHADOW_INDEX)

    for fraction, shade in CEILING_BANDS + FLOOR_BANDS:
        band_top = VIEW_TOP + int(VIEW_H * fraction)
        art[band_top:VIEW_TOP + VIEW_H, VIEW_LEFT:VIEW_LEFT + VIEW_W] = shade
    for edge in range(2):                                                        # recess the view window
        art[VIEW_TOP - 1 - edge, VIEW_LEFT - 1 - edge:VIEW_LEFT + VIEW_W + 1 + edge] = STEEL_DARK
        art[VIEW_TOP + VIEW_H + edge, VIEW_LEFT - 1 - edge:VIEW_LEFT + VIEW_W + 1 + edge] = STEEL_LIT

    _draw_bevel_box(art, STATUS_TOP, VIEW_LEFT, SCREEN_H - STATUS_TOP - VIEW_TOP, VIEW_W, STEEL_MID, STEEL_DARK, STEEL_DARK)
    _blit_text(art, STATUS_TEXT, STATUS_TEXT_ROW, STATUS_TEXT_COL, STEEL_WHITE, SHADOW_INDEX)
    _blit_text(art, STATUS_TITLE, STATUS_TITLE_ROW, STATUS_TITLE_COL, STONE_LIT, SHADOW_INDEX)
    _blit_text(art, LOGO_TEXT, LOGO_ROW, LOGO_COL, STEEL_WHITE, SHADOW_INDEX)

    icon = ammo_icon()
    target = art[ICON_POS_ROW:ICON_POS_ROW + ICON_H, ICON_POS_COL:ICON_POS_COL + ICON_W]
    art[ICON_POS_ROW:ICON_POS_ROW + ICON_H, ICON_POS_COL:ICON_POS_COL + ICON_W] = np.where(icon == TRANSPARENT_INDEX, target, icon)
    return art


# ---- assembly and output ------------------------------------------------------------
BACKDROP_PREVIEW = "hud_backdrop.png"
FONT_SHEET_COLUMNS = 16
PALETTE_SWATCH = 24             # preview swatch size in pixels, before PREVIEW_SCALE
TEXTURE_PREVIEW_GAP = 4         # gap between the lit and dark halves of a texture preview


@dataclass(frozen=True)
class DemoAssets:
    """Everything the demo generates, before serialisation -- so tests can inspect the art."""

    palette: StePalette
    textures: list[Texture]
    shade_table: bytes
    sprite: Sprite
    icon: np.ndarray
    backdrop: np.ndarray


def build_demo_assets() -> DemoAssets:
    """Generate the whole demo set from one seed, so a rebuild is byte-identical."""
    rng = np.random.default_rng(ART_SEED)
    palette = build_demo_palette()
    textures = [
        Texture("BRICK", brick_texture(rng)),
        Texture("METAL", metal_texture(rng)),
        Texture("STONE", stone_texture(rng)),
        Texture("DOOR", door_texture(rng)),
    ]
    # The transparency key must survive shading: a shaded sprite whose key was remapped
    # would render its holes as a solid colour.
    shade_table = build_shade_table(palette, DEFAULT_DARK_FACTOR, frozenset({TRANSPARENT_INDEX}))
    return DemoAssets(palette, textures, shade_table, Sprite("BARREL", barrel_sprite(rng)), ammo_icon(), hud_backdrop())


def _save_preview(path: str, indices: np.ndarray, palette: StePalette, scale: int = PREVIEW_SCALE) -> None:
    """Write a nearest-neighbour upscaled PNG so a human can actually see 64x64 art."""
    image = Image.fromarray(indices_to_rgb(indices, palette), mode="RGB")
    image.resize((image.width * scale, image.height * scale), Image.NEAREST).save(path)


def _palette_preview(palette: StePalette) -> np.ndarray:
    """A strip of 16 swatches, index 0 first -- the quickest way to eyeball a palette."""
    return np.repeat(np.repeat(np.arange(PALETTE_SIZE, dtype=np.uint8)[None, :], PALETTE_SWATCH, axis=0), PALETTE_SWATCH, axis=1)


def _texture_preview(texture: Texture, shade_table: bytes) -> np.ndarray:
    """Lit and dark variants side by side: the N-S vs E-W cue has to be visible, not asserted."""
    dark = apply_shade_table(texture.indices, shade_table)
    gap = np.full((TEXTURE_DIM, TEXTURE_PREVIEW_GAP), TRANSPARENT_INDEX, dtype=np.uint8)
    return np.concatenate([texture.indices, gap, dark], axis=1)


def write_demo(outdir: str) -> tuple[DemoAssets, dict[str, bytes]]:
    """Generate, serialise and preview everything.

    Returns the art it generated and the resources it put in the .PAK, so a caller verifies
    what was actually written rather than a second, independently rebuilt copy of it.
    """
    os.makedirs(outdir, exist_ok=True)
    assets = build_demo_assets()
    palette = assets.palette

    resources: dict[str, bytes] = {
        "PALETTE": palette.to_bytes(),
        "TEXTURES": pack_textures(assets.textures, assets.shade_table),
        "SPRITES": pack_sprites([assets.sprite]),
        "FONT": font.font_bytes(),
        "HUDSCR": screen_to_planar(assets.backdrop),
    }
    icon_blit = hud_blit(assets.icon)
    resources["ICONDATA"] = icon_blit.data
    resources["ICONMASK"] = icon_blit.mask

    for name, blob in resources.items():
        with open(os.path.join(outdir, f"{name.lower()}.bin"), "wb") as handle:
            handle.write(blob)

    headers = [palette.to_c_array("demo_palette"), shade_table_to_c_array(assets.shade_table)]
    headers += [texture_to_c_array(texture, shade_table=assets.shade_table) for texture in assets.textures]
    headers.append(hud_blit_to_c_array(icon_blit, "hud_ammo_icon"))
    with open(os.path.join(outdir, "demo_assets.h"), "w", encoding="ascii") as handle:
        handle.write("/* Generated by stepix.demo_assets -- do not edit by hand. */\n\n" + "\n".join(headers))

    _save_preview(os.path.join(outdir, "palette.png"), _palette_preview(palette), palette)
    for texture in assets.textures:
        _save_preview(os.path.join(outdir, f"tex_{texture.name.lower()}.png"), _texture_preview(texture, assets.shade_table), palette)
    _save_preview(os.path.join(outdir, "sprite_barrel.png"), assets.sprite.indices, palette)
    _save_preview(os.path.join(outdir, "hud_icon.png"), assets.icon, palette)
    _save_preview(os.path.join(outdir, "font_sheet.png"), font.font_sheet(FONT_SHEET_COLUMNS, fg=STEEL_WHITE, bg=SHADOW_INDEX), palette)
    _save_preview(os.path.join(outdir, BACKDROP_PREVIEW), assets.backdrop, palette)
    write_pi1(os.path.join(outdir, "hudscr.pi1"), assets.backdrop, palette)

    pak = build_pak(resources)
    with open(os.path.join(outdir, "demo.pak"), "wb") as handle:
        handle.write(pak)
    return assets, resources


def compression_report(outdir: str) -> str:
    """Per-resource packed/raw sizes -- the numbers the REPORT quotes."""
    with open(os.path.join(outdir, "demo.pak"), "rb") as handle:
        entries = read_pak_directory(handle.read())
    lines = [f"{'resource':10s} {'raw':>7s} {'packed':>7s} {'ratio':>6s}  method"]
    total_raw = total_packed = 0
    for entry in entries:
        method = "lzss" if entry.method else "stored"
        lines.append(f"{entry.name:10s} {entry.raw_len:7d} {entry.packed_len:7d} {entry.ratio:6.3f}  {method}")
        total_raw += entry.raw_len
        total_packed += entry.packed_len
    lines.append(f"{'TOTAL':10s} {total_raw:7d} {total_packed:7d} {total_packed / total_raw:6.3f}")
    return "\n".join(lines)


def _check_backdrop_indices_are_drawable(backdrop: np.ndarray) -> None:
    """The backdrop ships as 4-bitplane data with no mask, so every index must be paintable.

    An index outside 0..15 cannot be encoded at all, and the transparency key would punch a
    hole through the HUD wherever it leaked in from a generator.
    """
    used = sorted(set(np.unique(backdrop).tolist()))
    illegal = [index for index in used if not 0 <= index < PALETTE_SIZE or index == TRANSPARENT_INDEX]
    if illegal:
        raise AssertionError(f"demo backdrop uses indices {illegal}, which the HUD layer cannot draw")


def _check_saved_preview_is_palettised(outdir: str, palette: StePalette) -> None:
    """Read the written PNG back and audit its RGB against the palette.

    Checking the in-memory indices could not fail -- they are palette indices by construction.
    The PNG has been through indices_to_rgb, an upscale and an encoder, so this is the first
    point where a real defect (a wrong palette, a lossy save) could show up.
    """
    with Image.open(os.path.join(outdir, BACKDROP_PREVIEW)) as preview:
        report = check_palettized(preview, palette)
    if not report.clean:
        raise AssertionError(f"{BACKDROP_PREVIEW} is not palettised:\n{report.describe()}")


def main(outdir: str = "out") -> None:
    """Entry point: build the demo set, then verify what was written to disk."""
    assets, resources = write_demo(outdir)
    _check_backdrop_indices_are_drawable(assets.backdrop)
    _check_saved_preview_is_palettised(outdir, assets.palette)
    print(f"wrote {len(resources)} resources to {outdir}/")
    print(compression_report(outdir))


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "out")
