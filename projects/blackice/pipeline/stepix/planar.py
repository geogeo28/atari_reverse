"""Indexed image <-> Atari ST/STE 4-bitplane word-interleaved bitmap.

The shifter reads four 16-bit planes per 16 pixels, interleaved in memory:
plane0 word, plane1 word, plane2 word, plane3 word, then the next 16 pixels. A pixel's
colour index is one bit taken from each plane, plane 0 being the LSB, and within a word
bit 15 is the LEFTMOST pixel. Getting plane order wrong scrambles colours but not shapes,
which is exactly the bug that survives a casual eyeball -- hence the round-trip tests.

This module is for full-screen and HUD-layer art. The raycaster's own wall/sprite texels do
NOT live in this format (see texture.py): planar is wrong for a per-column inner loop.
"""
from __future__ import annotations

import struct

import numpy as np

from .palette import PALETTE_BYTES, PALETTE_SIZE, StePalette, check_index_range

PLANES = 4                              # 4 bitplanes = 16 colours, ST/STE low resolution
PIXELS_PER_CHUNK = 16                   # one word per plane covers 16 pixels
BYTES_PER_CHUNK = PLANES * 2            # 4 planes x 1 word
MSB_PIXEL_BIT = PIXELS_PER_CHUNK - 1    # bit 15 holds the leftmost pixel of a chunk

SCREEN_W = 320
SCREEN_H = 200
SCREEN_ROW_BYTES = SCREEN_W // PIXELS_PER_CHUNK * BYTES_PER_CHUNK   # 160
SCREEN_BYTES = SCREEN_ROW_BYTES * SCREEN_H                          # 32000

# DEGAS Elite uncompressed .PI1: resolution word, 16 palette words, then the raw screen.
PI1_RES_LOW = 0x0000
PI1_HEADER_BYTES = 2 + PALETTE_BYTES    # 34
PI1_BYTES = PI1_HEADER_BYTES + SCREEN_BYTES


def _validate_indices(indices: np.ndarray) -> np.ndarray:
    idx = np.asarray(indices)
    if idx.ndim != 2:
        raise ValueError(f"expected a 2-D index image, got shape {idx.shape}")
    if idx.shape[1] % PIXELS_PER_CHUNK:
        raise ValueError(f"width {idx.shape[1]} must be a multiple of {PIXELS_PER_CHUNK}")
    check_index_range(idx, "index image")       # before the cast: uint8 would wrap 256 to 0
    return idx.astype(np.uint8, copy=False)


def indices_to_planar(indices: np.ndarray) -> bytes:
    """(h, w) indices -> interleaved planar bytes, w a multiple of 16."""
    idx = _validate_indices(indices)
    height, width = idx.shape
    chunks = idx.reshape(height, width // PIXELS_PER_CHUNK, PIXELS_PER_CHUNK).astype(np.uint16)
    pixel_weights = (1 << np.arange(MSB_PIXEL_BIT, -1, -1, dtype=np.uint16))
    planes = np.empty((height, width // PIXELS_PER_CHUNK, PLANES), dtype=">u2")
    for plane in range(PLANES):
        bits = (chunks >> plane) & 1
        planes[:, :, plane] = (bits * pixel_weights).sum(axis=2).astype(np.uint16)
    return planes.tobytes()


def planar_to_indices(data: bytes, width: int, height: int) -> np.ndarray:
    """Interleaved planar bytes -> (h, w) uint8 indices. Exact inverse of `indices_to_planar`."""
    if width % PIXELS_PER_CHUNK:
        raise ValueError(f"width {width} must be a multiple of {PIXELS_PER_CHUNK}")
    chunks_per_row = width // PIXELS_PER_CHUNK
    expected = chunks_per_row * height * BYTES_PER_CHUNK
    if len(data) != expected:
        raise ValueError(f"expected {expected} planar bytes for {width}x{height}, got {len(data)}")

    planes = np.frombuffer(data, dtype=">u2").reshape(height, chunks_per_row, PLANES).astype(np.uint16)
    shifts = np.arange(MSB_PIXEL_BIT, -1, -1, dtype=np.uint16)
    indices = np.zeros((height, chunks_per_row, PIXELS_PER_CHUNK), dtype=np.uint8)
    for plane in range(PLANES):
        bits = (planes[:, :, plane, None] >> shifts) & 1
        indices |= (bits << plane).astype(np.uint8)
    return indices.reshape(height, width)


def screen_to_planar(indices: np.ndarray) -> bytes:
    """320x200 indices -> the exact 32000 bytes a screen buffer holds."""
    idx = np.asarray(indices)
    if idx.shape != (SCREEN_H, SCREEN_W):
        raise ValueError(f"a full screen is {SCREEN_W}x{SCREEN_H}, got {idx.shape[1]}x{idx.shape[0]}")
    return indices_to_planar(idx)


def pi1_bytes(indices: np.ndarray, palette: StePalette) -> bytes:
    """Build a DEGAS Elite .PI1 so the art opens in any ST paint tool.

    The palette words written are the STE words -- the same 32 bytes the engine pokes at
    $ffff8240 -- so what a viewer shows matches the hardware. An ST-only viewer wants each
    channel's STE low bit dropped; that is a palette-level transform (`palette.to_st_word`),
    not a file-format flag, and `read_pi1` decodes STE words either way.
    """
    header = struct.pack(">H", PI1_RES_LOW) + struct.pack(f">{PALETTE_SIZE}H", *palette.to_words())
    return header + screen_to_planar(indices)


def write_pi1(path: str, indices: np.ndarray, palette: StePalette) -> int:
    """Write a .PI1 file; returns the byte count written (always PI1_BYTES)."""
    blob = pi1_bytes(indices, palette)
    with open(path, "wb") as handle:
        handle.write(blob)
    return len(blob)


def read_pi1(blob: bytes) -> tuple[np.ndarray, StePalette]:
    """Parse a .PI1 back to (indices, palette). Only low resolution is supported."""
    if len(blob) != PI1_BYTES:
        raise ValueError(f"a low-res .PI1 is {PI1_BYTES} bytes, got {len(blob)}")
    resolution = struct.unpack_from(">H", blob, 0)[0]
    if resolution != PI1_RES_LOW:
        raise ValueError(f"resolution word {resolution} is not low resolution ({PI1_RES_LOW})")
    palette = StePalette.from_bytes(blob[2:PI1_HEADER_BYTES])
    return planar_to_indices(blob[PI1_HEADER_BYTES:], SCREEN_W, SCREEN_H), palette
