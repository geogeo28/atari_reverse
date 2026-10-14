"""THE DESK'S HIT TESTS AND ICON DRAGS (`src/desk/deskact.c`; band 6 wave 1b, group G3, unit B), HELD AT TIER 1 AT
THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskact.arrival`): a chain of the hands stopped at the routine's first instruction,
    the arguments read off the frame the desk's caller pushed. A routine whose callees never reach the dispatcher is
    the kit's plain differential over the arrival's megabyte (`aes_deskact.plain`); one that calls a binding of unit
    D's — which yields — is A ROW THAT SWITCHES (`aes_deskact.row_of`, `held`: `aes_switching.companion`, nothing
    dropped), its wait ended by the case's `wake`.
  * WHERE NO CHAIN REACHES AN ARM, A LABELLED ARGUMENT CLASS (its label in the id): the same machine with other
    arguments, or — where it says LAID — a staging laid over it (points, the windows' view word).
  * D0 AT RETURN: an answering routine's word or long is held to the ROM's run IN PLACE at every arrival it returns
    from without idling; a void routine's D0 is the ROM's leftover — A NAMED, COUNTED DIVERGENCE, read by no caller.
"""
import struct
from collections import Counter

import pytest

import aes
import aes_desk
import aes_deskact as da
import aes_deskbind as db
import aes_event
import case

Case, UNPOISONED = da.Case, da.UNPOISONED
BUS = da.BUS

# THE CHAINS
SELECTED, OPEN_A, OPENED, AS_TEXT = "drive A: selected", "A: File > Open", "A: opened", "window: View > Show as Text"
DRAGGED, RUBBER = "drive A: dragged to the trash, Return", "a rubber box on the desktop, round the trash"
FILE_TRASHED, FILES_OPENED = "file: dragged to the trash, OK", "files: A: opened"
CORNER = "drive A:'s object clicked at its corner, outside its image and its label"
PUT_DOWN, FILE_SELECTED = "drive A: dragged to a bare spot of the desktop", "file: selected"
TEXT_VIEW_OPENED = "text view: A: opened"
TWO_WINDOWS = "window: A: opened again (two windows)"
# THE WAKES of a row's wait (`aes_deskbind.row_of`'s, unit D's)
LET_GO, CARRIED_OFF = "the button let go at the first idle", "the mouse carried off at the first idle"
AWAY = (300, 150)                       # a point of the desktop far from every icon: out of a drag's square
WAKES = {LET_GO: dict(at_idle={0: aes_event.release}), CARRIED_OFF: dict(at_idle={0: aes_event.move_to(*AWAY)})}

DESK_ROOT, OUTSIDE_EVERY_TREE = db.DESK_GLOBALS["DESKTOP_ROOT"], -1
AN_OBJECT_NO_ICON_IS, A_TYPE_NO_NODE_HAS = 0x7FFF, 9
A_DESKTOP_DRIVE = 2                     # a desktop drive icon's ANODE type (its flags AF_ISDESK)
DESK_VIEW, DESK_ICON_INDEX, DESK_ICON_BLOCKS = (db.DESK_GLOBALS[name] for name in ("DESK_G_IVIEW", "DESK_G_INDEX", "DESK_G_IBLIST"))
A_VIEW_NEITHER = 2
TEXT_LINE_CHARS = 45


def _with(index, value):
    return lambda arrived: (*arrived.arguments[:index], value(arrived) if callable(value) else value, *arrived.arguments[index + 1:])


def _desk(arrived):
    return case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & BUS


def _past_the_text_line(arrived):
    """act_chkobj's own arguments, the rectangle moved right of the object's text line (a line of 45 cells)."""
    tree, root, obj = arrived.arguments[:3]
    ram = arrived.boot.ram
    line_x = sum(case.word_in(ram, (tree & BUS) + each * aes.OB_BYTES + aes.OB_X) for each in (root, obj))
    return (*arrived.arguments[:3], line_x + TEXT_LINE_CHARS * case.word_in(ram, aes.AES_GL_WCHAR) + 1, *arrived.arguments[4:])


