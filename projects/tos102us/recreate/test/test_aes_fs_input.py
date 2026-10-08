r"""fs_input ($fe7d90) — THE FILE SELECTOR RUN WHOLE (`src/aes/fslib.c`), over sessions a user drives
(`test/aes_fs_sessions.py`): every interrupt delivered by the ROM's own ISRs at the selector's waits, on both shores.

    fs_input(path, selection, &button)
        dos_alloc 1600 / 400 / 256 -> the names, the index, the DTA (a refusal: those before freed, 0 answered)
        fs_sset: the title " *.* ", the path, the selection formatted (fmt_str); gsx_sclip(gl_rfs); fm_dial(START);
        the last path read forgotten; ob_draw(root, depth 1)
        each pass:  fm_do(tree, the selection field) — skipped while a directory is to be read
                    gsx_mxmy; the path field copied to the working path ($b89a); not the path last read ($bb3e):
                        the row and an OK / Cancel put down, fs_pspec, GEMDOS's spec "*.*", fs_newdir; top := 0
                    the object (its double-click bit apart), by the table $fefab0:
                         4 the close box   the working path cut to the folder above; read again
                         5 the title       read again
                         6, 7              nothing
                         8, 9 the arrows   one row
                        10 the track       a page, the side of the elevator the mouse is on
                        11 the elevator    fm_own, gr_slidebox, fm_own: the rows it was dragged by
                        12..20 a row       selected; a file: the selection (double-clicked: done); a folder:
                                           into the working path, read again
                        21, 22             done
                    read again: the working path into its field; the selection field redrawn (done: OK SELECTED);
                    the list scrolled (fs_nscroll)
        the path field -> path; the selection unformatted -> selection; fm_dial(FINISH); *button = inf_what (-1: 0);
        dos_free the DTA, the index, the names; 1

GEMDOS under a session is REPLAYED, its script derived from the ROM's own run of the same session over the staged disk
(`aes_fslib.session_script`); each session's replayed run is held here to that real-disk run where the selector can
see it. REAL GEMDOS on both shores serves the sessions one run can make: the keys typed ahead, and the three arms
where GEMDOS has no memory — its arena exhausted by the ROM's own Malloc.
"""
import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_fs_sessions as ss
import aes_fslib as fsl
import aes_objdraw as od
import aes_strings
import case
import test_aes_fmdo as fmdo
import vdi
from aes_fs_sessions import (A_C_ROW, AB_TXT_ROW, AUTO_ROW, BACKSPACE, CANCEL, CLOSER, DOWN_ARROW, EMPTY_ROW, ESCAPE, INSIDE, LONG,
                             LONGER, MIDDLE, MIXED, OK, ONE, RETURN, ROOT_PATH, SHORT, SHUFFLED, SLIDER, TAB, TITLE, TOOLS_ROW,
                             UP, UP_ARROW, Places, Session, at, click, folder, press, release, schedule, twice, typed)
from case import merge_pokes

# The cases of ONE session are collected back to back (`test/conftest.py`): the two tests below that every session of
# SESSIONS goes through share its derivation and its child, on the worker that made them.
pytestmark = pytest.mark.collected_with(by=lambda params: params.get("name") if params.get("name") in SESSIONS else None)
FS = fsl.FS
INPUT, ARGUMENTS = fsl.INPUT, fsl.ARGUMENTS
PATH_AT, FILE_AT, BUTTON_AT = fsl.PATH_AT, fsl.FILE_AT, fsl.BUTTON_AT
DONE, NO_MEMORY = FS["FS_INPUT_DONE"], FS["FS_INPUT_NO_MEMORY"]
# The button word fs_input answers through is inf_what's: which of its two buttons is SELECTED, counted from 1 — OK,
# its first — or Cancel's 0 (the header's, which the C stores for inf_what's "neither").
OK_BUTTON = 1
CANCEL_BUTTON = FS["FS_CANCELLED"]
TOOLS = folder("MIXED\\TOOLS")
TXT_SPEC = folder("MIXED", "*.TXT")

NO_DRIVE_ROOT = "\\*.*"
HUNDRED, BIG = folder("HUNDRED"), folder("BIG")

# ---- where the slider's parts are -------------------------------------------------------------------------------------
TRACK_HEIGHT = aes.read_object(BASE_IMAGE, fsl.SELECTOR, SLIDER)["HEIGHT"]


def low_in_the_track(places):
    """Near the track's foot: below the elevator wherever it stands short of the list's end."""
    return places.track(TRACK_HEIGHT - INSIDE)


def high_in_the_track(places):
    """At the track's head: above the elevator once the list has left its top."""
    return places.track(INSIDE - 1)


# Where SHUFFLED's elevator stands after one page down: its 28 names give it 9/28 of the track (18 of 56 pixels), and
# top 9 of the 19 it can scroll by puts it 9/19 of the 38 pixels it travels down — 18.
ELEVATOR_AFTER_A_PAGE = 18


def beside_the_elevator_s_top_after_a_page(places):
    """The track's left edge on the pixel row the elevator's top is on, one page down SHUFFLED."""
    x, y = places.corner(SLIDER)
    return x, y + ELEVATOR_AFTER_A_PAGE


# HOW FAR THE ELEVATOR IS DRAGGED in the sessions below, in pixels down from the track's top (over SHUFFLED's 28 names
# it travels 38: nineteen rows of scroll).
DRAGGED_BY = 20                         # ten rows: all nine redrawn
DRAGGED_SIX_ROWS = 13                   # 342 of gr_slidebox's 1000, which mul_div rounds to 6 rows (999 would round to 7)
DRAGGED_PART_WAY = 7                    # the first of two moves
DRAGGED_PAST_THE_FOOT = 60              # further than the track is long
DRAGGED_BACK_TO = 6                     # ...and where a second drag brings it back up to


def on_the_elevator(down=0):
    """A point `down` pixels below the elevator's top as it stands at the list's top (the track's own)."""
    return lambda places: places.track(down + INSIDE)


# The path field edited to another spec: Up to the field, its "*.*" rubbed out, "*.TXT" typed.
RESPEC = [UP, BACKSPACE, BACKSPACE, BACKSPACE, *typed("*.txt")]
# ...the same edit begun at a wait that also takes the release a TOUCHEXIT object's press left owing; and to "*.DAT",
# which keeps every name of SHUFFLED.
RELEASED_AND_RESPEC = [(release, UP), *RESPEC[1:]]
RELEASED_AND_RESPEC_TO_DAT = [(release, UP), BACKSPACE, BACKSPACE, BACKSPACE, *typed("*.dat")]
DAT_SPEC = folder("SHUFFLED", "*.DAT")
# A spec past the title's room: fs_newdir's title " " + spec + " " has 28 bytes of text, and the bytes after them are
# the first row's — whose first, the row's KIND, is then a character of the spec.
SPEC_PAST_THE_TITLE = "ABCDEFGH" * 5 + "*.*"
# Where the elevator of SHUFFLED under "*.DAT" is pressed and how far it is dragged: from its top row at the list's
# top (the read has put it back there) to twelve pixels down — six rows.
ELEVATOR_PRESSED_AT, ELEVATOR_DRAGGED_TO = 18, 30


def session(budget):
    """A constructor of the sessions of one budget class: `(path, selection, steps, button, path_out, file_out)`."""
    def of_that_class(path, selection, steps, button, path_out, file_out, **kwargs):
        return Session(path, selection, schedule(steps), budget, button, path_out, file_out, **kwargs)
    return of_that_class


short, middle, long, longer = session(SHORT), session(MIDDLE), session(LONG), session(LONGER)


