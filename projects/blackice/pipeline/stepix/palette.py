"""STE 4096-colour palette model: RGB(0..15 per channel) <-> the hardware colour word.

WHY the swizzle exists: the STE widened the ST's 3-bit channels to 4 bits but had to keep
old ST software working. An ST program writes a 3-bit value into bits 2..0 of each nibble;
on an STE those same bits still mean the *high* three bits of the intensity, and the new
4th bit was bolted on at bit 3 as the new *least* significant bit. So the nibble stored in
the register is a rotation of the intensity, not the intensity:

    stored_nibble = (intensity >> 1) | ((intensity & 1) << 3)
    intensity     = ((stored_nibble & 7) << 1) | (stored_nibble >> 3)

Source: docs/graphics.md in this workspace ("STE: 4 bits/channel but bit-rotated -- the LSB
sits in bit 3 of each nibble: intensity = ((v&7)<<1) | ((v>>3)&1)"), which matches the
Hatari shifter implementation. Consequence worth remembering: an *even* intensity has bit 3
clear and its word is byte-identical to the ST word for intensity/2, which is why ST art
loaded on an STE looks right, and why intensity 14 -- not 15 -- is "ST white" ($0777).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .colourspace import RGB888_MAX, lab_lightness, srgb_to_lab

PALETTE_SIZE = 16               # 16 colours on screen in ST/STE low resolution
BACKGROUND_INDEX = 0            # index 0 is also the border colour -- the hardware says so
CHANNEL_MAX = 15                # 4 bits per channel on the STE
ST_CHANNEL_MAX = 7              # 3 bits per channel on the plain ST
CHANNEL_BITS = 4
CHANNEL_MASK = 0x0F
ST_CHANNEL_MASK = 0x07          # bits 2..0: the ST-compatible part of a nibble
STE_LOW_BIT = 0x08              # bit 3 of a nibble: the STE-only least significant bit
RED_SHIFT = 8
GREEN_SHIFT = 4
BLUE_SHIFT = 0
PALETTE_WORD_MASK = 0x0FFF      # the top nibble of a colour word is always zero
PALETTE_WORD_BYTES = 2
PALETTE_BYTES = PALETTE_SIZE * PALETTE_WORD_BYTES
RGB888_PER_STEP = RGB888_MAX // CHANNEL_MAX      # 17: 4-bit level -> 8-bit preview level

Rgb = tuple[int, int, int]


def check_index_range(indices: np.ndarray, subject: str) -> None:
    """Reject palette indices outside 0..PALETTE_SIZE-1, on the array's ORIGINAL dtype.

    Every writer casts to uint8 on the way to disk, and that cast is silent: index 256 lands
    as 0 and -1 as 255, so art with an out-of-range index would ship as art with the wrong
    colour. The check therefore has to happen before the cast, not after it.
    """
    idx = np.asarray(indices)
    if not idx.size:
        return
    lowest, highest = int(idx.min()), int(idx.max())
    if lowest < 0 or highest >= PALETTE_SIZE:
        offender = lowest if lowest < 0 else highest
        raise ValueError(f"{subject} uses index {offender}, outside the {PALETTE_SIZE}-colour palette")


def encode_channel(intensity: int) -> int:
    """4-bit intensity -> the nibble actually stored in the palette register."""
    if not 0 <= intensity <= CHANNEL_MAX:
        raise ValueError(f"channel intensity {intensity} out of range 0..{CHANNEL_MAX}")
    return ((intensity >> 1) & ST_CHANNEL_MASK) | ((intensity & 1) << 3)


def decode_channel(nibble: int) -> int:
    """Stored nibble -> 4-bit intensity (inverse of `encode_channel`)."""
    if not 0 <= nibble <= CHANNEL_MASK:
        raise ValueError(f"palette nibble {nibble} out of range 0..{CHANNEL_MASK}")
    return ((nibble & ST_CHANNEL_MASK) << 1) | ((nibble & STE_LOW_BIT) >> 3)


def ste_word(red: int, green: int, blue: int) -> int:
    """Pack three 4-bit intensities into the $0RGB word written to $ffff8240+n."""
    return (encode_channel(red) << RED_SHIFT) | (encode_channel(green) << GREEN_SHIFT) | encode_channel(blue)


def from_ste_word(word: int) -> Rgb:
    """Unpack a hardware colour word back to 4-bit intensities."""
    if not 0 <= word <= 0xFFFF:
        raise ValueError(f"colour word {word:#06x} is not a 16-bit value")
    if word & ~PALETTE_WORD_MASK:
        raise ValueError(f"colour word {word:#06x} has a non-zero top nibble")
    return (
        decode_channel((word >> RED_SHIFT) & CHANNEL_MASK),
        decode_channel((word >> GREEN_SHIFT) & CHANNEL_MASK),
        decode_channel(word & CHANNEL_MASK),
    )


def is_st_compatible(word: int) -> bool:
    """True when no channel uses the STE-only low bit, i.e. a plain ST shows this word right."""
    return all(((word >> shift) & STE_LOW_BIT) == 0 for shift in (RED_SHIFT, GREEN_SHIFT, BLUE_SHIFT))


def to_st_word(word: int) -> int:
    """Drop the STE-only bit from every channel, giving the closest ST-legal word."""
    return word & ~((STE_LOW_BIT << RED_SHIFT) | (STE_LOW_BIT << GREEN_SHIFT) | STE_LOW_BIT)


def rgb4_to_rgb888(colour: Rgb) -> tuple[int, int, int]:
    """4-bit intensities -> 8-bit preview colour (x17 hits both 0 and 255 exactly)."""
    return tuple(int(channel) * RGB888_PER_STEP for channel in colour)  # type: ignore[return-value]


def rgb888_to_rgb4(colour: Sequence[int]) -> Rgb:
    """8-bit colour -> nearest 4-bit intensities (plain rounding; use `quantize` for images)."""
    return tuple(int(round(int(channel) * CHANNEL_MAX / RGB888_MAX)) for channel in colour)  # type: ignore[return-value]


@dataclass(frozen=True)
class StePalette:
    """A 16-entry STE palette. Entry 0 is the background/border colour by hardware rule."""

    colours: tuple[Rgb, ...]

    def __post_init__(self) -> None:
        if len(self.colours) != PALETTE_SIZE:
            raise ValueError(f"palette must have exactly {PALETTE_SIZE} entries, got {len(self.colours)}")
        for index, colour in enumerate(self.colours):
            if len(colour) != 3:
                raise ValueError(f"palette entry {index} is not an RGB triple: {colour!r}")
            for channel in colour:
                if not 0 <= channel <= CHANNEL_MAX:
                    raise ValueError(f"palette entry {index} channel {channel} out of range 0..{CHANNEL_MAX}")

    # ---- construction -------------------------------------------------------------
    @classmethod
    def build(cls, background: Rgb, entries: Iterable[Rgb]) -> "StePalette":
        """Assemble a palette with `background` pinned at index 0 and `entries` after it.

        This is the only sanctioned constructor for authored palettes: it makes the
        "index 0 is the border colour" rule impossible to get wrong by hand.
        """
        colours = [tuple(int(c) for c in background)] + [tuple(int(c) for c in e) for e in entries]
        if len(colours) != PALETTE_SIZE:
            raise ValueError(f"background + entries must total {PALETTE_SIZE} colours, got {len(colours)}")
        return cls(tuple(colours))  # type: ignore[arg-type]

    @classmethod
    def from_words(cls, words: Sequence[int]) -> "StePalette":
        """Rebuild a palette from 16 hardware colour words."""
        if len(words) != PALETTE_SIZE:
            raise ValueError(f"expected {PALETTE_SIZE} colour words, got {len(words)}")
        return cls(tuple(from_ste_word(int(w)) for w in words))

    @classmethod
    def from_bytes(cls, blob: bytes) -> "StePalette":
        """Rebuild a palette from the 32-byte big-endian on-disk/on-hardware form."""
        if len(blob) != PALETTE_BYTES:
            raise ValueError(f"expected {PALETTE_BYTES} palette bytes, got {len(blob)}")
        words = np.frombuffer(blob, dtype=">u2")
        return cls.from_words([int(w) for w in words])

    # ---- accessors ----------------------------------------------------------------
    @property
    def background(self) -> Rgb:
        """The index-0 colour, which the shifter also paints the border with."""
        return self.colours[BACKGROUND_INDEX]

    def with_background(self, colour: Rgb) -> "StePalette":
        """Copy of this palette with index 0 replaced -- keeps the enforcement in one place."""
        return StePalette((tuple(int(c) for c in colour),) + self.colours[1:])  # type: ignore[arg-type]

    def to_words(self) -> list[int]:
        return [ste_word(*colour) for colour in self.colours]

    def to_bytes(self) -> bytes:
        """The 32-byte blob that can be `move.l`-copied straight to $ffff8240."""
        return np.array(self.to_words(), dtype=">u2").tobytes()

    def to_rgb888(self) -> np.ndarray:
        """(16, 3) uint8 array for PNG previews and for nearest-colour searches."""
        return np.array([rgb4_to_rgb888(c) for c in self.colours], dtype=np.uint8)

    def to_lab(self) -> np.ndarray:
        """(16, 3) Lab array -- cached by callers that match many pixels against it."""
        return srgb_to_lab(self.to_rgb888().astype(np.float64))

    def st_compatible_indices(self) -> list[int]:
        """Entries a plain ST would display identically; useful when art must run on both."""
        return [i for i, word in enumerate(self.to_words()) if is_st_compatible(word)]

    def to_c_array(self, name: str = "ste_palette") -> str:
        """Emit the palette as a C array of hardware words, ready for the engine's palette.h."""
        lines = [
            f"/* {PALETTE_SIZE}-entry STE palette; write to $ffff8240..$ffff825e. Index 0 = border. */",
            f"static const unsigned short {name}[{PALETTE_SIZE}] = {{",
        ]
        for index, (word, colour) in enumerate(zip(self.to_words(), self.colours)):
            comma = "," if index < PALETTE_SIZE - 1 else ""
            lines.append(f"    0x{word:04x}{comma:<1}  /* {index:2d}: rgb4 {colour[0]:2d},{colour[1]:2d},{colour[2]:2d} */")
        lines.append("};")
        return "\n".join(lines) + "\n"