def _disabled(arrived):
    """LAID: act_chg's object with its DISABLED bit set (no icon of the desk's is ever disabled)."""
    tree, obj = arrived.arguments[1] & BUS, arrived.arguments[3]
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(arrived.boot.ram, state) | 1 << aes.OB_STATE_DISABLED_BIT)}


def _selected_already(arrived):
    """LAID: act_chg's object SELECTED already (every chain's act_chg changes a bit the object has not)."""
    tree, obj = arrived.arguments[1] & BUS, arrived.arguments[3]
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(arrived.boot.ram, state) | 1 << aes.OB_STATE_SELECTED_BIT)}


def _data_as_application(arrived):
    """LAID: every ANODE in use of the type app_afind asks for, its data pattern (a_pdata) its application pattern's
    (a_pappl) — no INF line names a node whose two patterns are one."""
    ram, wanted, pokes = arrived.boot.ram, arrived.arguments[1], {}
    node = case.long_in(ram, _desk(arrived) + db.DESK_GLOBALS["DESK_ANODES_IN_USE"]) & BUS
    while node:
        if case.word_in(ram, node + db.DESK_GLOBALS["ANODE_TYPE"]) == wanted:
            pokes[node + db.DESK_GLOBALS["ANODE_PDATA"]] = struct.pack(">I", case.long_in(ram, node + db.DESK_GLOBALS["ANODE_PAPPL"]))
        node = case.long_in(ram, node + db.DESK_GLOBALS["ANODE_NEXT"]) & BUS
    assert pokes, "no node of the type asked"
    return pokes


# A TREE OF MORE SELECTED CHILDREN THAN gr_accobs KEEPS, laid in the group's own tree band (`aes_deskact.TREE_BAND_AT`,
# dead at the arrival): the root at (ROOT_X, ROOT_Y), each child's place its index's.
MORE_THAN_KEPT = 61                     # GR_ACCOBS_MAX (`desk/deskact.h`) is 60
ROOT_X, ROOT_Y = 100, 200


def _a_wide_selection(arrived):
    """LAID: the tree — root 0, children 1..MORE_THAN_KEPT linked in order, every one SELECTED — over bytes the
    arrival's machine holds dead."""
    objects = [struct.pack(">hhhHHHIhhhh", aes.OB_NIL, 1, MORE_THAN_KEPT, aes.G_BOX, 0, 0, 0, ROOT_X, ROOT_Y, 0, 0)]
    for index in range(1, MORE_THAN_KEPT + 1):
        following = index + 1 if index < MORE_THAN_KEPT else 0
        objects.append(struct.pack(">hhhHHHIhhhh", following, aes.OB_NIL, aes.OB_NIL, aes.G_ICON, 0, 1 << aes.OB_STATE_SELECTED_BIT,
                                   0, index, 2 * index, 1, 1))
    tree = b"".join(objects)
    assert len(tree) <= da.TREE_BAND_BYTES and not any(arrived.boot.ram[da.TREE_BAND_AT:da.TREE_BAND_AT + len(tree)])
    return {da.TREE_BAND_AT: tree}


def _object_place(arrived):
    """(x, y) of act_chkobj's object on the screen: its root's place and its own."""
    tree, root, obj = arrived.arguments[0] & BUS, arrived.arguments[1], arrived.arguments[2]
    word = lambda index, field: aes.signed(case.word_in(arrived.boot.ram, tree + index * aes.OB_BYTES + field))  # noqa: E731
    return word(root, aes.OB_X) + word(obj, aes.OB_X), word(root, aes.OB_Y) + word(obj, aes.OB_Y)


def _on_the_label_alone(arrived):
    """act_chkobj's own arguments, the point one pixel inside the icon's LABEL (its ICONBLK's text rectangle), clear of
    its image."""
    ram, desk = arrived.boot.ram, _desk(arrived)
    obj = arrived.arguments[2]
    block = desk + DESK_ICON_BLOCKS + aes.signed(case.word_in(ram, desk + DESK_ICON_INDEX + 2 * obj)) * aes.IB_BYTES
    x, y = _object_place(arrived)
    label_x, label_y = (aes.signed(case.word_in(ram, block + field)) for field in (aes.IB_XTEXT, aes.IB_YTEXT))
    return (*arrived.arguments[:3], x + label_x + 1, y + label_y + 1, 1, 1)