# EVERY ARM OF THE TABLE $fefab0 but object 7's, each by the interaction that reaches it, and the exits — a session each
# (its budget class the measured run's). What each hands back is the ROM's, read from these runs and pinned.
SESSIONS = {
    # ---- the exits ----
    "Return, the DEFAULT: OK": short(MIXED, "", [RETURN], OK_BUTTON, MIXED, ""),
    "Return, the cursor shown": short(MIXED, "", [RETURN], OK_BUTTON, MIXED, "", shown=True),
    "OK clicked": short(MIXED, "", [click(OK), release], OK_BUTTON, MIXED, ""),
    "Cancel clicked": short(MIXED, "", [click(CANCEL), release], CANCEL_BUTTON, MIXED, ""),
    "a name typed, Cancel clicked: both strings handed back all the same": short(
        MIXED, "", [*typed("a"), click(CANCEL), release], CANCEL_BUTTON, MIXED, "A"),
    # ---- the selection, formatted into its field and unformatted out of it ----
    "a name typed into the selection, Return": short(MIXED, "", [*typed("ab.c"), RETURN], OK_BUTTON, MIXED, "AB.C"),
    "a selection handed in: eight and three": short(MIXED, "LONGNAME.PRG", [RETURN], OK_BUTTON, MIXED, "LONGNAME.PRG"),
    "a selection handed in: one letter, no extension": short(MIXED, "A", [RETURN], OK_BUTTON, MIXED, "A"),
    "a selection handed in: lower case, kept": short(MIXED, "readme.txt", [RETURN], OK_BUTTON, MIXED, "readme.txt"),
    "a selection handed in: too long for the field": short(
        MIXED, "TOOLONGNAME.EXTRA", [RETURN], OK_BUTTON, MIXED, "TOOLONGN.ME.EXTRA"),
    "a selection handed in, another typed after Escape": short(
        MIXED, "OLD.TXT", [ESCAPE, *typed("new"), RETURN], OK_BUTTON, MIXED, "NEW"),
    # ---- 12..20: a row ----
    "a file's row clicked, Return": short(MIXED, "", [click(A_C_ROW), (release, RETURN)], OK_BUTTON, MIXED, "A.C"),
    "a row, another, the same again, Return": short(
        MIXED, "", [click(A_C_ROW), (release, click(AB_TXT_ROW)), (release, click(AB_TXT_ROW)), (release, RETURN)],
        OK_BUTTON, MIXED, "AB.TXT"),
    "the list's first row clicked: a folder": long(MIXED, "", [click(AUTO_ROW), (release, RETURN)], OK_BUTTON,
                                                   folder("MIXED\\AUTO"), ""),
    "the list's last row clicked": short(MIXED, "", [click(fsl.FIRST_NAME + fsl.ROWS - 1), (release, RETURN)], OK_BUTTON,
                                         MIXED, "NOTES"),
    "a file's row double-clicked: OK": short(MIXED, "", [twice(A_C_ROW)], OK_BUTTON, MIXED, "A.C"),
    "a folder's row clicked: into it": long(MIXED, "OLD.SEL", [click(TOOLS_ROW), (release, RETURN)], OK_BUTTON, TOOLS, ""),
    "a file's row, then a folder's: the row put down, the selection cleared": long(
        MIXED, "", [click(A_C_ROW), (release, click(TOOLS_ROW)), (release, RETURN)], OK_BUTTON, TOOLS, ""),
    # The spec is found from the path's END: one shorter than a folder's name tells an end taken short.
    "a folder's row clicked under a one-character spec": long(
        folder("MIXED", "*"), "", [click(TOOLS_ROW), (release, RETURN)], OK_BUTTON, folder("MIXED\\TOOLS", "*"), ""),
    "a folder's row double-clicked: into it, no more": long(MIXED, "", [twice(TOOLS_ROW), (release, RETURN)], OK_BUTTON,
                                                              TOOLS, ""),
    "an empty row clicked: the selection cleared": short(ONE, "X.Y", [click(EMPTY_ROW), (release, RETURN)], OK_BUTTON,
                                                         ONE, ""),
    "an empty row double-clicked: OK, with no name": short(ONE, "X.Y", [twice(EMPTY_ROW)], OK_BUTTON, ONE, ""),
    # ---- 4: the close box ----
    "the close box, in a folder": long(MIXED, "", [click(CLOSER), (release, RETURN)], OK_BUTTON, ROOT_PATH, ""),
    "the close box, two folders down": long(TOOLS, "", [click(CLOSER), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the close box, at the root: read again": long(ROOT_PATH, "", [click(CLOSER), (release, RETURN)], OK_BUTTON,
                                                    ROOT_PATH, ""),
    "the close box, the path rubbed out: no separator to cut at": long(
        MIXED, "", [UP, ESCAPE, click(CLOSER), (release, RETURN)], OK_BUTTON, ROOT_PATH, ""),
    # The path's length is the one typed, the path by then fs_pspec's "A:\*.*": fs_back starts on its `:` and puts a
    # second `\` in after it.
    "the close box, the path one letter: a second separator put in": long(
        MIXED, "", [UP, ESCAPE, *typed("x"), click(CLOSER), (release, RETURN)], OK_BUTTON, "A:\\\\*.*", ""),
    # A path with no drive and no leading separator: nothing before its folder to cut back to — read again as it is.
    "the close box, a folder named from the current directory": long(
        "MIXED\\*.*", "", [click(CLOSER), (release, RETURN)], OK_BUTTON, "MIXED\\*.*", ""),
    # The drive's root is told by the byte before the last separator alone — a `:` there, wherever it is in the path.
    "the close box, a colon before the last separator: taken for a drive's root": long(
        "A:\\B:\\*.*", "", [click(CLOSER), (release, RETURN)], OK_BUTTON, "A:\\B:\\*.*", ""),
    # THE ROM's DEFECT, below: the path's only separator its first byte.
    "the close box, the root with no drive": long(NO_DRIVE_ROOT, "", [click(CLOSER), (release, RETURN)], OK_BUTTON,
                                                  NO_DRIVE_ROOT, ""),
    # ---- 5: the title ----
    "the title clicked: read again": long(MIXED, "", [click(TITLE), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "a row, the title, the same row: no row is selected after a read, so it is selected anew": long(
        MIXED, "", [click(A_C_ROW), (release, click(TITLE)), (release, click(A_C_ROW)), (release, RETURN)], OK_BUTTON,
        MIXED, "A.C"),
    "the down arrow, the title, the down arrow: the list's top is 0 after a read": long(
        MIXED, "", [click(DOWN_ARROW), (release, click(TITLE)), (release, click(DOWN_ARROW)), (release, RETURN)],
        OK_BUTTON, MIXED, ""),
    # ---- 6: the list's own box ----
    "the list's box clicked beside its rows: nothing": short(
        MIXED, "", [at(Places.beside_the_rows, press), (release, RETURN)], OK_BUTTON, MIXED, ""),
    # ---- 8, 9: the arrows ----
    "the up arrow at the top: nothing moves": short(MIXED, "", [click(UP_ARROW), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the down arrow: a row": short(MIXED, "", [click(DOWN_ARROW), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the down arrow held: to the list's end and no further": long(
        MIXED, "", [click(DOWN_ARROW), None, None, None, None, (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the down arrow, then the up arrow": middle(
        MIXED, "", [click(DOWN_ARROW), (release, click(UP_ARROW)), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the down arrow double-clicked: a row": short(MIXED, "", [twice(DOWN_ARROW), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "a row selected, the list scrolled, the same object clicked: the next name": short(
        MIXED, "", [click(A_C_ROW), (release, click(DOWN_ARROW)), (release, click(A_C_ROW)), (release, RETURN)],
        OK_BUTTON, MIXED, "AB.TXT"),
    # ---- 10: the track ----
    "the track clicked below the elevator: a page down": long(
        SHUFFLED, "", [at(low_in_the_track, press), (release, RETURN)], OK_BUTTON, SHUFFLED, ""),
    "a page down, then the track above the elevator: a page up": long(
        SHUFFLED, "", [at(low_in_the_track, press), (release, at(high_in_the_track, press)), (release, RETURN)],
        OK_BUTTON, SHUFFLED, ""),
    # The elevator is a pixel narrower than its track: the track's left edge answers the TRACK beside it. On the
    # elevator's own top row the mouse is not BELOW the elevator, so the page is up.
    "a page down, then the track's left edge beside the elevator's top row: a page up": long(
        SHUFFLED, "", [at(low_in_the_track, press), (release, at(beside_the_elevator_s_top_after_a_page, press)),
                       (release, RETURN)], OK_BUTTON, SHUFFLED, ""),
    "the track held: pages to the list's end": long(
        SHUFFLED, "", [at(low_in_the_track, press), None, None, (release, RETURN)], OK_BUTTON, SHUFFLED, ""),
    # ---- 11: the elevator ----
    "the elevator dragged down": long(
        SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_BY)), release, RETURN], OK_BUTTON,
        SHUFFLED, ""),
    "the elevator dragged 13 pixels: six rows": long(
        SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_SIX_ROWS)), release, RETURN], OK_BUTTON,
        SHUFFLED, ""),
    "the elevator dragged down in two moves": long(
        SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_PART_WAY)),
                       at(on_the_elevator(DRAGGED_BY)), release, RETURN], OK_BUTTON, SHUFFLED, ""),
    "the elevator dragged past the track's foot": long(
        SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_PAST_THE_FOOT)), release, RETURN],
        OK_BUTTON, SHUFFLED, ""),
    "the elevator pressed and let go: nothing moves": short(
        SHUFFLED, "", [at(on_the_elevator(), press), release, RETURN], OK_BUTTON, SHUFFLED, ""),
    "the elevator dragged down, then up": long(
        SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_BY)), release,
                       at(on_the_elevator(DRAGGED_BY), press), at(on_the_elevator(DRAGGED_BACK_TO)), release, RETURN],
        OK_BUTTON, SHUFFLED, ""),
    "the elevator of a list of one name: it fills its track": short(
        ONE, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_BY)), release, RETURN], OK_BUTTON, ONE, ""),
    # ---- the path edited: read when the selector next looks, whatever ended fm_do ----
    "the path edited, a row clicked: the new spec's list, its row": long(
        MIXED, "", [*RESPEC, click(A_C_ROW), (release, RETURN)], OK_BUTTON, TXT_SPEC, "AB.TXT"),
    "the path edited, a folder's row clicked: the spec lost": long(
        MIXED, "", [*RESPEC, click(TOOLS_ROW), (release, RETURN)], OK_BUTTON, TOOLS, ""),
    "the path edited, a file's row double-clicked: read, then OK with its name": long(
        MIXED, "", [*RESPEC, twice(A_C_ROW)], OK_BUTTON, TXT_SPEC, "AB.TXT"),
    "the path edited, the down arrow": long(MIXED, "", [*RESPEC, click(DOWN_ARROW), (release, RETURN)], OK_BUTTON, TXT_SPEC,
                                            ""),
    "the path edited, the title clicked: read twice, the spec lost": long(
        MIXED, "", [*RESPEC, click(TITLE), (release, RETURN)], OK_BUTTON, MIXED, ""),
    "the path edited, the close box": long(MIXED, "", [*RESPEC, click(CLOSER), (release, RETURN)], OK_BUTTON, ROOT_PATH, ""),
    # THE ROM's: the directory read and shown, OK put down — and the selector closed all the same, answering CANCEL.
    "the path edited, Return: the directory read, then CANCEL answered": long(
        MIXED, "", [*RESPEC, RETURN], CANCEL_BUTTON, TXT_SPEC, ""),
    "the path edited, OK clicked: CANCEL answered": long(MIXED, "", [*RESPEC, click(OK), release], CANCEL_BUTTON, TXT_SPEC,
                                                         ""),
    "the path edited, Cancel clicked": long(MIXED, "", [*RESPEC, click(CANCEL), release], CANCEL_BUTTON, TXT_SPEC, ""),
    # THE READ's OWN ORDER ($fe7f2c..$fe7f4e): the selected row put down, THEN the OK or Cancel that brought the read.
    # Only a session with a row selected, the path edited and an exit by a button draws both — and the selection it
    # hands back is the row's, though CANCEL is answered.
    "a row selected, the path edited, Return: the row put down, then OK": middle(
        MIXED, "", [click(A_C_ROW), *RELEASED_AND_RESPEC, RETURN], CANCEL_BUTTON, TXT_SPEC, "A.C"),
    "a row selected, the path edited, OK clicked: the row put down, then OK": middle(
        MIXED, "", [click(A_C_ROW), *RELEASED_AND_RESPEC, click(OK), release], CANCEL_BUTTON, TXT_SPEC, "A.C"),
    # THE LIST's TOP IS 0 FROM THE READ ON, in the pass that reads ($fe7fe2, before the switch): a scroll asked for
    # by the object that ended the same fm_do goes from the top of the new list, not from where the old one stood.
    "a page down, the path edited, the down arrow: a row from the new list's top": long(
        SHUFFLED, "", [at(low_in_the_track, press), *RELEASED_AND_RESPEC_TO_DAT, click(DOWN_ARROW), (release, RETURN)],
        OK_BUTTON, DAT_SPEC, ""),
    "a page down, the path edited, the elevator dragged: six rows from the new list's top": longer(
        SHUFFLED, "", [at(low_in_the_track, press), *RELEASED_AND_RESPEC_TO_DAT,
                       at(on_the_elevator(ELEVATOR_PRESSED_AT), press), at(on_the_elevator(ELEVATOR_DRAGGED_TO)), release,
                       RETURN],
        OK_BUTTON, DAT_SPEC, ""),
    # THE ROM's (below): the title's overrun makes the first row's kind neither a folder's 7 nor a file's space — and
    # every kind but the space is a folder's ($fe80d8 cmpi.b #32): the row's text, unformatted, goes into the path.
    "a spec past the title's room, the first row clicked: its kind is the title's overrun, so a folder's": middle(
        folder("MIXED", SPEC_PAST_THE_TITLE), "", [click(AUTO_ROW), (release, RETURN)], OK_BUTTON,
        "A:\\MIXED\\DEFGHABC.DEFGH*.* \\" + SPEC_PAST_THE_TITLE, ""),
    "Tab to the path and back, a name typed": short(MIXED, "", [TAB, TAB, *typed("z"), RETURN], OK_BUTTON, MIXED, "Z"),
    # ---- the paths an application hands in ----
    "the root": short(ROOT_PATH, "", [RETURN], OK_BUTTON, ROOT_PATH, ""),
    "a drive and a spec, no separator: one put in": short("A:*.*", "", [RETURN], OK_BUTTON, ROOT_PATH, ""),
    "a spec alone: the ROM's A:\\*.* in its place": short("*.TXT", "", [RETURN], OK_BUTTON, ROOT_PATH, ""),
    "no drive": short("\\MIXED\\*.*", "", [RETURN], OK_BUTTON, "\\MIXED\\*.*", ""),
    "a folder that is not there": short(folder("NOWHERE"), "", [RETURN], OK_BUTTON, folder("NOWHERE"), ""),
    "an empty folder": short(folder("SUBDIR"), "", [RETURN], OK_BUTTON, folder("SUBDIR"), ""),
    "the second drive": short("B:\\*.*", "", [RETURN], OK_BUTTON, "B:\\*.*", ""),
    # ---- a hundred names: the bell, and the list cut ----
    "a hundred names: the bell": middle(HUNDRED, "", [RETURN], OK_BUTTON, HUNDRED, ""),
    "a hundred and one names: the list cut at a hundred": middle(BIG, "", [RETURN], OK_BUTTON, BIG, ""),
    "a hundred names, the elevator dragged half way down its track": long(
        HUNDRED, "", [at(on_the_elevator(), press), at(on_the_elevator(TRACK_HEIGHT // 2 - INSIDE)), release, RETURN],
        OK_BUTTON, HUNDRED, ""),
    "a hundred names, the elevator dragged past the track's foot": long(
        HUNDRED, "", [at(on_the_elevator(), press), at(on_the_elevator(TRACK_HEIGHT)), release, RETURN], OK_BUTTON,
        HUNDRED, ""),
    "a hundred names, the track clicked: a page": long(HUNDRED, "", [at(low_in_the_track, press), (release, RETURN)],
                                                       OK_BUTTON, HUNDRED, ""),
    "a spec that keeps three files": short(TXT_SPEC, "", [RETURN], OK_BUTTON, TXT_SPEC, ""),
    "a spec with a letter before its star": short(folder("MIXED", "A*.*"), "", [RETURN], OK_BUTTON, folder("MIXED", "A*.*"),
                                                  ""),
}
# What the list shows when a session that scrolled ends: its first row.
FIRST_ROW = {
    "the up arrow at the top: nothing moves": b"\x07AUTO",
    "the down arrow: a row": b"\x07TOOLS",
    "the down arrow held: to the list's end and no further": b" A       C",
    "the down arrow, then the up arrow": b"\x07AUTO",
    "the down arrow double-clicked: a row": b"\x07TOOLS",
    "the down arrow, the title, the down arrow: the list's top is 0 after a read": b"\x07TOOLS",
    "the track clicked below the elevator: a page down": b" S09     DAT",
    "a page down, then the track above the elevator: a page up": b" S00     DAT",
    "the track held: pages to the list's end": b" S19     DAT",
    "a page down, then the track's left edge beside the elevator's top row: a page up": b" S00     DAT",
    "the elevator dragged down": b" S10     DAT",
    "the elevator dragged 13 pixels: six rows": b" S06     DAT",
    "the elevator dragged down in two moves": b" S10     DAT",
    "the elevator dragged past the track's foot": b" S19     DAT",
    "the elevator pressed and let go: nothing moves": b" S00     DAT",
    "the elevator dragged down, then up": b" S03     DAT",
    "the elevator of a list of one name: it fills its track": b" ONLY    TXT",
    "the path edited, the down arrow": b"\x07AUTO",
    "a page down, the path edited, the down arrow: a row from the new list's top": b" S01     DAT",
    "a page down, the path edited, the elevator dragged: six rows from the new list's top": b" S06     DAT",
    "a hundred names: the bell": b" F000    DAT",
    "a hundred and one names: the list cut at a hundred": b" F000    DAT",
    "a hundred names, the elevator dragged half way down its track": b" F046    DAT",
    "a hundred names, the elevator dragged past the track's foot": b" F091    DAT",
    "a hundred names, the track clicked: a page": b" F009    DAT",
}
assert set(FIRST_ROW) <= set(SESSIONS)


def text_at(image, address):
    """The NUL-ended string at `address`, as text."""
    return aes_strings.string_in(image, address).decode("latin-1")


def handed_back(image):
    """`(the button word, the path, the selection)` as fs_input left them for its caller."""
    return case.word_in(image, BUTTON_AT), text_at(image, PATH_AT), text_at(image, FILE_AT)


# Where the selector can SEE GEMDOS: its own memory (its tree, its two scratches, the texts of its fields and rows:
# `aes_fslib.SELECTOR_SPANS`), what it hands its caller, and the screen.
VISIBLE = [*fsl.SELECTOR_SPANS, (fsl.BAND_AT, fsl.BAND_BYTES), (vdi.SCREEN.base, vdi.SCREEN.bytes)]


def assert_the_replay_is_the_disk_s(session, replayed_memory):
    """The ROM's run of `session` over GEMDOS replayed left what its run over the staged disk left, wherever the
    selector can see GEMDOS."""
    _real, _replayed, script = ss.machine_of(session)
    for at_, size in VISIBLE:
        assert bytes(replayed_memory[at_:at_ + size]) == script.memory[at_:at_ + size], f"the replay differs at {at_:#x}"


@pytest.mark.parametrize("name", SESSIONS)
def test_fs_input_through_a_session(name):
    """The C held to the ROM over the whole session — its answer, every frame it hands the event layer, the whole
    image, then the bench's second differential — and what it hands back the ROM's, pinned."""
    session = SESSIONS[name]
    taken = ss.taken(session)
    assert taken.returned and taken.answer == DONE
    assert handed_back(taken.image) == (session.button, session.path_out, session.file_out)
    if name in FIRST_ROW:
        assert fsl.row_texts(taken.image)[0] == FIRST_ROW[name]
    assert_the_replay_is_the_disk_s(session, taken.rom_memory)


@pytest.mark.parametrize("name", SESSIONS)
def test_fs_input_draws_through_a_session_what_the_rom_draws(name):
    """WHAT IT DRAWS ON THE WAY: every VDI call the C makes over the session — its opcode and input arrays, in order —
    is the ROM's (`aes_fs_sessions.drawn_as_the_rom_draws`). The image a session ends on cannot tell: the selector has given
    the screen back, a row put down before a directory is read is drawn anew by the read, a clip set twice shows the
    second."""
    ss.drawn_as_the_rom_draws(SESSIONS[name])


def test_the_close_box_over_a_root_with_no_drive_writes_below_the_path_s_buffer():
    """A ROM DEFECT, reproduced byte for byte. The path's only separator is its first byte: the close box looks at the
    byte BEFORE it — below the working path's buffer — and, that being no `:`, calls fs_back from there. fs_back stops
    at a separator or at the path's start, which it is already below: it scans down through the AES's variables to
    the first `:` or `\\` byte there is (849 bytes down in this machine, a `:`), puts a `\\` in after it, and the
    path's "\\*.*" is then copied over that: five bytes of the AES's own data overwritten."""
    session = SESSIONS["the close box, the root with no drive"]
    real, _replayed, _script = ss.machine_of(session)
    start = make_image(real)
    working_path = aes.AES_RS_STRING
    separator = next(at_ for at_ in range(working_path - 1, 0, -1) if start[at_] in b":\\")
    assert start[separator:separator + 1] == b":" and working_path - separator > aes.OB_BYTES
    taken = ss.taken(session, second_differential=False)
    written = NO_DRIVE_ROOT.encode() + b"\0"
    assert bytes(taken.image[separator + 1:separator + 1 + len(written)]) == written
    assert bytes(start[separator + 1:separator + 1 + len(written)]) != written


def test_a_row_selected_anew_after_a_read_is_left_selected():
    """...and the row the last click selected stays SELECTED in the tree when the selector closes: fs_input puts no
    row down at its end (its next fs_format does)."""
    taken = ss.taken(SESSIONS["a row, the title, the same row: no row is selected after a read, so it is selected anew"],
                     second_differential=False)
    assert selected_objects(taken.image) == [A_C_ROW]


# ---- THE SELECTOR AS IT STANDS WHILE IT WAITS ------------------------------------------------------------------------------
# A session's END compares a screen the selector has already given back (fm_dial redraws what was under it). So each
# shape is also cut short: the user does nothing at the next wait, the ROM's run BLOCKS there, and the C — refused at
# the same call as one that would block — is held to the ROM's memory at the entry of that call: the selector on the
# screen, its fields, its rows, its tree. What it shows then is pinned: (the path field, the selection field, the
# list's first row, the SELECTED objects).
def waiting(path, selection, steps, budget=SHORT, **kwargs):
    return Session(path, selection, schedule(steps), budget, blocks=True, **kwargs)


WAITING = {
    "shown": (waiting(MIXED, "", []), (MIXED, "", b"\x07AUTO", [])),
    "shown, the cursor shown": (waiting(MIXED, "", [], shown=True), (MIXED, "", b"\x07AUTO", [])),
    "shown with a selection handed in": (waiting(MIXED, "NAME.EXT", []), (MIXED, "NAME    EXT", b"\x07AUTO", [])),
    "two letters typed": (waiting(MIXED, "", typed("ab")), (MIXED, "AB", b"\x07AUTO", [])),
    "a file's row clicked": (waiting(MIXED, "", [click(A_C_ROW), release]), (MIXED, "A       C", b"\x07AUTO", [A_C_ROW])),
    "another row clicked after it": (waiting(MIXED, "", [click(A_C_ROW), (release, click(AB_TXT_ROW)), release]),
                                     (MIXED, "AB      TXT", b"\x07AUTO", [AB_TXT_ROW])),
    "the same row clicked again": (waiting(MIXED, "", [click(A_C_ROW), (release, click(A_C_ROW)), release]),
                                   (MIXED, "A       C", b"\x07AUTO", [A_C_ROW])),
    "a folder's row clicked": (waiting(MIXED, "OLD.SEL", [click(TOOLS_ROW), release]), (TOOLS, "", b" ", [])),
    "an empty row clicked": (waiting(ONE, "X.Y", [click(EMPTY_ROW), release]), (ONE, "", b" ONLY    TXT", [EMPTY_ROW])),
    "the down arrow": (waiting(MIXED, "", [click(DOWN_ARROW), release]), (MIXED, "", b"\x07TOOLS", [])),
    "the up arrow at the top": (waiting(MIXED, "", [click(UP_ARROW), release]), (MIXED, "", b"\x07AUTO", [])),
    "a row selected, then the down arrow: the row put down": (
        waiting(MIXED, "", [click(A_C_ROW), (release, click(DOWN_ARROW)), release]), (MIXED, "A       C", b"\x07TOOLS", [])),
    "the track clicked: a page": (waiting(SHUFFLED, "", [at(low_in_the_track, press), release], MIDDLE),
                                  (SHUFFLED, "", b" S09     DAT", [])),
    "the elevator held mid-drag: its outline on the screen": (
        waiting(SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_BY))]),
        (SHUFFLED, "", b" S00     DAT", [])),
    "the elevator dragged and let go": (
        waiting(SHUFFLED, "", [at(on_the_elevator(), press), at(on_the_elevator(DRAGGED_BY)), release], MIDDLE),
        (SHUFFLED, "", b" S10     DAT", [])),
    "the close box": (waiting(MIXED, "", [click(CLOSER), release]), (ROOT_PATH, "", b"\x07BIG", [])),
    "the title, a selection handed in: cleared": (waiting(MIXED, "SEL.TXT", [click(TITLE), release]),
                                                  (MIXED, "", b"\x07AUTO", [])),
    "the list's box beside its rows": (waiting(MIXED, "", [at(Places.beside_the_rows, press), release]),
                                       (MIXED, "", b"\x07AUTO", [])),
    "the path edited, a row clicked": (waiting(MIXED, "", [*RESPEC, click(A_C_ROW), release], MIDDLE),
                                       (TXT_SPEC, "AB      TXT", b"\x07AUTO", [A_C_ROW])),
    "the path edited, the down arrow": (waiting(MIXED, "", [*RESPEC, click(DOWN_ARROW), release], MIDDLE),
                                        (TXT_SPEC, "", b"\x07AUTO", [])),
}


