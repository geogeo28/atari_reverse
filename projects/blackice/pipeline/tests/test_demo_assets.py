"""Demo-set tests: determinism, palette legality, and that the art is not a blank rectangle.

The generators are procedural, so "it looked right once" is not a guarantee -- these pin the
properties that made it look right: coverage of the palette, a non-trivial silhouette, and a
dark variant that is actually darker.
"""
import numpy as np
import pytest

from stepix.colourspace import lab_lightness
from stepix.demo_assets import (ART_SEED, BACKDROP_PREVIEW, ICON_H, ICON_W, KEY_RGB,
                                _blit_text, _check_backdrop_indices_are_drawable,
                                _check_saved_preview_is_palettised, build_demo_assets,
                                build_demo_palette, compression_report, main, write_demo)
from stepix.palette import PALETTE_SIZE
from stepix.pack import read_pak, read_pak_directory
from stepix.planar import PI1_BYTES, SCREEN_BYTES, SCREEN_H, SCREEN_W
from stepix.sprite import SPRITE_DIM, TRANSPARENT_INDEX, column_spans, hud_blit
from stepix.texture import TEXTURE_DIM, apply_shade_table

MIN_DISTINCT_COLOURS = 4        # art using fewer indices than this is a flat rectangle, not art
EXPECTED_TEXTURES = ["BRICK", "METAL", "STONE", "DOOR"]


@pytest.fixture(scope="module")
def assets():
    return build_demo_assets()


def test_seed_is_fixed_so_rebuilds_are_identical():
    first, second = build_demo_assets(), build_demo_assets()
    assert ART_SEED == 0x57454C46
    for left, right in zip(first.textures, second.textures):
        assert np.array_equal(left.indices, right.indices)
    assert np.array_equal(first.sprite.indices, second.sprite.indices)
    assert np.array_equal(first.backdrop, second.backdrop)


def test_palette_reserves_index_zero_and_fifteen():
    palette = build_demo_palette()
    assert len(palette.colours) == PALETTE_SIZE
    assert palette.background == palette.colours[0]
    assert palette.colours[TRANSPARENT_INDEX] == KEY_RGB


def test_key_colour_is_far_from_every_other_entry():
    """A key that resembles a real colour makes a leak invisible; magenta must stand out."""
    lab = build_demo_palette().to_lab()
    distances = np.linalg.norm(lab - lab[TRANSPARENT_INDEX], axis=1)
    assert np.sort(distances)[1] > 40.0


def test_texture_set_names_and_sizes(assets):
    assert [texture.name for texture in assets.textures] == EXPECTED_TEXTURES
    for texture in assets.textures:
        assert texture.indices.shape == (TEXTURE_DIM, TEXTURE_DIM)


@pytest.mark.parametrize("position", range(len(EXPECTED_TEXTURES)))
def test_textures_are_not_flat_and_never_use_the_key(assets, position):
    texture = assets.textures[position]
    used = set(np.unique(texture.indices).tolist())
    assert len(used) >= MIN_DISTINCT_COLOURS, f"{texture.name} is nearly flat"
    assert TRANSPARENT_INDEX not in used, f"{texture.name} leaks the transparency key"


@pytest.mark.parametrize("position", range(len(EXPECTED_TEXTURES)))
def test_dark_variant_is_measurably_darker(assets, position):
    """The N-S vs E-W cue has to be visible, not merely present."""
    lightness = lab_lightness(assets.palette.to_rgb888().astype(float))
    lit = assets.textures[position].indices
    dark = apply_shade_table(lit, assets.shade_table)
    assert lightness[dark].mean() < lightness[lit].mean() - 5.0


def test_sprite_has_a_real_silhouette(assets):
    art = assets.sprite.indices
    transparent = art == TRANSPARENT_INDEX
    assert art.shape == (SPRITE_DIM, SPRITE_DIM)
    assert 0.15 < transparent.mean() < 0.75, "a billboard that is all or nothing needs no span table"

    spans = column_spans(art)
    empty = sum(1 for column in range(SPRITE_DIM) if spans[2 * column] > spans[2 * column + 1])
    assert 0 < empty < SPRITE_DIM, "span table should skip some columns but not all"


