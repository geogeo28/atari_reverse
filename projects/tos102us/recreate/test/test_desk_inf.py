"""AN INFO DIALOG'S FIELDS (`src/desk/deskinf.c`; band 6 wave 1b, group G4, unit F): inf_field `$fdea5e` and inf_dttmsz
`$fdea9a`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`) of a Show Info — a drive's, a file's, a folder's, the
    program's: a name (fmt_str) and a number (merge_str's "%L") into fields, and a file's date, time and size. Never a
    poke; no arm wants a class.
  * NEITHER YIELDS: each case is the kit's plain differential over the arrival's megabyte.
  * D0 AT RETURN: both are `void` in C and the ROM leaves inf_sset's leftover: A NAMED, COUNTED DIVERGENCE, read by no
    instruction of the ROM (`aes_deskbind.answer_readers`).
"""
import pytest

import aes_deskarrive as da
import aes_deskbind as db
import aes_deskinf as inf

DRIVE_INFO, FILE_INFO = "A: File > Show Info, Return", "file: File > Show Info, Return"
FOLDER_INFO, PROGRAM_INFO = "folder: selected, File > Show Info, Return", "files: the program selected, File > Show Info, Return"
A_NUMBER, A_NAME = 0, 1                 # inf_field's last argument
A_NAME_IN_THE_HIGH_BYTE = 0x0100


def Case(*fields, **named):
    """A case of the unit: none yields."""
    return da.Case(*fields, yields=False, **named)


CASES = (
    # inf_field: the drive's numbers (its bytes used, free; its folders and files), a file's name and its size, a folder's name
    Case(inf.INF_FIELD, DRIVE_INFO, 0, arm=lambda a: a[4] == A_NUMBER), Case(inf.INF_FIELD, DRIVE_INFO, 3),
    Case(inf.INF_FIELD, FILE_INFO, 0, arm=lambda a: a[4] == A_NAME), Case(inf.INF_FIELD, FILE_INFO, 1, arm=lambda a: a[4] == A_NUMBER),
    Case(inf.INF_FIELD, FOLDER_INFO, 2, arm=lambda a: a[4] == A_NAME), Case(inf.INF_FIELD, PROGRAM_INFO, 0),
    Case(inf.INF_FIELD, FILE_INFO, 0, arguments=lambda a: (*a.arguments[:4], A_NAME_IN_THE_HIGH_BYTE),
         why="is_name $0100: a name by the WORD (`tst.w`), its low byte 0 — every caller hands 0 or 1"),
    # inf_dttmsz: a file's, a folder's (its size the walk's total), the program's
    Case(inf.INF_DTTMSZ, FILE_INFO), Case(inf.INF_DTTMSZ, FOLDER_INFO), Case(inf.INF_DTTMSZ, PROGRAM_INFO),
)
BY_LABEL = da.by_label(CASES)


@pytest.mark.parametrize("name", BY_LABEL)
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over the arrival's megabyte — the texts made and set into the
    tree's objects."""
    da.tier_1(BY_LABEL[name], answered=False)


ARRIVALS, CLASSES = 9, 1


def test_every_routine_of_the_unit_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES if not each.why]
    assert {each.name for each in at_its_own} == set(inf.UNIT_F)
    assert (len(at_its_own), len(CASES) - len(at_its_own)) == (ARRIVALS, CLASSES)


def test_the_answers_the_c_has_not_are_counted_and_read_by_no_caller():
    """THE DIVERGENCE, NAMED AND COUNTED: every case — inf_sset's word the ROM leaves, none in C — and no instruction of
    the ROM reads the D0 of either routine."""
    assert all(da.vdi.ALCYON[name].restype is None for name in inf.UNIT_F) and len(CASES) == ARRIVALS + CLASSES
    assert {name: db.answer_readers(da.entry_of(name)) for name in inf.UNIT_F} == {name: set() for name in inf.UNIT_F}


def test_the_unit_is_linked_and_unbound(blob):
    da.unbound(blob, inf.UNIT_F)