def field_text(image, index):
    """The text of the selector's field `index` (`test_aes_fmdo.field_text`), as a string."""
    return fmdo.field_text(image, fsl.SELECTOR, index).decode("latin-1")


def selected_objects(image):
    return [index for index in range(FS["FS_TREE_OBJECTS"])
            if aes.read_object(image, fsl.SELECTOR, index)["STATE"] & od.STATE_BITS["SELECTED"]]


@pytest.mark.parametrize("session, shows", WAITING.values(), ids=WAITING)
def test_fs_input_up_to_a_wait_nothing_ends(session, shows):
    """The C refused where the ROM's run blocks, its image the ROM's memory at the entry of that wait — every frame
    handed the door too — and the selector then showing what is pinned."""
    held = ss.taken(session)
    assert not held.returned
    assert (field_text(held.image, FS["FS_DIRECTORY"]), field_text(held.image, FS["FS_SELECTION"]),
            fsl.row_texts(held.image)[0], selected_objects(held.image)) == shows


def test_fs_input_with_nothing_delivered_blocks_at_fm_do_s_first_wait():
    """...and through the door's own name for it (`aes_event.refused_where_the_rom_blocks`, under the session's declared
    budget — a run to that wait is past what the default admits): the screen's lock taken, the mouse's owner changed,
    then the wait — three door calls, the third the one that blocks."""
    session, _shows = WAITING["shown"]
    _real, replayed, _script = ss.machine_of(session)
    held = aes_event.refused_where_the_rom_blocks(INPUT, ARGUMENTS, replayed, objects=True, budget=session.budget)
    assert [call.routine for call in held.calls] == [addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_CT_CHGOWN,
                                                     addrs.AES_ROM_EV_MULTI]
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        aes_event.refused_where_the_rom_blocks(INPUT, ARGUMENTS, replayed, objects=True)


