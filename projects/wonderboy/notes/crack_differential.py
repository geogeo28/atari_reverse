#!/usr/bin/env python3
"""Ground truth for the .STX -> .ST conversion: diff the original disk 2 against the crack,
and — with `--patch` — write a repaired image that fills the dump's holes from it.

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
The image `--patch` writes inherits that dependency: it cannot be rebuilt — or its
provenance re-checked — without the same crack, so it is an artefact, never a source of truth.

The Pasti dump the `.ST` was converted from is the second dependency, and the sole authority on
which sectors may be overwritten — so it is never merely guessed from the `.ST`'s own name.
`--stx` names it; without the flag the sibling `NAME.stx` is tried, which is a convenience and
not a belief. Either way every sector the Pasti image read cleanly must match the `.ST` byte
for byte before one byte is patched, so pointing at the wrong disk's dump is refused instead of
silently applying someone else's hole map.

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

PATCH MODE (`--patch OUT.ST`) turns that attribution into a repair. A differing byte is taken
from the crack **only** when its sector's cause is ZERO-FILLED or UNVERIFIED — the two cases
where the dump either read nothing or read it through an FDC error. A byte that differs inside
a CLEAN-READ sector is the crack editing the game (its releases patch code and strings), never
a hole; it is named, refused, and makes the run exit non-zero so it cannot pass unnoticed. The
authentic dump wins wherever it actually read something.

The bytes are written at the `.ST` sector offsets the files map to, so the result is one
complete disk that `st_extract.py`, Hatari and the game's own loader all see the same way. Only
data-cluster bytes move: the boot sector, the FATs and the directory entries are never touched
and no file changes length. **The result is a REPAIRED HYBRID** — the authentic dump plus
crack-sourced bytes — and is not a faithful image of the physical disk; do not archive it as
one. Without `--patch` nothing is written and the run is pure measurement.

What the comparison *found* is not the same as what the patch *covered*, so the run ends with a
ledger checked against the hole map itself rather than against the loop. Every hole sector
inside the volume is accounted for: filled from the crack, or already equal to it, or holding
bytes nothing reads (cluster slack, an unallocated cluster), or UNVERIFIED and cross-checked by
nothing — the dump's own bytes, still there, simply unproven — or lost. Only the last exits
non-zero, because a "PATCHED" banner over an image with a hole still in it is the one result
worth refusing.

Usage:
  crack_differential.py CONVERTED_DISK2.ST --crack PATH_TO_CRACK.ST [--patch OUT.ST]
                        [--stx DISK2.STX] [--strict]

Exit status:
  0  the differential ran clean (and the patch, if asked for, answered for every hole)
  1  it could not run — a missing or unreadable input, an input it refuses to trust (the wrong
     `.stx`, an ambiguous 8.3 name) — or it ran but an image raised a warning
  2  OUT.ST would have overwritten one of the inputs — nothing was written
  3  the patch ran but bytes differing inside cleanly-read sectors were refused
  4  the patch ran but a hole is still lost — the written image is incomplete. 4 outranks 3 when
     both apply: refusing a byte is a correct decision, an incomplete image is not a result.
"""
import os
import pathlib
import sys

REVERSE = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REVERSE / "tools"))
import depack_lsd                                                   # noqa: E402
import st_extract                                                   # noqa: E402
import stx_extract                                                  # noqa: E402

COMPARED_SUFFIX = ".RAD"          # the overlays; the loader and data files differ between releases
CRACK_FLAG = "--crack"
PATCH_FLAG = "--patch"
STX_FLAG = "--stx"
STRICT_FLAG = "--strict"
USAGE = ("usage: crack_differential.py CONVERTED_DISK2.ST %s PATH_TO_CRACK.ST [%s OUT.ST]"
         " [%s DISK2.STX] [%s]" % (CRACK_FLAG, PATCH_FLAG, STX_FLAG, STRICT_FLAG))
PASTI_SUFFIX = ".stx"             # extension of the sibling tried when --stx is not given
NAME_COLUMN = 13
CAUSE_COLUMN = 11
# What a hole sector in the boot/FAT/root region costs; that region has no cluster chain, so it
# is named by region rather than by owner.
VOLUME_METADATA = "the boot sector / FAT / root directory"

