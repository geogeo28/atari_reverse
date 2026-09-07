#!/usr/bin/env python3
"""Turn the Gamex hard-disk release of Flying Shark (Firebird 1988) back into a bootable folder.

    python3 projects/flyingshark/tools/unpack_dist.py [--bin DIR] [--quiet]

WHAT THE RELEASE IS. `bin/` holds "PP"'s 2012/2018 Gamex hard-disk install, not the original
floppies. Three layers sit between the shipped files and the 1988 program:

  RUNME.TOS      Gamex-LZ packed loader; picks the machine, loads the GOS and the cover art.
  FILES/D15RU.FIC  Gamex-LZ packed mini-OS the loader installs.  Both are WRAPPER, kept for the
                 record only — neither is the game.
  FILES/FSLA     a GEMDOS PRG whose TEXT is a 0x698-byte STUB and whose DATA is the packed game.
  FILES/FRD      one 600,440-byte blob holding every file the game opens, back to back.

The stub is what makes FRD usable: it hooks `trap #1` and serves Fopen/Fclose/Fread/Fseek/Fsfirst/
Fcreate out of FRD, so the game's own `A\\NAME` opens resolve inside the blob and never touch a
filesystem. Its directory — 16-byte entries of a 12-byte name plus a be32 start offset, ending on a
`ZZ.TOS` terminator whose start IS the blob length — is therefore the authoritative file list, and
this tool parses it rather than carrying a copy. notes/loader.md reads the stub instruction by
instruction.

WHAT THIS WRITES, under `bin/`:

  FLYSHARK.PRG     the game, depacked out of FSLA's DATA. THE analysis target.
  RUNME_PLAIN.PRG  RUNME.TOS depacked      } wrapper, for the record: neither is ever loaded by
  GOS.PRG          D15RU.FIC depacked      } the game, and nothing downstream reads them.
  disk/AUTO/FLYSHARK.PRG + disk/A/<NAME>   a folder a plain TOS boots the game from.

The `disk/` layout works because the game asks for its files by the RELATIVE paths `A\\FLY_SHK.NEO`,
`A\\SPRITES.cru`, `A\\HSC_0.DAT` ... — a subdirectory `A` next to the program, which is exactly what
the floppy release must have had. So once the payload is out of FSLA, the stub and the whole Gamex
runtime become unnecessary: TOS's own GEMDOS answers the same opens. `tools/boot_shots.py` boots it.

Every structural fact above is ASSERTED, not assumed: a release that is not this one must fail here
and say which invariant broke, rather than write a plausible-looking folder that does not run.
"""
import hashlib
import os
import struct
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from depack_gamex import find_stream  # noqa: E402  (needs the path above)

# --- the shipped files -----------------------------------------------------------------------
FILES_SUBDIR = "FILES"
PACKED_LOADER = "RUNME.TOS"
PACKED_GOS = "D15RU.FIC"
PACKED_GAME = "FSLA"
CONTAINER = "FRD"

DEPACKED_LOADER = "RUNME_PLAIN.PRG"
DEPACKED_GOS = "GOS.PRG"
DEPACKED_GAME = "FLYSHARK.PRG"

# The folder a plain TOS runs the game out of. `A` is the game's own name for it — every filename
# in its DATA is spelled `A\<NAME>` — so the subdirectory name is not a choice this tool makes.
DISK_SUBDIR = "disk"
GAME_DATA_SUBDIR = "A"
# The program goes in `AUTO\`, and that is not a convenience: TOS runs `\AUTO\*.PRG` on the boot
# drive BEFORE it loads the desktop, so the program gets the lowest TPA the machine can give it. The
# game needs that. It asks for a fixed 320x200 screen at $70000/$78000 and builds its scroll ring
# down from Physbase, and the ring only clears the program's own BSS if the program loaded low —
# started from the desktop instead, the ring lands on top of it and the game dies. The measured
# numbers are in notes/loader.md, "Where the screen lives".
AUTO_SUBDIR = "AUTO"

# The one output anything downstream depends on. Pinning its digest here means a change in the
# depacker, in the stream search or in the shipped bytes is caught in the run that causes it.
GAME_SHA256 = "659c09d5f9c8f42f1fc3c7e29aa6d63649df0e3886b0544e23252a01e4325c89"

# --- GEMDOS executable header ------------------------------------------------------------------
PRG_MAGIC = 0x601A
# magic, text, data, bss, symbol-table lengths, reserved, program flags, absflag.
PRG_HEADER_FORMAT = ">HIIIIIIH"
PRG_HEADER_BYTES = struct.calcsize(PRG_HEADER_FORMAT)   # 28
# A set absflag means "no relocation table": the image is position-INDEPENDENT and TOS loads it
# wherever it likes. MODULE.BAK is built that way because the game loads it as data, into its own
# BSS, and calls it there without ever relocating it.
ABSFLAG_POSITION_INDEPENDENT = 0xFFFF

