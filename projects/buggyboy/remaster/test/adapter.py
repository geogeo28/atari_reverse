"""adapter.py — bridge recreate's flat image to remaster's native structs.

Phase A validates the remaster renderer from real captured state: this maps the recreate globals
and static asset tables a renderer reads out of the flat image into the ctypes structs remaster's C
takes. It is test-only scaffolding — the seam that lets one captured snapshot drive both sides so
their framebuffers can be diffed (see ../README.md). The shipped remaster game shares none of it.
"""
import ctypes
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
for p in ("oracle", "test", "render", "tools"):
    sys.path.insert(0, str(RECREATE / p))

import harness                                    # noqa: E402  recreate's image accessors / .so
import render_screen as R                         # noqa: E402  SCREEN_BASE + buffer layout

SCREEN_BASE = R.SCREEN_BASE
SCREEN_BYTES = R.ROW_STRIDE * R.H                 # 32000

# ---- recreate globals the HUD reads (mirror recreate/include/addrs.h) ----
A_flag_seq_count, A_flag_seq_off = 0x18c48, 0x18c40
A_dsp_color_scroll, A_crash_lap = 0x18d06, 0x18c4a
A_dsp_toggle, A_crash_active, A_hud_crash_timer = 0x18c7c, 0x18c7a, 0x18c4c

# ---- static asset tables the HUD reads (STATIC.BIN region) ----
A_color_pairs = 0x15afa                           # 16 colours x 8-byte fill
A_color_bar_mask = 0x17d14                        # phase-5 {mask,ink} stream (5 cols x 12 rows x 4B)
A_color_bar_cidx = 0x17e40                        # phase-5 colour-index cursor (signed-offset window)
A_fuel_mask = 0x17f08                             # phase-6a two mask longs
COLOR_PAIRS_BYTES = 16 * 8
COLOR_BAR_MASK_BYTES = 5 * 12 * 4
FUEL_MASK_BYTES = 8
CIDX_ZERO_OFF = 0x200                             # window is [-0x200, +0x200) around the cursor base
CIDX_WINDOW_BYTES = 2 * CIDX_ZERO_OFF


class HudState(ctypes.Structure):
    _fields_ = [("flag_seq_count", ctypes.c_int16), ("flag_seq_off", ctypes.c_int16),
                ("dsp_color_scroll", ctypes.c_int16), ("crash_lap", ctypes.c_int16)]


class HudAssets(ctypes.Structure):
    _fields_ = [("color_pairs", ctypes.POINTER(ctypes.c_uint8)),
                ("color_bar_mask", ctypes.POINTER(ctypes.c_uint8)),
                ("color_bar_cidx", ctypes.POINTER(ctypes.c_uint8)),
                ("fuel_mask", ctypes.POINTER(ctypes.c_uint8))]


class Framebuffer(ctypes.Structure):
    _fields_ = [("px", ctypes.c_uint8 * SCREEN_BYTES)]


def _i16(image, addr):
    v = (image[addr] << 8) | image[addr + 1]
    return v - 0x10000 if v & 0x8000 else v


def hud_state(image):
    """The dynamic HUD scalars the ported phases read, as a native HudState."""
    return HudState(_i16(image, A_flag_seq_count), _i16(image, A_flag_seq_off),
                    _i16(image, A_dsp_color_scroll), _i16(image, A_crash_lap))


def hud_assets(image):
    """The static HUD asset tables as a native HudAssets. Returns (assets, keepalive) — the caller
    must hold `keepalive` for as long as `assets` is used (it owns the underlying buffers)."""
    def buf(addr, n):
        return (ctypes.c_uint8 * n)(*image[addr:addr + n])

    color_pairs = buf(A_color_pairs, COLOR_PAIRS_BYTES)
    color_bar_mask = buf(A_color_bar_mask, COLOR_BAR_MASK_BYTES)
    fuel_mask = buf(A_fuel_mask, FUEL_MASK_BYTES)
    # cidx is indexed by a signed cursor offset, so extract a window and point at its zero offset.
    cidx_window = buf(A_color_bar_cidx - CIDX_ZERO_OFF, CIDX_WINDOW_BYTES)
    p = ctypes.POINTER(ctypes.c_uint8)
    assets = HudAssets(
        ctypes.cast(color_pairs, p),
        ctypes.cast(color_bar_mask, p),
        ctypes.cast(ctypes.byref(cidx_window, CIDX_ZERO_OFF), p),
        ctypes.cast(fuel_mask, p),
    )
    return assets, (color_pairs, color_bar_mask, fuel_mask, cidx_window)


def framebuffer(image):
    """The current draw buffer (SCREEN_BASE..+32000) as a native Framebuffer."""
    return Framebuffer((ctypes.c_uint8 * SCREEN_BYTES)(*image[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES]))
