"""THE DESK'S PATH AND FILE NODES (`src/desk/deskfpd.c`; band 6 wave 1b, group G3, unit G): sixteen routines
`$fdf6d0..$fdfc3b`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskact.arrival`): a chain of the hands stopped at the routine's first
    instruction, the arguments read off the frame the desk's caller pushed. None of the sixteen reaches the
    dispatcher: each case is the kit's plain differential over the arrival's megabyte (`aes_deskact.plain`) — the
    answer at its declared width, every byte. The list routines run UNPOISONED (`aes_deskact.UNPOISONED`: they follow
    the links they store).
  * WHERE NO CHAIN REACHES AN ARM, A LABELLED ARGUMENT CLASS (its label in the id): the same machine with other
    arguments — a pointer moved to bytes the machine itself holds (a text's own NUL, a run of the ROM's bytes with no
    NUL, a node's name) wherever one serves — or, where it says LAID, a staging laid over it (a spec text, a list's
    head, a date word); fpd_parse's arm of the current drive with Dgetdrv SCRIPTED (`aes_gemdosif`'s recording trap).
  * D0 AT RETURN: an answering routine's word or long is held to the ROM's run IN PLACE at every arrival; a void
    routine's D0 is the ROM's leftover — A NAMED, COUNTED DIVERGENCE (no word in C), read by no caller
    (`aes_deskbind.answer_readers`).

TWO ROM BEHAVIOURS NO C CAN HAVE (`deskfpd.c`): fpd_parse moves its own argument pointers in its caller's frame, and
pn_sort counts into its own count word there — no ROM caller reads them back (the same reading).
"""
import functools
import struct
from collections import Counter

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_deskact as da
import aes_deskbind as db
import aes_deskfpd as df
import aes_gemdosif as gd
import case
import layouts

Case, UNPOISONED = da.Case, da.UNPOISONED
BUS = da.BUS

# THE CHAINS
SHOWN, SHOWN_LONG = "file: shown, a key at its end", "files: the long file shown, a blank at each page's end and at its end"
OPEN_A, OPENED, FOLDER_OPENED, FOLDER_CLOSED = "A: File > Open", "A: opened", "folder: opened", "folder: File > Close"
CLOSED, CLOSER, SELECTED = "window: File > Close Window", "window: its closer clicked", "file: selected"
COPIED_INTO_THE_FOLDER, FILES_OPENED = "folder: the file dragged onto it, Return", "files: A: opened"
BY_SIZE, BY_DATE, BY_TYPE = "files: View > Sort by Size", "files: View > Sort by Date", "files: View > Sort by Type"
TO_THE_TRASH, NOT_EMPTY = "file: dragged to the trash, OK", "files: the folder (not empty) dragged to the trash, OK"
AS_TEXT, NEW_FOLDER = "window: View > Show as Text", "folder: File > New Folder, 'A', Return"

