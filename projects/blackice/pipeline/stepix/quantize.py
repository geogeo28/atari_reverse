"""Map arbitrary RGB art onto a fixed 16-colour STE palette, and audit art that claims to
already be palettised.

Two jobs, both needed by the build:
  * `quantize_image` -- for photographic or anti-aliased source art, with optional ordered
    dither. Ordered (Bayer) rather than error-diffusion because a dithered wall texture is
    tiled and scaled by the raycaster: error diffusion's noise does not tile, so seams show
    at every texture repeat, whereas an ordered pattern repeats with the tile.
  * `check_palettized` -- for art authored against the palette (our procedural textures).
    A single stray colour there is a silent bug: quantisation would "fix" it and nobody
    would notice the artist's intent was lost. This reports instead of fixing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .colourspace import RGB888_MAX, nearest_lab_index
from .palette import PALETTE_SIZE, RGB888_PER_STEP, StePalette

RGB_CHANNELS = 3
BITS_PER_CHANNEL = 8            # one 0..255 channel per byte of a packed RGB key

# Bayer threshold matrices, values 0..n*n-1. Normalised to a signed offset before use.
BAYER_2X2 = np.array([[0, 2],
                      [3, 1]], dtype=np.float64)
BAYER_4X4 = np.array([[0, 8, 2, 10],
                      [12, 4, 14, 6],
                      [3, 11, 1, 9],
                      [15, 7, 13, 5]], dtype=np.float64)
DITHER_MATRICES = {"bayer2": BAYER_2X2, "bayer4": BAYER_4X4}

# A dither offset spanning roughly one palette step is what trades banding for texture
# without visibly greying the image -- so it is that step, not a copy of its value.
DEFAULT_DITHER_STRENGTH = float(RGB888_PER_STEP)

MAX_REPORTED_OFFENDERS = 16     # a report is for a human: list the worst few, count the rest


def _as_rgb_array(image: Image.Image | np.ndarray) -> np.ndarray:
    """Accept a PIL image or an (h, w, 3) array; always return (h, w, 3) float64 0..255."""
    if isinstance(image, Image.Image):
        array = np.asarray(image.convert("RGB"), dtype=np.float64)
    else:
        array = np.asarray(image, dtype=np.float64)
    if array.ndim != 3 or array.shape[2] != RGB_CHANNELS:
        raise ValueError(f"expected an (h, w, 3) RGB image, got shape {array.shape}")
    return array


def _dither_offsets(matrix: np.ndarray, height: int, width: int, strength: float) -> np.ndarray:
    """Tile a Bayer matrix over the image as a zero-mean offset in 8-bit level units."""
    levels = matrix.size
    normalised = (matrix + 0.5) / levels - 0.5          # centre on zero: -0.5 .. +0.5
    tiles = np.tile(normalised, (height // matrix.shape[0] + 1, width // matrix.shape[1] + 1))
    return tiles[:height, :width, None] * strength


def palette_lookup(colours: np.ndarray, palette: StePalette) -> np.ndarray:
    """Nearest palette index for an (n, 3) array of 0..255 RGB colours, matched in Lab."""
    return nearest_lab_index(np.asarray(colours, dtype=np.float64), palette.to_lab())


def quantize_image(image: Image.Image | np.ndarray, palette: StePalette, dither: str | None = None,
                   strength: float = DEFAULT_DITHER_STRENGTH) -> np.ndarray:
    """Quantise RGB art to palette indices. Returns (h, w) uint8 with values 0..15.

    Unique colours are matched once and reused: procedural art has a handful of distinct
    colours, so the Lab search runs over tens of colours rather than tens of thousands of
    pixels. Dithering is applied before the search, so the offsets have to be quantised too
    -- the cache key is the offset colour, not the source colour.
    """
    rgb = _as_rgb_array(image)
    if dither is not None:
        if dither not in DITHER_MATRICES:
            raise ValueError(f"unknown dither {dither!r}; expected one of {sorted(DITHER_MATRICES)} or None")
        rgb = rgb + _dither_offsets(DITHER_MATRICES[dither], rgb.shape[0], rgb.shape[1], strength)
    flat = np.clip(np.rint(rgb.reshape(-1, RGB_CHANNELS)), 0, RGB888_MAX).astype(np.uint8)
    unique, inverse = np.unique(flat, axis=0, return_inverse=True)
    return palette_lookup(unique, palette)[inverse].astype(np.uint8).reshape(rgb.shape[:2])


def indices_to_rgb(indices: np.ndarray, palette: StePalette) -> np.ndarray:
    """Expand palette indices back to an (h, w, 3) uint8 RGB image for PNG previews."""
    idx = np.asarray(indices)
    if idx.dtype != np.uint8:
        idx = idx.astype(np.uint8)
    if idx.size and int(idx.max()) >= PALETTE_SIZE:
        raise ValueError(f"index {int(idx.max())} is outside the {PALETTE_SIZE}-colour palette")
    return palette.to_rgb888()[idx]


@dataclass
class PaletteReport:
    """Result of auditing supposedly-palettised art against a palette."""

    total_pixels: int
    off_palette_pixels: int
    offenders: list[tuple[tuple[int, int, int], int, tuple[int, int]]] = field(default_factory=list)
    distinct_offending_colours: int = 0

    @property
    def clean(self) -> bool:
        return self.off_palette_pixels == 0

    def describe(self) -> str:
        """One-line-per-offender summary; the first line alone answers 'is this art legal?'."""
        head = (f"{self.off_palette_pixels}/{self.total_pixels} pixels off-palette "
                f"({self.distinct_offending_colours} distinct colours)")
        lines = [head if not self.clean else f"clean: all {self.total_pixels} pixels are palette colours"]
        for colour, count, (row, col) in self.offenders:
            lines.append(f"  rgb{colour} x{count}, first at y={row} x={col}")
        if self.distinct_offending_colours > len(self.offenders):
            lines.append(f"  ... and {self.distinct_offending_colours - len(self.offenders)} more colours")
        return "\n".join(lines)


def _rgb_keys(rgb: np.ndarray) -> np.ndarray:
    """Pack (n, 3) 0..255 channels into one int32 key each, so matching is a 1-D set test."""
    return (rgb[:, 0] << 2 * BITS_PER_CHANNEL) | (rgb[:, 1] << BITS_PER_CHANNEL) | rgb[:, 2]


def check_palettized(image: Image.Image | np.ndarray, palette: StePalette) -> PaletteReport:
    """Report pixels whose exact RGB is not a palette colour (no tolerance, no fixing).

    Matching is done on packed keys rather than by broadcasting the pixels against all 16
    palette colours: the broadcast allocates an (n, 16, 3) scratch array, which is 50 MB on a
    1024x1024 image for a test that only ever needs a set membership.
    """
    rgb = _as_rgb_array(image)
    flat = np.rint(rgb.reshape(-1, RGB_CHANNELS)).astype(np.int32)
    # A channel outside 0..255 cannot be a palette colour, and would corrupt the packed key
    # by carrying into the neighbouring channel's bits: mark it off-palette before packing.
    in_range = ((flat >= 0) & (flat <= RGB888_MAX)).all(axis=1)
    matches = np.zeros(flat.shape[0], dtype=bool)
    matches[in_range] = np.isin(_rgb_keys(flat[in_range]), _rgb_keys(palette.to_rgb888().astype(np.int32)))

    bad_positions = np.flatnonzero(~matches)
    report = PaletteReport(total_pixels=int(flat.shape[0]), off_palette_pixels=int(bad_positions.size))
    if bad_positions.size == 0:
        return report

    # Grouped on the colour rows, not the keys: an out-of-range channel has no valid key, and
    # collapsing every such pixel onto one would under-report the distinct offenders.
    bad_colours, first_seen, counts = np.unique(flat[bad_positions], axis=0, return_index=True, return_counts=True)
    report.distinct_offending_colours = int(bad_colours.shape[0])
    width = rgb.shape[1]
    for rank in np.argsort(-counts, kind="stable")[:MAX_REPORTED_OFFENDERS]:
        first = int(bad_positions[first_seen[rank]])
        report.offenders.append((tuple(int(c) for c in bad_colours[rank]), int(counts[rank]), (first // width, first % width)))
    return report
