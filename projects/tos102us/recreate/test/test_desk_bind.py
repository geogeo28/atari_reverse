"""THE DESK'S AES BINDINGS (`src/desk/deskbind.c`; band 6 wave 1a, unit D): the forty routines `$fddde6..$fde4ff` and
desk_wait `$fe1bdc`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F1, FLIPPED: the Line-F
table's entry for each is its thunk, and its cases at arrivals are Tier 3 rows (evnt_multi and objc_draw, held at F1,
flipped at slice F2c; appl_exit, held at F1, flipped at slice F2 with no row — ⚠️ verified-but-unpriced,
`aes_deskbind.VERIFIED_UNPRICED_AT_F2`).

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
  * FLIPPED (band 6 slice F1), held on both blobs: each binding's thunk of the table calls its core, and no function
    outside the unbound desk refers to a core still held; EVERY CASE AT AN ARRIVAL IS A ROW (`ROWS`, below: a row that
    switches, or the two that never yield a plain one), priced by Tier 3 over the arrival's machine (the orchestrator's
    provisional ruling R6).

WHAT IS NOT HELD: an objc_draw of a tree with G_USERDEF objects (the text view: it calls the desk's own draw code
`$fde844`, unit E's, the ROM's still); the argument classes' prices (Tier 1's alone).
"""
import functools
import re
import sys
from collections import Counter, namedtuple
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_boot
import aes_desk
import aes_deskbind as db
import aes_event
import aes_objects
import case
import isr
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


def _four_out_pointers_apart(arrived):
    """graf_mkstate's own arguments, its four out pointers made four DIFFERENT words of the same frame: the arrival's
    x pointer, the two words after it, and its buttons pointer (every desk run hands x, y and keys one address)."""
    x_out, _y_out, buttons_out, _keys_out = arrived.arguments
    return (x_out, x_out + aes.WORD_BYTES, buttons_out, x_out + 2 * aes.WORD_BYTES)


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
    Case("GRAF_MKSTATE", SELECTED, arguments=_four_out_pointers_apart,
         why="four DIFFERENT out pointers (no desk run passes distinct ones: x, y and keys share one address at all three arrivals)"),
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


ARRIVALS, CLASSES = 112, 20


