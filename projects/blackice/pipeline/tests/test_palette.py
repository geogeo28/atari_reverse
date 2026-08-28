"""Palette tests. The swizzle pairs are hand-computed from the documented rule, not from a
previous run of this code -- otherwise the test only proves the code agrees with itself."""
import numpy as np
import pytest

from stepix.palette import (CHANNEL_MAX, PALETTE_BYTES, PALETTE_SIZE, StePalette, build_ramp,
                            decode_channel, encode_channel, from_ste_word, is_st_compatible,
                            rgb4_to_rgb888, rgb888_to_rgb4, ste_word, to_st_word)

# (r, g, b) 4-bit intensities -> hardware word, each worked out by hand from
# nibble = (v >> 1) | ((v & 1) << 3):
#   15 -> 0b1111 = 0xF   8 -> 0b0100 = 0x4   14 -> 0b0111 = 0x7
#    1 -> 0b1000 = 0x8   7 -> 0b1011 = 0xB    2 -> 0x1, 4 -> 0x2, 6 -> 0x3
KNOWN_PAIRS = [
    ((15, 15, 15), 0x0FFF),     # STE white
    ((0, 0, 0), 0x0000),        # black
    ((8, 8, 8), 0x0444),        # mid grey: NOT 0x0888 -- the swizzle rotates the LSB out
    ((14, 14, 14), 0x0777),     # "ST white": even intensities are ST-compatible
    ((1, 0, 0), 0x0800),        # intensity 1 sets only the STE-only bit 3
    ((7, 0, 0), 0x0B00),
    ((2, 4, 6), 0x0123),
]


@pytest.mark.parametrize("rgb,word", KNOWN_PAIRS)
def test_known_swizzle_pairs(rgb, word):
    assert ste_word(*rgb) == word
    assert from_ste_word(word) == rgb


@pytest.mark.parametrize("intensity", range(CHANNEL_MAX + 1))
def test_channel_codec_round_trips(intensity):
    assert decode_channel(encode_channel(intensity)) == intensity


def test_every_channel_triple_round_trips():
    for red in range(CHANNEL_MAX + 1):
        for green in range(CHANNEL_MAX + 1):
            for blue in range(CHANNEL_MAX + 1):
                assert from_ste_word(ste_word(red, green, blue)) == (red, green, blue)


def test_encoded_word_uses_only_twelve_bits():
    for rgb, word in KNOWN_PAIRS:
        assert 0 <= ste_word(*rgb) <= 0x0FFF, rgb
        assert word >> 12 == 0


def test_even_intensities_are_st_compatible_and_odd_are_not():
    assert is_st_compatible(ste_word(14, 8, 0))
    assert not is_st_compatible(ste_word(15, 8, 0))
    assert to_st_word(ste_word(15, 15, 15)) == ste_word(14, 14, 14)


@pytest.mark.parametrize("bad", [-1, CHANNEL_MAX + 1])
def test_out_of_range_channel_rejected(bad):
    with pytest.raises(ValueError):
        encode_channel(bad)


def test_word_with_top_nibble_set_rejected():
    with pytest.raises(ValueError):
        from_ste_word(0x1FFF)


def test_rgb888_conversion_hits_the_endpoints():
    assert rgb4_to_rgb888((0, 15, 8)) == (0, 255, 136)
    assert rgb888_to_rgb4((0, 255, 136)) == (0, 15, 8)


def _demo_colours():
    return [(index, index, index) for index in range(PALETTE_SIZE)]


def test_palette_bytes_round_trip():
    palette = StePalette(tuple(_demo_colours()))
    blob = palette.to_bytes()
    assert len(blob) == PALETTE_BYTES == 32
    assert StePalette.from_bytes(blob) == palette
    assert StePalette.from_words(palette.to_words()) == palette


def test_palette_bytes_are_big_endian():
    palette = StePalette.build((2, 4, 6), _demo_colours()[1:])
    assert palette.to_bytes()[:2] == b"\x01\x23"        # 0x0123, high byte first


def test_build_pins_background_at_index_zero():
    palette = StePalette.build((1, 2, 3), _demo_colours()[1:])
    assert palette.colours[0] == (1, 2, 3)
    assert palette.background == (1, 2, 3)
    assert palette.with_background((4, 5, 6)).colours[1:] == palette.colours[1:]


def test_build_rejects_wrong_entry_count():
    with pytest.raises(ValueError):
        StePalette.build((0, 0, 0), _demo_colours())        # background + 16 = 17


def test_palette_rejects_out_of_gamut_entry():
    with pytest.raises(ValueError):
        StePalette(tuple([(0, 0, 16)] + _demo_colours()[1:]))


def test_c_array_mentions_every_entry():
    text = StePalette(tuple(_demo_colours())).to_c_array("demo")
    assert f"unsigned short demo[{PALETTE_SIZE}]" in text
    assert text.count("0x") == PALETTE_SIZE


@pytest.mark.parametrize("shades", [2, 3, 4, 6, 8])
def test_ramp_length_and_gamut(shades):
    ramp = build_ramp(30.0, shades, 0.6)
    assert len(ramp) == shades
    assert all(0 <= channel <= CHANNEL_MAX for colour in ramp for channel in colour)


@pytest.mark.parametrize("hue", [0.0, 45.0, 120.0, 210.0, 300.0])
@pytest.mark.parametrize("saturation", [0.15, 0.5, 0.9, 1.0])
def test_ramp_shades_are_distinct_and_brighten(hue, saturation):
    """A ramp with a repeated or non-monotonic shade destroys the lighting cue it exists for."""
    from stepix.colourspace import lab_lightness

    ramp = build_ramp(hue, 5, saturation)
    assert len(set(ramp)) == len(ramp)
    lightness = [float(lab_lightness(np.array(rgb4_to_rgb888(c), dtype=float))) for c in ramp]
    assert lightness == sorted(lightness)


def test_ramp_rejects_degenerate_arguments():
    with pytest.raises(ValueError):
        build_ramp(0.0, 1)
    with pytest.raises(ValueError):
        build_ramp(0.0, 4, saturation=1.5)
    with pytest.raises(ValueError):
        build_ramp(0.0, 4, lightness_min=90.0, lightness_max=10.0)
