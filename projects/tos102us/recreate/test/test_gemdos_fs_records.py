"""The record layer's TEXT half and the byte swaps — `src/gemdos/fs_records.c`, `src/gemdos/fs_copy.c`.

Name equality, an FCB name as text, a directory's path, and the DTA a search fills: routines that
build nothing out of the pool and touch no disk, so every arm of each is reachable with records
staged in `test/fs_records.py`'s slots. The pool and cache half is `test_gemdos_fs_records_pool.py`.
"""
import ctypes
import struct

import pytest

from harness import _lib, addrs

import case
import fs_records as rec
import gemdos
import gemdos_fs as fs

for _name in ("gemdos_fcb_name_eq", "gemdos_fcb_to_text", "gemdos_dnd_path"):
    getattr(_lib, _name).restype = ctypes.c_uint32
for _name in ("os_swap_word", "os_swap_long", "gemdos_fill_dta"):
    getattr(_lib, _name).restype = None

# Two output buffers, each pre-filled with `SLACK_FILL` so a byte past what a routine should write
# still reads as that: a text, and a DTA.
TEXT_BAND = fs.SPAN.claim(rec.TEXT_BAND_AT, rec.TEXT_BAND_BYTES, "test/test_gemdos_fs_records.py")
TEXT_BYTES = rec.TEXT_BAND_BYTES // 2
TEXT_AT = TEXT_BAND
DTA_AT = TEXT_BAND + TEXT_BYTES

NAME_AT = rec.dirent_slot(0)
OTHER_AT = rec.dirent_slot(1)


def _text_buffers():
    return {TEXT_AT: bytes([fs.SLACK_FILL]) * rec.TEXT_BAND_BYTES}


# ---- the byte swaps, $fc4f10 and $fc4f22 ---------------------------------------------------------

SWAP_AT = rec.dirent_slot(2)
# The word after a swapped word, which a swap must not reach.
NEIGHBOUR = 0x5A5A


def _swap_word_pokes(value):
    return {SWAP_AT: struct.pack(">HH", value, NEIGHBOUR), **case.long_args(SWAP_AT)}


def _swap_long_pokes(value):
    return {SWAP_AT: struct.pack(">I", value), **case.long_args(SWAP_AT)}


@pytest.mark.parametrize("value", (0x1234, 0x00FF, 0xFF00, 0x8001))
def test_swap_word_exchanges_the_two_bytes_in_place(value):
    pokes = _swap_word_pokes(value)
    info = case.run(addrs.OS_SWAP_WORD, {"_pokes": pokes},
                    lambda lib, buf: lib.os_swap_word(buf, SWAP_AT), width=case.NO_RESULT)
    final = case.final_image(info, pokes)
    assert bytes(final[SWAP_AT:SWAP_AT + 4]) == struct.pack(">HH", fs.byte_swapped(value, "H"), NEIGHBOUR)


@pytest.mark.parametrize("value", (0x12345678, 0x000000FF, 0x80000001, 0x00FF00FF))
def test_swap_long_reverses_all_four_bytes_in_place(value):
    info = case.run(addrs.OS_SWAP_LONG, {"_pokes": _swap_long_pokes(value)},
                    lambda lib, buf: lib.os_swap_long(buf, SWAP_AT), width=case.NO_RESULT)
    assert case.written_long(info, SWAP_AT) == fs.byte_swapped(value, "I")


# ---- fcb_name_eq, $fc5672 ------------------------------------------------------------------------

def _name_eq_pokes(name, other):
    return {NAME_AT: name, OTHER_AT: other, **case.long_args(NAME_AT, OTHER_AT)}


def _name_eq(name, other):
    return case.run(addrs.GEMDOS_FCB_NAME_EQ, {"d0": fs.ENTRY_D0, "_pokes": _name_eq_pokes(name, other)},
                    lambda lib, buf: lib.gemdos_fcb_name_eq(fs.ENTRY_D0, buf, NAME_AT, OTHER_AT))


EQ_CASES = (
    (fs.fcb_name("SUBDIR"), fs.fcb_name("SUBDIR"), True, "the same name"),
    (fs.fcb_name("subdir"), fs.fcb_name("SUBDIR"), True, "folded on the first side"),
    (fs.fcb_name("SUBDIR"), fs.fcb_name("subDir"), True, "...and on the second"),
    (fs.fcb_name("XUBDIR"), fs.fcb_name("SUBDIR"), False, "the first byte apart"),
    (fs.fcb_name("SUBDIR", "ABC"), fs.fcb_name("SUBDIR", "ABD"), False, "the ELEVENTH byte apart"),
    (fs.fcb_name("?UBDIR"), fs.fcb_name("SUBDIR"), False, "a `?` is a byte here, not a wildcard"),
    (b"\xe1" + fs.fcb_name("X")[1:], b"\xe1" + fs.fcb_name("x")[1:], True,
     "a bit-7 byte is left unfolded and matches itself"),
    (b"\xe1" + fs.fcb_name("X")[1:], b"\xc1" + fs.fcb_name("X")[1:], False,
     "...and is not folded onto another: $e1 & $5f would be $41"),
)


