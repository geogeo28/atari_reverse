"""THE DESK'S AES BINDINGS (`src/desk/deskbind.c`; band 6 wave 1a, unit D): the forty routines `$fddde6..$fde4ff` and
desk_wait `$fe1bdc`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

    binding(arguments):  ret = the AES routine(the same, re-pushed);  dsptch();  return ret

  * EVERY CASE IS AN ARRIVAL (`aes_deskbind.arrival`): a chain of the hands — or the DESKTOP.INF machine's own boot —
    stopped at the binding's first instruction, the arguments read off the frame the desk's caller pushed. Where no
    chain makes the machine an arm needs, the case is A LABELLED ARGUMENT CLASS, said in its name: the same binding
    over an arrival's machine with other arguments, or (appl_exit with a message in the desk's pipe, or where an
    accessory has a menu entry) over ANOTHER binding's arrival. Never a poke.
  * TIER 1: the C core against the ROM's own routine from that entry (`aes_switching.companion`, nothing dropped: the
    same idles, every byte outside the run's own stack, the image at every dispatch — and the answer, below). A
    binding that waits is taken through its wake (`WAKES`).
  * D0 AT RETURN. Where the core answers a word it is held to the ROM's D0.w. TWO NAMED DIVERGENCES, COUNTED
    (`test_the_answers_that_are_not_the_rom_s_are_counted_by_name`), each held to BE one and to be READ BY NO CALLER
    — by the reading of every call site (`aes_deskbind.answer_readers`) and BY RUNS (the desk's own run on from the
    binding's return is the same machine whatever D0 and A0 hold there):
      - NO WORD IN C: the seven bindings of `void` implementations;
      - THE NESTED RELEASE'S LEFTOVER: wm_open's and wm_set's known divergence (`aes/wmupdate.h`), met at every
        arrival of wind_open and at wind_set's WF_NEWDESK.
  * UNBOUND, held on both blobs: no function outside `deskbind.c` refers to a binding, the Line-F table's entries for
    them are the ROM's, no registry names one.

WHAT IS NOT HELD: any row, any price, anything of a blob's run; an objc_draw of a tree with G_USERDEF objects (the
text view: it calls the desk's own draw code `$fde844`, unit E's, the ROM's still).
"""
import functools
import re
import sys
from collections import Counter, namedtuple
from pathlib import Path

import pytest

from harness import addrs

import aes
import aes_boot
import aes_desk
import aes_deskbind as db
import aes_event
import aes_objects
import case
import routines
import transcription

BENCH = Path(__file__).resolve().parents[1] / "bench"

BOOT = db.THE_BOOT
RETURN = aes_event.key(aes_event.RETURN_KEY)
# THE WAKES: what ends a binding's wait, and where the scheduled run takes it.
RETURN_TYPED = "Return at the first idle"
PRESSED = "the button pressed at the first idle"
LET_GO = "the button let go at the first idle"
CARRIED_OFF = "the mouse carried off at the first idle"
LET_GO_AT_ONCE = "the button let go at the first door call"
LET_GO_LATER = "the button let go at the second door call"
BOX_GROWN = "the mouse carried at the first door call, the button let go at the third"
AWAY = (300, 150)                       # a point of the desktop far from every icon: out of a drag's first rectangle
WAKES = {RETURN_TYPED: dict(at_idle={0: RETURN}), PRESSED: dict(at_idle={0: aes_event.press}),
         LET_GO: dict(at_idle={0: aes_event.release}), CARRIED_OFF: dict(at_idle={0: aes_event.move_to(*AWAY)}),
         LET_GO_AT_ONCE: dict(at_calls={0: aes_event.release}), LET_GO_LATER: dict(at_calls={1: aes_event.release}),
         BOX_GROWN: dict(at_calls={0: aes_event.move_to(*AWAY), 2: aes_event.release})}

IDLE_WAKES = (RETURN_TYPED, PRESSED, LET_GO, CARRIED_OFF)

Case = namedtuple("Case", "short chain nth wake arm over arguments why", defaults=(0, None, None, None, None, None))
Case.__doc__ = """One case: the binding `short` at the `nth` arrival of `chain` (BOOT: the boot), its wait ended by
`wake` (a key of WAKES). `arm`: what the arrival's own arguments must be for the case to be the arm it was chosen for
(`arguments -> bool`). AN ARGUMENT CLASS has a `why` (its label): it runs over the arrival of `over` (another binding;
None: its own) with `arguments` — a tuple, or `arrival -> tuple`."""

