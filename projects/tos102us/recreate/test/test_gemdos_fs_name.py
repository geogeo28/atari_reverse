"""The file system's 8.3 NAME layer — `src/gemdos/fs_name.c`, four routines that touch no disk.

These are the bottom of the directory search: `Fsfirst`, `Fopen`, `Fcreate`, `Frename` and
`Fdelete` all turn the caller's text into eleven FCB bytes here, and compare them against a
directory entry here. Nothing in this file stages a medium — two buffers in the case band is the
whole machine — which is why they are the first of the group to be verified and why every arm of
each is reachable.

`gemdos_cluster_record` is here too, for the same reason: it is one `muls.w`, and it is the only
piece of the DISK layer that needs no disk.
"""
import ctypes

import pytest

from harness import _lib, addrs

import case
import gemdos
import gemdos_fs as fs

for _name in ("gemdos_fs_log2", "gemdos_fs_toupper", "gemdos_name_match",
              "gemdos_cluster_record"):
    getattr(_lib, _name).restype = ctypes.c_uint32
# ...and the one that returns nothing, which ctypes would otherwise report as a C `int` — the shape
# `case.NO_RESULT` refuses.
_lib.gemdos_build_fcb_name.restype = None

# The two buffers a name case works over. These routines read and write a few dozen bytes and need
# no sector at all — but `staging.SCRATCH`'s 4 KB is claimed to its last byte by the six bands
# `test/staging.py`'s registry holds, so the span they take is `gemdos_fs.NAMES_AT`, inside the RAM
# disk's own (which `test_gemdos_fs_disk.py` proves clear of every declared tenant and zero in the
# capture). The first spelling of this band was `staging.SCRATCH + 0x600` — exactly on top of
# `test/gemdos_console.py`'s, with both of its hand-written neighbour assertions still passing.
NAME_BAND = fs.NAMES_AT
PATTERN_AT = NAME_BAND
ENTRY_AT = NAME_BAND + 0x20
TEXT_AT = NAME_BAND + 0x40
FCB_AT = NAME_BAND + 0x80
NAME_BAND_BYTES = 0xA0
assert NAME_BAND_BYTES <= fs.NAMES_BYTES, "the name buffers outgrew the span reserved for them"

# A D0 nothing in these routines writes the whole of, so that a reconstruction clearing the high
# half has something to fail against.
ENTRY_D0 = 0xDEC0_DE00
# ...and what an FCB buffer is filled with before a case writes into it: every one of the eleven
# bytes must be stored, and a byte left holding this says which was not.
FCB_FILL = 0xA5
FCB_NAME_BYTES = 11
FCB_BUFFER_BYTES = 16       # the eleven, plus slack a run must not reach


def _staged(pattern=None, entry=None, text=None):
    """The buffers a case hands the routines, each padded so an overrun is visible."""
    pokes = {FCB_AT: bytes([FCB_FILL]) * FCB_BUFFER_BYTES}
    if pattern is not None:
        pokes[PATTERN_AT] = pattern + bytes([FCB_FILL]) * (FCB_BUFFER_BYTES - len(pattern))
    if entry is not None:
        pokes[ENTRY_AT] = entry + bytes([FCB_FILL]) * (FCB_BUFFER_BYTES - len(entry))
    if text is not None:
        pokes[TEXT_AT] = text.encode("latin-1") + b"\0"
    return pokes


def _fcb(name, extension="", attr=0):
    """An eleven-byte FCB name with an attribute byte after it — the twelve `$fc5c9a` compares."""
    return (name.ljust(8)[:8] + extension.ljust(3)[:3]).encode("latin-1") + bytes([attr])


# ---- toupper, $fc50ca ----------------------------------------------------------------------------

