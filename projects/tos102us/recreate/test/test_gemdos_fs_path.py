r"""The file system's PATH layer — `src/gemdos/fs_drive.c`'s four string routines.

  $fc68dc  gemdos_path_start  `X:` and a leading `\` -> the directory node a path starts in
  $fc7e52  gemdos_dot_name    "" / "." / ".." / anything else
  $fc5e08  gemdos_split_path  the next component into an FCB name
  $fc7e94  gemdos_strneq      n bytes equal? — verified STANDALONE: its one caller is the dispatcher's
                              device-name arm (`$fc9aca`), which is a later band

`path_start` NEVER POISONS: the one thing it stores is the path POINTER it then reads through, so the
attribution pass's inverted pointer sends both shores' text reads off the machine (`make guarded`
aborts on it), and a drive not yet logged in takes the staged `Getbpb` besides, whose `trap #13`
writes `savptr` (`gemdos_fs.run`'s reason). The pointer's store is pinned by every case that
CONSUMES something; the one arm that stores it back unchanged ("FOO") is a store no machine state can
see. The other three routines touch nothing but their buffers and always poison.

`entry_d0` is live on all three string routines: each can return through a `move.w`/`clr.w` that
leaves the caller's high half of D0 standing, and `split_path` hands back three DIFFERENT high halves
depending on the arm (`src/gemdos/fs_drive.c` says which), so every case enters with a D0 whose high
half no arm produces.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import fs_records
import gemdos
import gemdos_fs as fs

for _name in ("gemdos_path_start", "gemdos_dot_name", "gemdos_split_path", "gemdos_strneq"):
    getattr(_lib, _name).restype = ctypes.c_uint32

# ---- the band, in the fs record gap (`test/fs_records.py`) ---------------------------------------
PATH_BAND = fs.SPAN.claim(fs_records.PATH_BAND_AT, fs_records.PATH_BAND_BYTES, "test/test_gemdos_fs_path.py")
POINTER_AT = PATH_BAND                  # the `char **` path_start is handed
TEXT_AT = PATH_BAND + 0x10              # a path, or strneq's left string
OTHER_AT = PATH_BAND + 0x60             # strneq's right string
FCB_AT = PATH_BAND + 0xB0               # split_path's FCB
TEXT_BYTES = OTHER_AT - TEXT_AT
FCB_BYTES = 0x10                        # the eleven, plus slack a run must not reach
FCB_NAME_BYTES = fs.DIRENT_NAME_BYTES
assert FCB_AT + FCB_BYTES <= PATH_BAND + fs_records.PATH_BAND_BYTES

ENTRY_D0 = fs.ENTRY_D0
FILL = gemdos.FILL
# `$fc7e52`'s dot answers as the low word they are: the number of dots, negated.
DOT_NAME_SELF = -1 & fs.D0_LOW_WORD
DOT_NAME_PARENT = -2 & fs.D0_LOW_WORD

LOGGED_IN = 0                           # A:, in the snapshot's mask
NOT_LOGGED_IN = 1                       # B:, not
SNAPSHOT_CURDIR = BASE_IMAGE[fs.curdir_at(LOGGED_IN)]
# A directory node a case stages for p_curdir to name: any non-zero longword that is not the root's,
# because the routine answers it without following it.
SOME_NODE = fs.ROOT_DND_AT


def _node(index):
    return case.long_in(BASE_IMAGE, fs.node_slot(index))


def _root_node(drive):
    return case.long_in(BASE_IMAGE, case.long_in(BASE_IMAGE, fs.dmd_slot(drive))
                        + fs.DMD_ROOT_DND)


def _text(text, at=TEXT_AT):
    """`text` NUL-ended, the rest of its buffer `FILL` — so a read past the NUL reads a byte no
    case chose to make meaningful, and the two shores read the same one."""
    raw = text.encode("latin-1") + b"\0"
    assert len(raw) <= TEXT_BYTES
    return {at: raw + bytes([FILL]) * (TEXT_BYTES - len(raw))}


# ---- path_start, $fc68dc -------------------------------------------------------------------------

def _path_start_pokes(text, pokes=None):
    return {**_text(text), POINTER_AT: struct.pack(">I", TEXT_AT), **(pokes or {}), **case.long_args(POINTER_AT)}


def _path_start(text, pokes=None):
    result = fs.run(addrs.GEMDOS_PATH_START, lambda lib, buf: lib.gemdos_path_start(buf, POINTER_AT),
                    _path_start_pokes(text, pokes))
    return result.info, result.final


def _consumed(final):
    return case.long_in(final, POINTER_AT) - TEXT_AT


@pytest.mark.parametrize("text,node,consumed,why", (
    ("A:\\FOO", "root", 3, "a drive and a separator: that drive's root, both consumed"),
    ("a:\\FOO", "root", 3, "the letter is upper-cased first"),
    ("A:FOO", "curdir", 2, "a drive and no separator: the process's directory ON THAT DRIVE"),
    ("\\FOO", "root", 1, "no drive: the current one, and its root"),
    ("FOO", "curdir", 0, "neither: the current drive's current directory — the pointer STORED back"),
    ("", "curdir", 0, "the empty path, whose `:` test reads the byte past its NUL"),
))
def test_path_start_on_a_logged_in_drive(text, node, consumed, why):
    info, final = _path_start(text)
    expected = _root_node(LOGGED_IN) if node == "root" else _node(SNAPSHOT_CURDIR)
    assert info["ret"] == expected, why
    assert _consumed(final) == consumed, why
    assert POINTER_AT in info["writes"], "the ROM stores the pointer even when nothing was consumed"
    assert not fs.DISK_CALLS


def test_the_current_directory_is_the_process_s_own_and_not_the_root():
    """The snapshot's p_curdir[0] names the root node itself, so "curdir" and "root" answer alike
    over it; a directory staged elsewhere is what tells the two arms apart."""
    slot = 5
    pokes = fs.current_directory_poke(LOGGED_IN, slot, SOME_NODE)
    assert SOME_NODE != _root_node(LOGGED_IN)
    info, _final = _path_start("A:FOO", pokes)
    assert info["ret"] == SOME_NODE


def test_path_start_logs_a_new_drive_in():
    """`B:` is not in the mask: the log-in runs whole under it, and the node answered is the one it
    just handed the process — B:'s new root."""
    info, final = _path_start("B:FOO")
    slot = final[fs.curdir_at(NOT_LOGGED_IN)]
    assert info["ret"] == case.long_in(final, fs.node_slot(slot)) != 0
    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_GETBPB_FN]
    assert _consumed(final) == 2


