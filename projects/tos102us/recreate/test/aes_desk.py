r"""THE HANDS — a user's acts on the desk, as chains of receptions over THE ROM'S OWN MACHINE (band 6 wave 0, slice H;
`test_aes_desk_rom.py`).

Band 6's subject is the desk, and a desk routine runs when a hand does something: a menu dropped, an icon dragged, a
dialog answered. This module is the hand. NOTHING OF OURS RUNS HERE — every machine below is one the ROM booted, with
no blob in it (a machine that holds one is refused by name), so nothing here is "ours ran": it is the campaign the
later waves' rows are arrivals of, and the ROM-side column of the invariants slice B will hold both shores to.

  * POINTS ARE READ OFF THE MACHINE'S OWN TREES (`menu_point`, `icon_point`, `drive_point`, `top_window`,
    `button_point`): the menu tree gl_mntree names, the desk's own object block, the AES's window tree, the tree of
    the dialog the desk's process is parked in — where ob_offset puts each object on THIS machine. An item that is not
    there, that is there twice, that is out of sight or that is DISABLED is refused by name: a click on a disabled
    item is a chain that idles and did nothing. (And a dialog's Return is ITS DEFAULT, which is not always its OK: the
    delete dialog's is Cancel.)
  * A HAND IS A DELIVERY through the device model `aes_boot.continued` has (`the mouse moved`, IKBD bytes through the
    ROM's ACIA handler, the system timer's ticks) — never a poke of the AES's or the desk's state.
  * A CHAIN is steps, each one continuation: to the machine's next idle, or — for the two acts that wait for a hand
    WITHOUT idling — to A NAMED STOP (`STOPS`: the file viewer's two key waits, the rubber box's poll), where the next
    step's reception is taken (`aes_boot.continued`'s `until` and `at`).
  * EVERY STEP IS PROFILED (`stepped`, a kept derivation): the cycles at each PC of the ROM's GEM text, the OS under
    it, and the Line-F handler's copy. WHAT A CHAIN REACHED IS READ OFF THAT PROFILE AND NOWHERE ELSE (`entered`,
    `reach`: a routine is reached when its first instruction ran) — never off the chain's name: a held drag that idles
    one step early looks done and is not (the design's risk 7), and two "Show Info" chains of the measuring pass ran
    nothing at all (the oracle's CPU executed their call word as MOVE16 — fixed in the kit, band 6 slice M16).
  * A STACK'S DEPTH PER CHAIN IS READ OFF THE RUNS' WRITE LEDGERS (`depths`: the lowest byte of the stack a step's
    run stored, `Boot.stored`), not off residue: what THIS chain's steps stored, whatever an earlier chain left.
    ITS TWO LIMITS, as `aes_stack.py` says of every measured depth: a depth is the lowest STORE, not the lowest SP,
    and no interrupt is taken at the deepest point — a reception's handlers run on the harness's own stack.

THE MACHINES (`MACHINES`): the DESKTOP.INF machine (the fourth capture: one file on the disk) in both views, and THE
FILES MACHINE (the fifth, `make preinit-files`: files, a folder with a file in it, a program).

WHAT NO CHAIN HERE DOES, each for a reason the device model has (the design's 3.3): a resolution change, a critical
error, the screen dump — AND A FOLDER THAT WAS ON THE DISK FROM POWER-ON OPENED: the desk forces a media
change and GEMDOS's next call reads the folder's cluster before it asks Mediach (no chain made since band 6 wave 4,
whose model answers that read E_CHNG as the ROM's driver does, has tried it; a folder made in the session opens: its
cluster is in GEMDOS's buffers). The files machine's folder is copied into and deleted, not opened. (Print, format,
disk copy and drive B: are band 6 wave 4's chains, over `aes_boot`'s W6-R9 devices: the block at the end.)
"""
import functools
from collections import namedtuple
from pathlib import Path

import derived
from harness import addrs, emu

import aes
import aes_boot
import aes_event
import aes_gemctrl
import aes_objects
import case
from aes_boot import Refused

BUS = aes_boot.BUS
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES

# ---- BAND 6'S ROUTINES: what a reach table has a row for ------------------------------------------------------------------------
# The desk's range and the utilities', the desk-only leaves filed in AES modules, less the seven routines of those
# ranges bands 0-5 own already (the design's §1: 244 routines). WHERE A ROUTINE BEGINS is the AES map's inventory
# (`aes_map/inventory.txt`, one line a routine) — read here, outside every kept derivation: the file is not in the
# tree's key.
INVENTORY = Path(__file__).resolve().parents[2] / "aes_map" / "inventory.txt"
INVENTORY_ADDRESS_DIGITS = 6
DESK_TEXT = (0xfdb014, 0xfe387c)        # deskapp's first routine .. the DOS glue's first: units A-L
UTILITY_TEXT = (0xfed478, 0xfee498)     # the cartridge pair, the show / print engine, format, copy, the BIOS door, trp14
DESK_LEAVES_IN_AES_MODULES = (          # unit O: gemgraf's three, thirteen entries of the DOS glue, the hardcopy leaf
    0xfda8a8, 0xfdae96, 0xfdaee2, 0xfe3a7c, 0xfe3ab0, 0xfe3ac4, 0xfe3ae8, 0xfe3b02, 0xfe3b6a, 0xfe3ba0, 0xfe3be8,
    0xfe3bfa, 0xfe3c16, 0xfe3c1a, 0xfe3c1e, 0xfe3c22, 0xfe8862)
OWNED_BY_BANDS_0_TO_5 = (               # app_reschange, set_defdrv, far_call, desk_rsrc_free, cart_init, cart_find, trp14
    0xfdbae0, 0xfdbecc, 0xfddec6, addrs.AES_ROM_DESK_RSRC_FREE, 0xfed478, 0xfed4be, 0xfee488)


@functools.cache
def inventoried():
    """Every routine start the AES map's inventory lists, in address order."""
    starts = []
    for line in INVENTORY.read_text().splitlines():
        try:
            starts.append(int(line[:INVENTORY_ADDRESS_DIGITS], 16))
        except ValueError:
            continue                    # the header line
    return tuple(sorted(starts))


@functools.cache
def routines():
    """BAND 6'S ROUTINES (above), by their first instruction's address, in address order."""
    in_the_ranges = {start for start in inventoried() for lo, hi in (DESK_TEXT, UTILITY_TEXT) if lo <= start < hi}
    return tuple(sorted((in_the_ranges | set(DESK_LEAVES_IN_AES_MODULES)) - set(OWNED_BY_BANDS_0_TO_5)))


# ---- POINTS, READ OFF THE MACHINE'S OWN TREES -------------------------------------------------------------------------------------
MENU_OBJECTS_AT_MOST = 256              # more objects than any menu tree has: a tree whose last object is not flagged
MENU_POINT_INSET = 12                   # how far into a title or an item the point is taken (never past its middle)
ICON_IMAGE_HALF = 16                    # an icon's image is 32 pixels square: its centre, from the ICONBLK's own origin
ICON_EDGE_INSET = 4                     # ...and how far inside an edge of it a point is taken where its centre is covered
SIZE_FIELDS = ("WIDTH", "HEIGHT")
GADGET_INSET_X, GADGET_INSET_Y = 6, 5   # inside a window's corner gadget (the closer's box, the fuller's), from the window's corner
DISABLED = 1 << aes.OB_STATE_DISABLED_BIT
SELECTED = 1 << aes.OB_STATE_SELECTED_BIT
CHECKED = 1 << aes.OB_STATE_CHECKED_BIT
# A window's scroll gadgets, from its bottom right corner (the files window's: arrows a character cell square, the
# vertical bar's page area between the slider and the down arrow)
SCROLL_GADGET_INSET = 8                 # into the right column (the vertical bar's) or the bottom row (the horizontal's)
DOWN_ARROW_FROM_THE_BOTTOM = 28         # the down arrow, above the sizer
PAGE_AREA_FROM_THE_BOTTOM = 60          # the vertical bar under its slider: a click there is a page down
RIGHT_ARROW_FROM_THE_RIGHT = 28         # the right arrow, left of the sizer


def text_at(ram, at):
    """The NUL-ended text the machine holds at `at`."""
    at &= BUS
    return bytes(ram[at:ram.index(b"\0", at)]).decode("latin1")


def _object_type(ram, tree, index):
    return case.word_in(ram, tree + index * aes.OB_BYTES + aes.OB_TYPE) & aes.OB_TYPE_MASK


def _menu_object(machine, text):
    """`(the menu's tree, the index)` of THE title or item of the machine's menu that reads `text` (blanks at its ends
    apart) — REFUSED BY NAME where the menu has none, or more than one."""
    ram, tree = machine.ram, machine.long(aes.AES_GL_MNTREE) & BUS
    found = []
    for index in range(MENU_OBJECTS_AT_MOST):
        thing = tree + index * aes.OB_BYTES
        if _object_type(ram, tree, index) in (aes.G_STRING, aes.G_TITLE) and text_at(ram, case.long_in(ram, thing + aes.OB_SPEC)).strip() == text:
            found.append(index)
        if case.word_in(ram, thing + aes.OB_FLAGS) & aes.OB_FLAG_LASTOB:
            break
    if len(found) != 1:
        raise Refused(f"the machine's menu holds {len(found)} titles or items that read {text!r}: a hand points at one")
    return tree, found[0]


def menu_item_is_checked(machine, text):
    """Does the machine's menu hold the item reading `text` CHECKED (the View menu's two marks)?"""
    tree, index = _menu_object(machine, text)
    return bool(case.word_in(machine.ram, tree + index * aes.OB_BYTES + aes.OB_STATE) & CHECKED)