DROPPED_FILE = "file: dragged to the trash, Return (Cancel, the dialog's default)"
SHOWN, SHOWN_LONG = "file: shown, a key at its end", "files: the long file shown, a blank at each page's end and at its end"
LAUNCHED = "files: the program double-clicked — launched"
INFO, DRIVE_INFO = "Desk > Desktop Info, Return", "A: File > Show Info, Return"
SAVED, RUBBER = "Options > Save Desktop, Return", "a rubber box on the desktop, round the trash"
DRAGGED = "drive A: dragged to the trash, Return"
TRASHED, DENIED = "file: dragged to the trash, OK", "file: read-only, dragged to the trash, OK — access denied, Return"
EVDOOR = aes.header_constants("evdoor.h")
TIMER, FIRST_RECTANGLE = EVDOOR["EV_MU_TIMER"], EVDOOR["EV_MU_M1"]
TIMER_LOW, TIMER_HIGH = 15, 16          # evnt_multi's arguments: the timer's two words, after the message buffer
OPENED, SELECTED, AS_TEXT, BY_SIZE = "A: opened", "drive A: selected", "window: View > Show as Text", "window: View > Sort by Size"
CLOSED, CLOSER, TWO_WINDOWS = "window: File > Close Window", "window: its closer clicked", "window: A: opened again (two windows)"
GEMSUPER = aes.header_constants("gemsuper.h")
HIDE, SHOW, USER_FORM = GEMSUPER["GRAF_MOUSE_HIDE"], GEMSUPER["GRAF_MOUSE_SHOW"], GEMSUPER["GRAF_MOUSE_USER_FORM"]
FIRST_IMAGE = GEMSUPER["GRAF_MOUSE_FIRST_IMAGE"]
DESKBIND = db.CONSTANTS
ARROW, HOURGLASS = DESKBIND["DESK_CURSOR_ARROW"], DESKBIND["DESK_CURSOR_HOURGLASS"]
REDRAW_THE_BAR = 0x8000                 # menu_ienable's item: its top bit
NEWDESK, NAME, HSLIDE, VSLIDE = db.WMLIB["WF_NEWDESK"], db.WMUPDATE["WF_NAME"], db.WMLIB["WF_HSLIDE"], db.WMLIB["WF_VSLIDE"]
NO_ALERT_FOR_THIS_CODE, FILE_NOT_FOUND, ACCESS_DENIED = 100, 2, 5
GROW = aes.header_constants("fmdo.h")["FMD_GROW"]    # form_dial's type 1: a box grown from the little rectangle
BUTTON_DOWN, RIGHT_BUTTON_S_PLACE = 1, 0x100    # evnt_button's state; a state word with a bit in the mask's byte
A_LEAST_WIDTH = 40                      # ...a graf_rubbox least width that is not its least height (the desk hands 6 and 6)
THE_INF_S_SECOND_LINE = 9               # shel_put's data, from this byte: "\n#b" where the shell's buffer begins "#a0"


def _hourglass_form(arrived):
    """(255, the address of the system resource's hourglass image): what rs_gaddr answers graf_mouse(2), handed by the
    caller instead — read off the arrival's own resource."""
    ram = arrived.boot.ram
    header = aes.resource_header(ram)
    bitblk = header + case.word_in(ram, header + aes.RSH_BITBLK) + (HOURGLASS + FIRST_IMAGE) * aes.BI_BYTES
    return USER_FORM, case.long_in(ram, bitblk + aes.BI_PDATA)


def _with(index, value):
    """An arrival's own arguments, the one at `index` made `value`."""
    return lambda arrived: (*arrived.arguments[:index], value, *arrived.arguments[index + 1:])


def _asking_a_timer(arrived):
    """evnt_multi's own arguments, a timer of 5 ms asked too."""
    asked = list(arrived.arguments)
    asked[0], asked[TIMER_LOW], asked[TIMER_HIGH] = asked[0] | TIMER, 5, 0
    return tuple(asked)


def _item_flagged(enable):
    return lambda arrived: (arrived.arguments[0], arrived.arguments[1] | REDRAW_THE_BAR, enable)


def is_disabled(arrived, item):
    """Whether the menu tree a menu binding's arrival was handed holds `item` DISABLED."""
    return bool(case.word_in(arrived.boot.ram, (arrived.arguments[0] & aes_boot.BUS) + item * aes.OB_BYTES + aes.OB_STATE)
                & 1 << aes.OB_STATE_DISABLED_BIT)