@pytest.mark.parametrize("name,other,equal,why", EQ_CASES, ids=[row[-1] for row in EQ_CASES])
def test_fcb_name_eq_is_eleven_folded_bytes(name, other, equal, why):
    info = _name_eq(name + b"\x10", other + b"\x01")   # the attribute bytes differ, and are not read
    assert (info["regs"]["d0"] == 1) is equal, why


def test_a_mismatch_clears_only_the_low_word_of_d0():
    """`clr.w d0`, the `$fc5c9a` quirk: the caller's high half stands, which a `uint16_t` core would
    have cleared. The ROM's callers test with `tst.w`, so it is moot to them and a fact here."""
    info = _name_eq(fs.fcb_name("ONE"), fs.fcb_name("TWO"))
    assert info["regs"]["d0"] == fs.callers_high_half(fs.ENTRY_D0)


# ---- fcb_to_text, $fc6b66 ------------------------------------------------------------------------

def _fcb_to_text_pokes(fcb):
    return {NAME_AT: fcb, **_text_buffers(), **case.long_args(NAME_AT, TEXT_AT)}


def _fcb_to_text(fcb):
    pokes = _fcb_to_text_pokes(fcb)
    info = case.run(addrs.GEMDOS_FCB_TO_TEXT, {"_pokes": pokes},
                    lambda lib, buf: lib.gemdos_fcb_to_text(buf, NAME_AT, TEXT_AT))
    return info, case.final_image(info, pokes)


TEXT_CASES = (
    (fs.fcb_name("SHORT", "TXT"), b"SHORT.TXT", "stem, dot, extension"),
    (fs.fcb_name("SUBDIR"), b"SUBDIR", "a blank extension gets no dot"),
    (fs.fcb_name("ABCDEFGH", "XYZ"), b"ABCDEFGH.XYZ", "both fields full"),
    (fs.fcb_name("short", "txt"), b"short.txt", "no folding: the bytes go through as they are"),
    (fs.fcb_name("."), b".", "the `.` entry"),
    (fs.fcb_name("..", "XYZ"), b"..", "a stem starting with `.` gets NO extension, even a non-blank one"),
    (fs.fcb_name("A B", "TXT"), b"A.TXT", "a space ends the stem, and the extension still follows"),
    (fs.fcb_name("A", "T X"), b"A.T", "...and ends the extension"),
    (b"A\0CDEFGHTXT", b"A.TXT", "a NUL ends the stem"),
    (fs.fcb_name("A")[:8] + b"\0XY", b"A.", "an extension starting with NUL is not blank: the dot is written"),
    (b"\0" + fs.fcb_name("GONE", "OLD")[1:], b"", "an FCB starting with NUL is the empty string"),
)


@pytest.mark.parametrize("fcb,text,why", TEXT_CASES, ids=[row[-1] for row in TEXT_CASES])
def test_fcb_to_text_writes_the_name_and_a_nul_and_answers_the_nul(fcb, text, why):
    info, final = _fcb_to_text(fcb)
    assert bytes(final[TEXT_AT:TEXT_AT + len(text) + 1]) == text + b"\0", why
    assert info["regs"]["d0"] == TEXT_AT + len(text), "the answer is the address of the NUL"
    assert final[TEXT_AT + len(text) + 1] == fs.SLACK_FILL, "a byte past the NUL was written"


# ---- dnd_path, $fc6bd2 ---------------------------------------------------------------------------

ROOT_AT = rec.record_slot(0)
SUB_AT = rec.record_slot(1)
DEEP_AT = rec.record_slot(2)


def _tree():
    """root (no name) <- SUB <- DEEP.EXT, each DND naming its parent."""
    return {**fs.stage_dnd(ROOT_AT, name=bytes(fs.DIRENT_NAME_BYTES)),
            **fs.stage_dnd(SUB_AT, name=fs.fcb_name("SUB"), parent=ROOT_AT),
            **fs.stage_dnd(DEEP_AT, name=fs.fcb_name("DEEP", "EXT"), parent=SUB_AT)}


def _dnd_path_pokes(dnd, pokes):
    return {**pokes, **_text_buffers(), **case.long_args(dnd, TEXT_AT)}


def _dnd_path(dnd, pokes):
    pokes = _dnd_path_pokes(dnd, pokes)
    info = case.run(addrs.GEMDOS_DND_PATH, {"_pokes": pokes},
                    lambda lib, buf: lib.gemdos_dnd_path(buf, dnd, TEXT_AT))
    return info, case.final_image(info, pokes)


@pytest.mark.parametrize("dnd,path", ((ROOT_AT, b"\\"), (SUB_AT, b"\\SUB\\"),
                                      (DEEP_AT, b"\\SUB\\DEEP.EXT\\")))