# Why one `.ST` sector's bytes are not what the disk held. The first two are holes in the dump
# and may be filled from the crack; the third means the dump read the sector and the crack is
# the one that differs, so it is refused. Reported in this order, worst hole first.
CAUSE_ZERO_FILLED = "ZERO-FILLED"
CAUSE_UNVERIFIED = "UNVERIFIED"
CAUSE_CLEAN_READ = "CLEAN-READ"
REPORTED_CAUSES = (CAUSE_ZERO_FILLED, CAUSE_UNVERIFIED, CAUSE_CLEAN_READ)
RECOVERABLE_CAUSES = frozenset((CAUSE_ZERO_FILLED, CAUSE_UNVERIFIED))

HYBRID_NOTICE = (
    "        REPAIRED HYBRID — the authentic dump wherever it read anything, plus crack-sourced\n"
    "        bytes in its holes. This is not a faithful image of the physical disk: it is a\n"
    "        playable reconstruction, and must never be archived or compared as the original.")

EXIT_OK = 0
EXIT_WARNED = 1                    # also what `sys.exit(<reason>)` gives, as in st_extract.py
EXIT_REFUSED_OVERWRITE = 2
EXIT_UNSAFE_DIFFERENCE = 3
EXIT_UNFILLED_HOLE = 4


def _load(path):
    """A FAT12 image and every entry in it, or exit with the reason."""
    try:
        image = st_extract.Fat12Image(pathlib.Path(path).read_bytes())
    except (OSError, ValueError) as err:
        sys.exit("cannot read %s as a FAT12 image: %s" % (path, err))
    return image, st_extract.walk(image)


def _files_by_path(entries):
    """The regular files of a walk, keyed by full path.

    Keyed by path, not by base name: two directories may hold the same 8.3 name, and a
    base-name key would silently compare one file's bytes against another's.
    """
    return {entry["path"]: entry for entry in entries if not entry["is_dir"]}


def _load_pasti(stx_path, strict):
    """The Pasti image the `.ST` was converted from, or exit with the reason."""
    try:
        return stx_extract.StxImage(pathlib.Path(stx_path).read_bytes(), strict=strict)
    except (OSError, ValueError) as err:
        sys.exit("cannot read %s as a Pasti image: %s" % (stx_path, err))


def _report_new_warnings(images, printed):
    """Print the warnings these images have raised since the last call; True if any were new.

    Re-read rather than drained once, because `Fat12Image` warns *lazily*: "chain holds N bytes
    but the entry says M", "cluster chain loops at N" and "chain runs into a bad cluster marker"
    are appended while a file's chain is walked, which happens in the compare loop and again in
    the hole ledger — long after the images were opened. `printed` (updated in place) is what
    keeps a finding to one line: the same chain is walked more than once, and each walk repeats
    its warning verbatim.

    The Pasti image is deliberately not in this list. Its warnings are this tool's *input* — the
    unreadable and unformatted sectors it names are exactly what becomes ZERO-FILLED/UNVERIFIED
    — so treating them as a failure would make a clean exit unreachable for every protected
    disk. The subset that would really invalidate the run is a wrong LBA stride, and
    `_check_pasti_source` pins that far harder than a warning could.
    """
    new = False
    for path, image in images:
        for warning in image.warnings:
            line = "WARNING %s: %s" % (path, warning)
            if line not in printed:
                printed.add(line)
                print(line)
                new = True
    return new


def _container_form(blob):
    """The crack's copy in the same form as the original's: depacked when `LSD!`-stamped."""
    if blob[:len(depack_lsd.MAGIC)] != depack_lsd.MAGIC:
        return blob
    return bytes(depack_lsd.depack(blob, depack_lsd.parse_header(blob)))


def _file_sectors(image, entry):
    """`.ST` sector number for each 512-byte slice of a file or directory, in order.

    `empty_ok` mirrors `Fat12Image.file_clusters`: a zero-length file stores no start cluster at
    all, which is the one empty chain that is not a defect and must not be warned about.
    """
    lbas = []
    for cluster in image.chain(entry["cluster"], entry["path"],
                               empty_ok=not entry["is_dir"] and not entry["size"]):
        start = image.cluster_start_sector(cluster)
        lbas += range(start, start + image.bpb["sectors_per_cluster"])
    return lbas


