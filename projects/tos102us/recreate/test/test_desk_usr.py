"""THE TEXT VIEW'S LINE AND ITS FORMATTERS (`src/desk/deskusr.c`; band 6 wave 1b, group G4, unit E): my_itoa `$fde500`,
fmt_time `$fde546`, fmt_date `$fde5ba` and ob_sfcb `$fde610`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND
NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`) — the text view drawing its lines, Show Info's date and time —
    or A LABELLED ARGUMENT CLASS, said in its name, where no chain's file has the arm: an hour of the afternoon, noon,
    a year past 1999, a number the compare tells apart signed from unsigned. Never a poke.
  * NONE YIELDS: each case is the kit's plain differential over the arrival's megabyte.
  * D0 AT RETURN: fmt_time's and ob_sfcb's answers held at the longword. my_itoa and fmt_date are `void` in C and the
    ROM leaves merge_str's (my_itoa's) leftover: A NAMED, COUNTED DIVERGENCE, read by no instruction of the ROM
    (`aes_deskbind.answer_readers`; ob_sfcb's answer is read by none either, and held all the same).
  * UNPINNED BY NAME: ob_sfcb on a screen WIDER than 320 pixels (every machine of the hands boots low resolution, and the
    width is the machine's, not an argument: the wide line's extra blanks and its two later columns — the sweep's E14
    survives so), and a size of more than eight digits (the blank count's word runs round; no file on a floppy).
"""
import pytest

import aes_deskarrive as da
import aes_deskbind as db
import aes_deskusr as usr



def Case(*fields, **named):
    """A case of the unit: none yields."""
    return da.Case(*fields, yields=False, **named)


AS_TEXT, FILE_INFO = "window: View > Show as Text", "file: File > Show Info, Return"
FOLDER_INFO, FILES_AS_TEXT = "folder: selected, File > Show Info, Return", "files: View > Show as Text"
ONE_DIGIT_MOST = 9
TWO_SIXTY_ONE = 0x0105                  # above ONE_DIGIT_MOST as a word, at or under it in its low byte
HOUR_SHIFT, MINUTE_SHIFT, YEAR_SHIFT, MONTH_SHIFT = 11, 5, 9, 5      # a DOS time's and a DOS date's fields


def _time(hours, minutes):
    return lambda arrived: (hours << HOUR_SHIFT | minutes << MINUTE_SHIFT, arrived.arguments[1])


def _date(years_from_1980, month, day):
    return lambda arrived: (years_from_1980 << YEAR_SHIFT | month << MONTH_SHIFT | day, arrived.arguments[1])


CASES = (
    # my_itoa: a month (1: a leading 0), a year (89: two digits), an hour (12)
    Case(usr.MY_ITOA, AS_TEXT, 0, arm=lambda a: a[0] <= ONE_DIGIT_MOST), Case(usr.MY_ITOA, AS_TEXT, 2, arm=lambda a: a[0] > ONE_DIGIT_MOST),
    Case(usr.MY_ITOA, FILE_INFO, 3), Case(usr.MY_ITOA, FOLDER_INFO, 1),
    Case(usr.MY_ITOA, AS_TEXT, arguments=lambda arrived: (0xFFFF, arrived.arguments[1]),
         why="the number $ffff: above 9 unsigned (`bls`), -1 signed — no file's field has it"),
    Case(usr.MY_ITOA, AS_TEXT, arguments=lambda arrived: (TWO_SIXTY_ONE, arrived.arguments[1]),
         why="the number $0105: above 9 as a WORD, its low byte 5 — no file's field has it"),
    # fmt_time: the files' hour 0 (twelve, the morning)
    Case(usr.FMT_TIME, AS_TEXT), Case(usr.FMT_TIME, FILE_INFO), Case(usr.FMT_TIME, FOLDER_INFO),
    Case(usr.FMT_TIME, AS_TEXT, arguments=_time(9, 47), why="9:47 — an hour of the morning that is not 0"),
    Case(usr.FMT_TIME, AS_TEXT, arguments=_time(12, 5), why="12:05 — noon: the afternoon, nothing taken off"),
    Case(usr.FMT_TIME, AS_TEXT, arguments=_time(23, 59), why="23:59 — an hour of the afternoon past noon: twelve taken off"),
    # fmt_date: 1-1-89 (the disk's files), 4-22-87 (a folder made in the session)
    Case(usr.FMT_DATE, AS_TEXT), Case(usr.FMT_DATE, FOLDER_INFO),
    Case(usr.FMT_DATE, AS_TEXT, arguments=_date(27, 11, 30), why="11-30-07 — a year past 1999: the century taken off"),
    Case(usr.FMT_DATE, AS_TEXT, arguments=_date(127, 12, 31), why="12-31-07 of 2107 — the year field's last value"),
    # ob_sfcb: the INF machine's one file; the files machine's folder (its first line) and three files
    Case(usr.OB_SFCB, AS_TEXT), Case(usr.OB_SFCB, FILES_AS_TEXT, 0), Case(usr.OB_SFCB, FILES_AS_TEXT, 1),
    Case(usr.OB_SFCB, FILES_AS_TEXT, 2), Case(usr.OB_SFCB, FILES_AS_TEXT, 3),
)
BY_LABEL = da.by_label(CASES)
VOID = (usr.MY_ITOA, usr.FMT_DATE)


@pytest.mark.parametrize("name", BY_LABEL)
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over the arrival's megabyte — the bytes it lays, its answer at
    its width where the C has one."""
    each = BY_LABEL[name]
    da.tier_1(each, answered=each.name not in VOID)


ARRIVALS, CLASSES = 14, 7


def test_every_routine_of_the_unit_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES if not each.why]
    assert {each.name for each in at_its_own} == set(usr.UNIT_E)
    assert (len(at_its_own), len(CASES) - len(at_its_own)) == (ARRIVALS, CLASSES)


NO_WORD_IN_C = 10


def test_the_answers_the_c_has_not_are_counted_and_read_by_no_caller():
    """THE DIVERGENCE, NAMED AND COUNTED: the cases of my_itoa and fmt_date, whose ROM routine leaves merge_str's word
    and whose C answers nothing — and no instruction of the ROM reads the D0 of any routine of the unit."""
    assert sum(1 for each in CASES if each.name in VOID) == NO_WORD_IN_C
    assert {name: db.answer_readers(da.entry_of(name)) for name in usr.UNIT_E} == {name: set() for name in usr.UNIT_E}


def test_the_unit_is_linked_and_unbound(blob):
    da.unbound(blob, usr.UNIT_E)
