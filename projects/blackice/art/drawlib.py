"""Indexed-pixel drawing primitives for BLACK ICE art scripts.

Every asset in this package is a numpy uint8 array of PALETTE indices - never RGB.  That is
the same representation the STE renderer works in (a chunky nibble/byte buffer), so what the
scripts draw is what the c2p pass will convert.

Vector primitives are rasterised through a PIL mask rather than hand-rolled scanline code:
PIL owns the polygon/ellipse maths, we own the palette.  Canvas stays numpy-backed so the
procedural passes (grid drift, torn glyphs, depth remaps) are plain array work.
"""

import numpy as np
from PIL import Image, ImageDraw

import palette

MASK_MODE = "L"
MASK_OFF, MASK_ON = 0, 1
DEFAULT_LINE_WIDTH = 1
#: 8-connected structuring element - a 1-px rim must cover diagonal edges or it leaks at 2x2.
NEIGHBOUR_OFFSETS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


class Canvas:
    """A rectangle of palette indices with drawing primitives.  Coordinates are inclusive."""

    def __init__(self, width, height, fill=palette.VOID):
        self.width = width
        self.height = height
        self.pixels = np.full((height, width), fill, dtype=np.uint8)

    # --- construction ---------------------------------------------------------------------
    @classmethod
    def from_array(cls, array):
        canvas = cls(array.shape[1], array.shape[0])
        canvas.pixels = array.astype(np.uint8).copy()
        return canvas

    def copy(self):
        return Canvas.from_array(self.pixels)

    @property
    def array(self):
        return self.pixels

    # --- mask plumbing --------------------------------------------------------------------
    def _paint(self, draw_calls, index):
        """Rasterise draw_calls onto a scratch mask, then stamp `index` where the mask is set."""
        mask = Image.new(MASK_MODE, (self.width, self.height), MASK_OFF)
        draw = ImageDraw.Draw(mask)
        draw_calls(draw)
        self.pixels[np.asarray(mask) == MASK_ON] = index

    # --- primitives -----------------------------------------------------------------------
    def fill(self, index):
        self.pixels[:, :] = index

    def pixel(self, x, y, index):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y, x] = index

    def rect(self, x0, y0, x1, y1, index):
        self._paint(lambda d: d.rectangle((x0, y0, x1, y1), fill=MASK_ON), index)

    def outline_rect(self, x0, y0, x1, y1, index, width=DEFAULT_LINE_WIDTH):
        self._paint(lambda d: d.rectangle((x0, y0, x1, y1), outline=MASK_ON, width=width), index)

    def hline(self, y, x0, x1, index, thickness=DEFAULT_LINE_WIDTH):
        self.rect(x0, y, x1, y + thickness - 1, index)

    def vline(self, x, y0, y1, index, thickness=DEFAULT_LINE_WIDTH):
        self.rect(x, y0, x + thickness - 1, y1, index)

    def line(self, x0, y0, x1, y1, index, width=DEFAULT_LINE_WIDTH):
        self._paint(lambda d: d.line((x0, y0, x1, y1), fill=MASK_ON, width=width), index)

    def polygon(self, points, index):
        self._paint(lambda d: d.polygon(list(points), fill=MASK_ON), index)

    def polyline(self, points, index, width=DEFAULT_LINE_WIDTH):
        self._paint(lambda d: d.line(list(points), fill=MASK_ON, width=width), index)

    def ellipse(self, x0, y0, x1, y1, index):
        self._paint(lambda d: d.ellipse((x0, y0, x1, y1), fill=MASK_ON), index)

    def outline_ellipse(self, x0, y0, x1, y1, index, width=DEFAULT_LINE_WIDTH):
        self._paint(lambda d: d.ellipse((x0, y0, x1, y1), outline=MASK_ON, width=width), index)

    # --- composition ----------------------------------------------------------------------
    def blit(self, source, x, y, key=None):
        """Stamp `source` (array or Canvas) at (x, y); pixels equal to `key` are not drawn."""
        source = source.array if isinstance(source, Canvas) else source
        height, width = source.shape
        dst_x0, dst_y0 = max(x, 0), max(y, 0)
        dst_x1, dst_y1 = min(x + width, self.width), min(y + height, self.height)
        if dst_x0 >= dst_x1 or dst_y0 >= dst_y1:
            return
        patch = source[dst_y0 - y:dst_y1 - y, dst_x0 - x:dst_x1 - x]
        target = self.pixels[dst_y0:dst_y1, dst_x0:dst_x1]
        target[:] = patch if key is None else np.where(patch == key, target, patch)

    def region(self, x0, y0, x1, y1):
        return self.pixels[y0:y1 + 1, x0:x1 + 1]


# --- array operations ---------------------------------------------------------------------
def remap(array, table):
    """Apply a 16-entry index remap (a shade table) to an index array."""
    return np.asarray(table, dtype=np.uint8)[array]


def shade(array, band):
    """Depth-fog an index array: a table lookup, never a new colour."""
    return remap(array, palette.SHADE_TABLES[band])


def shade_sprite(array, band, key=palette.TRANSPARENT_INDEX):
    """Fog a sprite without fogging its transparency: the key is a flag, not a colour.

    The key shares an index with the GRID slate, which fogs to cyan 4 and then cyan 5, so a
    plain `shade` would silently repaint a far enemy's transparent pixels as wall-coloured
    slate.  Sprites therefore never paint the key themselves either - see sprites.key_leaks.
    """
    out = shade(array, band)
    out[array == key] = key
    return out


def upscale(array, factor):
    return np.repeat(np.repeat(array, factor, axis=0), factor, axis=1)


def mirror_x(array):
    return array[:, ::-1]


