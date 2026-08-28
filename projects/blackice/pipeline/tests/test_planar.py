"""Planar tests: the bit layout is pinned by hand-computed words, not just by a round-trip.

A round-trip alone would pass happily with the planes in the wrong order or the pixels
mirrored inside the word -- both bugs that look plausible on screen.
"""
import numpy as np
import pytest

from stepix.palette import PALETTE_SIZE, StePalette, build_ramp
from stepix.planar import (BYTES_PER_CHUNK, PI1_BYTES, PI1_HEADER_BYTES, PIXELS_PER_CHUNK, PLANES,
                           SCREEN_BYTES, SCREEN_H, SCREEN_ROW_BYTES, SCREEN_W, indices_to_planar,
                           pi1_bytes, planar_to_indices, read_pi1, screen_to_planar, write_pi1)


@pytest.fixture
def palette():
    return StePalette.build((0, 0, 1), build_ramp(20.0, 7, 0.7) + build_ramp(200.0, 8, 0.3))


def test_screen_geometry_constants():
    assert SCREEN_ROW_BYTES == 160
    assert SCREEN_BYTES == 32000 == SCREEN_W * SCREEN_H * PLANES // 8
    assert BYTES_PER_CHUNK == 8


def test_leftmost_pixel_is_bit_15_of_plane_0():
    art = np.zeros((1, PIXELS_PER_CHUNK), dtype=np.uint8)
    art[0, 0] = 1
    assert indices_to_planar(art) == bytes.fromhex("8000000000000000")


def test_rightmost_pixel_index_8_sets_only_plane_3_bit_0():
    art = np.zeros((1, PIXELS_PER_CHUNK), dtype=np.uint8)
    art[0, PIXELS_PER_CHUNK - 1] = 8
    assert indices_to_planar(art) == bytes.fromhex("0000000000000001")


def test_plane_order_is_lsb_first():
    """Index 5 = planes 0 and 2: getting the order wrong swaps colours without moving pixels."""
    art = np.full((1, PIXELS_PER_CHUNK), 5, dtype=np.uint8)
    assert indices_to_planar(art) == bytes.fromhex("ffff0000ffff0000")


def test_all_ones_sets_every_plane():
    art = np.full((1, PIXELS_PER_CHUNK), 15, dtype=np.uint8)
    assert indices_to_planar(art) == b"\xff" * BYTES_PER_CHUNK


@pytest.mark.parametrize("width,height", [(16, 1), (32, 3), (64, 64), (320, 200), (48, 7)])
def test_round_trip_random_art(width, height):
    rng = np.random.default_rng(width * height)
    art = rng.integers(0, 16, (height, width), dtype=np.uint8)
    assert np.array_equal(planar_to_indices(indices_to_planar(art), width, height), art)


def test_row_stride_matches_the_hardware():
    art = np.zeros((2, SCREEN_W), dtype=np.uint8)
    art[1, 0] = 15
    blob = indices_to_planar(art)
    assert blob[:SCREEN_ROW_BYTES] == bytes(SCREEN_ROW_BYTES)
    assert blob[SCREEN_ROW_BYTES:SCREEN_ROW_BYTES + BYTES_PER_CHUNK] == bytes.fromhex("8000800080008000")


def test_width_must_be_a_multiple_of_sixteen():
    with pytest.raises(ValueError):
        indices_to_planar(np.zeros((1, 20), dtype=np.uint8))
    with pytest.raises(ValueError):
        planar_to_indices(b"\0" * 8, 20, 1)


def test_index_outside_palette_rejected():
    with pytest.raises(ValueError):
        indices_to_planar(np.full((1, PIXELS_PER_CHUNK), 16, dtype=np.uint8))


def test_planar_to_indices_checks_length():
    with pytest.raises(ValueError):
        planar_to_indices(b"\0" * 7, 16, 1)


def test_screen_to_planar_rejects_wrong_size():
    with pytest.raises(ValueError):
        screen_to_planar(np.zeros((100, 320), dtype=np.uint8))


def _screen(seed=5):
    return np.random.default_rng(seed).integers(0, 16, (SCREEN_H, SCREEN_W), dtype=np.uint8)


def test_pi1_layout_and_round_trip(palette):
    art = _screen()
    blob = pi1_bytes(art, palette)
    assert len(blob) == PI1_BYTES == 34 + 32000
    assert blob[:2] == b"\x00\x00"                                  # low resolution
    assert blob[2:PI1_HEADER_BYTES] == palette.to_bytes()
    recovered_art, recovered_palette = read_pi1(blob)
    assert np.array_equal(recovered_art, art)
    assert recovered_palette == palette


def test_pi1_rejects_a_truncated_file():
    with pytest.raises(ValueError):
        read_pi1(b"\0" * (PI1_BYTES - 1))


def test_pi1_rejects_a_non_low_resolution_file(palette):
    blob = bytearray(pi1_bytes(_screen(), palette))
    blob[1] = 1
    with pytest.raises(ValueError):
        read_pi1(bytes(blob))


def test_write_pi1_writes_the_file(tmp_path, palette):
    path = tmp_path / "art.pi1"
    assert write_pi1(str(path), _screen(), palette) == PI1_BYTES
    assert path.stat().st_size == PI1_BYTES


@pytest.mark.parametrize("bad_index", [PALETTE_SIZE, PALETTE_SIZE + 1, 256, -1])
def test_out_of_range_indices_are_rejected_before_the_uint8_cast(bad_index):
    """The cast is silent: 256 lands as 0 and -1 as 255, so art with a bad index used to be
    encoded as art with the wrong colour."""
    art = np.zeros((1, PIXELS_PER_CHUNK), dtype=np.int32)
    art[0, 3] = bad_index
    with pytest.raises(ValueError):
        indices_to_planar(art)
