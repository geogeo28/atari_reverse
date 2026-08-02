"""Differential test for rad_depack @ 0x5d62 (src/rad.c) — the game's own .RAD/.CRU depacker.

Every case runs the ORIGINAL routine under the Musashi oracle and the reconstruction on the same
image, and requires the two to agree byte for byte over the whole image, plus on the d0 the routine
returns. The corpus is the game's own resource files, so the format is exercised by the data it was
written for rather than by anything invented here.

WHAT IS PINNED, AND BY WHICH CASES
  * the decode itself, on 41 intact streams (disk 1 plus the repaired disk 2) — the destination, the
    scratch long, and d0 (the spent bit buffer, which is not a status but is diffable all the same);
  * the routine's ONE failure branch, twice over: synthetically, by corrupting the checksum of an
    otherwise well-formed stream, which is the only way to reach it with a CLEAN decode; and on the
    disk's own four damaged overlays, where the decode is garbage as well;
  * that it writes nothing but the destination and that scratch long (`_stray_writes`), which is the
    memory surface a wrong reconstruction would show up on.

KNOWINGLY NOT PINNED
  * the failure path's 65536-iteration delay loop. It is timing, and this differential's surfaces
    are memory and d0; the oracle counts the instructions but nothing asserts on them.
  * the four damaged overlays are read from bin/disk2/, the authentic dump, but their intact
    counterparts come from bin/disk2_repaired/, a repaired HYBRID (authentic bytes outside the
    protection's holes, crack bytes inside them). A green row for one of those four proves the two
    implementations agree on those bytes, not that the bytes are what the pressed disk held.
  * `notes/rad_differential.py` is the other half of this pin, and stays worth running: it diffs the
    HOST reimplementation (tools/depack_rad.py) against the same original code. This file says
    nothing about that one.
"""
import ctypes
import struct

import pytest

import harness
from harness import differential, report
from layout import wb

# harness put tools/ on sys.path (it is where the kit lives), which is also where the container's
# host-side definition lives. Used for its header parse alone: restating the container here would be
# a third spelling of the same three longwords.
import depack_rad                                                # noqa: E402
import emu                                                       # noqa: E402
import loader                                                    # noqa: E402

ENTRY = wb("RAD_DEPACK")
SAVED_SP = wb("RAD_SAVED_SP")
SAVED_SP_LEN = wb("RAD_SAVED_SP_LEN")
BAD_CHECKSUM = wb("RAD_BAD_CHECKSUM")

# `move.l a7,$5e3a.l` — the routine's first instruction. Pins both addresses above against the
# loaded image, so a wrong constant fails here rather than as a puzzling diff.
ENTRY_INSN = b"\x23\xcf" + SAVED_SP.to_bytes(4, "big")

# --- the corpus -------------------------------------------------------------------------------
# disk1 is clean; disk2/ is the authentic dump, whose four protection-damaged overlays are decoded
# by neither implementation, so the decodable set takes all of disk 2 from the repaired extraction
# and the damaged four get their own cases. Same policy as notes/rad_differential.py.
BIN = harness.PRG.resolve().parents[2]                # projects/wonderboy/bin (PRG: bin/disk1/AUTO)
REPAIRED_DIR = "disk2_repaired"
INTACT_DIRS = ("disk1", REPAIRED_DIR)
DAMAGED_DIR = "disk2"
RAD_SUFFIX = ".RAD"
# The damaged files, recorded rather than only derived: a repair (or a re-extraction) that changed
# which files differ would otherwise silently move cases between the two batteries.
DAMAGED_NAMES = ("OVALAY4B.RAD", "OVALAY5B.RAD", "OVALAY6A.RAD", "OVALAY9A.RAD")
# The intact count is recorded for the same reason in the other direction: a glob over a directory
# that is not there returns nothing rather than raising, so a partial checkout would shrink this
# battery silently — a merely non-empty corpus would not catch it.
INTACT_COUNT = 41          # 2 on disk 1 (CREDITS, TITLESCR) + 39 under disk2_repaired/

# --- where the case lays the two buffers out in the image --------------------------------------
# Both are clear of the program (which ends at 0x218d0) and of the kit's staged-file table; the same
# placement notes/rad_differential.py uses. The CEILING deliberately differs, so do not "fix" one
# bound to match the other: these cases run under the kit's TOS model, so `_check_layout` caps the
# destination at harness.OS_FS_TABLE (the staged-file table), while notes drives bare `emu.run` with
# no such table and caps at the stack-scratch floor instead.
PACKED_AT = 0x40000        # the packed file, as if just read off disk into a load buffer
DEST_AT = 0x80000          # what the caller passes in a1
# The destination is pre-filled rather than left zeroed: a match with offset 0 sources the byte it is
# about to write, i.e. whatever the buffer last held (the game's five call sites reuse fixed load
# buffers). No corpus stream does that today, and a zeroed buffer would hide a future one.
DEST_POISON = 0x5A
# The largest run measured is TILEDATA.RAD at 1.77M instructions, and the failure path adds its
# 65536-iteration delay loop on top; this leaves room for both without capping a real run.
MAX_INSNS = 4_000_000