ABOVE_THE_LINE = (10, -12, 20, 10)      # (dx, dy, w, h) from the line's corner: wider than tall, ending 2 rows above it
INTO_THE_LINE = (10, 10, 1, 1)          # ...a point ten rows down: inside a line a character cell (16 rows) tall
TALL_CELL = 16


def _from_the_line(dx, dy, w, h):
    def arguments(arrived):
        x, y = _object_place(arrived)
        return (*arrived.arguments[:3], x + dx, y + dy, w, h)
    return arguments


TWO_CORNERS = (10, 20, 40, 5)           # two icons' corners, x apart from y
ONE_CORNER = (0, 150)                    # (a snap to the icons' grid rounds a few pixels away)


def _corners_laid(*words):
    return lambda _arrived: {da.BAND_AT: struct.pack(f">{len(words)}h", *words)}


def _except_selected(arrived):
    """LAID: act_allchg's excepted icon SELECTED (no chain's arrival has it so)."""
    tree, obj = arrived.arguments[1] & BUS, arrived.arguments[3]
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(arrived.boot.ram, state) | 1 << aes.OB_STATE_SELECTED_BIT)}


def _rect_laid(rect_of):
    """LAID: a rectangle in the group's band, `rect_of(arrival) -> (x, y, w, h)`."""
    return lambda arrived: {da.BAND_AT: struct.pack(">4h", *rect_of(arrived))}


def _a_corner_of_the_box(arrived):
    """The top left 10 by 10 of act_allchg's rectangle (the rubber box): a clip smaller than what changes."""
    box = arrived.arguments[4] & BUS
    return (*(aes.signed(case.word_in(arrived.boot.ram, box + 2 * nth)) for nth in range(2)), SMALL_CLIP, SMALL_CLIP)


SMALL_CLIP = 10


def _down_the_label_right_of_the_image(arrived):
    """A one-pixel-wide rectangle from the top of drive A:'s object (8) down into its label, right of its image: it
    touches the label alone — and laid on its side, neither."""
    ram, desk, tree = arrived.boot.ram, _desk(arrived), arrived.arguments[1] & BUS
    block = desk + DESK_ICON_BLOCKS + aes.signed(case.word_in(ram, desk + DESK_ICON_INDEX + 2 * DRIVE_A)) * aes.IB_BYTES
    field = lambda at: aes.signed(case.word_in(ram, block + at))     # noqa: E731
    word = lambda index, at: aes.signed(case.word_in(ram, tree + index * aes.OB_BYTES + at))     # noqa: E731
    x, y = word(DESK_ROOT, aes.OB_X) + word(DRIVE_A, aes.OB_X), word(DESK_ROOT, aes.OB_Y) + word(DRIVE_A, aes.OB_Y)
    right_of_the_image = field(aes.IB_XICON) + field(aes.IB_XICON + 4) + 1
    assert right_of_the_image < field(aes.IB_XTEXT) + field(aes.IB_XTEXT + 4), "the label is no wider than the image"
    return x + right_of_the_image, y + 1, 1, field(aes.IB_YTEXT) + 1


DRIVE_A = 8


# gr_isdown's rectangle ENTERED awaited (leave 0), taller than wide, the mouse carried into it: AWAY lies inside
# (295..305, 100..160) and outside the same rectangle laid on its side (295..355, 100..110)
TALL_BOX = (0, 295, 100, 10, 60)


POINTS_WITH_NEGATIVES = (-5, 3, 10, -7, 2, 2)     # three points, a negative x and a negative y among them


def _points_laid(_arrived):
    return {da.BAND_AT: struct.pack(">6h", *POINTS_WITH_NEGATIVES)}