def _lightness_of_rgb4(colour: Rgb) -> float:
    return float(lab_lightness(np.array(rgb4_to_rgb888(colour), dtype=np.float64)))


def _hsv_to_rgb888(hue_deg: float, saturation: float, value: float) -> np.ndarray:
    """Minimal HSV->RGB; the ramp builder only needs one hue at a time, so no PIL detour."""
    hue = (hue_deg % 360.0) / 60.0
    chroma = value * saturation
    second = chroma * (1.0 - abs((hue % 2.0) - 1.0))
    sector = int(hue) % 6
    table = [(chroma, second, 0.0), (second, chroma, 0.0), (0.0, chroma, second),
             (0.0, second, chroma), (second, 0.0, chroma), (chroma, 0.0, second)]
    base = value - chroma
    return (np.array(table[sector], dtype=np.float64) + base) * RGB888_MAX


RAMP_LIGHTNESS_MIN = 12.0       # L* of the darkest shade a wall ramp should reach
RAMP_LIGHTNESS_MAX = 88.0       # L* of the brightest; 100 would blow out to flat white
RAMP_VALUE_SEARCH_STEPS = 24    # bisection depth: 2**-24 of the value range is far below 1/15
RAMP_MIN_SHADES = 2


def _value_for_lightness(hue_deg: float, saturation: float, target_l: float) -> float:
    """Bisect HSV value for a target L*: L* is monotone in value at fixed hue/saturation."""
    low, high = 0.0, 1.0
    for _ in range(RAMP_VALUE_SEARCH_STEPS):
        mid = (low + high) / 2.0
        if _lightness_of_rgb4(rgb888_to_rgb4(_hsv_to_rgb888(hue_deg, saturation, mid))) < target_l:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _nudge_brighter(colour: Rgb) -> Rgb | None:
    """Push a colour one 4-bit step brighter, or None if it is already white.

    Every channel steps up together, which also desaturates slightly. That is deliberate: a
    duplicate near the top of a saturated ramp means the hue has hit its lightness ceiling,
    and the only way further up the L* axis is towards white.
    """
    if all(channel >= CHANNEL_MAX for channel in colour):
        return None
    return tuple(min(CHANNEL_MAX, channel + 1) for channel in colour)  # type: ignore[return-value]