def test_path_start_follows_the_current_drive_byte():
    """No `X:`: the drive is the basepage's `p_curdrv`, here B:."""
    info, _final = _path_start("FOO", gemdos.current_drive_poke(NOT_LOGGED_IN))
    assert fs.DISK_CALLS[0] == (addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, NOT_LOGGED_IN)
    assert info["ret"] != 0


@pytest.mark.parametrize("text,drive,why", (
    ("Q:FOO", ord("Q") - ord("A"), "a drive with no BPB"),
    ("1:FOO", (ord("1") - ord("A")) & 0xFFFF, "a digit: 'A' subtracted as a WORD with no bound, so "
                                              "drive -16 is what the BIOS is asked about"),
))
def test_path_start_answers_0_and_leaves_the_pointer_when_the_drive_will_not_open(text, drive, why):
    info, _final = _path_start(text, fs.getbpb_answer(0))
    assert info["ret"] == 0, why
    assert POINTER_AT not in info["writes"], "the pointer is stored only on success"
    assert fs.DISK_CALLS == [(addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, drive)], why


def test_the_current_drive_byte_is_SIGNED():
    """`ext.w` on `p_curdrv`: a byte of $ff is drive -1, which the BIOS is asked about as $ffff."""
    info, _final = _path_start("FOO", {**gemdos.current_drive_poke(0xFF), **fs.getbpb_answer(0)})
    assert info["ret"] == 0
    assert fs.DISK_CALLS == [(addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, 0xFFFF)]