def _a_disabled_item(arrived):
    """menu_icheck's own arguments, the item A DISABLED ONE of the same tree (the first: File > Open at the boot)."""
    tree = arrived.arguments[0] & aes_boot.BUS
    disabled = next(item for item in range(1, aes.TREE_OBJECTS * 2)
                    if case.word_in(arrived.boot.ram, tree + item * aes.OB_BYTES + aes.OB_TYPE) & aes.OB_TYPE_MASK == aes.G_STRING
                    and is_disabled(arrived, item))
    return (arrived.arguments[0], disabled, arrived.arguments[2])


def _grown_from_a_little_rectangle(arrived):
    """form_dial's own arguments, the type GROW and the little rectangle four words that all differ."""
    return (GROW, 8, 16, 24, 32, *arrived.arguments[5:])


CASES = (
    Case("APPL_INIT", BOOT), Case("APPL_INIT", SHOWN),
    Case("APPL_BVSET", BOOT), Case("APPL_BVSET", SHOWN_LONG),
    Case("APPL_EXIT", SHOWN), Case("APPL_EXIT", LAUNCHED),
    Case("APPL_EXIT", DROPPED_FILE, over="APPL_WRITE", arguments=(), why="called where the desk's pipe holds a message — an arrival of appl_write's"),
    Case("APPL_EXIT", db.THE_ACCESSORY_BOOT, over="EVNT_MULTI", arguments=(),
         why="called where an accessory has a menu entry (mn_clsda's AC_CLOSE) — an arrival of evnt_multi's"),
    Case("APPL_WRITE", AS_TEXT), Case("APPL_WRITE", DROPPED_FILE),
    Case("EVNT_MULTI", BOOT, wake=RETURN_TYPED), Case("EVNT_MULTI", BOOT, wake=PRESSED),
    Case("EVNT_MULTI", INFO, arm=lambda a: a[0] & TIMER), Case("EVNT_MULTI", AS_TEXT), Case("EVNT_MULTI", "file: selected", wake=RETURN_TYPED),
    # (the drag's wait: the button, and the mouse LEAVING the two pixels it was pressed at — the one caller with a rectangle)
    Case("EVNT_MULTI", DRAGGED, wake=LET_GO, arm=lambda a: a[0] & FIRST_RECTANGLE and a[4:9] != (0,) * 5),
    Case("EVNT_MULTI", DRAGGED, wake=CARRIED_OFF),
    Case("EVNT_MULTI", AS_TEXT, arguments=_asking_a_timer, why="a timer of 5 ms asked beside its events (every caller of the desk's hands 0): a message waits"),
    # (the mask is ADDED to the state, `add.w`: a state with a bit in the mask's byte moves the MASK on — here to the
    # right button, which is up, so the ROM's wait is over at once where an OR would wait for the left one let go)
    Case("EVNT_MULTI", DRAGGED, arguments=_with(3, RIGHT_BUTTON_S_PLACE),
         why="a state word with a bit in the mask's byte (no caller of the desk's hands one): the mask ADDED to, the right button's"),
    Case("EVNT_BUTTON", DRAGGED), Case("EVNT_BUTTON", RUBBER),
    Case("EVNT_BUTTON", RUBBER, wake=PRESSED, arguments=_with(2, BUTTON_DOWN),
         why="the button awaited DOWN (the desk's one caller awaits it up): the buttons word answered is not the keys'"),
    Case("EVNT_DCLICK", BOOT), Case("EVNT_DCLICK", SHOWN),
    Case("FORM_DO", INFO, wake=RETURN_TYPED), Case("FORM_DO", DRIVE_INFO, wake=RETURN_TYPED),
    Case("FORM_DO", "file: dragged to the trash, OK", wake=RETURN_TYPED),
    Case("FORM_DIAL", INFO), Case("FORM_DIAL", INFO, 1), Case("FORM_DIAL", "A: Options > Install Disk Drive, Return"),
    Case("FORM_DIAL", INFO, arguments=_grown_from_a_little_rectangle,
         why="type 1, a box GROWN from a little rectangle of four different words (the desk's four callers hand types 0 and 3 and four zeros)"),
    Case("FORM_ALERT", SAVED, wake=RETURN_TYPED), Case("FORM_ALERT", "A: File > Format, Return (the warning answered)", wake=RETURN_TYPED),
    Case("FORM_ALERT", "file: File > Open (the Show / Print / Cancel alert)", wake=RETURN_TYPED),
    # (a read-only file dragged to the trash: GEMDOS refuses, the copy engine shows error 5 — the one chain that calls it)
    Case("FORM_ERROR", DENIED, wake=RETURN_TYPED, arm=lambda a: a == (ACCESS_DENIED,)),
    Case("FORM_ERROR", DENIED, wake=RETURN_TYPED, arguments=(FILE_NOT_FOUND,), why="error 2's alert (the one chain's GEMDOS answers access denied, 5)"),
    Case("FORM_ERROR", DENIED, arguments=(NO_ALERT_FOR_THIS_CODE,), why="a code fm_error shows nothing for"),
    Case("FORM_CENTER", INFO), Case("FORM_CENTER", DRIVE_INFO), Case("FORM_CENTER", "file: dragged to the trash, OK"),
    Case("GRAF_MOUSE", BOOT, arm=lambda a: a[0] == HOURGLASS), Case("GRAF_MOUSE", INFO, arm=lambda a: a[0] == ARROW),
    Case("GRAF_MOUSE", OPENED, arm=lambda a: a[0] == HIDE), Case("GRAF_MOUSE", OPENED, 1, arm=lambda a: a[0] == SHOW),
    Case("GRAF_MOUSE", OPENED, arguments=(SHOW + 1, 0), why="a number above 257: neither hidden nor shown"),
    Case("GRAF_MOUSE", OPENED, arguments=(0xFFFF, 0), why="a negative number: a form (the compare is signed), image 2"),
    Case("GRAF_MOUSE", OPENED, arguments=_hourglass_form, why="255: the caller's own form, the hourglass's image handed by address"),
    Case("GRAF_RUBBOX", RUBBER, wake=LET_GO_AT_ONCE), Case("GRAF_RUBBOX", RUBBER, wake=LET_GO_LATER),
    Case("GRAF_RUBBOX", RUBBER, wake=BOX_GROWN),          # (a box wider than it is tall: the two answers differ)
    Case("GRAF_RUBBOX", RUBBER, wake=LET_GO_AT_ONCE, arguments=_with(2, A_LEAST_WIDTH),
         why="a least width of 40 beside the least height of 6 (the desk's one caller hands 6 and 6)"),
    Case("GRAF_MKSTATE", SELECTED), Case("GRAF_MKSTATE", RUBBER), Case("GRAF_MKSTATE", "file: selected"),
    Case("GRAF_GROWBOX", OPENED), Case("GRAF_GROWBOX", "window: its fuller clicked"),
    Case("GRAF_SHRINKBOX", CLOSED), Case("GRAF_SHRINKBOX", CLOSER), Case("GRAF_SHRINKBOX", "folder: File > Close"),
    Case("MENU_TNORMAL", INFO, arm=lambda a: a[2] == 1), Case("MENU_TNORMAL", BY_SIZE),
    Case("MENU_TNORMAL", INFO, arguments=_with(2, 0), why="the title made NOT normal (the desk's one caller asks for normal alone)"),
    Case("MENU_BAR", BOOT, arm=lambda a: a[1] == 1), Case("MENU_BAR", SHOWN, arm=lambda a: a == (0, 0)),
    Case("MENU_ICHECK", BOOT, arm=lambda a: a[2] == 1), Case("MENU_ICHECK", AS_TEXT, arm=lambda a: a[2] == 0), Case("MENU_ICHECK", AS_TEXT, 1),
    Case("MENU_ICHECK", BOOT, arguments=_a_disabled_item, why="a DISABLED item checked (the desk checks none that is): do_chg is not asked to mind it"),
    Case("MENU_IENABLE", BOOT, arm=lambda a: a[2] == 1 and not a[1] & REDRAW_THE_BAR),
    Case("MENU_IENABLE", SELECTED, 23, arm=lambda a: a[2] == 0 and not a[1] & REDRAW_THE_BAR),
    # (THE BINDING'S MAIN USE: a drive selected, and File > Open — disabled till then — is enabled: held below)
    Case("MENU_IENABLE", SELECTED, 0, arm=lambda a: a[2] == 1 and not a[1] & REDRAW_THE_BAR),
    Case("MENU_IENABLE", BOOT, arguments=_item_flagged(1), why="the item's top bit set (no caller of the desk's sets it): enabled, the bar redrawn"),
    Case("MENU_IENABLE", BOOT, arguments=_item_flagged(0), why="the item's top bit set: disabled, the bar redrawn"),
    Case("OBJC_OFFSET", "file: dragged to the trash, OK"), Case("OBJC_OFFSET", "folder: dragged to the trash, OK"),
    Case("OBJC_ORDER", OPENED), Case("OBJC_ORDER", CLOSED),
    Case("OBJC_FIND", SELECTED), Case("OBJC_FIND", OPENED), Case("OBJC_FIND", RUBBER),
    Case("OBJC_FIND", DRAGGED, 3, arm=lambda a: a[4] > 4 * a[3]),       # (the trash's icon, far below its own x: no point of the diagonal)
    Case("OBJC_ADD", OPENED), Case("OBJC_ADD", "A: File > Open"), Case("OBJC_ADD", BY_SIZE),
    Case("OBJC_DRAW", INFO), Case("OBJC_DRAW", OPENED), Case("OBJC_DRAW", OPENED, 2), Case("OBJC_DRAW", SELECTED),
    Case("OBJC_CHANGE", SELECTED, arm=lambda a: a[7] == 1), Case("OBJC_CHANGE", OPENED, 1, arm=lambda a: a[7] == 0),
    Case("RSRC_GADDR", BOOT), Case("RSRC_GADDR", "A: File > Open"),
    Case("SHEL_WRITE", SHOWN), Case("SHEL_WRITE", LAUNCHED),
    Case("SHEL_GET", BOOT), Case("SHEL_GET", SAVED),
    Case("SHEL_GET", BOOT, arguments=_with(1, 3), why="three bytes asked (the desk asks a kilobyte, whose last bytes are zeros over zeros)"),
    Case("SHEL_PUT", SAVED), Case("SHEL_PUT", SHOWN),
    Case("SHEL_PUT", SAVED, arguments=lambda arrived: (arrived.arguments[0] + THE_INF_S_SECOND_LINE, 3),
         why="three bytes of the INF's second line put (the desk puts two kilobytes, whose last bytes are zeros over zeros)"),
    Case("WIND_CLOSE", CLOSED), Case("WIND_CLOSE", CLOSER),
    Case("WIND_DELETE", CLOSED), Case("WIND_DELETE", CLOSER),
    Case("WIND_FIND", SELECTED), Case("WIND_FIND", OPENED), Case("WIND_FIND", RUBBER),
    Case("WIND_FIND", TRASHED, 2),      # (the trash's icon, where the file is let go: a point of the desktop WHOSE MIRROR IS IN THE WINDOW — held below)
    Case("WIND_UPDATE", BOOT, arm=lambda a: a[0] == 1), Case("WIND_UPDATE", INFO, 1, arm=lambda a: a[0] == 0), Case("WIND_UPDATE", OPENED, 2),
    Case("WIND_CREATE", OPENED), Case("WIND_CREATE", TWO_WINDOWS),
    Case("WIND_OPEN", OPENED), Case("WIND_OPEN", TWO_WINDOWS),
    *(Case("WIND_GET", OPENED, nth) for nth in (0, 1, 2, 7, 8)),
    Case("WIND_SET", BOOT, arm=lambda a: a[1] == NEWDESK),
    Case("WIND_SET", "A: File > Open", 0, arm=lambda a: a[1] == NAME), Case("WIND_SET", "A: File > Open", 1), Case("WIND_SET", "A: File > Open", 2),
    Case("WIND_SET", "A: File > Open", 3, arm=lambda a: a[1] == HSLIDE), Case("WIND_SET", BY_SIZE, 3, arm=lambda a: a[1] == VSLIDE),
    Case("WIND_CALC", BOOT), Case("WIND_CALC", SHOWN),
    Case("WAIT", BOOT, arm=lambda a: a[0] == 1), Case("WAIT", INFO, arm=lambda a: a[0] == 0),
    Case("WAIT", INFO, arguments=(2,), why="busy 2: any word but 0 is the hourglass (`tst.w`; the desk's callers hand 0 and 1)"),
)


