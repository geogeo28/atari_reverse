#!/usr/bin/env python3
"""The Atari ST low-res pixel model: bitplane decoding, ST palettes, and PNG building.

Game-agnostic, and the one place this workspace spells any of it out. Import it from a
project's extractor rather than re-deriving the layouts:

    import sys, os
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import st_pixels

The model
---------
A low-res ST pixel is a 4-bit colour index gathered ONE BIT PER BITPLANE, plane 0 being the
index's LSB. The planes are interleaved in memory in fixed-size units, and a unit is either

  * word granular (`unit_bits=16`) - four big-endian plane words, 16 pixels per group. Screens,
    tiles and most bitmaps are this.
  * byte granular (`unit_bits=8`)  - four consecutive plane bytes, 8 pixels per group. Fonts,
    digit glyphs and other 8-px-wide cells are this.

Within a unit the LEFTMOST pixel is the most significant bit.

A *masked* bitmap (a sprite) puts one extra field, the MASK, ahead of the four plane fields of
every group, so a group is five fields wide instead of four. A SET mask bit means "keep the
background", i.e. that pixel is TRANSPARENT - the blitter ANDs the mask, then ORs the data.
`decode_planar` returns `TRANSPARENT` for those pixels and a 0-15 colour index for the rest.

A colour is one `0x0RGB` word with three bits per channel, so 0-7 per channel; `st_word_to_rgb`
scales that to 8-bit as `value * 255 // 7` - the scaling every ST tool in this workspace needs.

Pillow is imported lazily, inside the image builders, so index decoding and palette reading work
without it.
"""

import struct

# --- the pixel model --------------------------------------------------------
PLANES = 4
BITS_PER_BYTE = 8
BYTES_PER_WORD = 2
PIXELS_PER_BYTE = BITS_PER_BYTE
PIXELS_PER_WORD = BYTES_PER_WORD * BITS_PER_BYTE
MASK_FIELDS = 1  # a masked group carries this many fields ahead of the planes

# A masked pixel has no colour index at all, so it needs a value outside 0..15. Beware: it is
# negative, so never use it to subscript a palette list.
TRANSPARENT = -1

# --- colour -----------------------------------------------------------------
PALETTE_ENTRIES = 16
PALETTE_BYTES = PALETTE_ENTRIES * BYTES_PER_WORD
ST_CHANNEL_MAX = 7  # 3 bits per channel
EIGHT_BIT_MAX = 255
OPAQUE = EIGHT_BIT_MAX  # the alpha byte of a non-masked pixel
ST_COLOUR_INVALID = 0xF888  # any of these bits set means it is not a 0-7-per-channel colour


def _unit_bytes(unit_bits):
    if unit_bits not in (PIXELS_PER_BYTE, PIXELS_PER_WORD):
        raise ValueError("unit_bits must be %d or %d, not %r"
                         % (PIXELS_PER_BYTE, PIXELS_PER_WORD, unit_bits))
    return unit_bits // BITS_PER_BYTE


def _fields_per_group(masked):
    """Fields in one group: the four planes, and the mask ahead of them when there is one."""
    return PLANES + (MASK_FIELDS if masked else 0)


def group_bytes(unit_bits=PIXELS_PER_WORD, masked=False):
    """Bytes one interleaved group (the four planes, plus the mask when masked) occupies."""
    return _fields_per_group(masked) * _unit_bytes(unit_bits)


def row_bytes(width, unit_bits=PIXELS_PER_WORD, masked=False):
    """Bytes one pixel row of a `width`-wide bitmap occupies - the stride from row to row."""
    return width // unit_bits * group_bytes(unit_bits, masked)


def image_bytes(width, rows, unit_bits=PIXELS_PER_WORD, masked=False):
    return rows * row_bytes(width, unit_bits, masked)


def _gather(planes, mask, unit_bits):
    """One group's plane (and mask) fields to `unit_bits` colour indices, leftmost pixel first."""
    pixels = []
    for bit in reversed(range(unit_bits)):
        if (mask >> bit) & 1:
            pixels.append(TRANSPARENT)
            continue
        index = 0
        for plane, value in enumerate(planes):
            index |= ((value >> bit) & 1) << plane
        pixels.append(index)
    return pixels


