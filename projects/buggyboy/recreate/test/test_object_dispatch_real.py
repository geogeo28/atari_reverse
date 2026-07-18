"""Differential test for draw_object_list dispatch over REAL course data (all obj_type_jumptable
handlers). Complements test_object_list.py (which fuzzes synthetic single records for the classic 8
handlers): this stages the actual COURSES.DAT layout the game builds, runs init_leg, then diffs the
full first-pass object draw (draw_game_objects' `count`-sprite pass) against the Musashi oracle for
every leg. It exercises the ~25 real jump-table targets that appear in the shipped course data —
the objsprite hi/scan/a6-prefix/view-transform families and the objshift2 "P-prefix" cluster — which
the synthetic fuzz never reached (they were the missing handlers that left roadside objects/poles/
flags unrendered until obj_dispatch was completed).

The staging mirrors render_screen._prepared_image (main's buffer layout + COURSES.DAT + GRAPHICS.GRA
unpacked); init_leg is the oracle's own 0x104b8 so both sides start byte-identical, then only the C
g_draw_object_list vs the oracle 0x1306e differ. Whole-framebuffer diff, parametrized per leg (0-4)
so the five heavy Musashi runs shard across xdist workers.
"""
import ctypes
import sys
from pathlib import Path

import pytest

import harness
import emu

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))
import render_screen as R                                             # noqa: E402

INIT_LEG = 0x104b8
ENTRY = 0x1306e                        # draw_object_list
A_LEG_INDEX = 0x18c38
A_SPRITE_BASE = 0x18d5a                # sprite-count loop base (draw_game_objects)
A_OBJ_SPRITE_DISP = 0x16a90            # a5 base
A_OBJ_SPRITE_FLAGS = 0x18d5c           # a3 base
SPRITE_STRIDE = 0x20
SPRITE_SLOTS_MAX = 11                  # draw_game_objects counts up to 11 slots
D6_INIT = 0xb0                         # first-pass d6 seed
SCREEN = R.SCREEN_BASE

harness._lib.g_draw_object_list.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
harness._lib.g_draw_object_list.restype = None


def _w(mem, a):
    return int.from_bytes(bytes(mem[a:a + 2]), "big")


def _sprite_count(mem):
    """Mirror draw_game_objects: if the base word is >= 0, count consecutive non-negative slots."""
    if _w(mem, A_SPRITE_BASE) & 0x8000:
        return 0
    count, p = 0, A_SPRITE_BASE + SPRITE_STRIDE
    for _ in range(SPRITE_SLOTS_MAX):
        if _w(mem, p) & 0x8000:
            break
        count += 1
        p += SPRITE_STRIDE
    return count


def _first_pass_diffs(post_init):
    """Run draw_object_list's first sprite pass (d4=count-1, d6=0xb0, d1=count) oracle-vs-C."""
    count = _sprite_count(post_init)
    if count == 0:
        return None
    d4, d6, d1 = count - 1, D6_INIT, count
    a5, a3, a6 = A_OBJ_SPRITE_DISP, A_OBJ_SPRITE_FLAGS, SCREEN
    o_img, _, _ = emu.run(bytearray(post_init), ENTRY,
                          {"a5": a5, "a3": a3, "a6": a6, "d4": d4, "d6": d6, "d1": d1},
                          max_insns=8_000_000)
    m = bytearray(post_init)
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(m)
    harness._lib.g_draw_object_list(buf, a5, a3, a6, d4, d6, d1)
    return [a for a in range(emu.STACK_GUARD_LO) if bytes(m)[a] != o_img[a]]


@pytest.mark.parametrize("leg", range(5))
def test_dispatch_real_courses(leg):
    img, _ = R._prepared_image({A_LEG_INDEX: leg.to_bytes(2, "big")})
    post_init, _, _ = emu.run(bytearray(img), INIT_LEG, {}, max_insns=4_000_000)
    diffs = _first_pass_diffs(post_init)
    assert diffs is not None, f"leg {leg}: no active sprites staged (staging changed?)"
    assert not diffs, (f"leg {leg}: {len(diffs)} byte(s) differ from the oracle; "
                       f"first at {hex(diffs[0])} — a jump-table handler is wrong/missing")
