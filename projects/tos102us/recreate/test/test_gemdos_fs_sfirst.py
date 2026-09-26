r"""The FIRST SEARCH — `$fc6d14` (`sfirst`) and the leaf over it, `Fsfirst` ($4e, `$fc6cf6`), which hands
it the running process's DTA — over `test/fs_dir.py`'s tree, then `Fsnext` continuing from exactly
the DTA it left.

`sfirst` is `$fc696c` then `$fc663c` from position 0, under the caller's attribute WIDENED by
read-only and archive unless the word is exactly VOLUME. What it leaves in the DTA is the whole search
`Fsnext` resumes: twelve bytes of the path's tail (a short name brings its NUL and the caller's bytes
after it), the widened attribute's low byte, and at ODD offsets the position after the match and the
directory's DND — then `$fc6ebc` fills the rest from the entry. Either miss, the directory's or the
name's, is EFILNF with the DTA untouched.

Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import pytest

import fs_dir as d
import fs_open as fo
import gemdos
import gemdos_fs as fs

FSFIRST, FSNEXT, SFIRST = fs.FSFIRST, fs.FSNEXT, fs.SFIRST
SUBDIR = fs.GEMDOS_ATTR_SUBDIR
VOLUME = fs.GEMDOS_ATTR_VOLUME
HIDDEN = fs.GEMDOS_ATTR_HIDDEN
# A search attribute WORD whose low byte is VOLUME's: the ROM compares the whole word ($fc6d1c
# `cmpi.w #8`), so this one is widened — and its low byte is then no longer the volume pattern.
VOLUME_UNDER_A_HIGH_BYTE = fs.ARGUMENT_HIGH_BYTE | VOLUME
NO_DTA = 0
ROOT = fs.ROOT_DND_AT


def _fsfirst(path, attr, extra=None):
    return fo.run(FSFIRST, (fo.NAME_AT, attr), path, extra)


def _fsnext(previous):
    """`Fsnext` over the machine `previous` left — its DTA, its DNDs, its cache."""
    return fo.run(FSNEXT, (), "", fs.continued(previous))


def _widened(attr):
    return attr if attr == VOLUME else (attr | fs.GEMDOS_SFIRST_ALSO_MATCHES) & fs.D0_LOW_WORD


def _assert_dta_untouched(result):
    assert result.after(fo.DTA_AT, d.DTA_BYTES) == bytes([fs.SLACK_FILL]) * d.DTA_BYTES


# ---- what it finds ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,attr,found,index,why", (
    ("A:\\*.*", 0, "SHORT.TXT", "SHORT", "the first plain file: SUBDIR's bit is not in the widened 0 ($21)"),
    ("A:\\*.*", SUBDIR, "SUBDIR", "SUBDIR", "...which a subdirectory attribute finds first"),
    ("A:\\*.*", VOLUME, "STAGEDDS", "STAGEDDSK", "VOLUME alone is not widened and loses the plain-file shortcut"),
    ("A:\\*.*", VOLUME_UNDER_A_HIGH_BYTE, "SHORT.TXT", "SHORT", "a WORD that is not exactly 8 is widened"),
    ("A:\\EMPTY.BIN", 0, "EMPTY.BIN", "EMPTY", "a READ-ONLY file answers attribute 0 only because of the widening"),
    ("A:\\SECRET.HID", HIDDEN, "SECRET.HID", "SECRET", "a hidden file its own bit"),
    ("a:\\s?an.dat", 0, "SPAN.DAT", "SPAN", "a lower-case drive and name, and a `?`"),
))
def test_fsfirst_finds_the_first_match_and_fills_the_dta(path, attr, found, index, why):
    result = _fsfirst(path, attr)
    assert result.info["ret"] == 0, why
    assert fo.dta_name(result) == found, why
    assert result.after(fo.DTA_AT + fs.DTA_ATTR, 1) == bytes([_widened(attr) & 0xFF]), why
    assert fo.dta_long(result, fs.DTA_DIRPOS) == d.position_of(d.ROOT_INDEX[index]), why
    assert fo.dta_long(result, fs.DTA_DND) == ROOT, why


# What the caller's buffer holds after the path's NUL: bytes no DTA holds, so every one of them the
# pattern copy takes is told apart from the DTA's own fill.
AFTER_THE_NUL = b"ABCDEFGHIJKL"


def test_the_dta_keeps_twelve_bytes_of_the_tail_whatever_its_length():
    """"*.*" is four bytes with its NUL; the DTA gets those and the EIGHT the caller's buffer held
    after them ($fc6d8e `move.w #12`) — and not a ninth."""
    path = "A:\\*.*"
    result = _fsfirst(path, 0, {fo.NAME_AT + len(path) + 1: AFTER_THE_NUL})
    pattern = result.after(fo.DTA_AT + fs.DTA_PATTERN, fs.DTA_PATTERN_BYTES + 1)
    kept = fs.DTA_PATTERN_BYTES - len(b"*.*\0")
    assert pattern == b"*.*\0" + AFTER_THE_NUL[:kept] + bytes([_widened(0)])


def test_fsfirst_two_levels_down_keeps_the_directory_s_dnd():
    """No drive and a leading `\\`: the current drive's root, then SUBDIR and INNER, each DND made by
    the walk's own searches. The DTA's DND is INNER's."""
    result = _fsfirst("\\SUBDIR\\INNER\\*.TXT", 0)
    subdir = d.child_named(result, ROOT, "SUBDIR")
    inner = d.child_named(result, subdir, "INNER")
    assert result.info["ret"] == 0 and inner != 0
    assert fo.dta_name(result) == "DEEP.TXT"
    assert fo.dta_long(result, fs.DTA_DND) == inner
    assert fo.dta_long(result, fs.DTA_DIRPOS) == d.position_of(d.DOT_ENTRIES)


