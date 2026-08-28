"""Sprite tests: span tables, blob layout, and the HUD mask/data pair."""
import struct

import numpy as np
import pytest

from stepix.palette import PALETTE_SIZE
from stepix.planar import PIXELS_PER_CHUNK, planar_to_indices
from stepix.sprite import (SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST, SPAN_TABLE_BYTES, SPRITE_BYTES,
                           SPRITE_DIM, SPRITE_ENTRY_BYTES, SPRITE_HEADER_BYTES, SPRITE_MAGIC,
                           SPRITE_RECORD_BYTES, TRANSPARENT_INDEX, Sprite, column_spans, hud_blit,
                           hud_blit_to_c_array, hud_blit_to_indices, pack_sprites, parse_sprites,
                           sprite_record)
from stepix.texture import to_column_major


def _sprite_art(seed=1):
    """An opaque blob inside a transparent field, so most columns have a real span."""
    rng = np.random.default_rng(seed)
    art = np.full((SPRITE_DIM, SPRITE_DIM), TRANSPARENT_INDEX, dtype=np.uint8)
    art[10:40, 5:50] = rng.integers(0, TRANSPARENT_INDEX, (30, 45), dtype=np.uint8)
    return art


def test_transparent_index_is_fifteen_not_zero():
    """Index 0 is the border colour and the darkest wall ink; the key has to be elsewhere."""
    assert TRANSPARENT_INDEX == 15


def test_span_table_size_and_values():
    art = _sprite_art()
    spans = column_spans(art)
    assert len(spans) == SPAN_TABLE_BYTES == 2 * SPRITE_DIM
    assert (spans[0], spans[1]) == (SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST)      # column 0 is empty
    assert (spans[2 * 10], spans[2 * 10 + 1]) == (10, 39)                   # column 10 spans rows 10..39


def test_empty_column_is_skipped_by_the_first_greater_than_last_test():
    empty = np.full((SPRITE_DIM, SPRITE_DIM), TRANSPARENT_INDEX, dtype=np.uint8)
    spans = column_spans(empty)
    for column in range(SPRITE_DIM):
        assert spans[2 * column] > spans[2 * column + 1]


def test_spans_bound_exactly_the_opaque_texels():
    art = _sprite_art(2)
    spans = column_spans(art)
    for column in range(SPRITE_DIM):
        first, last = spans[2 * column], spans[2 * column + 1]
        opaque_rows = np.flatnonzero(art[:, column] != TRANSPARENT_INDEX)
        if opaque_rows.size == 0:
            assert first > last
        else:
            assert (first, last) == (int(opaque_rows[0]), int(opaque_rows[-1]))
            assert (art[first:last + 1, column] != TRANSPARENT_INDEX).any()


def test_span_respects_a_custom_key():
    art = np.zeros((SPRITE_DIM, SPRITE_DIM), dtype=np.uint8)
    art[7, 3] = 5
    spans = column_spans(art, transparent_index=0)
    assert (spans[2 * 3], spans[2 * 3 + 1]) == (7, 7)


def test_record_is_spans_then_column_major_texels():
    sprite = Sprite("BARREL", _sprite_art(3))
    record = sprite_record(sprite)
    assert len(record) == SPRITE_RECORD_BYTES == SPAN_TABLE_BYTES + SPRITE_BYTES
    assert record[:SPAN_TABLE_BYTES] == column_spans(sprite.indices)
    assert record[SPAN_TABLE_BYTES:] == to_column_major(sprite.indices)


def test_sprite_rejects_wrong_size_or_index_or_name():
    with pytest.raises(ValueError):
        Sprite("S", np.zeros((8, 8), dtype=np.uint8))
    with pytest.raises(ValueError):
        Sprite("S", np.full((SPRITE_DIM, SPRITE_DIM), PALETTE_SIZE, dtype=np.uint8))
    with pytest.raises(ValueError):
        Sprite("WAYTOOLONG", _sprite_art())


