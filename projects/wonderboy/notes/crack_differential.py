#!/usr/bin/env python3
"""Ground truth for the .STX -> .ST conversion: diff the original disk 2 against the crack.

The Pasti dump of disk 2 has holes — sectors the FDC could not read cleanly, or that were
never formatted at all — and `stx_extract.py` reports them but cannot say what *should* have
been there. A cracked release of the same game can: it carries the same `OVALAY*.RAD`
overlays with the protection stripped, so wherever the two agree the conversion is right and
wherever they differ the dump lost something.

KNOWN DATA DEPENDENCY: the crack image is **not in this repo** and never will be, so `--crack`
is required and there is no default path — without it this script cannot run and says so
instead of reporting green. Everything it proves is therefore a *recorded* result,
re-checkable only by whoever has the same file — the same arrangement as
`lsd_differential.py`, which needs `bin/extracted/`. The copy these results came from was
"Wonderboy in Monsterland.st", an LSD! release of the same 1989 Activision game.

The crack's overlays are `LSD!`-packed, except a handful already stored in the game's own
container form; both are handled, so the comparison is always container-vs-container.

Every differing byte is attributed to the `.ST` sector it came from, and each such sector to
why it is wrong — which is the point of the exercise:

  ZERO-FILLED   nothing could be placed (no descriptor, an unformatted track, or `--strict`
                refusing a flagged one). Unrecoverable from the `.stx` by any means when
                there is no descriptor at all.
  UNVERIFIED    placed from a sector the FDC flagged. Comparing here is the only way to
                learn how much of it was good.

Pass `--strict` when the `.ST` under test was written with `stx_extract.py --strict`, so the
two agree on which sectors were placed; the attribution is wrong otherwise.

Usage:  crack_differential.py CONVERTED_DISK2.ST --crack PATH_TO_CRACK.ST [--strict]
Exit status: 0 the differential ran · 1 it could not run (missing input, unreadable image)
"""
import pathlib
import sys

REVERSE = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REVERSE / "tools"))
import depack_lsd                                                   # noqa: E402
import st_extract                                                   # noqa: E402
import stx_extract                                                  # noqa: E402

COMPARED_SUFFIX = ".RAD"          # the overlays; the loader and data files differ between releases
CRACK_FLAG = "--crack"
STRICT_FLAG = "--strict"
USAGE = ("usage: crack_differential.py CONVERTED_DISK2.ST %s PATH_TO_CRACK.ST [%s]"
         % (CRACK_FLAG, STRICT_FLAG))
NAME_COLUMN = 13
CAUSE_COLUMN = 11


def _load(path):
    """A FAT12 image and its regular files by full path, or exit with the reason.

    Keyed by path, not by base name: two directories may hold the same 8.3 name, and a
    base-name key would silently compare one file's bytes against another's.
    """
    try:
        image = st_extract.Fat12Image(pathlib.Path(path).read_bytes())
    except (OSError, ValueError) as err:
        sys.exit("cannot read %s as a FAT12 image: %s" % (path, err))
    entries = {entry["path"]: entry for entry in st_extract.walk(image) if not entry["is_dir"]}
    for warning in image.warnings:
        print("WARNING %s: %s" % (path, warning))
    return image, entries


def _container_form(blob):
    """The crack's copy in the same form as the original's: depacked when `LSD!`-stamped."""
    if blob[:len(depack_lsd.MAGIC)] != depack_lsd.MAGIC:
        return blob
    return bytes(depack_lsd.depack(blob, depack_lsd.parse_header(blob)))


def _file_sectors(image, entry):
    """`.ST` sector number for each 512-byte slice of a file, in order."""
    lbas = []
    for cluster in image.chain(entry["cluster"], entry["path"]):
        start = image.cluster_start_sector(cluster)
        lbas += range(start, start + image.bpb["sectors_per_cluster"])
    return lbas


