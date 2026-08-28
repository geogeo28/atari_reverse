"""The shipped art is in the engine, unaltered, in the slots the legend names.

tools/mkassets.py converts art/out/native/*.png into src/assets_data.c, and from there the
texels reach the host renderer, atari/dumpassets and the .PAK.  Nothing downstream can tell a
texture that landed in the wrong slot, a sprite that was transposed on the way in or a pickup
that floats at eye height from art that was authored that way - they all just draw.  So this
file compares the arrays THE ENGINE ACTUALLY LINKS against a fresh conversion of the PNGs, and
restates the id -> file mapping rather than importing mkassets' own table: a pin that reads its
expectation out of the thing it is pinning proves nothing.

art/out/ is generated and not committed (.gitignore), so the tests that need the PNGs skip when
the art tree has not been built.  The two invariants that need no PNG - the palette the engine
holds, and where a pickup sits in its frame - run either way.
"""
import ctypes
import pathlib
import sys

import numpy
import pytest
from PIL import Image

import blackice
from blackice import CONST

sys.path.insert(0, str(blackice.ROOT / "art"))
sys.path.insert(0, str(blackice.ROOT / "pipeline"))
import palette as art_palette                                       # noqa: E402
import pixelio as art_pixelio                                       # noqa: E402
from stepix import sprite as stepix_sprite                          # noqa: E402
from stepix import texture as stepix_texture                        # noqa: E402

#: From art/pixelio.py, the module that writes them, so this pin cannot look in the wrong place.
ART_DIR = pathlib.Path(art_pixelio.NATIVE_DIR)
TEX_DIM = CONST["TEX_DIM"]
TEX_SIZE = CONST["TEX_SIZE"]
SPRITE_TRANSPARENT = CONST["SPRITE_TRANSPARENT"]
ENT_TYPE_COUNT = CONST["ENT_TYPE_COUNT"]
PALETTE_SIZE = art_palette.PALETTE_SIZE
RGB_CHANNELS = 3

#: Wall texture id (include/map.h) -> the art file that must fill it.  DESIGN 11's legend.
WALL_TEXTURE_ART = (
    ("TEX_CIRCUIT_LATTICE",  "tex_circuit_lattice"),
    ("TEX_HEX_MESH",         "tex_hex_mesh"),
    ("TEX_GLYPH_COLUMN",     "tex_glyph_column"),
    ("TEX_BUS_TRUNK",        "tex_bus_trunk"),
    ("TEX_FIREWALL_CHEVRON", "tex_firewall_chevron"),
    ("TEX_CORRUPT_NOISE",    "tex_corrupted_sector"),
    ("TEX_ANCHOR_PYLON",     "tex_anchor_pylon"),
    ("TEX_EXIT_PLATING",     "tex_exit_gate"),
    ("TEX_GATE_PANEL",       "tex_door"),
    ("TEX_LOCKED_PANEL",     "tex_sector_key_panel"),
)

#: Entity type -> the art file its billboard must come from.  The three tokens share one card
#: and the small/large pickups share one icon, which is checked as pointer identity below.
ENTITY_SPRITE_ART = (
    ("ENT_WATCHDOG",        "spr_watchdog"),
    ("ENT_SENTRY",          "spr_sentry"),
    ("ENT_TRACER",          "spr_tracer"),
    ("ENT_BLACK_ICE",       "spr_black_ice"),
    ("ENT_TOKEN_ALPHA",     "spr_access_token"),
    ("ENT_TOKEN_BETA",      "spr_access_token"),
    ("ENT_TOKEN_GAMMA",     "spr_access_token"),
    ("ENT_CYCLES_SMALL",    "spr_cycles_cell"),
    ("ENT_CYCLES_LARGE",    "spr_cycles_cell"),
    ("ENT_INTEGRITY_SMALL", "spr_integrity_patch"),
    ("ENT_INTEGRITY_LARGE", "spr_integrity_patch"),
    ("ENT_SCRUBBER",        "spr_trace_scrubber"),
    ("ENT_DATA_CACHE",      "spr_data_particle"),
)

#: Everything the player picks up off the floor.  DESIGN 17.1 gives these PICKUP_HEIGHT_CELLS,
#: which is half a cell, so none of their texels may reach the frame's upper half.
PICKUP_TYPES = tuple(name for name, _ in ENTITY_SPRITE_ART if name.startswith(("ENT_TOKEN_",
                                                                               "ENT_CYCLES_",
                                                                               "ENT_INTEGRITY_"))
                     ) + ("ENT_SCRUBBER", "ENT_DATA_CACHE")