def test_blob_header_and_round_trip():
    sprites = [Sprite("BARREL", _sprite_art(4)), Sprite("AMMO", _sprite_art(5))]
    blob = pack_sprites(sprites)
    magic, version, count, dim, key = struct.unpack_from(">4sHHHH", blob, 0)
    assert magic == SPRITE_MAGIC and version == 1 and count == 2
    assert dim == SPRITE_DIM and key == TRANSPARENT_INDEX
    assert len(blob) == SPRITE_HEADER_BYTES + 2 * SPRITE_ENTRY_BYTES + 2 * SPRITE_RECORD_BYTES

    parsed = parse_sprites(blob)
    assert [entry.name for entry in parsed] == ["BARREL", "AMMO"]
    for entry, sprite in zip(parsed, sprites):
        assert np.array_equal(entry.indices, sprite.indices)
        assert entry.spans == column_spans(sprite.indices)


def test_parse_rejects_bad_magic_and_version():
    blob = bytearray(pack_sprites([Sprite("A", _sprite_art(6))]))
    with pytest.raises(ValueError):
        parse_sprites(b"XXXX" + bytes(blob[4:]))
    blob[5] = 7
    with pytest.raises(ValueError):
        parse_sprites(bytes(blob))


# ---- HUD blit -----------------------------------------------------------------------
def test_hud_mask_bit_is_set_where_the_art_is_transparent():
    art = np.zeros((1, PIXELS_PER_CHUNK), dtype=np.uint8)
    art[0, 0] = TRANSPARENT_INDEX               # leftmost pixel is a hole
    blit = hud_blit(art)
    assert blit.mask == b"\x80\x00"             # bit 15 set: the AND keeps the background there


def test_hud_data_is_zero_under_the_holes():
    art = np.full((1, PIXELS_PER_CHUNK), TRANSPARENT_INDEX, dtype=np.uint8)
    art[0, 3] = 9
    blit = hud_blit(art)
    recovered = planar_to_indices(blit.data, blit.width, blit.height)
    assert recovered[0, 3] == 9
    assert set(recovered[0, [0, 1, 2, 4]].tolist()) == {0}, "OR data must not leak under the mask"


def test_hud_round_trip_restores_the_key():
    art = _sprite_art(7)
    assert np.array_equal(hud_blit_to_indices(hud_blit(art)), art)


def test_hud_geometry():
    blit = hud_blit(np.full((32, 32), TRANSPARENT_INDEX, dtype=np.uint8))
    assert blit.chunks_per_row == 2
    assert blit.data_row_bytes == 16 and blit.mask_row_bytes == 4
    assert len(blit.data) == 32 * 16 and len(blit.mask) == 32 * 4


def test_hud_width_must_be_a_multiple_of_sixteen():
    """Fixed-position HUD art is never pre-shifted, so a ragged width is a bug, not a feature."""
    with pytest.raises(ValueError):
        hud_blit(np.zeros((4, 20), dtype=np.uint8))


def test_hud_c_array_emits_geometry_and_both_arrays():
    text = hud_blit_to_c_array(hud_blit(_sprite_art(8)), "icon")
    assert "#define ICON_W 64" in text and "#define ICON_MASK_ROW_BYTES 8" in text
    assert "icon_data[" in text and "icon_mask[" in text


def test_packed_sprite_carries_the_blobs_own_transparency_key():
    """The key is a property of the blob: a reader must mask with what the art was packed
    against, not with whatever TRANSPARENT_INDEX happens to be compiled in."""
    art = _sprite_art()
    key = 3
    blob = pack_sprites([Sprite("BARREL", art)], transparent_index=key)
    assert struct.unpack_from(">H", blob, 10)[0] == key
    parsed = parse_sprites(blob)[0]
    assert parsed.transparent_index == key
    assert parsed.spans == column_spans(art, key)


@pytest.mark.parametrize("bad_index", [PALETTE_SIZE, -1])
def test_sprite_rejects_out_of_range_indices(bad_index):
    art = np.zeros((SPRITE_DIM, SPRITE_DIM), dtype=np.int32)
    art[0, 0] = bad_index
    with pytest.raises(ValueError):
        Sprite("BAD", art)