def label(each):
    where = f"arrival {each.nth} of {each.chain}" + (f" (at the desk's {each.over.lower()})" if each.over else "")
    said = f"{each.short.lower()} — " + (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + where
    return said + (f"; {each.wake}" if each.wake else "")


BY_LABEL = {label(each): each for each in CASES}
assert len(BY_LABEL) == len(CASES), "two cases of one name"
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)
A_CLASS = [name for name, each in BY_LABEL.items() if each.why]
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]


@functools.cache
def arrival_of(name):
    """The case's `Arrival`: the chain's own — or, for an argument class, that machine under the case's binding and
    arguments. The arm the case was chosen for is held here."""
    each = BY_LABEL[name]
    arrived = db.arrival(each.over or each.short, each.chain, each.nth)
    assert each.arm is None or each.arm(arrived.arguments), f"{name}: the arrival's arguments {arrived.arguments} are not the arm it names"
    if not each.why:
        return arrived
    arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
    return arrived._replace(short=each.short, arguments=tuple(arguments))


def row_of(name):
    """The case's row, its answer compared exactly where it is HELD (`aes_deskbind.answer_class`)."""
    each, arrived = BY_LABEL[name], arrival_of(name)
    answered = db.SIGNATURES[each.short][0] is not None and db.answer_class(arrived) == db.HELD
    return db.row_of(arrived, label=name.split(" — ", 1)[1], answered=answered, **WAKES.get(each.wake, {}))