# THE NODES' LAYOUT (`desk/deskfpd.h`) and the desk's globals (`desk/deskglobals.h`), as the cases read them
FPD = layouts.parse_constants((db.GLOBALS_HEADER, aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)
FNODE_NAME, FNODE_DATE, FNODE_SIZE, FNODE_ATTR = FPD["FNODE_NAME"], FPD["FNODE_DATE"], FPD["FNODE_SIZE"], FPD["FNODE_ATTR"]
FNODE_ATTR_SUBDIR = FPD["FNODE_ATTR_SUBDIR"]
SORT_BY_SIZE, SORT_BY_DATE, SORT_BY_TYPE, A_KEY_NO_ARM_HAS = FPD["SORT_BY_SIZE"], FPD["SORT_BY_DATE"], FPD["SORT_BY_TYPE"], 4
DESK_FILES_FREE, DESK_PATHS_FREE = FPD["DESK_FILES_FREE"], FPD["DESK_PATHS_FREE"]
SPEC_BYTES, SPEC_ROOM_BESIDE_THE_PATH = FPD["SPEC_BYTES"], FPD["SPEC_ROOM_BESIDE_THE_PATH"]
A_DAY = 1                               # a date word's day field: its low bits


def _a_text_s_nul(arrived, index):
    """The address of the NUL that ends the text argument `index` points at: an EMPTY text the machine holds."""
    at = arrived.arguments[index] & BUS
    return at + bytes(arrived.boot.ram[at:]).index(b"\0")


@functools.cache
def _a_text_of_the_rom_s(length):
    """An address of the ROM's GEM text from which exactly `length` bytes run to a NUL: a 'path' of that length."""
    lo, hi = aes.AES_TEXT
    run_from = lo
    for at in range(lo, hi):
        if BASE_IMAGE[at] == 0:
            if at - run_from >= length:
                return at - length
            run_from = at + 1
    raise AssertionError(f"the ROM's GEM text has no run of {length} bytes before a NUL")


LONGEST_PATH = SPEC_BYTES - SPEC_ROOM_BESIDE_THE_PATH - 1     # 107: the spec's room less the rest, the compare `blt`


def _with(index, value):
    """An arrival's own arguments, the one at `index` made `value` (a value, or `arrival -> value`)."""
    return lambda arrived: (*arrived.arguments[:index], value(arrived) if callable(value) else value, *arrived.arguments[index + 1:])


def _nth_node(arrived, files, nth):
    """The list's `nth` node (from 0), off the arrival's megabyte."""
    for _step in range(nth):
        files = case.long_in(arrived.boot.ram, files & BUS)
    return files


def _desk(arrived):
    return case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & BUS


def _head_laid(offset, value=0):
    """LAID: the desk's list head at `offset` of its globals."""
    return lambda arrived: {_desk(arrived) + offset: struct.pack(">I", value)}


def _spec_laid(text):
    return f"the spec {text!r}", lambda _arrived: da.laid_text(text)


def _date_on(days):
    """LAID: the second file's date word, `days` on from its own."""
    def laid(arrived):
        second = arrived.arguments[1] & BUS
        return {second + FNODE_DATE: struct.pack(">H", case.word_in(arrived.boot.ram, second + FNODE_DATE) + days * A_DAY)}
    return laid


FNODE_TIME, TWO_SECOND_FIELD_BIT, A_MINUTE = FPD["FNODE_TIME"], 0x10, 0x20
SIXTEEN_HOURS = 0x8000                  # a time word's top bit: its hour field 16 or more
THREE_DAYS = 3
A_HIGH_WORD_ALONE = 0x10000             # a size larger by its high word alone (its low word 0: smaller there)
ATTRIBUTE_HIGH_BYTE = 0x0100            # an attribute word with a bit in its high byte
READ_ONLY = 0x01                        # a DTA's read-only attribute bit


def _time_on(by):
    """LAID: the second file's time word `by` on from its own."""
    def laid(arrived):
        second = arrived.arguments[1] & BUS
        return {second + FNODE_TIME: struct.pack(">H", case.word_in(arrived.boot.ram, second + FNODE_TIME) + by)}
    return laid


def _size_laid(size):
    """LAID: the second file's size long."""
    return lambda arrived: {(arrived.arguments[1] & BUS) + FNODE_SIZE: struct.pack(">I", size)}


PNODE_FLAGS, FLAGS_IN_BOTH_BYTES = FPD["PNODE_FLAGS"], 0x0101


def _free_path_s_flags_laid(arrived):
    """LAID: the free path list's first node's flags word, a bit in each byte."""
    node = case.long_in(arrived.boot.ram, _desk(arrived) + DESK_PATHS_FREE) & BUS
    return {node + PNODE_FLAGS: struct.pack(">H", FLAGS_IN_BOTH_BYTES)}


def _first_read_only(arrived):
    """LAID: pn_comp's first file's attributes with the read-only bit set (no disk of the chains has a read-only file
    beside another to sort)."""
    first, second = (each & BUS for each in arrived.arguments[:2])
    assert not (arrived.boot.ram[first + FNODE_ATTR] | arrived.boot.ram[second + FNODE_ATTR]) & FNODE_ATTR_SUBDIR, "a folder"
    return {first + FNODE_ATTR: bytes((arrived.boot.ram[first + FNODE_ATTR] | READ_ONLY,))}


def _a_name_twice(arrived):
    """LAID: the list's third file's name made its fourth's (two files pn_comp answers 0 for)."""
    files = arrived.arguments[1]
    third, fourth = (_nth_node(arrived, files, nth) & BUS for nth in (2, 3))
    name = bytes(arrived.boot.ram[fourth + FNODE_NAME:fourth + FNODE_NAME + 14])
    return {third + FNODE_NAME: name}


THE_CURRENT_DRIVE = 2                   # what the scripted Dgetdrv answers: C:


def _dgetdrv_scripted(_arrived):
    return case.merge_pokes(gd.STALE_DOS, gd.scripted_pokes([THE_CURRENT_DRIVE]))


SCRIPTED = "Dgetdrv SCRIPTED (aes_gemdosif's recording trap) answers C:"

CASES = (
    *(Case(name, chain) for name in ("AES_ROM_FN_INIT", "AES_ROM_PN_INIT", "AES_ROM_FPD_START") for chain in (SHOWN, SHOWN_LONG)),
    # fpd_bldspec: no name ("A:\"), a name and an extension ("A:\*.*"), and a path before them ("A:\A\*.*")
    Case("AES_ROM_FPD_BLDSPEC", OPEN_A), Case("AES_ROM_FPD_BLDSPEC", SHOWN), Case("AES_ROM_FPD_BLDSPEC", FOLDER_OPENED),
    Case("AES_ROM_FPD_BLDSPEC", FOLDER_OPENED, why="a path and no name (the name its own NUL): no separator after the path",
         arguments=_with(2, lambda arrived: _a_text_s_nul(arrived, 1))),
    Case("AES_ROM_FPD_BLDSPEC", FOLDER_OPENED, why="a name and no extension (the extension its own NUL): no mark",
         arguments=_with(3, lambda arrived: _a_text_s_nul(arrived, 3))),
    Case("AES_ROM_FPD_BLDSPEC", FOLDER_OPENED, why="a path of 108 bytes (a run of the ROM's own text): refused",
         arguments=_with(1, lambda _arrived: _a_text_of_the_rom_s(LONGEST_PATH + 1))),
    Case("AES_ROM_FPD_BLDSPEC", FOLDER_OPENED, why="a path of 107 bytes (a run of the ROM's own text): built, the longest",
         arguments=_with(1, lambda _arrived: _a_text_of_the_rom_s(LONGEST_PATH))),
    # fpd_parse: its three callers, each "A:\..."
    Case("AES_ROM_FPD_PARSE", CLOSED), Case("AES_ROM_FPD_PARSE", FOLDER_CLOSED), Case("AES_ROM_FPD_PARSE", SHOWN),
    # (Dgetdrv's recording trap keeps a ledger in its band: the attribution pass would invert it under the ROM's records)
    Case("AES_ROM_FPD_PARSE", CLOSED, why="a spec with no drive (the spec past its \"A:\\\"): the current drive's letter, from Dgetdrv",
         arguments=_with(0, lambda arrived: arrived.arguments[0] + 3), laid=(SCRIPTED, _dgetdrv_scripted), steered=UNPOISONED),
    Case("AES_ROM_FPD_PARSE", CLOSED, why="a drive and no separator, a name and no extension",
         arguments=_with(0, da.BAND_AT), laid=_spec_laid("B:NAME")),
    Case("AES_ROM_FPD_PARSE", CLOSED, why="a name with two marks: the extension after the LAST",
         arguments=_with(0, da.BAND_AT), laid=_spec_laid("C:\\NAME.B.EXT")),
    Case("AES_ROM_FPD_PARSE", CLOSED, why="a drive byte above $7f: its word SIGN-extended (`ext.w`)",
         arguments=_with(0, da.BAND_AT), laid=_spec_laid("\xc1:NAME.EXT")),
    # (a '.' in the path and NONE in the name is no case: the name's copy runs from the last separator to that mark,
    # which lies behind it — on through memory, a ROM behaviour no spec the desk builds meets: each ends in "*.*")
    Case("AES_ROM_FPD_PARSE", CLOSED, why="a '.' in the path and one in the name: the extension from the name's, the last",
         arguments=_with(0, da.BAND_AT), laid=_spec_laid("C:\\DIR.X\\NAME.EXT")),
    # fpd_ofind: the file the object shows; and an object no file shows
    Case("AES_ROM_FPD_OFIND", SELECTED), Case("AES_ROM_FPD_OFIND", COPIED_INTO_THE_FOLDER),
    Case("AES_ROM_FPD_OFIND", SELECTED, why="an object no file of the list shows: 0 after the whole list", arguments=_with(1, 0)),
    Case("AES_ROM_FPD_OFIND", SELECTED, why="an object word whose low byte is the file's (0x0109): none — a WORD compare",
         arguments=_with(1, 0x0109)),
    Case("AES_ROM_FPD_ELIST", CLOSED, steered=UNPOISONED), Case("AES_ROM_FPD_ELIST", TO_THE_TRASH, steered=UNPOISONED),
    # (the chains' lists ask for the last node alone: the files machine's four, sorted, handed with their THIRD node the
    # stop — the walk ends at the second, whose link it is)
    Case("AES_ROM_FPD_ELIST", FILES_OPENED, over="AES_ROM_PN_SORT", why="a stop on the list: the node before it",
         arguments=lambda arrived: (arrived.arguments[1], _nth_node(arrived, arrived.arguments[1], 2)), steered=UNPOISONED),
    Case("AES_ROM_FN_FREE", FOLDER_OPENED, steered=UNPOISONED),
    Case("AES_ROM_FL_FREE", CLOSED, steered=UNPOISONED), Case("AES_ROM_FL_FREE", FOLDER_OPENED, steered=UNPOISONED),
    Case("AES_ROM_FL_FREE", OPEN_A, arm=lambda a: a == (0,), steered=UNPOISONED),       # (a new path's empty list: nothing)
    Case("AES_ROM_FN_ALLOC", OPEN_A, steered=UNPOISONED), Case("AES_ROM_FN_ALLOC", FILES_OPENED, 3, steered=UNPOISONED),
    Case("AES_ROM_FN_ALLOC", OPEN_A, why="none free: 0, nothing stored", arguments=(), steered=UNPOISONED,
         laid=("the free list's head 0", _head_laid(DESK_FILES_FREE))),
    Case("AES_ROM_PN_ALLOC", OPEN_A, steered=UNPOISONED), Case("AES_ROM_PN_ALLOC", FOLDER_OPENED, steered=UNPOISONED),
    Case("AES_ROM_PN_ALLOC", OPEN_A, why="none free: 0, nothing stored", arguments=(), steered=UNPOISONED,
         laid=("the free list's head 0", _head_laid(DESK_PATHS_FREE))),
    Case("AES_ROM_PN_ALLOC", OPEN_A, why="a free node whose flags word has a bit in each byte: cleared, a WORD",
         arguments=(), steered=UNPOISONED, laid=("the free node's flags $0101", _free_path_s_flags_laid)),
    Case("AES_ROM_PN_FREE", CLOSED, steered=UNPOISONED), Case("AES_ROM_PN_FREE", FOLDER_CLOSED, steered=UNPOISONED),
    Case("AES_ROM_PN_OPEN", OPEN_A, steered=UNPOISONED), Case("AES_ROM_PN_OPEN", FOLDER_OPENED, steered=UNPOISONED),
    Case("AES_ROM_PN_OPEN", FOLDER_OPENED, why="a path too long (a run of the ROM's text with no NUL): 0 — THE NODE LEFT OPEN",
         arguments=_with(1, lambda _arrived: _a_text_of_the_rom_s(LONGEST_PATH + 1)), steered=UNPOISONED),
    Case("AES_ROM_PN_OPEN", FOLDER_OPENED, why="an extension other than the name (the path's own text): each in its place",
         arguments=_with(3, lambda arrived: arrived.arguments[1]), steered=UNPOISONED),
    Case("AES_ROM_PN_OPEN", OPEN_A, why="no path node free: 0", steered=UNPOISONED, arguments=lambda arrived: arrived.arguments,
         laid=("the free list's head 0", _head_laid(DESK_PATHS_FREE))),
    Case("AES_ROM_PN_OPEN", OPEN_A, why="an attribute word with a bit in its high byte (every caller hands a byte's): stored a WORD",
         arguments=_with(4, lambda a: a.arguments[4] | ATTRIBUTE_HIGH_BYTE), steered=UNPOISONED),
    # pn_fcomp: by name (the chains' own key), by size (both ways), by date (equal dates: the times), by type
    Case("AES_ROM_PN_FCOMP", FILES_OPENED, arm=lambda a: a[2] == 0), Case("AES_ROM_PN_FCOMP", NOT_EMPTY),
    Case("AES_ROM_PN_FCOMP", BY_SIZE, 0, arm=lambda a: a[2] == SORT_BY_SIZE), Case("AES_ROM_PN_FCOMP", BY_SIZE, 2),
    Case("AES_ROM_PN_FCOMP", BY_DATE, arm=lambda a: a[2] == SORT_BY_DATE),
    Case("AES_ROM_PN_FCOMP", BY_TYPE, arm=lambda a: a[2] == SORT_BY_TYPE), Case("AES_ROM_PN_FCOMP", BY_TYPE, 2),
    Case("AES_ROM_PN_FCOMP", BY_SIZE, why="one file against itself by size: the sizes equal, then the names", arguments=_with(1, lambda a: a.arguments[0])),
    Case("AES_ROM_PN_FCOMP", BY_TYPE, why="one file against itself by type: the types equal, then the names", arguments=_with(1, lambda a: a.arguments[0])),
    # (a node one byte on reads the name one byte on: "ESKTOP.INF" — the same type as "DESKTOP.INF", another name)
    Case("AES_ROM_PN_FCOMP", BY_TYPE, why="two names of one type: the types equal, the names' order",
         arguments=_with(1, lambda a: a.arguments[0] + 1), arm=lambda a: a[2] == SORT_BY_TYPE),
    Case("AES_ROM_PN_FCOMP", BY_DATE, why="the second file a day later: the dates' difference", arguments=lambda a: a.arguments,
         laid=("the second file's date a day on", _date_on(1))),
    Case("AES_ROM_PN_FCOMP", BY_DATE, why="the second file three days later: the dates' difference itself, not its sign",
         arguments=lambda a: a.arguments, laid=("the second file's date three days on", _date_on(THREE_DAYS))),
    Case("AES_ROM_PN_FCOMP", BY_DATE, why="the second file's time past 16:00, its word over $8000: shifted UNSIGNED (`lsr`)",
         arguments=lambda a: a.arguments, laid=("the second file's time 16 hours on", _time_on(SIXTEEN_HOURS))),
    Case("AES_ROM_PN_FCOMP", BY_SIZE, why="the second file larger by its size's high word alone: a LONG compare",
         arguments=lambda a: a.arguments, laid=("the second file's size $10000", _size_laid(A_HIGH_WORD_ALONE))),
    Case("AES_ROM_PN_FCOMP", FILES_OPENED, why="a key no arm has (4): answered itself", arguments=_with(2, A_KEY_NO_ARM_HAS)),
    Case("AES_ROM_PN_FCOMP", BY_DATE, why="the second file's time later in its two-second field alone: equal (the field dropped)",
         arguments=lambda a: a.arguments, laid=("the second file's time 16 on", _time_on(TWO_SECOND_FIELD_BIT))),
    Case("AES_ROM_PN_FCOMP", BY_DATE, why="the second file's time a minute on: the times' difference",
         arguments=lambda a: a.arguments, laid=("the second file's time a minute on", _time_on(A_MINUTE))),
    Case("AES_ROM_PN_FCOMP", BY_SIZE, why="the second file's size a negative long: the smaller (SIGNED compares)",
         arguments=lambda a: a.arguments, laid=("the second file's size $80000000", _size_laid(0x80000000))),
    Case("AES_ROM_PN_COMP", FILES_OPENED), Case("AES_ROM_PN_COMP", NEW_FOLDER), Case("AES_ROM_PN_COMP", NOT_EMPTY),
    # (its second arrival compares two files, DESKTOP.INF and TESTPRG.PRG — the first its folder against a file)
    Case("AES_ROM_PN_COMP", FILES_OPENED, 1, why="a read-only file against a plain one: one kind (the folder bit alone), the names",
         arguments=lambda a: a.arguments, laid=("the first file read-only", _first_read_only)),
    # pn_sort: a list counted first (-1) and the counts its other callers hand
    Case("AES_ROM_PN_SORT", AS_TEXT, arm=lambda a: a[0] == 0xFFFF, steered=UNPOISONED),
    *(Case("AES_ROM_PN_SORT", chain, arm=lambda a, n=n: a[0] == n, steered=UNPOISONED)
      for chain, n in ((TO_THE_TRASH, 0), (OPEN_A, 1), (NEW_FOLDER, 2), (NOT_EMPTY, 3), (FILES_OPENED, 4))),
    Case("AES_ROM_PN_SORT", AS_TEXT, why="a count of -2: no list counted, nothing sorted, 0", arguments=_with(0, 0xFFFE), steered=UNPOISONED),
    Case("AES_ROM_PN_SORT", FILES_OPENED, why="two files of one name: left in their order (no swap of equals)",
         arguments=lambda a: a.arguments, steered=UNPOISONED, laid=("the third file's name the fourth's", _a_name_twice)),
)
BY_LABEL = da.by_label(CASES)
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]
A_CLASS = [name for name, each in BY_LABEL.items() if each.why]


