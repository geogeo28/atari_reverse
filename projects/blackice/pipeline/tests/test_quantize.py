"""Quantiser tests: nearest-colour correctness, dither behaviour, and the off-palette audit."""
import numpy as np
import pytest
from PIL import Image

from stepix.palette import PALETTE_SIZE, StePalette, build_ramp
from stepix.quantize import (DITHER_MATRICES, PaletteReport, check_palettized, indices_to_rgb,
                             palette_lookup, quantize_image)

IMAGE_H, IMAGE_W = 16, 64


@pytest.fixture
def palette():
    return StePalette.build((0, 0, 1), build_ramp(10.0, 7, 0.8) + build_ramp(210.0, 8, 0.25))


def _gradient():
    return np.tile(np.linspace(0, 255, IMAGE_W)[None, :, None], (IMAGE_H, 1, 3))


def test_exact_palette_colours_map_to_their_own_index(palette):
    rgb = palette.to_rgb888()[None, :, :].astype(np.uint8)
    assert np.array_equal(quantize_image(rgb, palette)[0], np.arange(PALETTE_SIZE, dtype=np.uint8))


def test_quantize_accepts_a_pil_image(palette):
    image = Image.fromarray(_gradient().astype(np.uint8), mode="RGB")
    assert quantize_image(image, palette).shape == (IMAGE_H, IMAGE_W)


def test_quantize_output_is_in_range(palette):
    indices = quantize_image(_gradient(), palette)
    assert indices.dtype == np.uint8
    assert int(indices.max()) < PALETTE_SIZE


def test_black_and_white_pick_the_extreme_entries(palette):
    """A hue-blind RGB search can land white on a light blue; Lab must not."""
    probe = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    darkest = int(np.argmin(palette.to_lab()[:, 0]))
    lightest = int(np.argmax(palette.to_lab()[:, 0]))
    assert quantize_image(probe, palette)[0].tolist() == [darkest, lightest]


@pytest.mark.parametrize("dither", sorted(DITHER_MATRICES))
def test_dither_changes_some_pixels_but_not_the_average_much(dither, palette):
    plain = quantize_image(_gradient(), palette)
    dithered = quantize_image(_gradient(), palette, dither)
    assert (plain != dithered).any(), "dither did nothing"
    plain_rgb = indices_to_rgb(plain, palette).astype(float)
    dithered_rgb = indices_to_rgb(dithered, palette).astype(float)
    assert abs(plain_rgb.mean() - dithered_rgb.mean()) < 8.0     # ordered dither is zero-mean


def test_dither_pattern_repeats_with_its_tile(palette):
    """Ordered dither must tile, or a repeated wall texture shows a seam at every repeat."""
    flat = np.full((8, 8, 3), 100, dtype=np.uint8)
    dithered = quantize_image(flat, palette, "bayer4")
    assert np.array_equal(dithered[:4, :4], dithered[4:, 4:])


def test_unknown_dither_rejected(palette):
    with pytest.raises(ValueError):
        quantize_image(_gradient(), palette, "floyd")


def test_indices_to_rgb_round_trips_through_quantize(palette):
    indices = quantize_image(_gradient(), palette)
    assert np.array_equal(quantize_image(indices_to_rgb(indices, palette), palette), indices)


def test_indices_to_rgb_rejects_out_of_palette_index(palette):
    with pytest.raises(ValueError):
        indices_to_rgb(np.array([[PALETTE_SIZE]], dtype=np.uint8), palette)


def test_check_palettized_passes_clean_art(palette):
    clean = indices_to_rgb(quantize_image(_gradient(), palette), palette)
    report = check_palettized(clean, palette)
    assert report.clean and report.off_palette_pixels == 0
    assert "clean" in report.describe()


def test_check_palettized_locates_every_stray_pixel(palette):
    art = indices_to_rgb(quantize_image(_gradient(), palette), palette).copy()
    art[2, 3] = (1, 2, 3)
    art[9, 40] = (1, 2, 3)
    art[0, 0] = (250, 251, 252)
    report = check_palettized(art, palette)
    assert not report.clean
    assert report.off_palette_pixels == 3
    assert report.distinct_offending_colours == 2
    assert report.offenders[0][:2] == ((1, 2, 3), 2)         # most frequent offender first
    assert report.offenders[0][2] == (2, 3)                  # first occurrence, (row, col)


def test_check_palettized_reports_total_pixels(palette):
    report = check_palettized(np.zeros((4, 5, 3), dtype=np.uint8), palette)
    assert report.total_pixels == 20
    assert isinstance(report, PaletteReport)


def test_palette_lookup_handles_a_flat_colour_list(palette):
    assert palette_lookup(palette.to_rgb888(), palette).tolist() == list(range(PALETTE_SIZE))


def test_non_rgb_input_rejected(palette):
    with pytest.raises(ValueError):
        quantize_image(np.zeros((4, 4), dtype=np.uint8), palette)


@pytest.mark.parametrize("stray", [(300, 0, 0), (-5, 0, 0), (0, 0, 999)])
def test_check_palettized_reports_out_of_range_channels(palette, stray):
    """Channels outside 0..255 cannot be a palette colour, and must not be able to carry into
    a neighbouring channel of the packed match key and alias onto one."""
    art = np.tile(palette.to_rgb888()[0].astype(np.float64), (4, 4, 1))
    art[1, 2] = stray
    report = check_palettized(art, palette)
    assert report.off_palette_pixels == 1
    assert report.offenders[0][0] == stray
    assert report.offenders[0][2] == (1, 2)