# ---- a second call ------------------------------------------------------------------------------------------------------------
def test_a_second_selector_over_the_path_the_first_read_reads_it_again():
    """fs_input forgets the path last read before its first pass. A second call over the machine the first left — the
    last path read still in its buffer, the same path handed in — reads the directory again; did it not, no pass
    would ever read one (the empty path's fate, below)."""
    first = SESSIONS["Return, the DEFAULT: OK"]
    real, _replayed, script = ss.machine_of(first)
    again = fsl.continued(real, script.memory)
    assert text_at(make_image(again), aes.AES_SH_PATH_BUFFER) == MIXED == text_at(make_image(again), PATH_AT)
    taken = _session_with(ARGUMENTS, again, [click(A_C_ROW), (release, RETURN)])
    assert handed_back(taken.image) == (OK_BUTTON, MIXED, "A.C")


def test_a_second_selector_starts_with_no_row_selected_whatever_its_frame_held():
    """fs_input clears its selected row before its first pass. The machine a session that left a row SELECTED in the
    tree leaves (fs_input puts none down at its end), and the C's frame holding that row's number where the ROM's
    stack holds whatever was there: the first pass puts NO row down — the C draws what the ROM draws."""
    first = SESSIONS["a file's row clicked, Return"]
    real, _replayed, script = ss.machine_of(first)
    assert selected_objects(script.memory) == [A_C_ROW]
    slot = aes.HOST_SLOTS["HOST_SLOT_AES_FS_INPUT_FRAME"] + FS["FS_INPUT_SELECTED"]
    again = merge_pokes(fsl.continued(real, script.memory), {slot: vdi.pack_words(A_C_ROW - fsl.FIRST_NAME + 1)})
    steps = schedule([RETURN])(Places(again))
    replayed = fsl.replay_machine(again, fsl.session_script(again, aes_event.Waits(steps), SHORT).answers)
    fsl.vet_the_draws_of_a_child_of_its_own(replayed, aes_event.Waits(steps), SHORT)


