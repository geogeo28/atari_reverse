"""Differential tests for load_file @ 0x144e8 (src/fileio.c).

The three GEMDOS calls are served by the kit's staged-file model (TRAP_MODEL.md, Phase 4), so the
filename comes out of the game's own table and the bytes come out of ../bin/disk — the real files
`_start` loads. The image diff then covers both the copied bytes and the handle word.
"""
import ctypes
from pathlib import Path

import pytest

import abi
import harness
from harness import differential, report, stage_files

ENTRY_LOAD_FILE = 0x144e8

A_FILE_HANDLE = 0x18246          # mirror of include/fileio.h

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


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_FILE_HANDLE", "include/fileio.h", "A_file_handle"),
)
ENTRY_PROLOGUES = {
    "ENTRY_LOAD_FILE": "48e7404042672f083f3c",
}
