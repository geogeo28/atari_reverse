"""Wall textures in the raycaster's own format: 64x64 bytes, COLUMN-MAJOR.

WHY column-major: a raycaster draws one screen column from one texture column. With
row-major storage that inner loop strides 64 bytes per texel and misses on every fetch;
stored column-major, texel (x, y) sits at x*64 + y, so once the column base x*64 is in an
address register the whole column is a contiguous walk -- `move.b (a0)+,d0` with the
fractional step folded into the caller's stepper. One byte per texel (not 4 bits) because
unpacking a nibble costs a shift and a mask per texel in the hottest loop in the game; the
texels go through a chunky buffer and a c2p pass anyway, so bytes are the natural unit.

The dark-side variant is the N-S vs E-W lighting cue. It is baked at build time through a
16-entry shade remap table rather than computed per texel: at runtime the "darker" texture
is just a different base pointer, costing nothing per pixel.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from .blob import c_byte_array, fixed_name_field
from .colourspace import linear_to_srgb, srgb_to_lab, srgb_to_linear
from .palette import PALETTE_SIZE, StePalette, check_index_range

TEXTURE_DIM = 64                                    # 64x64 texels: a power of two, so the
TEXTURE_BYTES = TEXTURE_DIM * TEXTURE_DIM           # texture coordinate wraps with an AND
SHADE_TABLE_ENTRIES = PALETTE_SIZE
DEFAULT_DARK_FACTOR = 0.55                          # linear-light scale for the shaded side

TEXTURE_MAGIC = b"STXT"
TEXTURE_FORMAT_VERSION = 1
TEXTURE_NAME_BYTES = 8
TEXTURE_ENTRY_BYTES = TEXTURE_NAME_BYTES + 4        # name8 + u32 offset
TEXTURE_HEADER_BYTES = 12                           # magic4 + version2 + count2 + dim2 + flags2
TEX_FLAG_DARK = 0x0001                              # each entry carries a dark variant


@dataclass(frozen=True)
class Texture:
    """One named wall texture as (dim, dim) uint8 palette indices, row-major in Python."""

    name: str
    indices: np.ndarray

    def __post_init__(self) -> None:
        if self.indices.shape != (TEXTURE_DIM, TEXTURE_DIM):
            raise ValueError(f"texture {self.name!r} must be {TEXTURE_DIM}x{TEXTURE_DIM}, got {self.indices.shape}")
        check_index_range(self.indices, f"texture {self.name!r}")
        if len(self.name.encode("ascii")) > TEXTURE_NAME_BYTES:
            raise ValueError(f"texture name {self.name!r} exceeds {TEXTURE_NAME_BYTES} bytes")


def to_column_major(indices: np.ndarray) -> bytes:
    """(h, w) indices -> column-major bytes: texel (x, y) lands at x*height + y."""
    idx = np.asarray(indices)
    if idx.ndim != 2:
        raise ValueError(f"expected a 2-D index image, got shape {idx.shape}")
    check_index_range(idx, "index image")       # before the cast: uint8 would wrap 256 to 0
    return np.ascontiguousarray(idx.astype(np.uint8, copy=False).T).tobytes()


def from_column_major(data: bytes, width: int, height: int) -> np.ndarray:
    """Column-major bytes -> (height, width) indices. Exact inverse of `to_column_major`."""
    if len(data) != width * height:
        raise ValueError(f"expected {width * height} bytes for {width}x{height}, got {len(data)}")
    return np.frombuffer(data, dtype=np.uint8).reshape(width, height).T.copy()


def build_shade_table(palette: StePalette, factor: float = DEFAULT_DARK_FACTOR,
                      fixed_indices: frozenset[int] = frozenset()) -> bytes:
    """16-byte index->index table darkening each palette entry by `factor` in LINEAR light.

    Scaling in linear light (not in the 0..15 register values) is what makes the shaded side
    read as the same surface under less light rather than as a different, muddier material.

    The nearest match is searched only among entries that are NOT lighter than the source.
    An unconstrained Lab search does not respect that: on a coarse 16-colour ramp the nearest
    neighbour of a darkened saturated red was measured landing on a *lighter* entry, which
    inverts the whole N-S vs E-W lighting cue. Where a strictly darker candidate exists the
    table is forced onto one, so no index silently shades to itself and loses the cue.

    `fixed_indices` are protected in BOTH directions -- they map to themselves, and no other
    index may shade onto them. Sprites pass the transparency key: shading a visible colour
    onto it would punch a hole in the dark variant, which is the same bug seen from the other
    side as remapping the key onto a visible colour.
    """
    if not 0.0 < factor <= 1.0:
        raise ValueError(f"dark factor {factor} must be in (0, 1]")
    for index in fixed_indices:
        if not 0 <= index < SHADE_TABLE_ENTRIES:
            raise ValueError(f"fixed index {index} outside 0..{SHADE_TABLE_ENTRIES - 1}")
    forbidden = np.array(sorted(fixed_indices), dtype=np.intp)
    rgb = palette.to_rgb888().astype(np.float64)
    palette_lab = palette.to_lab()
    darkened_lab = srgb_to_lab(linear_to_srgb(srgb_to_linear(rgb) * factor))
    lightness = palette_lab[:, 0]

    table = []
    for index in range(SHADE_TABLE_ENTRIES):
        strictly_darker = np.setdiff1d(np.flatnonzero(lightness < lightness[index]), forbidden)
        candidates = strictly_darker if strictly_darker.size else np.array([index])
        deltas = palette_lab[candidates] - darkened_lab[index]
        table.append(int(candidates[int(np.argmin(np.einsum("mc,mc->m", deltas, deltas)))]))

    for index in fixed_indices:
        table[index] = index
    return bytes(table)


def apply_shade_table(indices: np.ndarray, table: bytes) -> np.ndarray:
    """Remap every index through a 16-entry shade table."""
    if len(table) != SHADE_TABLE_ENTRIES:
        raise ValueError(f"a shade table is {SHADE_TABLE_ENTRIES} bytes, got {len(table)}")
    return np.frombuffer(table, dtype=np.uint8)[np.asarray(indices, dtype=np.uint8)]


def pack_textures(textures: list[Texture], shade_table: bytes | None = None) -> bytes:
    """Serialise textures to the .TEX blob. With a shade table each entry gains a dark copy."""
    with_dark = shade_table is not None
    flags = TEX_FLAG_DARK if with_dark else 0
    variants = 2 if with_dark else 1
    header = struct.pack(">4sHHHH", TEXTURE_MAGIC, TEXTURE_FORMAT_VERSION, len(textures), TEXTURE_DIM, flags)

    data_start = TEXTURE_HEADER_BYTES + TEXTURE_ENTRY_BYTES * len(textures)
    entries, payload = bytearray(), bytearray()
    for position, texture in enumerate(textures):
        entries += fixed_name_field(texture.name, TEXTURE_NAME_BYTES) + struct.pack(">I", data_start + position * variants * TEXTURE_BYTES)
        payload += to_column_major(texture.indices)
        if with_dark:
            payload += to_column_major(apply_shade_table(texture.indices, shade_table))
    return header + bytes(entries) + bytes(payload)


@dataclass(frozen=True)
class PackedTexture:
    """One entry read back out of a .TEX blob."""

    name: str
    lit: np.ndarray
    dark: np.ndarray | None


def parse_textures(blob: bytes) -> list[PackedTexture]:
    """Read a .TEX blob back; the round-trip test for `pack_textures` and a loader reference."""
    if len(blob) < TEXTURE_HEADER_BYTES:
        raise ValueError("blob is shorter than a texture header")
    magic, version, count, dim, flags = struct.unpack_from(">4sHHHH", blob, 0)
    if magic != TEXTURE_MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {TEXTURE_MAGIC!r}")
    if version != TEXTURE_FORMAT_VERSION:
        raise ValueError(f"unsupported texture format version {version}")

    texel_bytes = dim * dim
    with_dark = bool(flags & TEX_FLAG_DARK)
    out: list[PackedTexture] = []
    for position in range(count):
        name_bytes, offset = struct.unpack_from(f">{TEXTURE_NAME_BYTES}sI", blob, TEXTURE_HEADER_BYTES + position * TEXTURE_ENTRY_BYTES)
        lit = from_column_major(blob[offset:offset + texel_bytes], dim, dim)
        dark = from_column_major(blob[offset + texel_bytes:offset + 2 * texel_bytes], dim, dim) if with_dark else None
        out.append(PackedTexture(name_bytes.rstrip(b"\0").decode("ascii"), lit, dark))
    return out


def texture_to_c_array(texture: Texture, name: str | None = None, shade_table: bytes | None = None) -> str:
    """Emit one texture (and optionally its dark variant) as a C byte array, column-major."""
    symbol = (name or texture.name).lower()
    comment = f"{TEXTURE_DIM}x{TEXTURE_DIM} column-major texels: texel (x,y) at x*{TEXTURE_DIM}+y"
    parts = [c_byte_array(f"tex_{symbol}", to_column_major(texture.indices), comment)]
    if shade_table is not None:
        dark = to_column_major(apply_shade_table(texture.indices, shade_table))
        parts.append(c_byte_array(f"tex_{symbol}_dark", dark, comment))
    return "\n".join(parts)


def shade_table_to_c_array(table: bytes, symbol: str = "shade_table_dark") -> str:
    """Emit the shade table as C, so the engine can also shade at runtime if it ever needs to."""
    body = ",".join(f"0x{b:02x}" for b in table)
    return (f"/* index -> darker index, for the N-S vs E-W wall lighting cue */\n"
            f"static const unsigned char {symbol}[{SHADE_TABLE_ENTRIES}] = {{{body}}};\n")