harness._lib.g_rad_depack.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_rad_depack.restype = ctypes.c_uint32


def _rad_files(directory):
    """Every .RAD directly in `directory` — all three corpus directories are flat."""
    return sorted((BIN / directory).glob("*" + RAD_SUFFIX))


def _damaged_files():
    """The disk2/ originals that differ from their repaired counterpart.

    Derived by comparison rather than by name so that a file whose damage was repaired away stops
    being claimed here; `test_the_corpus_is_the_one_these_cases_were_written_for` then holds the
    derived set to DAMAGED_NAMES. Paired by bare filename, which the flat layout above makes exact.
    """
    pairs = ((p, BIN / REPAIRED_DIR / p.name) for p in _rad_files(DAMAGED_DIR))
    return [p for p, repaired in pairs
            if repaired.is_file() and repaired.read_bytes() != p.read_bytes()]


INTACT = [p for d in INTACT_DIRS for p in _rad_files(d)]
DAMAGED = _damaged_files()


def _id(path):
    return str(path.relative_to(BIN))


# The two smallest intact streams carry an extra attribution (poison) pass inside their own case:
# both cores re-run on an image whose oracle-written bytes are pre-poisoned, so a destination byte
# the reconstruction never writes cannot pass by already holding the right value. Two files rather
# than the corpus, because the poison pass doubles both runs and every stream exercises the same
# write path. Selected by size, which is deterministic and so agrees across xdist workers.
POISON_PATHS = frozenset(sorted(INTACT, key=lambda p: p.stat().st_size)[:2])


def _check_layout(packed_len, unpacked_size):
    """Fail loudly if one region of the flat image lands on top of the next — the failure mode that
    would make a green diff meaningless, since both sides would be corrupted identically."""
    assert loader.PROGRAM_END <= PACKED_AT, (
        f"SWB.PRG reaches {loader.PROGRAM_END:#x}, past the packed-file buffer at {PACKED_AT:#x}")
    assert PACKED_AT + packed_len <= DEST_AT, (
        f"the {packed_len}-byte packed file at {PACKED_AT:#x} reaches into the destination buffer "
        f"at {DEST_AT:#x}")
    assert DEST_AT + unpacked_size <= harness.OS_FS_TABLE, (
        f"{unpacked_size} unpacked bytes at {DEST_AT:#x} reach the TOS model's staged-file table at "
        f"{harness.OS_FS_TABLE:#x}")


def _stray_writes(writes, unpacked_size):
    """Oracle writes the routine is not entitled to make: anything but the destination, the machine
    stack (which the diff drops) and the one scratch long it parks the entry a7 in."""
    return sorted(a for a in writes
                  if not (DEST_AT <= a < DEST_AT + unpacked_size
                          # Two-sided: A7 enters at STACK_TOP and the stack grows DOWN, so nothing
                          # at or above STACK_TOP is a legitimate call frame.
                          or emu.STACK_TOP - emu.STACK_SCRATCH <= a < emu.STACK_TOP
                          or SAVED_SP <= a < SAVED_SP + SAVED_SP_LEN))


def _depack_case(packed, unpacked_size, what, poison=False):
    """Depack `packed` on both sides and require identical memory, identical d0, no stray write."""
    _check_layout(len(packed), unpacked_size)
    pokes = {PACKED_AT: packed, DEST_AT: bytes([DEST_POISON]) * unpacked_size}
    regs = {"a0": PACKED_AT, "a1": DEST_AT, "_pokes": pokes}
    # emu.STACK_TOP is the stack pointer the oracle enters with, so it is what the original parks in
    # the scratch long. The reconstruction has no machine stack of its own, so the harness hands it
    # that value and the diff still covers the write (see g_rad_depack in src/rad.c).
    diffs, info = differential(
        ENTRY, regs,
        lambda lib, buf: lib.g_rad_depack(buf, PACKED_AT, DEST_AT, emu.STACK_TOP),
        max_insns=MAX_INSNS, poison=poison)
    assert not diffs, f"{what}\n{report(diffs)}"
    assert info["ret"] == info["regs"]["d0"], (
        f"{what}: d0 cand={info['ret']:#010x} oracle={info['regs']['d0']:#010x}")
    stray = _stray_writes(info["writes"], unpacked_size)
    assert not stray, (f"{what}: {len(stray)} write(s) outside the destination and the scratch "
                       f"long, e.g. {harness.label(stray[0])} @ {stray[0]:#x}")
    return info