def _hook_of(each):
    return {"hook": gd.scripted_hook} if each.laid and each.laid[0] == SCRIPTED else {}


@EVERY_CASE
def test_a_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over the arrival's megabyte — every byte, the answer at its
    width. At its own arrival, the answer is ALSO the one the ROM's run in place leaves its caller."""
    each = BY_LABEL[name]
    arrived = da.arrival_of(each)
    result = da.plain(arrived, *da.layers_of(each), **dict(each.steered or ()), **_hook_of(each))
    if each.why or df.SIGNATURES[each.name][0] is None:
        return
    back = da.returned_in_place(arrived)
    assert da.answered_at_its_width(each.name, result.long_answer()) == da.answered_at_its_width(each.name, back.registers["d0"])


ARRIVALS, CLASSES = 44, 33


def test_every_routine_has_a_case_at_an_arrival_of_its_own():
    """Sixteen routines, each with cases at its own arrivals; the classes by name."""
    assert {BY_LABEL[name].name for name in AT_ITS_OWN_ARRIVAL} == set(df.UNIT_G)
    assert (len(AT_ITS_OWN_ARRIVAL), len(A_CLASS)) == (ARRIVALS, CLASSES)


# ---- D0 AT RETURN -----------------------------------------------------------------------------------------------------------------
VOID = [name for name, (restype, _frame) in df.SIGNATURES.items() if restype is None]


