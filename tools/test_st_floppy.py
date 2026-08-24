#!/usr/bin/env python3
"""The pins for `tools/st_build.py` and the reader half of `tools/st_extract.py` it writes for.

WHY IT LIVES HERE, next to the tools, and not under any `projects/<name>/recreate/test/`: both files
are game-agnostic, and a per-project suite would pin a shared tool from inside one game.
Deliberately NOT wired into any project's `make test`, which builds an oracle `.so` neither needs.

    pytest tools/test_st_floppy.py

FOUR CASES, and the failure each exists to catch:

  * the ROUND TRIP — every file the builder placed comes back out through the reader, byte for byte.
    The two halves are never verified against each other in a project's own checks (a real TOS reads
    one and writes the other, which is the better proof), so this is where they meet directly.
  * a SUBDIRECTORY THAT OUTGREW ONE CLUSTER — measured, this is the case that retired the reader the
    Wonder Boy project used to carry beside its builder: it followed only a directory's FIRST
    cluster, so a disk TOS had grown reported files that were plainly there as ABSENT. It is exactly
    the handed-back-disk case the hardware runbook depends on.
  * the BOOT SECTOR IS NOT EXECUTABLE — TOS runs sector 0 when its words sum to $1234, and a volume
    that carries no boot code must never hit it. Including the re-draw that makes it so.
  * DETERMINISM — the same file list twice is the same bytes, and two different lists are two
    different serials. The first is what makes the published sha256 mean anything; the second is what
    stops TOS reading a swapped disk through the previous one's cached directory.
"""
import hashlib
import importlib.util
import pathlib
import struct

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent


def _module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st_build = _module("st_build")
st_extract = _module("st_extract")

LABEL = "TESTVOL"
OEM = b"TSTBLD"


def _sample_files(directory, count=3, size=3000):
    """`count` throwaway files of distinguishable contents, as (dos name, host path) pairs."""
    made = []
    for index in range(count):
        path = directory / f"F{index:02d}.DAT"
        path.write_bytes(bytes([index]) * (size + index))
        made.append((path.name, str(path)))
    return made


def _build(directory, root_files, auto_files=()):
    image = directory / "volume.st"
    layout = st_build.build(image, root_files, auto_files, LABEL, OEM)
    return image, layout


def test_every_file_comes_back_out(tmp_path):
    """The round trip, root and `\\AUTO\\` alike, through the reader that is not the writer."""
    root = _sample_files(tmp_path, count=3)
    program = tmp_path / "PROG.PRG"
    program.write_bytes(b"\x60\x1a" + bytes(9000))
    auto = [(program.name, str(program))]
    image, layout = _build(tmp_path, root, auto)

    assert image.stat().st_size == st_build.TOTAL_SECTORS * st_build.SECTOR_BYTES
    assert layout.digest == hashlib.sha256(image.read_bytes()).hexdigest()

    volume = st_extract.Fat12Image(image.read_bytes())
    for name, host in root:
        assert st_extract.read_file(volume, name) == pathlib.Path(host).read_bytes()
    assert st_extract.read_file(volume, "AUTO/PROG.PRG") == program.read_bytes()
    # Either separator, either case: a caller should not have to know which the volume uses.
    assert st_extract.read_file(volume, "auto\\prog.prg") is not None
    assert st_extract.read_file(volume, "NOTHERE.BIN") is None
    assert volume.warnings == []