@pytest.mark.parametrize("character", (
    ord("a"), ord("z"), ord("A"), ord("Z"),     # both ends of the range, and past both
    ord("a") - 1, ord("z") + 1,                 # '`' and '{', the two the SIGNED compares exclude
    ord("0"), ord("."), ord("?"), ord("*"), 0,
    0x80, 0xE1, 0xFF,                           # bit 7 set: NEGATIVE to a `cmp.b`, so untouched
))
def test_toupper_folds_only_the_lower_case_range(character):
    """`and.w #$5f` between 'a' and 'z', and the argument through unchanged otherwise. The compares
    are SIGNED byte compares, which is why the ST's accented characters — every one of them above
    $7f — come back as they went in rather than being folded by a range test on an unsigned byte."""
    info = case.run(addrs.GEMDOS_FS_TOUPPER, {"d0": ENTRY_D0, "a5": 0, "_pokes": case.word_arg(character)},
                    lambda lib, buf: lib.gemdos_fs_toupper(ENTRY_D0, character))
    # The result is SIGN-EXTENDED from the byte, both ways round: the fold is `move.b`/`ext.w`/
    # `and.w #$5f` and the pass-through is `move.b`/`ext.w` with nothing after it, so a character
    # with bit 7 set comes back as `$ffXX` rather than as itself.
    expected = (character & 0x5F if ord("a") <= character <= ord("z")
                else (character | 0xFF00 if character & 0x80 else character))
    assert info["regs"]["d0"] & 0xFFFF == expected
    assert info["regs"]["d0"] >> 16 == ENTRY_D0 >> 16, "the caller's high half must stand"


def test_toupper_reads_only_the_low_byte_of_its_argument_word():
    """The routine's `move.b 9(a6),d7` takes the low byte of the argument word, and the result is
    sign-extended from THAT byte — so a wide value is folded by its bottom eight bits alone."""
    wide = 0xFF00 | ord("q")
    info = case.run(addrs.GEMDOS_FS_TOUPPER, {"d0": ENTRY_D0, "a5": 0,
                                              "_pokes": case.word_arg(wide)},
                    lambda lib, buf: lib.gemdos_fs_toupper(ENTRY_D0, wide))
    assert info["regs"]["d0"] & 0xFFFF == ord("Q")


# ---- log2, $fc539a -------------------------------------------------------------------------------

@pytest.mark.parametrize("value", (1, 2, 4, 8, 512, 1024, 0x4000, 3, 5, 1000, 0))
def test_log2_counts_arithmetic_shifts_and_subtracts_one(value):
    """The three call sites pass `m_clsiz`, `m_recsiz` and `m_clsizb`, all powers of two, and for
    those it is log2. For anything else it is the position of the TOP SET BIT — 1000 answers 9 —
    and for 0 it is -1, because the loop makes no pass and the `subq.w #1` runs anyway."""
    info = case.run(addrs.GEMDOS_FS_LOG2, {"d0": ENTRY_D0, "a5": 0, "_pokes": case.word_arg(value)},
                    lambda lib, buf: lib.gemdos_fs_log2(ENTRY_D0, value))
    assert info["regs"]["d0"] & 0xFFFF == (value.bit_length() - 1) & 0xFFFF
    assert info["regs"]["d0"] >> 16 == ENTRY_D0 >> 16


# ---- cluster -> record, $fc55e6 ------------------------------------------------------------------

@pytest.mark.parametrize("cluster", (0, 1, 2, 33, fs.ROOT_START_CLUSTER, fs.FAT_START_CLUSTER,
                                     -1, 0x7FFF, 0x8000))
def test_a_cluster_becomes_a_record_by_a_signed_multiply(cluster):
    """`muls.w m_clsiz,d0` — the whole 32-bit product, so a NEGATIVE cluster (the FAT's and the root
    directory's, which live below 0 in the DMD's pseudo-cluster space) comes back negative and a
    cluster of $8000 does not wrap to a positive record."""
    pokes = {**fs.drive(), **case.args(">HI", cluster & 0xFFFF, fs.DMD_AT)}
    info = case.run(addrs.GEMDOS_CLUSTER_RECORD, {"a5": 0, "_pokes": pokes},
                    lambda lib, buf: lib.gemdos_cluster_record(buf, cluster & 0xFFFF, fs.DMD_AT))
    expected = ctypes.c_int16(cluster).value * fs.SECTORS_PER_CLUSTER
    assert ctypes.c_int32(info["regs"]["d0"]).value == expected


# ---- name_match, $fc5c9a -------------------------------------------------------------------------

