"""One sheet that answers every question an art director would ask about BLACK ICE.

Sections, top to bottom:
  1. the 16 palette registers with index and luminance
  2. every wall texture at all five depth bands - the fog is an index remap, shown as one
  3. the rim-light readability grid: every rimmed sprite over every wall at band 0 (the worst
     case the harness finds), each cell rule-marked green for pass and orange for fail
  4. the HUD strip
  5. the three 320x200 mockups
"""

import numpy as np

import drawlib
import font
import hud
import keyart
import palette
import pixelio
import rimtest
import sprites
import textures
from drawlib import Canvas

SHEET_WIDTH = 1000
MARGIN = 8
LINE = font.GLYPH_HEIGHT
TITLE_GAP = 4
SECTION_GAP = 14
CELL = textures.TEX_SIZE
CELL_PITCH = CELL + 2
LABEL_WIDTH = 132
#: Sized against font.ADVANCE so a label cannot run into the cell beside it.
LABEL_CHARS = LABEL_WIDTH // font.ADVANCE
HEADER_CHARS = (CELL_PITCH - font.ADVANCE) // font.ADVANCE
AGREEMENT_NAME_CHARS = 13
SWATCH_WIDTH, SWATCH_HEIGHT = 46, 34
SWATCH_PITCH = 50
PASS_RULE_HEIGHT = 2
MOCKUP_PITCH = hud.SCREEN_WIDTH + 8
#: Band 0 is where rimtest finds every worst case, so that is the band the grid shows.
RIM_GRID_BAND = 0
SHEET_HEIGHT = 1700


def _title(canvas, y, text):
    hud.draw_text(canvas, MARGIN, y, text, palette.CYAN_1)
    canvas.hline(y + LINE, MARGIN, SHEET_WIDTH - MARGIN, palette.CYAN_5, thickness=1)
    return y + LINE + TITLE_GAP


def _palette_section(canvas, y):
    y = _title(canvas, y, "1. PALETTE - 16 REGISTERS, EVERY CHANNEL A MULTIPLE OF 0X11")
    for entry in palette.PALETTE:
        x = MARGIN + entry.index * SWATCH_PITCH
        canvas.rect(x, y, x + SWATCH_WIDTH - 1, y + SWATCH_HEIGHT - 1, entry.index)
        canvas.outline_rect(x, y, x + SWATCH_WIDTH - 1, y + SWATCH_HEIGHT - 1, palette.GRID)
        reserved = "*" if entry.index in palette.SPRITE_ONLY else " "
        hud.draw_text(canvas, x + 2, y + SWATCH_HEIGHT + 2, "%02d%s" % (entry.index, reserved),
                      palette.RIM)
        hud.draw_text(canvas, x + 2, y + SWATCH_HEIGHT + 2 + LINE,
                      "%3d" % round(palette.luminance(entry.index)), palette.CYAN_3)
    hud.draw_text(canvas, MARGIN, y + SWATCH_HEIGHT + 2 + LINE * 2 + 2,
                  "* = RESERVED SPRITE/HUD ONLY - NO WALL TEXTURE MAY CONTAIN IT",
                  palette.DATA)
    return y + SWATCH_HEIGHT + LINE * 3 + 6 + SECTION_GAP


def _texture_band_section(canvas, y, tiles):
    y = _title(canvas, y, "2. WALL TEXTURES AT FIVE DEPTH BANDS - FOG IS AN INDEX REMAP")
    for band in range(palette.DEPTH_BANDS):
        hud.draw_text(canvas, MARGIN + LABEL_WIDTH + band * CELL_PITCH + 16, y,
                      "BAND %d" % band, palette.CYAN_2)
    y += LINE + 2
    for row, (name, array) in enumerate(tiles.items()):
        cell_y = y + row * CELL_PITCH
        hud.draw_text(canvas, MARGIN, cell_y + CELL // 2 - LINE // 2, name.upper()[:LABEL_CHARS],
                      palette.CYAN_3)
        for band in range(palette.DEPTH_BANDS):
            canvas.blit(drawlib.shade(array, band),
                        MARGIN + LABEL_WIDTH + band * CELL_PITCH, cell_y)
    _agreement_table(canvas, _sprite_gallery(canvas, y) + SECTION_GAP, tiles)
    return y + len(tiles) * CELL_PITCH + SECTION_GAP