# ---- dot_name, $fc7e52 ---------------------------------------------------------------------------

def _dot_name_pokes(text, terminator):
    return {**_text(text), **case.args(">IH", TEXT_AT, terminator)}


def _dot_name(text, terminator):
    info = case.run(addrs.GEMDOS_DOT_NAME, {"d0": ENTRY_D0, "a5": 0, "_pokes": _dot_name_pokes(text, terminator)},
                    lambda lib, buf: lib.gemdos_dot_name(ENTRY_D0, buf, TEXT_AT, terminator))
    return info["regs"]["d0"]


SEPARATOR = ord("\\")
DOT_CASES = (
    ("", 0, fs.DOT_NAME_EMPTY, "the NUL: `moveq #1`, which writes the whole register"),
    (".", 0, DOT_NAME_SELF, "'.' then the terminator"),
    ("..", 0, DOT_NAME_PARENT, "'..' then the terminator"),
    (".\\X", SEPARATOR, DOT_NAME_SELF, "...a separator as the terminator"),
    ("..\\X", SEPARATOR, DOT_NAME_PARENT, "..."),
    (".\\X", 0, 0, "'.' followed by something that is NOT the terminator"),
    ("...", 0, 0, "three dots: the loop takes at most two"),
    (".X", 0, 0, "a dot then a letter"),
    ("..X", 0, 0, "two dots then a letter"),
    ("X", 0, 0, "no dot at all"),
    ("\\", SEPARATOR, 0, "the component is empty but not the NUL: a separator is not a dot"),
    ("..", ord("."), DOT_NAME_SELF, "a terminator of '.' makes '..' the SELF name"),
    ("..", 0xFF00, DOT_NAME_PARENT, "only the terminator's LOW byte is compared (`cmp.b 13(a6)`)"),
)


@pytest.mark.parametrize("text,terminator,expected,why", DOT_CASES, ids=[row[-1] for row in DOT_CASES])
def test_dot_name(text, terminator, expected, why):
    d0 = _dot_name(text, terminator)
    if expected == fs.DOT_NAME_EMPTY:
        assert d0 == fs.DOT_NAME_EMPTY, why
    else:
        assert d0 == fs.callers_high_half(ENTRY_D0) | expected, why


# ---- split_path, $fc5e08 -------------------------------------------------------------------------

def _split_pokes(text, take_tail):
    return {**_text(text), FCB_AT: bytes([FILL]) * FCB_BYTES, **case.args(">IIH", TEXT_AT, FCB_AT, take_tail)}


def _split(text, take_tail):
    info = case.run(addrs.GEMDOS_SPLIT_PATH, {"d0": ENTRY_D0, "a5": 0, "_pokes": _split_pokes(text, take_tail)},
                    lambda lib, buf: lib.gemdos_split_path(ENTRY_D0, buf, TEXT_AT, FCB_AT, take_tail))
    fcb = bytes(info["writes"].get(FCB_AT + at, FILL) for at in range(FCB_BYTES))
    return info["regs"]["d0"], fcb


