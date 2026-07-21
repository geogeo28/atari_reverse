"""test_assets_bounds.py — the unpack refuses a malformed GRAPHICS.GRA instead of leaving the arena.

The RLE stream is self-terminating, so nothing but the end marker stops the decoder. A truncated or
foreign file simply has no marker, and an unbounded decode writes until it walks out of the arena —
on the ST that is a wild write through the object records, road geometry and the rest of the TPA.

A size check at the call site cannot stand in for this: a file can be any length and still carry an
unterminated stream. So the bound lives in `rm_assets_unpack`, and these tests are what hold it
there. They deliberately include a mid-file truncation, which is the case a floor-only size check
lets through.

Every case asserts the arena is untouched beyond its end, using a guarded allocation whose trailing
canary must survive.
"""
import ctypes

import assets_load as al
import pytest

CANARY = b"\xa5" * 4096                             # trailing guard: any overrun scribbles on it
GFX_DST_OFF = al.RM_GFX_OFF + al.RM_GFX_LOAD_OFF
# Offset of the RLE stream WITHIN the file — the header's length. Not to be confused with
# RM_GFX_LOAD_OFF, which is where the file lands in the arena.
GFX_STREAM_FILE_OFF = 0xD00


def _unpack(graphics: bytes):
    """Run rm_assets_unpack over `graphics` in a canary-guarded arena. -> (ok, canary_intact)."""
    lib = ctypes.CDLL(str(al.adapter.LIBREMASTER))
    lib.rm_arena_init.argtypes = [ctypes.POINTER(al.RmArena), ctypes.POINTER(ctypes.c_uint8)]
    lib.rm_arena_init.restype = None
    lib.rm_assets_unpack.argtypes = [ctypes.POINTER(al.RmArena), ctypes.c_uint32]
    lib.rm_assets_unpack.restype = ctypes.c_bool

    block = (ctypes.c_uint8 * (al.RM_ARENA_BYTES + len(CANARY)))()
    ctypes.memmove(ctypes.byref(block, al.RM_ARENA_BYTES), CANARY, len(CANARY))
    arena = al.RmArena()
    lib.rm_arena_init(ctypes.byref(arena), block)

    courses = (al.DATA_DIR / "COURSES.DAT").read_bytes()
    ctypes.memmove(block, courses, len(courses))
    ctypes.memmove(ctypes.byref(block, GFX_DST_OFF), graphics, len(graphics))

    ok = lib.rm_assets_unpack(ctypes.byref(arena), len(graphics))
    intact = bytes(block)[al.RM_ARENA_BYTES:] == CANARY
    return bool(ok), intact


@pytest.fixture(scope="module")
def graphics():
    return (al.DATA_DIR / "GRAPHICS.GRA").read_bytes()


def test_intact_file_is_accepted(graphics):
    ok, intact = _unpack(graphics)
    assert ok, "the real GRAPHICS.GRA must unpack"
    assert intact, "unpacking the real file overran the arena"


@pytest.mark.parametrize("keep", [
    0x1000,          # just past the header — the case a floor-only size check lets through
    0x8000,
    0x20000,
    len(b"") or 1,   # 1 byte: shorter than the header itself
])
def test_truncated_file_is_refused(graphics, keep):
    """Truncation anywhere must be refused with the arena still intact — NOT decoded past its end."""
    ok, intact = _unpack(graphics[:keep])
    assert not ok, f"a {keep}-byte GRAPHICS.GRA was accepted; the decode had no terminator to find"
    assert intact, f"a {keep}-byte GRAPHICS.GRA overran the arena"


def test_foreign_file_is_refused():
    """A file of plausible length that is not GRAPHICS.GRA at all (no markers, no terminator)."""
    ok, intact = _unpack(bytes(range(256)) * 800)   # 204800 B of non-marker literals
    assert not ok, "a foreign file was accepted"
    assert intact, "a foreign file overran the arena"


def test_unterminated_fill_run_is_refused(graphics):
    """A file of entirely legitimate length whose stream is all maximum-count fill runs and never
    terminates — the case no input-length check can catch.

    Worth knowing WHY this is refused, because it is not the output bound: the decode runs in place
    with dst below src, so the first 131072-byte run overwrites the stream's own remaining input, the
    rest degenerates into 2-byte literals, and the run ends on src exhaustion. Measured with the
    output bound removed: 211068 of 256000 output bytes used, arena intact."""
    body = bytearray(graphics)
    body[GFX_STREAM_FILE_OFF:] = b"\x12\x34\xff\xff" * 20000   # zero-run, count 0xffff, no end marker
    ok, intact = _unpack(bytes(body))
    assert not ok, "an unterminated fill-run stream was accepted"
    assert intact, "an unterminated fill-run stream overran the arena"
