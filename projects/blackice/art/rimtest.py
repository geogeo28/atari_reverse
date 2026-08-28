"""The rim-light readability harness the critique demanded before any art production.

"Reserve two accents as sprite-only colours no wall may use, and mandate a 1-px #FFFFFF
rim-light on every enemy, tested against every wall at every band before art production
starts."  This is that test, and it gates the art: `main` exits non-zero on a failure.

WHAT THE 31.3 FIGURE IS, HONESTLY.  The headline "worst rim margin 31.3 Y" is not an
independent discovery: it is `palette.rim_headroom()` re-derived - white (Y 255.0) against
data yellow (Y 223.7), the brightest colour a wall is allowed to contain.  Because white
never fogs and `textures.reserved_colours_used` separately forbids walls from containing it,
the margin gate CANNOT return anything lower unless one of those two invariants is already
broken elsewhere.  On its own it is a tautology dressed as a measurement.

So the harness gates three things instead, and only the first can be called a measurement of
the art rather than of the palette:

  COVERAGE  every silhouette edge pixel has a RIM neighbour, on every wall at every band.
            This is the falsifiable one: two pickups shipped Revision 2 with no rim at all
            and this gate is what fails on them.
  MARGIN    white against the wall colours the rim actually borders (the tautology above,
            kept because it is the thing that would break first if a wall ever gained a
            reserved colour).
  LOAD      the harness must be testing something: at least one combination has to have a
            body-to-wall margin below MIN_BODY_MARGIN, or the rim is decorative and none of
            the above proves anything.  It is 0.0 Y for cycles_cell's cyan 2 against
            anchor_pylon's cyan 2 at band 0 - identical colours, silhouette invisible without
            the rim.  The rule is deliberately NOT "bodies must contrast with walls": they
            cannot, in a 16-colour palette where sprites and walls share a ramp.  The rim is
            the answer to that, and LOAD asserts the question was real.
"""

from collections import namedtuple

import numpy as np

import drawlib
import palette
import sprites
import textures

#: White against the wall colours it borders.  Same threshold palette.py proves it can meet.
MIN_RIM_MARGIN = palette.MIN_RIM_HEADROOM_LUMA
#: Below this a silhouette would be invisible against the wall without its rim.
MIN_BODY_MARGIN = palette.MIN_WALL_PAIR_LUMA
#: Every edge pixel must be rimmed.  Not "most".
REQUIRED_COVERAGE = 1.0

RimResult = namedtuple("RimResult", "sprite texture band coverage rim_margin body_margin")