def test_dnd_path_is_root_first_with_a_separator_after_every_name(dnd, path):
    """Recursion up the parent chain: the root's empty name is what makes the leading `\\`. Every `\\`
    lands on the NUL `fcb_to_text` left, so the text is NOT terminated — the byte after it is still
    the buffer's fill, and the answer is one past the last `\\` (`Dgetpath` writes the NUL there)."""
    info, final = _dnd_path(dnd, _tree())
    assert bytes(final[TEXT_AT:TEXT_AT + len(path)]) == path
    assert final[TEXT_AT + len(path)] == fs.SLACK_FILL
    assert info["regs"]["d0"] == TEXT_AT + len(path)


def test_a_dnd_with_no_parent_is_a_root_whatever_its_name():
    """The recursion stops on DND_PARENT == 0, not on an empty name."""
    info, final = _dnd_path(SUB_AT, fs.stage_dnd(SUB_AT, name=fs.fcb_name("X")))
    assert bytes(final[TEXT_AT:TEXT_AT + 2]) == b"X\\"


# ---- fill_dta, $fc6ebc ---------------------------------------------------------------------------

DTA_ENTRY_LENGTH = 0x0001_2345
# A found attribute with two bits set, so a DTA that took one of them is a wrong byte.
FOUND_ATTR = fs.GEMDOS_ATTR_ARCHIVE | fs.GEMDOS_ATTR_READ_ONLY
# The ten DOS-reserved bytes, staged non-zero, so a copy reaching into them is a wrong byte.
RESERVED_FILL = 0x77


def _dta_entry(name, extension, reserved=0):
    return fs.dirent_bytes(name, extension, attr=FOUND_ATTR, cluster=fs.SHORT_CLUSTER,
                           length=DTA_ENTRY_LENGTH, time=fs.STAGED_DIRENT_TIME,
                           date=fs.STAGED_DIRENT_DATE, reserved=reserved)


def _fill_dta_pokes(entry):
    return {NAME_AT: entry, **_text_buffers(), **case.long_args(NAME_AT, DTA_AT)}


def _fill_dta(entry):
    pokes = _fill_dta_pokes(entry)
    info = case.run(addrs.GEMDOS_FILL_DTA, {"_pokes": pokes},
                    lambda lib, buf: lib.gemdos_fill_dta(buf, NAME_AT, DTA_AT), width=case.NO_RESULT)
    return case.final_image(info, pokes)


@pytest.mark.parametrize("name,extension,text", (("SHORT", "TXT", b"SHORT.TXT"),
                                                 ("SUBDIR", "", b"SUBDIR")))
def test_fill_dta_turns_time_date_and_length_round_and_writes_the_name(name, extension, text):
    """The attribute byte as it is; time, date and length from the entry's little-endian order into
    the 68000's; the name as `fcb_to_text` makes it. The ten DOS-reserved bytes are staged non-zero,
    so a copy reaching into them would be a wrong byte."""
    final = _fill_dta(_dta_entry(name, extension, reserved=RESERVED_FILL))
    assert final[DTA_AT + fs.DTA_FOUND_ATTR] == FOUND_ATTR
    assert case.word_in(final, DTA_AT + fs.DTA_TIME) == fs.STAGED_DIRENT_TIME
    assert case.word_in(final, DTA_AT + fs.DTA_DATE) == fs.STAGED_DIRENT_DATE
    assert case.long_in(final, DTA_AT + fs.DTA_FILELN) == DTA_ENTRY_LENGTH
    name_at = DTA_AT + fs.DTA_NAME
    assert bytes(final[name_at:name_at + len(text) + 1]) == text + b"\0"
    # ...and nothing of the DTA's first 21 bytes, the search state, is touched.
    assert bytes(final[DTA_AT:DTA_AT + fs.DTA_FOUND_ATTR]) == bytes([fs.SLACK_FILL]) * fs.DTA_FOUND_ATTR


# ---- the registry --------------------------------------------------------------------------------

gemdos.register("os_swap_word, one word", addrs.OS_SWAP_WORD, {}, _swap_word_pokes(0x1234))
gemdos.register("os_swap_long, one long", addrs.OS_SWAP_LONG, {}, _swap_long_pokes(0x12345678))
gemdos.register("fcb_name_eq, equal but for case", addrs.GEMDOS_FCB_NAME_EQ, {"d0": fs.ENTRY_D0},
                _name_eq_pokes(fs.fcb_name("subdir"), fs.fcb_name("SUBDIR")))
gemdos.register("fcb_to_text, stem and extension", addrs.GEMDOS_FCB_TO_TEXT, {},
                _fcb_to_text_pokes(fs.fcb_name("SHORT", "TXT")))
gemdos.register("dnd_path, two levels below the root", addrs.GEMDOS_DND_PATH, {},
                _dnd_path_pokes(DEEP_AT, _tree()))
gemdos.register("fill_dta, a file", addrs.GEMDOS_FILL_DTA, {}, _fill_dta_pokes(_dta_entry("SHORT", "TXT")))