def test_fsfirst_through_a_child_list_three_long():
    """The root's list as a whole search left it: SUBDIR is its THIRD child, and the root is never read."""
    result = _fsfirst("A:\\SUBDIR\\*.*", SUBDIR, fo.walked_root())
    assert fo.dta_name(result) == "."
    assert fo.dta_long(result, fs.DTA_DND) == d.SUBDIR_DND_AT
    assert result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS) == 0, "the root was searched"


@pytest.mark.parametrize("path,attr,why", (
    ("A:\\SECRET.HID", 0, "a hidden file under the widened 0"),
    ("A:\\EMPTY.BIN", VOLUME, "a read-only file under VOLUME, which is not widened"),
    ("A:\\NOPE.TXT", 0, "a name the directory has not got"),
    ("A:\\NOPE\\*.*", 0, "a DIRECTORY the path has not got: EFILNF too, not EPTHNF"),
    ("A:\\SUBDIR\\INNER\\NOPE", 0, "a name two levels down"),
))
def test_a_miss_is_efilnf_with_the_dta_untouched(path, attr, why):
    result = _fsfirst(path, attr)
    assert result.info["ret"] == fo.EFILNF, why
    _assert_dta_untouched(result)


# ---- sfirst at its own address -----------------------------------------------------------------------------

def _sfirst(path, attr, dta):
    return fo.run(SFIRST, (fo.NAME_AT, attr, dta), path)


def test_sfirst_fills_the_dta_it_is_handed():
    result = _sfirst("A:\\S*.*", 0, fo.DTA_AT)
    assert result.info["ret"] == 0
    assert fo.dta_name(result) == "SHORT.TXT"


def test_sfirst_with_no_dta_answers_0_and_stores_nothing():
    """`Pexec`'s use ($fc81b0): does the file exist? The search still runs — its OFD moves — but no DTA
    is written."""
    result = _sfirst("A:\\SPAN.DAT", 0, NO_DTA)
    assert result.info["ret"] == 0
    _assert_dta_untouched(result)
    assert result.long(fs.ROOT_OFD_AT + fs.OFD_POS) == d.position_of(d.ROOT_INDEX["SPAN"])


# ---- then Fsnext, from the DTA Fsfirst left ------------------------------------------------------------------

def test_fsfirst_then_fsnext_walks_a_wildcard_to_its_end():
    """`S*.*` in the root: SHORT.TXT, SPAN.DAT — and then ENMFIL, the hidden, system, volume and
    subdirectory entries starting with S all refused by the widened attribute 0."""
    first = _fsfirst("A:\\S*.*", 0)
    second = _fsnext(first)
    third = _fsnext(second)
    assert [fo.dta_name(first), fo.dta_name(second)] == ["SHORT.TXT", "SPAN.DAT"]
    assert second.info["ret"] == 0
    assert third.info["ret"] == fo.ENMFIL


def test_fsfirst_then_fsnext_through_a_subdirectory_two_levels_down():
    """INNER under a subdirectory attribute: `.`, `..`, DEEP.TXT (attribute 0 matches anything), LEAF —
    the DND Fsfirst stored, a pool record of the first run, carried into every later one."""
    runs = [_fsfirst("A:\\SUBDIR\\INNER\\*.*", SUBDIR)]
    for _step in range(4):
        runs.append(_fsnext(runs[-1]))
    assert [fo.dta_name(result) for result in runs[:4]] == [".", "..", "DEEP.TXT", "LEAF"]
    assert [result.info["ret"] for result in runs] == [0, 0, 0, 0, fo.ENMFIL]


# ---- through the dispatcher ------------------------------------------------------------------------------

def test_a_dispatched_fsfirst_runs_the_leaf():
    result = fo.dispatch(FSFIRST, (*gemdos.long_words(fo.NAME_AT), SUBDIR), "A:\\SUBDIR\\INNER\\L*")
    assert result.info["ret"] == 0
    assert fo.dta_name(result) == "LEAF"


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    fo.register("sfirst, the first match", SFIRST, (fo.NAME_AT, 0, fo.DTA_AT), "A:\\S*.*")
    fo.register("Fsfirst, two levels down", FSFIRST, (fo.NAME_AT, 0), "\\SUBDIR\\INNER\\*.TXT")
    fo.register("Fsfirst, a miss", FSFIRST, (fo.NAME_AT, 0), "A:\\NOPE.TXT")


_register_all()