def test_every_binding_has_a_case_at_an_arrival_of_its_own():
    """41 routines, each with a case at its own arrival — form_error's since a chain refuses a delete (the fix pass)
    — and the bindings that ALSO have a labelled argument class, by name: 112 cases at arrivals, 20 classes."""
    at_its_own = {BY_LABEL[name].short for name in AT_ITS_OWN_ARRIVAL}
    assert at_its_own == set(db.SIGNATURES) and len(db.SIGNATURES) == 41
    assert {BY_LABEL[name].short for name in A_CLASS} == {
        "APPL_EXIT", "EVNT_MULTI", "EVNT_BUTTON", "FORM_DIAL", "FORM_ERROR", "GRAF_MKSTATE", "GRAF_MOUSE", "GRAF_RUBBOX", "MENU_TNORMAL",
        "MENU_ICHECK",
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
NOT_THE_ROM_S = {db.NO_WORD_IN_C: 20, db.NESTED_RELEASE: 3}


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


# ---- FLIPPED (band 6 slice F1) ----------------------------------------------------------------------------------------------------
CORES = frozenset(routines.core_symbol(name) for name in db.BINDINGS)


FLIPPED = frozenset(routines.core_symbol(name) for name in db.BINDINGS if name not in db.HELD_AT_F1)


def test_each_flipped_binding_s_thunk_calls_its_core_and_nothing_outside_the_unbound_desk_refers_to_a_held_core(blob):
    """THE FLIP: every flipped binding's core linked and CALLED BY ITS OWN THUNK of the table (`linef_to_<core>`) — and
    the desk's one unbound pin (`aes_deskbind.bound_referrers`) holds for the cores still held, the held bindings'
    among them (no thunk, no function outside the unbound desk refers to one)."""
    graph = transcription.call_graph(blob.elf)
    for core in FLIPPED:
        assert core in graph[_linef_table().THUNK_PREFIX + core], f"{core}'s thunk does not call it"
    assert not db.bound_referrers(blob, db.HELD_AT_F1)


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


def _linef_table():
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


def test_the_table_s_entries_for_the_bindings_are_their_thunks_but_the_held_one_s():
    """...the generator's verdict for each binding is OURS, THROUGH ITS THUNK (none held since slice F2c: `HELD_AT_F1`
    empty, as `LINKED_AND_NOT_FLIPPED` is of them)."""
    linef_table = _linef_table()
    ours = {getattr(addrs, name): name for name in db.BINDINGS}
    verdicts = {ours[entry.target]: (entry.verdict, entry.symbol) for entry in linef_table.entries() if entry.target in ours}
    assert verdicts == {name: ((linef_table.THE_ROM_S, None) if name in db.HELD_AT_F1 else
                               (linef_table.OURS_THROUGH_A_THUNK, linef_table.thunk_symbol(name))) for name in db.BINDINGS}
    assert set(db.BINDINGS) & set(linef_table.LINKED_AND_NOT_FLIPPED) == set(db.HELD_AT_F1)


# ---- band 6 slice F1: THE UNIT'S ROWS ----------------------------------------------------------------------------------------------
# EVERY CASE AT AN ARRIVAL, REGISTERED (the orchestrator's provisional ruling R6: the ROM's arrival machine, taken over
# at the arrival — Tier 3 lays the blob and maps the registry's code slots at the entry, the table and the door's among
# them): a binding that yields is A ROW THAT SWITCHES (`aes_event.register_woken`: settled from the ROM's own runs, its
# by-nature windows dropped with the companion a drop needs — the Tier 1 case above, its wake its own), the two that
# never yield a plain row (`aes.register`). The machine is the arrival's (`aes_deskbind.machine_of`: whole but the
# harness's window); the answer compared where the case holds it. The labelled argument classes stay Tier 1's.
#   * THE X FLAG (`aes_switching.THE_X_FLAG_ALONE`, a by-nature class held to one bit): where a binding's yield follows
#     arithmetic of its own C — the answer's word made the binding's before `dsptch` — the X flag the dispatcher parks
#     is GCC's on our shore and Alcyon's on the ROM's (measured `$00` / `$10` at `$8995`): THOSE ROWS DECLARE IT, and a
#     declaration a row does not need is refused (Tier 3 flips the bit and compares the byte whole).
#   * NO ROW, by name (`NOT_A_ROW`): the cases at an arrival no row can be made at — each said.
X_FLAG_DIFFERS = frozenset(name for name in AT_ITS_OWN_ARRIVAL if (BY_LABEL[name].short, BY_LABEL[name].chain, BY_LABEL[name].nth) in {
    ("OBJC_FIND", SELECTED, 0), ("OBJC_FIND", OPENED, 0), ("OBJC_FIND", DRAGGED, 3), ("WIND_FIND", SELECTED, 0), ("WIND_FIND", OPENED, 0),
    ("WIND_FIND", RUBBER, 0), ("RSRC_GADDR", BOOT, 0), ("RSRC_GADDR", "A: File > Open", 0), ("WIND_GET", OPENED, 1),
    ("SHEL_WRITE", LAUNCHED, 0)})
SCREEN_MANAGER_NO_HISTORY_REACHES = ("its takeover is refused by name (`aes_takeover`): the screen manager stands parked where no "
                                     "history of our build is known to leave it")
MASK_WORD_FOUND = ("its companion re-derives its first door call's delivery over the SETTLED machine — the Line-F mask word "
                   "staged where the run leaves it, `$2000` — and the registry over the arrival's own, `$00f8`: the two "
                   "deliveries differ in that one word (`test_tier3.test_every_dropped_row_has_a_differential_…`), a question "
                   "of the switching registrar's (`aes_switching.register_row`), not of the row: Tier 1 holds the case")
# (form_dial's finish over Desktop Info — its C walks the tree, just_draw `$fe9a88` — was NOT A ROW until slice F2c, its
# row made with objc_draw's so the table moved once: since F2c A ROW WITH NO DOOR, `FORM_DIAL_WALKS_A_TREE` below.)
NOT_A_ROW = {
    **{name: SCREEN_MANAGER_NO_HISTORY_REACHES for name in AT_ITS_OWN_ARRIVAL
       if (BY_LABEL[name].short, BY_LABEL[name].chain, BY_LABEL[name].nth) == ("MENU_IENABLE", BOOT, 0)},
    **{name: MASK_WORD_FOUND for name in AT_ITS_OWN_ARRIVAL
       if BY_LABEL[name].short == "GRAF_RUBBOX" and BY_LABEL[name].wake in (LET_GO_AT_ONCE, BOX_GROWN)},
}
HELD = frozenset(name for name in AT_ITS_OWN_ARRIVAL if db.PREFIX + BY_LABEL[name].short in db.HELD_AT_F1)
# ...and (band 6 slice F2) the cases at arrivals of a binding FLIPPED WITH NO ROW (`aes_deskbind.VERIFIED_UNPRICED_AT_F2`:
# appl_exit's two, ⚠️ verified-but-unpriced by the user's ruling — its reason there).
UNPRICED = frozenset(name for name in AT_ITS_OWN_ARRIVAL if db.PREFIX + BY_LABEL[name].short in db.VERIFIED_UNPRICED_AT_F2)
# A DOOR USER'S ROW (`aes_switching.SwitchingRow.door`) is one whose run arrives at an entry of the event layer's door
# — its call open across the switch, priced on two counts and pinned in `test_tier3.py`'s door users. MEASURED: the
# twelve bindings below arrive there (their AES routine waits: a message, a button, a form, the screen's lock, and since
# slice F2c evnt_multi's events — one call of a rebound entry each); the others yield by their own `dsptch` alone and
# are rows that switch with no door (`door` None), pinned and held here three ways (`NO_DOOR_PRICED`, below).
DOOR_USER_BINDINGS = frozenset(("APPL_WRITE", "EVNT_BUTTON", "EVNT_MULTI", "FORM_ALERT", "FORM_DO", "FORM_ERROR", "GRAF_RUBBOX", "MENU_BAR",
                                "WIND_CLOSE", "WIND_OPEN", "WIND_SET", "WIND_UPDATE"))


def _row_registered(name):
    """The case's row as registered: the X flag declared where `X_FLAG_DIFFERS` says, and no door where it has none."""
    row = row_of(name)._replace(x_flag_differs=name in X_FLAG_DIFFERS)
    return row if BY_LABEL[name].short in DOOR_USER_BINDINGS else row._replace(door=None)


def _registered(name):
    each, arrived = BY_LABEL[name], arrival_of(name)
    if each.short in db.NEVER_YIELD:
        return aes.register(name.split(" — ", 1)[1], db.PREFIX + each.short, arrived.arguments, db.machine_of(arrived))
    return aes_event.register_woken(_row_registered(name))


ROWS = {name: _registered(name) for name in AT_ITS_OWN_ARRIVAL if name not in NOT_A_ROW and name not in HELD | UNPRICED}
ROWS_MADE = ARRIVALS - 3 - 2          # the 112 cases at arrivals less NOT_A_ROW's three, appl_exit's two (none held since F2c)


def test_every_flipped_binding_has_a_row_at_an_arrival_and_every_other_case_at_an_arrival_is_one():
    """EVERY FLIPPED BINDING HAS A ROW (each of its cases at an arrival but NOT_A_ROW's, by name) but the one flipped
    with none (`aes_deskbind.VERIFIED_UNPRICED_AT_F2`: appl_exit, ⚠️ verified-but-unpriced); the held bindings none
    (`aes_deskbind.HELD_AT_F1`); the X flag declared on exactly the rows above."""
    rows = {name.split(", ", 1)[0] for name in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS)} & CORES
    unpriced = {routines.core_symbol(name) for name in db.VERIFIED_UNPRICED_AT_F2}
    assert rows == FLIPPED - unpriced and unpriced <= FLIPPED
    assert len(ROWS) == ROWS_MADE and len(NOT_A_ROW) == 3 and not HELD and len(UNPRICED) == 2
    assert len(X_FLAG_DIFFERS) == 10 and X_FLAG_DIFFERS <= set(ROWS)


# ---- band 6 slice H2: THE TWO HARNESS PIECES objc_draw's FLIP WAS HELD FOR (it flips at F2c) ----------------------------------------
# (P1) A ROW THAT SWITCHES WITH NO DOOR IS SERVED THE WALKED ROUTINES (`aes_switch._served_with_no_door`), as a door child is:
# a no-door companion whose C walks a tree runs its walk — objc_draw's four and form_dial's finish over Desktop Info
# (`FORM_DIAL_WALKS_A_TREE`; each a row since slice F2c). RED before the piece: each refused at just_draw (`$fe9a88`),
# "where this case staged no routine" (the F1 fix pass's measurement).
FORM_DIAL_WALKS_A_TREE = next(name for name in AT_ITS_OWN_ARRIVAL
                              if (BY_LABEL[name].short, BY_LABEL[name].chain, BY_LABEL[name].nth) == ("FORM_DIAL", INFO, 1))
WALKS_A_TREE = sorted(name for name in AT_ITS_OWN_ARRIVAL
                      if BY_LABEL[name].short == "OBJC_DRAW" or name == FORM_DIAL_WALKS_A_TREE)