def _sector_verdicts(image):
    """`.ST` sector -> "ZERO-FILLED" / "UNVERIFIED" for every sector that is not a clean read.

    Read from the Pasti image itself rather than guessed from the `.ST`, because a plain
    sector dump carries no record of which of its sectors were ever readable. The rule must
    match `StxImage._choose_copy`'s — a slot with both a flagged and a clean copy is placed
    from the clean one and is not unverified — so it is derived from the same candidate map.
    """
    verdicts = {lba: CAUSE_ZERO_FILLED
                for lba, block in enumerate(image.sector_map) if block is None}
    for lba, copies in image.placement_candidates().items():
        if not any(image.is_trusted(sector) for _, sector in copies):
            verdicts[lba] = CAUSE_UNVERIFIED
    return verdicts


def _check_pasti_source(stx_image, verdicts, st_data, st_path, stx_path):
    """Refuse unless this Pasti image really is where this `.ST` came from.

    The `.stx` is the only thing that says which sectors a patch may overwrite, so aiming it at
    another disk's dump — a mistyped `--stx`, a stale sibling symlink — would apply the wrong
    hole map without a word. Every sector the dump read *cleanly* is therefore required to be
    byte-identical in the `.ST`. The holes themselves are skipped: they are precisely where a
    `.ST` that has already been patched is meant to differ, and where `--strict` legitimately
    zero-fills what the default mode places.
    """
    size = stx_extract.STANDARD_SECTOR_SIZE
    checked = 0
    differing = []
    for lba, block in enumerate(stx_image.sector_map):
        if block is None or lba in verdicts:
            continue
        checked += 1
        if st_data[lba * size:(lba + 1) * size] != block:
            differing.append(lba)
    if not differing:
        return
    sys.exit("%s is not the Pasti image %s was converted from: %d of the %d sector(s) it read"
             " cleanly differ, first at .ST sector %d — the wrong dump means the wrong hole map,"
             " so nothing may be attributed to it, let alone patched from it. (A .ST trimmed to"
             " the volume, rather than to the dump's whole geometry, lands here too.)"
             % (stx_path, st_path, len(differing), checked, differing[0]))


def _differing_slices(mine, theirs, lbas, verdicts):
    """Every `.ST`-sector-sized slice of one file whose bytes disagree with the crack.

    Empty when the two are not the same length: that is a different file, not a hole, and
    nothing about it may be attributed to a sector — let alone patched.
    """
    if len(mine) != len(theirs):
        return []
    size = stx_extract.STANDARD_SECTOR_SIZE
    slices = []
    for slice_index, lba in enumerate(lbas):
        start = slice_index * size
        end = min(len(mine), start + size)
        if start >= end or mine[start:end] == theirs[start:end]:
            continue
        slices.append(dict(lba=lba, start=start, end=end,
                           wrong=sum(mine[i] != theirs[i] for i in range(start, end)),
                           cause=verdicts.get(lba, CAUSE_CLEAN_READ)))
    return slices


def _slice_line(differing):
    return "    .ST sector %-4d [%#06x..%#06x] %-*s %d of %d bytes wrong" % (
        differing["lba"], differing["start"], differing["end"] - 1, CAUSE_COLUMN,
        differing["cause"], differing["wrong"], differing["end"] - differing["start"])


def _compare(name, mine, theirs, slices):
    """One file's report line, plus a line per `.ST` sector of it that does not match."""
    if len(mine) != len(theirs):
        return ["%-*s LENGTH %d vs %d in the crack — not the same file"
                % (NAME_COLUMN, name, len(mine), len(theirs))]
    if mine == theirs:
        return ["%-*s ok  %d bytes identical to the crack" % (NAME_COLUMN, name, len(mine))]
    total_wrong = sum(differing["wrong"] for differing in slices)
    return ["%-*s %d of %d bytes differ from the crack"
            % (NAME_COLUMN, name, total_wrong, len(mine))] + [_slice_line(s) for s in slices]