CASES = (
    # app_afind: a desktop icon by its object; a file's name as a node's data; as an application; a folder by its type
    Case("AES_ROM_APP_AFIND", SELECTED, arm=lambda a: a[0] == 1),
    Case("AES_ROM_APP_AFIND", OPEN_A, 1, arm=lambda a: a[:2] == (0, 0)),
    Case("AES_ROM_APP_AFIND", FILES_OPENED, 4, arm=lambda a: a[:2] == (0, 0)),
    Case("AES_ROM_APP_AFIND", FILES_OPENED, 1, arm=lambda a: a[:2] == (0, 1)),
    Case("AES_ROM_APP_AFIND", SELECTED, why="an object no desktop icon is: 0 after the whole list", arguments=_with(2, AN_OBJECT_NO_ICON_IS)),
    Case("AES_ROM_APP_AFIND", OPEN_A, 1, why="a type no node has: 0 after the whole list", arguments=_with(1, A_TYPE_NO_NODE_HAS)),
    Case("AES_ROM_APP_AFIND", OPEN_A, 1, why="a type word whose low byte is the file's type (0x0100): no node's — a WORD compare",
         arguments=_with(1, 0x0100)),
    Case("AES_ROM_APP_AFIND", SELECTED, why="an object word whose low byte is drive A:'s (0x0108): no icon's — a WORD compare",
         arguments=_with(2, 0x0108)),
    Case("AES_ROM_APP_AFIND", SELECTED, why="a file's search for a desktop icon's type and name (2, its own text): the icon's node skipped",
         arguments=lambda arrived: (0, A_DESKTOP_DRIVE, *arrived.arguments[2:])),
    # (the program's own arrival, matched as an application: with its node's two patterns one, the DATA's is tried first)
    Case("AES_ROM_APP_AFIND", FILES_OPENED, 4, why="a node whose data pattern is its application's: matched as data, isapp 0",
         arguments=lambda arrived: arrived.arguments, laid=("each node of the type, its a_pdata its a_pappl", _data_as_application)),
    # gr_accobs: the desktop's selection (one drive) and a window's (one file)
    Case("AES_ROM_GR_ACCOBS", DRAGGED), Case("AES_ROM_GR_ACCOBS", FILE_TRASHED),
    Case("AES_ROM_GR_ACCOBS", DRAGGED, why="61 selected children: 60 kept (no chain selects as many)",
         arguments=lambda arrived: (da.TREE_BAND_AT, 0, da.BAND_AT, da.BAND_AT + aes.WORD_BYTES),
         laid=("a tree of 61 selected children", _a_wide_selection)),
    # gr_extent: an icon's outline (nine points) and the corners of one icon
    Case("AES_ROM_GR_EXTENT", DRAGGED, 0), Case("AES_ROM_GR_EXTENT", DRAGGED, 1), Case("AES_ROM_GR_EXTENT", FILE_TRASHED, 1),
    Case("AES_ROM_GR_EXTENT", DRAGGED, why="points with a negative x and a negative y (SIGNED compares)",
         arguments=lambda arrived: (3, da.BAND_AT, arrived.arguments[2]), laid=("three points", _points_laid)),
    Case("AES_ROM_GR_OBALIGN", DRAGGED), Case("AES_ROM_GR_OBALIGN", FILE_TRASHED),
    # act_chkobj: an icon hit at a point; an icon's whole rectangle; a text line; an icon's object MISSED (its corner)
    Case("AES_ROM_ACT_CHKOBJ", SELECTED, 0), Case("AES_ROM_ACT_CHKOBJ", SELECTED, 1), Case("AES_ROM_ACT_CHKOBJ", AS_TEXT),
    Case("AES_ROM_ACT_CHKOBJ", OPEN_A), Case("AES_ROM_ACT_CHKOBJ", CORNER, 0, arm=lambda a: a[5:] == (1, 1)),
    Case("AES_ROM_ACT_CHKOBJ", TEXT_VIEW_OPENED, 0, arm=lambda a: a[1] == DESK_ROOT),     # (the desktop's own: icons, whatever the view)
    Case("AES_ROM_ACT_CHKOBJ", TWO_WINDOWS, 4),         # (the second window's icon: far from the screen's corner)
    Case("AES_ROM_ACT_CHKOBJ", AS_TEXT, why="a rectangle right of the text line (no object is wider than its line): the root",
         arguments=_past_the_text_line),
    Case("AES_ROM_ACT_CHKOBJ", SELECTED, why="a point on the icon's label alone: the object", arguments=_on_the_label_alone),
    Case("AES_ROM_ACT_CHKOBJ", TWO_WINDOWS, 4, why="a point on the label alone of an icon far from the screen's corner: the object",
         arguments=_on_the_label_alone),
    Case("AES_ROM_ACT_CHKOBJ", AS_TEXT, why="a rectangle wider than tall, ending above the text line: the root",
         arguments=_from_the_line(*ABOVE_THE_LINE)),
    # (the chains' machine is a low-resolution one, 320 x 200: a cell 8 by 8, its height and width alike — so a cell 16 rows tall
    # is LAID, a high-resolution machine's, and a point ten rows down lies in the line only by the cell's HEIGHT)
    Case("AES_ROM_ACT_CHKOBJ", AS_TEXT, why="a point ten rows into a line a cell 16 rows tall: the object",
         arguments=_from_the_line(*INTO_THE_LINE), laid=("gl_hchar 16", lambda _arrived: {aes.AES_GL_HCHAR: struct.pack(">H", TALL_CELL)})),
    Case("AES_ROM_ACT_CHKOBJ", OPEN_A, why="a window's view neither icons nor text: the object", arguments=lambda a: a.arguments,
         laid=("the windows' view word 2", lambda arrived: {_desk(arrived) + DESK_VIEW: struct.pack(">H", A_VIEW_NEITHER)})),
    # ---- the rows that switch: a binding of unit D's under each
    Case("AES_ROM_GR_OBFIND", SELECTED), Case("AES_ROM_GR_OBFIND", RUBBER), Case("AES_ROM_GR_OBFIND", CORNER),
    Case("AES_ROM_GR_OBFIND", OPENED), Case("AES_ROM_GR_OBFIND", FILE_SELECTED),
    # (the drag let go over the trash: a point far below its own x — the two words in the other order find no trash)
    Case("AES_ROM_GR_OBFIND", DRAGGED, 3, arm=lambda a: a[3] > 4 * a[2]),
    Case("AES_ROM_GR_OBFIND", OPENED, why="a point outside the tree's root: objc_find's NIL, answered as it is",
         arguments=_with(2, OUTSIDE_EVERY_TREE)),
    Case("AES_ROM_GR_PLNS", DRAGGED, 0), Case("AES_ROM_GR_PLNS", DRAGGED, 1), Case("AES_ROM_GR_PLNS", FILE_TRASHED),
    Case("AES_ROM_GR_PLNS", DRAGGED, why="two icons, their corners x apart from y (the chains carry one, at (0, 0))",
         arguments=lambda arrived: (*arrived.arguments[:4], 2, da.BAND_AT), laid=("two corners", _corners_laid(*TWO_CORNERS))),
    Case("AES_ROM_GR_ISDOWN", DRAGGED, wake=LET_GO), Case("AES_ROM_GR_ISDOWN", DRAGGED, wake=CARRIED_OFF),
    Case("AES_ROM_GR_ISDOWN", DRAGGED, wake=CARRIED_OFF, why="a rectangle ENTERED awaited, taller than wide, the mouse carried into it",
         arguments=lambda arrived: (*TALL_BOX, *arrived.arguments[5:])),
    Case("AES_ROM_GR_BWAIT", DRAGGED, wake=LET_GO), Case("AES_ROM_GR_BWAIT", DRAGGED, wake=CARRIED_OFF),
    Case("AES_ROM_GR_BWAIT", FILE_TRASHED, wake=LET_GO),
    # move_drvicon: the one chain that puts a desktop icon down on a bare spot
    Case("AES_ROM_MOVE_DRVICON", PUT_DOWN),
    Case("AES_ROM_MOVE_DRVICON", PUT_DOWN, why="the icon's corner x apart from y (one icon's own is (0, 0))",
         arguments=lambda arrived: (*arrived.arguments[:4], da.BAND_AT), laid=("one corner", _corners_laid(*ONE_CORNER))),
    # act_chg: an icon selected and drawn; deselected; the trash lit and put out under a drag; a window's file selected
    Case("AES_ROM_ACT_CHG", SELECTED, arm=lambda a: a[6] == 1), Case("AES_ROM_ACT_CHG", OPEN_A, arm=lambda a: a[6] == 0),
    Case("AES_ROM_ACT_CHG", DRAGGED, 1), Case("AES_ROM_ACT_CHG", DRAGGED, 2), Case("AES_ROM_ACT_CHG", FILE_SELECTED),
    Case("AES_ROM_ACT_CHG", SELECTED, why="not drawn (every caller of the chains asks it drawn)", arguments=_with(7, 0)),
    Case("AES_ROM_ACT_CHG", SELECTED, why="a value of no bit: the state unchanged, nothing changed or drawn", arguments=_with(5, 0)),
    Case("AES_ROM_ACT_CHG", SELECTED, why="a DISABLED object, the check asked: refused, nothing changed", arguments=lambda a: a.arguments,
         laid=("the object's state DISABLED", _disabled)),
    Case("AES_ROM_ACT_CHG", SELECTED, why="a DISABLED object, the check not asked: changed", arguments=_with(8, 0),
         laid=("the object's state DISABLED", _disabled)),
    Case("AES_ROM_ACT_CHG", SELECTED, why="an object SELECTED already, set SELECTED: unchanged (an OR), nothing drawn",
         arguments=lambda a: a.arguments, laid=("the object's state SELECTED", _selected_already)),
    # act_allchg: the desktop's icons put out but one; a window's; those a rubber box holds lit; the second window's
    Case("AES_ROM_ACT_ALLCHG", SELECTED), Case("AES_ROM_ACT_ALLCHG", OPEN_A), Case("AES_ROM_ACT_ALLCHG", RUBBER, 1, arm=lambda a: a[7] == 1),
    Case("AES_ROM_ACT_ALLCHG", TWO_WINDOWS, 2),
    Case("AES_ROM_ACT_ALLCHG", RUBBER, 1, why="not drawn (every caller of the chains asks it drawn)", arguments=_with(8, 0)),
    Case("AES_ROM_ACT_ALLCHG", RUBBER, 1, why="a clip smaller than what changed: the redraw held to the clip",
         arguments=_with(5, da.BAND_AT), laid=("a 10 by 10 clip at the box's corner", _rect_laid(_a_corner_of_the_box))),
    Case("AES_ROM_ACT_ALLCHG", RUBBER, 1, why="a thin rectangle down into drive A:'s label, right of its image: it is lit",
         arguments=_with(4, da.BAND_AT), laid=("the thin rectangle", _rect_laid(_down_the_label_right_of_the_image))),
    Case("AES_ROM_ACT_ALLCHG", SELECTED, why="the excepted icon selected: left as it is", arguments=lambda a: a.arguments,
         laid=("the excepted icon SELECTED", _except_selected)),
)
BY_LABEL = da.by_label(CASES)
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]
A_CLASS = [name for name, each in BY_LABEL.items() if each.why]
SIGNATURES = da.SIGNATURES