def tiled_wall(texture, shape):
    """A wall big enough to sit a sprite on, tiled from one 64x64 texel block."""
    height, width = shape
    repeats = (height // texture.shape[0] + 1, width // texture.shape[1] + 1)
    return np.tile(texture, repeats)[:height, :width]


def _neighbourhood(mask):
    """Union of a mask's eight shifts - "is there one of these next to me"."""
    grown = np.zeros_like(mask)
    for dy, dx in drawlib.NEIGHBOUR_OFFSETS:
        grown |= drawlib.shift(mask, dy, dx)
    return grown


def rim_coverage(shaded_sprite, key):
    """Fraction of silhouette edge pixels that have a RIM pixel next to them."""
    body = (shaded_sprite != key) & (shaded_sprite != palette.RIM)
    #: An edge pixel is a body pixel with anything that is not body beside it - key OR rim.
    #: Testing against the key alone reads 0% on a correctly rimmed sprite, because the rim
    #: is exactly what stands between the body and the key.
    edge = body & _neighbourhood(~body)
    if not edge.any():
        return 0.0
    return float((edge & _neighbourhood(shaded_sprite == palette.RIM)).sum() / edge.sum())


def _adjacent_background_colours(composite, background, selection):
    """Every background colour touching the 8-neighbourhood of `selection`."""
    colours = set()
    for dy, dx in drawlib.NEIGHBOUR_OFFSETS:
        touching = drawlib.shift(selection, dy, dx) & background
        colours.update(int(index) for index in np.unique(composite[touching]))
    return colours


def _worst_body_to_wall_margin(sprite_shaded, wall, key):
    """The contrast the silhouette would rely on if the rim were deleted."""
    body = (sprite_shaded != key) & (sprite_shaded != palette.RIM)
    body_colours = np.where(body, sprite_shaded, palette.VOID)
    worst = float("inf")
    for dy, dx in drawlib.NEIGHBOUR_OFFSETS:
        touching = drawlib.shift(body, dy, dx) & ~body
        if not touching.any():
            continue
        for body_index in np.unique(drawlib.shift(body_colours, dy, dx)[touching]):
            for wall_index in np.unique(wall[touching]):
                worst = min(worst, palette.luma_distance(int(body_index), int(wall_index)))
    return worst


def measure(sprite, texture, band, key=sprites.KEY):
    """(coverage, rim margin, body margin) for one sprite on one wall at one depth band."""
    shaded_sprite = drawlib.shade_sprite(sprite, band, key)
    wall = tiled_wall(drawlib.shade(texture, band), sprite.shape)
    background = shaded_sprite == key
    composite = np.where(background, wall, shaded_sprite)
    colours = _adjacent_background_colours(composite, background, composite == palette.RIM)
    #: No rim-adjacent wall pixel at all means there is no rim: a hard zero, never infinity.
    rim_margin = (min(palette.luma_distance(palette.RIM, index) for index in colours)
                  if colours else 0.0)
    return (rim_coverage(shaded_sprite, key), rim_margin,
            _worst_body_to_wall_margin(shaded_sprite, wall, key))


def rimmed_sprites():
    """Everything that carries a rim: the four enemies and the four pickups."""
    built = sprites.build_all()
    return [(name, built[name]) for name in sprites.rimmed_names()]


def run():
    walls = list(textures.build_all().items())
    return [RimResult(sprite_name, wall_name, band, *measure(sprite, wall, band))
            for sprite_name, sprite in rimmed_sprites()
            for wall_name, wall in walls
            for band in range(palette.DEPTH_BANDS)]


def coverage_failures(results):
    return [result for result in results if result.coverage < REQUIRED_COVERAGE]


def margin_failures(results):
    return [result for result in results if result.rim_margin < MIN_RIM_MARGIN]


def load_bearing(results):
    """Combinations where the silhouette would have been invisible without its rim."""
    return [result for result in results if result.body_margin < MIN_BODY_MARGIN]


def worst_by_sprite(results):
    worst = {}
    for result in results:
        current = worst.get(result.sprite)
        if current is None or result.coverage < current.coverage or (
                result.coverage == current.coverage and result.rim_margin < current.rim_margin):
            worst[result.sprite] = result
    return worst


def main():
    results = run()
    uncovered, thin, load = coverage_failures(results), margin_failures(results), load_bearing(results)
    print("rim-light harness: %d combinations (%d sprites x %d walls x %d bands)"
          % (len(results), len(rimmed_sprites()), len(textures.ALL_BUILDERS), palette.DEPTH_BANDS))
    print()
    print("  sprite            coverage   rim margin   worst against         band")
    for name, result in worst_by_sprite(results).items():
        print("  %-16s %7.1f%%   %10.1f   %-20s %d"
              % (name, result.coverage * 100, result.rim_margin, result.texture, result.band))
    print()
    worst_load = min(results, key=lambda result: result.body_margin)
    print("COVERAGE  every edge pixel rimmed on every wall at every band: %d failures" % len(uncovered))
    print("MARGIN    white vs the wall colours the rim borders, >= %.0f Y: %d failures"
          % (MIN_RIM_MARGIN, len(thin)))
    print("LOAD      %d of %d combinations would be invisible without the rim (need >= 1);"
          % (len(load), len(results)))
    print("          worst body-to-wall margin %.1f Y - %s on %s at band %d"
          % (worst_load.body_margin, worst_load.sprite, worst_load.texture, worst_load.band))
    for result in (uncovered + thin)[:20]:
        print("  FAIL %s over %s at band %d: coverage %.1f%%, margin %.1f"
              % (result.sprite, result.texture, result.band, result.coverage * 100,
                 result.rim_margin))
    return 1 if (uncovered or thin or not load) else 0


if __name__ == "__main__":
    raise SystemExit(main())