#: An enemy is one cell tall and must fill the frame, which is the contrast that makes the
#: pickup rule a rule rather than something every sprite happens to satisfy.
ENEMY_TYPES = ("ENT_WATCHDOG", "ENT_SENTRY", "ENT_TRACER", "ENT_BLACK_ICE")

#: The one type with no billboard at all: an anchor pylon IS its wall texture (cell value 7).
UNDRAWN_TYPES = ("ENT_NONE", "ENT_ANCHOR")


class SpriteSpan(ctypes.Structure):
    _fields_ = [("first", ctypes.c_uint8), ("last", ctypes.c_uint8)]


class SpriteAsset(ctypes.Structure):
    _fields_ = [("texels", ctypes.POINTER(ctypes.c_uint8)),
                ("spans", ctypes.POINTER(SpriteSpan))]


def indexed_png(stem):
    """One art PNG, refusing anything but mode P - where the pixels ARE palette indices."""
    image = Image.open(ART_DIR / (stem + ".png"))
    assert image.mode == "P", "%s is mode %r, so its pixels are colours and not indices" % (
        stem, image.mode)
    return image


def indices_of(image):
    """An indexed image as a [row][column] array of palette indices."""
    return numpy.asarray(image, dtype=numpy.uint8)


def png_indices(stem):
    return indices_of(indexed_png(stem))


def wall_texture_bytes(lib, id_name):
    slot = blackice.wall_texture_slots(lib)[CONST[id_name]]
    assert slot, "%s has no art in g_wall_textures" % id_name
    return ctypes.string_at(slot, TEX_SIZE)


def entity_sprites(lib):
    return (ctypes.POINTER(SpriteAsset) * ENT_TYPE_COUNT).in_dll(lib, "g_entity_sprites")


def sprite_asset(lib, type_name):
    asset = entity_sprites(lib)[CONST[type_name]]
    assert asset, "%s has no billboard in g_entity_sprites" % type_name
    return asset.contents


def sprite_texels(asset):
    return ctypes.string_at(asset.texels, TEX_SIZE)


def sprite_span_bytes(asset):
    return ctypes.string_at(ctypes.cast(asset.spans, ctypes.c_void_p), TEX_DIM * 2)


def opaque_rows_and_columns(texels):
    """The frame rows and columns holding a non-key texel, from column-major bytes."""
    rows = {index % TEX_DIM for index, value in enumerate(texels) if value != SPRITE_TRANSPARENT}
    columns = {index // TEX_DIM for index, value in enumerate(texels)
               if value != SPRITE_TRANSPARENT}
    return rows, columns


requires_art = pytest.mark.skipif(
    not ART_DIR.is_dir(),
    reason="art/out/ is generated and not committed; run `make -C art` to build it")


# ---- the palette -----------------------------------------------------------------------

def test_the_engine_holds_the_art_departments_palette(lib):
    """g_palette_rgb and art/palette.py must be the same sixteen colours.

    They are written independently - src/tables.c is generated by tools/mktables.py - and the
    art's pixel values are INDICES into this table, so a divergence repaints the whole game in
    colours nobody chose.  atari/mkpak.py makes the same check for the target; this is the one
    the host build cannot skip.
    """
    engine = blackice.table(lib, "g_palette_rgb", ctypes.c_uint8 * RGB_CHANNELS, PALETTE_SIZE)
    assert [tuple(entry) for entry in engine] == list(art_palette.RGB)


@requires_art
@pytest.mark.parametrize("stem", [stem for _, stem in WALL_TEXTURE_ART]
                         + sorted({stem for _, stem in ENTITY_SPRITE_ART}))
def test_every_shipped_png_carries_that_palette(stem):
    """The PNG's own palette, not just its indices: a file written against other colours would
    convert without complaint and only look wrong."""
    image = indexed_png(stem)
    png_palette = list(image.getpalette() or [])[:PALETTE_SIZE * RGB_CHANNELS]
    assert png_palette == art_palette.pil_palette()
    assert int(indices_of(image).max()) < PALETTE_SIZE


# ---- the wall textures -----------------------------------------------------------------

@requires_art
@pytest.mark.parametrize("id_name,stem", WALL_TEXTURE_ART)
def test_each_wall_slot_holds_a_fresh_conversion_of_its_art(lib, id_name, stem):
    """Byte-for-byte against pipeline/stepix, which also pins the ORIENTATION: a transposed or
    mirrored import would still be 4,096 legal bytes in the right slot."""
    assert wall_texture_bytes(lib, id_name) == stepix_texture.to_column_major(png_indices(stem))