# --- the stub's file directory -----------------------------------------------------------------
# All three are read straight off the stub's own code (notes/loader.md): the Fopen matcher walks
# from `lea $538(pc),a1` in steps of 16 until it reaches the end of TEXT, comparing the name field
# and taking the start offset from the longword behind it.
DIRECTORY_TEXT_OFFSET = 0x538
DIRECTORY_ENTRY_BYTES = 16
DIRECTORY_NAME_BYTES = 12
# The last entry is a terminator, not a file: it exists only so the entry before it has an end.
TERMINATOR_NAME = "ZZ.TOS"

# --- what the container must hold ---------------------------------------------------------------
CONTAINER_BYTES = 600_440
# A NEOchrome picture: 128-byte header (flag word, resolution word, 16 palette words, ...) followed
# by one whole low-res ST screen. The flag word is zero on every NEO file ever written.
NEO_NAME = "FLY_SHK.NEO"
NEO_HEADER_BYTES = 128
NEO_SCREEN_BYTES = 32_000
NEO_BYTES = NEO_HEADER_BYTES + NEO_SCREEN_BYTES
NEO_FLAG_WORD = 0

MODULE_NAME = "MODULE.BAK"


def read(*path_parts):
    with open(os.path.join(*path_parts), "rb") as handle:
        return handle.read()


