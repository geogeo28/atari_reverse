"""sRGB <-> CIE Lab conversion.

Colour *distance* is the one place this pipeline must not work in raw RGB: the STE gamut is
only 16 levels per channel, so a nearest-colour search in RGB happily picks a hue-shifted
neighbour that is numerically close but visibly wrong. Every match in `quantize` and every
shade table in `texture` therefore compares in CIE Lab, where Euclidean distance approximates
perceived difference. Kept in its own module so palette, quantize and texture share one
implementation rather than three subtly different ones.

All functions take/return numpy arrays with the colour channels in the last axis.
"""
from __future__ import annotations

import numpy as np

RGB888_MAX = 255                # 8-bit sRGB full scale; the one definition in the pipeline
SRGB_LINEAR_CUTOFF = 0.04045    # sRGB transfer-function knee (IEC 61966-2-1)
SRGB_LINEAR_SLOPE = 12.92
SRGB_GAMMA_OFFSET = 0.055
SRGB_GAMMA_SCALE = 1.055
SRGB_GAMMA_EXP = 2.4

# CIE XYZ of the D65 white point, Y normalised to 1.0.
D65_WHITE = np.array([0.95047, 1.00000, 1.08883], dtype=np.float64)

# sRGB (linear) -> CIE XYZ, D65.
SRGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float64)

XYZ_TO_SRGB = np.linalg.inv(SRGB_TO_XYZ)

LAB_EPSILON = 216.0 / 24389.0   # CIE standard epsilon (6/29)**3
LAB_KAPPA = 24389.0 / 27.0      # CIE standard kappa
LAB_L_SCALE = 116.0
LAB_L_OFFSET = 16.0
LAB_A_SCALE = 500.0
LAB_B_SCALE = 200.0
LAB_LINEAR_SLOPE = 1.0 / 3.0
LAB_LINEAR_OFFSET = 4.0 / 29.0


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Undo the sRGB transfer function. Input 0..255, output linear 0..1."""
    c = np.asarray(rgb, dtype=np.float64) / RGB888_MAX
    low = c / SRGB_LINEAR_SLOPE
    high = ((c + SRGB_GAMMA_OFFSET) / SRGB_GAMMA_SCALE) ** SRGB_GAMMA_EXP
    return np.where(c <= SRGB_LINEAR_CUTOFF, low, high)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Apply the sRGB transfer function. Input linear 0..1, output 0..255 (unclipped)."""
    c = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    low = c * SRGB_LINEAR_SLOPE
    high = SRGB_GAMMA_SCALE * (c ** (1.0 / SRGB_GAMMA_EXP)) - SRGB_GAMMA_OFFSET
    return np.where(c <= SRGB_LINEAR_CUTOFF / SRGB_LINEAR_SLOPE, low, high) * RGB888_MAX


def _lab_f(t: np.ndarray) -> np.ndarray:
    """The CIE Lab compression function, with its linear segment near black."""
    return np.where(t > LAB_EPSILON, np.cbrt(t), (LAB_KAPPA * t + LAB_L_OFFSET) / LAB_L_SCALE)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert 0..255 sRGB to CIE Lab (D65). Shape (..., 3) in, shape (..., 3) out."""
    xyz = srgb_to_linear(rgb) @ SRGB_TO_XYZ.T
    f = _lab_f(xyz / D65_WHITE)
    lightness = LAB_L_SCALE * f[..., 1] - LAB_L_OFFSET
    a = LAB_A_SCALE * (f[..., 0] - f[..., 1])
    b = LAB_B_SCALE * (f[..., 1] - f[..., 2])
    return np.stack([lightness, a, b], axis=-1)


def lab_lightness(rgb: np.ndarray) -> np.ndarray:
    """L* only -- used by the ramp builder, which spaces shades by perceived lightness."""
    return srgb_to_lab(rgb)[..., 0]


def nearest_lab_index(colours: np.ndarray, targets_lab: np.ndarray) -> np.ndarray:
    """Index of the nearest `targets_lab` entry for each 0..255 RGB colour in `colours`.

    `colours` is (N, 3) RGB, `targets_lab` is (M, 3) Lab; returns (N,) int32.
    """
    lab = srgb_to_lab(np.asarray(colours, dtype=np.float64))
    deltas = lab[:, None, :] - targets_lab[None, :, :]
    return np.argmin(np.einsum("nmc,nmc->nm", deltas, deltas), axis=1).astype(np.int32)