# ---- the billboards --------------------------------------------------------------------

@requires_art
@pytest.mark.parametrize("type_name,stem", ENTITY_SPRITE_ART)
def test_each_entity_billboard_is_a_fresh_conversion_of_its_art(lib, type_name, stem):
    """Both halves of the record: the texels and the span table the drawer skips with."""
    art = png_indices(stem)
    height, width = art.shape
    frame = numpy.full((TEX_DIM, TEX_DIM), SPRITE_TRANSPARENT, dtype=numpy.uint8)
    left = (TEX_DIM - width) // 2
    frame[TEX_DIM - height:, left:left + width] = art

    asset = sprite_asset(lib, type_name)
    assert sprite_texels(asset) == stepix_texture.to_column_major(frame)
    assert sprite_span_bytes(asset) == stepix_sprite.column_spans(frame, SPRITE_TRANSPARENT)


@requires_art
@pytest.mark.parametrize("type_name,stem", ENTITY_SPRITE_ART)
def test_a_billboard_sits_centred_on_the_floor_of_its_frame(lib, type_name, stem):
    """The placement rule stated in the frame's own coordinates: the art is centred left to
    right and its last row is the frame's last row, which is where the floor is."""
    height, width = png_indices(stem).shape
    left = (TEX_DIM - width) // 2
    rows, columns = opaque_rows_and_columns(sprite_texels(sprite_asset(lib, type_name)))

    assert min(rows) >= TEX_DIM - height and max(rows) <= TEX_DIM - 1
    assert min(columns) >= left and max(columns) <= left + width - 1


def test_a_pickup_never_reaches_the_upper_half_of_its_frame(lib):
    """DESIGN 17.1's PICKUP_HEIGHT_CELLS of 0.5, checked on the engine's own texels.

    A pickup drawn into the top half would project at eye height and compete with an enemy
    silhouette for the same screen rows - the exact read the half-height rule exists to prevent.
    """
    for type_name in PICKUP_TYPES:
        rows, _ = opaque_rows_and_columns(sprite_texels(sprite_asset(lib, type_name)))
        assert min(rows) >= TEX_DIM // 2, "%s reaches row %d" % (type_name, min(rows))


def test_an_enemy_fills_its_frame(lib):
    """ENEMY_HEIGHT_CELLS is 1.0: an enemy is as tall as the wall behind it."""
    for type_name in ENEMY_TYPES:
        rows, _ = opaque_rows_and_columns(sprite_texels(sprite_asset(lib, type_name)))
        assert min(rows) < TEX_DIM // 2, "%s is drawn like a pickup" % type_name


def test_the_shared_billboards_are_one_asset_and_the_anchor_has_none(lib):
    """The three tokens are one card and each pickup pair is one icon - shared by POINTER, which
    is what atari/dumpassets deduplicates on when it writes the .PAK."""
    table = entity_sprites(lib)
    for group in (("ENT_TOKEN_ALPHA", "ENT_TOKEN_BETA", "ENT_TOKEN_GAMMA"),
                  ("ENT_CYCLES_SMALL", "ENT_CYCLES_LARGE"),
                  ("ENT_INTEGRITY_SMALL", "ENT_INTEGRITY_LARGE")):
        addresses = {ctypes.cast(table[CONST[name]], ctypes.c_void_p).value for name in group}
        assert len(addresses) == 1, "%s do not share one billboard" % (group,)

    for type_name in UNDRAWN_TYPES:
        assert not table[CONST[type_name]], "%s should not be drawn" % type_name


# ---- the fallback generator ------------------------------------------------------------

def test_the_placeholder_generator_still_emits_the_same_shape(tmp_path):
    """`mkassets.py --placeholder` is the documented fallback, so it has to keep working.

    Nothing in the build runs it, which is exactly why it needs a test: the two modes feed the
    same emitters, and a change to the art path's row shape that missed the procedural one
    would only surface the day someone reached for the fallback.  The check is structural, not
    a golden - the placeholder art is allowed to change, its C layout is not.
    """
    import subprocess

    generated = subprocess.run(
        [sys.executable, str(blackice.ROOT / "tools" / "mkassets.py"), "--placeholder"],
        capture_output=True, text=True, check=True).stdout

    assert generated.count("static const uint8_t ") == len(WALL_TEXTURE_ART) + 2
    for id_name, _ in WALL_TEXTURE_ART:
        assert "static const uint8_t %s[TEX_SIZE]" % id_name.lower() in generated
    assert "const uint8_t *g_wall_textures[WALL_TEXTURE_MAX + 1]" in generated
    assert "const SpriteAsset *g_entity_sprites[ENT_TYPE_COUNT]" in generated
    for type_name, _ in ENTITY_SPRITE_ART:
        assert "/* %-20s */ &spr_" % type_name in generated
    for type_name in UNDRAWN_TYPES:
        assert "/* %-20s */ 0," % type_name in generated