# ---- TIER 1 ----------------------------------------------------------------------------------------------------------------------------
@EVERY_CASE
def test_a_binding_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core through the host's scheduler held to the ROM's binding from the same entry — the idles, the
    image at every dispatch and where it returns, the answer where the core has the ROM's word. A leaf that never
    yields is a plain differential. And A NAMED DIVERGENCE IS ONE: the nested release's leftover differs from the
    core's word on the case that names it (never silently equal)."""
    each, arrived = BY_LABEL[name], arrival_of(name)
    if each.short in db.NEVER_YIELD:
        assert db.plain(arrived).answer() == DESKBIND["DESK_BIND_DONE"]
        return
    row = row_of(name)
    ran, the_rom_s = db.held(row), db.the_rom_s_run(row)
    assert ran.answer is None or ran.answer & aes.WORD_MASK == the_rom_s.d0 & aes.WORD_MASK
    assert bool(the_rom_s.idles) == (each.wake in IDLE_WAKES), f"{name}: the ROM's run idles {the_rom_s.idles} time(s)"
    assert ran.entered and ran.entered[-1] == aes.SHELL_PD, f"{name}: the run does not end in the desk's own process"
    if db.answer_class(arrived) == db.NESTED_RELEASE:   # ...RED with its answer compared: the core's 0, the ROM's leftover
        with pytest.raises(AssertionError, match=r"answers 0x0, the ROM's run 0x[0-9a-f]*[1-9a-f]"):
            db.held(row._replace(answered=True))


