"""Billboard sprites and HUD-layer blit art.

Two different consumers, so two different formats -- this is the module's whole point:

  * Billboard sprites (enemies, pickups) are drawn by the same scaled column loop as walls,
    so they use the walls' column-major byte layout, plus a per-column span table giving the
    first and last opaque row. Transparent spans are the common case in a billboard, and the
    span table lets the column loop skip them without testing every texel against the key.

  * HUD art (weapon overlay, icons, panel decorations) is drawn at FIXED screen positions on
    16-pixel boundaries, so it needs no pre-shifted rotations: plain interleaved planar data
    plus a 1-plane AND mask is enough, and the blitter (or `and.w`/`or.w`) does the rest.
    Pre-shifting would multiply the art by 16 for motion the HUD never has.

WHY index 15 is the transparency key and not index 0: index 0 is the hardware border colour
and the darkest entry the wall ramps need, so it appears throughout the wall art. Reserving
it would cost the shadow end of every ramp. Index 15 is reserved as a key colour instead: it
is set to a garish magenta that must never appear in wall or HUD art, so a leak is visible
on screen at once rather than silently punching holes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from .blob import c_byte_array, fixed_name_field
from .palette import check_index_range
from .planar import (BYTES_PER_CHUNK, MSB_PIXEL_BIT, PIXELS_PER_CHUNK, PLANES, indices_to_planar,
                     planar_to_indices)
from .texture import TEXTURE_DIM, from_column_major, to_column_major

SPRITE_DIM = TEXTURE_DIM                    # billboards share the walls' 64x64 column loop
SPRITE_BYTES = SPRITE_DIM * SPRITE_DIM
TRANSPARENT_INDEX = 15                      # the reserved key colour; see the module docstring

SPAN_BYTES_PER_COLUMN = 2                   # first opaque row, last opaque row
SPAN_TABLE_BYTES = SPRITE_DIM * SPAN_BYTES_PER_COLUMN
# A fully transparent column is encoded so that the engine's single test `first > last`
# skips it -- no separate "empty" flag to forget to check.
SPAN_EMPTY_FIRST = 0xFF
SPAN_EMPTY_LAST = 0x00

SPRITE_MAGIC = b"STSP"
SPRITE_FORMAT_VERSION = 1
SPRITE_NAME_BYTES = 8
SPRITE_ENTRY_BYTES = SPRITE_NAME_BYTES + 4
SPRITE_HEADER_BYTES = 12                    # magic4 + version2 + count2 + dim2 + key2
SPRITE_RECORD_BYTES = SPAN_TABLE_BYTES + SPRITE_BYTES


@dataclass(frozen=True)
class Sprite:
    """A 64x64 billboard sprite as row-major uint8 indices; TRANSPARENT_INDEX punches holes."""

    name: str
    indices: np.ndarray

    def __post_init__(self) -> None:
        if self.indices.shape != (SPRITE_DIM, SPRITE_DIM):
            raise ValueError(f"sprite {self.name!r} must be {SPRITE_DIM}x{SPRITE_DIM}, got {self.indices.shape}")
        check_index_range(self.indices, f"sprite {self.name!r}")
        if len(self.name.encode("ascii")) > SPRITE_NAME_BYTES:
            raise ValueError(f"sprite name {self.name!r} exceeds {SPRITE_NAME_BYTES} bytes")


def column_spans(indices: np.ndarray, transparent_index: int = TRANSPARENT_INDEX) -> bytes:
    """Per-column (first_opaque_row, last_opaque_row) bytes; empty columns get first > last."""
    idx = np.asarray(indices, dtype=np.uint8)
    height, width = idx.shape
    if height > SPAN_EMPTY_FIRST:
        raise ValueError(f"sprite height {height} exceeds the {SPAN_EMPTY_FIRST}-row span encoding limit")
    opaque = idx != transparent_index
    table = bytearray()
    for column in range(width):
        rows = np.flatnonzero(opaque[:, column])
        if rows.size == 0:
            table += bytes((SPAN_EMPTY_FIRST, SPAN_EMPTY_LAST))
        else:
            table += bytes((int(rows[0]), int(rows[-1])))
    return bytes(table)


def sprite_record(sprite: Sprite, transparent_index: int = TRANSPARENT_INDEX) -> bytes:
    """One sprite's on-disk record: span table then column-major texels."""
    return column_spans(sprite.indices, transparent_index) + to_column_major(sprite.indices)


def pack_sprites(sprites: list[Sprite], transparent_index: int = TRANSPARENT_INDEX) -> bytes:
    """Serialise sprites to the .SPR blob."""
    header = struct.pack(">4sHHHH", SPRITE_MAGIC, SPRITE_FORMAT_VERSION, len(sprites), SPRITE_DIM, transparent_index)
    data_start = SPRITE_HEADER_BYTES + SPRITE_ENTRY_BYTES * len(sprites)
    entries, payload = bytearray(), bytearray()
    for position, sprite in enumerate(sprites):
        entries += fixed_name_field(sprite.name, SPRITE_NAME_BYTES) + struct.pack(">I", data_start + position * SPRITE_RECORD_BYTES)
        payload += sprite_record(sprite, transparent_index)
    return header + bytes(entries) + bytes(payload)