def menu_point(machine, text):
    """A point inside the title or the item of the machine's menu that reads `text` — REFUSED BY NAME where the menu
    has none, more than one (`_menu_object`), or holds it DISABLED."""
    ram, (tree, index) = machine.ram, _menu_object(machine, text)
    if case.word_in(ram, tree + index * aes.OB_BYTES + aes.OB_STATE) & DISABLED:
        raise Refused(f"the menu's {text!r} is DISABLED on this machine: a click on it does nothing, and the chain "
                      f"would idle having done nothing")
    x, y, width, height = box(ram, tree, index)
    return x + min(width // 2, MENU_POINT_INSET), y + height // 2


def desk_tree(machine):
    return (machine.long(aes.AES_DESK_GLOBALS) & BUS) + aes_event.DESK_OBJECTS


def _live_objects(ram, tree, parent=0):
    """Every object of `tree` linked under `parent`, itself apart: what the tree SHOWS (a freed object keeps its type)."""
    below = []
    for child in aes_objects.children_of(ram, tree, parent):
        below += [child, *_live_objects(ram, tree, child)]
    return below


def icons(machine):
    """THE ICONS THE DESK SHOWS — on the desktop and in its windows —, `((index, its text, its letter), ...)`: the
    objects linked into the desk's own tree that are icons."""
    ram, tree, shown = machine.ram, desk_tree(machine), []
    for index in _live_objects(ram, tree):
        if _object_type(ram, tree, index) == aes.G_ICON:
            block = case.long_in(ram, tree + index * aes.OB_BYTES + aes.OB_SPEC) & BUS
            shown.append((index, text_at(ram, case.long_in(ram, block + aes.IB_PTEXT)).strip(),
                          chr(case.word_in(ram, block + aes.IB_CHAR) & aes.BYTE_MASK)))
    return tuple(shown)


def box(ram, tree, index):
    """`(x, y, width, height)` of object `index` of `tree`, on the screen — REFUSED BY NAME for an object not linked
    under the tree's root (band 6 wave 4's harness gap: it climbed for ever): a dialog laid INSIDE another's tree is
    a tree of its own, rooted at its own object and indexed from it (the DISKCOPY dialog is the utility tree's objects
    11..16, its COPY button that root's 5) — box it from there, as `dialog_button` finds it."""
    try:
        origin = aes_objects.screen_origin(ram, tree, index)
    except aes_objects.Unrooted as unrooted:
        raise Refused(f"object {index} of the tree at {tree:#x}: {unrooted} — an object of a sub-tree rooted "
                      f"elsewhere, boxed from the outer tree's root") from unrooted
    return (*origin, *(aes_objects.object_word(ram, tree, index, field) for field in SIZE_FIELDS))


def windows(machine):
    """`(x, y, width, height)` of every window the AES has open, off its window tree (the root's children)."""
    return tuple(box(machine.ram, aes.AES_WINDOW_TREE, handle) for handle in aes_objects.children_of(machine.ram, aes.AES_WINDOW_TREE, 0))


def _holds(box, inner):
    """Does the rectangle `box` hold the whole of `inner`?"""
    x, y, width, height = inner
    return aes_objects.inside(x, y, box) and aes_objects.inside(x + width - 1, y + height - 1, box)


def _point_in_sight(machine, index, name):
    """A POINT OF THE IMAGE OF THE ICON `index` THAT A HAND CAN REACH: its centre, else a point just inside one of the
    image's four edges — the first that lies inside the pane the icon is in (the desktop's, a window's work area) and
    UNDER NO WINDOW BUT ITS OWN. REFUSED BY NAME where none does: a click there is a click on whatever covers the icon
    (a drive's icon under a window's closer CLOSES the window — the measuring pass's "two windows")."""
    ram, tree = machine.ram, desk_tree(machine)
    block = case.long_in(ram, tree + index * aes.OB_BYTES + aes.OB_SPEC) & BUS
    x, y = aes_objects.screen_origin(ram, tree, index)
    left, top = x + case.word_in(ram, block + aes.IB_XICON), y + case.word_in(ram, block + aes.IB_YICON)
    middle, far = ICON_IMAGE_HALF, 2 * ICON_IMAGE_HALF - ICON_EDGE_INSET
    pane = box(ram, tree, aes_objects.parent_by_climbing(tree, index, ram))
    over = [window for window in windows(machine) if not _holds(window, pane)]
    for dx, dy in ((middle, middle), (ICON_EDGE_INSET, middle), (far, middle), (middle, ICON_EDGE_INSET), (middle, far)):
        point = left + dx, top + dy
        if aes_objects.inside(*point, pane) and not any(aes_objects.inside(*point, window) for window in over):
            return point
    raise Refused(f"the icon {name!r} is not in sight: no point of its image at {(left, top)} lies inside the pane it is "
                  f"in {pane} and under no other window ({over}) — a click there would land on what covers it")


def _the_one(machine, what, matching):
    found = [index for index, text, letter in icons(machine) if matching(text, letter)]
    if len(found) != 1:
        raise Refused(f"the desk shows {len(found)} icons that are {what}: a hand points at one — it shows "
                      f"{[(text, letter) for _index, text, letter in icons(machine)]}")
    return found[0]


def icon_index(machine, name):
    """The object of the desk's tree that is THE icon reading `name` — refused by name where there is none, or two."""
    return _the_one(machine, f"named {name!r}", lambda text, _letter: text == name)


def icon_point(machine, name):
    """A point of the image of the icon reading `name` (a file, a folder, the trash) that is in sight (`_point_in_sight`)."""
    return _point_in_sight(machine, icon_index(machine, name), name)


def drive_point(machine, letter):
    """...and of the drive icon bearing `letter` (two drives read alike: the letter in the ICONBLK tells them apart)."""
    return _point_in_sight(machine, _the_one(machine, f"drive {letter}:'s", lambda _text, its: its == letter), f"drive {letter}:")


def _is_selected(machine, index):
    return bool(case.word_in(machine.ram, desk_tree(machine) + index * aes.OB_BYTES + aes.OB_STATE) & SELECTED)


def icon_is_selected(machine, name):
    return _is_selected(machine, icon_index(machine, name))


def drive_is_selected(machine, letter):
    return _is_selected(machine, _the_one(machine, f"drive {letter}:'s", lambda _text, its: its == letter))


def top_window(machine):
    """`(x, y, width, height)` of the AES's top window, off its window tree — refused by name where none is open."""
    handle = aes.signed(machine.word(aes.AES_GL_WTOP))
    if handle <= 0:
        raise Refused(f"no window is on top on this machine (gl_wtop is {handle}): nothing to point a gadget of")
    return box(machine.ram, aes.AES_WINDOW_TREE, handle)


def closer_point(machine):
    x, y, _width, _height = top_window(machine)
    return x + GADGET_INSET_X, y + GADGET_INSET_Y


def fuller_point(machine):
    x, y, width, _height = top_window(machine)
    return x + width - GADGET_INSET_X, y + GADGET_INSET_Y


def from_the_bottom_right(from_the_right, from_the_bottom):
    """`machine -> the point` that far inside the top window's bottom right corner: where its scroll gadgets are."""
    def point(machine):
        x, y, width, height = top_window(machine)
        return x + width - from_the_right, y + height - from_the_bottom
    return point


def _buttons_reading(ram, text):
    """Every OBJECT of the megabyte that is a G_BUTTON whose text reads `text`, by its address — found by its type
    byte and held to its text (the desk's dialogs lie in its own resource block, the alert's in the AES's: no one
    table lists both)."""
    found, at = [], ram.find(bytes((aes.G_BUTTON,)))
    while at != -1:
        thing = at - aes.OB_TYPE - 1                # the type is the word's low byte
        spec = case.long_in(ram, thing + aes.OB_SPEC) & BUS if thing >= 0 and not thing % WORD_BYTES else 0
        if 0 < spec < len(ram) and bytes(ram[spec:spec + len(text) + 1]).strip(b" ") == text.encode() + b"\0":
            found.append(thing)
        at = ram.find(bytes((aes.G_BUTTON,)), at + 1)
    return found


def _shown_under(ram, root):
    """THE OBJECTS LINKED UNDER THE OBJECT AT `root`, by their index: what a tree rooted there SHOWS — a bounded walk
    of its head and next links (an address that is no tree's root answers whatever its bytes link, or nothing: it
    never loops, and it reads no further than a tree's length)."""
    shown, parents = set(), [aes.OB_ROOT]
    while parents:
        child = aes_objects.object_word(ram, root, parents.pop(), "HEAD")
        while 0 < child <= aes.TREE_OBJECTS and child not in shown:
            shown.add(child)
            parents.append(child)
            child = aes_objects.object_word(ram, root, child, "NEXT")
    return shown


def _trees_showing(ram, thing, roots):
    """`[(the tree, the index)]` of the object at `thing` in every tree of `roots` (addresses) THAT SHOWS IT: a root —
    an object with no next — a whole number of objects below it, with the object linked under it. NOT "the first
    object below it whose ob_next is NIL": a dialog's tree holds objects ITS DESK TOOK OUT OF IT, each left with no
    next (the Install Disk Drive dialog's four, between its text fields and its three buttons), and a walk down from
    a button stops at the nearest of those — a root nobody runs."""
    found = []
    for index in range(1, aes.TREE_OBJECTS + 1):
        root = thing - index * aes.OB_BYTES
        if root in roots and aes_objects.object_word(ram, root, aes.OB_ROOT, "NEXT") == aes.OB_NIL and index in _shown_under(ram, root):
            found.append((root, index))
    return found


def _buttons_up(machine, text):
    """`[(the tree, the index)]` of every BUTTON READING `text` OF A DIALOG THAT IS UP: the button object SHOWN BY a
    tree the desk's process holds ON ITS LIVE STACK (the form the AES is running was handed it there:
    `_trees_showing`)."""
    ram, parked = machine.ram, machine.long(machine.static_processes()[0].uda + aes.UDA_SUPER_SP) & BUS
    held = {case.long_in(ram, at) & BUS for at in range(parked, stacks(machine)[PD0_STACK][1] - LONG_BYTES + WORD_BYTES, WORD_BYTES)}
    return [shown for thing in _buttons_reading(ram, text) for shown in _trees_showing(ram, thing, held)]


def dialog_button(machine, text):
    """`(the tree, the index)` of THE BUTTON READING `text` OF THE DIALOG THAT IS UP (`_buttons_up`) — refused by name
    where no such button's tree is being run, or more than one."""
    up = _buttons_up(machine, text)
    if len(up) != 1:
        raise Refused(f"{len(up)} dialogs that are up on this machine hold a button reading {text!r}: a hand presses one")
    return up[0]


def button_point(machine, text):
    """THE MIDDLE OF THAT BUTTON. For a dialog's button that is NOT its default: Return takes the default, and the
    delete dialog's is Cancel."""
    x, y, width, height = box(machine.ram, *dialog_button(machine, text))
    return x + width // 2, y + height // 2


# ---- THE NAMED STOPS: where a run that never idles waits for a hand -----------------------------------------------------------------
# Each is an instruction of the ROM's own polling loop (held to its bytes by the battery): the run is ended at its
# first arrival there, and the next reception is taken there, between two turns of the loop.
VIEWER_AT_A_PAGE_S_END = "the file viewer's key wait at a page's end"
VIEWER_AT_THE_FILE_S_END = "the file viewer's key wait at the file's end"
RUBBER_BOX_POLL = "the rubber box's poll (gr_stilldn's entry, under gr_rubwind)"
STOPS = {
    VIEWER_AT_A_PAGE_S_END: 0xfed79c,       # `move.w #$ff,-(sp)`; Crawio's glue; `tst.w d0`; `beq` back: until a key comes
    VIEWER_AT_THE_FILE_S_END: 0xfed754,     # ...the same four instructions, after the last line
    RUBBER_BOX_POLL: addrs.AES_ROM_GR_STILLDN}

# ---- A HAND'S RECEPTIONS ----------------------------------------------------------------------------------------------------------------
KEY_RELEASED = 0x80                     # the IKBD's break code: the make code with this bit
SCAN_A, SCAN_RETURN, SCAN_SPACE = 0x1e, 0x1c, 0x39
SCAN_BACKSPACE, SCAN_C = 0x0e, 0x2e
BUTTON_DOWN, BUTTON_UP = aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.ikbd(aes_boot.NO_BUTTON, 0, 0)
A_CLICK = (BUTTON_DOWN, BUTTON_UP, aes_boot.CLICK_TICKS)
A_DOUBLE_CLICK = (BUTTON_DOWN, BUTTON_UP, BUTTON_DOWN, BUTTON_UP, aes_boot.CLICK_TICKS)
A_PRESS = (BUTTON_DOWN, aes_boot.CLICK_TICKS)          # the button down and held: the click's count run out with it down
STEP_INSNS = aes_boot.CONTINUED_INSNS
LAUNCH_INSNS = 6_000_000                # a program launched: the desk's teardown, the load, the program's own start-up
VIEWER_INSNS = 12_000_000               # a page of the file viewer is drawn a character at a time through the BIOS

Step = namedtuple("Step", "what hand until budget", defaults=(None, STEP_INSNS))
Step.__doc__ = """One step of a chain: `what` the hand does (for a reader), `hand` — `machine -> the receptions` —,
`until`: THE NAMED STOP the step's run ends at (a key of `STOPS`; None: the machine's next idle), and its `budget`."""


def _moved(point_of, *then):
    return lambda machine: (aes_boot.mouse_to(*point_of(machine)), *then)


def item(title, text):
    """The menu item `text` under `title`, chosen: the bar's title touched (the menu drops), the item, a click."""
    return (Step(f"the mouse on the bar's {title!r}", _moved(lambda machine: menu_point(machine, title))),
            Step(f"...on its {text!r}", _moved(lambda machine: menu_point(machine, text))),
            Step("...clicked", lambda _machine: A_CLICK))


def clicked(what, point_of):
    return (Step(f"{what} clicked", _moved(point_of, *A_CLICK)),)


def double_clicked(what, point_of, until=None, budget=STEP_INSNS):
    return (Step(f"{what} double-clicked", _moved(point_of, *A_DOUBLE_CLICK), until, budget),)


def typed(what, scan, until=None, budget=STEP_INSNS):
    return (Step(f"{what} typed", lambda _machine: (aes_boot.ikbd(scan), aes_boot.ikbd(scan | KEY_RELEASED)), until, budget),)


def dragged(what, from_point_of, to, to_point_of):
    """An icon pressed, carried and let go: three steps, each to an idle (the drag's loop waits for the mouse)."""
    return (Step(f"{what} pressed", _moved(from_point_of, *A_PRESS)),
            Step(f"...carried to {to}", _moved(to_point_of)),
            Step("...let go", lambda _machine: (BUTTON_UP,)))


RETURN = typed("Return", SCAN_RETURN)


def pressed(text):
    """The dialog's button reading `text`, clicked."""
    return clicked(f"the dialog's {text!r}", lambda machine: button_point(machine, text))


def drive(letter):
    return lambda machine: drive_point(machine, letter)


def icon(name):
    return lambda machine: icon_point(machine, name)


# ---- ONE STEP, PROFILED: a kept derivation ----------------------------------------------------------------------------------------------
PROFILE_HELD_BY_A_STEP = "a profiled step of the hands' campaign (`aes_desk.stepped`)"
OS_TEXT = (emu.ROM_BASE, aes.AES_TEXT[0])           # the BIOS, GEMDOS and the VDI: what runs under GEM's text
Profile = namedtuple("Profile", "text os line_f")
Profile.__doc__ = """One step's cycle profile: `text` — `((PC, cycles), ...)` for every PC of the ROM's GEM text
(`aes.AES_TEXT`) that ran, in address order —, `os`: the cycles in the ROM below it, `line_f`: those in the Line-F
handler's RAM copy."""
Stepped = namedtuple("Stepped", "boot profile")


def _profile_read():
    lo, hi = aes.AES_TEXT
    first = emu._LIB.osh_prof_slot(lo)
    tallies = emu.prof_slice(first, emu._LIB.osh_prof_slot(hi - emu.PROF_SLOT_BYTES) + 1)
    text = tuple((lo + nth * emu.PROF_SLOT_BYTES, cycles) for nth, cycles in enumerate(tallies) if cycles)
    return Profile(text, emu.prof_cycles(*OS_TEXT), emu.prof_cycles(*aes_boot.LINE_F_COPY))


@derived.kept
def stepped(boot, received, until=None, at=None, budget=STEP_INSNS):
    """ONE STEP: `boot` — THE ROM'S MACHINE, at its idle or stopped at the named stop `at` — continued through
    `received` to its next idle, or to its first arrival at `until` (`aes_boot.continued`, made here and not served:
    the profile is this run's) — a `Stepped`: the `Boot` there and the step's `Profile`, the receptions' own handlers
    in it. REFUSED BY NAME on a machine that holds a blob: nothing of ours runs in this campaign."""
    if aes_boot.blob_of(boot) is not None:
        raise Refused("the hands' campaign is THE ROM'S MACHINE'S: this one holds a blob — what ran on it would be "
                      "called the ROM's and be ours")
    aes_event.vet_the_profile_is_free("a step of the hands' campaign")
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        with aes_event.profile_held(PROFILE_HELD_BY_A_STEP):
            after = aes_boot.continued.derive(boot, tuple(received), budget, until, at)
        profile = _profile_read()
    finally:
        emu.prof_enable(False)
    return Stepped(after, profile)


# ---- THE CHAINS ----------------------------------------------------------------------------------------------------------------------------
INF_ICONS, INF_TEXT, FILES = "the DESKTOP.INF machine", "the DESKTOP.INF machine, as text", "the files machine"
MACHINES = {INF_ICONS: aes_boot.inf_machine, INF_TEXT: lambda: aes_boot.inf_machine(aes_boot.VIEW_AS_TEXT),
            FILES: aes_boot.files_machine}
THE_INF, THE_README, THE_PROGRAM, THE_FOLDER, THE_TRASH = "DESKTOP.INF", "README.TXT", "TESTPRG.PRG", "AUTO", "TRASH"
NEW_FOLDER = "A"                        # the folder the New Folder chain types the name of
PRINT_SCREEN_S_ALERT = "Options > Print Screen (its alert raised, not answered)"
BOX_MARGIN = 6                          # how far outside an icon's object a rubber box round it begins and ends
Chain = namedtuple("Chain", "after steps enters")
Chain.__doc__ = """A chain of a user's acts: `after` — the chain it goes on from, or a key of `MACHINES` (that
machine's first idle) —, its `steps`, and `enters`: THE ROUTINES ITS OWN STEPS MUST ENTER for the chain to be what
its name says (the act's own routine, read off the ROM: a chain that idles without it did nothing)."""

OPEN_A = double_clicked("drive A:'s icon", drive("A"))
SHOW_INFO, MAKE_FOLDER = 0xfe16e6, 0xfdfebc         # the File menu's Show Info and New Folder ($fe1ec2, $fe1ece: the two call words)
ICON_DRAG, COPY_ENGINE = 0xfdc57a, 0xfdd918         # deskact's icon drag; deskdir's copy / move / delete engine
DIALOG_RUNNER = 0xfde8a6                # the desk's dialog runner
OPEN_SELECTION = 0xfe1568               # the File menu's Open ($fe1eb4)
DO_FORMAT, INF_WRITE = 0xfe1800, 0xfdbb34            # the File menu's Format ($fe1f06); deskapp's DESKTOP.INF writer
SHOW_FILE = addrs.AES_ROM_DESK_SHOW_FILE
# ...and the routines the chains that choose no dialog enter, each READ OFF THE ROM (`aes_map/linef_dis.py`) and held
# to its chain's own profile:
BUTTON_HANDLER, KEY_HANDLER = 0xfe2172, 0xfe22a6    # the desk's button handler; its key handler (a key at the idle)
VIEW_MENU, OPTIONS_MENU = 0xfe1f2a, 0xfe1fde        # the View menu's handler (items 29-35) and the Options menu's (37-44)
SET_VIEW_AND_SORT = 0xfe2a7c            # ...the View handler's one callee: the view and the sort key set, the windows rebuilt
DESK_ALERT = 0xfde022                   # the desk's alert (the Options handler's Print Screen arm, `$fe20fc`, asks it first)
RUBBER_BOX_BINDING = 0xfde122           # unit D's binding of gr_rubbox (`gr_rubbox(); dsptch()`)
OPEN_A_DRIVE, OPEN_A_FOLDER = 0xfe13ea, 0xfe14ba    # the File menu's Open's two callees: a drive's window, a folder's
CLOSE_A_WINDOW, CLOSE_TO_THE_PARENT = 0xfe18e4, 0xfe1972   # `$fe1a18`'s two arms: the root's window shut; a folder's, up one level
FULL_A_WINDOW = 0xfe0f9c                # the full box: wind_get's current / previous / full, the one that is not current set
SCROLL_A_WINDOW = 0xfe3310              # a window's view moved by its bars...
SCROLL_VERTICALLY, SCROLL_HORIZONTALLY = 0xfe3504, 0xfe359a     # ...through the message handler's two arrow / page arms
# ...and the leaves and the binding only a dialog's less-trodden button reaches (band 6 wave 1a's fix pass: units O and
# D take their cases at these chains' arrivals)
RENAME_A_FILE, SET_ATTRIBUTES = addrs.AES_ROM_DOS_RENAME, addrs.AES_ROM_DOS_CHMOD      # Show Info's two acts on a file
FREE_AN_ICON, TAKE_AN_ICON = addrs.AES_ROM_APP_FREE, addrs.AES_ROM_APP_ALLOC         # Install Disk Drive's Remove and Install
SHOW_A_DOS_ERROR = addrs.AES_ROM_DESK_FORM_ERROR    # the desk's form_error binding: the copy engine's, after a DOS error
THE_RENAMED = "DESKTOP.INA"             # what the file reads once its name's last character is typed over with an A
READ_ONLY_FILE = "file: File > Show Info, Read-Only pressed, Return"


def _icon_box(machine, name):
    """`(x, y, width, height)` of the object of the icon reading `name`, on the screen."""
    return box(machine.ram, desk_tree(machine), icon_index(machine, name))


def above(name):
    """A point of the bare desktop just above the icon reading `name`, at its left edge: where a box round it begins."""
    def point(machine):
        x, y, _width, _height = _icon_box(machine, name)
        return x, y - BOX_MARGIN
    return point


def past(name):
    """...and one past its right edge, inside its last row: where that box ends (a box grows right and down)."""
    def point(machine):
        x, y, width, height = _icon_box(machine, name)
        return x + width + BOX_MARGIN, y + height - 1
    return point


def rubber_box(from_point_of, to_point_of):
    """A rubber box drawn on the desktop: the button pressed on no object — the run ends in the box's poll, which never
    idles —, the mouse carried THERE, the button let go THERE."""
    return (Step("the button pressed on the bare desktop", _moved(from_point_of, *A_PRESS), RUBBER_BOX_POLL),
            Step("...the mouse carried, the box growing", _moved(to_point_of), RUBBER_BOX_POLL),
            Step("...the button let go", lambda _machine: (BUTTON_UP,)))


def shown(stops):
    """The selection's Open answered Show: Return, then a key at each of the viewer's waits `stops` (the last ends it)."""
    waits = (*stops, None)
    return (Step("Return (Show)", RETURN[0].hand, waits[0], VIEWER_INSNS),
            *(Step(f"a blank typed at {stop}", typed("a blank", SCAN_SPACE)[0].hand, after, VIEWER_INSNS)
              for stop, after in zip(stops, waits[1:])))


CHAINS = {
    # ---- the desk alone, no window
    "Desk > Desktop Info, Return": Chain(INF_ICONS, (*item("Desk", "Desktop Info..."), *RETURN), (DIALOG_RUNNER,)),
    "Options > Set Preferences, Return": Chain(INF_ICONS, (*item("Options", "Set Preferences..."), *RETURN), (DIALOG_RUNNER,)),
    "Options > Save Desktop, Return": Chain(INF_ICONS, (*item("Options", "Save Desktop"), *RETURN), (INF_WRITE,)),
    # (the item's arm asks an alert first and prints on its button 1: the chain RAISES THE ALERT AND DOES NOT ANSWER IT —
    # the hardcopy leaf `$fe8862` is the screen dump's, which no chain tries)
    PRINT_SCREEN_S_ALERT: Chain(INF_ICONS, item("Options", "Print Screen"), (OPTIONS_MENU, DESK_ALERT)),
    "a key typed at the desk's idle": Chain(INF_ICONS, typed("A", SCAN_A), (KEY_HANDLER,)),
    "drive A: selected": Chain(INF_ICONS, clicked("drive A:'s icon", drive("A")), (BUTTON_HANDLER,)),
    "A: File > Show Info, Return": Chain("drive A: selected", (*item("File", "Show Info..."), *RETURN), (SHOW_INFO,)),
    "A: Options > Install Disk Drive, Return": Chain("drive A: selected", (*item("Options", "Install Disk Drive..."), *RETURN), (DIALOG_RUNNER,)),
    # (the dialog's two other buttons: Remove frees the drive's ANODE — the list in use's LAST, the INF's first line —;
    # a letter typed over the field's and Install takes a new one, linked AT THE TAIL: `$fdf210` hands app_alloc 0.
    # The desk keeps the letter as typed: the new icon's is a lower-case c)
    "A: Options > Install Disk Drive, Remove pressed": Chain(
        "drive A: selected", (*item("Options", "Install Disk Drive..."), *pressed("Remove")), (DIALOG_RUNNER, FREE_AN_ICON)),
    "A: Options > Install Disk Drive, 'C' typed, Install pressed": Chain(
        "drive A: selected", (*item("Options", "Install Disk Drive..."), *typed("C", SCAN_C), *pressed("Install")), (DIALOG_RUNNER, TAKE_AN_ICON)),
    "A: File > Open": Chain("drive A: selected", item("File", "Open"), (OPEN_SELECTION,)),
    "A: File > Format, Return (the warning answered)": Chain("drive A: selected", (*item("File", "Format..."), *RETURN), (DO_FORMAT,)),
    "drive A: dragged to the trash, Return": Chain(
        INF_ICONS, (*dragged("drive A:'s icon", drive("A"), "the trash", icon(THE_TRASH)), *RETURN), (ICON_DRAG,)),
    "a rubber box on the desktop, round the trash": Chain(INF_ICONS, rubber_box(above(THE_TRASH), past(THE_TRASH)), (RUBBER_BOX_BINDING,)),
    # ---- drive A:'s window, one file in it
    "A: opened": Chain(INF_ICONS, OPEN_A, (OPEN_A_DRIVE,)),
    "window: View > Show as Text": Chain("A: opened", item("View", "Show as Text"), (VIEW_MENU, SET_VIEW_AND_SORT, addrs.AES_ROM_DESK_USERDEF)),
    "window: View > Sort by Size": Chain("A: opened", item("View", "Sort by Size"), (VIEW_MENU, SET_VIEW_AND_SORT)),
    "window: File > Close Window": Chain("A: opened", item("File", "Close Window"), (CLOSE_A_WINDOW,)),
    "window: its closer clicked": Chain("A: opened", clicked("the closer", closer_point), (CLOSE_A_WINDOW,)),
    "window: its fuller clicked": Chain("A: opened", clicked("the fuller", fuller_point), (FULL_A_WINDOW,)),
    "window: A: opened again (two windows)": Chain("A: opened", OPEN_A, (OPEN_A_DRIVE,)),
    "file: selected": Chain("A: opened", clicked("the file's icon", icon(THE_INF)), (BUTTON_HANDLER,)),
    "file: File > Show Info, Return": Chain("file: selected", (*item("File", "Show Info..."), *RETURN), (SHOW_INFO,)),
    # (Show Info's two acts on a file: its name edited — the last character typed over — is Frename; its Read-Only
    # button is Fattrib. And a read-only file dragged to the trash is REFUSED by GEMDOS: the copy engine shows the
    # error through the desk's form_error, the one chain that reaches that binding)
    "file: File > Show Info, Backspace, 'A', Return (renamed)": Chain(
        "file: selected", (*item("File", "Show Info..."), *typed("Backspace", SCAN_BACKSPACE), *typed("A", SCAN_A), *RETURN),
        (SHOW_INFO, RENAME_A_FILE)),
    READ_ONLY_FILE: Chain("file: selected", (*item("File", "Show Info..."), *pressed("Read-Only"), *RETURN), (SHOW_INFO, SET_ATTRIBUTES)),
    "file: read-only, dragged to the trash, OK — access denied, Return": Chain(
        READ_ONLY_FILE, (*dragged("the file's icon", icon(THE_INF), "the trash", icon(THE_TRASH)), *pressed("OK"), *RETURN),
        (ICON_DRAG, COPY_ENGINE, SHOW_A_DOS_ERROR)),
    "file: File > Open (the Show / Print / Cancel alert)": Chain("file: selected", item("File", "Open"), (OPEN_SELECTION,)),
    "file: shown, a key at its end": Chain("file: File > Open (the Show / Print / Cancel alert)", shown((VIEWER_AT_THE_FILE_S_END,)), (SHOW_FILE,)),
    "file: double-clicked (the alert)": Chain("A: opened", double_clicked("the file's icon", icon(THE_INF)), (OPEN_SELECTION,)),
    # (the delete dialog's DEFAULT IS CANCEL: Return deletes nothing — the dialog's own OK is pressed)
    "file: dragged to the trash, Return (Cancel, the dialog's default)": Chain(
        "file: selected", (*dragged("the file's icon", icon(THE_INF), "the trash", icon(THE_TRASH)), *RETURN), (ICON_DRAG, COPY_ENGINE)),
    "file: dragged to the trash, OK": Chain(
        "file: selected", (*dragged("the file's icon", icon(THE_INF), "the trash", icon(THE_TRASH)), *pressed("OK")), (ICON_DRAG, COPY_ENGINE)),
    # ---- THE FOLDER CHAIN: New Folder makes one on the disk, and the rest go on from it
    "folder: File > New Folder, 'A', Return": Chain("A: opened", (*item("File", "New Folder..."), *typed("A", SCAN_A), *RETURN), (MAKE_FOLDER,)),
    "folder: the file dragged onto it, Return": Chain(
        "folder: File > New Folder, 'A', Return", (*dragged("the file's icon", icon(THE_INF), "the folder", icon(NEW_FOLDER)), *RETURN),
        (ICON_DRAG, COPY_ENGINE)),
    "folder: opened": Chain("folder: File > New Folder, 'A', Return", double_clicked("the folder's icon", icon(NEW_FOLDER)), (OPEN_A_FOLDER,)),
    "folder: File > Close": Chain("folder: opened", item("File", "Close"), (CLOSE_TO_THE_PARENT, OPEN_A_FOLDER)),
    "folder: selected, File > Show Info, Return": Chain(
        "folder: File > New Folder, 'A', Return", (*clicked("the folder's icon", icon(NEW_FOLDER)), *item("File", "Show Info..."), *RETURN), (SHOW_INFO,)),
    "folder: dragged to the trash, OK": Chain(
        "folder: File > New Folder, 'A', Return", (*dragged("the folder's icon", icon(NEW_FOLDER), "the trash", icon(THE_TRASH)), *pressed("OK")),
        (ICON_DRAG, COPY_ENGINE)),
    # ---- the text view (the window's items are G_USERDEF objects)
    "text view: A: opened": Chain(INF_TEXT, OPEN_A, (addrs.AES_ROM_DESK_USERDEF,)),
    "text view: Options > Save Desktop, Return": Chain("text view: A: opened", (*item("Options", "Save Desktop"), *RETURN), (INF_WRITE,)),
    # ---- THE FILES MACHINE: files, a folder with a file in it, a program
    "files: A: opened": Chain(FILES, OPEN_A, (OPEN_A_DRIVE,)),
    # ---- its window's scroll gadgets (the disk's four items do not fit the window as it opens)
    "files: the window's down arrow clicked": Chain(
        "files: A: opened", clicked("the down arrow", from_the_bottom_right(SCROLL_GADGET_INSET, DOWN_ARROW_FROM_THE_BOTTOM)),
        (SCROLL_A_WINDOW, SCROLL_VERTICALLY)),
    "files: the window's vertical bar clicked under its slider (a page)": Chain(
        "files: A: opened", clicked("the vertical bar", from_the_bottom_right(SCROLL_GADGET_INSET, PAGE_AREA_FROM_THE_BOTTOM)),
        (SCROLL_A_WINDOW, SCROLL_VERTICALLY)),
    "files: the window's right arrow clicked": Chain(
        "files: A: opened", clicked("the right arrow", from_the_bottom_right(RIGHT_ARROW_FROM_THE_RIGHT, SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    "files: the long file shown, a blank at each page's end and at its end": Chain(
        "files: A: opened", (*clicked("the long file's icon", icon(THE_README)), *item("File", "Open"),
                             *shown((VIEWER_AT_A_PAGE_S_END, VIEWER_AT_A_PAGE_S_END, VIEWER_AT_THE_FILE_S_END))), (OPEN_SELECTION, SHOW_FILE)),
    "files: the long file dragged onto the folder, Return": Chain(
        "files: A: opened", (*dragged("the long file's icon", icon(THE_README), "the folder", icon(THE_FOLDER)), *RETURN), (ICON_DRAG, COPY_ENGINE)),
    "files: the folder (not empty) dragged to the trash, OK": Chain(
        "files: A: opened", (*dragged("the folder's icon", icon(THE_FOLDER), "the trash", icon(THE_TRASH)), *pressed("OK")), (ICON_DRAG, COPY_ENGINE)),
    # (the window as it opens shows three of the disk's four items whole: made full, it shows the program's too)
    "files: the window made full": Chain("files: A: opened", clicked("the fuller", fuller_point), (FULL_A_WINDOW,)),
    "files: the program selected, File > Show Info, Return": Chain(
        "files: the window made full", (*clicked("the program's icon", icon(THE_PROGRAM)), *item("File", "Show Info..."), *RETURN), (SHOW_INFO,)),
    "files: the program selected, Options > Install Application, Return": Chain(
        "files: the window made full",
        (*clicked("the program's icon", icon(THE_PROGRAM)), *item("Options", "Install Application..."), *RETURN), (DIALOG_RUNNER,)),
    "files: View > Show as Text": Chain("files: A: opened", item("View", "Show as Text"), (addrs.AES_ROM_DESK_USERDEF,)),
    # ---- A PROGRAM LAUNCHED, on the ROM's machine: deskmain returns, the shell's dos_exec loads it over free memory (no
    # blob lies there: the standing limit is a machine of ours'), and it waits in its own evnt_mesag — an idle
    "files: the program double-clicked — launched": Chain(
        "files: the window made full", double_clicked("the program's icon", icon(THE_PROGRAM), budget=LAUNCH_INSNS), (OPEN_SELECTION,)),
}
# ---- band 6 wave 1b: each group APPENDS its own chains inside its own block (the order above unchanged), and adds
# their count, steps and reach to its own entries of `test_aes_desk_rom.py`'s pins ----
# ---- band 6 wave 1b, group G1 (units I, L) ----
# (the fuller clicked on a FULL window: do_wfull's other arm, the window back to its previous size; and on a window
# whose view is scrolled a column right: win_ocalc pulls the scroll back to keep the grown view filled; that view rebuilt
# at its scroll, the first file shown is the second)
CHAINS.update({
    "window: its fuller clicked again (back to its size)": Chain("window: its fuller clicked", clicked("the fuller", fuller_point),
                                                                 (FULL_A_WINDOW,)),
    "files: the right arrow clicked, then the window made full": Chain(
        "files: the window's right arrow clicked", clicked("the fuller", fuller_point), (FULL_A_WINDOW,)),
    # (...and its view rebuilt at that scroll: the first file shown the second)
    "files: the right arrow clicked, then View > Sort by Size": Chain(
        "files: the window's right arrow clicked", item("View", "Sort by Size"), (VIEW_MENU, SET_VIEW_AND_SORT)),
})
# ---- end of group G1's ----
# ---- band 6 wave 1b, group G2 (units A, K, J) ----
# (the fix pass's chains for unit K's arms no chain made: the View menu's Show as Icons over a window already in icons;
# Save Desktop with a window open — cnx_put's per-window entry — and with its view scrolled; two icons selected at once by a rubber box —
# men_update's many-selected list. TRIED AND NOT KEPT: drive C: installed, then selected and Show Info — the desk keeps
# the letter as typed, a lower-case c, past 'B': men_update's hard-disk list DISABLES Show Info (refused by name), and
# the drive opened instead never enters drive_check)
DO_VIEWMENU, CNX_PUT, MEN_UPDATE = 0xfe1f2a, 0xfe2536, 0xfe1cb6         # desktop's
BOX_START_ABOVE = 3                     # how far above drive B:'s object a box round it and the trash begins: between
                                        # drive A:'s object (it ends 5 rows above B:'s) and B:'s


def above_drive(letter):
    """A point of the bare desktop just above the object of the drive icon bearing `letter`, at its left edge."""
    def point(machine):
        x, y, _width, _height = box(machine.ram, desk_tree(machine), _the_one(machine, f"drive {letter}:'s", lambda _text, its: its == letter))
        return x, y - BOX_START_ABOVE
    return point


CHAINS.update({
    "window: View > Show as Icons (the view it has)": Chain("A: opened", item("View", "Show as Icons"), (VIEW_MENU, DO_VIEWMENU)),
    "window: Options > Save Desktop, Return": Chain("A: opened", (*item("Options", "Save Desktop"), *RETURN), (INF_WRITE, CNX_PUT)),
    # (...and with the window's view scrolled a column right: its scroll's column and row apart)
    "files: the right arrow clicked, then Options > Save Desktop, Return": Chain(
        "files: the window's right arrow clicked", (*item("Options", "Save Desktop"), *RETURN), (INF_WRITE, CNX_PUT)),
    "a rubber box on the desktop, round drive B: and the trash": Chain(
        INF_ICONS, rubber_box(above_drive("B"), past(THE_TRASH)), (RUBBER_BOX_BINDING, MEN_UPDATE)),
})
# ---- end of group G2's ----
# ---- band 6 wave 1b, group G3 (units B, G) ----
BARE_DESKTOP = (300, 150)               # a point of the desktop far from every icon of the INF machine's (and under no window)
MOVE_DRVICON, CHECK_AN_ICON_S_HIT = 0xfdc268, 0xfdc86e   # deskact's desktop icons put down; its hit held to an icon's image
SORT_BY_THE_KEY = 0xfdfa2c              # deskfpd's pn_fcomp
DRIVE_CORNER_INSET = 1                  # a point this far inside a drive icon's object: outside its image and its label


def drive_corner(letter):
    """A point just inside the top left corner of the OBJECT of the drive icon bearing `letter` — the object is wider and
    taller than its image and label, and this point lies on neither (a click objc_find gives the icon and gr_obfind's
    act_chkobj does not)."""
    def point(machine):
        index = _the_one(machine, f"drive {letter}:'s", lambda _text, its: its == letter)
        x, y, _width, _height = box(machine.ram, desk_tree(machine), index)
        return x + DRIVE_CORNER_INSET, y + DRIVE_CORNER_INSET
    return point


CHAINS.update({
    # (an icon let go where it began — on the desktop, no icon under it — is put down there: move_drvicon, the one
    # caller `$fdcec4` in the drag loop; the icon's ANODE takes the new place)
    "drive A: dragged to a bare spot of the desktop": Chain(
        INF_ICONS, dragged("drive A:'s icon", drive("A"), "a bare spot of the desktop", lambda _machine: BARE_DESKTOP), (MOVE_DRVICON,)),
    "drive A:'s object clicked at its corner, outside its image and its label": Chain(
        INF_ICONS, clicked("drive A:'s object's corner", drive_corner("A")), (BUTTON_HANDLER, CHECK_AN_ICON_S_HIT)),
    # (the files machine's directory sorted by each of the View menu's other three keys: pn_fcomp's three arms)
    "files: View > Sort by Size": Chain("files: A: opened", item("View", "Sort by Size"), (VIEW_MENU, SORT_BY_THE_KEY)),
    "files: View > Sort by Date": Chain("files: A: opened", item("View", "Sort by Date"), (VIEW_MENU, SORT_BY_THE_KEY)),
    "files: View > Sort by Type": Chain("files: A: opened", item("View", "Sort by Type"), (VIEW_MENU, SORT_BY_THE_KEY)),
})
# ---- end of group G3's ----
# ---- band 6 wave 1b, group G4 (units C, H, E, F) ----
# THE COPY ENGINE'S NAME CONFLICT AND A FOLDER INSIDE A FOLDER, each made on the ROM's machine by the hands: a file
# copied where its name is already, a folder copied onto its own drive (a folder of that name is there: dos_mkdir
# answers EACCDN), the conflict's field typed over — the copy made as B, a second folder at the root —, B copied into A,
# and A, a folder now holding a folder, deleted (the walk goes down into B and comes back up). NO STEP OF THESE IS NEW
# FOLDER (its Line-F word: `test_aes_desk_rom.THROUGH_THE_TWO_WORDS`): the second folder is the conflict's copy.
# (Tried and refused by name, not kept: a folder made INSIDE an opened folder, and Show Info of A holding B — both
# stop at "Rwabs ... while the driver holds the disk CHANGED", the forced media change `aes_desk`'s docstring names.)
SCAN_B = 0x30
DO_NAMECON, SUB_PATH, PATH_PART = 0xfdcf48, 0xfdd0d2, 0xfdd762   # deskdir's name-conflict dialog, its folder up, par_chk's folder walk
A_COPY_OF_A_AS_B = "folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)"
B_INTO_A = "folders: B dragged onto A, Return"
CHAINS.update({
    "folder: the file dragged onto it again, Return — the name conflict, Return": Chain(
        "folder: the file dragged onto it, Return",
        (*dragged("the file's icon", icon(THE_INF), "the folder", icon(NEW_FOLDER)), *RETURN, *RETURN), (COPY_ENGINE, DO_NAMECON)),
    A_COPY_OF_A_AS_B: Chain(
        "folder: File > New Folder, 'A', Return",
        (*dragged("the folder's icon", icon(NEW_FOLDER), "drive A:'s icon", drive("A")), *RETURN, *typed("Backspace", SCAN_BACKSPACE),
         *typed("B", SCAN_B), *RETURN), (COPY_ENGINE, DO_NAMECON, PATH_PART)),
    B_INTO_A: Chain(A_COPY_OF_A_AS_B, (*dragged("folder B's icon", icon("B"), "folder A", icon(NEW_FOLDER)), *RETURN), (COPY_ENGINE, PATH_PART)),
    "folders: A (holding B) dragged to the trash, OK": Chain(
        B_INTO_A, (*dragged("folder A's icon", icon(NEW_FOLDER), "the trash", icon(THE_TRASH)), *pressed("OK")), (COPY_ENGINE, SUB_PATH)),
})


def lowest_button_point(text):
    """THE MIDDLE OF THE LOWEST BUTTON READING `text` OF THE DIALOG THAT IS UP — Set Preferences holds two "No"s, the
    deletes' confirmation above the copies' (`dialog_button` refuses a text two buttons read; both walk `_buttons_up`)."""
    def point(machine):
        up = [box(machine.ram, *shown) for shown in _buttons_up(machine, text)]
        if not up:
            raise Refused(f"no dialog that is up on this machine holds a button reading {text!r}")
        x, y, width, height = max(up, key=lambda each: each[1])
        return x + width // 2, y + height // 2
    return point


# ...and THE SAME CONFLICT WITH COPIES UNCONFIRMED (Set Preferences' second No): no copy dialog is up, and the conflict
# dialog is put up for the first time — do_namecon's two other arms.
COPIES_UNCONFIRMED = "folder: Options > Set Preferences, copies unconfirmed (the lower No), Return"
CHAINS.update({
    COPIES_UNCONFIRMED: Chain(
        "folder: the file dragged onto it, Return", (*item("Options", "Set Preferences..."), *clicked("the lower No", lowest_button_point("No")),
                                                      *RETURN), (DIALOG_RUNNER,)),
    "folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return": Chain(
        COPIES_UNCONFIRMED, (*dragged("the file's icon", icon(THE_INF), "the folder", icon(NEW_FOLDER)), *RETURN), (COPY_ENGINE, DO_NAMECON)),
})
# ---- end of group G4's ----
# ---- end of band 6 wave 1b's ----
# ---- band 6 wave 2: each group APPENDS its own chains inside its own block (the order above unchanged), and adds
# their count, steps and reach to its own entries of `test_aes_desk_rom.py`'s pins ----
# ---- band 6 wave 2, group G1 (units C, F, E) ----
# A LINE OF THE TEXT VIEW CLICKED: the desk selects it, and the line's G_USERDEF draw is called over a state whose
# SELECTED bit changed — dr_code's inverting arm (`$fde7c8`), which no line drawn whole takes.
import layouts                          # (here, inside the group's block: the module's head is no group's)

SFCB_NAME = layouts.parse_constants((aes.INCLUDE / "desk" / "deskusr.h",), known=aes.CONSTANTS)["SFCB_NAME"]


def _line_shows(ram, tree, index, name):
    """Is object `index` of `tree` a line of a text view (a G_USERDEF) whose SFCB — its USERBLK's parameter — names `name`?"""
    if aes_objects.object_word(ram, tree, index, "TYPE") & aes.WORD_MASK != aes.CONSTANTS["G_USERDEF"]:
        return False
    sfcb = case.long_in(ram, (case.long_in(ram, tree + index * aes.OB_BYTES + aes.CONSTANTS["OB_SPEC"]) & BUS)
                        + aes.CONSTANTS["UB_PARM"]) & BUS
    return bytes(ram[sfcb + SFCB_NAME:]).split(b"\0")[0] == name.encode()


def text_line_point(name):
    """THE MIDDLE OF THE TEXT VIEW'S LINE SHOWING THE FILE `name` — refused by name where the desk shows none, or two."""
    def point(machine):
        ram, tree = machine.ram, desk_tree(machine)
        found = [index for index in _live_objects(ram, tree) if _line_shows(ram, tree, index, name)]
        if len(found) != 1:
            raise Refused(f"the desk shows {len(found)} text-view lines of {name!r}: a hand clicks one")
        x, y, width, height = box(ram, tree, found[0])
        return x + width // 2, y + height // 2
    return point


# DELETES UNCONFIRMED (Set Preferences' first No, above the copies' — `lowest_button_point`'s other end): the delete
# dialog is not put up, so dir_op's delete runs whole with no idle — its file and folder arms (a folder walked by d_doop
# with no tree) at arrivals of their own.
def highest_button_point(text):
    """THE MIDDLE OF THE HIGHEST BUTTON READING `text` OF THE DIALOG THAT IS UP (`lowest_button_point`'s twin)."""
    def point(machine):
        up = [box(machine.ram, *shown) for shown in _buttons_up(machine, text)]
        if not up:
            raise Refused(f"no dialog that is up on this machine holds a button reading {text!r}")
        x, y, width, height = min(up, key=lambda each: each[1])
        return x + width // 2, y + height // 2
    return point


DELETES_UNCONFIRMED = "folder: Options > Set Preferences, deletes unconfirmed (the upper No), Return"
CHAINS.update({
    "files: View > Show as Text, the long file's line clicked": Chain(
        "files: View > Show as Text", clicked("the long file's line", text_line_point(THE_README)), (addrs.AES_ROM_DESK_USERDEF,)),
    DELETES_UNCONFIRMED: Chain(
        "folder: File > New Folder, 'A', Return", (*item("Options", "Set Preferences..."), *clicked("the upper No", highest_button_point("No")),
                                                    *RETURN), (DIALOG_RUNNER,)),
    "folder: deletes unconfirmed — the file dragged to the trash": Chain(
        DELETES_UNCONFIRMED, dragged("the file's icon", icon(THE_INF), "the trash", icon(THE_TRASH)), (ICON_DRAG, COPY_ENGINE)),
    "folder: deletes unconfirmed — the folder dragged to the trash": Chain(
        DELETES_UNCONFIRMED, dragged("the folder's icon", icon(NEW_FOLDER), "the trash", icon(THE_TRASH)), (ICON_DRAG, COPY_ENGINE)),
    # A FOLDER HOLDING A FILE COPIED: AUTO (INSIDE.TXT in it) dragged onto drive A:'s root, where it is already — the
    # folder's name conflict answered AUTB — so d_doop's walk copies a file (d_dofcopy from the walk's DTA)
    "files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB)": Chain(
        "files: A: opened", (*dragged("the folder's icon", icon(THE_FOLDER), "drive A:'s icon", drive("A")), *RETURN,
                             *typed("Backspace", SCAN_BACKSPACE), *typed("B", SCAN_B), *RETURN), (COPY_ENGINE,)),
})
# (the wave-2 fix pass's) DRIVE A:'s SHOW INFO AFTER A DELETE: the copy engine's tallies left by the delete's count
# (inf_folder clears them — g_nfiles 1, g_size the file's), and the walk over an EMPTY root (Fsfirst's EFILNF at once,
# where a folder's own search always finds "." first — the glue makes it AX 18, as ENMFIL).
EMPTIED_INFO = "file: dragged to the trash, OK — then drive A: selected, File > Show Info, Return"
# ...and A READ-ONLY FILE COPIED: the file made read-only, a folder made, the file dragged onto it — d_dofcopy handed
# attributes $01 (Fcreate drops the bit).
READ_ONLY_COPIED = "file: read-only — File > New Folder, 'A', Return, the file dragged onto it, Return"
CHAINS.update({
    EMPTIED_INFO: Chain("file: dragged to the trash, OK", (*clicked("drive A:'s icon", drive("A")), *item("File", "Show Info..."),
                                                            *RETURN), (SHOW_INFO,)),
    READ_ONLY_COPIED: Chain(READ_ONLY_FILE, (*item("File", "New Folder..."), *typed("A", SCAN_A), *RETURN,
                                             *dragged("the file's icon", icon(THE_INF), "the folder", icon(NEW_FOLDER)), *RETURN),
                            (MAKE_FOLDER, ICON_DRAG, COPY_ENGINE)),
})
# ---- end of group G1's wave-2 ----
# ---- band 6 wave 2, group G2 (units H, G, M) ----
# Unit H's drops no chain made (the cut's §3.2): desktop icons let go in a window (fun_drag -> fun_desk2win: a drive's
# files copied there by fun_disk, the trash refused), and on a desktop icon (fun_d2desk: a disk onto a disk — the copy's
# alert, Cancel its default; the trash onto a disk — refused).
WINDOW_INSIDE = 48                      # a point this far inside the top window's bottom right corner: its bare work area
CHAINS.update({
    "A: opened, drive A: dragged into its window, Return": Chain(
        "A: opened", (*dragged("drive A:'s icon", drive("A"), "A:'s window", from_the_bottom_right(WINDOW_INSIDE, WINDOW_INSIDE)),
                      *RETURN), (ICON_DRAG, addrs.AES_ROM_DESK_FUN_DESK2WIN)),
    "A: opened, the trash dragged into its window, Return": Chain(
        "A: opened", (*dragged("the trash", icon(THE_TRASH), "A:'s window", from_the_bottom_right(WINDOW_INSIDE, WINDOW_INSIDE)),
                      *RETURN), (ICON_DRAG, addrs.AES_ROM_DESK_FUN_DESK2WIN)),
    "drive A: dragged onto drive B:, Return": Chain(
        INF_ICONS, (*dragged("drive A:'s icon", drive("A"), "drive B:", drive("B")), *RETURN), (ICON_DRAG, addrs.AES_ROM_DESK_FUN_D2DESK)),
    "the trash dragged onto drive A:, Return": Chain(
        INF_ICONS, (*dragged("the trash", icon(THE_TRASH), "drive A:", drive("A")), *RETURN), (ICON_DRAG, addrs.AES_ROM_DESK_FUN_D2DESK)),
    # (a window's file onto its own drive's icon: fun_ddst's disk arm, a copy to the root it is in — the conflict with
    # itself, Return)
    "file: dragged onto drive A:'s icon, Return — the name conflict, Return": Chain(
        "A: opened", (*dragged("the file's icon", icon(THE_INF), "drive A:", drive("A")), *RETURN, *RETURN),
        (ICON_DRAG, addrs.AES_ROM_DESK_FUN_DDST)),
    # (New Folder again, of the name just made: fun_mkdir's search finds it — "You can not create a folder with that
    # name" — and Return takes the alert's default, Cancel)
    "folder: File > New Folder again, 'A', Return — the name taken, Return": Chain(
        "folder: File > New Folder, 'A', Return", (*item("File", "New Folder..."), *typed("A", SCAN_A), *RETURN, *RETURN), (MAKE_FOLDER,)),
    # (the wave-2 fix pass's) drive A: dropped into its window ONCE ITS ONE FILE IS DELETED: fun_disk over an empty root
    # (pn_active's Fsfirst answers EFILNF: nothing dropped)
    "file: dragged to the trash, OK — then drive A: dragged into its window": Chain(
        "file: dragged to the trash, OK", dragged("drive A:'s icon", drive("A"), "A:'s window",
                                                  from_the_bottom_right(WINDOW_INSIDE, WINDOW_INSIDE)),
        (ICON_DRAG, addrs.AES_ROM_DESK_FUN_DESK2WIN)),
})
# ---- end of group G2's wave-2 ----
# ---- band 6 wave 2, group G3 (units I, J, K, L) ----
# A window's bottom row from its left (the left arrow, its first gadget), and its sizer pulled up and left: what unit
# L's win_blt is reached through backward (a column left) and by a step no less than what is shown (a page of a
# narrower window: its redraw whole).
LEFT_ARROW_FROM_THE_LEFT = 8            # into the left arrow, the bottom row's first gadget
SIZER_PULL = 48                         # how far up and left of the sizer's corner it is let go: a column narrower
ARROW_BESIDE_THE_SIZER = 16             # into the right (down) arrow itself, beside the sizer
UP_ARROW_FROM_THE_TOP = 24              # into the up arrow, under the title bar
BAR_FROM_THE_LEFT = 20                  # into the horizontal bar, right of the left arrow
SLIDER_FROM_THE_LEFT = 24               # into the horizontal slider, right of the left arrow (it starts at the bar's left)
SLIDER_PULL = 40                        # how far right the slider is carried


def from_the_bottom_left(from_the_left, from_the_bottom):
    """`machine -> the point` that far inside the top window's bottom left corner."""
    def point(machine):
        x, y, _width, height = top_window(machine)
        return x + from_the_left, y + height - from_the_bottom
    return point


def from_the_top_right(from_the_right, from_the_top):
    """`machine -> the point` that far inside the top window's top right corner."""
    def point(machine):
        x, y, width, _height = top_window(machine)
        return x + width - from_the_right, y + from_the_top
    return point


SCAN_ESCAPE = 0x01                      # Esc: hndl_kbd's key, the top window read again
LONG_FILE_SHOWN = (*clicked("the long file's icon", icon(THE_README)), *item("File", "Open"),
                   *shown((VIEWER_AT_A_PAGE_S_END, VIEWER_AT_A_PAGE_S_END, VIEWER_AT_THE_FILE_S_END)))
A_FIFTH_ENTRY = "files: File > New Folder, 'A', Return (a fifth entry: a second row)"
SIZED_SMALLER = "files: the window's sizer pulled up and left (smaller)"
CHAINS.update({
    "files: the right arrow clicked, then the left arrow clicked": Chain(
        "files: the window's right arrow clicked", clicked("the left arrow", from_the_bottom_left(LEFT_ARROW_FROM_THE_LEFT, SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    SIZED_SMALLER: Chain(
        "files: A: opened", dragged("the sizer", from_the_bottom_right(SCROLL_GADGET_INSET, SCROLL_GADGET_INSET), "up and left",
                                    from_the_bottom_right(SIZER_PULL, SIZER_PULL)), (addrs.AES_ROM_DESK_VERIFY,)),
    "files: the right arrow clicked, then the horizontal bar left of its slider (a page)": Chain(
        "files: the window's right arrow clicked", clicked("the bar left of the slider", from_the_bottom_left(BAR_FROM_THE_LEFT,
                                                                                                             SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    "files: the window's right arrow gadget itself clicked (a column)": Chain(
        "files: A: opened", clicked("the right arrow", from_the_bottom_right(ARROW_BESIDE_THE_SIZER, SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    "files: the window's down arrow gadget itself clicked (a row)": Chain(
        "files: A: opened", clicked("the down arrow", from_the_bottom_right(SCROLL_GADGET_INSET, ARROW_BESIDE_THE_SIZER)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    "files: the window's up arrow gadget clicked (a row)": Chain(
        "files: A: opened", clicked("the up arrow", from_the_top_right(SCROLL_GADGET_INSET, UP_ARROW_FROM_THE_TOP)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    "files: the window's horizontal slider dragged right": Chain(
        "files: A: opened", dragged("the horizontal slider", from_the_bottom_left(SLIDER_FROM_THE_LEFT, SCROLL_GADGET_INSET),
                                    "the right", from_the_bottom_left(SLIDER_FROM_THE_LEFT + SLIDER_PULL, SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_VERTICALLY)),
    "window: Esc typed (the top window read again)": Chain("A: opened", typed("Esc", SCAN_ESCAPE), (KEY_HANDLER,)),
    "two windows: File > Close Window (one left on top)": Chain(
        "window: A: opened again (two windows)", item("File", "Close Window"), (CLOSE_A_WINDOW,)),
    "files: the window sized smaller, then its right arrow clicked": Chain(
        SIZED_SMALLER, clicked("the right arrow", from_the_bottom_right(RIGHT_ARROW_FROM_THE_RIGHT, SCROLL_GADGET_INSET)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
    # (the wave-2 fix pass's) the desk restarted after a file is shown, the INF keeping a window scrolled, and a sort
    # not the first: cnx_get's kept scroll and sort
    "files: the right arrow clicked, then the long file shown": Chain(
        "files: the window's right arrow clicked", LONG_FILE_SHOWN, (OPEN_SELECTION, SHOW_FILE)),
    "files: View > Sort by Size, then the long file shown": Chain("files: View > Sort by Size", LONG_FILE_SHOWN, (OPEN_SELECTION, SHOW_FILE)),
    # ...and a view kept not 0 with its sort 0 (the view told from the sort: Reviewer B's K1)
    "files: View > Show as Text, then the long file's line shown": Chain(
        "files: View > Show as Text", (*clicked("the long file's line", text_line_point(THE_README)), *item("File", "Open"),
                                       *shown((VIEWER_AT_A_PAGE_S_END, VIEWER_AT_A_PAGE_S_END, VIEWER_AT_THE_FILE_S_END))),
        (OPEN_SELECTION, SHOW_FILE)),
    # ...and A FIFTH ENTRY in the files window (a folder made: the icon view's four columns, so a second row), then the
    # down arrow: win_arrow's and win_blt's vertical arms
    A_FIFTH_ENTRY: Chain("files: A: opened", (*item("File", "New Folder..."), *typed("A", SCAN_A), *RETURN), (MAKE_FOLDER,)),
    # ...and TWO WINDOWS SHOWN AS TEXT (win_bdall over a second WNODE)
    "two windows: View > Show as Text": Chain("window: A: opened again (two windows)", item("View", "Show as Text"),
                                              (VIEW_MENU, SET_VIEW_AND_SORT)),
    "files: a fifth entry, then the down arrow gadget clicked (a row)": Chain(
        A_FIFTH_ENTRY, clicked("the down arrow", from_the_bottom_right(SCROLL_GADGET_INSET, ARROW_BESIDE_THE_SIZER)),
        (SCROLL_A_WINDOW, SCROLL_HORIZONTALLY)),
})
# ---- end of group G3's wave-2 ----
# ---- band 6 wave 2, group G4 (units A, B) ----
# (Ruling R-W2-8, TRIED AND NOT KEPT: "window: Options > Save Desktop, Return", then the file clicked, File > Open,
# Return (Show) and a blank at its end — deskmain re-enters after the viewer and app_start parses the shell's buffer.
# It walks (PD0 1,438, the dispatcher's 188) and enters app_start, over THE SAME INF TEXT as "file: shown, a key at its
# end": deskmain's own app_save(0) before any show already writes the open window's #W line, its path "A:\*.*", into
# the buffer — so that chain reaches the window-line arms already, and this one reaches no routine and no arm more.)
# (the wave-2 fix pass's) A PRESS IN THE TEXT VIEW: act_bdown in a window shown as text — the file's line dragged to the
# trash (its dialog cancelled: Return) — and on the desktop of the machine booted as text (an icon put down: the
# windows' view word TEXT, the desktop's icons still icons)
TEXT_LINE_DRAGGED = "text view: A: opened, the file's line dragged to the trash, Return (Cancel)"
TEXT_PUT_DOWN = "text view: drive A: dragged to a bare spot of the desktop"
CHAINS.update({
    TEXT_LINE_DRAGGED: Chain("text view: A: opened", (*dragged("the file's line", text_line_point(THE_INF), "the trash", icon(THE_TRASH)),
                                                      *RETURN), (ICON_DRAG, addrs.AES_ROM_ACT_BDOWN)),
    TEXT_PUT_DOWN: Chain(INF_TEXT, dragged("drive A:'s icon", drive("A"), "a bare spot of the desktop", lambda _machine: BARE_DESKTOP),
                         (MOVE_DRVICON, addrs.AES_ROM_ACT_BDOWN)),
})
# ---- end of group G4's wave-2 ----
# ---- end of band 6 wave 2's ----
# ---- band 6 wave 4, slice H: THE DEVICES (ruling W6-R9; `aes_boot`'s formatter, drive B: and printer) ----
# The utilities' built-ins, each walked to its end on the ROM's machine: File > Format (single-sided, its dialog's
# default) formats drive A: through the formatter's two entries; drive A: dropped on drive B: copies it onto a SECOND
# DISK (a machine made with one in drive B: — the capture's machine counts two floppies, so the ROM's own two-drive
# path, no swap); a file's Print reaches the printer — on a machine made WITH ONE ON LINE when the alert is up (every
# other machine's port is declared by nothing) — "not ready" while the BIOS's five-second hold-off since power-on runs
# (the machine has been up 563 ticks: `PRINTER_RETRY_AT` is 0, and the driver answers 0 without touching the port),
# printed once that time has passed.
# (the wave-4 fix pass: each by its `addrs` name, the groups' — the utilities' dialog fetched and centred, drawn and run;
# Format's progress bar laid, the redraw before its alert; the copy's tracks; the show / print engine, a buffer read,
# a byte put)
UTILITY_DIALOG_SET_UP, UTILITY_DIALOG_RUN = addrs.AES_ROM_DESK_UTIL_OPEN, addrs.AES_ROM_DESK_UTIL_SHOW
FORMAT_LAID_OUT, FORMAT_ALERT_REDRAWN = addrs.AES_ROM_DESK_UTIL_BARS, addrs.AES_ROM_DESK_UTIL_REDRAW
COPY_TRACKS = addrs.AES_ROM_DESK_COPY_TRACKS
PRINT_ENGINE, PRINT_READ, PRINT_PUT = (addrs.AES_ROM_DESK_SHOW_OR_PRINT, addrs.AES_ROM_DESK_SHOW_NEXT_BYTE,
                                       addrs.AES_ROM_DESK_PRINT_CHAR)
DISK_IN_B = "the DESKTOP.INF machine, a second disk in drive B:"
MACHINES[DISK_IN_B] = lambda: aes_boot.with_a_disk_in_drive_b(aes_boot.inf_machine(), aes_boot.blank_disk())
SHOW_PRINT_ALERT = "file: File > Open (the Show / Print / Cancel alert)"
PRINTER_ON_LINE = "the Show / Print / Cancel alert's machine, a printer on line"
MACHINES[PRINTER_ON_LINE] = lambda: aes_boot.with_a_printer_on_line(walked(SHOW_PRINT_ALERT).machine)
FIVE_SECONDS = Step("five seconds pass (the printer's hold-off)", lambda _machine: (aes_boot.ticked(addrs.PRINTER_RETRY_HOLDOFF_TICKS),))
DEVICE_INSNS = 4_000_000                # a disk copied (measured 2,473,753), a file printed (1,513,290)


def answered(text, budget=STEP_INSNS):
    """The button reading `text` — its blanks aside, as an alert's and a utility dialog's are padded — of what is up,
    clicked (`aes_deskfun.alert_button_point`)."""
    def point(machine):
        import aes_deskfun              # (here: the desk's function modules import this one)
        return aes_deskfun.alert_button_point(text)(machine)
    return (Step(f"the {text!r} button clicked", _moved(point, *A_CLICK), None, budget),)


FORMAT_UP = "A: File > Format, the warning's OK (the FORMAT dialog)"
FORMATTED = "A: File > Format, OK, FORMAT clicked (formatted)"
COPY_UP = "drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)"
COPIED = "a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)"
NOT_READY = "file: File > Open, Print clicked (the printer not ready)"
CHAINS.update({
    FORMAT_UP: Chain("drive A: selected", (*item("File", "Format..."), *answered("OK")),
                     (DO_FORMAT, addrs.AES_ROM_DESK_FORMAT, UTILITY_DIALOG_SET_UP, UTILITY_DIALOG_RUN)),
    "A: File > Format, OK, EXIT clicked": Chain(FORMAT_UP, answered("EXIT"), (addrs.AES_ROM_DESKMAIN,)),
    FORMATTED: Chain(FORMAT_UP, pressed("FORMAT"), (FORMAT_LAID_OUT, FORMAT_ALERT_REDRAWN)),
    "A: formatted, the alert's OK, EXIT clicked": Chain(FORMATTED, (*answered("OK"), *answered("EXIT")),
                                                      (UTILITY_DIALOG_RUN, addrs.AES_ROM_DESKMAIN)),
    COPY_UP: Chain(INF_ICONS, (*dragged("drive A:'s icon", drive("A"), "drive B:", drive("B")), *answered("OK")),
                   (ICON_DRAG, addrs.AES_ROM_DESK_COPY_DISK, UTILITY_DIALOG_SET_UP, UTILITY_DIALOG_RUN)),
    "drive A: onto drive B:, OK, then Return (EXIT, the default)": Chain(COPY_UP, RETURN, (addrs.AES_ROM_DESKMAIN,)),
    COPIED: Chain(DISK_IN_B, (*dragged("drive A:'s icon", drive("A"), "drive B:", drive("B")), *answered("OK"),
                              Step("the dialog's 'COPY' clicked", _moved(lambda machine: button_point(machine, "COPY"), *A_CLICK),
                                   None, DEVICE_INSNS)),
                  (addrs.AES_ROM_DESK_COPY_DISK, COPY_TRACKS)),
    NOT_READY: Chain(PRINTER_ON_LINE, answered("Print"),
                     (addrs.AES_ROM_DESK_PRINT_FILE, PRINT_ENGINE, PRINT_READ, PRINT_PUT)),
    "file: the printer not ready, Cancel": Chain(NOT_READY, answered("Cancel"), (addrs.AES_ROM_DESKMAIN,)),
    "file: the printer not ready, Retry (not ready again)": Chain(NOT_READY, answered("Retry"), (addrs.AES_ROM_DESK_WAIT,)),
    "file: the printer not ready, five seconds, Retry (printed)": Chain(
        NOT_READY, (FIVE_SECONDS, *answered("Retry", DEVICE_INSNS)), (PRINT_READ, PRINT_PUT, addrs.AES_ROM_DESKMAIN)),
    "file: File > Open, five seconds, Print clicked (printed)": Chain(
        PRINTER_ON_LINE, (FIVE_SECONDS, *answered("Print", DEVICE_INSNS)),
        (addrs.AES_ROM_DESK_PRINT_FILE, PRINT_ENGINE, PRINT_READ, PRINT_PUT)),
})
# ---- end of band 6 wave 4, slice H's ----
# ---- band 6 wave 4: each group APPENDS its own chains inside its own block (the order above unchanged), and adds
# their count to `test_aes_desk_rom.py`'s matching block ----
# ---- band 6 wave 4, group G1 (unit M) ----
# (the wave-4 fix pass, reviewer A's finding 2) THE ENGINE'S WORDS STALE BY A RUN: the INF shown to its end, then shown
# again — the second show's arrival finds `$9556` -1, `$9558` 1 and `$955a` the first's count (529), as the first run
# left them (reviewer A's probe, `probe_stale.py`).
SHOWN_AGAIN = "file: shown, a key at its end — the file clicked, File > Open, shown again"
# THE VIEWER'S KEYS at its "-MORE-" (the fix pass, reviewer A's finding 1): each typed at the named stop as a chain types
# its blank there — the scan codes of q, x, F1 and the Control key (^C: Control held, then C).
SCAN_Q, SCAN_X, SCAN_F1, SCAN_CONTROL = 0x10, 0x2d, 0x3b, 0x1d
CHAINS.update({
    SHOWN_AGAIN: Chain("file: shown, a key at its end", (*clicked("the file's icon", icon(THE_INF)), *item("File", "Open"),
                                                         *shown((VIEWER_AT_THE_FILE_S_END,))), (SHOW_FILE,)),
})
# ---- end of group G1's wave-4 ----
# ---- band 6 wave 4, group G2 (unit N) ----
# THE COPY REFUSED: a SINGLE-SIDED disk in drive B: (the blank disk's boot sector made one side's — half its sectors,
# one side; slice H's DRIVE_B class), drive A:'s two-sided disk dropped on it: COPY finds the two disks' BPBs differ
# in their sides and util_error says "not the same type" (`$fee364`'s alert, which no other run reaches).
import struct                           # (here, inside the group's block: the module's head is no group's)


def single_sided_disk():
    """The blank disk with a one-sided boot sector: its sectors and sides words halved / 1 (`aes_boot`'s offsets)."""
    disk, boot = bytearray(aes_boot.blank_disk()), aes_boot.BOOT_SECTOR_BPB
    fields = list(boot.unpack_from(disk, aes_boot.st_build.BPB_AT))
    sides_at = aes_boot.BOOT_SECTOR_GEOMETRY_AT + aes.WORD_BYTES
    fields[SECTORS_FIELD] //= aes_boot.st_build.HEADS
    boot.pack_into(disk, aes_boot.st_build.BPB_AT, *fields)
    struct.pack_into("<H", disk, sides_at, 1)
    return bytes(disk)


SECTORS_FIELD = 5                       # BOOT_SECTOR_BPB's sectors word (`aes_boot.geometry_of`'s)
SINGLE_SIDED_IN_B = "the DESKTOP.INF machine, a single-sided disk in drive B:"
MACHINES[SINGLE_SIDED_IN_B] = lambda: aes_boot.with_a_disk_in_drive_b(aes_boot.inf_machine(), single_sided_disk())
NOT_THE_SAME_TYPE = "a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type)"
CHAINS.update({
    NOT_THE_SAME_TYPE: Chain(SINGLE_SIDED_IN_B, (*dragged("drive A:'s icon", drive("A"), "drive B:", drive("B")), *answered("OK"),
                                                 Step("the dialog's 'COPY' clicked",
                                                      _moved(lambda machine: button_point(machine, "COPY"), *A_CLICK))),
                             (addrs.AES_ROM_DESK_COPY_DISK, addrs.AES_ROM_DESK_UTIL_ERROR)),
})
# ---- end of group G2's wave-4 ----
# ---- end of band 6 wave 4's ----

# A LAUNCH FREES THE DESK'S BLOCKS (deskmain's return) and the loader CLEARS the program's memory over them: the
# kilobyte that was the userdef stack is stored whole, which is no depth of a stack. (Band 6 wave 4: so does THE DISK
# COPY — a built-in, run by the shell after deskmain's return, whose buffer is all of free memory but a kilobyte, read
# full of tracks.)
THE_DESK_S_BLOCKS_ARE_CLEARED_IN = ("files: the program double-clicked — launched", COPIED)

Walked = namedtuple("Walked", "machine steps")
Walked.__doc__ = """A chain walked: the `Machine` its last step left, and a `Stepped` for each of ITS OWN steps."""


@functools.cache
def walked(name):
    """THE CHAIN `name` (a key of `CHAINS`) WALKED from the machine its predecessor left: a `Walked`. Each step's hand
    is asked of the machine the step before left; a step that follows one ended at a named stop is taken THERE."""
    chain = CHAINS[name]
    machine = MACHINES[chain.after]() if chain.after in MACHINES else walked(chain.after).machine
    steps, stands_at = [], None
    for step in chain.steps:
        until = STOPS[step.until] if step.until else None
        steps.append(stepped(machine.boot, tuple(step.hand(machine)), until, stands_at, step.budget))
        machine, stands_at = aes_boot.Machine(steps[-1].boot), until
    return Walked(machine, tuple(steps))


# ---- WHAT A CHAIN REACHED: read off its steps' profiles ------------------------------------------------------------------------------
def cycles_at(profile):
    """`{PC: cycles}` of one step's GEM text."""
    return dict(profile.text)


def entered(name):
    """THE ROUTINES OF BAND 6 THE CHAIN `name`'s OWN STEPS ENTERED: those whose first instruction ran, a frozenset."""
    ran = set().union(*(cycles_at(step.profile) for step in walked(name).steps))
    return frozenset(start for start in routines() if start in ran)


def reach(names=None):
    """THE REACH TABLE, a derivation: `{routine: the chains whose own steps entered it, in `CHAINS`' order}` over the
    chains `names` (all of them) — every routine of band 6 has a row, an empty one where no chain reaches it."""
    table = {start: [] for start in routines()}
    for name in names or CHAINS:
        for start in entered(name):
            table[start].append(name)
    return {start: tuple(chains) for start, chains in table.items()}


# ---- STACK DEPTHS, off the runs' write ledgers ------------------------------------------------------------------------------------------
PD0_STACK, PD1_STACK = "PD0's stack (the desk's: UDA0)", "PD1's stack (the screen manager's: UDA1)"
DISPATCHER_STACK, USERDEF_STACK = "the dispatcher's stack", "the desk's G_USERDEF stack"
USERDEF_STACK_BYTES = aes.header_constants("deskmem.h")["USERDEF_STACK_BYTES"]
# THE SPANS OF PD0's AND PD1's STACKS (`stacks`), in bytes — ONE HOME, read by both shores' batteries
# (`test_aes_desk_rom.py`, `test_aes_desk_ours.py`: each asserts its machines' spans are these).
PD0_BYTES, PD1_BYTES = 1792, 1196


def stacks(machine):
    """THE STACKS OF `machine`, `{which: (lo, hi)}`, each through the machine's own pointers: PD0's — from the end of
    its UDA's state block to the next UDA —, PD1's (`aes_gemctrl.its_stack`), the dispatcher's, and the kilobyte under
    the top the desk's start-up kept for ub_trampoline."""
    desk, manager, _spare = machine.static_processes()
    pd1_lo, pd1_hi, _why = aes_gemctrl.its_stack(machine.ram)
    userdef_top = machine.long(aes.AES_USERDEF_STACK) & BUS
    return {PD0_STACK: (desk.uda + aes.UDA_STATE_BYTES, manager.uda), PD1_STACK: (pd1_lo, pd1_hi),
            DISPATCHER_STACK: aes_event.DISPATCHER_STACK, USERDEF_STACK: (userdef_top - USERDEF_STACK_BYTES, userdef_top)}


def depth_stored(stored, lo, hi):
    """How deep the `(start, length)` runs `stored` reach into the stack `[lo, hi)`: from its top down to the lowest
    byte stored, 0 where none was."""
    reached = [max(start, lo) for start, length in stored if start < hi and start + length > lo]
    return hi - min(reached) if reached else 0


def depths(name):
    """THE DEPTH OF EACH STACK OVER THE CHAIN `name`'s OWN STEPS, `{which: bytes}`: the deepest any one step's run
    stored (its write ledger: `Boot.stored`)."""
    chain = walked(name)
    spans = stacks(chain.machine)
    for step in chain.steps:
        if step.boot.writes_truncated:
            raise Refused(f"a step of {name!r} saturated its write ledger: what it stored is not known")
    return {which: max(depth_stored(step.boot.stored, lo, hi) for step in chain.steps) for which, (lo, hi) in spans.items()}


def deepest(which, names=None):
    """`(the chain, the bytes)` of the chain whose own steps took the stack `which` deepest (the first, of equals) —
    the userdef stack's over the chains in which it IS a stack (`THE_DESK_S_BLOCKS_ARE_CLEARED_IN`)."""
    asked = [name for name in names or CHAINS if which != USERDEF_STACK or name not in THE_DESK_S_BLOCKS_ARE_CLEARED_IN]
    return max(((name, depths(name)[which]) for name in asked), key=lambda found: found[1])


# ---- band 6 slice H (slice B's): THE OUR SHORE — the same chains, walked on machines OUR gem_entry booted -------------------------
# The binding (slice B0) lays OUR Line-F call table at `$cc24` on every machine of ours: the ROM's desk — every routine
# of it not yet flipped — runs over OUR AES. So each chain of `CHAINS` is walked a second time, on THE OUR-BOOT MACHINE
# of its capture (`aes_boot.booted(..., laid=AT_GEM_ENTRY)`, ruling W4-R1's labelled staging), by the same hands — every
# point read off THAT machine's own trees — and `test_aes_desk_ours.py` holds the two walks to one another. This block
# makes the walk and reads it; it compares nothing.
#   * A STEP OF OURS (`stepped_ours`) is `stepped`'s twin for a machine that HOLDS A BLOB (the ROM's step refuses one):
#     the same continuation, made and not served, the same profile — and the blob's own cycles beside it. Kept: like
#     `aes_boot.continued` of a machine of ours, it runs THE BLOB, never the host library, and its key holds the blob's
#     bytes (the `Boot`'s `OurBoot`): a rebuilt blob is another question.
#   * A NAMED STOP HAS AN ADDRESS ON EACH SHORE (`our_stop`): the entry of OUR routine where one is declared
#     (`OUR_STOPS`: the rubber box's poll is gr_stilldn's entry, and gr_stilldn is band 3's C), else the ROM's own —
#     the viewer's two key waits lie inside the show engine's body, the ROM's on our machine until unit M flips (its
#     slice declares their C-side stops).
#   * WHO RAN (ruling W6-R5): every PC of the ROM's GEM text a step ran is CHARGED TO ITS ROUTINE — the last start of
#     the AES map's inventory at or below it, so every routine bounds its neighbour (`charged`) — and the ROM's text
#     that may run on our machine is DECLARED and shrinks with each flip: band 6's routines whose entry of the bound
#     table is still the ROM's longword, or that no entry names (`still_the_rom_s`), and the ROM's text of bands 0-5
#     those reach by a `bsr`, a `jsr`, a `jmp` or a branch (`ROM_TEXT_UNDER_ROM_CALLERS`).
import bisect                           # (here, inside the slice's block: the module's head is no slice's)
from collections import Counter

from harness import BASE_IMAGE

import isr
import transcription
import vdi

OUR_BLOB = "the shipped blob"           # what ships, and what W6-R4's gate is measured on (the cut's numbers are its)


@functools.cache
def our_blob():
    return isr.blob_named(OUR_BLOB)


def _our_boot(capture, disk):
    return aes_boot.Machine(aes_boot.booted(capture, disk, ours=aes_boot.ours_of(our_blob()), laid=aes_boot.AT_GEM_ENTRY))


# The machines of `MACHINES`, booted by OUR gem_entry over the same captures and disks (the devices' made as theirs are).
OUR_MACHINES = {
    INF_ICONS: lambda: _our_boot(aes_boot.inf_preinit(), aes_boot.inf_disk_of()),
    INF_TEXT: lambda: _our_boot(aes_boot.inf_preinit(), aes_boot.inf_disk_of(aes_boot.VIEW_AS_TEXT)),
    FILES: lambda: _our_boot(aes_boot.files_preinit(), aes_boot.files_disk_of()),
    DISK_IN_B: lambda: aes_boot.with_a_disk_in_drive_b(OUR_MACHINES[INF_ICONS](), aes_boot.blank_disk()),
    SINGLE_SIDED_IN_B: lambda: aes_boot.with_a_disk_in_drive_b(OUR_MACHINES[INF_ICONS](), single_sided_disk()),
    PRINTER_ON_LINE: lambda: aes_boot.with_a_printer_on_line(walked_ours(SHOW_PRINT_ALERT).machine)}

# ---- who ran: each PC charged to its routine; the ROM's text declared still to run ----
# THE ROM'S TEXT OF BANDS 0-5 THAT A ROUTINE STILL THE ROM'S REACHES OTHERWISE THAN THROUGH THE TABLE — so the ROM's,
# on our machine too, under that caller (measured over the campaign: each ran on our shore; each goes when its last
# such caller flips). `{its start: who reaches it, and how}`.
GEMGRAF_HELPER, DOS_CALL, DOS_CALL_BODY = 0xfdae38, 0xfe39b6, 0xfe3c3e
DOS_FREE, DOS_SFIRST_S_ONE, LMUL = 0xfe3c26, 0xfe3a08, 0xfe3db4
ROM_TEXT_UNDER_ROM_CALLERS = {
    GEMGRAF_HELPER: "gemgraf's helper: `bsr` from unit O's leaf $fda8a8",
    DOS_CALL: "__DOS: `bsr` from unit O's DOS-glue leaves",
    DOS_CALL_BODY: "__DOS's body: `jmp` from __DOS",
    DOS_FREE: "dos_free's body, ours through the table: unit O's stubs $fe3c16..$fe3c22 (`moveq #n,d1; bra`) branch into it",
    DOS_SFIRST_S_ONE: "dos_sfirst's `moveq #1 / rts`: unit O's leaf $fe3b02 branches into it",
    LMUL: "Alcyon's lmul: `jsr` from deskapp's $fdb220"}
# ...a span ENTERED PAST ITS START by the callers that reach it (reviewer B's F5): the routine's own entry is ours
# through the table, so not a cycle of the ROM's text before `past` may run on our shore. `{its start: past}`.
DOS_FREE_BODY = 0xfe3c28                # where unit O's stubs `bra` to: dos_free's own entry, `$fe3c26`, is our table's
ENTERED_PAST_ITS_START = {DOS_FREE: DOS_FREE_BODY}


def charged(text):
    """`{routine: cycles}` of a profile's GEM text (`Profile.text`): each PC charged to the routine whose start — of
    EVERY start the AES map's inventory lists — is the last at or below it (a span bounded by band 6's starts alone
    would charge trp14's cycles to trp13, its neighbour in the ROM)."""
    starts, per = inventoried(), Counter()
    for pc, cycles in text:
        at = bisect.bisect_right(starts, pc) - 1
        assert at >= 0, f"{pc:#x} lies below the inventory's first routine"
        per[starts[at]] += cycles
    return dict(per)


def _table_of(memory, at):
    return tuple(case.long_in(memory, at + index * LONG_BYTES) for index in range(aes.AES_LINEF_TABLE_ENTRIES))


@functools.cache
def flipped(blob=None):
    """BAND 6'S ROUTINES WHOSE ENTRY OF THE TABLE `blob` (ours by default) BINDS IS OURS — a longword other than the
    ROM's own: on a machine of ours a ROM caller's Line-F call of one runs our code. A frozenset of their starts."""
    blob = blob or our_blob()
    bound = _table_of(blob.blob, blob.entry(transcription.LINEF_TABLE_SYMBOL) - blob.base)
    return frozenset(rom for rom, ours in zip(_table_of(BASE_IMAGE, aes.AES_LINEF_TABLE), bound) if ours != rom) & frozenset(routines())


def still_the_rom_s(blob=None):
    """BAND 6'S ROUTINES STILL THE ROM'S on a machine of `blob` (W6-R5's declared spans, by their starts): not
    `flipped` — their entry the ROM's, or no entry at all (reached by `bsr` or by value: the ROM's here until the slice
    that flips one says so in this function)."""
    return frozenset(routines()) - flipped(blob)


# ---- a step of ours, its named stops ----
OUR_STOPS = {RUBBER_BOX_POLL: "aes_gr_stilldn"}     # N4: band 3's C gr_stilldn — its entry is the poll's
PROFILE_HELD_BY_OUR_STEP = "a profiled step of the hands' campaign on our shore (`aes_desk.stepped_ours`)"
OurStepped = namedtuple("OurStepped", "boot profile blob")
OurStepped.__doc__ = """A step of ours: the `Boot` there, the step's `Profile` (`stepped`'s) and `blob`, the cycles the
blob's own span ran."""


def our_stop(name, blob=None):
    """THE NAMED STOP `name` ON OUR SHORE (the block's comment): our routine's entry, or the ROM's own address."""
    return (blob or our_blob()).entry(OUR_STOPS[name]) if name in OUR_STOPS else STOPS[name]


@derived.kept
def stepped_ours(boot, received, until=None, at=None, budget=STEP_INSNS):
    """ONE STEP OF OURS: `stepped`, of a machine that HOLDS A BLOB (`boot`: an our-boot's, at OUR idle or stopped at a
    stop of ours) — an `OurStepped`. REFUSED BY NAME on the ROM's machine (`stepped` is its step)."""
    ours = aes_boot.blob_of(boot)
    if ours is None:
        raise Refused("a step of ours is of a machine that holds a blob: this is the ROM's machine (`stepped`)")
    aes_event.vet_the_profile_is_free("a step of the hands' campaign on our shore")
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        with aes_event.profile_held(PROFILE_HELD_BY_OUR_STEP):
            after = aes_boot.continued.derive(boot, tuple(received), budget, until, at)
        profile, blob = _profile_read(), emu.prof_cycles(ours.base, ours.end)
    finally:
        emu.prof_enable(False)
    return OurStepped(after, profile, blob)


@functools.cache
def walked_ours(name):
    """THE CHAIN `name` WALKED ON OUR SHORE (`walked`'s twin, from its predecessor's machine of ours or `OUR_MACHINES`'):
    a `Walked` of `OurStepped`s — REFUSED BY NAME, its step said, where a step's run is refused."""
    chain = CHAINS[name]
    machine = OUR_MACHINES[chain.after]() if chain.after in OUR_MACHINES else walked_ours(chain.after).machine
    steps, stands_at = [], None
    for nth, step in enumerate(chain.steps):
        until = our_stop(step.until) if step.until else None
        try:
            steps.append(stepped_ours(machine.boot, tuple(step.hand(machine)), until, stands_at, step.budget))
        except Refused as refused:
            raise Refused(f"step {nth} of {name!r} on our shore ({step.what}): {refused}") from refused
        machine, stands_at = aes_boot.Machine(steps[-1].boot), until
    return Walked(machine, tuple(steps))


def screen_of(machine):
    """The screen's bytes as `machine` holds them."""
    return bytes(machine.ram[vdi.SCREEN.base:vdi.SCREEN.base + vdi.SCREEN.bytes])


def desk_block(ram):
    """`(its address, its bytes)`: the desk's globals block a megabyte holds (`aes.AES_DESK_GLOBALS`)."""
    block = case.long_in(ram, aes.AES_DESK_GLOBALS) & BUS
    return block, bytes(ram[block:block + aes_event.DESK_GLOBALS_BYTES])


def our_desk_block(machine):
    """...of a machine of ours, EVERY CODE ADDRESS GIVEN THE ROM'S NAME (`aes_ourboot.mapped_back`: the registry's
    slots, the trampoline's in the desk's USERBLKs among them)."""
    import aes_ourboot                  # (here: the comparison alone needs its registry, a heavy import)
    return desk_block(aes_ourboot.mapped_back(machine.ram, our_blob()))
# ---- end of band 6 slice H's ----