def test_a_subdirectory_that_outgrew_one_cluster(tmp_path):
    """A file in an `\\AUTO\\` TOS extended onto a SECOND cluster is still found.

    The builder never writes such a directory — it refuses more entries than fit one cluster — so
    the growth is done here, the way TOS does it: chain a free cluster onto the directory and put the
    entry in it. This is a disk that has been in a real machine, which is the only kind the hardware
    runbook ever reads."""
    payload = tmp_path / "PAY.BIN"
    payload.write_bytes(b"PAYLOAD!" * 64)
    entries_per_cluster = st_build.CLUSTER_BYTES // st_build.DIR_ENTRY_BYTES
    # `.` and `..` take two, so this fills the first cluster exactly.
    auto = _sample_files(tmp_path, count=entries_per_cluster - 2, size=10)
    auto = [(f"A{index:02d}.PRG", host) for index, (_name, host) in enumerate(auto)]
    image, layout = _build(tmp_path, [("PAY.BIN", str(payload))], auto)

    data = bytearray(image.read_bytes())
    root_at = ((st_build.RESERVED_SECTORS + st_build.FAT_COPIES * st_build.SECTORS_PER_FAT)
               * st_build.SECTOR_BYTES)

    def root_entry(eleven):
        for index in range(st_build.ROOT_ENTRIES):
            at = root_at + index * st_build.DIR_ENTRY_BYTES
            if data[at:at + st_build.DIR_NAME_BYTES] == eleven:
                return at
        raise AssertionError(f"{eleven!r} is not in the root this test just wrote")

    auto_at, payload_at = root_entry(st_build.dos_name("AUTO")), root_entry(st_build.dos_name("PAY.BIN"))
    auto_cluster = struct.unpack_from("<H", data, auto_at + st_extract.DIR_START_CLUSTER_OFF)[0]
    payload_cluster = struct.unpack_from("<H", data, payload_at + st_extract.DIR_START_CLUSTER_OFF)[0]
    payload_size = struct.unpack_from("<I", data, payload_at + st_extract.DIR_SIZE_OFF)[0]

    grown = layout.used_clusters + st_build.FIRST_CLUSTER          # the next unallocated cluster
    fat_at = st_build.RESERVED_SECTORS * st_build.SECTOR_BYTES
    fat_bytes = st_build.SECTORS_PER_FAT * st_build.SECTOR_BYTES
    fat = bytearray(data[fat_at:fat_at + fat_bytes])
    st_build._fat12_set(fat, auto_cluster, grown)
    st_build._fat12_set(fat, grown, st_build.FAT_END_OF_CHAIN)
    for copy in range(st_build.FAT_COPIES):
        at = (st_build.RESERVED_SECTORS + copy * st_build.SECTORS_PER_FAT) * st_build.SECTOR_BYTES
        data[at:at + len(fat)] = fat
    second = ((st_build.FIRST_DATA_SECTOR
               + (grown - st_build.FIRST_CLUSTER) * st_build.SECTORS_PER_CLUSTER)
              * st_build.SECTOR_BYTES)
    data[second:second + st_build.DIR_ENTRY_BYTES] = st_build._entry_bytes(
        st_build.dos_name("LATE.PRG"), st_build.ATTR_NONE, payload_cluster, payload_size)

    volume = st_extract.Fat12Image(bytes(data))
    assert st_extract.read_file(volume, "AUTO/LATE.PRG") == payload.read_bytes()
    assert st_extract.read_file(volume, "AUTO/A00.PRG") is not None     # the first cluster still reads
    assert volume.warnings == []


def test_the_boot_sector_is_never_the_one_tos_executes(tmp_path):
    """The sum is not $1234, and the search that guarantees it really re-draws."""
    image, _layout = _build(tmp_path, _sample_files(tmp_path, count=1))
    boot = image.read_bytes()[:st_build.SECTOR_BYTES]
    assert st_build.boot_checksum(boot) != st_build.ATARI_BOOT_EXECUTABLE_SUM

    # Force the first draw to collide. The second must be a DIFFERENT serial, and it must be the one
    # the volume gets — an accident here used to be an unactionable refusal.
    entries = [("F00.DAT", b"whatever")]
    honest = st_build.boot_checksum
    collisions = [True]

    def once(sector):
        if collisions and collisions.pop():
            return st_build.ATARI_BOOT_EXECUTABLE_SUM
        return honest(sector)

    digest = hashlib.sha256(b"".join(n.encode() + d for n, d in entries)).digest()
    first = st_build._boot_sector(digest[:st_build.BOOT_SERIAL_BYTES], OEM)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(st_build, "boot_checksum", once)
        redrawn = st_build._mountable_boot_sector(entries, OEM)
    serial = slice(st_build.BOOT_SERIAL_AT, st_build.BOOT_SERIAL_AT + st_build.BOOT_SERIAL_BYTES)
    assert redrawn[serial] != first[serial]
    assert honest(redrawn) != st_build.ATARI_BOOT_EXECUTABLE_SUM


def test_the_same_files_build_the_same_disk_and_two_disks_differ(tmp_path):
    """Determinism, and the media-change serial that must NOT be deterministic across file lists."""
    files = _sample_files(tmp_path, count=2)
    one = st_build.build(tmp_path / "one.st", files, (), LABEL, OEM)
    again = st_build.build(tmp_path / "again.st", files, (), LABEL, OEM)
    assert (tmp_path / "one.st").read_bytes() == (tmp_path / "again.st").read_bytes()
    assert one.digest == again.digest

    other = st_build.build(tmp_path / "other.st", files[:1], (), LABEL, OEM)
    serial = slice(st_build.BOOT_SERIAL_AT, st_build.BOOT_SERIAL_AT + st_build.BOOT_SERIAL_BYTES)
    assert ((tmp_path / "one.st").read_bytes()[serial]
            != (tmp_path / "other.st").read_bytes()[serial])
    assert other.digest != one.digest