def _split_by_cause(slices):
    """(may be taken from the crack, must not be) — the safety rule, in one place.

    Only a hole may be filled: ZERO-FILLED means the dump had nothing there, UNVERIFIED that
    it read the sector through an FDC error. A byte that differs inside a cleanly-read sector
    is the crack editing the game — those releases patch code and strings — and the dump, which
    read those bytes off the physical disk, is the authority on them.
    """
    return ([s for s in slices if s["cause"] in RECOVERABLE_CAUSES],
            [s for s in slices if s["cause"] not in RECOVERABLE_CAUSES])


def _take_from_crack(image, theirs, slices):
    """Copy the crack's bytes for each recoverable slice into `image`, in place.

    A file's slices are cut in whole sectors from its start, so a slice always maps to the head
    of its own `.ST` sector — and stops at the file's last byte, which leaves the cluster slack,
    the FATs and the directory exactly as the dump had them. `_patchable_copy` is what
    guarantees the volume's sectors really are that size.
    """
    for differing in slices:
        offset = differing["lba"] * stx_extract.STANDARD_SECTOR_SIZE
        image[offset:offset + differing["end"] - differing["start"]] = \
            theirs[differing["start"]:differing["end"]]


def _patchable_copy(image, st_path):
    """A writable copy of the `.ST` — refused unless its sectors are the size the mapping assumes.

    A file is attributed to sectors in `STANDARD_SECTOR_SIZE` steps; were the volume's own
    sectors any other size, every patch offset would land somewhere else and the "repair" would
    corrupt the image instead.
    """
    if image.bpb["bytes_per_sector"] != stx_extract.STANDARD_SECTOR_SIZE:
        sys.exit("%s has %d-byte sectors — the .ST sector attribution only holds for %d, so"
                 " nothing may be patched into it"
                 % (st_path, image.bpb["bytes_per_sector"], stx_extract.STANDARD_SECTOR_SIZE))
    return bytearray(image.data)


def _cause_breakdown(slices):
    """Bytes per cause, as in "ZERO-FILLED 483, UNVERIFIED 31"; causes with none are left out."""
    per_cause = {cause: sum(s["wrong"] for s in slices if s["cause"] == cause)
                 for cause in REPORTED_CAUSES}
    return ", ".join("%s %d" % (cause, per_cause[cause])
                     for cause in REPORTED_CAUSES if per_cause[cause]) or "nothing"


def _refused_line(differing):
    return ("    REFUSED %s — the dump read this sector cleanly, so the crack is what changed"
            " here" % _slice_line(differing).strip())


def _patch_lines(repaired, refused):
    """One file's patch verdict: what was taken from the crack and what was left alone."""
    verdict = ("    patched %d byte(s) from the crack [%s], left %d alone [%s]"
               % (sum(s["wrong"] for s in repaired), _cause_breakdown(repaired),
                  sum(s["wrong"] for s in refused), _cause_breakdown(refused)))
    return [verdict] + [_refused_line(differing) for differing in refused]


def _reached_sectors(lbas, size):
    """The leading sectors of a chain a file's own length reaches; the rest is cluster slack."""
    step = stx_extract.STANDARD_SECTOR_SIZE
    return [lba for index, lba in enumerate(lbas) if index * step < size]


def _live_sectors(image, entries):
    """`.ST` sector -> the file or directory whose content is read out of it.

    A file's own length bounds it: the tail of its last cluster is slack nothing reads, and the
    patch deliberately leaves that as the dump had it. A directory carries no length field, so
    every sector of its chain counts.
    """
    live = {}
    for entry in entries:
        lbas = _file_sectors(image, entry)
        for lba in lbas if entry["is_dir"] else _reached_sectors(lbas, entry["size"]):
            live.setdefault(lba, entry["path"])
    return live