def build_ramp(hue_deg: float, shades: int, saturation: float = 0.75,
               lightness_min: float = RAMP_LIGHTNESS_MIN, lightness_max: float = RAMP_LIGHTNESS_MAX) -> list[Rgb]:
    """`shades` colours of one hue, spaced evenly in perceived lightness on the 4-bit gamut.

    Even *linear* spacing bunches the dark end into indistinguishable mud once quantised to
    16 levels, so the targets are placed in L* and the HSV value that hits each one is found
    by bisection. Duplicates that survive quantisation are nudged one step apart, because a
    wall ramp whose shades collide loses the lighting cue the raycaster depends on.
    """
    if shades < RAMP_MIN_SHADES:
        raise ValueError(f"a ramp needs at least {RAMP_MIN_SHADES} shades, got {shades}")
    if not 0.0 <= saturation <= 1.0:
        raise ValueError(f"saturation {saturation} out of range 0..1")
    if not lightness_min < lightness_max:
        raise ValueError("lightness_min must be below lightness_max")

    ramp: list[Rgb] = []
    used: set[Rgb] = set()
    for step in range(shades):
        target = lightness_min + (lightness_max - lightness_min) * step / (shades - 1)
        colour = rgb888_to_rgb4(_hsv_to_rgb888(hue_deg, saturation, _value_for_lightness(hue_deg, saturation, target)))
        while colour in used:                       # compare against every earlier shade, not just the last
            nudged = _nudge_brighter(colour)
            if nudged is None:                      # gamut exhausted at white: accept the collision
                break
            colour = nudged
        ramp.append(colour)
        used.add(colour)
    return ramp