def _answers(name):
    return SIGNATURES[name][0] is not None


@EVERY_CASE
def test_a_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine from the same entry — a plain differential, or the row through
    the host's scheduler held to the ROM's scheduled run (the idles, the image at every dispatch, the answer). At its
    own arrival, a routine that returns without idling leaves its caller the answer the ROM's run in place does."""
    each = BY_LABEL[name]
    arrived = da.arrival_of(each)
    if each.name not in da.YIELDING:
        answer = da.plain(arrived, *da.layers_of(each), **dict(each.steered or ())).long_answer()
    else:
        row = da.row_of(arrived, name.split(" — ", 1)[1], answered=_answers(each.name), layers=da.layers_of(each),
                        **WAKES.get(each.wake, {}))
        ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
        assert bool(the_rom_s.idles) == bool(each.wake), f"{name}: the ROM's run idles {the_rom_s.idles} time(s)"
        # (an arm that reaches no binding — nothing changed, nothing drawn — never enters the dispatcher, on either shore)
        assert ran.entered == the_rom_s.entered and (not ran.entered or ran.entered[-1] == aes.SHELL_PD), (
            f"{name}: the processes entered {ran.entered}, the ROM's run's {the_rom_s.entered}")
        answer = the_rom_s.d0
        if ran.answer is not None:
            assert ran.answer & aes.WORD_MASK == the_rom_s.d0 & aes.WORD_MASK
    if each.why or each.wake or not _answers(each.name):
        return
    back = da.returned_in_place(arrived)
    assert da.answered_at_its_width(each.name, answer) == da.answered_at_its_width(each.name, back.registers["d0"])