# ---- the GEMDOS calls it makes -----------------------------------------------------------------------------------------
def test_fs_input_mallocs_its_three_blocks_first_and_frees_them_last_the_dta_first():
    """The ledger of a session that reads one directory: Malloc of the names', the index's and the DTA's bytes, the
    search, then Mfree of the DTA, the index and the names — the blocks GEMDOS answered, in that order."""
    session = SESSIONS["Return, the DEFAULT: OK"]
    taken = ss.taken(session, second_differential=False)
    made = fsl.replay_calls(taken.image)
    assert made == fsl.replay_calls(taken.rom_memory)
    names, index, dta = (case.long_in(taken.image, FS[name]) for name in ("AES_AD_FSNAMES", "AES_AD_FSINDEX",
                                                                          "AES_AD_FSDTA"))
    assert made[:3] == [fsl.call(fsl.MALLOC, ("l", FS[size])) for size in (
        "FS_NAMES_BLOCK_BYTES", "FS_INDEX_BLOCK_BYTES", "FS_DTA_BLOCK_BYTES")]
    assert made[3] == fsl.call(fsl.FSETDTA, ("l", dta))
    assert made[-3:] == [fsl.call(fsl.MFREE, ("l", block)) for block in (dta, index, names)]
    assert case.long_in(taken.image, aes.AES_DOS_RETURN) == addrs.AES_FS_INPUT_NAMES_FREE_RETURN