def test_no_caller_in_the_rom_reads_what_a_void_routine_leaves_in_d0():
    """BY READING THE CALLERS (`aes_deskbind.answer_readers`): the D0 the ROM's void routines leave is read nowhere —
    the C's having none is a counted divergence (below), not a difference a caller sees. Every answering routine's
    answer IS read (each caller's own reading, word or long)."""
    assert {name: db.answer_readers(da.entry_of(name)) for name in VOID} == {name: set() for name in VOID}
    assert all(db.answer_readers(da.entry_of(name)) for name in df.UNIT_G if name not in VOID)


NO_WORD_IN_C = 20


def test_the_cases_whose_d0_the_c_does_not_have_are_counted():
    """THE COUNT: the cases of void routines — the ROM's D0 there a leftover the C has no word for."""
    assert Counter(BY_LABEL[name].name in VOID for name in BY_LABEL)[True] == NO_WORD_IN_C


# ---- THE ARMS THE CASES WERE CHOSEN FOR, read off their machines --------------------------------------------------------------
def test_the_sort_chains_hand_pn_fcomp_their_own_keys_and_the_spec_s_arms_are_the_texts_their_names_say():
    """The three sort chains reach pn_fcomp with the key their item names; and fpd_bldspec's arrivals build "A:\\*.*"
    (a drive's window: no path; a file shown) and "A:\\A\\*.*" (a folder's)."""
    keys = {chain: da.arrival("AES_ROM_PN_FCOMP", chain).arguments[2] for chain in (BY_SIZE, BY_DATE, BY_TYPE)}
    assert keys == {BY_SIZE: SORT_BY_SIZE, BY_DATE: SORT_BY_DATE, BY_TYPE: SORT_BY_TYPE}

    def built(chain):
        arrived = da.arrival("AES_ROM_FPD_BLDSPEC", chain)
        spec = arrived.arguments[4] & BUS
        back = da.returned_in_place(arrived)
        return bytes(back.ram[spec:spec + SPEC_BYTES]).split(b"\0")[0]
    assert [built(chain) for chain in (OPEN_A, SHOWN, FOLDER_OPENED)] == [b"A:\\*.*", b"A:\\*.*", b"A:\\A\\*.*"]


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------------
def test_no_function_of_a_blob_outside_the_unit_refers_to_one_of_its_routines(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every core of the unit
    linked; and no function outside the unbound desk (the held cores and what only they reach) refers to ANY held core."""
    assert not db.bound_referrers(blob, df.UNIT_G)


def test_the_table_s_entries_for_the_unit_stay_the_rom_s_and_no_registry_names_one():
    verdicts, linef_table = da.table_verdicts(df.UNIT_G)
    assert verdicts == {name: linef_table.THE_ROM_S for name in df.UNIT_G}
    assert set(df.UNIT_G) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    assert not da.registered(df.UNIT_G)


# ---- band 6 wave 2, group G2 (unit G): pn_close `$fdfa20`, pn_active `$fdfc3c` ---------------------------------------------------
# pn_active SEARCHES THE DISK: every case of it runs over GEMDOS REPLAYED (`aes_deskfpd.gemdos_script`: the ROM's own run in
# place's answers and DTAs, `aes_fslib`'s replay on both shores — in the id), unpoisoned as the list routines are. A
# drive's spec is all the chains hand it ("A:\..."): the cartridge's arm ('c', unit M's search) and a file pool spent
# are labelled classes, and a name the disk does not hold (".AB": begins with '.' and goes on) a class whose replay's
# answer says it.
CLOSE, ACTIVE = "AES_ROM_PN_CLOSE", "AES_ROM_PN_ACTIVE"
NONE_LEFT = "file: dragged to the trash, OK"                # A:'s one file deleted: the search finds none (EFILNF)
REPLAYED_STEERED = (*UNPOISONED, ("hook", df.replay_hook))
REPLAYED = df.replay_laid()
PNODE_SPEC, DOS_AX_NO_FILE_NODES = FPD["PNODE_SPEC"], FPD["DOS_AX_NO_FILE_NODES"]
# THE CARTRIDGE'S DRIVE AS THE ROM COMPARES IT — the immediate of pn_active's `cmpi.b #99,8(a5)` at `$fdfc48`, read off
# the ROM, not the C's header (a header mutated would lay its own wrong letter: the fix pass's RB12)
PN_ACTIVE_CARTRIDGE_COMPARE = 0xfdfc48
CARTRIDGE_DRIVE = case.word_in(BASE_IMAGE, PN_ACTIVE_CARTRIDGE_COMPARE + aes.WORD_BYTES) & 0xff
DTA_NAME = 30                           # a DTA's found name (`desk/deskleaf.h` DTA_NAME)


def _cartridge_s_spec(arrived):
    """LAID: the path's spec drive 'c' — the cartridge's (no GEMDOS call follows: nothing replayed)."""
    return {(arrived.arguments[0] & BUS) + PNODE_SPEC: bytes((CARTRIDGE_DRIVE,))}


def _no_file_node_free(arrived):
    """LAID: the free file list's head 0 — over the replay of the arrival's own search (its first two calls are made)."""
    return case.merge_pokes(REPLAYED[1](arrived), _head_laid(DESK_FILES_FREE)(arrived))


def _first_found_renamed(arrived):
    """The arrival's script, its first search's DTA naming ".AB" in place of "." (a name of the class `.` + more)."""
    script = list(df.gemdos_script(arrived))
    first = next(at for at, (d0, dta) in enumerate(script) if not d0 and dta[DTA_NAME:DTA_NAME + 2] == b".\0")
    d0, dta = script[first]
    script[first] = (d0, dta[:DTA_NAME] + b".AB\0" + dta[DTA_NAME + 4:])
    return tuple(script)


TWELVE = b"ABCDEFGH.TXT"                 # an 8.3 name of twelve bytes: its NUL is the last byte pn_active copies
STALE_NAME = b"X" * 14                  # a node's name bytes as a longer name left them


def _first_found_named_twelve(arrived):
    """The arrival's script, its first search's DTA naming a full 8.3 name (the disk holds none of twelve bytes)."""
    script = list(df.gemdos_script(arrived))
    first = next(at for at, (d0, _dta) in enumerate(script) if at and not d0)
    d0, dta = script[first]
    script[first] = (d0, dta[:DTA_NAME] + TWELVE + b"\0" + dta[DTA_NAME + len(TWELVE) + 1:])
    return tuple(script)


def _twelve_over_stale_nodes(arrived):
    """...replayed, and the node the first entry is taken into — the old list's head, which fl_free puts first, or the
    free list's head — its name bytes LAID stale (a name of fourteen bytes): the copy's last byte, the NUL, is seen."""
    ram, path = arrived.boot.ram, arrived.arguments[0] & BUS
    heads = {case.long_in(ram, path + FPD["PNODE_FLIST"]), case.long_in(ram, _desk(arrived) + DESK_FILES_FREE)} - {0}
    return case.merge_pokes(df.replay_laid(_first_found_named_twelve)[1](arrived),
                            *({(node & BUS) + FNODE_NAME: STALE_NAME} for node in heads))


def _attributes_with_a_high_byte(arrived):
    """...replayed, the path's attribute word LAID with a bit in its high byte (every caller hands pn_open a byte's)."""
    at = (arrived.arguments[0] & BUS) + FPD["PNODE_ATTR"]
    word = case.word_in(arrived.boot.ram, at) | ATTRIBUTE_HIGH_BYTE
    return case.merge_pokes(REPLAYED[1](arrived), {at: struct.pack(">H", word)})


def test_the_header_s_cartridge_drive_is_the_rom_s():
    assert FPD["CARTRIDGE_DRIVE"] == CARTRIDGE_DRIVE


CASES_WAVE_2 = (
    Case(CLOSE, CLOSED, steered=UNPOISONED), Case(CLOSE, FOLDER_CLOSED, steered=UNPOISONED),
    # pn_active: one file, four (a folder among them, sorted), a folder's "." and ".." (not listed: its node left over
    # and freed), and none (Fsfirst's EFILNF)
    *(Case(ACTIVE, chain, laid=REPLAYED, steered=REPLAYED_STEERED) for chain in (OPEN_A, FILES_OPENED, FOLDER_OPENED, NONE_LEFT)),
    Case(ACTIVE, OPEN_A, why="the spec's drive 'c', the cartridge's (no machine of ours opens one): unit M's search, none",
         arguments=lambda a: a.arguments, laid=("the path's spec drive 'c'", _cartridge_s_spec), steered=UNPOISONED),
    Case(ACTIVE, FILES_OPENED, why="no file node free: the search ends at its first entry, AES_DOS_AX 100",
         arguments=lambda a: a.arguments, laid=(f"{df.REPLAYED}; the free file list's head 0", _no_file_node_free),
         steered=REPLAYED_STEERED),
    Case(ACTIVE, FOLDER_OPENED, why="a name '.AB' (a '.' and more): listed",
         arguments=lambda a: a.arguments, laid=df.replay_laid(_first_found_renamed, f"{df.REPLAYED}, the first found named '.AB'"),
         steered=REPLAYED_STEERED),
    Case(ACTIVE, OPEN_A, why="an attribute word with a bit in its high byte: handed Fsfirst a WORD",
         arguments=lambda a: a.arguments, laid=(f"{df.REPLAYED}; the path's attributes $01xx", _attributes_with_a_high_byte),
         steered=REPLAYED_STEERED),
    Case(ACTIVE, FILES_OPENED, why="a full 8.3 name (twelve bytes) into a node of stale name bytes: its NUL copied",
         arguments=lambda a: a.arguments, laid=(f"{df.REPLAYED}, the first found named {TWELVE.decode()}; its node's name "
                                                f"bytes stale", _twelve_over_stale_nodes), steered=REPLAYED_STEERED),
)
BY_LABEL_WAVE_2 = da.by_label(CASES_WAVE_2)


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over the arrival's megabyte — every byte, the answer at its width;
    at its own arrival the answer ALSO the one the ROM's run in place leaves its caller (pn_active's AES_DOS_AX)."""
    each = BY_LABEL_WAVE_2[name]
    arrived = da.arrival_of(each)
    result = da.plain(arrived, *da.layers_of(each), **dict(each.steered or ()))
    if each.why or df.SIGNATURES_WAVE_2[each.name][0] is None:
        return
    back = da.returned_in_place(arrived)
    assert da.answered_at_its_width(each.name, result.long_answer()) == da.answered_at_its_width(each.name, back.registers["d0"])


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 6, 5


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES_WAVE_2 if not each.why]
    assert {each.name for each in at_its_own} == set(df.UNIT_G_WAVE_2)
    assert (len(at_its_own), len(CASES_WAVE_2) - len(at_its_own)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)