# ---------------------------------------------------------------------------
# Which way round the art goes on the wall.
#
# The mirror rule in src/raycast.c was inverted until 2026-08-28, and the whole
# world was left-right flipped.  Nothing caught it: the rule was UNIFORM across
# north, south, east and west faces, so walls still met cleanly, corners still
# lined up, and every geometry test still passed.  What was wrong was the global
# handedness, and the only thing that can see it is a texture that is not its own
# mirror image - which is why this check lives with the art and not with the
# raycaster.
# ---------------------------------------------------------------------------

#: The two textures whose asymmetry is the evidence: the chevron's apex points one
#: way, and the key panel's keyway sits off centre.  (TEX_LOCKED_PANEL is the slot the
#: art department calls tex_sector_key_panel.)
HANDEDNESS_TEXTURES = ("TEX_FIREWALL_CHEVRON", "TEX_LOCKED_PANEL")
#: A face is only read across its middle: the outer columns of the view are the
#: side walls of the test room, not the face being examined.
FACE_MARGIN_COLUMNS = 20


@requires_art
@pytest.mark.parametrize("id_name", HANDEDNESS_TEXTURES)
def test_the_handedness_textures_are_not_their_own_mirror(id_name):
    """Without this the check below would pass on a mirrored renderer and mean nothing.

    A symmetric texture looks identical either way round, so it can witness nothing about
    handedness.  These two are the witnesses, and this is the assertion that they can be.
    """
    stem = dict(WALL_TEXTURE_ART)[id_name]
    texels = png_indices(stem)
    mirrored = texels[:, ::-1]
    differing = int((texels != mirrored).sum())

    assert differing > texels.size // 8, (
        "%s is nearly symmetric (%d of %d texels differ from its mirror), so it cannot "
        "witness which way round the renderer puts a face" % (stem, differing, texels.size))


@pytest.mark.parametrize("facing,quarter_turns", [("east", 0), ("south", 1), ("west", 2),
                                                  ("north", 3)])
def test_a_wall_face_shows_texture_column_zero_on_the_left(lib, facing, quarter_turns):
    """Stand square to a wall and the authored PNG's column 0 must be on your LEFT.

    Read off the RenderColumn list rather than off pixels: `tex_col` IS the PNG's x index,
    so "column 0 on the left" is exactly "tex_col increases with screen column", with no
    shading, scaling or palette to see through.  Measured before the fix, this ran 63 -> 0
    across the face on all four facings.

    All four are checked because the inverted rule was uniform: a test that only stood
    facing north would have proved the seam was consistent and missed the flip entirely.
    """
    size = 9
    wall = CONST["TEX_FIREWALL_CHEVRON"]
    cells = [wall if (x in (0, size - 1) or y in (0, size - 1)) else 0
             for y in range(size) for x in range(size)]
    centre = size // 2
    level = blackice.make_level(lib, size, size, cells, (centre, centre))
    state = blackice.new_state(lib, level)
    state.detail_level = CONST["DETAIL_COLUMNS_160"]
    state.player.x = centre * blackice.CELL + blackice.CENTRE
    state.player.y = centre * blackice.CELL + blackice.CENTRE
    state.player.angle = (quarter_turns * CONST["ANGLE_QUARTER_TURN"]) & 0xFFFF
    scratch = blackice.RenderScratch()

    lib.render_cast(ctypes.byref(state), ctypes.byref(scratch))

    columns = CONST["RENDER_COLUMNS_HIGH"]
    span = range(columns // 2 - FACE_MARGIN_COLUMNS, columns // 2 + FACE_MARGIN_COLUMNS + 1)
    seen = [(c, scratch.columns[c].tex_col) for c in span]
    assert all(scratch.columns[c].tex_id == wall for c in span), \
        "facing %s did not put the chevron wall across the middle of the view" % facing
    first, last = seen[0][1], seen[-1][1]
    assert last > first, (
        "facing %s renders the face MIRRORED: tex_col runs %d -> %d across the middle of the "
        "screen, so the PNG's column 0 is on the right.  %s" % (facing, first, last, seen))
    assert all(b >= a for (_, a), (_, b) in zip(seen, seen[1:])), \
        "facing %s does not walk the texture monotonically: %s" % (facing, seen)