CALLERS = fs.callers_high_half(ENTRY_D0)
UNTOUCHED = bytes([FILL]) * FCB_BYTES
SPLIT_CASES = (
    # (text, take_tail, D0, FCB name or None for "not built", why)
    ("FOO\\BAR", 0, 3, "FOO        ", "a component before a separator: built, its length, high half 0"),
    ("FOO", 0, CALLERS, None, "the TAIL without take_tail: 0 over the caller's high half, nothing built"),
    ("FOO", 1, 3, "FOO        ", "...and with it: taken like any other"),
    ("NAME.TXT\\X", 0, 8, "NAME    TXT", "the length counts the dot"),
    ("LONGFILENAME.TXT\\X", 0, 16, "LONGFILETXT", "...and every byte to the separator"),
    (".\\X", 0, CALLERS | DOT_NAME_SELF, None, "'.': -1, nothing built"),
    ("..\\X", 0, CALLERS | DOT_NAME_PARENT, None, "'..': -2"),
    ("..", 1, CALLERS | DOT_NAME_PARENT, None, "'..' as the tail, taken"),
    ("..", 0, CALLERS, None, "...and not taken: the tail test comes BEFORE the dot test"),
    ("\\X", 0, CALLERS, None, "an empty component at a separator: 0, nothing built"),
    ("", 1, 0, None, "the empty tail, taken: `$fc7e52`'s `moveq #1` leaves the high half 0"),
    ("...\\X", 0, 3, "           ", "three dots are an ordinary name, built — as eleven spaces"),
)


@pytest.mark.parametrize("text,take_tail,d0,name,why", SPLIT_CASES, ids=[row[-1] for row in SPLIT_CASES])
def test_split_path(text, take_tail, d0, name, why):
    result, fcb = _split(text, take_tail)
    assert result == d0, why
    if name is None:
        assert fcb == UNTOUCHED, why
    else:
        assert fcb[:FCB_NAME_BYTES] == name.encode("latin-1"), why


# ---- strneq, $fc7e94 -----------------------------------------------------------------------------

def _strneq_pokes(left, right, count):
    return {**_text(left), **_text(right, OTHER_AT), **case.args(">HII", count, TEXT_AT, OTHER_AT)}


def _strneq(left, right, count):
    info = case.run(addrs.GEMDOS_STRNEQ, {"d0": ENTRY_D0, "a5": 0, "_pokes": _strneq_pokes(left, right, count)},
                    lambda lib, buf: lib.gemdos_strneq(ENTRY_D0, buf, count, TEXT_AT, OTHER_AT))
    return info["regs"]["d0"]


STRNEQ_CASES = (
    ("CON:", "CON:", 4, 1, "the device name the dispatcher asks about"),
    ("CON:", "CON;", 4, CALLERS, "the last byte differs"),
    ("XON:", "CON:", 4, CALLERS, "the first differs"),
    ("CON:", "CON;", 3, 1, "a count short of the difference"),
    ("A", "B", 0, 1, "a count of 0 compares nothing"),
    ("AB\0X", "AB\0X", 4, 1, "no NUL stops it: the bytes after one are compared too"),
    ("AB\0X", "AB\0Y", 4, CALLERS, "...and can differ"),
    ("con:", "CON:", 4, CALLERS, "case-sensitive"),
    ("\xe9\x80", "\xe9\x80", 2, 1, "bit 7 set on both sides"),
    ("\x80", "\x00", 1, CALLERS, "...and against a byte without it"),
)


@pytest.mark.parametrize("left,right,count,expected,why", STRNEQ_CASES, ids=[row[-1] for row in STRNEQ_CASES])
def test_strneq(left, right, count, expected, why):
    assert _strneq(left, right, count) == expected, why


# ---- the registry --------------------------------------------------------------------------------

gemdos.register("path_start, a drive and its root", addrs.GEMDOS_PATH_START, {"a5": 0},
                fs.machine(_path_start_pokes("A:\\FOO")))
gemdos.register("dot_name, '..'", addrs.GEMDOS_DOT_NAME, {"d0": ENTRY_D0, "a5": 0},
                _dot_name_pokes("..\\X", SEPARATOR))
gemdos.register("split_path, a component", addrs.GEMDOS_SPLIT_PATH, {"d0": ENTRY_D0, "a5": 0},
                _split_pokes("NAME.TXT\\X", 0))
gemdos.register("strneq, a device name", addrs.GEMDOS_STRNEQ, {"d0": ENTRY_D0, "a5": 0},
                _strneq_pokes("CON:", "CON:", 4))
