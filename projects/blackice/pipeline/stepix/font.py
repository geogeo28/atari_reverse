"""8x8, 1-bitplane bitmap font for the STE raycaster HUD.

The 68000 engine blits glyphs as raw bytes, one byte per pixel row, bit 7 = the
leftmost pixel. That is exactly the 1-bitplane layout the ST's blitter and the
classic `move.b (a0)+,d0 / roxl` software span loops expect, so `font_bytes()`
can be written straight into the .PRG image with no repacking on target.

Glyph shapes are authored here as ASCII art (`#` = ink) rather than as hex
tables, because a hex table is unreviewable: a wrong nibble in a hand-typed
0x7E is invisible, a wrong pixel in the art is not.

Cell geometry: every glyph is drawn on a 5x7 grid and padded programmatically to
the 8x8 cell, leaving a blank rightmost 3 columns and bottom row. Keeping the
gap structural (rather than typed into each art literal) guarantees that
adjacent characters and stacked lines can never touch, and keeps the art
literals short enough to scan a whole row of the table at once.

Lowercase: a-z deliberately render the UPPERCASE glyphs. This is a design
choice, not a gap. The HUD vocabulary ("AMMO", "HEALTH", score digits) is
uppercase-only, and a 5x7 cell has no room for the descenders that make real
lowercase legible; aliasing means a caller passing "Ammo" gets readable output
instead of 26 placeholder boxes. Any other character that has no art falls back
to PLACEHOLDER_ART (a hollow box) so a bad string degrades visibly rather than
raising.
"""

from __future__ import annotations

import numpy as np

# --- Public format constants (mirrored by the engine's asm equates) -----------

FONT_CHAR_W = 8
FONT_CHAR_H = 8
FONT_FIRST_CHAR = 32  # ASCII space
FONT_CHAR_COUNT = 96  # 32..127 inclusive
FONT_BYTES_PER_GLYPH = 8  # one byte per row, bit 7 = leftmost pixel
FONT_BYTES = FONT_CHAR_COUNT * FONT_BYTES_PER_GLYPH  # 768

FONT_LAST_CHAR = FONT_FIRST_CHAR + FONT_CHAR_COUNT - 1  # 127

# --- Authoring constants -----------------------------------------------------

INK = "#"
"""The character that marks a lit pixel in the art table below."""

GLYPH_ART_W = 5
GLYPH_ART_H = 7
"""Drawable area inside the cell; the remaining columns/rows are the blank gap."""

MSB_BIT = FONT_CHAR_W - 1
"""Shift for column 0, i.e. bit 7 -- the leftmost pixel of a row byte."""

MAX_COLOR_INDEX = 255
"""Rendered arrays are uint8 palette indices; anything wider would wrap silently."""

DEFAULT_INK_INDEX = 1
"""Ink used when a caller does not pick one. Deliberately NOT 15: that index is the sprite
and HUD transparency key, so text rendered in it is punched straight back out by the blit --
the default has to be a colour that survives being drawn."""

# --- Glyph art ---------------------------------------------------------------
# Each entry is GLYPH_ART_H lines of at most GLYPH_ART_W columns. Short lines and
# missing trailing lines are padded with background, so a blank row may be "".

PLACEHOLDER_ART = (
    "#####",
    "#...#",
    "#...#",
    "#...#",
    "#...#",
    "#...#",
    "#####",
)
"""Hollow box drawn for any character in range that has no art of its own."""

