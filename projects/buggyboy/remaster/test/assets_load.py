"""assets_load.py — drive remaster's own asset loader from Python.

Loads the game's unmodified `COURSES.DAT` + `GRAPHICS.GRA` into a remaster arena through the shipped
`rm_arena_init` / `rm_assets_unpack` (src/assets.c) and hands back the arena bytes.

Two callers, and they need the *same* arena for the comparison to mean anything:
  * `test_assets.py` diffs it against recreate's verified `g_unpack_graphics`;
  * `render/atari/gen_demo_fixture.py` stages it into the reference image before computing the
    demo's golden frame, so the golden and the on-target demo (which loads the files off disk at
    boot) are rendered from byte-identical assets.
"""
import ctypes
from pathlib import Path

import adapter

DATA_DIR = adapter.harness.PRG.parent                # projects/buggyboy/bin — the original files

# Mirror include/assets.h. test_assets.py pins these against recreate's own layout constants.
RM_ARENA_BYTES = 0x5EE08
RM_COURSE_OFF = 0x00000
RM_TABLES_OFF = 0x01900
RM_SCRATCH_OFF = 0x0F660
RM_GFX_OFF = 0x1C660
RM_AUX_OFF = 0x57000
RM_COURSE_FILE_BYTES = 0xF660
RM_GFX_LOAD_OFF = 0xC350
RM_GFX_READ_MAX = RM_ARENA_BYTES - RM_GFX_OFF - RM_GFX_LOAD_OFF

class RmArena(ctypes.Structure):
    """Mirror include/assets.h's RmArena exactly — rm_arena_init writes every field, so a missing
    one here would have it write past this buffer."""
    _fields_ = [(name, ctypes.POINTER(ctypes.c_uint8))
                for name in ("base", "course", "tables", "scratch", "gfx", "aux")]


def fresh_arena(data_dir: Path = DATA_DIR) -> bytes:
    """Load both data files into a zeroed arena and unpack — exactly what the game does at boot."""
    lib = ctypes.CDLL(str(adapter.LIBREMASTER))
    lib.rm_arena_init.argtypes = [ctypes.POINTER(RmArena), ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_arena_init.restype = None
    lib.rm_assets_unpack.argtypes = [ctypes.POINTER(RmArena), ctypes.c_uint32]
    lib.rm_assets_unpack.restype = ctypes.c_bool

    block = (ctypes.c_uint8 * RM_ARENA_BYTES)()      # zero-filled, as the game's Malloc'd block is
    arena = RmArena()
    lib.rm_arena_init(ctypes.byref(arena), block)

    courses = (data_dir / "COURSES.DAT").read_bytes()
    graphics = (data_dir / "GRAPHICS.GRA").read_bytes()
    # Bound both copies: memmove past the ctypes buffer corrupts the CPython heap, which surfaces as
    # a segfault or a silently wrong golden rather than a failed assertion.
    assert len(courses) == RM_COURSE_FILE_BYTES, "COURSES.DAT is read whole; its size is the count"
    assert len(graphics) <= RM_GFX_READ_MAX, f"GRAPHICS.GRA is {len(graphics)}B; arena holds {RM_GFX_READ_MAX}B"
    ctypes.memmove(ctypes.byref(block, RM_COURSE_OFF), courses, len(courses))
    ctypes.memmove(ctypes.byref(block, RM_GFX_OFF + RM_GFX_LOAD_OFF), graphics, len(graphics))

    assert lib.rm_assets_unpack(ctypes.byref(arena), len(graphics)), "rm_assets_unpack rejected the stream"
    return bytes(block)