ARRIVALS, CLASSES = 42, 27


def test_every_routine_has_a_case_at_an_arrival_of_its_own():
    assert {BY_LABEL[name].name for name in AT_ITS_OWN_ARRIVAL} == set(da.UNIT_B)
    assert (len(AT_ITS_OWN_ARRIVAL), len(A_CLASS)) == (ARRIVALS, CLASSES)


def test_the_arrivals_are_the_arms_their_names_say():
    """WHAT AN `arm` OF THE ARGUMENTS ALONE CANNOT SAY, read off the ROM's own runs in place: the corner's click is
    act_chkobj's MISS (the root answered), drive A:'s click its hit; app_afind's two file arrivals answer a node's data
    (isapp 0) and an application (isapp 1)."""
    def in_place(name, chain, nth=0):
        arrived = da.arrival(name, chain, nth)
        return arrived, da.returned_in_place(arrived)
    missed, back = in_place("AES_ROM_ACT_CHKOBJ", CORNER)
    assert back.registers["d0"] & aes.WORD_MASK == DESK_ROOT == missed.arguments[1]
    hit, back = in_place("AES_ROM_ACT_CHKOBJ", SELECTED)
    assert back.registers["d0"] & aes.WORD_MASK == hit.arguments[2]
    for nth, isapp in ((1, 0), (4, 1)):
        found, back = in_place("AES_ROM_APP_AFIND", OPEN_A if nth == 1 else FILES_OPENED, nth)
        assert case.word_in(back.ram, found.arguments[4] & BUS) == isapp and back.registers["d0"]