GLYPH_ART: dict[str, tuple[str, ...]] = {
    " ": (),
    "!": (
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        ".....",
        "..#..",
    ),
    '"': (
        ".#.#.",
        ".#.#.",
    ),
    "#": (
        ".#.#.",
        ".#.#.",
        "#####",
        ".#.#.",
        "#####",
        ".#.#.",
        ".#.#.",
    ),
    "$": (
        "..#..",
        ".####",
        "#.#..",
        ".###.",
        "..#.#",
        "####.",
        "..#..",
    ),
    "%": (
        "##..#",
        "##..#",
        "...#.",
        "..#..",
        ".#...",
        "#..##",
        "#..##",
    ),
    "&": (
        ".##..",
        "#..#.",
        "#..#.",
        ".##..",
        "#.#.#",
        "#..#.",
        ".##.#",
    ),
    "'": (
        "..#..",
        "..#..",
    ),
    "(": (
        "...#.",
        "..#..",
        ".#...",
        ".#...",
        ".#...",
        "..#..",
        "...#.",
    ),
    ")": (
        ".#...",
        "..#..",
        "...#.",
        "...#.",
        "...#.",
        "..#..",
        ".#...",
    ),
    "*": (
        ".....",
        "..#..",
        "#.#.#",
        ".###.",
        "#.#.#",
        "..#..",
    ),
    "+": (
        ".....",
        "..#..",
        "..#..",
        "#####",
        "..#..",
        "..#..",
    ),
    ",": (
        ".....",
        ".....",
        ".....",
        ".....",
        ".##..",
        ".##..",
        ".#...",
    ),
    "-": (
        ".....",
        ".....",
        ".....",
        "#####",
    ),
    ".": (
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".##..",
        ".##..",
    ),
    "/": (
        "....#",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#....",
        "#....",
    ),
    "0": (
        ".###.",
        "#...#",
        "#..##",
        "#.#.#",
        "##..#",
        "#...#",
        ".###.",
    ),
    "1": (
        "..#..",
        ".##..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        ".###.",
    ),
    "2": (
        ".###.",
        "#...#",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#####",
    ),
    "3": (
        "#####",
        "...#.",
        "..#..",
        "...#.",
        "....#",
        "#...#",
        ".###.",
    ),
    "4": (
        "...#.",
        "..##.",
        ".#.#.",
        "#..#.",
        "#####",
        "...#.",
        "...#.",
    ),
    "5": (
        "#####",
        "#....",
        "####.",
        "....#",
        "....#",
        "#...#",
        ".###.",
    ),
    "6": (
        "..##.",
        ".#...",
        "#....",
        "####.",
        "#...#",
        "#...#",
        ".###.",
    ),
    "7": (
        "#####",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        ".#...",
        ".#...",
    ),
    "8": (
        ".###.",
        "#...#",
        "#...#",
        ".###.",
        "#...#",
        "#...#",
        ".###.",
    ),
    "9": (
        ".###.",
        "#...#",
        "#...#",
        ".####",
        "....#",
        "...#.",
        ".##..",
    ),
    ":": (
        ".....",
        ".##..",
        ".##..",
        ".....",
        ".##..",
        ".##..",
    ),
    ";": (
        ".....",
        ".##..",
        ".##..",
        ".....",
        ".##..",
        ".##..",
        ".#...",
    ),
    "<": (
        "...#.",
        "..#..",
        ".#...",
        "#....",
        ".#...",
        "..#..",
        "...#.",
    ),
    "=": (
        ".....",
        ".....",
        "#####",
        ".....",
        "#####",
    ),
    ">": (
        ".#...",
        "..#..",
        "...#.",
        "....#",
        "...#.",
        "..#..",
        ".#...",
    ),
    "?": (
        ".###.",
        "#...#",
        "....#",
        "...#.",
        "..#..",
        ".....",
        "..#..",
    ),
    "@": (
        ".###.",
        "#...#",
        "#.###",
        "#.#.#",
        "#.###",
        "#....",
        ".###.",
    ),
    "A": (
        ".###.",
        "#...#",
        "#...#",
        "#####",
        "#...#",
        "#...#",
        "#...#",
    ),
    "B": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#...#",
        "#...#",
        "####.",
    ),
    "C": (
        ".###.",
        "#...#",
        "#....",
        "#....",
        "#....",
        "#...#",
        ".###.",
    ),
    "D": (
        "####.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "####.",
    ),
    "E": (
        "#####",
        "#....",
        "#....",
        "####.",
        "#....",
        "#....",
        "#####",
    ),
    "F": (
        "#####",
        "#....",
        "#....",
        "####.",
        "#....",
        "#....",
        "#....",
    ),
    "G": (
        ".###.",
        "#...#",
        "#....",
        "#.###",
        "#...#",
        "#...#",
        ".###.",
    ),
    "H": (
        "#...#",
        "#...#",
        "#...#",
        "#####",
        "#...#",
        "#...#",
        "#...#",
    ),
    "I": (
        ".###.",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        ".###.",
    ),
    "J": (
        "..###",
        "...#.",
        "...#.",
        "...#.",
        "...#.",
        "#..#.",
        ".##..",
    ),
    "K": (
        "#...#",
        "#..#.",
        "#.#..",
        "##...",
        "#.#..",
        "#..#.",
        "#...#",
    ),
    "L": (
        "#....",
        "#....",
        "#....",
        "#....",
        "#....",
        "#....",
        "#####",
    ),
    "M": (
        "#...#",
        "##.##",
        "#.#.#",
        "#.#.#",
        "#...#",
        "#...#",
        "#...#",
    ),
    "N": (
        "#...#",
        "##..#",
        "#.#.#",
        "#..##",
        "#...#",
        "#...#",
        "#...#",
    ),
    "O": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "P": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#....",
        "#....",
        "#....",
    ),
    "Q": (
        ".###.",
        "#...#",
        "#...#",
        "#...#",
        "#.#.#",
        "#..#.",
        ".##.#",
    ),
    "R": (
        "####.",
        "#...#",
        "#...#",
        "####.",
        "#.#..",
        "#..#.",
        "#...#",
    ),
    "S": (
        ".####",
        "#....",
        "#....",
        ".###.",
        "....#",
        "....#",
        "####.",
    ),
    "T": (
        "#####",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "U": (
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".###.",
    ),
    "V": (
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
    ),
    "W": (
        "#...#",
        "#...#",
        "#...#",
        "#.#.#",
        "#.#.#",
        "##.##",
        "#...#",
    ),
    "X": (
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
        ".#.#.",
        "#...#",
        "#...#",
    ),
    "Y": (
        "#...#",
        "#...#",
        ".#.#.",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "Z": (
        "#####",
        "....#",
        "...#.",
        "..#..",
        ".#...",
        "#....",
        "#####",
    ),
    "[": (
        ".###.",
        ".#...",
        ".#...",
        ".#...",
        ".#...",
        ".#...",
        ".###.",
    ),
    "\\": (
        "#....",
        "#....",
        ".#...",
        "..#..",
        "...#.",
        "....#",
        "....#",
    ),
    "]": (
        ".###.",
        "...#.",
        "...#.",
        "...#.",
        "...#.",
        "...#.",
        ".###.",
    ),
    "^": (
        "..#..",
        ".#.#.",
        "#...#",
    ),
    "_": (
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        "#####",
    ),
    "`": (
        ".#...",
        "..#..",
    ),
    "{": (
        "...##",
        "..#..",
        "..#..",
        ".#...",
        "..#..",
        "..#..",
        "...##",
    ),
    "|": (
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    ),
    "}": (
        "##...",
        "..#..",
        "..#..",
        "...#.",
        "..#..",
        "..#..",
        "##...",
    ),
    "~": (
        ".....",
        ".....",
        ".#..#",
        "#.#.#",
        "#..#.",
    ),
}


def _art_to_rows(art: tuple[str, ...]) -> list[int]:
    """Pack ASCII art into FONT_BYTES_PER_GLYPH row bytes, bit 7 = leftmost pixel.

    Lines shorter than the cell (and missing trailing lines) pad with background,
    which is what reserves the right/bottom gap between cells.
    """
    rows = []
    for y in range(FONT_CHAR_H):
        line = art[y] if y < len(art) else ""
        bits = 0
        for x, cell in enumerate(line[:FONT_CHAR_W]):
            if cell == INK:
                bits |= 1 << (MSB_BIT - x)
        rows.append(bits)
    return rows


def _validate_art_table() -> None:
    """Fail at import if any art literal overflows the drawable 5x7 area.

    A too-wide or too-tall literal would silently eat the inter-character gap and
    make HUD text touch, which is exactly the defect the gap exists to prevent.
    """
    for ch, art in GLYPH_ART.items():
        if len(art) > GLYPH_ART_H:
            raise ValueError(f"glyph {ch!r}: {len(art)} art lines exceeds {GLYPH_ART_H}")
        for line in art:
            if len(line) > GLYPH_ART_W:
                raise ValueError(f"glyph {ch!r}: line {line!r} exceeds {GLYPH_ART_W} columns")


_validate_art_table()


def _art_for(ch: str) -> tuple[str, ...]:
    """Resolve a character to its art, applying the lowercase->uppercase alias."""
    if ch in GLYPH_ART:
        return GLYPH_ART[ch]
    upper = ch.upper()
    if upper in GLYPH_ART:
        return GLYPH_ART[upper]
    return PLACEHOLDER_ART


# Built once at import so glyph_rows() and font_bytes() cannot disagree.
_GLYPH_TABLE: list[list[int]] = [
    _art_to_rows(_art_for(chr(FONT_FIRST_CHAR + index))) for index in range(FONT_CHAR_COUNT)
]


def glyph_rows(ch: str) -> list[int]:
    """8 row bytes for one character; bit 7 is the leftmost pixel.

    Raises ValueError outside ASCII 32..127: the font has no storage there, and
    silently substituting a box would hide a caller feeding it binary data.
    """
    if len(ch) != 1:
        raise ValueError(f"expected a single character, got {ch!r}")
    code = ord(ch)
    if not FONT_FIRST_CHAR <= code <= FONT_LAST_CHAR:
        raise ValueError(f"character {ch!r} (code {code}) is outside {FONT_FIRST_CHAR}..{FONT_LAST_CHAR}")
    return list(_GLYPH_TABLE[code - FONT_FIRST_CHAR])


def font_bytes() -> bytes:
    """The whole font as FONT_BYTES bytes: glyph N at N*8, N = ord(c) - FONT_FIRST_CHAR.

    Flat and index-addressable so the engine reaches a glyph with a shift and an
    add, never a lookup table.
    """
    return bytes(row for rows in _GLYPH_TABLE for row in rows)


def _check_color(name: str, value: int) -> None:
    """Reject palette indices that a uint8 array would wrap around silently."""
    if not 0 <= value <= MAX_COLOR_INDEX:
        raise ValueError(f"{name}={value} is outside 0..{MAX_COLOR_INDEX}")


def _paint_glyph(target: np.ndarray, top: int, left: int, rows: list[int], fg: int) -> None:
    """Stamp one glyph's ink pixels into an already background-filled array."""
    for y, bits in enumerate(rows):
        for x in range(FONT_CHAR_W):
            if bits & (1 << (MSB_BIT - x)):
                target[top + y, left + x] = fg


def render_text(text: str, fg: int = DEFAULT_INK_INDEX, bg: int = 0) -> np.ndarray:
    """Render one line to an indexed uint8 array of shape (8, 8*len(text)).

    Indexed rather than RGB because the STE HUD is palette-driven; the caller
    picks real colours when it writes the palette. Propagates glyph_rows()'s
    ValueError for characters outside 32..127.
    """
    _check_color("fg", fg)
    _check_color("bg", bg)
    image = np.full((FONT_CHAR_H, FONT_CHAR_W * len(text)), bg, dtype=np.uint8)
    for index, ch in enumerate(text):
        _paint_glyph(image, 0, index * FONT_CHAR_W, glyph_rows(ch), fg)
    return image


def font_sheet(columns: int = 16, fg: int = DEFAULT_INK_INDEX, bg: int = 0) -> np.ndarray:
    """All 96 glyphs laid out on a grid, indexed uint8 -- used for a PNG preview.

    The preview is the human check on the art table; 16 columns puts each ASCII
    row of 16 codes on its own sheet row, so a wrong glyph is easy to locate.
    """
    if columns < 1:
        raise ValueError(f"columns={columns} must be at least 1")
    _check_color("fg", fg)
    _check_color("bg", bg)
    sheet_rows = -(-FONT_CHAR_COUNT // columns)  # ceiling division
    sheet = np.full(
        (sheet_rows * FONT_CHAR_H, columns * FONT_CHAR_W),
        bg,
        dtype=np.uint8,
    )
    for index in range(FONT_CHAR_COUNT):
        row, column = divmod(index, columns)
        _paint_glyph(sheet, row * FONT_CHAR_H, column * FONT_CHAR_W, list(_GLYPH_TABLE[index]), fg)
    return sheet