def _hole_coverage(image, entries, verdicts, patched_lbas, examined_lbas):
    """How every hole inside the volume ended up: (filled, matched, unclaimed, unchecked, lost).

    `verdicts` is the complete hole map, so it — not the compare loop — is what says whether the
    patch is finished. A hole the comparison *examined* and found already equal to the crack is
    answered for exactly as much as one it overwrote: the crack is the only reference either
    way, and an FDC-flagged sector often reads back perfectly. Counting only what was written
    would fail the run for an image that is complete.

    The rest are split by what was actually lost, because the two hole causes are not the same
    fact. A ZERO-FILLED sector nothing cross-checked is `lost` — its bytes are gone and no file
    can supply them, which is the only case that breaks the exit-0 promise. An UNVERIFIED one is
    merely `unchecked`: the dump's own 512 bytes are in the image, they simply went unread by
    any comparison, and calling that "missing" would make a clean exit unreachable on any disk
    with a flagged sector outside the overlays.

    Two kinds of hole are not the patch's to answer for at all: sectors past the volume's
    declared size hold no filesystem (a dump routinely carries spare cylinders), and a hole in
    cluster slack or an unallocated cluster is real but inert — nothing reads those bytes.
    Ownership comes from the chains, so a sector orphaned by a chain the dump lost also counts
    as `unclaimed`; the chain warning that `_report_new_warnings` prints is what names that.
    """
    live = _live_sectors(image, entries)
    filled = 0
    matched = 0
    unclaimed = 0
    unchecked = []
    lost = []
    for lba in sorted(lba for lba in verdicts if lba < image.bpb["total_sectors"]):
        if lba in patched_lbas:
            filled += 1
        elif lba in examined_lbas:
            matched += 1
        else:
            what = VOLUME_METADATA if lba < image.bpb["data_start"] else live.get(lba)
            if what is None:
                unclaimed += 1
            else:
                (unchecked if verdicts[lba] == CAUSE_UNVERIFIED else lost).append((lba, what))
    return filled, matched, unclaimed, unchecked, lost


def _coverage_report(coverage):
    """The hole ledger: every in-volume hole, and whether the patch answered for it."""
    filled, matched, unclaimed, unchecked, lost = coverage
    print("HOLES   %d hole sector(s) inside the volume — %d filled from the crack, %d already"
          " matched it, %d hold nothing any file reads, %d unverified and never cross-checked,"
          " %d lost"
          % (filled + matched + unclaimed + len(unchecked) + len(lost), filled, matched,
             unclaimed, len(unchecked), len(lost)))
    for lba, what in unchecked:
        print("        .ST sector %-4d %s — the dump's own bytes, read through an FDC error and"
              " compared against nothing" % (lba, what))
    if not lost:
        return EXIT_OK
    print("\n!!! the patched image is INCOMPLETE: %d hole sector(s) hold bytes something reads,"
          " and nothing filled them:" % len(lost))
    for lba, what in lost:
        print("!!!   .ST sector %-4d %s" % (lba, what))
    print("!!! only a paired %s file of equal length can fill a hole — a file the crack does not"
          " carry, a file this tool never compares, a chain the dump lost, or the boot/FAT/root"
          " region (which the patch may never touch) all leave it as it was" % COMPARED_SUFFIX)
    return EXIT_UNFILLED_HOLE


def _refusal_report(refusals):
    """The final word on refused bytes: loud, per file, and never zero-exit."""
    if not refusals:
        return EXIT_OK
    bytes_refused = sum(differing["wrong"] for _, differing in refusals)
    print("\n!!! %d byte(s) in %d file(s) differ inside cleanly-read sectors and were NOT taken"
          " from the crack:" % (bytes_refused, len({name for name, _ in refusals})))
    for name, differing in refusals:
        print("!!!   %-*s .ST sector %d [%#06x..%#06x] %d byte(s)"
              % (NAME_COLUMN, name, differing["lba"], differing["start"],
                 differing["end"] - 1, differing["wrong"]))
    print("!!! the dump read those sectors off the disk, so the crack altered the file there —"
          " the patched image keeps the dump's bytes")
    return EXIT_UNSAFE_DIFFERENCE


def _write_repaired(out_path, image, repaired_bytes, repaired_files):
    """Write the patched image and say plainly what it is."""
    try:
        pathlib.Path(out_path).write_bytes(bytes(image))
    except OSError as err:
        sys.exit("cannot write %s: %s" % (out_path, err))
    print("\nPATCHED %s — %d byte(s) taken from the crack across %d file(s), %d bytes total"
          % (out_path, repaired_bytes, repaired_files, len(image)))
    print(HYBRID_NOTICE)