def _sector_verdicts(stx_path, strict):
    """`.ST` sector -> "ZERO-FILLED" / "UNVERIFIED" for every sector that is not a clean read.

    Read from the Pasti image itself rather than guessed from the `.ST`, because a plain
    sector dump carries no record of which of its sectors were ever readable. The rule must
    match `StxImage._choose_copy`'s — a slot with both a flagged and a clean copy is placed
    from the clean one and is not unverified — so it is derived from the same candidate map.
    """
    image = stx_extract.StxImage(pathlib.Path(stx_path).read_bytes(), strict=strict)
    verdicts = {lba: "ZERO-FILLED" for lba, block in enumerate(image.sector_map) if block is None}
    for lba, copies in image.placement_candidates().items():
        if not any(image.is_trusted(sector) for _, sector in copies):
            verdicts[lba] = "UNVERIFIED"
    return verdicts


def _compare(name, mine, theirs, lbas, verdicts):
    """One file's report line, plus a line per `.ST` sector of it that does not match."""
    if len(mine) != len(theirs):
        return ["%-*s LENGTH %d vs %d in the crack — not the same file"
                % (NAME_COLUMN, name, len(mine), len(theirs))]
    if mine == theirs:
        return ["%-*s ok  %d bytes identical to the crack" % (NAME_COLUMN, name, len(mine))]
    size = stx_extract.STANDARD_SECTOR_SIZE
    lines = []
    total_wrong = 0
    for slice_index, lba in enumerate(lbas):
        start = slice_index * size
        end = min(len(mine), start + size)
        if start >= end or mine[start:end] == theirs[start:end]:
            continue
        wrong = sum(mine[i] != theirs[i] for i in range(start, end))
        total_wrong += wrong
        lines.append("    .ST sector %-4d [%#06x..%#06x] %-*s %d of %d bytes wrong"
                     % (lba, start, end - 1, CAUSE_COLUMN, verdicts.get(lba, "CLEAN-READ"),
                        wrong, end - start))
    return ["%-*s %d of %d bytes differ from the crack"
            % (NAME_COLUMN, name, total_wrong, len(mine))] + lines


def _parse_args(args):
    """(converted .ST, crack .ST, strict) — or exit 1 with the usage line."""
    if not args or args[0].startswith("-"):
        sys.exit(USAGE)
    crack = None
    strict = False
    rest = args[1:]
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == STRICT_FLAG:
            strict = True
        elif flag == CRACK_FLAG and rest and not crack:
            crack, rest = rest[0], rest[1:]
        else:
            sys.exit(USAGE)
    if not crack:
        sys.exit(USAGE)
    return args[0], crack, strict


def main():
    st_path, crack_path, strict = _parse_args(sys.argv[1:])
    stx_path = pathlib.Path(st_path).with_suffix(".stx")
    if not pathlib.Path(crack_path).exists():
        sys.exit("the crack image %s is not here — nothing was verified (see this file's "
                 "docstring: it is a deliberate external dependency)" % crack_path)
    mine_image, mine = _load(st_path)
    crack_image, theirs = _load(crack_path)
    if not stx_path.exists():
        sys.exit("%s is not beside %s — without the Pasti image no sector can be attributed "
                 "to a cause, which is the whole product here" % (stx_path, st_path))
    verdicts = _sector_verdicts(stx_path, strict)

    # The two releases lay the same overlays out in different directories, so they are paired
    # by base name — but each side is keyed by its own full path, so a name that repeats
    # within one image still resolves to one specific file.
    crack_by_name = {pathlib.PurePath(path).name: entry for path, entry in theirs.items()}
    compared = sorted(path for path in mine if path.endswith(COMPARED_SUFFIX)
                      and pathlib.PurePath(path).name in crack_by_name)
    if not compared:
        sys.exit("no %s file is present in both images — nothing was verified" % COMPARED_SUFFIX)
    for path in compared:
        entry = mine[path]
        crack_entry = crack_by_name[pathlib.PurePath(path).name]
        for line in _compare(entry["name"], mine_image.file_bytes(entry),
                             _container_form(crack_image.file_bytes(crack_entry)),
                             _file_sectors(mine_image, entry), verdicts):
            print(line)
    print("\n%d file(s) compared" % len(compared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