MATCH_CASES = (
    # (pattern name, pattern ext, pattern attr, entry name, entry ext, entry attr, matches, why)
    ("SHORT", "TXT", 0, "SHORT", "TXT", 0, True, "the plain hit"),
    ("SHORT", "TXT", 0, "SHORTX", "TXT", 0, False, "one byte of stem apart"),
    ("SHORT", "TXT", 0, "SHORT", "TXA", 0, False, "...and one of extension"),
    ("????????", "???", 0, "ANY", "ONE", 0, True, "`?` in every position"),
    ("SHORT", "???", 0, "SHORT", "TXT", 0, True, "a wildcard extension"),
    ("short", "txt", 0, "SHORT", "TXT", 0, True, "BOTH sides are folded, so a lower-case pattern hits"),
    ("SHORT", "TXT", 0, "short", "txt", 0, True, "...and so does a lower-case ENTRY"),
    ("SUBDIR", "", 0x10, "SUBDIR", "", 0x10, True, "attributes sharing a bit"),
    ("SUBDIR", "", 0x10, "SUBDIR", "", 0x01, False, "...and sharing none"),
    ("SUBDIR", "", 0x10, "SUBDIR", "", 0x00, True, "an entry attribute of 0 matches anything but 8"),
    ("STAGEDDSK", "", 8, "STAGEDDSK", "", 8, True, "the volume label against a volume label"),
    ("STAGEDDSK", "", 8, "STAGEDDSK", "", 0, False, "...and not a plain file, which a 0 attribute "
                                                    "would otherwise have let through"),
    ("STAGEDDSK", "", 8, "STAGEDDSK", "", 0x18, True, "...but a volume-label pattern is NOT an "
                                                      "equality test: $18 shares bit 3 and matches"),
    ("GONE", "OLD", 0, "\xe5ONE", "OLD", 0, False, "an `$e5` pattern byte against a LIVE entry is "
                                                   "just a byte, and this one does not match 'G'"),
    ("ANY", "ONE", 0x80, "ANY", "ONE", 0x80, True, "a bit-7 attribute on both sides, where the "
                                                   "ROM's `ext.w` pair could have differed from a "
                                                   "byte `and`"),
)


@pytest.mark.parametrize("pattern_name,pattern_ext,pattern_attr,entry_name,entry_ext,entry_attr,"
                         "matches,why", MATCH_CASES,
                         ids=[row[-1] for row in MATCH_CASES])
def test_name_match_compares_eleven_folded_bytes_and_then_the_attribute(
        pattern_name, pattern_ext, pattern_attr, entry_name, entry_ext, entry_attr, matches, why):
    pokes = _staged(pattern=_fcb(pattern_name, pattern_ext, pattern_attr),
                    entry=_fcb(entry_name, entry_ext, entry_attr))
    info = case.run(addrs.GEMDOS_NAME_MATCH, {"d0": ENTRY_D0, "a5": 0,
                                              "_pokes": {**pokes,
                                                         **case.long_args(PATTERN_AT, ENTRY_AT)}},
                    lambda lib, buf: lib.gemdos_name_match(ENTRY_D0, buf, PATTERN_AT, ENTRY_AT))
    assert (info["regs"]["d0"] == 1) is matches, why


@pytest.mark.parametrize("first,matches,why", (
    (ord("?"), False, "a `?` is REFUSED against a deleted entry — the one place it does not match"),
    (fs.DIRENT_DELETED, True, "...and an `$e5` pattern matches one, which is how a free slot is found"),
    (ord("G"), False, "anything else falls into the general comparison, where `$e5` is just a byte"),
))
def test_a_deleted_entry_has_three_arms_of_its_own(first, matches, why):
    """THE DELETED TEST COMES FIRST, before any name comparison, and its two special answers are
    about the pattern's FIRST byte alone."""
    pattern = bytes([first]) + _fcb("ONE", "OLD")[1:]
    entry = bytes([fs.DIRENT_DELETED]) + _fcb("GONE", "OLD")[1:]
    pokes = _staged(pattern=pattern, entry=entry)
    info = case.run(addrs.GEMDOS_NAME_MATCH,
                    {"d0": ENTRY_D0, "a5": 0,
                     "_pokes": {**pokes, **case.long_args(PATTERN_AT, ENTRY_AT)}},
                    lambda lib, buf: lib.gemdos_name_match(ENTRY_D0, buf, PATTERN_AT, ENTRY_AT))
    assert (info["regs"]["d0"] == 1) is matches, why