@pytest.mark.parametrize("name", WALKS_A_TREE)
def test_a_no_door_companion_whose_c_walks_a_tree_is_served_the_walk(name):
    import aes_switching
    row = _row_registered(name)
    assert row.door is None
    aes_switching.companion(row)


def test_the_walk_served_with_no_door_reroutes_no_handed_routine():
    """P1's docstring claim, PINNED (the RH2 review's F5): the walked routines served beside the handed ones are none of
    them — so a C that walks no tree runs every handed routine as before, and only a call into a walker reaches one."""
    walked, handed = set(aes.walkers()), set(aes_event.handed_routines())
    assert walked and handed and not walked & handed, f"served both ways: {sorted(hex(at) for at in walked & handed)}"


# (P2) THE IDLE'S KEYBOARD POLL ON THE DISPATCHER'S STACK — ONE BIOS FRAME, TWO DEPTHS. The F1 fix pass read a refusal of
# those rows' blob differential (27 / 33 bytes at `$8b34..` / `$8b2a..`, by its words a BIOS trap's frame) as a second
# piece owed. MEASURED AT SLICE H2, it is none: its script measured on THE KIT'S OWN BENCH (`isr.blob_named`), which gives
# nothing back, where the battery and the table measure on Tier 3's (`tier3.RomBench`: the dispatcher's stack given back
# over the frames OUR run pushed, from its top down). Every row of the unit that switches with no door stands so (the
# slice's probe: all 64, both benches): the ROM's run leaves poll_key's `trap #13` frame — the idle's keyboard poll — as
# its LOWEST store on the dispatcher's stack, the low end of the drop the registrar derives; our run leaves THE SAME
# FRAME lower (our dispatcher's frames are deeper; `$8b2a` shipped, `$8b34` bench), inside what it pushed. Held on one
# such row, both ways, on each blob.
A_ROW_WITH_NO_DOOR = "aes_desk_graf_mouse, arrival 0 of A: opened"
TRAP_13 = 0x4E4D                        # `trap #13`: the BIOS's


def _the_key_poll_s_return():
    """BY READING: the address after poll_key's `trap #13` (`addrs.VDI_ROM_POLL_KEY`) — where its BIOS frame returns."""
    at = addrs.VDI_ROM_POLL_KEY
    while case.word_in(BASE_IMAGE, at) != TRAP_13:
        at += aes.WORD_BYTES
    return at + aes.WORD_BYTES


def _key_poll_frames(memory, lo, hi):
    """Every BIOS frame of the key poll's in `[lo, hi)` of `memory`: where its saved PC (after the SR word) is that return."""
    return [at for at in range(lo, hi - aes.LONG_BYTES, aes.WORD_BYTES)
            if case.long_in(memory, at + aes.WORD_BYTES) & aes_boot.BUS == _the_key_poll_s_return()]


@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_the_idle_s_key_poll_leaves_one_bios_frame_two_deep_and_tier3_gives_ours_back(monkeypatch, blob_name):
    import aes_switching
    import harness
    from recreate_kit import rom_bench
    row = _registered_row(A_ROW_WITH_NO_DOOR)
    made = aes_switching.settled(row)
    _reference, _watch, final, writes = aes_switching._replayed(row, made.pokes)
    lo, hi = aes_event.DISPATCHER_STACK
    lowest = min(at for at in writes if lo <= at < hi)
    assert _key_poll_frames(final, lo, hi) == [lowest] and any(drop[:2] == (lowest, hi) for drop in made.drops)
    tier3, seen = harness.bench_tier3(), {}
    called = rom_bench.RomBench._call

    def before_it_is_given_back(self, image, symbol, *args, **kwargs):
        ran = called(self, image, symbol, *args, **kwargs)
        seen.update(image=bytes(ran.image), stored=set(tier3.stored_by_the_run_just_made(ran.image)))
        return ran
    monkeypatch.setattr(rom_bench.RomBench, "_call", before_it_is_given_back)
    aes_switching.measured_on(tier3.RomBench(isr.BLOBS[blob_name]), row)
    pushed = tier3._pushed_from_the_top(seen["stored"], lo, hi)
    ours = [at for at in _key_poll_frames(seen["image"], lo, hi) if pushed <= at < lowest]
    assert len(ours) == 1, f"our run's key-poll frame under the ROM's ({lowest:#x}), inside what it pushed ({pushed:#x}..)"
    monkeypatch.undo()
    with pytest.raises(AssertionError, match=f"left different memory than the original at .*first {ours[0]:#x} "):
        aes_switching.measured_on(isr.blob_named(blob_name), row)