# ---- D0 AT RETURN -----------------------------------------------------------------------------------------------------------------
VOID = [name for name, (restype, _frame) in SIGNATURES.items() if restype is None]


ANSWER_READ_BY_NONE = ("AES_ROM_ACT_CHG",)        # its 0 / 1: each of its six callers drops it


def test_no_caller_in_the_rom_reads_what_a_void_routine_leaves_in_d0():
    """BY READING THE CALLERS (`aes_deskbind.answer_readers`): the D0 the ROM's void routines leave is read nowhere;
    every answering routine's answer is read — but act_chg's, which no caller reads either (held all the same)."""
    unread = (*VOID, *ANSWER_READ_BY_NONE)
    assert {name: db.answer_readers(da.entry_of(name)) for name in unread} == {name: set() for name in unread}
    assert all(db.answer_readers(da.entry_of(name)) for name in da.UNIT_B if name not in unread)


NO_WORD_IN_C = 23


def test_the_cases_whose_d0_the_c_does_not_have_are_counted():
    assert Counter(BY_LABEL[name].name in VOID for name in BY_LABEL)[True] == NO_WORD_IN_C


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------------
def test_no_function_of_a_blob_outside_the_unit_refers_to_one_of_its_routines(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every core of the unit
    linked; and no function outside the unbound desk (the held cores and what only they reach) refers to ANY held core (unit L's
    win_icalc calls app_afind: an importer of wave 1b, itself unbound)."""
    assert not db.bound_referrers(blob, da.UNIT_B)


def test_the_table_s_entries_for_the_unit_stay_the_rom_s_and_no_registry_names_one():
    verdicts, linef_table = da.table_verdicts(da.UNIT_B)
    assert verdicts == {name: linef_table.THE_ROM_S for name in da.UNIT_B}
    assert set(da.UNIT_B) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    assert not da.registered(da.UNIT_B)


def test_the_new_chains_of_the_group_reach_what_they_were_made_for():
    """THE GROUP'S CHAINS (`aes_desk`'s block): a drive put down on a bare spot reaches move_drvicon — no chain did
    before —; the corner's click, act_chkobj; each sort, pn_fcomp. Held to each chain's own profile."""
    assert aes_desk.MOVE_DRVICON in aes_desk.entered("drive A: dragged to a bare spot of the desktop")
    assert aes_desk.CHECK_AN_ICON_S_HIT in aes_desk.entered(CORNER)
    for key in ("Size", "Date", "Type"):
        assert aes_desk.SORT_BY_THE_KEY in aes_desk.entered(f"files: View > Sort by {key}")