# ---- pointers on the bus, and the order it stores in ----------------------------------------------------------------------
TAGGED = {"the path": (PATH_AT | aes.BUS_TAG, FILE_AT, BUTTON_AT), "the selection": (PATH_AT, FILE_AT | aes.BUS_TAG, BUTTON_AT),
          "the button": (PATH_AT, FILE_AT, BUTTON_AT | aes.BUS_TAG)}


def _session_with(arguments, machine, steps, budget=SHORT):
    """A session over `machine` (a real-disk one) handed `arguments`: the C held to the ROM."""
    def waits():
        return aes_event.Waits(schedule(steps)(Places(machine)))
    script = fsl.session_script(machine, waits(), budget, arguments)
    return fsl.session(fsl.replay_machine(machine, script.answers), waits(), budget, arguments)


@pytest.mark.parametrize("arguments", TAGGED.values(), ids=TAGGED)
def test_fs_input_takes_each_pointer_off_the_24_bit_bus(arguments):
    """A top byte on each pointer argument in turn: the strings and the button word land where the bus puts them."""
    taken = _session_with(arguments, fsl.fs_input_machine(MIXED, "NAME.EXT"), [click(A_C_ROW), (release, RETURN)])
    assert handed_back(taken.image) == (OK_BUTTON, MIXED, "A.C")


def test_a_folder_with_an_extension_is_walked_into_by_its_unformatted_name():
    """A row shows a folder's name FORMATTED as a file's is — eight and three, padded. Into the path goes the name
    unformatted: over the disk whose DOTTED folder holds the folder SUB.DIR (`aes_fslib.disk_of` the path)."""
    machine = fsl.fs_input_machine(folder("DOTTED"), "")
    taken = _session_with(ARGUMENTS, machine, [click(fsl.FIRST_NAME), (release, RETURN)], LONG)
    assert handed_back(taken.image) == (OK_BUTTON, folder("DOTTED\\SUB.DIR"), "")


def test_the_button_word_is_stored_after_the_selection_is_handed_back():
    """The button word laid over the selection's first two bytes: the selection is copied out first, the word then
    stored over it (OK's 1: a NUL and $01)."""
    taken = _session_with((PATH_AT, FILE_AT, FILE_AT), fsl.fs_input_machine(MIXED, ""),
                          [click(A_C_ROW), (release, RETURN)])
    stored_over = vdi.pack_words(OK_BUTTON) + b"A.C\0"[aes.WORD_BYTES:]
    assert bytes(taken.image[FILE_AT:FILE_AT + len(stored_over)]) == stored_over


def test_the_selection_is_handed_back_after_the_path():
    """The selection's pointer inside the caller's path: the path is copied out first, the selection over it."""
    selection_at = PATH_AT + len("A:\\")
    taken = _session_with((PATH_AT, selection_at, BUTTON_AT), fsl.fs_input_machine(MIXED, ""),
                          [click(A_C_ROW), (release, RETURN)])
    assert text_at(taken.image, PATH_AT) == "A:\\A.C"


# ---- REAL GEMDOS on both shores: what one run can make ----------------------------------------------------------------------
def _typed_ahead(path, *codes, selection="", shown=False):
    return aes_event.typed_ahead(fsl.fs_input_machine(path, selection, shown), *aes_event.scancodes_of(*codes))


REAL = {
    "Return in the ring": (MIXED, (aes_event.RETURN_KEY,), SHORT, (OK_BUTTON, MIXED, "")),
    "a name and Return in the ring": (MIXED, ("ab.c", aes_event.RETURN_KEY), SHORT, (OK_BUTTON, MIXED, "AB.C")),
    "the root, Return in the ring": (ROOT_PATH, (aes_event.RETURN_KEY,), SHORT, (OK_BUTTON, ROOT_PATH, "")),
    "a folder that is not there": (folder("NOWHERE"), (aes_event.RETURN_KEY,), SHORT, (OK_BUTTON, folder("NOWHERE"), "")),
}


@pytest.mark.parametrize("path, codes, budget, back", REAL.values(), ids=REAL)
def test_fs_input_over_real_gemdos(path, codes, budget, back):
    """The whole selector in one run — its keys typed before the call — with the ROM's GEMDOS on the oracle's side and
    the reconstructed one on ours, over the staged disk: the blocks Malloc'd and freed for real, every VDI call the C
    makes the ROM's (`aes_fslib.run_session`)."""
    result = fsl.run_session(_typed_ahead(path, *codes), budget)
    assert result.answer() == DONE
    assert handed_back(result.final) == back


def test_a_return_typed_before_a_hundred_names_selector_never_reaches_it():
    """A ROM FINDING, over real GEMDOS: the bell fs_active rings at a hundred names is GEMDOS's Cconout, which polls
    the console for a Control-S / Control-C first — and so takes a key typed ahead out of the BIOS's keyboard ring into
    GEMDOS's own type-ahead buffer, where the event layer (which polls the BIOS) never sees it. The Return that ends a
    selector over 99 names is lost to one over a hundred: the ROM's run blocks at fm_do's first wait."""
    def returned(path):
        machine = _typed_ahead(path, aes_event.RETURN_KEY)
        return aes_event.rom_watched(INPUT, ARGUMENTS, machine, blocks=True, budget=MIDDLE)[2]
    assert returned(folder("NINETY9")) and not returned(HUNDRED)


def test_the_replayed_blocks_are_the_ones_real_gemdos_answers():
    """...and the three blocks of a replayed session are those blocks: the script's first three answers."""
    result = fsl.run_session(_typed_ahead(MIXED, aes_event.RETURN_KEY), SHORT)
    taken = ss.taken(SESSIONS["Return, the DEFAULT: OK"], second_differential=False)
    for block in ("AES_AD_FSNAMES", "AES_AD_FSINDEX", "AES_AD_FSDTA"):
        assert result.long(FS[block]) == case.long_in(taken.image, FS[block]) != 0


# ---- GEMDOS with no memory: the three refusals ------------------------------------------------------------------------------
NAMES_BYTES, INDEX_BYTES, DTA_BYTES = (FS[size] for size in ("FS_NAMES_BLOCK_BYTES", "FS_INDEX_BLOCK_BYTES",
                                                             "FS_DTA_BLOCK_BYTES"))
# How many bytes the arena is left with, and what fs_input then leaves in its three globals: a block it was answered
# (True) or the 0 it was refused; a global it never reached stays as the snapshot has it, 0.
NO_MEMORY_ARMS = {
    "no memory at all: the names refused": (0, (False, False, False)),
    "room for the names alone: the index refused, the names freed": (NAMES_BYTES + INDEX_BYTES - 2, (True, False, False)),
    "room for the names and the index: the DTA refused, both freed": (NAMES_BYTES + INDEX_BYTES + DTA_BYTES - 2,
                                                                      (True, True, False)),
}