def _is_same_file(out_path, source):
    """True when writing `out_path` would land on `source`.

    Compared by file *identity*, not by path text: a case-insensitive volume (`DIR/x.ST` vs
    `dir/x.st`) and a hard link both give one inode two spellings that no amount of resolving
    makes equal, and only a symlink survives a resolved-path comparison. `samefile` needs both
    ends to exist, so a target that is not there yet falls back to the path test — which is
    still what catches a dangling symlink aimed at an input.
    """
    try:
        return os.path.samefile(out_path, source)
    except OSError:
        return pathlib.Path(out_path).resolve() == pathlib.Path(source).resolve()


def _refuse_overwrite(out_path, inputs):
    """Never write the patched image over a file it was made from; the inputs are irreplaceable."""
    for source in inputs:
        if _is_same_file(out_path, source):
            sys.stderr.write("refusing to write the patched image over its own input %s\n"
                             % source)
            sys.exit(EXIT_REFUSED_OVERWRITE)


def _parse_args(args):
    """(converted .ST, crack .ST, patch output or None, Pasti image, strict) — or exit 1 + usage.

    The Pasti image defaults to the `.ST`'s sibling, which is a convenience only: it is the sole
    authority on which sectors may be overwritten, so `_check_pasti_source` still has to prove
    that whichever file was chosen really is this `.ST`'s source.
    """
    if not args or not args[0] or args[0].startswith("-"):
        sys.exit(USAGE)
    crack = None
    patch = None
    stx = None
    strict = False
    rest = args[1:]
    while rest:
        flag, rest = rest[0], rest[1:]
        if flag == STRICT_FLAG:
            strict = True
        elif flag == CRACK_FLAG and rest and not crack:
            crack, rest = rest[0], rest[1:]
        elif flag == STX_FLAG and stx is None and rest and rest[0] and not rest[0].startswith("-"):
            stx, rest = rest[0], rest[1:]
        # A flag that *writes* must not swallow the next option as its filename, nor an empty
        # one: either would create a file nobody asked for, named after an option.
        elif flag == PATCH_FLAG and not patch and rest and rest[0] and not rest[0].startswith("-"):
            patch, rest = rest[0], rest[1:]
        else:
            sys.exit(USAGE)
    if not crack:
        sys.exit(USAGE)
    # `splitext`, not `Path.with_suffix`, which raises on a path with no name of its own (".",
    # "..", "/") — an argument that deserves the tool's own error, not a traceback.
    return args[0], crack, patch, stx or os.path.splitext(args[0])[0] + PASTI_SUFFIX, strict


def _compare_one(name, mine, theirs, slices, patched):
    """Report one paired file, patch it when asked, and return (slices taken, refused slices)."""
    for line in _compare(name, mine, theirs, slices):
        print(line)
    if patched is None or not slices:
        return [], []
    repaired, refused = _split_by_cause(slices)
    _take_from_crack(patched, theirs, repaired)
    for line in _patch_lines(repaired, refused):
        print(line)
    return repaired, [(name, differing) for differing in refused]


def _one_path_per_name(paths, whose):
    """{8.3 base name: path} for these files, refusing any name that resolves to more than one.

    The two releases lay the same overlays out in different directories, so both sides of the
    comparison are paired by base name — which makes a name held under two paths, in *either*
    image, equally fatal. Taking the one `walk()` happened to visit last would compare, and in
    patch mode write in, an arbitrary namesake's bytes: directory-order-dependent, invisible in
    the output, and inside a hole sector where the safety rule cannot see it.
    """
    by_name = {}
    for path in paths:
        by_name.setdefault(pathlib.PurePath(path).name, []).append(path)
    ambiguous = sorted(name for name, found in by_name.items() if len(found) > 1)
    if ambiguous:
        sys.exit("%s holds %d name(s) under more than one path (%s) — the pairing is by 8.3 base"
                 " name, so there is no one file to compare; nothing was verified"
                 % (whose, len(ambiguous), "; ".join("%s: %s" % (name, ", ".join(by_name[name]))
                                                     for name in ambiguous)))
    return {name: found[0] for name, found in by_name.items()}


def _pair_overlays(mine, theirs):
    """({base name: dump path}, {base name: crack entry}) — the comparison's two sides.

    The dump's overlays *are* this comparison's key space, so every one of them is judged. The
    crack is a whole unrelated release that happens to carry them: only the names the dump asks
    for are judged there, since a duplicate among the other hundred files is none of this
    comparison's business.
    """
    overlays = _one_path_per_name([path for path in mine if path.endswith(COMPARED_SUFFIX)],
                                  "the dump")
    matches = _one_path_per_name([path for path in theirs
                                  if pathlib.PurePath(path).name in overlays], "the crack")
    return overlays, {name: theirs[path] for name, path in matches.items()}