ARRIVALS, CLASSES = 112, 19


def test_every_binding_has_a_case_at_an_arrival_of_its_own():
    """41 routines, each with a case at its own arrival — form_error's since a chain refuses a delete (the fix pass)
    — and the bindings that ALSO have a labelled argument class, by name: 112 cases at arrivals, 19 classes."""
    at_its_own = {BY_LABEL[name].short for name in AT_ITS_OWN_ARRIVAL}
    assert at_its_own == set(db.SIGNATURES) and len(db.SIGNATURES) == 41
    assert {BY_LABEL[name].short for name in A_CLASS} == {
        "APPL_EXIT", "EVNT_MULTI", "EVNT_BUTTON", "FORM_DIAL", "FORM_ERROR", "GRAF_MOUSE", "GRAF_RUBBOX", "MENU_TNORMAL", "MENU_ICHECK",
        "MENU_IENABLE", "SHEL_GET", "SHEL_PUT", "WAIT"}
    assert (len(AT_ITS_OWN_ARRIVAL), len(A_CLASS)) == (ARRIVALS, CLASSES)


def test_the_arrivals_two_cases_were_chosen_for_are_the_machines_their_names_say():
    """WHAT AN `arm` OF THE ARGUMENTS ALONE CANNOT SAY, read off the arrival's machine: menu_ienable's first arrival
    of "drive A: selected" ENABLES AN ITEM THAT IS DISABLED there (File > Open: the binding's main use, which no case
    held — the first review's surviving mutant, do_chg asked to mind DISABLED); and wind_find's arrival where the
    file is let go on the trash is a point of the desktop whose MIRROR lies in the open window (the two words in the
    other order find another window: the class this arrival replaced)."""
    enabled = arrival_of(next(name for name, each in BY_LABEL.items() if (each.short, each.chain, each.nth) == ("MENU_IENABLE", SELECTED, 0)))
    assert enabled.arguments[2] == 1 and is_disabled(enabled, enabled.arguments[1])
    found = arrival_of(next(name for name, each in BY_LABEL.items() if (each.short, each.chain) == ("WIND_FIND", TRASHED)))
    (window,) = aes_desk.windows(aes_boot.Machine(found.boot))
    x, y = found.arguments
    assert not aes_objects.inside(x, y, window) and aes_objects.inside(y, x, window)