def decode_planar(data, width, rows, offset=0, unit_bits=PIXELS_PER_WORD, masked=False):
    """Interleaved bitplanes at `offset` -> `rows` lists of `width` colour indices.

    Masked pixels come back as TRANSPARENT. This is the one decoder: word- or byte-granular,
    masked or not, are the two axes every ST bitmap in this workspace varies along.
    """
    fields_per_group = _fields_per_group(masked)
    plane_at = MASK_FIELDS if masked else 0
    stride = row_bytes(width, unit_bits, masked)  # also rejects any granularity but 8 or 16 bits
    end = offset + rows * stride
    if end > len(data):
        # A short slice would decode as zeros - a blank, plausible-looking bitmap - which is the
        # one failure that never shows up in the PNG.
        raise ValueError("a %dx%d bitmap at %#x needs %d bytes, the data holds %d: the address is "
                         "wrong or the file is truncated" % (width, rows, offset, end, len(data)))
    groups = width // unit_bits
    row_format = ">%dH" % (groups * fields_per_group)
    out = []
    for row in range(rows):
        base = offset + row * stride
        raw = data[base:base + stride]
        fields = struct.unpack(row_format, raw) if unit_bits == PIXELS_PER_WORD else raw
        pixels = []
        for group in range(groups):
            at = group * fields_per_group
            mask = fields[at] if masked else 0
            planes = fields[at + plane_at:at + fields_per_group]
            pixels += _gather(planes, mask, unit_bits)
        out.append(pixels)
    return out


def split_rows(pixel_rows, frame_rows):
    """A tall decode split into equal frames. The exact multiple is the format's own invariant."""
    if len(pixel_rows) % frame_rows:
        raise ValueError("%d rows do not divide into %d-row frames"
                         % (len(pixel_rows), frame_rows))
    return [pixel_rows[at:at + frame_rows] for at in range(0, len(pixel_rows), frame_rows)]


# --- palettes ---------------------------------------------------------------

def st_word_to_rgb(word):
    """One 0x0RGB colour word to an 8-bit (r, g, b) tuple."""
    channels = ((word >> 8) & ST_CHANNEL_MAX, (word >> 4) & ST_CHANNEL_MAX, word & ST_CHANNEL_MAX)
    return tuple(channel * EIGHT_BIT_MAX // ST_CHANNEL_MAX for channel in channels)


def is_st_colour_word(word):
    """A 0x0RGB word with every channel nibble in 0-7 - the test a palette scan is built on."""
    return (word & ST_COLOUR_INVALID) == 0


def read_palette_words(data, offset, entries=PALETTE_ENTRIES):
    return list(struct.unpack(">%dH" % entries, data[offset:offset + entries * BYTES_PER_WORD]))


def palette_rgb(words):
    return [st_word_to_rgb(word) for word in words]


def read_palette(data, offset, entries=PALETTE_ENTRIES):
    """`entries` colour words at `offset` -> list of 8-bit (r, g, b) tuples."""
    return palette_rgb(read_palette_words(data, offset, entries))


# --- images (the only part that needs Pillow) -------------------------------

def _pil_image():
    try:
        from PIL import Image
    except ImportError as error:
        raise SystemExit("this needs Pillow: run it with the atari_reverse conda env's python "
                         "(the interpreter this workspace supports), or `pip install pillow`") from error
    return Image


def _image_from_buffer(mode, pixel_rows, buffer):
    Image = _pil_image()
    return Image.frombytes(mode, (len(pixel_rows[0]), len(pixel_rows)), bytes(buffer))


def to_rgb_image(pixel_rows, palette):
    """Opaque RGB image. Rejects TRANSPARENT: RGB cannot hold it, and -1 would subscript
    the palette from the end and quietly paint the wrong colour."""
    entries = [bytes(colour) for colour in palette]
    for row in pixel_rows:
        if TRANSPARENT in row:
            raise ValueError("an RGB image cannot hold a masked pixel; use to_rgba_image")
    return _image_from_buffer("RGB", pixel_rows,
                              b"".join(entries[index] for row in pixel_rows for index in row))


def to_rgba_image(pixel_rows, palette):
    """RGBA image with the TRANSPARENT pixels fully transparent and every other one opaque."""
    entries = [bytes(colour) + bytes((OPAQUE,)) for colour in palette]
    clear = bytes(len(entries[0]))
    buffer = b"".join(clear if index == TRANSPARENT else entries[index]
                      for row in pixel_rows for index in row)
    return _image_from_buffer("RGBA", pixel_rows, buffer)


def scaled(image, factor):
    """Nearest-neighbour zoom, so the pixels stay pixels."""
    Image = _pil_image()
    return image.resize((image.width * factor, image.height * factor), Image.NEAREST)
