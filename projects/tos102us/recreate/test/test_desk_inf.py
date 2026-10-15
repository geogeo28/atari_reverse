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

import aes
import aes_deskarrive as da
from aes_desk import EMPTIED_INFO
import aes_deskbind as db
import aes_deskdir as cdir
import aes_deskinf as inf
import case

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


# ==== BAND 6 WAVE 2, group G1: inf_folder `$fde9ce` ==================================================================
# AT ITS ARRIVALS — Show Info of drive A: and of a folder, both through the File menu's Show Info word ($fe1ec2) — its
# count walk's GEMDOS REPLAYED from the ROM's own run in place (`aes_deskdir.in_place`, `REPLAYED` in the id). It
# reaches no binding (the walk has no tree): the plain differential.
INF_FOLDER = inf.INF_FOLDER
FOLDER_CASES = {f"{INF_FOLDER} — arrival 0 of {chain} [{cdir.REPLAYED}]": chain for chain in (DRIVE_INFO, FOLDER_INFO, EMPTIED_INFO)}


def folder_counted(arrived, replay):
    """The plain differential over the arrival, GEMDOS replayed: the image the C left."""
    pokes = case.merge_pokes(da.machine_of(arrived), cdir.replayed(replay))
    return aes.run_function(INF_FOLDER, arrived.arguments, pokes, hook=cdir.engine_hook, poison=False).final


@pytest.mark.parametrize("name", FOLDER_CASES)
def test_inf_folder_from_its_arrival_with_gemdos_replayed_is_the_rom_s(name):
    """THE CASE: the counts walked and set into the dialog's two fields, D0 at its width — the calls the ROM's own."""
    arrived = da.arrival(INF_FOLDER, FOLDER_CASES[name])
    replay = cdir.in_place(arrived)
    image = folder_counted(arrived, replay)
    assert tuple(function for function, _frame in cdir.engine_calls(image)) == replay.functions


# The walk's failure: no chain's GEMDOS fails a search of a folder Show Info is asked of (the model's disk answers
# every read). AN ARGUMENT CLASS, SCRIPTED: Fsfirst answering ERROR (-1, above -32: d_errmsg shows no alert) — the walk
# stops at once (asking its search once more: the ROM's), and inf_folder answers 0 with its fields untouched.
GEMDOS_ERROR = -1


def test_inf_folder_an_argument_class_the_walk_failing_answers_0_scripted():
    arrived = da.arrival(INF_FOLDER, FOLDER_INFO)
    replay = cdir.in_place(arrived)
    dta = replay.fills[0]
    failed = replay._replace(answers=(0, GEMDOS_ERROR & aes.LONG_MASK, GEMDOS_ERROR & aes.LONG_MASK), fills=(dta, dta),
                             functions=(cdir.FSETDTA, cdir.FSFIRST, cdir.FSNEXT))
    image = folder_counted(arrived, failed)
    assert tuple(function for function, _frame in cdir.engine_calls(image)) == failed.functions


# THE TALLIES CLEARED FIRST: Show Info of drive A: once its one file is deleted (the fix pass's EMPTIED_INFO, a case
# above) arrives with the delete's count left in them — g_nfiles 1, g_size the file's — and over an empty root.
def test_inf_folder_s_emptied_arrival_finds_the_tallies_stale():
    arrived = da.arrival(INF_FOLDER, EMPTIED_INFO)
    desk = case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & db.BUS
    stale = [case.long_in(arrived.boot.ram, desk + db.DESK_GLOBALS[name]) for name in ("DESK_G_NFILES", "DESK_G_SIZE")]
    assert all(stale), stale


def test_inf_folder_is_linked_and_unbound(blob):
    da.unbound(blob, inf.UNIT_F_WAVE_2)


def test_inf_folder_s_answer_is_held_at_the_word_and_read_by_its_two_callers():
    assert da.vdi.ALCYON[INF_FOLDER].restype is aes.WORD_ANSWER
    assert len(db.answer_readers(da.entry_of(INF_FOLDER))) == 2 and len(FOLDER_CASES) == 3