def test_a_byte_move_into_d0_is_no_overwrite_of_the_answer_and_an_ext_w_behind_it_is():
    """`answer_readers`' reading of a byte move (the first review's finding): the ROM's three `move.b …,d0` are each
    followed by `ext.w d0` — the pair makes the word new, NOT READ — and over a listing made here a byte move with a
    read of the word behind it IS a read, where the reading that took any `move` for an overwrite said it was not."""
    for at in BYTE_MOVES_INTO_D0:
        length, text = db.listed_at(at)
        assert text.startswith(db.BYTE_MOVE) and text.endswith(",%d0") and db.listed_at(at + length)[1] == f"{db.EXTEND_THE_BYTE} %d0"
        assert db._followed(at, set()) == {(db.NOT_READ, at + length)}
    byte_then = lambda behind: {0: (2, "moveb %a0@,%d0", None, False), 2: (2, behind, None, False), 4: (2, "movel %a5,%d0", None, False)}   # noqa: E731
    assert db._followed(0, set(), byte_then("tstw %d0")) == {(db.READ, 2)}
    assert db._followed(0, set(), byte_then("extw %d0")) == {(db.NOT_READ, 2)}
    assert db._followed(2, set(), byte_then("extw %d0")) == {(db.READ, 2)}, "an ext.w with no byte move before it reads the answer's byte"
    assert db._followed(0, set(), byte_then("nop")) == {(db.NOT_READ, 4)}, "a longword move is an overwrite"


# ---- D0 AT RETURN -----------------------------------------------------------------------------------------------------------------
NOT_THE_ROM_S = {db.NO_WORD_IN_C: 19, db.NESTED_RELEASE: 3}


def _yielding(names):
    return [name for name in names if BY_LABEL[name].short not in db.NEVER_YIELD]


def test_the_answers_that_are_not_the_rom_s_are_counted_by_name():
    """THE COUNT, over the battery's own cases: how many answer nothing where the ROM's binding answers the word a
    `void` implementation left, and how many meet the nested release's leftover — every other case's answer is the
    ROM's D0.w, or the binding stores no answer on either shore."""
    classes = Counter(db.answer_class(arrival_of(name)) for name in _yielding(BY_LABEL))
    assert {klass: classes[klass] for klass in NOT_THE_ROM_S} == NOT_THE_ROM_S
    nested = {BY_LABEL[name].short for name in BY_LABEL if db.answer_class(arrival_of(name)) == db.NESTED_RELEASE}
    assert nested == {"WIND_OPEN", "WIND_SET"}


BYTE_MOVES_INTO_D0 = (0xfe1ca4, 0xfdb6f8, 0xfed9ec)        # the ROM's three (the first review's count)
# WHO READS EACH BINDING'S ANSWER IN THE ROM: how many instructions of the GEM text read it (through a caller that
# returns it as its own, too). The eleven whose C answers nothing, and the two that meet the leftover, are read by none.
READ_AT = {"APPL_INIT": 1, "APPL_EXIT": 1, "EVNT_MULTI": 3, "FORM_ALERT": 8, "OBJC_FIND": 1, "RSRC_GADDR": 1, "SHEL_WRITE": 1,
           "WIND_FIND": 2, "WIND_CREATE": 1}


def test_no_caller_in_the_rom_reads_an_answer_the_c_does_not_have():
    """BY READING THE CALLERS (`aes_deskbind.answer_readers`: every call site, both arms of every branch, through the
    callers that return it): nine bindings' answers are read; the other thirty-two's by nothing — among them every
    binding of a `void` implementation, every one that stores no answer, wind_open and wind_set."""
    read = {short: len(db.answer_readers(db.entry_of(short))) for short in db.SIGNATURES}
    assert {short: sites for short, sites in read.items() if sites} == READ_AT
    assert all(db.call_sites(short) for short in db.SIGNATURES), "a binding nothing calls has no reader to find"
    unread = set(db.VOID_ANSWERS) | set(db.NO_ANSWER_OF_ITS_OWN) | {"WIND_OPEN", "WIND_SET", "WIND_DELETE", "WIND_CALC"}
    assert not unread & set(READ_AT)