def exhausted_machine(left):
    return fsl.exhausted(fsl.fs_input_machine(MIXED, "NAME.EXT"), left)


def no_memory_replayed(left):
    """...with GEMDOS replayed: the Mallocs' and the Mfrees' answers the ROM's own, over that arena."""
    machine = exhausted_machine(left)
    return fsl.replay_machine(machine, fsl.session_script(machine, {}, None).answers)


def refused_in_a_child(left):
    """The arm FIRST IN A CHILD, over the arena's replay (`aes_fslib.session`, nothing delivered: it waits on nothing):
    a C that went on where the ROM's run ends would halt the worker in process; in a child it fails the case. The GEMDOS
    calls it made, as the replay's ledger holds them — the ROM's, frame for frame."""
    held = fsl.session(no_memory_replayed(left), {}, None, second_differential=False)
    assert held.returned and held.answer == NO_MEMORY and not held.calls
    return held, fsl.replay_calls(held.image)


@pytest.mark.parametrize("left, answered", NO_MEMORY_ARMS.values(), ids=NO_MEMORY_ARMS)
def test_fs_input_with_no_memory_answers_0_and_shows_nothing(left, answered):
    """GEMDOS's arena exhausted by the ROM's own Malloc, but for `left` bytes: the Malloc that is refused ends it — the
    blocks before it freed, the names first, 0 answered, the screen, the strings and the button word untouched."""
    held, made = refused_in_a_child(left)
    names, index = (case.long_in(held.image, FS[block]) for block in ("AES_AD_FSNAMES", "AES_AD_FSINDEX"))
    mallocs = [fsl.call(fsl.MALLOC, ("l", size)) for size in (NAMES_BYTES, INDEX_BYTES, DTA_BYTES)][:sum(answered) + 1]
    assert made == mallocs + [fsl.call(fsl.MFREE, ("l", block)) for block in (names, index)[:sum(answered)]]
    machine = exhausted_machine(left)
    result = fsl.run_session(machine, None)
    assert result.answer() == NO_MEMORY
    blocks = tuple(result.long(FS[name]) != 0 for name in ("AES_AD_FSNAMES", "AES_AD_FSINDEX", "AES_AD_FSDTA"))
    assert blocks == answered
    start = make_image(machine)
    assert handed_back(result.final) == (aes.STALE_WORD, MIXED, "NAME.EXT")
    assert result.after(vdi.SCREEN.base, vdi.SCREEN.bytes) == bytes(start[vdi.SCREEN.base:vdi.SCREEN.base + vdi.SCREEN.bytes])
    assert result.word(aes.AES_DOS_ERR) == (1 if left == 0 else 0)


def test_fs_input_through_its_call_word():
    """Entered by the ROM's own Line-F word (the arm that waits on nothing: no memory), real GEMDOS on both shores."""
    refused_in_a_child(0)
    assert fsl.run_session(exhausted_machine(0), None, through_line_f=True).answer() == NO_MEMORY


def test_an_arena_with_room_for_all_three_is_not_refused():
    """The premise of the third arm's size: two bytes more and the DTA is answered — the selector runs."""
    machine = aes_event.typed_ahead(exhausted_machine(NAMES_BYTES + INDEX_BYTES + DTA_BYTES), aes_event.RETURN_KEY)
    assert fsl.run_session(machine, SHORT).answer() == DONE


# ---- THE ROM NEVER RETURNS FROM AN EMPTY PATH -------------------------------------------------------------------------------
PASSES_COMPARED = 3                     # arrivals at the pass's head kept: the second and the third are compared
SPIN_REFUSAL = "fs_input with a directory to read and its working path empty: the ROM never returns"


def test_the_rom_s_fs_input_over_an_empty_path_runs_the_same_pass_for_ever():
    """fs_input("", ...): the path equals the one last read (both empty), so no directory is read, the flag that skips
    fm_do stays set, and after the first (which draws the selection field once more) every pass leaves the machine as
    it found it — the whole memory at two consecutive arrivals at the pass's head is byte for byte the same, the stack
    too, thousands of instructions apart: a run with no door call and no end."""
    _script, passes = fsl.looping(fsl.fs_input_machine("", ""), PASSES_COMPARED - 1)
    assert len(passes) == PASSES_COMPARED
    spent, memories = zip(*passes)
    assert {len(memory) for memory in memories} == {fsl.RAM_BYTES}, "a pass keeps its RAM, not the sixteen megabytes"
    assert memories[1] == memories[2] != memories[0]
    assert spent[1] - spent[0] == spent[2] - spent[1] > 0


def test_a_looping_run_that_spends_its_budget_is_refused_naming_what_its_watch_does_not_see():
    """`aes_fslib.looping`'s watch is blind from each arrival at the pass that reads nothing to the next pass's head
    (`GemdosCalls`), so a run that never ends where it was asked to is not left with "raise the budget" alone: the
    refusal says what the watch could not have seen. (Here the empty path's run, asked for a pass it would take
    longer than its budget to reach.)"""
    with pytest.raises(AssertionError, match=r"raise the budget, from this run — BUT this run was ended at no pass "
                                             r"after its arrival \d+ .* watched at the next pass's head ALONE"):
        fsl.looping(fsl.fs_input_machine("", ""), aes_event.DERIVATION_INSNS)


MALLOCS_BEFORE_THE_FIRST_PASS = ("the names", "the index", "the DTA")       # fs_input's three blocks, each a GEMDOS call


def _shown(differ):
    """The first addresses of `differ`, as a failure names them."""
    return [hex(address) for address in differ[:aes_event.COMPARED_DIFFERENCES_SHOWN]]


def test_fs_input_over_an_empty_path_is_refused_by_name_where_the_rom_s_run_first_arrives():
    """...and off target the C refuses that run by name, on its first pass — its image the ROM's memory at its first
    arrival at the pass's head: the three blocks Malloc'd, the selector shown."""
    machine = fsl.fs_input_machine("", "")
    script, _passes = fsl.looping(machine, 0)
    replayed = fsl.replay_machine(machine, script)
    final, _writes, _regs = aes_event.stopped_at(make_image(aes.staged(INPUT, ARGUMENTS, replayed)),
                                                 addrs.AES_ROM_FS_INPUT, addrs.AES_FS_INPUT_NO_READ)
    returncode, stderr, image = aes_event.door_child(INPUT, ARGUMENTS, replayed, objects=True,
                                                     before=aes_event.CHILD_DOORS[INPUT])
    assert returncode != 0 and SPIN_REFUSAL in stderr
    differ = aes_event.differing(image, final)
    assert not differ, f"{len(differ)} bytes differ from the ROM's run at its first pass: {_shown(differ)}"
    assert len(fsl.replay_calls(image)) == len(script) == len(MALLOCS_BEFORE_THE_FIRST_PASS)


# ...AND A SECOND ROAD TO THE SAME PASS, by the close box. Under the working path lie the AES's four text buffers, the
# last of them AES_FMTSTR — where ob_format leaves every formatted text it merges, 81 bytes that end where the path
# begins. The close box over "\\*.*" scans down from below the path for a `:` or a `\\` (the defect above) and copies
# the path's five bytes to where it stops. The selector's own fields are short: what lies in the buffer's last bytes is
# whatever formatted text an application drew before it. One whose template runs 77 characters and ends in a `:` —
# or reaches a `\\` at its 78th — puts that copy's NUL on the working path's first byte: the path is empty, a
# directory is to be read, and the pass never ends.
COPIED_BYTES = len(NO_DRIVE_ROOT) + len(b"\0")
# Where the scan must stop for the copy's NUL to land on the path's first byte: ON a `\\` that many bytes below the
# path — or on a `:` one byte lower, the text's last character (fs_back puts a `\\` in after it, and the copy starts
# there).
BACKSLASH_AT = aes.AES_TEXT_BUFFER_BYTES - COPIED_BYTES + 1
COLON_AT = BACKSLASH_AT - 1
LONGEST_TEMPLATE = aes.AES_TEXT_BUFFER_BYTES - len(b"\0")
STALE_TEMPLATES = {"a template of 77 characters ending in a colon": b"x" * COLON_AT + b":",
                   "a template with a backslash as its 78th character": (b"y" * BACKSLASH_AT + b"\\").ljust(LONGEST_TEMPLATE, b"_")}