def _report_unpaired(overlays, crack_by_name):
    """Name the dump's overlays the crack does not carry — they are compared by nothing."""
    unpaired = sorted(name for name in overlays if name not in crack_by_name)
    if unpaired:
        print("%d %s file(s) have no namesake in the crack and were not compared: %s"
              % (len(unpaired), COMPARED_SUFFIX, ", ".join(unpaired)))


def main():
    st_path, crack_path, out_path, stx_path, strict = _parse_args(sys.argv[1:])
    if out_path:
        _refuse_overwrite(out_path, (st_path, crack_path, stx_path))
    if not pathlib.Path(crack_path).exists():
        sys.exit("the crack image %s is not here — nothing was verified (see this file's "
                 "docstring: it is a deliberate external dependency)" % crack_path)
    if not pathlib.Path(stx_path).exists():
        sys.exit("the Pasti image %s is not here — without it no sector can be attributed to a"
                 " cause, which is the whole product; pass %s PATH if it lives elsewhere"
                 % (stx_path, STX_FLAG))
    mine_image, mine_entries = _load(st_path)
    crack_image, crack_entries = _load(crack_path)
    images = ((st_path, mine_image), (crack_path, crack_image))
    printed_warnings = set()
    # What `walk()` found, said now: several refusals below exit before the compare loop, and a
    # broken directory chain is usually the reason for them.
    warned = _report_new_warnings(images, printed_warnings)
    mine = _files_by_path(mine_entries)
    theirs = _files_by_path(crack_entries)
    pasti = _load_pasti(stx_path, strict)
    verdicts = _sector_verdicts(pasti)
    _check_pasti_source(pasti, verdicts, mine_image.data, st_path, stx_path)

    overlays, crack_by_name = _pair_overlays(mine, theirs)
    _report_unpaired(overlays, crack_by_name)
    compared = sorted(name for name in overlays if name in crack_by_name)
    if not compared:
        sys.exit("no %s file is present in both images — nothing was verified" % COMPARED_SUFFIX)
    patched = _patchable_copy(mine_image, st_path) if out_path else None
    refusals = []
    patched_lbas = set()
    examined_lbas = set()
    repaired_bytes = 0
    repaired_files = 0
    for name in compared:
        entry = mine[overlays[name]]
        crack_entry = crack_by_name[name]
        original = mine_image.file_bytes(entry)
        replacement = _container_form(crack_image.file_bytes(crack_entry))
        lbas = _file_sectors(mine_image, entry)
        slices = _differing_slices(original, replacement, lbas, verdicts)
        repaired, refused = _compare_one(entry["name"], original, replacement, slices, patched)
        taken = sum(differing["wrong"] for differing in repaired)
        repaired_bytes += taken
        repaired_files += 1 if taken else 0
        patched_lbas.update(differing["lba"] for differing in repaired)
        # Only an equal-length pair speaks for a sector — the same rule `_differing_slices` uses.
        if len(original) == len(replacement):
            examined_lbas.update(_reached_sectors(lbas, len(original)))
        refusals += refused
    print("\n%d file(s) compared" % len(compared))
    # The ledger walks every remaining cluster chain, which is where the rest of the lazy
    # warnings appear — so it is computed before they are reported, never after.
    coverage = None if patched is None else _hole_coverage(mine_image, mine_entries, verdicts,
                                                           patched_lbas, examined_lbas)
    warned = _report_new_warnings(images, printed_warnings) or warned
    if coverage is None:
        return EXIT_WARNED if warned else EXIT_OK
    _write_repaired(out_path, patched, repaired_bytes, repaired_files)
    # Both reports always run — one must not silence the other — but an unfilled hole outranks a
    # refusal: refusing is the correct decision, an unfilled hole means the image is incomplete.
    hole_status = _coverage_report(coverage)
    refusal_status = _refusal_report(refusals)
    return hole_status or refusal_status or (EXIT_WARNED if warned else EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