def _left_unread(name):
    each = BY_LABEL[name]
    return not each.why and not each.wake and each.short not in READ_AT


UNREAD_IN_PLACE = [name for name in BY_LABEL if _left_unread(name)]
EVERY_REGISTER_BIT = 0xFFFFFFFF


@pytest.mark.parametrize("name", UNREAD_IN_PLACE)
def test_the_desk_runs_on_alike_whatever_an_unread_binding_leaves_in_d0_and_a0(name):
    """BY RUNS: the ROM's own machine continued IN PLACE from the arrival to the binding's return, and from there to
    the step's end twice — as the binding left D0 and A0, and with every bit of both inverted. The two machines are
    one: megabyte and registers. (A what-if of the ROM alone: nothing of ours runs.)"""
    arrived = arrival_of(name)
    back = db.returned_in_place(arrived)
    assert back is not None, f"{name}: the binding idles before it returns"
    inverted = back._replace(registers={**back.registers, "d0": back.registers["d0"] ^ EVERY_REGISTER_BIT,
                                        "a0": back.registers["a0"] ^ EVERY_REGISTER_BIT})
    as_left, otherwise = (aes_boot.continued(boot, (), arrived.budget, arrived.ends_at, arrived.returns_to) for boot in (back, inverted))
    assert as_left.ram == otherwise.ram and as_left.registers == otherwise.registers


IN_PLACE = [name for name in AT_ITS_OWN_ARRIVAL if not BY_LABEL[name].wake and BY_LABEL[name].short not in db.NEVER_YIELD
            and BY_LABEL[name].short != "EVNT_MULTI"]


@pytest.mark.parametrize("name", IN_PLACE)
def test_the_rom_s_binding_in_place_leaves_the_word_its_harness_run_does(name):
    """THE HARNESS-STACK RUN IS THE MACHINE'S OWN, as far as the answer: the ROM's binding run IN PLACE from the
    arrival (the desk's own stack, to the address its caller's call returns to) leaves the D0.w the ROM's scheduled
    run of the case leaves."""
    back = db.returned_in_place(arrival_of(name))
    assert back is not None, f"{name}: the binding idles before it returns"
    assert back.registers["d0"] & aes.WORD_MASK == db.the_rom_s_run(row_of(name)).d0 & aes.WORD_MASK


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------------
CORES = frozenset(routines.core_symbol(name) for name in db.BINDINGS)


def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_a_binding(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every binding's core linked;
    and no function outside the unbound desk (the held cores and what only they reach) refers to ANY held core — wave
    1b's routines call the bindings by design (form_do's desk_wait, desk_wait's graf_mouse among the bindings' own)."""
    assert not db.bound_referrers(blob, db.BINDINGS)


JUMP = re.compile(r"\tjmp (.*)$")
NAMED = re.compile(r"<([\w.]+)>$")


def test_a_binding_s_yield_is_a_call_and_never_a_jump(blob):
    """`deskbind.c`'s `yield`: no binding JUMPS into the switch (GCC's sibling call, which the bindings of no answer
    would end in: the dispatcher would resume the desk at the binding's CALLER, at no instruction of the routine's
    own). Read off the listing: the only `jmp` in a binding's core is to another binding's (desk_wait's graf_mouse)
    — none to the switch, none through a register."""
    jumps, function = [], None
    for line in transcription.listing(blob.elf).splitlines():
        start = transcription.LISTED_FUNCTION.match(line)
        if start:
            function = start.group(2)
        jump = JUMP.search(line)
        if function in CORES and jump:
            named = NAMED.search(jump.group(1))
            jumps.append((function, named.group(1) if named else jump.group(1)))
    assert all(target in CORES for _function, target in jumps), f"a binding leaves by a jump: {jumps}"


def test_the_table_s_entries_for_the_bindings_stay_the_rom_s_and_no_registry_names_one():
    """...the generator's verdict for each of the 41 is THE ROM'S (`linef_table.LINKED_AND_NOT_FLIPPED`: declared, as
    sh_main's and sh_cmd's are kept), and no registered row is a binding's."""
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    ours = {getattr(addrs, name): name for name in db.BINDINGS}
    verdicts = {ours[entry.target]: entry.verdict for entry in linef_table.entries() if entry.target in ours}
    assert verdicts == {name: linef_table.THE_ROM_S for name in db.BINDINGS}
    assert set(db.BINDINGS) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    registered = [name for name in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS) if name.split(",")[0] in CORES]
    assert not registered