def test_the_arrivals_are_the_arms_their_comments_say():
    """pn_active's four arrivals: the files each search finds (".": its first's name) and its last answer — the
    disk's, read off the replay's script, not by a chain's name."""
    def found(chain):
        script = df.gemdos_script(da.arrival(ACTIVE, chain))
        return [dta[DTA_NAME:].split(b"\0")[0] for d0, dta in script[1:] if not d0]       # past Fsetdta
    assert {chain: found(chain) for chain in (OPEN_A, FILES_OPENED, FOLDER_OPENED, NONE_LEFT)} == {
        OPEN_A: [b"DESKTOP.INF"], FILES_OPENED: [b"AUTO", b"DESKTOP.INF", b"README.TXT", b"TESTPRG.PRG"],
        FOLDER_OPENED: [b".", b".."], NONE_LEFT: []}


def test_pn_close_s_d0_is_read_by_no_caller_and_pn_active_s_by_its_callers():
    """D0: pn_close is void (its D0 pn_free's leftover, the C none — a NAMED, COUNTED divergence: its two cases), read
    by no instruction of the ROM; pn_active's word answer read by its callers (`aes_deskbind.answer_readers`)."""
    assert not db.answer_readers(da.entry_of(CLOSE))
    assert db.answer_readers(da.entry_of(ACTIVE))
    assert sum(each.name == CLOSE for each in CASES_WAVE_2) == 2


def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_a_wave_2_routine(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`) asked of the unit's wave-2 routines."""
    assert not db.bound_referrers(blob, df.UNIT_G_WAVE_2)


def test_the_table_s_entries_for_the_wave_2_routines_stay_the_rom_s_and_no_registry_names_one():
    verdicts, linef_table = da.table_verdicts(df.UNIT_G_WAVE_2)
    assert verdicts == {name: linef_table.THE_ROM_S for name in df.UNIT_G_WAVE_2}
    assert set(df.UNIT_G_WAVE_2) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    assert not da.registered(df.UNIT_G_WAVE_2)
