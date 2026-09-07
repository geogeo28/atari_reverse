#!/usr/bin/env python3
"""Pin the Flying Shark distribution's shape, so a change in the depacker or the shipped bytes shows.

    /Users/geogeo/miniconda3/envs/atari_reverse/bin/python -m pytest projects/flyingshark/tools/

`bin/` is gitignored — the release is not redistributable — so every test skips cleanly when it is
absent rather than failing on a clean checkout.

WHAT IS ACTUALLY PINNED. `unpack_dist.py` asserts its own invariants and would already raise; these
tests pin the VALUES those assertions leave free, which is what a silent regression would move: the
directory's exact contents and order, the sizes adding up to the whole container, and the digest of
the payload every downstream step (Ghidra, notes/loader.md, the Hatari run) is built on.
"""
import os
import sys

import pytest

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)

from unpack_dist import (  # noqa: E402  (needs the path above)
    AUTO_SUBDIR, CONTAINER, CONTAINER_BYTES, DEPACKED_GAME, DISK_SUBDIR, FILES_SUBDIR, GAME_SHA256,
    PACKED_GAME, TERMINATOR_NAME, container_files, depack, directory_entries, read)

BIN_DIR = os.path.join(PROJECT_DIR, "bin")
FILES_DIR = os.path.join(BIN_DIR, FILES_SUBDIR)

# The container's contents as the stub spells and orders them: the picture, the five level maps
# COUNTING DOWN from 5, thirteen graphics banks counting down from C, the sprites and the music
# driver. The order is the stub's, not sorted — a re-sort would break nothing at run time and so
# would otherwise go unnoticed.
EXPECTED_FILES = (
    "FLY_SHK.NEO",
    "LEVEL5.MAP", "LEVEL4.MAP", "LEVEL3.MAP", "LEVEL2.MAP", "LEVEL1.MAP",
    "HSC_C.DAT", "HSC_B.DAT", "HSC_A.DAT", "HSC_9.DAT", "HSC_8.DAT", "HSC_7.DAT", "HSC_6.DAT",
    "HSC_5.DAT", "HSC_4.DAT", "HSC_3.DAT", "HSC_2.DAT", "HSC_1.DAT", "HSC_0.DAT",
    "SPRITES.CRU", "MODULE.BAK",
)


def require(*path_parts):
    path = os.path.join(*path_parts)
    if not os.path.isfile(path):
        pytest.skip(f"{path} is not present (bin/ is gitignored — supply your own release)")
    return path


@pytest.fixture(scope="module")
def files():
    require(FILES_DIR, PACKED_GAME)
    container = read(require(FILES_DIR, CONTAINER))
    return container_files(directory_entries(read(FILES_DIR, PACKED_GAME)), container)


def test_directory_lists_every_file_in_the_stub_s_order(files):
    assert tuple(name for name, _start, _size in files) == EXPECTED_FILES


def test_the_terminator_is_dropped_and_not_a_file(files):
    assert TERMINATOR_NAME not in {name for name, _start, _size in files}


def test_the_files_tile_the_container_with_no_gap_or_overlap(files):
    assert sum(size for _name, _start, size in files) == CONTAINER_BYTES
    ends = [start + size for _name, start, size in files]
    assert [start for _name, start, _size in files][1:] == ends[:-1]


def test_the_depacked_game_is_the_expected_image():
    import hashlib
    _start, image = depack(read(require(FILES_DIR, PACKED_GAME)), PACKED_GAME)
    assert hashlib.sha256(image).hexdigest() == GAME_SHA256


def test_the_written_game_matches_the_payload():
    written = read(require(BIN_DIR, DEPACKED_GAME))
    _start, image = depack(read(require(FILES_DIR, PACKED_GAME)), PACKED_GAME)
    assert written == image


def test_the_bootable_folder_puts_the_game_in_auto():
    """Load-bearing, not tidy: from the desktop the game's own screen ring overwrites it mid-run.

    notes/loader.md, "Where the screen lives". A copy left at the folder's root would boot from the
    desktop instead and die on an illegal instruction a second after the last file loads.
    """
    disk = os.path.join(BIN_DIR, DISK_SUBDIR)
    require(disk, AUTO_SUBDIR, DEPACKED_GAME)
    assert not os.path.exists(os.path.join(disk, DEPACKED_GAME))