def test_a_refusal_writes_only_the_low_word_of_d0_where_a_hit_writes_all_of_it():
    """`clr.w d0` against `moveq #1,d0`, which is not symmetry: a NO clears only the LOW WORD and
    leaves the caller's high half standing, where a YES writes the whole register. The ROM's own
    callers test the result with `tst.w`, so it is moot there — and it is exactly the half a
    reconstruction returning a plain 0 would get wrong."""
    pokes = _staged(pattern=_fcb("ONE"), entry=_fcb("TWO"))
    info = case.run(addrs.GEMDOS_NAME_MATCH,
                    {"d0": ENTRY_D0, "a5": 0,
                     "_pokes": {**pokes, **case.long_args(PATTERN_AT, ENTRY_AT)}},
                    lambda lib, buf: lib.gemdos_name_match(ENTRY_D0, buf, PATTERN_AT, ENTRY_AT))
    assert info["regs"]["d0"] == ENTRY_D0 & 0xFFFF_0000


# ---- build_fcb_name, $fc5d28 ---------------------------------------------------------------------

BUILD_CASES = (
    ("SHORT.TXT", "SHORT   TXT", "the plain one"),
    ("short.txt", "SHORT   TXT", "folded on the way in"),
    ("A.B", "A       B  ", "both fields padded with space"),
    ("NOEXT", "NOEXT      ", "no dot at all: the extension is three spaces"),
    ("NOEXT.", "NOEXT      ", "...and a trailing dot is the same thing"),
    ("VERYLONGNAME.TXT", "VERYLONGTXT", "a stem past eight is TRUNCATED and the rest thrown away "
                                        "up to the dot"),
    ("VERYLONGNAME", "VERYLONG   ", "...and with no dot, the skip runs to the NUL"),
    ("FILE.LONGEXT", "FILE    LON", "an extension past three simply stops"),
    ("*.*", "???????????", "`*` fills the REST of its field with `?`, in both"),
    ("*", "????????   ", "a BARE `*` is not `*.*`: the stem's tail steps PAST the `*`, so the "
                         "extension's loop sees the NUL and pads with SPACE"),
    ("AB*.TXT", "AB??????TXT", "a `*` after two characters fills the six that are left"),
    ("SHORT.*", "SHORT   ???", "...and one in the extension alone"),
    ("A B.TXT", "A          ", "a SPACE ends a field, so the stem stops at 'A' and the text left "
                               "over is not an extension"),
    ("", "           ", "nothing at all: eleven spaces"),
    (".TXT", "        TXT", "a leading dot is an extension with an empty stem"),
    ("SUB\\FILE.TXT", "SUB        ", "a path separator ends the name as surely as a NUL"),
    ("ABCDEFGH*.TXT", "ABCDEFGHTXT", "the OVER-LONG skip swallows a `*`, so the extension is TXT "
                                     "and no `?` is written anywhere"),
    ("ABCDEFGHI*J.TXT", "ABCDEFGHTXT", "...and it keeps going PAST the `*` to the dot, which is "
                                       "what tells the skip's stop set apart from the copy loop's "
                                       "— a skip that stopped at the `*` would answer "
                                       "'ABCDEFGHJ  '"),
    ("ABCDEFGH XYZ", "ABCDEFGH   ", "...nor by a SPACE, where the copy loop above it stops — so "
                                    "the skip runs to the NUL and there is no extension"),
    ("AB*X.TXT", "AB??????X  ", "a `*` whose next character is NOT a dot: $fc5d9c does not advance, "
                                "so the extension's loop starts at 'X'"),
)


