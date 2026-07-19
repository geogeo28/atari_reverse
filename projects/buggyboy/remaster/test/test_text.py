"""test_text.py — remaster glyph blitter (rm_glyph_run) vs recreate's verified glyph body.

recreate exposes the glyph body through two of its own entry points, so the primitive is validated
in isolation (whole-framebuffer EXACT match, not just coverage):
  - g_draw_hud_bar    — fill passed directly (D2/D3), cell budget preset to 0x13
  - g_draw_hud_gauge0 — fill derived from a colour index, caller-supplied cell budget

Each case draws one glyph run onto a random (shared) background at a random offset from a random
paired-glyph string, and asserts the remaster framebuffer is byte-identical to recreate's.
"""
import ctypes
import random

import adapter
import pytest

harness = adapter.harness
SCREEN_BASE, SCREEN_BYTES = adapter.SCREEN_BASE, adapter.SCREEN_BYTES

FONT_ADDR, FONT_LEN = 0x176a8, 0x600      # 1bpp glyph table (chars 0..0x5f, 16 bytes each)
A_color_pairs = adapter.A_color_pairs
STR_ADDR, STR_MAX = 0x800, 48             # scratch string buffer, below the framebuffer region
GLYPH_LO, GLYPH_HI = 0x20, 0x5f           # printable glyph range (stays inside the font table)
CHUNKS, CASES = 8, 60


def _lib():
    lib = ctypes.CDLL(str(equiv_lib_path()))
    p8, p32 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint32)
    lib.rm_glyph_run.argtypes = [ctypes.POINTER(adapter.Framebuffer), ctypes.c_uint32,
                                 ctypes.c_uint32, ctypes.c_uint32,
                                 p8, p8, ctypes.c_uint32, ctypes.c_uint16, p32]
    lib.rm_glyph_run.restype = ctypes.c_uint32
    return lib


def equiv_lib_path():
    return adapter.REMASTER / "build" / "libremaster.so"


def _bind_ref():
    for name in ("g_draw_hud_bar", "g_draw_hud_gauge0"):
        fn = getattr(harness._lib, name)
        fn.restype = None
    harness._lib.g_draw_hud_bar.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
    harness._lib.g_draw_hud_gauge0.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4


def _rand_string(rng):
    """A paired-glyph string: n pairs of printable chars, 0-terminated. Some cases end a pair with a
    0 second byte to exercise the last-cell glyph-0x2f substitution."""
    pairs = rng.randint(1, 8)
    s = bytearray()
    for _ in range(pairs):
        s.append(rng.randint(GLYPH_LO, GLYPH_HI))
        s.append(rng.randint(GLYPH_LO, GLYPH_HI))
    if rng.random() < 0.2:                    # trigger char2==0 substitution on the last pair
        s[-1] = 0
    else:
        s.append(0)                           # normal terminator
    return bytes(s)


def _case(rng):
    return {"off": rng.randrange(0x300, 0x5000, 8),
            "string": _rand_string(rng),
            "color": rng.randint(0, 0xf),
            "cells_m1": rng.choice([0x13, rng.randint(1, 0x13)]),
            "bg": bytes(rng.getrandbits(8) for _ in range(SCREEN_BYTES))}


def _prepare(case):
    """Image with the random background staged at SCREEN_BASE and the string at STR_ADDR."""
    img = harness.make_image({})
    img[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES] = case["bg"]
    img[STR_ADDR:STR_ADDR + len(case["string"])] = case["string"]
    return img


def _candidate(lib, img, case, fill_lo, fill_hi, cells_m1):
    font = (ctypes.c_uint8 * FONT_LEN)(*img[FONT_ADDR:FONT_ADDR + FONT_LEN])
    s = case["string"]
    strbuf = (ctypes.c_uint8 * len(s))(*s)
    fb = adapter.Framebuffer((ctypes.c_uint8 * SCREEN_BYTES)(*case["bg"]))
    end = ctypes.c_uint32()
    lib.rm_glyph_run(ctypes.byref(fb), case["off"], fill_lo, fill_hi, font, strbuf, 0,
                     cells_m1, ctypes.byref(end))
    return bytes(fb.px)


def _color_fill(img, color):
    off = (color & 0xf) << 3
    def be32(a):
        return int.from_bytes(img[a:a + 4], "big")
    return be32(A_color_pairs + off), be32(A_color_pairs + off + 4)


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_glyph_run_matches_hud_bar(chunk):
    lib, rng = _lib(), random.Random(1000 + chunk)
    _bind_ref()
    for _ in range(CASES):
        case = _case(rng)
        fill_lo, fill_hi = rng.getrandbits(32), rng.getrandbits(32)
        img = _prepare(case)
        ref = bytearray(img)
        buf = (ctypes.c_uint8 * len(ref)).from_buffer(ref)
        harness._lib.g_draw_hud_bar(buf, SCREEN_BASE + case["off"], fill_lo, fill_hi, STR_ADDR)
        ref_fb = bytes(ref[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES])
        # g_draw_hud_bar presets the cell budget to 0x13 (ignores any argument).
        assert _candidate(lib, img, case, fill_lo, fill_hi, 0x13) == ref_fb


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_glyph_run_matches_hud_gauge0(chunk):
    lib, rng = _lib(), random.Random(2000 + chunk)
    _bind_ref()
    for _ in range(CASES):
        case = _case(rng)
        img = _prepare(case)
        ref = bytearray(img)
        buf = (ctypes.c_uint8 * len(ref)).from_buffer(ref)
        harness._lib.g_draw_hud_gauge0(buf, SCREEN_BASE + case["off"], case["color"],
                                       case["cells_m1"], STR_ADDR)
        ref_fb = bytes(ref[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES])
        fill_lo, fill_hi = _color_fill(img, case["color"])
        assert _candidate(lib, img, case, fill_lo, fill_hi, case["cells_m1"]) == ref_fb
