"""Texture tests: column-major addressing, the shade table's darkening rule, blob layout."""
import struct

import numpy as np
import pytest

from stepix.colourspace import lab_lightness
from stepix.palette import PALETTE_SIZE, StePalette, build_ramp
from stepix.texture import (DEFAULT_DARK_FACTOR, SHADE_TABLE_ENTRIES, TEXTURE_BYTES, TEXTURE_DIM,
                            TEXTURE_ENTRY_BYTES, TEXTURE_HEADER_BYTES, TEXTURE_MAGIC, TEX_FLAG_DARK,
                            Texture, apply_shade_table, build_shade_table, from_column_major,
                            pack_textures, parse_textures, shade_table_to_c_array, texture_to_c_array,
                            to_column_major)


@pytest.fixture
def palette():
    return StePalette.build((0, 0, 1), build_ramp(12.0, 7, 0.7) + build_ramp(210.0, 8, 0.2))


def _art(seed=1):
    return np.random.default_rng(seed).integers(0, PALETTE_SIZE, (TEXTURE_DIM, TEXTURE_DIM), dtype=np.uint8)


def test_texel_address_is_x_times_dim_plus_y():
    """The whole point of the format: a column is contiguous. Pin the address arithmetic."""
    art = _art()
    blob = to_column_major(art)
    assert len(blob) == TEXTURE_BYTES == 4096
    for x, y in [(0, 0), (0, 63), (63, 0), (3, 5), (17, 41), (63, 63)]:
        assert blob[x * TEXTURE_DIM + y] == art[y, x], (x, y)


def test_column_major_round_trip():
    art = _art(2)
    assert np.array_equal(from_column_major(to_column_major(art), TEXTURE_DIM, TEXTURE_DIM), art)


def test_a_whole_column_is_contiguous():
    art = np.zeros((TEXTURE_DIM, TEXTURE_DIM), dtype=np.uint8)
    art[:, 9] = np.arange(TEXTURE_DIM, dtype=np.uint8) % PALETTE_SIZE
    blob = to_column_major(art)
    assert list(blob[9 * TEXTURE_DIM:10 * TEXTURE_DIM]) == [row % PALETTE_SIZE for row in range(TEXTURE_DIM)]


def test_from_column_major_checks_length():
    with pytest.raises(ValueError):
        from_column_major(b"\0" * 10, TEXTURE_DIM, TEXTURE_DIM)


def test_texture_rejects_wrong_size_or_out_of_palette_index():
    with pytest.raises(ValueError):
        Texture("SMALL", np.zeros((8, 8), dtype=np.uint8))
    with pytest.raises(ValueError):
        Texture("HOT", np.full((TEXTURE_DIM, TEXTURE_DIM), PALETTE_SIZE, dtype=np.uint8))
    with pytest.raises(ValueError):
        Texture("TOOLONGNAME", _art())


def test_shade_table_never_brightens(palette):
    """An unconstrained nearest-Lab search was measured mapping a colour to a lighter one,
    which inverts the N-S vs E-W cue. This is the regression pin."""
    table = build_shade_table(palette, DEFAULT_DARK_FACTOR)
    lightness = lab_lightness(palette.to_rgb888().astype(float))
    for index in range(SHADE_TABLE_ENTRIES):
        assert lightness[table[index]] <= lightness[index] + 1e-9, index


def test_shade_table_darkens_every_index_that_can_be_darkened(palette):
    table = build_shade_table(palette, DEFAULT_DARK_FACTOR)
    lightness = lab_lightness(palette.to_rgb888().astype(float))
    darkest = int(np.argmin(lightness))
    for index in range(SHADE_TABLE_ENTRIES):
        if index != darkest:
            assert table[index] != index, f"index {index} shades to itself: the cue vanishes"


def test_shade_table_length_and_range(palette):
    table = build_shade_table(palette)
    assert len(table) == SHADE_TABLE_ENTRIES == 16
    assert all(0 <= entry < PALETTE_SIZE for entry in table)


def test_fixed_indices_are_passed_through(palette):
    table = build_shade_table(palette, fixed_indices=frozenset({15, 3}))
    assert table[15] == 15 and table[3] == 3


def test_fixed_index_out_of_range_rejected(palette):
    with pytest.raises(ValueError):
        build_shade_table(palette, fixed_indices=frozenset({PALETTE_SIZE}))


@pytest.mark.parametrize("factor", [0.0, -0.5, 1.5])
def test_bad_dark_factor_rejected(palette, factor):
    with pytest.raises(ValueError):
        build_shade_table(palette, factor)


def test_apply_shade_table_maps_every_texel(palette):
    table = build_shade_table(palette)
    art = _art(3)
    shaded = apply_shade_table(art, table)
    assert shaded.shape == art.shape
    assert np.array_equal(shaded, np.frombuffer(table, dtype=np.uint8)[art])


def test_apply_shade_table_checks_table_length():
    with pytest.raises(ValueError):
        apply_shade_table(_art(), b"\0" * 8)