@pytest.mark.parametrize("text,expected,why", BUILD_CASES, ids=[row[-1] for row in BUILD_CASES])
def test_build_fcb_name_writes_eleven_bytes_and_no_more(text, expected, why):
    pokes = _staged(text=text)
    info = case.run(addrs.GEMDOS_BUILD_FCB_NAME,
                    {"a5": 0, "_pokes": {**pokes, **case.long_args(TEXT_AT, FCB_AT)}},
                    lambda lib, buf: lib.gemdos_build_fcb_name(buf, TEXT_AT, FCB_AT),
                    width=case.NO_RESULT)
    built = bytes(info["writes"].get(FCB_AT + at, FCB_FILL) for at in range(FCB_NAME_BYTES))
    assert built.decode("latin-1") == expected, why
    for at in range(FCB_NAME_BYTES, FCB_BUFFER_BYTES):
        assert FCB_AT + at not in info["writes"], "a twelfth byte was written"


def test_every_one_of_the_eleven_bytes_is_STORED_even_when_it_is_already_right():
    """The buffer is pre-filled with `$a5`, so a byte the routine skipped reads as `$a5` rather
    than as the space it should be — which is what makes the padding loops a compared fact and not
    something a zeroed buffer would hide."""
    pokes = _staged(text="A")
    info = case.run(addrs.GEMDOS_BUILD_FCB_NAME,
                    {"a5": 0, "_pokes": {**pokes, **case.long_args(TEXT_AT, FCB_AT)}},
                    lambda lib, buf: lib.gemdos_build_fcb_name(buf, TEXT_AT, FCB_AT),
                    width=case.NO_RESULT)
    for at in range(FCB_NAME_BYTES):
        assert FCB_AT + at in info["writes"], f"byte {at} of the FCB name was never stored"


def test_the_names_the_staged_disk_uses_round_trip_through_the_builder():
    """The one test here that ties the two halves of this wave together: every file on the staged
    RAM disk is named by a string the builder turns into exactly the eleven bytes its directory
    entry holds, so a case that searches that disk later is searching for what is on it."""
    for name, extension, _attr, _cluster, _length, deleted in fs.ROOT_FILES:
        if deleted or not name:
            continue
        text = f"{name}.{extension}" if extension else name
        pokes = _staged(text=text)
        info = case.run(addrs.GEMDOS_BUILD_FCB_NAME,
                        {"a5": 0, "_pokes": {**pokes, **case.long_args(TEXT_AT, FCB_AT)}},
                        lambda lib, buf: lib.gemdos_build_fcb_name(buf, TEXT_AT, FCB_AT),
                        width=case.NO_RESULT)
        built = bytes(info["writes"][FCB_AT + at] for at in range(FCB_NAME_BYTES))
        assert built == _fcb(name, extension)[:FCB_NAME_BYTES], f"{text} is not what {name} holds"


# ---- the registry --------------------------------------------------------------------------------
# One row per routine, in the shape `test_boot_snapshot.VERIFIED_CASES` takes. The cases above drive
# many more values; these are the ones Tier 3 prices and the snapshot mask is checked against.

gemdos.register("toupper, a lower-case letter", addrs.GEMDOS_FS_TOUPPER,
            {"d0": ENTRY_D0, "a5": 0}, {**case.word_arg(ord("q"))})
gemdos.register("log2, 512", addrs.GEMDOS_FS_LOG2, {"d0": ENTRY_D0, "a5": 0},
            {**case.word_arg(fs.SECTOR_BYTES)})
gemdos.register("cluster -> record, a data cluster", addrs.GEMDOS_CLUSTER_RECORD, {"a5": 0},
            {**fs.drive(), **case.args(">HI", fs.FIRST_DATA_CLUSTER, fs.DMD_AT)})
gemdos.register("name_match, a plain hit", addrs.GEMDOS_NAME_MATCH, {"d0": ENTRY_D0, "a5": 0},
            {**_staged(pattern=_fcb("SHORT", "TXT"), entry=_fcb("SHORT", "TXT")),
             **case.long_args(PATTERN_AT, ENTRY_AT)})
gemdos.register("build_fcb_name, a wildcard stem", addrs.GEMDOS_BUILD_FCB_NAME, {"a5": 0},
            {**_staged(text="AB*.TXT"), **case.long_args(TEXT_AT, FCB_AT)})

# The staging band these cases own, for `test_boot_snapshot.py`'s claim about which bytes a case
# rests on. The RAM disk's own span is `test_gemdos_fs_disk.py`'s.
CASE_FIELDS = (
    (NAME_BAND, NAME_BAND_BYTES, "the two FCB buffers and the caller's text"),
)