@dataclass(frozen=True)
class PackedSprite:
    """One entry read back out of a .SPR blob, including the blob's own transparency key.

    The key is a property of the blob, not of the reader: carrying it means a consumer of a
    parsed sprite masks with the key the art was actually packed against, rather than with
    whatever TRANSPARENT_INDEX happens to be compiled in.
    """

    name: str
    indices: np.ndarray
    spans: bytes
    transparent_index: int


def parse_sprites(blob: bytes) -> list[PackedSprite]:
    """Read a .SPR blob back; round-trip check for `pack_sprites` and a loader reference."""
    if len(blob) < SPRITE_HEADER_BYTES:
        raise ValueError("blob is shorter than a sprite header")
    magic, version, count, dim, transparent_index = struct.unpack_from(">4sHHHH", blob, 0)
    if magic != SPRITE_MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {SPRITE_MAGIC!r}")
    if version != SPRITE_FORMAT_VERSION:
        raise ValueError(f"unsupported sprite format version {version}")

    span_bytes = dim * SPAN_BYTES_PER_COLUMN
    out: list[PackedSprite] = []
    for position in range(count):
        name_bytes, offset = struct.unpack_from(f">{SPRITE_NAME_BYTES}sI", blob, SPRITE_HEADER_BYTES + position * SPRITE_ENTRY_BYTES)
        spans = blob[offset:offset + span_bytes]
        texels = blob[offset + span_bytes:offset + span_bytes + dim * dim]
        out.append(PackedSprite(name_bytes.rstrip(b"\0").decode("ascii"),
                                from_column_major(texels, dim, dim), spans, int(transparent_index)))
    return out


@dataclass(frozen=True)
class HudBlit:
    """Fixed-position HUD art: interleaved planar data plus a 1-plane AND mask.

    Draw is `and.w mask,(dst) / or.w data,(dst)` per plane, the same mask word reused for all
    four planes. Mask bits are 1 where the sprite is TRANSPARENT, so the AND keeps the
    background there; `data` is already zeroed under the holes so the OR cannot leak.
    """

    width: int
    height: int
    data: bytes
    mask: bytes

    @property
    def chunks_per_row(self) -> int:
        return self.width // PIXELS_PER_CHUNK

    @property
    def data_row_bytes(self) -> int:
        return self.chunks_per_row * BYTES_PER_CHUNK

    @property
    def mask_row_bytes(self) -> int:
        return self.chunks_per_row * 2      # one plane, one word per 16 pixels


def hud_blit(indices: np.ndarray, transparent_index: int = TRANSPARENT_INDEX) -> HudBlit:
    """Build fixed-position HUD planar data + mask. Width must be a multiple of 16."""
    idx = np.asarray(indices, dtype=np.uint8)
    if idx.ndim != 2:
        raise ValueError(f"expected a 2-D index image, got shape {idx.shape}")
    height, width = idx.shape
    if width % PIXELS_PER_CHUNK:
        raise ValueError(f"HUD art width {width} must be a multiple of {PIXELS_PER_CHUNK} (no pre-shifting)")

    transparent = idx == transparent_index
    opaque_indices = np.where(transparent, 0, idx).astype(np.uint8)
    bits = transparent.reshape(height, width // PIXELS_PER_CHUNK, PIXELS_PER_CHUNK).astype(np.uint16)
    weights = 1 << np.arange(MSB_PIXEL_BIT, -1, -1, dtype=np.uint16)
    mask_words = (bits * weights).sum(axis=2).astype(">u2")
    return HudBlit(width, height, indices_to_planar(opaque_indices), mask_words.tobytes())


def hud_blit_to_indices(blit: HudBlit, transparent_index: int = TRANSPARENT_INDEX) -> np.ndarray:
    """Rebuild indices from a HudBlit; the mask's holes come back as `transparent_index`."""
    indices = planar_to_indices(blit.data, blit.width, blit.height)
    mask_words = np.frombuffer(blit.mask, dtype=">u2").reshape(blit.height, blit.chunks_per_row).astype(np.uint16)
    shifts = np.arange(MSB_PIXEL_BIT, -1, -1, dtype=np.uint16)
    transparent = ((mask_words[:, :, None] >> shifts) & 1).astype(bool).reshape(blit.height, blit.width)
    return np.where(transparent, transparent_index, indices).astype(np.uint8)


def hud_blit_to_c_array(blit: HudBlit, symbol: str) -> str:
    """Emit a HudBlit as two C arrays plus its geometry, for HUD art linked into the engine."""
    geometry = (f"#define {symbol.upper()}_W {blit.width}\n"
                f"#define {symbol.upper()}_H {blit.height}\n"
                f"#define {symbol.upper()}_DATA_ROW_BYTES {blit.data_row_bytes}\n"
                f"#define {symbol.upper()}_MASK_ROW_BYTES {blit.mask_row_bytes}\n")
    return (geometry
            + c_byte_array(f"{symbol}_data", blit.data, f"{blit.width}x{blit.height} interleaved planar, {PLANES} planes")
            + c_byte_array(f"{symbol}_mask", blit.mask, "1-plane AND mask: bit set = transparent"))