def test_blob_header_and_round_trip(palette):
    table = build_shade_table(palette)
    textures = [Texture("BRICK", _art(4)), Texture("METAL", _art(5))]
    blob = pack_textures(textures, table)

    magic, version, count, dim, flags = struct.unpack_from(">4sHHHH", blob, 0)
    assert magic == TEXTURE_MAGIC and version == 1 and count == 2 and dim == TEXTURE_DIM
    assert flags & TEX_FLAG_DARK
    assert len(blob) == TEXTURE_HEADER_BYTES + 2 * TEXTURE_ENTRY_BYTES + 2 * 2 * TEXTURE_BYTES

    parsed = parse_textures(blob)
    assert [entry.name for entry in parsed] == ["BRICK", "METAL"]
    for entry, texture in zip(parsed, textures):
        assert np.array_equal(entry.lit, texture.indices)
        assert np.array_equal(entry.dark, apply_shade_table(texture.indices, table))


def test_entry_offsets_point_at_the_texels(palette):
    textures = [Texture("A", _art(6)), Texture("B", _art(7))]
    blob = pack_textures(textures, build_shade_table(palette))
    for position, texture in enumerate(textures):
        offset = struct.unpack_from(">I", blob, TEXTURE_HEADER_BYTES + position * TEXTURE_ENTRY_BYTES + 8)[0]
        assert blob[offset:offset + TEXTURE_BYTES] == to_column_major(texture.indices)


def test_blob_without_a_shade_table_has_no_dark_variants():
    blob = pack_textures([Texture("BRICK", _art(8))])
    assert struct.unpack_from(">H", blob, 10)[0] & TEX_FLAG_DARK == 0
    parsed = parse_textures(blob)
    assert parsed[0].dark is None
    assert len(blob) == TEXTURE_HEADER_BYTES + TEXTURE_ENTRY_BYTES + TEXTURE_BYTES


def test_parse_rejects_bad_magic_and_version():
    blob = bytearray(pack_textures([Texture("A", _art(9))]))
    bad_magic = bytes(b"XXXX" + blob[4:])
    with pytest.raises(ValueError):
        parse_textures(bad_magic)
    blob[5] = 9
    with pytest.raises(ValueError):
        parse_textures(bytes(blob))


def test_c_arrays_emit_both_variants(palette):
    table = build_shade_table(palette)
    text = texture_to_c_array(Texture("BRICK", _art(10)), shade_table=table)
    assert f"tex_brick[{TEXTURE_BYTES}]" in text
    assert f"tex_brick_dark[{TEXTURE_BYTES}]" in text
    assert shade_table_to_c_array(table).count("0x") == SHADE_TABLE_ENTRIES


@pytest.mark.parametrize("bad_index", [PALETTE_SIZE, 256, -1])
def test_to_column_major_rejects_out_of_range_indices(bad_index):
    """It used to cast straight to uint8, so index 256 was written to disk as index 0."""
    art = np.zeros((TEXTURE_DIM, TEXTURE_DIM), dtype=np.int32)
    art[7, 9] = bad_index
    with pytest.raises(ValueError):
        to_column_major(art)


@pytest.mark.parametrize("bad_index", [PALETTE_SIZE, -1])
def test_texture_rejects_out_of_range_indices(bad_index):
    art = np.zeros((TEXTURE_DIM, TEXTURE_DIM), dtype=np.int32)
    art[0, 0] = bad_index
    with pytest.raises(ValueError):
        Texture("BAD", art)


# A palette measured leaking under the old table: index 11 shaded onto the key at index 15,
# so the barrel's dark variant would have been punched full of holes.
LEAKING_PALETTE = StePalette.build(
    (0, 0, 0),
    [(13, 10, 8), (4, 4, 0), (1, 0, 2), (13, 10, 14), (8, 9, 15), (11, 10, 8), (8, 14, 4),
     (13, 10, 0), (6, 13, 8), (0, 12, 11), (13, 2, 1), (13, 0, 8), (1, 4, 7), (6, 6, 0), (12, 3, 0)],
)
LEAKING_SOURCE_INDEX = 11
KEY_INDEX = PALETTE_SIZE - 1


def test_no_index_shades_onto_a_fixed_index():
    """A fixed index is protected in both directions: it maps to itself, and nothing maps TO it.
    Protecting it only as a source left the key a legal darker target."""
    table = build_shade_table(LEAKING_PALETTE, DEFAULT_DARK_FACTOR, frozenset({KEY_INDEX}))
    assert table[LEAKING_SOURCE_INDEX] != KEY_INDEX
    assert [index for index in range(SHADE_TABLE_ENTRIES) if table[index] == KEY_INDEX] == [KEY_INDEX]


@pytest.mark.parametrize("fixed", [frozenset({15}), frozenset({0, 15}), frozenset({3, 7, 15})])
def test_fixed_indices_are_never_a_shade_target(palette, fixed):
    table = build_shade_table(palette, DEFAULT_DARK_FACTOR, fixed)
    for index in range(SHADE_TABLE_ENTRIES):
        assert table[index] not in fixed or index in fixed, f"index {index} shades onto a fixed index"