def _corpus_case(path, poison=False):
    """One corpus file through `_depack_case`. Returns (info, unpacked size)."""
    packed = path.read_bytes()
    unpacked_size = depack_rad.parse_header(packed).unpacked_size
    return _depack_case(packed, unpacked_size, _id(path), poison=poison), unpacked_size


# --- the corpus is what these cases claim it is -------------------------------------------------

def test_the_corpus_is_the_one_these_cases_were_written_for():
    """Nothing checked is not a pass: an absent corpus would otherwise collect zero cases and the
    failure branch, which only the damaged files and one synthetic case reach, would be unverified.
    """
    assert len(INTACT) == INTACT_COUNT, (
        f"{len(INTACT)} {RAD_SUFFIX} file(s) under {BIN}/{{{','.join(INTACT_DIRS)}}}, not the "
        f"recorded {INTACT_COUNT} — nothing to diff, or a corpus these cases were not written for")
    assert tuple(p.name for p in DAMAGED) == DAMAGED_NAMES, (
        f"the damaged set under {BIN / DAMAGED_DIR} is {[p.name for p in DAMAGED]}, not the "
        f"recorded {list(DAMAGED_NAMES)}")


def test_the_entry_point_is_the_move_that_parks_the_stack_pointer():
    """Pins WB_RAD_DEPACK and WB_RAD_SAVED_SP against the loaded image, not against each other."""
    assert bytes(harness.BASE_IMAGE[ENTRY:ENTRY + len(ENTRY_INSN)]) == ENTRY_INSN


# --- the decode ---------------------------------------------------------------------------------

@pytest.mark.parametrize("path", INTACT, ids=[_id(p) for p in INTACT])
def test_an_intact_stream_depacks_identically(path):
    info, unpacked_size = _corpus_case(path, poison=path in POISON_PATHS)
    written = {a for a in info["writes"] if DEST_AT <= a < DEST_AT + unpacked_size}
    assert len(written) == unpacked_size, (
        f"{_id(path)}: the original wrote {len(written)} of the {unpacked_size} destination bytes — "
        f"a run that decoded less than the whole file would compare two mostly-untouched buffers")


# --- the failure branch -------------------------------------------------------------------------

def test_a_corrupted_checksum_takes_the_failure_branch():
    """The only way to reach the checksum test with a CLEAN decode, and so the case that pins the
    branch itself rather than what damaged data does on the way to it: flip one bit of the header's
    checksum and the stream still decodes byte for byte, but the residue no longer cancels.
    """
    path = min(INTACT, key=lambda p: p.stat().st_size)
    packed = bytearray(path.read_bytes())
    header = depack_rad.parse_header(bytes(packed))
    field = slice(depack_rad.HDR_LEN - 4, depack_rad.HDR_LEN)     # the checksum long, `+8..+12`
    packed[field] = struct.pack(">I", header.checksum ^ 1)
    # Re-parse rather than trust the slice: what makes this the CLEAN-decode case is that the flip
    # landed on the checksum and nowhere else, and a wrong offset here would quietly turn it into a
    # second damaged-stream case. Checked through the parse, so it holds however the field is spelt.
    corrupted = depack_rad.parse_header(bytes(packed))
    assert corrupted.checksum == header.checksum ^ 1, (
        f"the corruption did not land on the checksum field: {corrupted.checksum:#010x}, expected "
        f"{header.checksum ^ 1:#010x}")
    assert (corrupted.unpacked_size, corrupted.stream_end) == (header.unpacked_size,
                                                               header.stream_end), (
        "the corruption moved a length field as well, so this is no longer a clean decode")
    info = _depack_case(bytes(packed), header.unpacked_size, f"{_id(path)} with a corrupted checksum")
    assert info["ret"] == BAD_CHECKSUM, (
        f"a corrupted checksum returned {info['ret']:#010x}, not the failure status "
        f"{BAD_CHECKSUM:#010x}")


@pytest.mark.parametrize("path", DAMAGED, ids=[_id(p) for p in DAMAGED])
def test_a_damaged_stream_fails_identically(path):
    """The disk's own damaged overlays: the routine decodes garbage from them — reading above the
    destination, or walking the stream off the front of the file — and only then reports the bad
    checksum. The reconstruction reproduces that garbage byte for byte, deliberately: it is the
    original's behaviour, and it is what makes these files a test of the failure path rather than of
    a guard the original does not have.
    """
    info, _ = _corpus_case(path)
    assert info["ret"] == BAD_CHECKSUM, (
        f"{_id(path)}: returned {info['ret']:#010x}, not the failure status {BAD_CHECKSUM:#010x}")