GALLERY_X = MARGIN + LABEL_WIDTH + palette.DEPTH_BANDS * CELL_PITCH + 24
GALLERY_ROWS = (("ENEMIES - 64X64, INDEX 15 TRANSPARENT, 1-PX WHITE RIM",
                 ("watchdog", "sentry", "tracer", "black_ice")),
                ("PICKUPS - 32X32, AND THE 16X16 DATA PARTICLE",
                 ("cycles_cell", "integrity_patch", "access_token", "trace_scrubber",
                  "data_particle")),
                ("WEAPONS - 96X48, BOTTOM CENTRE OF THE 160X80 WINDOW",
                 ("buster_idle", "buster_firing")),
                ("", ("spike_idle", "spike_firing")))
GALLERY_GAP = 6


def _sprite_gallery(canvas, y):
    """Everything sprites.py builds, on the slate the wall textures leave empty."""
    built = sprites.build_all()
    hud.draw_text(canvas, GALLERY_X, y, "SPRITE SHEET", palette.CYAN_1)
    y += LINE + TITLE_GAP
    for caption, names in GALLERY_ROWS:
        if caption:
            hud.draw_text(canvas, GALLERY_X, y, caption, palette.CYAN_3)
            y += LINE + 2
        x = GALLERY_X
        row_height = 0
        for name in names:
            art = built[name]
            canvas.rect(x, y, x + art.shape[1] - 1, y + art.shape[0] - 1, palette.CYAN_5)
            canvas.blit(art, x, y, key=sprites.KEY)
            x += art.shape[1] + GALLERY_GAP
            row_height = max(row_height, art.shape[0])
        y += row_height + GALLERY_GAP
    return y


AGREEMENT_ROWS_SHOWN = 5


def _agreement_table(canvas, y, tiles):
    """The measured answer to 'do these read as different materials at distance?'"""
    hud.draw_text(canvas, GALLERY_X, y, "BAND AGREEMENT - IDENTICAL PIXELS AT WALL SIZE",
                  palette.CYAN_1)
    y += LINE + TITLE_GAP
    for band in textures.AGREEMENT_GATE_BANDS:
        rows = textures.agreement_pairs(band, tiles)
        hud.draw_text(canvas, GALLERY_X, y, "BAND %d (%d ROWS) - WORST %d OF %d PAIRS, GATE %d%%"
                      % (band, textures.BAND_SAMPLE_ROWS[band], AGREEMENT_ROWS_SHOWN, len(rows),
                         int(textures.MAX_BAND_AGREEMENT * 100)), palette.CYAN_3)
        y += LINE + 1
        for agreement, name_a, name_b in rows[:AGREEMENT_ROWS_SHOWN]:
            failed = agreement > textures.MAX_BAND_AGREEMENT
            hud.draw_text(canvas, GALLERY_X + 8, y, "%4.1f%% %s / %s"
                          % (agreement * 100, name_a.upper()[:AGREEMENT_NAME_CHARS], name_b.upper()[:AGREEMENT_NAME_CHARS]),
                          palette.ALERT if failed else palette.INTEGRITY)
            y += LINE + 1
        y += 3
    return y


def _rim_cell(sprite, wall):
    """One grid cell: the sprite centred on its own patch of tiled, shaded wall."""
    background = rimtest.tiled_wall(drawlib.shade(wall, RIM_GRID_BAND), (CELL, CELL))
    canvas = Canvas.from_array(background)
    shaded = drawlib.shade_sprite(sprite, RIM_GRID_BAND, sprites.KEY)
    canvas.blit(shaded, (CELL - sprite.shape[1]) // 2, (CELL - sprite.shape[0]) // 2,
                key=sprites.KEY)
    return canvas.array


