"""Differential tests for load_file @ 0x144e8 (src/fileio.c).

The three GEMDOS calls are served by the kit's staged-file model (TRAP_MODEL.md, Phase 4), so the
filename comes out of the game's own table and the bytes come out of ../bin/disk — the real files
`_start` loads. The image diff then covers both the copied bytes and the handle word.
"""
import ctypes
import random
from pathlib import Path

import pytest

import abi
import harness
from harness import differential, report, stage_files

ENTRY_LOAD_FILE = 0x144e8
ENTRY_ASTEROIDS_LOAD_AND_BUILD = 0x156ac

# --- mirrors of include/fileio.h ---
A_FILE_HANDLE = 0x18246
A_FILENAME_BIGAST_DAT = 0x1974d
ASTEROID_FILE_BYTES = 0xf00
# --- mirrors of include/sprite.h: the geometry the asteroid build lays out ---
ASTEROID_FRAME_ROWS = 32
ASTEROID_FRAME_CELLS = 3
ASTEROID_SOURCE_CELLS = 2
ASTEROID_SPRITES = 6
SPRITE_MASKED_ROW_BYTES = 10
SPRITE_PRESHIFT_SLOTS = 8
ASTEROID_SOURCE_BYTES = ASTEROID_FRAME_ROWS * ASTEROID_SOURCE_CELLS * SPRITE_MASKED_ROW_BYTES
ASTEROID_FRAME_BYTES = ASTEROID_FRAME_CELLS * ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES
ASTEROID_BANK_BYTES = SPRITE_PRESHIFT_SLOTS * ASTEROID_FRAME_BYTES
# --- mirrors of include/scroll.h and include/video.h: where the build reads and writes ---
A_TILE_SET_BASE = 0x4b3be
A_BACKDROP_PAGE0 = 0x1a8ae

DISK = Path(__file__).resolve().parents[2] / "bin" / "disk"

# (the name's address in the game's own table at 0x19686, the file on the disk). The names in the
# image are lowercase and the extracted disk holds them uppercase, so the staged name is read back
# out of the IMAGE — a staged name that did not match the image's bytes would fail to open, and the
# model refuses rather than fabricating a handle, so this cannot pass by accident.
SHIPPED_FILES = (
    (0x197b4, "EXTCHARS.DAT"),   # the font, 1920 bytes
    (0x1969d, "POWER.DAT"),      # the power gauge's four frames, 1024
    (0x196c6, "STATUS.PI1"),     # the status panel picture, 8480
    (0x196a7, "LEV1.MAP"),       # a level map, 8580
)

harness._lib.g_load_file.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_load_file.restype = None
harness._lib.g_asteroids_load_and_build.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_asteroids_load_and_build.restype = None


def _image_name(address):
    """The 0-terminated filename the game's table holds at `address`."""
    raw = bytes(harness.BASE_IMAGE[address:address + harness.OS_FS_NAME])
    return raw[:raw.index(0)].decode("ascii")


# Read once at import, like test_text.py's font: several cases stage the same file, and the largest
# is 8.5 KB.
DISK_BYTES = {name: (DISK / name).read_bytes() for _address, name in SHIPPED_FILES}