def mirror_left_half(array):
    """Complete a bilaterally symmetric sprite drawn only on its left half (even width only)."""
    width = array.shape[1]
    if width % 2:
        raise ValueError("mirror_left_half needs an even width, got %d" % width)
    half = width // 2
    out = array.copy()
    out[:, half:] = array[:, half - 1::-1]
    return out


def tile(array, columns, rows):
    return np.tile(array, (rows, columns))


def silhouette(array, key):
    return array != key


def shift(array, dy, dx):
    """Translate an array without wrapping - np.roll would leak a rim across the edge."""
    height, width = array.shape
    out = np.zeros_like(array)
    out[max(0, dy):height + min(0, dy), max(0, dx):width + min(0, dx)] = \
        array[max(0, -dy):height - max(0, dy), max(0, -dx):width - max(0, dx)]
    return out


def rim_mask(array, key):
    """The 1-px 8-connected halo just outside the silhouette - the enemy rim-light."""
    body = silhouette(array, key)
    grown = body.copy()
    for dy, dx in NEIGHBOUR_OFFSETS:
        grown |= shift(body, dy, dx)
    return grown & ~body


def apply_rim(array, key=palette.TRANSPARENT_INDEX, ink=palette.RIM):
    """Return a copy with a 1-px `ink` outline painted into the transparent halo."""
    out = array.copy()
    out[rim_mask(array, key)] = ink
    return out


#: How many rows either side of the wrap have to survive for a damaged tile to still stack.
WRAP_BAND = 8


def vertical_period(array):
    """Smallest proper divisor of the height at which the tile repeats exactly, else None.

    This is the property, not a proxy for it: a tile whose features land on a pitch dividing
    its height stacks with no seam, and one whose pitch does not (24 into 64, say) cannot.
    The previous version compared the wrap-row change count against the WORST internal row
    change, which every texture passes by construction - it could not fail.
    """
    height = array.shape[0]
    for period in range(1, height):
        if height % period == 0 and np.array_equal(array, np.roll(array, period, axis=0)):
            return period
    return None


def wrap_band_matches(array, reference, band=WRAP_BAND):
    """True when the rows either side of the wrap are identical to another tile's."""
    return (np.array_equal(array[:band], reference[:band])
            and np.array_equal(array[-band:], reference[-band:]))


#: A joint needs at least this many identical rows at each end to read as trim rather than
#: as an accident.  Two rows doubles to a four-row band when the tile is stacked.
MIN_JOINT_ROWS = 2


def joint_rows(array, minimum=MIN_JOINT_ROWS):
    """How many rows of identical trim top and bottom, or 0 if the ends do not match.

    A landmark tile - a door, a gate - has no repeat to be periodic about.  It stacks
    cleanly anyway if it opens and closes on the same uniform trim row, because the join
    then reads as a structural band rather than as a cut.
    """
    if not np.array_equal(array[0], array[-1]):
        return 0
    count = 1
    while (count < array.shape[0] // 2
           and np.array_equal(array[count], array[0])
           and np.array_equal(array[-1 - count], array[0])):
        count += 1
    return count if count >= minimum else 0


def vertical_seam_ok(array, reference=None, band=WRAP_BAND):
    """(ok, how) - can this tile be stacked on itself without printing a visible line?

    Three ways to qualify, and a tile whose pitch simply does not divide its height (24 into
    64, say) satisfies none of them:
      periodic   - the tile repeats at a pitch dividing its height (a structural wall)
      joint      - it opens and closes on the same uniform trim rows (a door, a gate)
      wrap-band  - its top and bottom `band` rows are byte-identical to a `reference` tile
                   that is itself periodic (a corrupted wall, irregular only in the middle)
    """
    period = vertical_period(array)
    if period is not None:
        return True, "period %d" % period
    joint = joint_rows(array)
    if joint:
        return True, "joint %d" % joint
    if reference is not None and vertical_period(reference) is not None:
        return wrap_band_matches(array, reference, band), "wrap-band"
    return False, None


def indices_used(array):
    return sorted(int(i) for i in np.unique(array))


# --- self-test -------------------------------------------------------------------------------
SELFTEST_SIZE = 64
BAD_PITCH = 24                       # does not divide 64: the seam test must reject it
GOOD_PITCH = 16
STRIPE_HEIGHT = 12


def _striped_tile(pitch):
    """A tile of horizontal bands on `pitch` - seamless if and only if pitch divides 64."""
    canvas = Canvas(SELFTEST_SIZE, SELFTEST_SIZE, palette.VOID)
    for y in range(0, SELFTEST_SIZE, pitch):
        canvas.rect(0, y, SELFTEST_SIZE - 1, min(y + STRIPE_HEIGHT, SELFTEST_SIZE) - 1,
                    palette.CYAN_2)
    return canvas.array


def main():
    """Pin the seam test in both directions, because a gate nobody can fail is not a gate."""
    good_ok, good_period = vertical_seam_ok(_striped_tile(GOOD_PITCH))
    bad_ok, bad_how = vertical_seam_ok(_striped_tile(BAD_PITCH))
    rimmed = apply_rim(np.full((6, 6), palette.TRANSPARENT_INDEX, dtype=np.uint8))
    print("drawlib self-test")
    print("  pitch %2d tile: seamless=%s via %-10s (expected True / period %d)"
          % (GOOD_PITCH, good_ok, good_period, GOOD_PITCH))
    print("  pitch %2d tile: seamless=%s via %-10s (expected False)"
          % (BAD_PITCH, bad_ok, bad_how))
    print("  empty sprite rims to nothing: %s" % (not (rimmed == palette.RIM).any()))
    failures = int(not good_ok) + int(good_period != "period %d" % GOOD_PITCH) + int(bad_ok)
    print("  failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