# ---- THE ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`: own, the
# caller's own, the calls it is net of, the foreign windows) and by each blob's second differential
# (`aes_switching.measured_on`: the whole run, the ROM's and ours), from the rows as registered; re-pinned from a recorded
# run (`tools/repin.py`), never by hand. No row of these has a turn of ours or a foreign window inside.
# THE DOOR USERS' (`DOOR_USER_BINDINGS`): `test_tier3.py` reads them, its door users that switch.
DOOR_USERS_PRICED = {
    "aes_desk_appl_write, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default)":
        ((9376, 14922), (3790, 5368), 1, (0, 0, 0)),
    'aes_desk_appl_write, arrival 0 of window: View > Show as Text':
        ((8898, 14276), (3790, 5368), 1, (0, 0, 0)),
    'aes_desk_evnt_button, arrival 0 of a rubber box on the desktop, round the trash':
        ((8058, 12896), (3974, 5508), 1, (0, 0, 0)),
    'aes_desk_evnt_button, arrival 0 of drive A: dragged to the trash, Return':
        ((8058, 12896), (3974, 5508), 1, (0, 0, 0)),
    'aes_desk_form_alert, arrival 0 of A: File > Format, Return (the warning answered); Return at the first idle':
        ((185222, 275142), (164486, 241362), 7, (0, 0, 0)),
    'aes_desk_form_alert, arrival 0 of Options > Save Desktop, Return; Return at the first idle':
        ((146090, 227672), (125354, 193892), 7, (0, 0, 0)),
    'aes_desk_form_alert, arrival 0 of file: File > Open (the Show / Print / Cancel alert); Return at the first idle':
        ((187774, 279276), (167038, 245496), 7, (0, 0, 0)),
    'aes_desk_form_do, arrival 0 of A: File > Show Info, Return; Return at the first idle':
        ((42864, 69402), (22484, 36300), 5, (0, 0, 0)),
    'aes_desk_form_do, arrival 0 of Desk > Desktop Info, Return; Return at the first idle':
        ((43470, 70182), (23090, 37080), 5, (0, 0, 0)),
    'aes_desk_form_do, arrival 0 of file: dragged to the trash, OK; Return at the first idle':
        ((42258, 68622), (21878, 35520), 5, (0, 0, 0)),
    'aes_desk_form_error, arrival 0 of file: read-only, dragged to the trash, OK — access denied, Return; Return at the first idle':
        ((161242, 247162), (140506, 213382), 7, (0, 0, 0)),
    'aes_desk_graf_rubbox, arrival 0 of a rubber box on the desktop, round the trash; the button let go at the second door call':
        ((27148, 35248), (21850, 27952), 3, (0, 0, 0)),
    'aes_desk_menu_bar, arrival 0 of file: shown, a key at its end':
        ((5982, 10252), (4488, 6902), 1, (0, 0, 0)),
    'aes_desk_menu_bar, arrival 0 of the boot of the DESKTOP.INF machine':
        ((45876, 62036), (44382, 58686), 1, (0, 0, 0)),
    'aes_desk_wind_close, arrival 0 of window: File > Close Window':
        ((67100, 91566), (65606, 88466), 3, (0, 0, 0)),
    'aes_desk_wind_close, arrival 0 of window: its closer clicked':
        ((66224, 90648), (64730, 87548), 3, (0, 0, 0)),
    'aes_desk_wind_open, arrival 0 of A: opened':
        ((273158, 376902), (266556, 364894), 4, (0, 0, 0)),
    'aes_desk_wind_open, arrival 0 of window: A: opened again (two windows)':
        ((491496, 657914), (484894, 645906), 4, (0, 0, 0)),
    'aes_desk_wind_set, arrival 0 of A: File > Open':
        ((16284, 39458), (15928, 38780), 2, (0, 0, 0)),
    'aes_desk_wind_set, arrival 0 of the boot of the DESKTOP.INF machine':
        ((4622, 7916), (4266, 7238), 2, (0, 0, 0)),
    'aes_desk_wind_set, arrival 1 of A: File > Open':
        ((16232, 39450), (15876, 38772), 2, (0, 0, 0)),
    'aes_desk_wind_set, arrival 2 of A: File > Open':
        ((53214, 98224), (52858, 97546), 2, (0, 0, 0)),
    'aes_desk_wind_set, arrival 3 of A: File > Open':
        ((53254, 98230), (52898, 97552), 2, (0, 0, 0)),
    'aes_desk_wind_set, arrival 3 of window: View > Sort by Size':
        ((53908, 99052), (53552, 98374), 2, (0, 0, 0)),
    'aes_desk_wind_update, arrival 0 of the boot of the DESKTOP.INF machine':
        ((4140, 6196), (3914, 5812), 1, (0, 0, 0)),
    'aes_desk_wind_update, arrival 1 of Desk > Desktop Info, Return':
        ((4084, 6156), (3876, 5790), 1, (0, 0, 0)),
    'aes_desk_wind_update, arrival 2 of A: opened':
        ((4140, 6196), (3914, 5812), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of the boot of the DESKTOP.INF machine; Return at the first idle':
        ((25494, 39408), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of the boot of the DESKTOP.INF machine; the button pressed at the first idle':
        ((26800, 41044), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of Desk > Desktop Info, Return':
        ((7196, 9704), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of window: View > Show as Text':
        ((12940, 19926), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of file: selected; Return at the first idle':
        ((25494, 39408), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        ((24376, 36250), (4448, 5996), 1, (0, 0, 0)),
    'aes_desk_evnt_multi, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        ((28020, 40172), (4448, 5996), 1, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN = {
    "aes_desk_appl_write, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default)":
        {"bench": (21684, 17496), "bench_shipped": (21684, 16750)},
    'aes_desk_appl_write, arrival 0 of window: View > Show as Text':
        {"bench": (21038, 16966), "bench_shipped": (21038, 16144)},
    'aes_desk_evnt_button, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (19658, 15630), "bench_shipped": (19658, 15196)},
    'aes_desk_evnt_button, arrival 0 of drive A: dragged to the trash, Return':
        {"bench": (19658, 15630), "bench_shipped": (19658, 15196)},
    'aes_desk_form_alert, arrival 0 of A: File > Format, Return (the warning answered); Return at the first idle':
        {"bench": (1706084, 1641494), "bench_shipped": (1706084, 1632620)},
    'aes_desk_form_alert, arrival 0 of Options > Save Desktop, Return; Return at the first idle':
        {"bench": (1275038, 1214050), "bench_shipped": (1275038, 1208076)},
    'aes_desk_form_alert, arrival 0 of file: File > Open (the Show / Print / Cancel alert); Return at the first idle':
        {"bench": (1731140, 1665570), "bench_shipped": (1731140, 1657550)},
    'aes_desk_form_do, arrival 0 of A: File > Show Info, Return; Return at the first idle':
        {"bench": (166206, 143018), "bench_shipped": (166206, 142416)},
    'aes_desk_form_do, arrival 0 of Desk > Desktop Info, Return; Return at the first idle':
        {"bench": (166026, 142664), "bench_shipped": (166026, 142062)},
    'aes_desk_form_do, arrival 0 of file: dragged to the trash, OK; Return at the first idle':
        {"bench": (165442, 142428), "bench_shipped": (165442, 141826)},
    'aes_desk_form_error, arrival 0 of file: read-only, dragged to the trash, OK — access denied, Return; Return at the first idle':
        {"bench": (1484962, 1425028), "bench_shipped": (1484962, 1412910)},
    'aes_desk_graf_rubbox, arrival 0 of a rubber box on the desktop, round the trash; the button let go at the second door call':
        {"bench": (151444, 146578), "bench_shipped": (151444, 146372)},
    'aes_desk_menu_bar, arrival 0 of file: shown, a key at its end':
        {"bench": (17014, 12928), "bench_shipped": (17014, 13112)},
    'aes_desk_menu_bar, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (252980, 240076), "bench_shipped": (252980, 239856)},
    'aes_desk_wind_close, arrival 0 of window: File > Close Window':
        {"bench": (777932, 762376), "bench_shipped": (777932, 760294)},
    'aes_desk_wind_close, arrival 0 of window: its closer clicked':
        {"bench": (772238, 756674), "bench_shipped": (772238, 754550)},
    'aes_desk_wind_open, arrival 0 of A: opened':
        {"bench": (1717582, 1646078), "bench_shipped": (1717582, 1647150)},
    'aes_desk_wind_open, arrival 0 of window: A: opened again (two windows)':
        {"bench": (2743662, 2634848), "bench_shipped": (2743662, 2636392)},
    'aes_desk_wind_set, arrival 0 of A: File > Open':
        {"bench": (46220, 23254), "bench_shipped": (46220, 23506)},
    'aes_desk_wind_set, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (14678, 11540), "bench_shipped": (14678, 11660)},
    'aes_desk_wind_set, arrival 1 of A: File > Open':
        {"bench": (46212, 23202), "bench_shipped": (46212, 23454)},
    'aes_desk_wind_set, arrival 2 of A: File > Open':
        {"bench": (227790, 186800), "bench_shipped": (227790, 187516)},
    'aes_desk_wind_set, arrival 3 of A: File > Open':
        {"bench": (227796, 186840), "bench_shipped": (227796, 187556)},
    'aes_desk_wind_set, arrival 3 of window: View > Sort by Size':
        {"bench": (324730, 283714), "bench_shipped": (324730, 284490)},
    'aes_desk_wind_update, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (12958, 11058), "bench_shipped": (12958, 11178)},
    'aes_desk_wind_update, arrival 1 of Desk > Desktop Info, Return':
        {"bench": (12918, 11002), "bench_shipped": (12918, 11122)},
    'aes_desk_wind_update, arrival 2 of A: opened':
        {"bench": (12958, 11058), "bench_shipped": (12958, 11178)},
    'aes_desk_evnt_multi, arrival 0 of the boot of the DESKTOP.INF machine; Return at the first idle':
        {"bench": (67476, 56152), "bench_shipped": (67476, 54966)},
    'aes_desk_evnt_multi, arrival 0 of the boot of the DESKTOP.INF machine; the button pressed at the first idle':
        {"bench": (68092, 56436), "bench_shipped": (68092, 55252)},
    'aes_desk_evnt_multi, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (23228, 21032), "bench_shipped": (23228, 21272)},
    'aes_desk_evnt_multi, arrival 0 of window: View > Show as Text':
        {"bench": (33450, 27924), "bench_shipped": (33450, 27224)},
    'aes_desk_evnt_multi, arrival 0 of file: selected; Return at the first idle':
        {"bench": (67476, 56152), "bench_shipped": (67476, 54966)},
    'aes_desk_evnt_multi, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        {"bench": (63298, 53794), "bench_shipped": (63298, 52836)},
    'aes_desk_evnt_multi, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        {"bench": (73274, 63642), "bench_shipped": (73274, 62810)},
}
# ...AND THE ROWS WITH NO DOOR, each held here THREE WAYS (`test_aes_switching_rows_held.py`'s rule): its PREMISE on the
# ROM's own run (the idles and polls its deliveries are taken at, its process, the processes entered, its answer), its
# WHOLE RUN on each blob, and WHAT THE TABLE PRICES of it. A premise is `aes_switching.Premise`'s fields.
NO_DOOR_PREMISES = {
    'aes_desk_evnt_dclick, arrival 0 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 3, ()),
    'aes_desk_evnt_dclick, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), 3, ()),
    'aes_desk_form_center, arrival 0 of A: File > Show Info, Return':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_form_center, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_form_center, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_form_dial, arrival 0 of A: Options > Install Disk Drive, Return':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_form_dial, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_graf_growbox, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_growbox, arrival 0 of window: its fuller clicked':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mkstate, arrival 0 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mkstate, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mkstate, arrival 0 of file: selected':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mouse, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mouse, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mouse, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_mouse, arrival 1 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_shrinkbox, arrival 0 of folder: File > Close':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_shrinkbox, arrival 0 of window: File > Close Window':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_graf_shrinkbox, arrival 0 of window: its closer clicked':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_menu_icheck, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_icheck, arrival 0 of window: View > Show as Text':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_icheck, arrival 1 of window: View > Show as Text':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_ienable, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_ienable, arrival 23 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_tnormal, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_menu_tnormal, arrival 0 of window: View > Sort by Size':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_objc_add, arrival 0 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_add, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_add, arrival 0 of window: View > Sort by Size':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_change, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_change, arrival 1 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_find, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 8, ()),
    'aes_desk_objc_find, arrival 0 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_objc_find, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), 8, ()),
    'aes_desk_objc_find, arrival 3 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e,), 6, ()),
    'aes_desk_objc_offset, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e,), 65535, ()),
    'aes_desk_objc_offset, arrival 0 of folder: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e,), 65535, ()),
    'aes_desk_objc_order, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_order, arrival 0 of window: File > Close Window':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_rsrc_gaddr, arrival 0 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_rsrc_gaddr, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_get, arrival 0 of Options > Save Desktop, Return':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_get, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_put, arrival 0 of Options > Save Desktop, Return':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_put, arrival 0 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_write, arrival 0 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_shel_write, arrival 0 of files: the program double-clicked — launched':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_wait, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_wait, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_wind_calc, arrival 0 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 157, ()),
    'aes_desk_wind_calc, arrival 0 of the boot of the DESKTOP.INF machine':
        ((), 0, 0xae5e, (0xae5e,), 157, ()),
    'aes_desk_wind_create, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_wind_create, arrival 0 of window: A: opened again (two windows)':
        ((), 0, 0xae5e, (0xae5e,), 2, ()),
    'aes_desk_wind_delete, arrival 0 of window: File > Close Window':
        ((), 0, 0xae5e, (0xae5e,), 40080, ()),
    'aes_desk_wind_delete, arrival 0 of window: its closer clicked':
        ((), 0, 0xae5e, (0xae5e,), 40080, ()),
    'aes_desk_wind_find, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_wind_find, arrival 0 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_wind_find, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_wind_find, arrival 2 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_wind_get, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 50374, ()),
    'aes_desk_wind_get, arrival 1 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_desk_wind_get, arrival 2 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    'aes_desk_wind_get, arrival 7 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 44, ()),
    'aes_desk_wind_get, arrival 8 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 48, ()),
    'aes_desk_objc_draw, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_draw, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_draw, arrival 2 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_objc_draw, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_form_dial, arrival 1 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
}
NO_DOOR_PRICED = {
    'aes_desk_evnt_dclick, arrival 0 of file: shown, a key at its end':
        ((4118, 5786), None, None, (0, 0, 0)),
    'aes_desk_evnt_dclick, arrival 0 of the boot of the DESKTOP.INF machine':
        ((4118, 5786), None, None, (0, 0, 0)),
    'aes_desk_form_center, arrival 0 of A: File > Show Info, Return':
        ((4850, 6980), None, None, (0, 0, 0)),
    'aes_desk_form_center, arrival 0 of Desk > Desktop Info, Return':
        ((4850, 6980), None, None, (0, 0, 0)),
    'aes_desk_form_center, arrival 0 of file: dragged to the trash, OK':
        ((4854, 6980), None, None, (0, 0, 0)),
    'aes_desk_form_dial, arrival 0 of A: Options > Install Disk Drive, Return':
        ((5182, 6938), None, None, (0, 0, 0)),
    'aes_desk_form_dial, arrival 0 of Desk > Desktop Info, Return':
        ((5182, 6938), None, None, (0, 0, 0)),
    'aes_desk_graf_growbox, arrival 0 of A: opened':
        ((289300, 344778), None, None, (0, 0, 0)),
    'aes_desk_graf_growbox, arrival 0 of window: its fuller clicked':
        ((208894, 248258), None, None, (0, 0, 0)),
    'aes_desk_graf_mkstate, arrival 0 of a rubber box on the desktop, round the trash':
        ((3998, 5652), None, None, (0, 0, 0)),
    'aes_desk_graf_mkstate, arrival 0 of drive A: selected':
        ((3998, 5652), None, None, (0, 0, 0)),
    'aes_desk_graf_mkstate, arrival 0 of file: selected':
        ((3998, 5652), None, None, (0, 0, 0)),
    'aes_desk_graf_mouse, arrival 0 of A: opened':
        ((4258, 5978), None, None, (0, 0, 0)),
    'aes_desk_graf_mouse, arrival 0 of Desk > Desktop Info, Return':
        ((6780, 9954), None, None, (0, 0, 0)),
    'aes_desk_graf_mouse, arrival 0 of the boot of the DESKTOP.INF machine':
        ((6780, 9958), None, None, (0, 0, 0)),
    'aes_desk_graf_mouse, arrival 1 of A: opened':
        ((4186, 5850), None, None, (0, 0, 0)),
    'aes_desk_graf_shrinkbox, arrival 0 of folder: File > Close':
        ((187374, 219384), None, None, (0, 0, 0)),
    'aes_desk_graf_shrinkbox, arrival 0 of window: File > Close Window':
        ((266060, 317318), None, None, (0, 0, 0)),
    'aes_desk_graf_shrinkbox, arrival 0 of window: its closer clicked':
        ((266060, 317318), None, None, (0, 0, 0)),
    'aes_desk_menu_icheck, arrival 0 of the boot of the DESKTOP.INF machine':
        ((5384, 7768), None, None, (0, 0, 0)),
    'aes_desk_menu_icheck, arrival 0 of window: View > Show as Text':
        ((5392, 7768), None, None, (0, 0, 0)),
    'aes_desk_menu_icheck, arrival 1 of window: View > Show as Text':
        ((5384, 7768), None, None, (0, 0, 0)),
    'aes_desk_menu_ienable, arrival 0 of drive A: selected':
        ((5502, 7856), None, None, (0, 0, 0)),
    'aes_desk_menu_ienable, arrival 23 of drive A: selected':
        ((5496, 7846), None, None, (0, 0, 0)),
    'aes_desk_menu_tnormal, arrival 0 of Desk > Desktop Info, Return':
        ((11082, 17324), None, None, (0, 0, 0)),
    'aes_desk_menu_tnormal, arrival 0 of window: View > Sort by Size':
        ((11638, 17968), None, None, (0, 0, 0)),
    'aes_desk_objc_add, arrival 0 of A: File > Open':
        ((4070, 6000), None, None, (0, 0, 0)),
    'aes_desk_objc_add, arrival 0 of A: opened':
        ((4070, 6000), None, None, (0, 0, 0)),
    'aes_desk_objc_add, arrival 0 of window: View > Sort by Size':
        ((4070, 6000), None, None, (0, 0, 0)),
    'aes_desk_objc_change, arrival 0 of drive A: selected':
        ((6032, 8236), None, None, (0, 0, 0)),
    'aes_desk_objc_change, arrival 1 of A: opened':
        ((6032, 8236), None, None, (0, 0, 0)),
    'aes_desk_objc_find, arrival 0 of A: opened':
        ((7374, 12378), None, None, (0, 0, 0)),
    'aes_desk_objc_find, arrival 0 of a rubber box on the desktop, round the trash':
        ((9862, 17354), None, None, (0, 0, 0)),
    'aes_desk_objc_find, arrival 0 of drive A: selected':
        ((7374, 12378), None, None, (0, 0, 0)),
    'aes_desk_objc_find, arrival 3 of drive A: dragged to the trash, Return':
        ((9656, 16876), None, None, (0, 0, 0)),
    'aes_desk_objc_offset, arrival 0 of file: dragged to the trash, OK':
        ((4610, 7726), None, None, (0, 0, 0)),
    'aes_desk_objc_offset, arrival 0 of folder: dragged to the trash, OK':
        ((4716, 7880), None, None, (0, 0, 0)),
    'aes_desk_objc_order, arrival 0 of A: opened':
        ((6172, 10154), None, None, (0, 0, 0)),
    'aes_desk_objc_order, arrival 0 of window: File > Close Window':
        ((5676, 9450), None, None, (0, 0, 0)),
    'aes_desk_rsrc_gaddr, arrival 0 of A: File > Open':
        ((4448, 7268), None, None, (0, 0, 0)),
    'aes_desk_rsrc_gaddr, arrival 0 of the boot of the DESKTOP.INF machine':
        ((4448, 6862), None, None, (0, 0, 0)),
    'aes_desk_shel_get, arrival 0 of Options > Save Desktop, Return':
        ((7578, 9414), None, None, (0, 0, 0)),
    'aes_desk_shel_get, arrival 0 of the boot of the DESKTOP.INF machine':
        ((61338, 63174), None, None, (0, 0, 0)),
    'aes_desk_shel_put, arrival 0 of Options > Save Desktop, Return':
        ((57224, 59060), None, None, (0, 0, 0)),
    'aes_desk_shel_put, arrival 0 of file: shown, a key at its end':
        ((57224, 59060), None, None, (0, 0, 0)),
    'aes_desk_shel_write, arrival 0 of file: shown, a key at its end':
        ((11110, 12950), None, None, (0, 0, 0)),
    'aes_desk_shel_write, arrival 0 of files: the program double-clicked — launched':
        ((11112, 12942), None, None, (0, 0, 0)),
    'aes_desk_wait, arrival 0 of Desk > Desktop Info, Return':
        ((6694, 10324), None, None, (0, 0, 0)),
    'aes_desk_wait, arrival 0 of the boot of the DESKTOP.INF machine':
        ((6696, 10334), None, None, (0, 0, 0)),
    'aes_desk_wind_calc, arrival 0 of file: shown, a key at its end':
        ((4486, 6198), None, None, (0, 0, 0)),
    'aes_desk_wind_calc, arrival 0 of the boot of the DESKTOP.INF machine':
        ((4486, 6198), None, None, (0, 0, 0)),
    'aes_desk_wind_create, arrival 0 of A: opened':
        ((5516, 10328), None, None, (0, 0, 0)),
    'aes_desk_wind_create, arrival 0 of window: A: opened again (two windows)':
        ((5570, 10442), None, None, (0, 0, 0)),
    'aes_desk_wind_delete, arrival 0 of window: File > Close Window':
        ((3860, 5568), None, None, (0, 0, 0)),
    'aes_desk_wind_delete, arrival 0 of window: its closer clicked':
        ((3860, 5568), None, None, (0, 0, 0)),
    'aes_desk_wind_find, arrival 0 of A: opened':
        ((5280, 8044), None, None, (0, 0, 0)),
    'aes_desk_wind_find, arrival 0 of a rubber box on the desktop, round the trash':
        ((5280, 8044), None, None, (0, 0, 0)),
    'aes_desk_wind_find, arrival 0 of drive A: selected':
        ((5280, 8044), None, None, (0, 0, 0)),
    'aes_desk_wind_find, arrival 2 of file: dragged to the trash, OK':
        ((6400, 10220), None, None, (0, 0, 0)),
    'aes_desk_wind_get, arrival 0 of A: opened':
        ((4780, 7368), None, None, (0, 0, 0)),
    'aes_desk_wind_get, arrival 1 of A: opened':
        ((5812, 9024), None, None, (0, 0, 0)),
    'aes_desk_wind_get, arrival 2 of A: opened':
        ((5226, 8074), None, None, (0, 0, 0)),
    'aes_desk_wind_get, arrival 7 of A: opened':
        ((4416, 6046), None, None, (0, 0, 0)),
    'aes_desk_wind_get, arrival 8 of A: opened':
        ((4348, 6046), None, None, (0, 0, 0)),
    'aes_desk_objc_draw, arrival 0 of Desk > Desktop Info, Return':
        ((94054, 111362), None, None, (0, 0, 0)),
    'aes_desk_objc_draw, arrival 0 of A: opened':
        ((37564, 46460), None, None, (0, 0, 0)),
    'aes_desk_objc_draw, arrival 2 of A: opened':
        ((27280, 33544), None, None, (0, 0, 0)),
    'aes_desk_objc_draw, arrival 0 of drive A: selected':
        ((37564, 46460), None, None, (0, 0, 0)),
    'aes_desk_form_dial, arrival 1 of Desk > Desktop Info, Return':
        ((72750, 86638), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    'aes_desk_evnt_dclick, arrival 0 of file: shown, a key at its end':
        {"bench": (12548, 11036), "bench_shipped": (12548, 11156)},
    'aes_desk_evnt_dclick, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (12548, 11036), "bench_shipped": (12548, 11156)},
    'aes_desk_form_center, arrival 0 of A: File > Show Info, Return':
        {"bench": (13742, 11830), "bench_shipped": (13742, 12056)},
    'aes_desk_form_center, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (13742, 11830), "bench_shipped": (13742, 12056)},
    'aes_desk_form_center, arrival 0 of file: dragged to the trash, OK':
        {"bench": (13742, 11834), "bench_shipped": (13742, 12060)},
    'aes_desk_form_dial, arrival 0 of A: Options > Install Disk Drive, Return':
        {"bench": (16358, 14808), "bench_shipped": (16358, 14970)},
    'aes_desk_form_dial, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (16358, 14808), "bench_shipped": (16358, 14970)},
    'aes_desk_graf_growbox, arrival 0 of A: opened':
        {"bench": (1976578, 1968092), "bench_shipped": (1976578, 1963120)},
    'aes_desk_graf_growbox, arrival 0 of window: its fuller clicked':
        {"bench": (1549680, 1543544), "bench_shipped": (1549680, 1540096)},
    'aes_desk_graf_mkstate, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (12414, 10916), "bench_shipped": (12414, 11036)},
    'aes_desk_graf_mkstate, arrival 0 of drive A: selected':
        {"bench": (12414, 10916), "bench_shipped": (12414, 11036)},
    'aes_desk_graf_mkstate, arrival 0 of file: selected':
        {"bench": (12414, 10916), "bench_shipped": (12414, 11036)},
    'aes_desk_graf_mouse, arrival 0 of A: opened':
        {"bench": (16852, 15336), "bench_shipped": (16852, 15500)},
    'aes_desk_graf_mouse, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (38792, 36108), "bench_shipped": (38792, 36118)},
    'aes_desk_graf_mouse, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (40054, 37366), "bench_shipped": (40054, 37376)},
    'aes_desk_graf_mouse, arrival 1 of A: opened':
        {"bench": (28356, 27084), "bench_shipped": (28356, 27008)},
    'aes_desk_graf_shrinkbox, arrival 0 of folder: File > Close':
        {"bench": (1232986, 1229012), "bench_shipped": (1232986, 1226628)},
    'aes_desk_graf_shrinkbox, arrival 0 of window: File > Close Window':
        {"bench": (1820194, 1812334), "bench_shipped": (1820194, 1807620)},
    'aes_desk_graf_shrinkbox, arrival 0 of window: its closer clicked':
        {"bench": (1818190, 1810330), "bench_shipped": (1818190, 1805616)},
    'aes_desk_menu_icheck, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (14530, 12302), "bench_shipped": (14530, 12422)},
    'aes_desk_menu_icheck, arrival 0 of window: View > Show as Text':
        {"bench": (14530, 12310), "bench_shipped": (14530, 12430)},
    'aes_desk_menu_icheck, arrival 1 of window: View > Show as Text':
        {"bench": (14530, 12302), "bench_shipped": (14530, 12422)},
    'aes_desk_menu_ienable, arrival 0 of drive A: selected':
        {"bench": (14618, 12420), "bench_shipped": (14618, 12540)},
    'aes_desk_menu_ienable, arrival 23 of drive A: selected':
        {"bench": (14608, 12414), "bench_shipped": (14608, 12534)},
    'aes_desk_menu_tnormal, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (57510, 52034), "bench_shipped": (57510, 52060)},
    'aes_desk_menu_tnormal, arrival 0 of window: View > Sort by Size':
        {"bench": (62876, 57544), "bench_shipped": (62876, 57490)},
    'aes_desk_objc_add, arrival 0 of A: File > Open':
        {"bench": (12762, 10988), "bench_shipped": (12762, 11108)},
    'aes_desk_objc_add, arrival 0 of A: opened':
        {"bench": (12762, 10988), "bench_shipped": (12762, 11108)},
    'aes_desk_objc_add, arrival 0 of window: View > Sort by Size':
        {"bench": (12762, 10988), "bench_shipped": (12762, 11108)},
    'aes_desk_objc_change, arrival 0 of drive A: selected':
        {"bench": (17656, 15658), "bench_shipped": (17656, 15820)},
    'aes_desk_objc_change, arrival 1 of A: opened':
        {"bench": (17656, 15658), "bench_shipped": (17656, 15820)},
    'aes_desk_objc_find, arrival 0 of A: opened':
        {"bench": (19140, 14774), "bench_shipped": (19140, 14628)},
    'aes_desk_objc_find, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (24116, 17740), "bench_shipped": (24116, 17332)},
    'aes_desk_objc_find, arrival 0 of drive A: selected':
        {"bench": (19140, 14774), "bench_shipped": (19140, 14628)},
    'aes_desk_objc_find, arrival 3 of drive A: dragged to the trash, Return':
        {"bench": (23638, 17536), "bench_shipped": (23638, 17126)},
    'aes_desk_objc_offset, arrival 0 of file: dragged to the trash, OK':
        {"bench": (14488, 11528), "bench_shipped": (14488, 11648)},
    'aes_desk_objc_offset, arrival 0 of folder: dragged to the trash, OK':
        {"bench": (14642, 11634), "bench_shipped": (14642, 11754)},
    'aes_desk_objc_order, arrival 0 of A: opened':
        {"bench": (16916, 13088), "bench_shipped": (16916, 13210)},
    'aes_desk_objc_order, arrival 0 of window: File > Close Window':
        {"bench": (16212, 12592), "bench_shipped": (16212, 12714)},
    'aes_desk_rsrc_gaddr, arrival 0 of A: File > Open':
        {"bench": (14030, 11364), "bench_shipped": (14030, 11486)},
    'aes_desk_rsrc_gaddr, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (13624, 11364), "bench_shipped": (13624, 11486)},
    'aes_desk_shel_get, arrival 0 of Options > Save Desktop, Return':
        {"bench": (16176, 17906), "bench_shipped": (16176, 14724)},
    'aes_desk_shel_get, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (69936, 121586), "bench_shipped": (69936, 68484)},
    'aes_desk_shel_put, arrival 0 of Options > Save Desktop, Return':
        {"bench": (65822, 129798), "bench_shipped": (65822, 64370)},
    'aes_desk_shel_put, arrival 0 of file: shown, a key at its end':
        {"bench": (65822, 129798), "bench_shipped": (65822, 64370)},
    'aes_desk_shel_write, arrival 0 of file: shown, a key at its end':
        {"bench": (19712, 26460), "bench_shipped": (19712, 18364)},
    'aes_desk_shel_write, arrival 0 of files: the program double-clicked — launched':
        {"bench": (19704, 26462), "bench_shipped": (19704, 18366)},
    'aes_desk_wait, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (39162, 36022), "bench_shipped": (39162, 36032)},
    'aes_desk_wait, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (40430, 37282), "bench_shipped": (40430, 37292)},
    'aes_desk_wind_calc, arrival 0 of file: shown, a key at its end':
        {"bench": (12960, 11404), "bench_shipped": (12960, 11524)},
    'aes_desk_wind_calc, arrival 0 of the boot of the DESKTOP.INF machine':
        {"bench": (12960, 11404), "bench_shipped": (12960, 11524)},
    'aes_desk_wind_create, arrival 0 of A: opened':
        {"bench": (17090, 12528), "bench_shipped": (17090, 12830)},
    'aes_desk_wind_create, arrival 0 of window: A: opened again (two windows)':
        {"bench": (17204, 12582), "bench_shipped": (17204, 12884)},
    'aes_desk_wind_delete, arrival 0 of window: File > Close Window':
        {"bench": (12330, 10778), "bench_shipped": (12330, 10898)},
    'aes_desk_wind_delete, arrival 0 of window: its closer clicked':
        {"bench": (12330, 10778), "bench_shipped": (12330, 10898)},
    'aes_desk_wind_find, arrival 0 of A: opened':
        {"bench": (14806, 12502), "bench_shipped": (14806, 12594)},
    'aes_desk_wind_find, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (14806, 12502), "bench_shipped": (14806, 12594)},
    'aes_desk_wind_find, arrival 0 of drive A: selected':
        {"bench": (14806, 12502), "bench_shipped": (14806, 12594)},
    'aes_desk_wind_find, arrival 2 of file: dragged to the trash, OK':
        {"bench": (16982, 13862), "bench_shipped": (16982, 13822)},
    'aes_desk_wind_get, arrival 0 of A: opened':
        {"bench": (14130, 11730), "bench_shipped": (14130, 11910)},
    'aes_desk_wind_get, arrival 1 of A: opened':
        {"bench": (15786, 12792), "bench_shipped": (15786, 13034)},
    'aes_desk_wind_get, arrival 2 of A: opened':
        {"bench": (14836, 12174), "bench_shipped": (14836, 12356)},
    'aes_desk_wind_get, arrival 7 of A: opened':
        {"bench": (12808, 11334), "bench_shipped": (12808, 11454)},
    'aes_desk_wind_get, arrival 8 of A: opened':
        {"bench": (12808, 11266), "bench_shipped": (12808, 11386)},
    'aes_desk_objc_draw, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (1115396, 1112218), "bench_shipped": (1115396, 1108464)},
    'aes_desk_objc_draw, arrival 0 of A: opened':
        {"bench": (350860, 346906), "bench_shipped": (350860, 345980)},
    'aes_desk_objc_draw, arrival 2 of A: opened':
        {"bench": (418522, 415890), "bench_shipped": (418522, 414914)},
    'aes_desk_objc_draw, arrival 0 of drive A: selected':
        {"bench": (350860, 346906), "bench_shipped": (350860, 345980)},
    'aes_desk_form_dial, arrival 1 of Desk > Desktop Info, Return':
        {"bench": (984526, 982092), "bench_shipped": (984526, 978258)},
}


def _registered_row(name):
    """The registered switching row of that name."""
    return aes_event.SWITCHING_ROWS[name].row


def test_the_pinned_rows_are_the_registered_ones_and_split_by_their_door():
    """EVERY ROW OF THE UNIT THAT SWITCHES IS PINNED ONCE: a door user's in `DOOR_USERS_*`, any other here."""
    import aes_switching
    switching = {aes_switching.row_name(row) for row in ROWS.values() if hasattr(row, "door")}
    assert set(DOOR_USERS_PRICED) | set(NO_DOOR_PRICED) == switching and not set(DOOR_USERS_PRICED) & set(NO_DOOR_PRICED)
    assert set(DOOR_USERS_PRICED) == set(DOOR_USERS_WHOLE_RUN) and set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN) == set(NO_DOOR_PREMISES)
    assert all((_registered_row(name).door is not None) == (name in DOOR_USERS_PRICED) for name in switching)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    import aes_switching
    aes_switching.vet_the_premise(_registered_row(name), aes_switching.Premise(*NO_DOOR_PREMISES[name]))


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    import aes_switching
    premise = aes_switching.Premise(*NO_DOOR_PREMISES[name])
    aes_switching.vet_on_a_blob(blob, _registered_row(name), premise, NO_DOOR_PRICED[name][3], NO_DOOR_WHOLE_RUN[name])


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    import aes_switching
    aes_switching.vet_the_table_s_price(_registered_row(name), aes_switching.Priced(*NO_DOOR_PRICED[name]))
