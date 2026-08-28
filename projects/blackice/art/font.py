"""The HUD/title font for the concept-art package - the engine's font, not a second one.

There were two independent 8x8 fonts in this project: this file used to carry 64 hand-drawn
glyphs on a 7-pixel advance, while `pipeline/stepix/font.py` carries 96 (ASCII 32..127) and is
the one the 68000 build actually consumes as 768 bytes of 1-bitplane glyph rows.  Concept art
that measures its own layouts against a font the machine will never load is concept art that
lies about how much room the HUD has, so this module is now a thin adapter over stepix's table.

Metrics come from stepix and are not re-chosen here: an 8x8 cell, art drawn on 5x7 inside it,
and an advance of a full cell (`FONT_CHAR_W`), which is the step `stepix.font.render_text`
uses.  That is three blank columns between characters, against the one this package assumed
before, so every string is ~14% wider than in Revision 2 and the HUD was re-laid to match.
"""

import os
import sys

import numpy as np

_PIPELINE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "pipeline")
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)

from stepix import font as stepix_font                                    # noqa: E402

GLYPH_WIDTH = stepix_font.FONT_CHAR_W
GLYPH_HEIGHT = stepix_font.FONT_CHAR_H
#: One full cell per character - stepix.font.render_text's own step, and so the engine's.
ADVANCE = stepix_font.FONT_CHAR_W
#: The authoring table, for anything that wants to count or inspect glyphs.
FONT = stepix_font.GLYPH_ART
GLYPH_COUNT = stepix_font.FONT_CHAR_COUNT
#: What the .PRG carries: one byte per glyph row, 96 glyphs.  The ledger figure.
FONT_BYTES = stepix_font.FONT_BYTES
#: stepix substitutes a hollow box for anything in range without art of its own.
MISSING_GLYPH = "?"

_MSB = stepix_font.MSB_BIT


def glyph_mask(character):
    """8x8 boolean ink mask for one character.  Out-of-range characters fall back visibly."""
    try:
        rows = stepix_font.glyph_rows(character)
    except ValueError:
        rows = stepix_font.glyph_rows(MISSING_GLYPH)
    mask = np.zeros((GLYPH_HEIGHT, GLYPH_WIDTH), dtype=bool)
    for row, bits in enumerate(rows):
        for column in range(GLYPH_WIDTH):
            mask[row, column] = bool(bits & (1 << (_MSB - column)))
    return mask


def text_width(text, advance=ADVANCE):
    return len(text) * advance


def text_mask(text, advance=ADVANCE):
    """The whole string as one ink mask, shape (8, text_width)."""
    mask = np.zeros((GLYPH_HEIGHT, max(text_width(text, advance), 1)), dtype=bool)
    for index, character in enumerate(text):
        left = index * advance
        mask[:, left:left + GLYPH_WIDTH] |= glyph_mask(character)[:, :mask.shape[1] - left]
    return mask


def draw_text(canvas, x, y, text, ink, advance=ADVANCE):
    """Paint only the ink pixels onto a canvas exposing pixel(x, y, index).  Returns the pen."""
    mask = text_mask(text, advance)
    for row in range(mask.shape[0]):
        for column in range(mask.shape[1]):
            if mask[row, column]:
                canvas.pixel(x + column, y + row, ink)
    return x + text_width(text, advance)


def draw_text_shadow(canvas, x, y, text, ink, shadow, advance=ADVANCE):
    draw_text(canvas, x + 1, y + 1, text, shadow, advance)
    return draw_text(canvas, x, y, text, ink, advance)


SAMPLES = ("BLACK ICE", "INTEGRITY 100%", "CYC 048", "TRACE 73%", "SECTOR 7: COLD STORE",
           "0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def main():
    print("font: %d glyphs, %dx%d cell, advance %d, %d bytes on target (stepix table)"
          % (GLYPH_COUNT, GLYPH_WIDTH, GLYPH_HEIGHT, ADVANCE, FONT_BYTES))
    for sample in SAMPLES:
        print()
        print("  %s  (%d px)" % (sample, text_width(sample)))
        for row in text_mask(sample):
            print("  " + "".join("#" if cell else " " for cell in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
