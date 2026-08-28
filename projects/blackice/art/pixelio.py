"""PNG output for BLACK ICE art scripts.

Two outputs per asset, because they answer different questions:
  out/native/<name>.png - 1:1, indexed, the 16-colour palette.  This is the asset.
  out/<name>.png        - the same pixels at PREVIEW_SCALE, nearest neighbour, for looking at.
"""

import os

import numpy as np
from PIL import Image

import palette

ART_ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ART_ROOT, "out")
NATIVE_DIR = os.path.join(OUT_DIR, "native")
PREVIEW_SCALE = 2
PNG_SUFFIX = ".png"


def ensure_dirs():
    os.makedirs(NATIVE_DIR, exist_ok=True)


def to_image(array):
    """Index array -> indexed PIL image carrying the BLACK ICE palette."""
    image = Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), mode="P")
    image.putpalette(palette.pil_palette())
    return image


def save(array, name, scale=PREVIEW_SCALE):
    """Write the native asset and its upscaled preview.  Returns both paths."""
    ensure_dirs()
    native_path = os.path.join(NATIVE_DIR, name + PNG_SUFFIX)
    preview_path = os.path.join(OUT_DIR, name + PNG_SUFFIX)
    image = to_image(array)
    image.save(native_path)
    image.resize((array.shape[1] * scale, array.shape[0] * scale), Image.NEAREST).save(preview_path)
    return native_path, preview_path


def save_preview_only(array, name, scale=PREVIEW_SCALE):
    """For composite sheets that are documentation, not shippable assets."""
    ensure_dirs()
    preview_path = os.path.join(OUT_DIR, name + PNG_SUFFIX)
    image = to_image(array)
    image.resize((array.shape[1] * scale, array.shape[0] * scale), Image.NEAREST).save(preview_path)
    return preview_path
