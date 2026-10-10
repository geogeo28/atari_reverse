#!/usr/bin/env python3
"""THE TEST ACCESSORY AND THE DISK IT BOOTS FROM — built once, here, for both of its users.

    python tools/accessory_disk.py --out build/acc/ACCDISK.ST

`test/acc/testacc.S` is a real GEM desk accessory (its own header says what it does). Two things need it on a floppy:
`tools/preinit_snapshot.py`, which boots Hatari with that floppy in drive A: from power-on to capture the accessory
pre-init machine (`make preinit-acc`), and `test/aes_boot.py`, whose model of the floppy driver serves the same
floppy to the ROM's own boot. So the build and the image are one module with no dependence on the test harness.

ONE DISK FOR EVERY MODE, UP TO THE ACCESSORIES' OWN CLUSTERS. An accessory's mode is a word of its TEXT, and
`tools/st_build.py` derives a disk's serial from its files' contents — so a disk BUILT from patched files would be
another disk to the driver's change detector, with another boot sector than the one GEMDOS read before `gem_entry`.
`disk_of` therefore builds the image from the UNPATCHED file and patches the mode word in the image, inside each
accessory's own data cluster: the boot sector (its serial), both FATs and the root directory — everything the
machine reads before `gem_entry` — are the same bytes whatever the modes (`test_aes_boot.py` holds it).
"""
import argparse
import struct
import subprocess
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))

import st_build                                                   # noqa: E402

import addrs                                                      # noqa: E402

ACC_DIR = RECREATE / "test" / "acc"
SOURCE, LINK, WRAPPER = ACC_DIR / "testacc.S", ACC_DIR / "acc.ld", RECREATE / "atari" / "mkprg.py"
PRG_HEADER_BYTES = addrs.parse(RECREATE / "include" / "gemdos" / "pexec_load.h")["PRG_HEADER_BYTES"]
TARGET_CPU = "-m68000"
QUIET, FIND, WRITE, MULTI = 0, 1, 2, 4  # `acc_mode`'s bits, as testacc.S names them (ACC_FIND, ACC_WRITE, ACC_MULTI)
REGISTER, HIDE = 8, 16                  # ...ACC_REGISTER: an entry of the desk's menu; ACC_HIDE: the bar hidden on AC_OPEN
DOUBLE = 32                             # ...ACC_DOUBLE: MULTI's wait asks for two clicks (a second multi-click waiter)
# A MODE IS A LONGWORD OF THE ACCESSORY'S TEXT: `acc_kind` — a window's kind, GEM's gadget bits, 0 for no window — and
# then `acc_mode`, the flags above (testacc.S lays the two words side by side).
WINDOW_SHIFT = 16
WINDOW_KINDS = 0x0fff                   # GEM's twelve gadget bits
MODE = struct.Struct(">I")
NAMES = ("TESTACC1", "TESTACC2")
EXTENSION = "ACC"
_LINKED_SYMBOL_KINDS = "TtDdBb"         # `nm`'s text, data and BSS symbols: the ones at an offset of the program

Accessory = namedtuple("Accessory", "file symbols")
Accessory.__doc__ = """The built accessory: its `.ACC` file's bytes and its symbols, `{name: offset from the TEXT
base}` — TEXT, DATA and BSS are one run from there, as GEMDOS lays them."""


def build(source, link, wrapper):
    """The accessory assembled, linked at 0 with its relocations kept, and wrapped as a GEMDOS program by
    atari/mkprg.py — from the three TEXTS, so a caller that keeps the answer keys it by them."""
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        for name, text in (("testacc.S", source), ("acc.ld", link), ("mkprg.py", wrapper)):
            (work / name).write_text(text)

        def tool(*command):
            return subprocess.run(command, cwd=work, check=True, capture_output=True, text=True).stdout
        tool("m68k-elf-gcc", TARGET_CPU, "-c", "testacc.S", "-o", "testacc.o")
        tool("m68k-elf-gcc", TARGET_CPU, "-nostdlib", "-T", "acc.ld", "-Wl,--emit-relocs",
             "-Wl,--no-warn-rwx-segments", "testacc.o", "-o", "testacc.elf")
        tool("m68k-elf-objcopy", "-O", "binary", "testacc.elf", "testacc.bin")
        tool(sys.executable, "mkprg.py", "testacc.elf", "testacc.bin", "TESTACC.ACC")
        symbols = {name: int(value, 16) for value, kind, name in map(str.split, tool("m68k-elf-nm", "testacc.elf").splitlines())
                   if kind in _LINKED_SYMBOL_KINDS}
        return Accessory((work / "TESTACC.ACC").read_bytes(), symbols)


def built():
    """...from the tree's own three files."""
    return build(SOURCE.read_text(), LINK.read_text(), WRAPPER.read_text())


def with_a_window(kind, mode=QUIET):
    """`mode` with a window of `kind` (GEM's gadget bits) opened before the wait."""
    assert kind and not kind & ~WINDOW_KINDS, f"{kind:#x} is no window kind"
    return mode | kind << WINDOW_SHIFT


def mode_word_at(accessory):
    """Where the mode longword lies in the accessory's FILE: at `acc_kind`, `acc_mode` the word after it."""
    assert accessory.symbols["acc_mode"] == accessory.symbols["acc_kind"] + MODE.size // 2, "the mode's two words lie apart"
    return PRG_HEADER_BYTES + accessory.symbols["acc_kind"]


def disk_with(files=()):
    """A 720 KB floppy as `tools/st_build.py` builds the capture's blank one, holding `files` (`(name, bytes)`) in
    its root, in that order."""
    with tempfile.TemporaryDirectory() as work:
        placed = []
        for name, data in files:
            (Path(work) / name).write_bytes(data)
            placed.append((name, Path(work) / name))
        image = Path(work) / "disk.st"
        st_build.build(image, placed)
        return image.read_bytes()


def file_at(index):
    """Where the `index`-th file of a `disk_with` image begins: `st_build` lays files in consecutive clusters, and
    the accessory is shorter than one."""
    return (st_build.FIRST_DATA_SECTOR + index * st_build.SECTORS_PER_CLUSTER) * st_build.SECTOR_BYTES


def disk_of(accessory, modes):
    """The disk with one test accessory per mode, named NAMES in turn (the module's docstring: built unpatched,
    each mode word then laid in the image)."""
    assert len(modes) <= len(NAMES) and len(accessory.file) <= st_build.CLUSTER_BYTES
    image = bytearray(disk_with(tuple((f"{name}.{EXTENSION}", accessory.file) for name, _mode in zip(NAMES, modes))))
    for index, mode in enumerate(modes):
        at = file_at(index)
        assert image[at:at + len(accessory.file)] == accessory.file, "the accessory is not where st_build lays a file"
        MODE.pack_into(image, at + mode_word_at(accessory), mode)
    return bytes(image)


def disk_path(recreate=RECREATE):
    """Where `make` writes the quiet pair's image, for the capture to boot (the Makefile's ACC_DISK)."""
    return recreate / "build" / "acc" / "ACCDISK.ST"


def serial_of(image):
    """A floppy image's three serial bytes, off its boot sector."""
    return bytes(image[st_build.BOOT_SERIAL_AT:st_build.BOOT_SERIAL_AT + st_build.BOOT_SERIAL_BYTES])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="where the image is written")
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(disk_of(built(), (QUIET,) * len(NAMES)))
    print(f"the accessory disk -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
