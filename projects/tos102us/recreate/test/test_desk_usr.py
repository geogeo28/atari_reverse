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
import aes_gsx



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


# ==== BAND 6 WAVE 2, group G1: dr_code `$fde7b4` and the userdef draw `$fde844` =======================================
# AT THEIR ARRIVALS — a window's lines drawn as text (the files disk's, the INF disk's, a selected line's: the chain this
# group added, "the long file's line clicked") — over the plain differential, the VDI's door bound (`aes_gsx.vdi_hook`:
# gsx_attr, bb_fill and gsx_tblt reach the VDI by `trap #2`). Neither yields. The userdef draw runs on the desk's userdef
# stack (its arrivals' own SP); called by value (ub_trampoline), it has no Line-F word (R-W2-4).
# TRIED, AND NO ARRIVAL: dr_code's INVERTING arm (a SELECTED bit that changed): a clicked line is drawn again WHOLE
# ($41 -> $41, the chain above) — the desk redraws a selection by objc_draw, never objc_change's userdef call. A
# LABELLED ARGUMENT CLASS, the bit flipped in `previous_state` over a line's arrival.
DR_CODE, USERDEF = usr.DR_CODE, usr.USERDEF
TEXT_VIEW_OPENED, TEXT_VIEW_SAVED = "text view: A: opened", "text view: Options > Save Desktop, Return"
LINE_CLICKED = "files: View > Show as Text, the long file's line clicked"
PREVIOUS_STATE = 2                      # dr_code's third argument
SELECTED = 1


def _changed(bit):
    def arguments_of(arrived):
        arguments = list(arrived.arguments)
        arguments[PREVIOUS_STATE] ^= bit
        return tuple(arguments)
    return arguments_of


CROSSED = 2                             # another state bit of the word's low byte than SELECTED


WAVE_2_CASES = (
    *(Case(name, chain) for name in (DR_CODE, USERDEF) for chain in (AS_TEXT, TEXT_VIEW_OPENED, TEXT_VIEW_SAVED, FILES_AS_TEXT,
                                                                     LINE_CLICKED)),
    Case(DR_CODE, FILES_AS_TEXT, 1), Case(USERDEF, FILES_AS_TEXT, 1),    # the folder's line: its glyph
    Case(DR_CODE, LINE_CLICKED, arguments=_changed(SELECTED),
         why="the SELECTED bit changed (no chain's desk changes a line's state but by drawing it whole): the line inverted"),
    Case(DR_CODE, LINE_CLICKED, arguments=_changed(CROSSED),
         why="a state bit OTHER than SELECTED changed: the line drawn whole, the CURRENT state answered"),
)
WAVE_2_BY_LABEL = da.by_label(WAVE_2_CASES)


@pytest.mark.parametrize("name", WAVE_2_BY_LABEL)
def test_a_line_of_the_text_view_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over the arrival's megabyte — the VDI's calls, the clip, the
    line's text — its answer (the state) at the word."""
    da.tier_1(WAVE_2_BY_LABEL[name], hook=aes_gsx.vdi_hook)


def test_the_arrivals_draw_whole_lines_and_the_clicked_one_selected():
    """The arms the arrivals take: every line drawn whole (no SELECTED bit changed), the clicked one in its selected
    state."""
    states = {chain: da.arrival(DR_CODE, chain).arguments[2:4] for chain in (AS_TEXT, LINE_CLICKED)}
    assert all(previous == current for previous, current in states.values())
    assert states[LINE_CLICKED][1] & SELECTED and not states[AS_TEXT][1] & SELECTED


def test_the_text_view_s_draw_is_linked_and_unbound(blob):
    da.unbound(blob, usr.UNIT_E_WAVE_2)


WAVE_2_ARRIVALS, WAVE_2_CLASSES = 12, 2


def test_every_line_routine_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in WAVE_2_CASES if not each.why]
    assert {each.name for each in at_its_own} == set(usr.UNIT_E_WAVE_2)
    assert (len(at_its_own), len(WAVE_2_CASES) - len(at_its_own)) == (WAVE_2_ARRIVALS, WAVE_2_CLASSES)


def test_the_line_s_answers_are_held_at_the_word():
    """dr_code's answer (the state) read by its one caller; the userdef draw's by no Line-F site — it is called by
    value, and ub_trampoline hands it back to ob_user: compared at the word on every case all the same."""
    assert all(da.vdi.ALCYON[name].restype is usr.aes.WORD_ANSWER for name in usr.UNIT_E_WAVE_2)
    assert {name: len(db.answer_readers(da.entry_of(name))) for name in usr.UNIT_E_WAVE_2} == {DR_CODE: 1, USERDEF: 0}
