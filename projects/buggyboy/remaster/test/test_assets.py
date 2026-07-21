"""test_assets.py — remaster loads the original data files itself, byte-for-byte.

Every other remaster test is fed assets by the adapter, which slices named windows out of a staged
recreate image. This one closes that loop: the remaster reads the *unmodified* `COURSES.DAT` and
`GRAPHICS.GRA` into its own arena and unpacks them with its own C, and we assert the resulting
arena is byte-identical to what recreate's verified `g_unpack_graphics` produces from the same two
files. Green here means the shipped game needs no baked asset blob — the files ARE the assets.

The comparison surface is the whole 0x5ee08-byte arena, not a sampled region, so a divergence in
any phase (RLE decode, screen de-interleave, compaction, the tail slide, either sprite pre-shift
table build) fails it.
"""
import ctypes

import adapter
import equiv
import pytest
import render_screen as R                          # recreate's staging + arena layout constants

# Mirror include/assets.h. Pinned against recreate's own layout constants below, so a drift in
# either place fails rather than silently comparing the wrong bytes.
RM_ARENA_BYTES = 0x5EE08
RM_GFX_OFF = 0x1C660
RM_GFX_LOAD_OFF = 0xC350

DATA_DIR = adapter.harness.PRG.parent                # projects/buggyboy/bin — the original files


def _lib():
    lib = ctypes.CDLL(str(equiv.LIBREMASTER))
    lib.rm_arena_init.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_arena_init.restype = None
    lib.rm_assets_unpack.argtypes = [ctypes.c_void_p]
    lib.rm_assets_unpack.restype = None
    return lib


def _remaster_arena():
    """Load both data files into a fresh remaster arena and unpack — the candidate."""
    block = (ctypes.c_uint8 * RM_ARENA_BYTES)()      # zero-filled, as the game's Malloc'd block is
    arena = (ctypes.c_void_p * 6)()                  # RmArena: base + 5 region pointers
    lib = _lib()
    lib.rm_arena_init(ctypes.byref(arena), block)

    courses = (DATA_DIR / "COURSES.DAT").read_bytes()
    graphics = (DATA_DIR / "GRAPHICS.GRA").read_bytes()
    ctypes.memmove(block, courses, len(courses))
    ctypes.memmove(ctypes.byref(block, RM_GFX_OFF + RM_GFX_LOAD_OFF), graphics, len(graphics))

    lib.rm_assets_unpack(ctypes.byref(arena))
    return bytes(block)


def _recreate_arena():
    """recreate's verified g_unpack_graphics over the same two files — the reference."""
    image, _ = R._prepared_image({})
    return bytes(image[R.MEM_BASE:R.MEM_BASE + RM_ARENA_BYTES])


def test_arena_layout_matches_recreate():
    """The arena offsets are dictated by the data files; pin ours to recreate's."""
    assert RM_GFX_OFF == R.BUF_C - R.MEM_BASE
    assert RM_GFX_LOAD_OFF == R.GFX_LOAD_OFFSET
    assert 0x01900 == R.BUF_A - R.MEM_BASE
    assert 0x0F660 == R.BUF_B - R.MEM_BASE
    assert 0x57000 == R.BUF_AUX - R.MEM_BASE


def test_course_file_loads_verbatim():
    """COURSES.DAT needs no unpacking, and nothing in the graphics unpack may tread on it."""
    courses = (DATA_DIR / "COURSES.DAT").read_bytes()
    assert len(courses) == 0xF660, "COURSES.DAT is read whole; its size is the read count"
    assert _remaster_arena()[:len(courses)] == courses


def test_unpacked_arena_is_byte_identical(capsys):
    candidate = _remaster_arena()
    reference = _recreate_arena()
    assert len(candidate) == len(reference) == RM_ARENA_BYTES

    wrong = sum(1 for a, b in zip(candidate, reference) if a != b)
    # Guard against a vacuous pass: the unpack must actually fill the arena.
    filled = sum(1 for b in reference if b)
    with capsys.disabled():
        print(f"  arena {RM_ARENA_BYTES} bytes, {filled} non-zero, {wrong} differing")
    assert filled > RM_ARENA_BYTES // 2, "reference arena looks empty — staging is broken"
    assert wrong == 0, f"remaster's unpack diverges from recreate on {wrong} bytes"


@pytest.mark.parametrize("region,off,length", [
    ("graphics", RM_GFX_OFF, 0x3B000),               # the sprite arena the object blits index
    ("sprite shift tables", 0x0F660, 0xD000),        # 208 sprites x 16 shifts x 16 bytes
    ("course tables", 0x01900, 0x2000),              # buf_a: scroll/object selectors + descriptors
])
def test_region_matches_recreate(region, off, length):
    """Spot the named regions individually, so a failure names the phase that broke it."""
    candidate = _remaster_arena()[off:off + length]
    reference = _recreate_arena()[off:off + length]
    assert candidate == reference, f"{region} region differs"