def _load_case(name_address, disk_file, length, destination=abi.SCRATCH, poison=False):
    data = DISK_BYTES[disk_file]
    pokes, _handles = stage_files([(_image_name(name_address), data)])
    # Noise under the destination, so a read that copies too few bytes leaves some of it standing.
    pokes[destination] = bytes(range(0x100)) * ((len(data) // 0x100) + 2)
    regs = {"a0": name_address, "a1": destination, "d1": length, "_pokes": pokes}
    diffs, _ = differential(
        ENTRY_LOAD_FILE, regs,
        lambda lib, buf: lib.g_load_file(buf, name_address, destination, length), poison=poison)
    assert not diffs, f"{disk_file} length={length:#x}\n{report(diffs)}"


@pytest.mark.parametrize("name_address,disk_file", SHIPPED_FILES)
def test_load_a_shipped_file_whole(name_address, disk_file):
    """The game's own call: the whole file, at its real name, into a staged destination."""
    _load_case(name_address, disk_file, len(DISK_BYTES[disk_file]))


@pytest.mark.parametrize("length", (0, 1, 2, 0x100, 0x780 - 1))
def test_load_a_short_count(length):
    """A count under the file's own length reads exactly that many bytes and no more — the rest of
    the destination must keep its noise, which is what the seeded buffer is for."""
    _load_case(*SHIPPED_FILES[0], length)


def test_load_a_count_past_the_end_of_the_file():
    """Fread serves what is there and stops. The count is not clamped by the caller, so this is the
    model's `min(count, remaining)` — and the bytes past the file must be untouched."""
    _load_case(*SHIPPED_FILES[0], len(DISK_BYTES[SHIPPED_FILES[0][1]]) * 2)


def test_load_leaves_the_handle_word_behind():
    """The handle is stored to `A_file_handle` and READ BACK for the close, so the word is program
    output. Two loads in a row through one stub prove it is rewritten rather than accumulated —
    both use slot 0, so both handles are the same value and only the store's presence is at stake.

    Driven as one run because the handle is the state that carries between the two calls.

    IT LEANS ON A0 SURVIVING THE FIRST CALL, and `load_file` does not save it — its `movem.l #$4040`
    keeps only D1 and A1. A0 comes back holding the filename only because the trap model leaves it
    alone across `trap #1`, which real GEMDOS does not (it clobbers a0-a2/d0-d2, a bug class this
    workspace has already met on hardware). If the model is ever made faithful there, this case
    fails on the SECOND `Fopen` reading a garbage name — loudly, since the staged-file model refuses
    rather than fabricating a handle — and the fix is to re-seed A0 between the calls, not to
    suspect `load_file`.
    """
    name_address, disk_file = SHIPPED_FILES[0]
    data = DISK_BYTES[disk_file]
    pokes, _handles = stage_files([(_image_name(name_address), data)])
    pokes.update(abi.call_sequence_pokes([ENTRY_LOAD_FILE, ENTRY_LOAD_FILE]))
    pokes[A_FILE_HANDLE] = b"\x5a\x5a"      # neither handle, so a missing store shows up
    regs = {"a0": name_address, "a1": abi.SCRATCH, "d1": len(data), "_pokes": pokes}

    def glue(lib, buf):
        lib.g_load_file(buf, name_address, abi.SCRATCH, len(data))
        lib.g_load_file(buf, name_address, abi.SCRATCH, len(data))

    diffs, _ = differential(abi.STUB, regs, glue)
    assert not diffs, report(diffs)


def test_load_attribution():
    """Poison the copied bytes, the handle word and the file table's own cursor/open fields."""
    _load_case(*SHIPPED_FILES[0], 0x200, poison=True)



# ================================================================================================
# asteroids_load_and_build @ 0x156ac
# ================================================================================================

BIGAST = "BIGAST.DAT"
BIGAST_BYTES = (DISK / BIGAST).read_bytes()
# The whole destination the six banks occupy, plus a guard bank past them — 0x1e00 bytes a candidate
# with one sprite too many would spill into.
ASTEROID_BANKS_BYTES = ASTEROID_SPRITES * ASTEROID_BANK_BYTES
NOISE_GUARD_BANKS = 1


def test_the_read_count_is_exactly_the_six_sprites():
    """`move.l #$f00,d1` is a LENGTH here, not a cap — and BIGAST.DAT is exactly that long.

    include/fileio.h says the two agree by arithmetic rather than by one being written as the other,
    and this is where that claim is held: six 32x32 masked sprites at ten bytes a cell-row is the
    read count, and the shipped file is neither longer nor shorter. include/init.h's two LEVEL reads
    are the contrasting case — those really are caps, and their files vary.
    """
    assert ASTEROID_FILE_BYTES == ASTEROID_SPRITES * ASTEROID_SOURCE_BYTES
    assert len(BIGAST_BYTES) == ASTEROID_FILE_BYTES


def _asteroid_case(payload, seed=0, poison=False, note=""):
    """Stage `payload` as BIGAST.DAT and run the whole load-expand-preshift chain.

    Both ends are seeded with noise: the staging buffer, so a read short of the count leaves some of
    it standing, and the six banks plus a seventh, so a build that ran one sprite too far — or wrote
    a frame at the wrong stride — lands on bytes that are not zero.
    """
    pokes, _handles = stage_files([(_image_name(A_FILENAME_BIGAST_DAT), payload)])
    rng = random.Random(seed)
    pokes[A_TILE_SET_BASE] = rng.randbytes(ASTEROID_FILE_BYTES * 2)
    pokes[A_BACKDROP_PAGE0] = rng.randbytes(ASTEROID_BANKS_BYTES
                                            + NOISE_GUARD_BANKS * ASTEROID_BANK_BYTES)
    diffs, _ = differential(ENTRY_ASTEROIDS_LOAD_AND_BUILD, {"_pokes": pokes},
                            lambda lib, buf: lib.g_asteroids_load_and_build(buf),
                            poison=poison, max_insns=ASTEROID_MAX_INSNS)
    assert not diffs, f"{note}\n{report(diffs)}"


# The build copies 6 x 8 x 32 rows of five words and then shifts six banks a total of 42 one-pixel
# passes, so it is well past the default cap.
ASTEROID_MAX_INSNS = 20_000_000


def test_asteroids_load_and_build_from_the_shipped_file():
    """The game's own call, over the real BIGAST.DAT.

    One run covers all three stages: the file lands in the tile-set staging buffer, six sprites
    become six banks of eight identical three-cell frames in `A_backdrop_page0`, and each bank is
    then preshifted in place. The bank stride, the source stride and the blank third cell are all in
    the diff.

    WHAT NO CASE HERE HOLDS is that the two passes are SEPARATE. Each bank's expansion and its
    preshift touch only that bank (and the expansion also reads the staging buffer, which the
    preshift never writes), so interleaving them into one loop is byte-identical on every input —
    src/fileio.c says so and STATUS.md records it as an unpinned residual rather than a covered one.
    """
    _asteroid_case(BIGAST_BYTES, seed=1, note="shipped BIGAST.DAT")


ASTEROID_FUZZ_CHUNKS = 4
ASTEROID_FUZZ_CASES = 8


@pytest.mark.parametrize("chunk", range(ASTEROID_FUZZ_CHUNKS))
def test_asteroids_load_and_build_over_synthetic_sprites(chunk):
    """The same chain over pseudorandom sprite bytes staged under BIGAST.DAT's own name.

    The staged-file model serves whatever bytes a case gives it, so this drives mask words and plane
    words the artwork never produces — every bit of every mask set and clear across the six sprites,
    which is what the `roxr` carry chain inside `asteroid_preshift_bank` is sensitive to. The real
    file exercises one point of that space.
    """
    for case in range(ASTEROID_FUZZ_CASES // ASTEROID_FUZZ_CHUNKS):
        seed = 0x156ac + chunk * ASTEROID_FUZZ_CASES + case
        _asteroid_case(random.Random(seed).randbytes(ASTEROID_FILE_BYTES), seed=seed,
                       note=f"synthetic seed={seed}")


def test_asteroids_load_and_build_over_a_short_file():
    """A file shorter than the read count: Fread serves what is there and the build runs anyway.

    The bytes past the file's end are whatever the staging buffer already held, so the last sprites
    are built out of the case's own noise — which is exactly what the original does and what makes
    "the read count is not clamped by the caller" observable here as well as in `load_file`'s own
    battery.
    """
    _asteroid_case(BIGAST_BYTES[:ASTEROID_SOURCE_BYTES + 1], seed=5, note="short BIGAST.DAT")


def test_asteroids_load_and_build_attribution():
    """Poison the whole output: the staged bytes, the six banks and the handle word."""
    _asteroid_case(BIGAST_BYTES, seed=2, poison=True, note="poison")


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_FILE_HANDLE", "include/fileio.h", "A_file_handle"),
    ("A_FILENAME_BIGAST_DAT", "include/fileio.h", "A_filename_bigast_dat"),
    ("ASTEROID_FILE_BYTES", "include/fileio.h", "ASTEROID_FILE_BYTES"),
    ("ASTEROID_FRAME_ROWS", "include/sprite.h", "ASTEROID_FRAME_ROWS"),
    ("ASTEROID_FRAME_CELLS", "include/sprite.h", "ASTEROID_FRAME_CELLS"),
    ("ASTEROID_SOURCE_CELLS", "include/sprite.h", "ASTEROID_SOURCE_CELLS"),
    ("ASTEROID_SPRITES", "include/sprite.h", "ASTEROID_SPRITES"),
    ("SPRITE_MASKED_ROW_BYTES", "include/sprite.h", "SPRITE_MASKED_ROW_BYTES"),
    ("SPRITE_PRESHIFT_SLOTS", "include/sprite.h", "SPRITE_PRESHIFT_SLOTS"),
    ("A_TILE_SET_BASE", "include/scroll.h", "A_tile_set_base"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
)
ENTRY_PROLOGUES = {
    "ENTRY_LOAD_FILE": "48e7404042672f083f3c",
    "ENTRY_ASTEROIDS_LOAD_AND_BUILD": "41f90001974d43f90004b3be",
}
