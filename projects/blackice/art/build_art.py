"""Regenerate every BLACK ICE art asset, run every gate, and print the RAM ledger.

    python build_art.py          rebuild everything and gate
    make                         the same thing

Gates (any failure exits non-zero):
  * palette.py   - the cyan and magenta ramps stay separated in luminance AND chroma in all
                   five depth bands, and white keeps its headroom over every wall-legal colour
  * textures.py  - every wall is vertically seamless and contains no RESERVED sprite colour
  * sprites.py   - every enemy silhouette is fully enclosed by its rim
  * rimtest.py   - every (sprite, wall, band) combination clears the rim contrast threshold
"""

import contact_sheet
import drawlib
import font
import hud
import keyart
import palette
import pixelio
import rimtest
import sprites
import textures

#: One byte per texel is the honest storage figure; the nibble column is what packing buys.
#: Rows already stored in their final form (the planar HUD, the 1-bit font) pack to themselves.
NIBBLES_PER_BYTE = 2

STAGES = (
    ("drawlib self-test", drawlib.main),
    ("palette", palette.main),
    ("textures", textures.main),
    ("sprites", sprites.main),
    ("hud", hud.main),
    ("rim-light harness", rimtest.main),
    ("key art", keyart.main),
    ("contact sheet", contact_sheet.main),
)


def _chunky_row(name, count, size):
    return (name, count, size, size // NIBBLES_PER_BYTE)


def ledger():
    """(group, count, byte-per-texel bytes, packed bytes) rows for ART_DIRECTION.md."""
    walls = textures.build_all()
    built = sprites.build_all()
    group = lambda builders: (len(builders),
                              sum(built[name].size for name, _ in builders))
    hud_bytes = hud.HUD_WIDTH // 2 * hud.HUD_HEIGHT
    return (
        _chunky_row("wall textures + door + key panel", len(walls),
                    sum(array.size for array in walls.values())),
        _chunky_row("enemy billboards 64x64", *group(sprites.ENEMY_BUILDERS)),
        _chunky_row("pickups 32x32", *group(sprites.PICKUP_BUILDERS)),
        _chunky_row("weapon overlays 96x48", *group(sprites.WEAPON_BUILDERS)),
        _chunky_row("data particle 16x16", 1, built["data_particle"].size),
        ("HUD strip 320x40, already planar", 1, hud_bytes, hud_bytes),
        ("8x8 font (stepix table, 1 bit per pixel)", font.GLYPH_COUNT,
         font.FONT_BYTES, font.FONT_BYTES),
    )


def print_ledger():
    print()
    print("RAM ledger  group                                     count     bytes   packed")
    raw_total = packed_total = 0
    for name, count, size, packed in ledger():
        raw_total += size
        packed_total += packed
        print("  %-42s %5d %9d %8d" % (name, count, size, packed))
    print("  %-42s %5s %9d %8d" % ("TOTAL", "", raw_total, packed_total))


def main():
    pixelio.ensure_dirs()
    failed = []
    for name, stage in STAGES:
        print("=" * 78)
        print("== %s" % name)
        print("=" * 78)
        if stage():
            failed.append(name)
        print()
    print_ledger()
    print()
    if failed:
        print("GATES FAILED: %s" % ", ".join(failed))
        return 1
    print("all gates passed; assets in %s and %s" % (pixelio.OUT_DIR, pixelio.NATIVE_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