def write(data, *path_parts):
    path = os.path.join(*path_parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def prg_header(image, what):
    """The eight GEMDOS header fields, refusing anything that is not an executable."""
    if len(image) < PRG_HEADER_BYTES:
        raise ValueError(f"{what}: {len(image)} bytes is shorter than a {PRG_HEADER_BYTES}-byte GEMDOS header")
    fields = struct.unpack(PRG_HEADER_FORMAT, image[:PRG_HEADER_BYTES])
    if fields[0] != PRG_MAGIC:
        raise ValueError(f"{what}: magic {fields[0]:#06x}, expected PRG_MAGIC {PRG_MAGIC:#06x}")
    return fields


def depack(packed, what):
    """One Gamex-LZ stream -> the GEMDOS executable it inflates to, with the offset it was found at."""
    start, image = find_stream(packed)
    if image is None:
        raise ValueError(f"{what}: no Gamex-LZ stream in {len(packed)} bytes — not this packer?")
    _magic, text, data, _bss, symbols, _reserved, _flags, _absflag = prg_header(image, what)
    stated = PRG_HEADER_BYTES + text + data + symbols
    if stated > len(image):
        raise ValueError(f"{what}: header claims {stated} bytes of header+text+data+symbols, "
                         f"but only {len(image)} were depacked")
    return start, image


def directory_entries(stub):
    """The stub's file directory as (name, start offset) pairs, in the order the stub stores them.

    The table runs from DIRECTORY_TEXT_OFFSET to the end of TEXT — the same bound the stub's own
    matcher uses to decide a name is not in the container.
    """
    _magic, text, _data, _bss, _symbols, _reserved, _flags, _absflag = prg_header(stub, PACKED_GAME)
    table = stub[PRG_HEADER_BYTES + DIRECTORY_TEXT_OFFSET:PRG_HEADER_BYTES + text]
    if len(table) % DIRECTORY_ENTRY_BYTES:
        raise ValueError(f"{PACKED_GAME}: the directory is {len(table)} bytes, not a whole number of "
                         f"{DIRECTORY_ENTRY_BYTES}-byte entries")
    entries = []
    for at in range(0, len(table), DIRECTORY_ENTRY_BYTES):
        entry = table[at:at + DIRECTORY_ENTRY_BYTES]
        name = entry[:DIRECTORY_NAME_BYTES].rstrip(b"\0").decode("ascii")
        start = struct.unpack(">I", entry[DIRECTORY_NAME_BYTES:])[0]
        entries.append((name, start))
    return entries


def container_files(entries, container):
    """(name, start, size) for every real file, with the terminator checked and dropped.

    A file ends where the next entry starts — the directory stores no lengths at all, which is why
    the terminator has to be there and has to point at the very end of the blob.
    """
    if len(entries) < 2:
        raise ValueError(f"{PACKED_GAME}: {len(entries)} directory entries — too few to hold a file plus its terminator")
    starts = [start for _name, start in entries]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError(f"{PACKED_GAME}: directory offsets are not strictly increasing: {starts}")
    terminator_name, terminator_start = entries[-1]
    if terminator_name != TERMINATOR_NAME:
        raise ValueError(f"{PACKED_GAME}: the directory ends on {terminator_name!r}, expected TERMINATOR_NAME "
                         f"{TERMINATOR_NAME!r}")
    if terminator_start != len(container):
        raise ValueError(f"{CONTAINER}: the {TERMINATOR_NAME} terminator says the blob is {terminator_start} bytes, "
                         f"but it is {len(container)}")
    return [(name, start, next_start - start)
            for (name, start), next_start in zip(entries[:-1], starts[1:])]


def check_neo(picture):
    """The title screen has to be a NEOchrome file, or the palette this project reads is noise."""
    if len(picture) != NEO_BYTES:
        raise ValueError(f"{NEO_NAME}: {len(picture)} bytes, expected NEO_BYTES {NEO_BYTES}")
    flag = struct.unpack(">H", picture[:2])[0]
    if flag != NEO_FLAG_WORD:
        raise ValueError(f"{NEO_NAME}: flag word {flag:#06x}, expected NEO_FLAG_WORD {NEO_FLAG_WORD:#06x}")


def check_module(module):
    """MODULE.BAK is the PSG driver: an executable the game loads as data and calls in place."""
    _magic, _text, _data, _bss, _symbols, _reserved, _flags, absflag = prg_header(module, MODULE_NAME)
    if absflag != ABSFLAG_POSITION_INDEPENDENT:
        raise ValueError(f"{MODULE_NAME}: absflag {absflag:#06x}, expected ABSFLAG_POSITION_INDEPENDENT "
                         f"{ABSFLAG_POSITION_INDEPENDENT:#06x} — the game never relocates it")


def check_game(image):
    digest = hashlib.sha256(image).hexdigest()
    if digest != GAME_SHA256:
        raise ValueError(f"{DEPACKED_GAME}: sha256 {digest}, expected GAME_SHA256 {GAME_SHA256}")


def unpack(bin_dir, report=print):
    """Depack the three wrappers, split the container, and lay out the bootable folder."""
    files_dir = os.path.join(bin_dir, FILES_SUBDIR)
    disk_dir = os.path.join(bin_dir, DISK_SUBDIR)

    for packed_name, depacked_name, where in ((PACKED_LOADER, DEPACKED_LOADER, bin_dir),
                                              (PACKED_GOS, DEPACKED_GOS, files_dir),
                                              (PACKED_GAME, DEPACKED_GAME, files_dir)):
        packed = read(where, packed_name)
        start, image = depack(packed, packed_name)
        if depacked_name == DEPACKED_GAME:
            check_game(image)
        _magic, text, data, bss, symbols, _reserved, _flags, _absflag = prg_header(image, depacked_name)
        write(image, bin_dir, depacked_name)
        report(f"{packed_name:>12} ({len(packed):7,} B)  stream@{start:#06x} -> {depacked_name:<16} "
               f"{len(image):7,} B  text={text:#x} data={data:#x} bss={bss:#x} sym={symbols:#x}")

    stub = read(files_dir, PACKED_GAME)
    container = read(files_dir, CONTAINER)
    if len(container) != CONTAINER_BYTES:
        raise ValueError(f"{CONTAINER}: {len(container)} bytes, expected CONTAINER_BYTES {CONTAINER_BYTES}")
    files = container_files(directory_entries(stub), container)

    write(read(bin_dir, DEPACKED_GAME), disk_dir, AUTO_SUBDIR, DEPACKED_GAME)
    report(f"\n{DEPACKED_GAME} -> {os.path.join(DISK_SUBDIR, AUTO_SUBDIR, DEPACKED_GAME)} (TOS runs it before the desktop)")
    report(f"{CONTAINER} directory ({len(files)} files, {len(container):,} B) -> "
           f"{os.path.join(DISK_SUBDIR, GAME_DATA_SUBDIR)}/")
    report(f"  {'NAME':<12} {'OFFSET':>10} {'SIZE':>10}")
    for name, start, size in files:
        content = container[start:start + size]
        if name == NEO_NAME:
            check_neo(content)
        if name == MODULE_NAME:
            check_module(content)
        write(content, disk_dir, GAME_DATA_SUBDIR, name)
        report(f"  {name:<12} {start:#10x} {size:>10,}")
    return files


def main():
    bin_dir = os.path.join(PROJECT_DIR, "bin")
    argv = sys.argv[1:]
    if "--bin" in argv:
        bin_dir = argv[argv.index("--bin") + 1]
    report = (lambda *_args: None) if "--quiet" in argv else print
    try:
        unpack(bin_dir, report)
    except (OSError, ValueError) as failure:
        raise SystemExit(f"unpack failed: {failure}")


if __name__ == "__main__":
    main()