SCREEN_RECT = (0, 0, vdi.SCREEN.width, vdi.SCREEN.height)
TEXT_ROW_HEIGHT = 8                     # pixels: a row of text in the snapshot's resolution
LAST_PASS_COMPARED = 4                  # arrivals at the pass's head: the read, the click, then the passes that repeat


def after_a_formatted_text(machine, template):
    """`machine` after an application has drawn a one-object dialog — a FORMATTED TEXT whose template is `template`,
    its raw text empty — by the ROM's own ob_draw under the whole screen's clip (the ROM's own gsx_sclip): what that
    wrote laid over it, the template merged in AES_FMTSTR."""
    dialog = merge_pokes(
        aes.tree_pokes([aes.node(None, TYPE=aes.G_FTEXT, SPEC=aes.BLOCKS_AT, WIDTH=SCREEN_RECT[2], HEIGHT=TEXT_ROW_HEIGHT)]),
        aes.tedinfo_pokes(aes.BLOCKS_AT, PTEXT=od.TEXT_AT, PTMPLT=od.TEMPLATE_AT, PVALID=od.TEXT_AT, FONT=od.FONT_IBM,
                          TXTLEN=len(template) + 1),
        od.string_pokes(b""), od.string_pokes(template, od.TEMPLATE_AT, od.TEMPLATE_BYTES))
    clipped = od.clip_set_by_the_rom(aes.RECTS_AT, merge_pokes(machine, dialog, {aes.RECTS_AT: vdi.pack_words(*SCREEN_RECT)}))
    frame = aes_event.frame_of(("l", aes.TREE_AT), ("w", aes.OB_ROOT), ("w", FS["FS_DRAW_DEPTH"]))
    written, final, _registers = aes_event.derived(addrs.AES_ROM_OB_DRAW, clipped, frame=frame)
    assert bytes(final[aes.AES_FMTSTR:aes.AES_FMTSTR + len(template) + 1]) == template + b"\0"
    return merge_pokes(clipped, written, aes_event.savptr_in_the_band())


@pytest.mark.parametrize("template", STALE_TEMPLATES.values(), ids=STALE_TEMPLATES)
def test_the_close_box_over_a_root_with_no_drive_never_returns_once_a_long_formatted_text_was_drawn(template):
    """The ROM's run over that machine — the close box clicked at its first wait — arrives at the pass's head with the
    same memory, the stack too, pass after pass; and the C refuses the run by name on the first of those passes, its
    image the ROM's memory there. The click is the one the same selector takes over the machine with no such text
    drawn (which returns: the session above), laid here only where the memory it found is this run's too."""
    session = SESSIONS["the close box, the root with no drive"]
    real, replayed, _script = ss.machine_of(session)
    interrupts = ss.interrupts_of(session, real)
    first_pass_that_repeats = LAST_PASS_COMPARED - 2
    stale = after_a_formatted_text(real, template)
    script, passes = fsl.looping(stale, LAST_PASS_COMPARED, budget=SHORT,
                                 delivered=aes_event.deliveries(INPUT, ARGUMENTS, real, interrupts, session.budget))
    spent, memories = zip(*passes)
    assert memories[LAST_PASS_COMPARED - 1] == memories[LAST_PASS_COMPARED] != memories[first_pass_that_repeats]
    assert spent[LAST_PASS_COMPARED] - spent[LAST_PASS_COMPARED - 1] == spent[LAST_PASS_COMPARED - 1] - spent[LAST_PASS_COMPARED - 2] > 0
    assert text_at(memories[LAST_PASS_COMPARED], aes.AES_RS_STRING) == ""
    # ...and the C, over GEMDOS replayed from that run: refused where the ROM's run first arrives with nothing to read.
    stale_replayed = fsl.replay_machine(after_a_formatted_text(replayed, template), script)
    delivered = aes_event.deliveries(INPUT, ARGUMENTS, replayed, interrupts, session.budget)
    _no_calls, replayed_passes = fsl.looping(stale_replayed, first_pass_that_repeats, budget=SHORT, delivered=delivered)
    returncode, stderr, image = aes_event.door_child(INPUT, ARGUMENTS, stale_replayed, objects=True, interrupts=delivered,
                                                     before=aes_event.CHILD_DOORS[INPUT],
                                                     seconds=aes_event.CHILD_RETURN_SECONDS)
    assert returncode != 0 and SPIN_REFUSAL in stderr
    differ = aes_event.differing(image, fsl.whole_image(replayed_passes[first_pass_that_repeats][1]))
    assert not differ, f"{len(differ)} bytes differ from the ROM's run at that pass: {_shown(differ)}"


def test_a_gemdos_handler_the_replay_does_not_serve_ends_the_child_by_name():
    """THE CHILD'S OWN GEMDOS DOOR (`aes_fslib.bind_replay_in_a_child`): a handler the C's dispatcher reaches that the
    replay does not serve — here every one, the replay's twins taken away in the child — ends the child by name, with
    a status of its own: never a callback that raises into the C."""
    _real, replayed, _script = ss.machine_of(SESSIONS["Return, the DEFAULT: OK"])
    none_served = aes_event.CHILD_DOORS[INPUT] + "aes_fslib.REPLAY_HANDLERS.clear(); "
    returncode, stderr, _image = aes_event.refusal(INPUT, replayed, ARGUMENTS,
                                                   bind=aes_event.child_binding(objects=True, before=none_served))
    assert returncode == fsl.CHILD_GEMDOS_REFUSED and "which the replay does not serve" in stderr


def test_a_path_of_one_space_returns():
    """The premise of the refusal: any path but the empty one differs from the one last read, and is read."""
    taken = ss.taken(short(" ", "", [RETURN], OK_BUTTON, ROOT_PATH, ""), second_differential=False)
    assert taken.returned and text_at(taken.image, PATH_AT) == ROOT_PATH


# ---- object 7, the one arm no click reaches -----------------------------------------------------------------------------------
def test_the_slider_s_box_is_covered_by_its_children_so_no_click_answers_it():
    """The table's row for object 7 (the box round the arrows and the track) is the same "nothing" as object 6's — and
    no press can answer 7: its three children (the up arrow, the track, the down arrow) tile it exactly, so ob_find
    always meets one of them."""
    box = aes.read_object(BASE_IMAGE, fsl.SELECTOR, FS["FS_SLIDER_BOX"])
    assert (box["HEAD"], box["TAIL"]) == (UP_ARROW, SLIDER)
    covered = set()
    for child in (UP_ARROW, DOWN_ARROW, SLIDER):
        placed = aes.read_object(BASE_IMAGE, fsl.SELECTOR, child)
        covered |= {(x, y) for x in range(placed["X"], placed["X"] + placed["WIDTH"])
                    for y in range(placed["Y"], placed["Y"] + placed["HEIGHT"])}
    assert covered == {(x, y) for x in range(box["WIDTH"]) for y in range(box["HEIGHT"])}


# ---- the budgets -----------------------------------------------------------------------------------------------------------------
def test_a_session_under_the_default_budget_is_refused_by_name():
    """RED: the same session with no budget declared is refused by the default's own words."""
    session = SESSIONS["Return, the DEFAULT: OK"]
    real, _replayed, _script = ss.machine_of(session)
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        aes_event.deliveries(INPUT, ARGUMENTS, real, ss.interrupts_of(session, real))