def _rim_section(canvas, y, tiles):
    y = _title(canvas, y, "3. RIM-LIGHT TEST - EVERY SPRITE ON EVERY WALL AT BAND %d "
                          "- RULE MARK = COVERAGE 100%% AND MARGIN" % RIM_GRID_BAND)
    wall_names = list(tiles)
    for column, name in enumerate(wall_names):
        hud.draw_text(canvas, MARGIN + LABEL_WIDTH + column * CELL_PITCH, y,
                      name.upper()[:HEADER_CHARS], palette.CYAN_2)
    y += LINE + 2
    for row, (sprite_name, sprite) in enumerate(rimtest.rimmed_sprites()):
        cell_y = y + row * (CELL_PITCH + PASS_RULE_HEIGHT)
        hud.draw_text(canvas, MARGIN, cell_y + CELL // 2 - LINE // 2, sprite_name.upper()[:LABEL_CHARS],
                      palette.CYAN_3)
        for column, wall_name in enumerate(wall_names):
            cell_x = MARGIN + LABEL_WIDTH + column * CELL_PITCH
            canvas.blit(_rim_cell(sprite, tiles[wall_name]), cell_x, cell_y)
            coverage, margin, _ = rimtest.measure(sprite, tiles[wall_name], RIM_GRID_BAND)
            passed = (coverage >= rimtest.REQUIRED_COVERAGE
                      and margin >= rimtest.MIN_RIM_MARGIN)
            canvas.rect(cell_x, cell_y + CELL, cell_x + CELL - 1,
                        cell_y + CELL + PASS_RULE_HEIGHT - 1,
                        palette.INTEGRITY if passed else palette.ALERT)
            if not passed:
                hud.draw_text(canvas, cell_x + 2, cell_y + 2, "FAIL", palette.ALERT)
    rows = len(rimtest.rimmed_sprites())
    return y + rows * (CELL_PITCH + PASS_RULE_HEIGHT) + SECTION_GAP


def _hud_section(canvas, y):
    y = _title(canvas, y, "4. HUD STRIP - 320X40 PLANAR, BOTTOM 40 SCANLINES, WORLD PALETTE")
    canvas.blit(hud.draw_hud(), MARGIN, y)
    return y + hud.HUD_HEIGHT + SECTION_GAP


def _mockup_section(canvas, y):
    y = _title(canvas, y, "5. MOCKUPS - 320X200, RAYCAST FROM THESE ASSETS")
    for index, (name, builder) in enumerate(keyart.MOCKUPS):
        canvas.blit(builder(), MARGIN + index * MOCKUP_PITCH, y)
        hud.draw_text(canvas, MARGIN + index * MOCKUP_PITCH, y + hud.SCREEN_HEIGHT + 2,
                      name.upper().replace("_", " "), palette.CYAN_2)
    return y + hud.SCREEN_HEIGHT + LINE + SECTION_GAP


def build_sheet():
    canvas = Canvas(SHEET_WIDTH, SHEET_HEIGHT, palette.VOID)
    tiles = textures.build_all()
    y = _title(canvas, MARGIN, "BLACK ICE - CONCEPT ART CONTACT SHEET - ATARI STE, 320X200, 16 COLOURS")
    y = _palette_section(canvas, y)
    y = _texture_band_section(canvas, y, tiles)
    y = _rim_section(canvas, y, tiles)
    y = _hud_section(canvas, y)
    y = _mockup_section(canvas, y)
    return canvas.array[:y], y


def main():
    pixelio.ensure_dirs()
    array, used_height = build_sheet()
    path = pixelio.save_preview_only(array, "contact_sheet", scale=1)
    results = rimtest.run()
    print("contact sheet %dx%d -> %s" % (array.shape[1], array.shape[0], path))
    print("rim-light grid: %d cells drawn at band %d; harness: %d combinations, "
          "%d coverage failures, %d margin failures"
          % (len(rimtest.rimmed_sprites()) * len(textures.ALL_BUILDERS), RIM_GRID_BAND,
             len(results), len(rimtest.coverage_failures(results)),
             len(rimtest.margin_failures(results))))
    if used_height > SHEET_HEIGHT:
        print("WARNING: sheet content %d px exceeded the %d px canvas" % (used_height, SHEET_HEIGHT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