def test_sprite_columns_vary_in_height(assets):
    """A rectangular sprite would make the span table pointless; the barrel is curved."""
    spans = column_spans(assets.sprite.indices)
    tops = {spans[2 * column] for column in range(SPRITE_DIM) if spans[2 * column] <= spans[2 * column + 1]}
    assert len(tops) > 1


def test_icon_is_hud_blittable(assets):
    assert assets.icon.shape == (ICON_H, ICON_W)
    assert ICON_W % 16 == 0
    blit = hud_blit(assets.icon)
    assert len(blit.mask) == ICON_H * blit.mask_row_bytes
    assert (assets.icon == TRANSPARENT_INDEX).any(), "the icon must exercise the mask"


def test_backdrop_is_a_full_screen_of_drawable_indices(assets):
    """`check_palettized(indices_to_rgb(...))` cannot fail here -- it audits colours this test
    just built FROM the palette. What can fail is the index set: the backdrop has no mask, so
    every index must be encodable in 4 bitplanes and must not be the transparency key."""
    assert assets.backdrop.shape == (SCREEN_H, SCREEN_W)
    used = set(np.unique(assets.backdrop).tolist())
    assert len(used) >= MIN_DISTINCT_COLOURS
    assert used <= set(range(PALETTE_SIZE)) - {TRANSPARENT_INDEX}, sorted(used)


def test_backdrop_does_not_use_the_transparency_key(assets):
    assert TRANSPARENT_INDEX not in set(np.unique(assets.backdrop).tolist())


def test_write_demo_emits_every_file(tmp_path):
    outdir = str(tmp_path / "out")
    assets, resources = write_demo(outdir)
    expected_files = ["palette.png", "tex_brick.png", "tex_metal.png", "tex_stone.png", "tex_door.png",
                      "sprite_barrel.png", "hud_icon.png", "font_sheet.png", "hud_backdrop.png",
                      "hudscr.pi1", "demo.pak", "demo_assets.h"]
    for filename in expected_files:
        assert (tmp_path / "out" / filename).is_file(), filename
    assert (tmp_path / "out" / "hudscr.pi1").stat().st_size == PI1_BYTES
    assert (tmp_path / "out" / "hudscr.bin").stat().st_size == SCREEN_BYTES

    pak = (tmp_path / "out" / "demo.pak").read_bytes()
    assert read_pak(pak) == resources
    assert {entry.name for entry in read_pak_directory(pak)} == set(resources)
    assert "TOTAL" in compression_report(outdir)


def test_pak_compresses_the_bulk_resources(tmp_path):
    outdir = str(tmp_path / "out")
    write_demo(outdir)
    entries = {entry.name: entry for entry in read_pak_directory((tmp_path / "out" / "demo.pak").read_bytes())}
    assert entries["TEXTURES"].ratio < 0.35
    assert entries["HUDSCR"].ratio < 0.35


# ---- the checks main() runs on what it wrote ------------------------------------------
def test_main_builds_and_verifies_the_written_set(tmp_path):
    outdir = str(tmp_path / "out")
    main(outdir)
    assert (tmp_path / "out" / "demo.pak").is_file()
    assert (tmp_path / "out" / BACKDROP_PREVIEW).is_file()


def test_backdrop_check_rejects_the_transparency_key(assets):
    """The mutation that slipped past the old tautological check must fail this one."""
    leaked = assets.backdrop.copy()
    leaked[0, 0] = TRANSPARENT_INDEX
    with pytest.raises(AssertionError):
        _check_backdrop_indices_are_drawable(leaked)


def test_saved_preview_check_rejects_off_palette_art(tmp_path):
    """The PNG audit has to be able to fail: hand it a preview with one stray colour."""
    from PIL import Image

    palette = build_demo_palette()
    art = np.tile(palette.to_rgb888()[0], (8, 8, 1)).astype(np.uint8)
    art[0, 0] = (1, 2, 3)                                   # a colour no palette entry can be
    Image.fromarray(art, mode="RGB").save(tmp_path / BACKDROP_PREVIEW)
    with pytest.raises(AssertionError):
        _check_saved_preview_is_palettised(str(tmp_path), palette)


def test_blit_text_rejects_a_string_that_runs_off_the_art():
    art = np.zeros((SCREEN_H, SCREEN_W), dtype=np.uint8)
    text = "THIS RUNS OFF THE RIGHT EDGE"
    with pytest.raises(ValueError, match=text):
        _blit_text(art, text, 0, SCREEN_W - 8, ink=1)
