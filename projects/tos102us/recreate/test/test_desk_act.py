"""THE DESK'S HIT TESTS AND ICON DRAGS (`src/desk/deskact.c`; band 6 wave 1b, group G3, unit B), HELD AT TIER 1 AT
THE ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2 (stage 2), SEVEN OF THEM FLIPPED, the five whose C called a core
then held (gr_isdown: unit D's evnt_multi; gr_bwait: gr_isdown; act_chg, act_allchg, move_drvicon: unit I's do_wredraw)
SINCE SLICE F2c: the Line-F table's entry for each is its thunk, and every case of theirs at an arrival is a Tier 3 row
(`ROWS`, below).

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
import aes_deskarrive as dar
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
    # UNPINNED BY NAME (F2 stage 2's review, MG5 survived): the text line's LAST CELL — its width is 45 cells, and no
    # case's point or rectangle lies in the 45th alone, so a width of 44 answers alike. No chain reaches it: every
    # hand's click on a text line is the line's middle (`aes_desk.text_line_point`), the rubber boxes are the desktop's.
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


# ---- FLIPPED (band 6 slice F2, stage 2) — AND THE FIVE HELD, UNBOUND -------------------------------------------------------------
def test_the_unit_s_seven_are_flipped_and_its_five_held_unbound(blob):
    """THE FLIP PIN of the seven (`aes_deskarrive.flipped`: each core called by its own thunk, its entry OURS THROUGH
    THAT THUNK) and THE UNBOUND PIN of the five held (`aes_deskarrive.unbound`: their entries the ROM's, no registry row,
    and no function outside the unbound desk refers to any held core)."""
    dar.flipped(blob, da.UNIT_B_FLIPPED)
    dar.unbound(blob, da.UNIT_B_HELD_AT_F2)


# ---- band 6 slice F2: THE UNIT'S ROWS — every case at an arrival of a flipped routine registered
# (`aes_deskact.register_row`): a plain row (app_afind, gr_accobs, gr_extent, gr_obalign, act_chkobj), or A ROW THAT
# SWITCHES (gr_obfind: the objc_find binding's yield; gr_plns: graf_mouse's) — WITH NO DOOR (measured: no run of either
# makes a call of the event layer's door), held here three ways (premise, whole run on both blobs, price). The classes
# stay Tier 1's.
#   * SINCE SLICE F2c, the five flipped there: gr_isdown's and gr_bwait's rows DOOR USERS' (MEASURED, the table's second
#     count: one call of a rebound entry each — the evnt_multi binding's wait, ended by the case's wake), pinned in
#     `DOOR_USERS_*` and read by `test_tier3.py`; move_drvicon's, act_chg's and act_allchg's (the objc_draw binding's
#     yield under do_wredraw) rows that switch with no door — but act_allchg's three arrivals whose ROM run through its
#     dispatcher enters no process (`REACHES_NO_BINDING`, MEASURED and pinned below: nothing changed, nothing drawn —
#     no binding reached), plain rows.
#   * THE X FLAG (`aes_switching.THE_X_FLAG_ALONE`), MEASURED (each row's blob differential at `$8995`, `$00` ours / `$10`
#     the ROM's): declared on gr_obfind's rows whose objc_find finds an object (the binding's yield after the C's own
#     compare) — not on the rubber box's, whose point is on no icon, nor on gr_plns's.
X_FLAG_DIFFERS = frozenset(name for name, each in BY_LABEL.items()
                           if each.name == "AES_ROM_GR_OBFIND" and not each.why and each.chain != RUBBER)
DOOR_USERS = frozenset(name for name, each in BY_LABEL.items()
                       if each.name in ("AES_ROM_GR_ISDOWN", "AES_ROM_GR_BWAIT") and not each.why)
REACHES_NO_BINDING = frozenset(name for name, each in BY_LABEL.items() if each.name == "AES_ROM_ACT_ALLCHG" and not each.why
                               and each.chain in (SELECTED, OPEN_A, TWO_WINDOWS))
ROWS = {name: da.register_row(each, answered=_answers(each.name), door_user=name in DOOR_USERS, x_flag_differs=name in X_FLAG_DIFFERS,
                              reaches_no_binding=name in REACHES_NO_BINDING, **WAKES.get(each.wake, {}))
        for name, each in da.at_arrivals(BY_LABEL, da.UNIT_B_FLIPPED).items()}

# ---- THE ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by each
# blob's second differential (`aes_switching.measured_on`), from the rows as registered (a recorded run, never by hand).
NO_DOOR_PREMISES = {
    'aes_gr_obfind, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e,), 8, ()),
    'aes_gr_obfind, arrival 0 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_gr_obfind, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e,), 8, ()),
    "aes_gr_obfind, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_gr_obfind, arrival 0 of file: selected':
        ((), 0, 0xae5e, (0xae5e,), 9, ()),
    'aes_gr_obfind, arrival 3 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e,), 6, ()),
    'aes_gr_plns, arrival 0 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_gr_plns, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_gr_plns, arrival 1 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_move_drvicon, arrival 0 of drive A: dragged to a bare spot of the desktop':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_act_chg, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    'aes_act_chg, arrival 0 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    'aes_act_chg, arrival 1 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    'aes_act_chg, arrival 2 of drive A: dragged to the trash, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    'aes_act_chg, arrival 0 of file: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    'aes_act_allchg, arrival 1 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED = {
    'aes_gr_obfind, arrival 0 of A: opened':
        ((9822, 16074), None, None, (0, 0, 0)),
    'aes_gr_obfind, arrival 0 of a rubber box on the desktop, round the trash':
        ((10132, 17958), None, None, (0, 0, 0)),
    'aes_gr_obfind, arrival 0 of drive A: selected':
        ((9822, 16074), None, None, (0, 0, 0)),
    "aes_gr_obfind, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        ((9824, 16048), None, None, (0, 0, 0)),
    'aes_gr_obfind, arrival 0 of file: selected':
        ((9442, 15478), None, None, (0, 0, 0)),
    'aes_gr_obfind, arrival 3 of drive A: dragged to the trash, Return':
        ((12104, 20572), None, None, (0, 0, 0)),
    'aes_gr_plns, arrival 0 of drive A: dragged to the trash, Return':
        ((18810, 24322), None, None, (0, 0, 0)),
    'aes_gr_plns, arrival 0 of file: dragged to the trash, OK':
        ((18802, 24314), None, None, (0, 0, 0)),
    'aes_gr_plns, arrival 1 of drive A: dragged to the trash, Return':
        ((18810, 24322), None, None, (0, 0, 0)),
    'aes_move_drvicon, arrival 0 of drive A: dragged to a bare spot of the desktop':
        ((107734, 146002), None, None, (0, 0, 0)),
    'aes_act_chg, arrival 0 of drive A: selected':
        ((67246, 88650), None, None, (0, 0, 0)),
    'aes_act_chg, arrival 0 of A: File > Open':
        ((67980, 89288), None, None, (0, 0, 0)),
    'aes_act_chg, arrival 1 of drive A: dragged to the trash, Return':
        ((66564, 87970), None, None, (0, 0, 0)),
    'aes_act_chg, arrival 2 of drive A: dragged to the trash, Return':
        ((66422, 87690), None, None, (0, 0, 0)),
    'aes_act_chg, arrival 0 of file: selected':
        ((61974, 82268), None, None, (0, 0, 0)),
    'aes_act_allchg, arrival 1 of a rubber box on the desktop, round the trash':
        ((65398, 85534), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    'aes_gr_obfind, arrival 0 of A: opened':
        {"bench": (22836, 17344), "bench_shipped": (22836, 17412)},
    'aes_gr_obfind, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (24720, 18010), "bench_shipped": (24720, 17602)},
    'aes_gr_obfind, arrival 0 of drive A: selected':
        {"bench": (22836, 17344), "bench_shipped": (22836, 17412)},
    "aes_gr_obfind, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        {"bench": (22810, 17346), "bench_shipped": (22810, 17414)},
    'aes_gr_obfind, arrival 0 of file: selected':
        {"bench": (22240, 16964), "bench_shipped": (22240, 17032)},
    'aes_gr_obfind, arrival 3 of drive A: dragged to the trash, Return':
        {"bench": (27334, 20106), "bench_shipped": (27334, 19910)},
    'aes_gr_plns, arrival 0 of drive A: dragged to the trash, Return':
        {"bench": (115872, 112400), "bench_shipped": (115872, 112464)},
    'aes_gr_plns, arrival 0 of file: dragged to the trash, OK':
        {"bench": (116182, 112710), "bench_shipped": (116182, 112774)},
    'aes_gr_plns, arrival 1 of drive A: dragged to the trash, Return':
        {"bench": (115872, 112400), "bench_shipped": (115872, 112464)},
    'aes_move_drvicon, arrival 0 of drive A: dragged to a bare spot of the desktop':
        {"bench": (606804, 577378), "bench_shipped": (606804, 578152)},
    'aes_act_chg, arrival 0 of drive A: selected':
        {"bench": (449374, 434140), "bench_shipped": (449374, 433958)},
    'aes_act_chg, arrival 0 of A: File > Open':
        {"bench": (448340, 433234), "bench_shipped": (448340, 433072)},
    'aes_act_chg, arrival 1 of drive A: dragged to the trash, Return':
        {"bench": (378428, 363130), "bench_shipped": (378428, 363010)},
    'aes_act_chg, arrival 2 of drive A: dragged to the trash, Return':
        {"bench": (374568, 359390), "bench_shipped": (374568, 359248)},
    'aes_act_chg, arrival 0 of file: selected':
        {"bench": (432068, 417682), "bench_shipped": (432068, 417282)},
    'aes_act_allchg, arrival 1 of a rubber box on the desktop, round the trash':
        {"bench": (354688, 340684), "bench_shipped": (354688, 340836)},
}
DOOR_USERS_PRICED = {
    'aes_gr_isdown, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        ((24990, 37030), (5062, 6776), 1, (0, 0, 0)),
    'aes_gr_isdown, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        ((28634, 40944), (5062, 6768), 1, (0, 0, 0)),
    'aes_gr_bwait, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        ((63422, 86944), (43494, 56690), 1, (0, 0, 0)),
    'aes_gr_bwait, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        ((67066, 90858), (43494, 56682), 1, (0, 0, 0)),
    'aes_gr_bwait, arrival 0 of file: dragged to the trash, OK; the button let go at the first idle':
        ((63406, 86928), (43478, 56674), 1, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN = {
    'aes_gr_isdown, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        {"bench": (64078, 54408), "bench_shipped": (64078, 53450)},
    'aes_gr_isdown, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        {"bench": (74046, 64256), "bench_shipped": (74046, 63424)},
    'aes_gr_bwait, arrival 0 of drive A: dragged to the trash, Return; the button let go at the first idle':
        {"bench": (297092, 280014), "bench_shipped": (297092, 279190)},
    'aes_gr_bwait, arrival 0 of drive A: dragged to the trash, Return; the mouse carried off at the first idle':
        {"bench": (306570, 289372), "bench_shipped": (306570, 288674)},
    'aes_gr_bwait, arrival 0 of file: dragged to the trash, OK; the button let go at the first idle':
        {"bench": (297712, 280634), "bench_shipped": (297712, 279810)},
}
ROWS_MADE, SWITCHING = 42, 16           # (slice F2c: +15 rows, 7 of them switching with no door, 5 door users', 3 plain)


def _registered_row(name):
    return aes_event.SWITCHING_ROWS[name].row


def test_every_flipped_routine_has_a_row_at_an_arrival_and_every_row_that_switches_is_pinned():
    import aes_switching
    entries = {da.entry_of(row.name) if hasattr(row, "door") else row[1] for row in ROWS.values()}      # (a plain row is a tuple)
    assert entries == {da.entry_of(name) for name in da.UNIT_B_FLIPPED} and len(ROWS) == ROWS_MADE
    switching = {aes_switching.row_name(row) for row in ROWS.values() if hasattr(row, "door") and not row.door}
    door_users = {aes_switching.row_name(row) for row in ROWS.values() if getattr(row, "door", None)}
    assert door_users == set(DOOR_USERS_PRICED) == set(DOOR_USERS_WHOLE_RUN) and {
        name for name, row in ROWS.items() if getattr(row, "door", None)} == DOOR_USERS
    assert set(NO_DOOR_PREMISES) == set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN) == switching and len(switching) == SWITCHING
    assert {name for name, row in ROWS.items() if getattr(row, "x_flag_differs", False)} == X_FLAG_DIFFERS and len(X_FLAG_DIFFERS) == 5


@pytest.mark.parametrize("name", sorted(REACHES_NO_BINDING))
def test_an_arrival_of_a_yielding_routine_that_reaches_no_binding_is_a_plain_row(name):
    """`REACHES_NO_BINDING`, MEASURED: the ROM's own run of the case through its dispatcher enters NO process (no binding
    reached — nothing changed, nothing drawn), so its row is the plain differential; the act_allchg arrivals that do
    reach one enter the desk."""
    each = BY_LABEL[name]
    assert not da.the_rom_s_run(da.row_of(da.arrival_of(each), da.row_label(each), answered=_answers(each.name))).entered
    assert not hasattr(ROWS[name], "door")


def test_the_act_allchg_arrival_that_reaches_a_binding_enters_the_desk():
    """...the converse, on the one act_allchg arrival outside `REACHES_NO_BINDING`: its ROM run enters the desk."""
    (name,) = [name for name, each in BY_LABEL.items() if each.name == "AES_ROM_ACT_ALLCHG" and not each.why
               and name not in REACHES_NO_BINDING]
    each = BY_LABEL[name]
    assert da.the_rom_s_run(da.row_of(da.arrival_of(each), da.row_label(each), answered=_answers(each.name))).entered
    assert hasattr(ROWS[name], "door")


# THE ROUTINES G3'S FLIP LEAVES ENTERED BY NO WALKED CHAIN (`test_aes_desk_ours.NOT_ENTERED_ON_OUR_SHORE`, group G3's block):
# every Line-F call word of each in the ROM's GEM text lies in a routine G3 flipped — so on our shore only our C calls it.
CALLED_BY_G3_ALONE = {"AES_ROM_FN_INIT": {"AES_ROM_FPD_START"}, "AES_ROM_PN_INIT": {"AES_ROM_FPD_START"},
                      "AES_ROM_FPD_BLDSPEC": {"AES_ROM_PN_OPEN"}, "AES_ROM_PN_ALLOC": {"AES_ROM_PN_OPEN"},
                      "AES_ROM_FPD_ELIST": {"AES_ROM_FL_FREE"}, "AES_ROM_PN_COMP": {"AES_ROM_PN_SORT"},
                      "AES_ROM_PN_FCOMP": {"AES_ROM_PN_COMP"}, "AES_ROM_DESK_OBJC_FIND": {"AES_ROM_GR_OBFIND"},
                      "AES_ROM_GSX_PLINE": {"AES_ROM_GR_PLNS"}}


def test_the_routines_g3_s_flip_leaves_entered_by_no_chain_are_called_by_g3_s_flipped_routines_alone():
    import test_aes_desk_ours
    held = dar._linef_table().LINKED_AND_NOT_FLIPPED
    for name, callers in CALLED_BY_G3_ALONE.items():
        assert dar.rom_callers(name) == {da.entry_of(caller) for caller in callers}, name
        assert not callers & set(held), name
    assert set(CALLED_BY_G3_ALONE) <= set(test_aes_desk_ours.NOT_ENTERED_ON_OUR_SHORE)


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


def test_the_new_chains_of_the_group_reach_what_they_were_made_for():
    """THE GROUP'S CHAINS (`aes_desk`'s block): a drive put down on a bare spot reaches move_drvicon — no chain did
    before —; the corner's click, act_chkobj; each sort, pn_fcomp. Held to each chain's own profile."""
    assert aes_desk.MOVE_DRVICON in aes_desk.entered("drive A: dragged to a bare spot of the desktop")
    assert aes_desk.CHECK_AN_ICON_S_HIT in aes_desk.entered(CORNER)
    for key in ("Size", "Date", "Type"):
        assert aes_desk.SORT_BY_THE_KEY in aes_desk.entered(f"files: View > Sort by {key}")


# ==== BAND 6 WAVE 2, GROUP G4: THE DRAG'S LOOP AND THE BUTTON'S TWO HANDLERS (gr_drgplns, act_bsclick, act_bdown) ====
# Every one of the three reaches a binding of unit D's that yields: each case is A ROW THAT SWITCHES at a chain's
# arrival. THE DRAGS WAIT (gr_bwait's evnt_multi, every turn of the loop): their rows are taken through A HAND'S WAKE
# at the drag's idles — where the mouse is carried and when the button is let go, each point read off the arrival's
# own machine (`aes_desk`'s points) and said in the case's id. The rubber box's poll never idles: its row is woken at
# its door calls, unit D's GRAF_RUBBOX wakes.
from pathlib import Path                                                            # noqa: E402

import aes_boot                                                                     # noqa: E402
import layouts                                                                      # noqa: E402
import vdi                                                                          # noqa: E402

DRGPLNS, BSCLICK, BDOWN = "AES_ROM_GR_DRGPLNS", "AES_ROM_ACT_BSCLICK", "AES_ROM_ACT_BDOWN"
RUBBER_B = "a rubber box on the desktop, round drive B: and the trash"
FILE_ON_FOLDER = "files: the long file dragged onto the folder, Return"
FILE_TRASHED_RETURN = "file: dragged to the trash, Return (Cancel, the dialog's default)"
DOUBLE_CLICKED = "file: double-clicked (the alert)"
THE_TRASH, THE_FOLDER, THE_PROGRAM = "TRASH", "AUTO", "TESTPRG.PRG"


def _point(of):
    """`arrival -> (x, y)`: a point read off the arrival's own machine."""
    return lambda arrived: of(aes_boot.Machine(arrived.boot))


TRASH = _point(lambda machine: aes_desk.icon_point(machine, THE_TRASH))
DRIVE_B = _point(lambda machine: aes_desk.drive_point(machine, "B"))
FOLDER = _point(lambda machine: aes_desk.icon_point(machine, THE_FOLDER))
PROGRAM = _point(lambda machine: aes_desk.icon_point(machine, THE_PROGRAM))
BARE = _point(lambda _machine: aes_desk.BARE_DESKTOP)
MENU_BAR_Y = 4                          # a row inside the menu bar (above the desktop's work area)
OVER_THE_MENU_BAR = _point(lambda _machine: (aes_desk.BARE_DESKTOP[0], MENU_BAR_Y))
TITLE_BAR_INSET = 4                     # a row of the top window's title bar: its border, outside its work area's tree


def _on_the_title_bar(machine):
    x, y, width, _height = aes_desk.top_window(machine)
    return x + width // 2, y + TITLE_BAR_INSET


ON_THE_TITLE_BAR = _point(_on_the_title_bar)


def _carried(*points):
    """A HAND'S WAKE: the mouse carried to each point at the drag's successive idles, then the button let go."""
    def wake(arrived):
        idles = {nth: aes_event.move_to(*point(arrived)) for nth, point in enumerate(points)}
        return dict(at_idle={**idles, len(points): aes_event.release})
    return wake


LET_GO_WHERE_PRESSED = "the button let go where it was pressed"
WAKES_WAVE_2 = {
    LET_GO_WHERE_PRESSED: _carried(),
    "carried to the trash, let go": _carried(TRASH),
    "carried to the trash, then to drive B:, let go": _carried(TRASH, DRIVE_B),
    "carried to the trash, then to a bare spot, let go": _carried(TRASH, BARE),
    "carried to a bare spot, let go": _carried(BARE),
    "carried over the menu bar, let go": _carried(OVER_THE_MENU_BAR),
    "carried onto the window's title bar, let go": _carried(ON_THE_TITLE_BAR),
    "carried to the trash, a bare spot, the trash again, let go": _carried(TRASH, BARE, TRASH),
    "carried to the trash, then a pixel on inside it, let go": _carried(TRASH, _point(
        lambda machine: tuple(at + 1 for at in aes_desk.icon_point(machine, THE_TRASH)))),
    "carried to the folder, let go": _carried(FOLDER),
    "carried to the program (a file: no drop), let go": _carried(PROGRAM),
    "the box let go at its first door call": lambda _arrived: dict(at_calls={0: aes_event.release}),
    "the box grown at its first door call, let go at its third": lambda _arrived: dict(
        at_calls={0: aes_event.move_to(*AWAY), 2: aes_event.release}),
}
SHIFT, LEFT_SHIFT, A_HIGH_KEY_BIT = 0x0001, 0x0002, 0x0100
# Unit B's header's constants (`include/desk/deskact.h`), read as unit A's are (`aes_deskapp.CONSTANTS`).
ACT_HEADER = Path(__file__).resolve().parents[1] / "include" / "desk" / "deskact.h"
ACT_CONSTANTS = layouts.parse_constants((ACT_HEADER.parent / "deskglobals.h", ACT_HEADER), known={**vdi.CONSTANTS, **aes.CONSTANTS})


def _keys(value):
    return lambda arrived: (*arrived.arguments[:5], value, *arrived.arguments[6:])


def _double_click(arrived):
    return (*arrived.arguments[:7], 1)


def _object_unselected(arrived):
    """LAID: the icon the press is on (found by the ROM's own run) NOT SELECTED — every chain's press finds it selected
    (the button handler's click selected it first)."""
    tree, obj = arrived.arguments[1] & BUS, _pressed_object(arrived)
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(arrived.boot.ram, state) & ~(1 << aes.OB_STATE_SELECTED_BIT) & 0xFFFF)}


def _pressed_object(arrived):
    """The icon under act_bdown's press: the selected child of its root under the point (the chains press on one)."""
    tree, root, mx, my = arrived.arguments[1] & BUS, arrived.arguments[2], arrived.arguments[3], arrived.arguments[4]
    ram = arrived.boot.ram
    word = lambda index, at: aes.signed(case.word_in(ram, tree + index * aes.OB_BYTES + at))     # noqa: E731
    child = word(root, aes.OB_HEAD)
    while child > root:
        x, y = word(root, aes.OB_X) + word(child, aes.OB_X), word(root, aes.OB_Y) + word(child, aes.OB_Y)
        if x <= mx < x + word(child, aes.OB_WIDTH) and y <= my < y + word(child, aes.OB_HEIGHT):
            return child
        child = word(child, aes.OB_NEXT)
    raise AssertionError("no child of the root under the press")


def _another_selected(arrived):
    """LAID: another child of the root than the one under the point SELECTED too (no chain selects two that way)."""
    tree, root, obj = arrived.arguments[1] & BUS, arrived.arguments[2], _pressed_object(arrived)
    ram = arrived.boot.ram
    child = aes.signed(case.word_in(ram, tree + root * aes.OB_BYTES + aes.OB_HEAD))
    while child == obj:
        child = aes.signed(case.word_in(ram, tree + child * aes.OB_BYTES + aes.OB_NEXT))
    state = tree + child * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(ram, state) | 1 << aes.OB_STATE_SELECTED_BIT)}


def _both_selected(arrived):
    """LAID: the icon under the click SELECTED, and another child of the root."""
    tree, obj = arrived.arguments[1] & BUS, _pressed_object(arrived)
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {**_another_selected(arrived),
            state: struct.pack(">H", case.word_in(arrived.boot.ram, state) | 1 << aes.OB_STATE_SELECTED_BIT)}


def _object_disabled(arrived):
    """LAID: the icon under the click DISABLED (no icon of the desk's ever is)."""
    tree, obj = arrived.arguments[1] & BUS, _pressed_object(arrived)
    state = tree + obj * aes.OB_BYTES + aes.OB_STATE
    return {state: struct.pack(">H", case.word_in(arrived.boot.ram, state) | 1 << aes.OB_STATE_DISABLED_BIT)}


def _at(point):
    return lambda arrived: (*arrived.arguments[:3], *point(arrived), *arrived.arguments[5:])


Wave2 = Case
CASES_WAVE_2 = (
    # act_bsclick: an icon selected (the others put out); double-clicked; one selected already (nothing put out);
    # a click on no icon (the root: everything put out) — at the corner of drive A:'s object, and where a box begins
    Wave2(BSCLICK, SELECTED), Wave2(BSCLICK, OPENED, arm=lambda a: a[7] == 1), Wave2(BSCLICK, FILE_TRASHED),
    Wave2(BSCLICK, CORNER), Wave2(BSCLICK, RUBBER), Wave2(BSCLICK, FILE_SELECTED), Wave2(BSCLICK, DOUBLE_CLICKED),
    Wave2(BSCLICK, SELECTED, why="Shift held (the right one): the unselected icon toggled on, nothing else put out",
          arguments=_keys(SHIFT)),
    Wave2(BSCLICK, FILE_TRASHED, why="Shift held (the left one): the selected icon toggled off", arguments=_keys(LEFT_SHIFT)),
    Wave2(BSCLICK, FILE_TRASHED, why="Shift held (the right one alone, $0001): the selected icon toggled off", arguments=_keys(SHIFT)),
    Wave2(BSCLICK, FILE_TRASHED, why="a keys word whose low two bits are clear ($0100): no Shift — a BYTE's bits",
          arguments=_keys(A_HIGH_KEY_BIT)),
    Wave2(BSCLICK, SELECTED, why="drive A: double-clicked SELECTED already, another icon selected too: the others put out",
          arguments=_double_click, laid=("drive A: and another icon SELECTED", _both_selected)),
    Wave2(BSCLICK, SELECTED, why="a click on the trash (its x far from its y): it selected, drive A: put out",
          arguments=_at(TRASH)),
    Wave2(BSCLICK, SELECTED, why="the clicked icon DISABLED: act_chg refuses it (the check asked)",
          arguments=lambda a: a.arguments, laid=("the icon DISABLED", _object_disabled)),
    Wave2(BSCLICK, SELECTED, why="a point outside the tree's root: objc_find's NIL, every icon put out", arguments=_with(3, 0xFFFF)),
    # act_bdown: the selection dragged and let go — on the trash, where it began, on a bare spot (put down there:
    # move_drvicon), from a window onto the desktop, back onto itself, onto a folder in its own window; a rubber box
    Wave2(BDOWN, DRAGGED, wake="carried to the trash, let go"), Wave2(BDOWN, DRAGGED, wake=LET_GO_WHERE_PRESSED),
    Wave2(BDOWN, PUT_DOWN, wake="carried to a bare spot, let go"), Wave2(BDOWN, FILE_TRASHED, wake="carried to the trash, let go"),
    Wave2(BDOWN, FILE_TRASHED, wake=LET_GO_WHERE_PRESSED), Wave2(BDOWN, FILE_ON_FOLDER, wake="carried to the folder, let go"),
    Wave2(BDOWN, FILE_TRASHED, wake="carried to a bare spot, let go"),
    Wave2(BDOWN, RUBBER, wake="the box let go at its first door call"),
    Wave2(BDOWN, RUBBER_B, wake="the box grown at its first door call, let go at its third"),
    Wave2(BDOWN, DRAGGED, wake="carried to a bare spot, let go", why="two icons selected: both dragged, both put down",
          arguments=lambda a: a.arguments, laid=("another icon SELECTED", _another_selected)),
    Wave2(BDOWN, DRAGGED, wake=LET_GO_WHERE_PRESSED, why="the pressed icon not selected: no drag, the button awaited",
          arguments=lambda a: a.arguments, laid=("the pressed icon UNSELECTED", _object_unselected)),
    # (the fix pass's) a window in the TEXT view, pressed on the file's line: the line's outline dragged; the desktop
    # of the machine booted as text (the windows' view word TEXT): still icons
    Wave2(BDOWN, aes_desk.TEXT_LINE_DRAGGED, wake="carried to the trash, let go"),
    Wave2(BDOWN, aes_desk.TEXT_PUT_DOWN, wake="carried to a bare spot, let go"),
    # gr_drgplns: let go where pressed; the trash lit, then put out (let go there); lit, then another lit in its
    # place; lit, then put out over the bare desktop; from a window to the trash; onto a folder in a window; over a
    # file, which takes no drop
    Wave2(DRGPLNS, DRAGGED, wake=LET_GO_WHERE_PRESSED), Wave2(DRGPLNS, DRAGGED, wake="carried to the trash, let go"),
    Wave2(DRGPLNS, DRAGGED, wake="carried to the trash, then to drive B:, let go"),
    Wave2(DRGPLNS, DRAGGED, wake="carried to the trash, then to a bare spot, let go"),
    Wave2(DRGPLNS, DRAGGED, wake="carried to the trash, a bare spot, the trash again, let go"),
    Wave2(DRGPLNS, DRAGGED, wake="carried to the trash, then a pixel on inside it, let go"),
    Wave2(DRGPLNS, PUT_DOWN, wake="carried to a bare spot, let go"),
    Wave2(DRGPLNS, FILE_TRASHED, wake="carried to the trash, let go"),
    Wave2(DRGPLNS, FILE_ON_FOLDER, wake="carried to the folder, let go"),
    Wave2(DRGPLNS, FILE_ON_FOLDER, wake="carried to the program (a file: no drop), let go"),
    # (the fix pass's) carried over the menu bar, and a window's file carried onto its window's title bar — Reviewer B's
    # points for objc_find's NIL. Both arrivals are kept; the NIL-as-an-icon mutant (D11) SURVIVES them: taken as an icon,
    # NIL reads object -1's state and i_find's NULL ANODE's type (low memory), which answer "no drop" on every machine
    # of ours — the two arms leave one machine (a reading, STATUS's sweep)
    Wave2(DRGPLNS, DRAGGED, wake="carried over the menu bar, let go"),
    Wave2(DRGPLNS, FILE_TRASHED, wake="carried onto the window's title bar, let go"),
)
BY_LABEL_WAVE_2 = da.by_label(CASES_WAVE_2)
SIGNATURES_WAVE_2 = da.SIGNATURES_WAVE_2


def wave_2_row(name):
    each = BY_LABEL_WAVE_2[name]
    arrived = da.arrival_of(each)
    wake = WAKES_WAVE_2[each.wake](arrived) if each.wake else {}
    return each, da.row_of(arrived, name.split(" — ", 1)[1], answered=SIGNATURES_WAVE_2[each.name][0] is not None,
                           layers=da.layers_of(each), **wake)


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the row through the host's scheduler held to the ROM's scheduled run — the idles, the image at every
    dispatch, act_bdown's answer (the window the drag was let go over) the ROM's D0. A drag's row idles at every turn of
    its loop; a click's never."""
    each, row = wave_2_row(name)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert bool(the_rom_s.idles) == (each.name != BSCLICK and each.wake is not None and "door call" not in each.wake), (
        f"{name}: the ROM's run idles {the_rom_s.idles} time(s)")
    assert ran.entered == the_rom_s.entered and ran.entered[-1] == aes.SHELL_PD
    if ran.answer is not None:
        assert ran.answer & aes.WORD_MASK == the_rom_s.d0 & aes.WORD_MASK


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 30, 10


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    own = [each for each in CASES_WAVE_2 if not each.why]
    assert {each.name for each in own} == set(da.UNIT_B_WAVE_2)
    assert (len(own), len(CASES_WAVE_2) - len(own)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)


def test_act_bsclick_s_arrivals_take_its_four_arms():
    """WHICH ARM EACH ARRIVAL TAKES, read off the ROM's own run in place: whether it reaches act_allchg (the others put
    out) and act_chg (the icon's own state) before it returns — a miss (allchg alone), a selection (both), a click on
    a selected icon (act_chg alone); the double click's (both, again)."""
    def reaches(arrived, routine):
        try:
            stop = aes_boot.continued(arrived.boot, (), arrived.budget, da.entry_of(routine), da.entry_of(BSCLICK))
        except aes_boot.Refused:
            return False
        return da.stack_pointer(stop) < da.stack_pointer(arrived.boot)
    arms = {chain: tuple(reaches(da.arrival(BSCLICK, chain), routine) for routine in ("AES_ROM_ACT_ALLCHG", "AES_ROM_ACT_CHG"))
            for chain in (SELECTED, FILE_TRASHED, CORNER, OPENED)}
    assert arms == {SELECTED: (True, True), FILE_TRASHED: (False, True), CORNER: (True, False), OPENED: (True, True)}


def test_act_bdown_s_cases_answer_each_of_its_drops():
    """act_bdown's answer over its cases, the ROM's run's: the desktop (0) for a drop on the trash or where it began;
    nothing (-1) for an icon put down on a bare spot, a file let go on itself, a press on no selection; the window (1)
    for a file let go on a folder in its own window."""
    answers = {}
    for name, each in BY_LABEL_WAVE_2.items():
        if each.name == BDOWN and not each.why:
            answers[(each.chain, each.wake)] = da.the_rom_s_run(wave_2_row(name)[1]).d0 & aes.WORD_MASK
    nothing = ACT_BDOWN_NOTHING & aes.WORD_MASK
    assert answers[(DRAGGED, "carried to the trash, let go")] == 0
    assert answers[(PUT_DOWN, "carried to a bare spot, let go")] == nothing
    assert answers[(FILE_TRASHED, LET_GO_WHERE_PRESSED)] == nothing
    assert answers[(FILE_ON_FOLDER, "carried to the folder, let go")] == 1


ACT_BDOWN_NOTHING = ACT_CONSTANTS["ACT_BDOWN_NOTHING"]
VOID_WAVE_2 = [name for name, (restype, _frame) in SIGNATURES_WAVE_2.items() if restype is None]


def test_no_caller_reads_what_gr_drgplns_or_act_bsclick_leave_in_d0_and_act_bdown_s_word_is_read():
    """BY READING THE CALLERS (`aes_deskbind.answer_readers`): the D0 the two void routines leave is read nowhere — the
    counted divergence of their cases —; act_bdown's word is read (its caller's `move.w d0,d4`). AND THE ARGUMENT WORDS
    act_bdown's evnt_button writes in place (16/18/20(a6)) are the frame its one caller `$fe2232` pops unread
    (`addal #18,sp`, then `d4` alone): no ROM caller reads them back."""
    assert {name: db.answer_readers(da.entry_of(name)) for name in VOID_WAVE_2} == {name: set() for name in VOID_WAVE_2}
    assert db.answer_readers(da.entry_of(BDOWN))
    assert sum(1 for each in CASES_WAVE_2 if each.name in VOID_WAVE_2) == NO_WORD_IN_C_WAVE_2


NO_WORD_IN_C_WAVE_2 = 27


# ---- FLIPPED (band 6 slice F3, stage 1): the three whole ------------------------------------------------------------------
def test_the_wave_2_routines_are_flipped(blob):
    """THE FLIP PIN (`aes_deskarrive.flipped`): each core called by its own thunk of the table, each entry OURS THROUGH
    THAT THUNK, none held — and no function outside the unbound desk refers to a core still held."""
    dar.flipped(blob, da.UNIT_B_WAVE_2)


# ---- band 6 slice F3: THE THREE'S ROWS — every case at an arrival registered (`aes_deskact.register_row`), each A ROW THAT
# SWITCHES (every one reaches a binding that yields), its wait ended by the case's own wake (`WAKES_WAVE_2`: the drags'
# idles, the rubber box's door calls). The classes stay Tier 1's.
#   * DOOR USERS (`DOOR_USERS_WAVE_2`, MEASURED, the table's second count: 2 to 5 calls of a rebound entry — the drags'
#     waits, the rubber box's polls), pinned in `DOOR_USERS_*_WAVE_2` and read by `test_tier3.py`: every row of act_bdown
#     and gr_drgplns. act_bsclick's make no such call — rows that switch with no door.
#   * THE X FLAG (`aes_switching.THE_X_FLAG_ALONE`), MEASURED (each row's blob differential at `$8995`, `$00` ours / `$10`
#     the ROM's): act_bsclick's on a selected icon (act_chg alone) and on the corner (act_allchg alone), gr_drgplns's let
#     go where it was pressed and over the program (a file: no drop).
DOOR_USERS_WAVE_2 = frozenset(name for name, each in BY_LABEL_WAVE_2.items() if each.name in (BDOWN, DRGPLNS) and not each.why)
X_FLAG_DIFFERS_WAVE_2 = frozenset(name for name, each in BY_LABEL_WAVE_2.items() if not each.why and (
    (each.name == BSCLICK and each.chain in (FILE_TRASHED, CORNER))
    or (each.name == DRGPLNS and (each.chain, each.wake) in ((DRAGGED, LET_GO_WHERE_PRESSED),
                                                             (FILE_ON_FOLDER, "carried to the program (a file: no drop), let go")))))
ROWS_WAVE_2 = {name: da.register_row(each, answered=SIGNATURES_WAVE_2[each.name][0] is not None, door_user=name in DOOR_USERS_WAVE_2,
                                     x_flag_differs=name in X_FLAG_DIFFERS_WAVE_2,
                                     **(WAKES_WAVE_2[each.wake](da.arrival_of(each)) if each.wake else {}))
               for name, each in da.at_arrivals(BY_LABEL_WAVE_2, da.UNIT_B_WAVE_2).items()}

# ---- THE WAVE-2 ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by
# each blob's second differential (`aes_switching.measured_on`), from the rows as registered (a recorded run, never by hand).
DOOR_USERS_PRICED_WAVE_2 = {
    'aes_act_bdown, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, let go':
        ((333056, 465346), (286916, 395166), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of drive A: dragged to the trash, Return; the button let go where it was pressed':
        ((108926, 159502), (84914, 121860), 2, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        ((305700, 431592), (258116, 359774), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; carried to the trash, let go':
        ((371766, 525942), (327186, 457540), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; the button let go where it was pressed':
        ((108920, 160122), (84908, 122480), 2, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of files: the long file dragged onto the folder, Return; carried to the folder, let go':
        ((341806, 480664), (295752, 410584), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; carried to a bare spot, let go':
        ((197330, 286322), (151220, 216182), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of a rubber box on the desktop, round the trash; the box let go at its first door call':
        ((50736, 72554), (41354, 57870), 4, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of a rubber box on the desktop, round drive B: and the trash; the box grown at its first door call, let go at its third':
        ((136006, 183514), (118480, 158378), 5, (0, 0, 0)),
    "aes_act_bdown, arrival 0 of text view: A: opened, the file's line dragged to the trash, Return (Cancel); carried to the trash, let go":
        ((354780, 504366), (308726, 434286), 3, (0, 0, 0)),
    'aes_act_bdown, arrival 0 of text view: drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        ((305700, 431592), (258116, 359774), 3, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; the button let go where it was pressed':
        ((88592, 127040), (68664, 96786), 1, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, let go':
        ((312722, 432884), (270666, 370092), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then to drive B:, let go':
        ((536146, 736890), (473490, 643314), 3, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then to a bare spot, let go':
        ((401794, 559002), (336190, 462070), 3, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, a bare spot, the trash again, let go':
        ((627324, 866414), (538204, 735366), 4, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then a pixel on inside it, let go':
        ((317124, 438740), (270666, 370092), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        ((177434, 252856), (133934, 188426), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of file: dragged to the trash, OK; carried to the trash, let go':
        ((352044, 494468), (311548, 433454), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of files: the long file dragged onto the folder, Return; carried to the folder, let go':
        ((320584, 446288), (278614, 383596), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of files: the long file dragged onto the folder, Return; carried to the program (a file: no drop), let go':
        ((183476, 262446), (142924, 201372), 2, (0, 0, 0)),
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried over the menu bar, let go':
        ((177404, 252790), (133928, 188396), 2, (0, 0, 0)),
    "aes_gr_drgplns, arrival 0 of file: dragged to the trash, OK; carried onto the window's title bar, let go":
        ((172376, 246078), (131848, 185040), 2, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN_WAVE_2 = {
    'aes_act_bdown, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, let go':
        {"bench": (1530048, 1428084), "bench_shipped": (1530048, 1426634)},
    'aes_act_bdown, arrival 0 of drive A: dragged to the trash, Return; the button let go where it was pressed':
        {"bench": (410188, 369250), "bench_shipped": (410188, 368692)},
    'aes_act_bdown, arrival 0 of drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        {"bench": (1380316, 1281310), "bench_shipped": (1380316, 1280736)},
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; carried to the trash, let go':
        {"bench": (1627272, 1505112), "bench_shipped": (1627272, 1504816)},
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; the button let go where it was pressed':
        {"bench": (409416, 368068), "bench_shipped": (409416, 367362)},
    'aes_act_bdown, arrival 0 of files: the long file dragged onto the folder, Return; carried to the folder, let go':
        {"bench": (1482988, 1375482), "bench_shipped": (1482988, 1373866)},
    'aes_act_bdown, arrival 0 of file: dragged to the trash, OK; carried to a bare spot, let go':
        {"bench": (770300, 699760), "bench_shipped": (770300, 698088)},
    'aes_act_bdown, arrival 0 of a rubber box on the desktop, round the trash; the box let go at its first door call':
        {"bench": (202274, 185766), "bench_shipped": (202274, 185012)},
    'aes_act_bdown, arrival 0 of a rubber box on the desktop, round drive B: and the trash; the box grown at its first door call, let go at its third':
        {"bench": (806530, 773644), "bench_shipped": (806530, 772482)},
    "aes_act_bdown, arrival 0 of text view: A: opened, the file's line dragged to the trash, Return (Cancel); carried to the trash, let go":
        {"bench": (1490200, 1370038), "bench_shipped": (1490200, 1369750)},
    'aes_act_bdown, arrival 0 of text view: drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        {"bench": (1380316, 1281310), "bench_shipped": (1380316, 1280736)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; the button let go where it was pressed':
        {"bench": (364202, 333828), "bench_shipped": (364202, 333630)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, let go':
        {"bench": (1484062, 1392662), "bench_shipped": (1484062, 1391572)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then to drive B:, let go':
        {"bench": (2743448, 2592116), "bench_shipped": (2743448, 2590052)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then to a bare spot, let go':
        {"bench": (1848478, 1728458), "bench_shipped": (1848478, 1726598)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, a bare spot, the trash again, let go':
        {"bench": (2972918, 2791754), "bench_shipped": (2972918, 2789044)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried to the trash, then a pixel on inside it, let go':
        {"bench": (1499466, 1406816), "bench_shipped": (1499466, 1405890)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to a bare spot of the desktop; carried to a bare spot, let go':
        {"bench": (727254, 668314), "bench_shipped": (727254, 667324)},
    'aes_gr_drgplns, arrival 0 of file: dragged to the trash, OK; carried to the trash, let go':
        {"bench": (1582274, 1470302), "bench_shipped": (1582274, 1470366)},
    'aes_gr_drgplns, arrival 0 of files: the long file dragged onto the folder, Return; carried to the folder, let go':
        {"bench": (1435088, 1338932), "bench_shipped": (1435088, 1337808)},
    'aes_gr_drgplns, arrival 0 of files: the long file dragged onto the folder, Return; carried to the program (a file: no drop), let go':
        {"bench": (732856, 670576), "bench_shipped": (732856, 670150)},
    'aes_gr_drgplns, arrival 0 of drive A: dragged to the trash, Return; carried over the menu bar, let go':
        {"bench": (727628, 668728), "bench_shipped": (727628, 667734)},
    "aes_gr_drgplns, arrival 0 of file: dragged to the trash, OK; carried onto the window's title bar, let go":
        {"bench": (716888, 659314), "bench_shipped": (716888, 658346)},
}
NO_DOOR_PREMISES_WAVE_2 = {
    'aes_act_bsclick, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_act_bsclick, arrival 0 of A: opened':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_act_bsclick, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_act_bsclick, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_act_bsclick, arrival 0 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_act_bsclick, arrival 0 of file: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_act_bsclick, arrival 0 of file: double-clicked (the alert)':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED_WAVE_2 = {
    'aes_act_bsclick, arrival 0 of drive A: selected':
        ((84844, 115178), None, None, (0, 0, 0)),
    'aes_act_bsclick, arrival 0 of A: opened':
        ((84824, 115156), None, None, (0, 0, 0)),
    'aes_act_bsclick, arrival 0 of file: dragged to the trash, OK':
        ((10940, 17730), None, None, (0, 0, 0)),
    "aes_act_bsclick, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        ((19976, 29756), None, None, (0, 0, 0)),
    'aes_act_bsclick, arrival 0 of a rubber box on the desktop, round the trash':
        ((20284, 31666), None, None, (0, 0, 0)),
    'aes_act_bsclick, arrival 0 of file: selected':
        ((73374, 100544), None, None, (0, 0, 0)),
    'aes_act_bsclick, arrival 0 of file: double-clicked (the alert)':
        ((73354, 100522), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN_WAVE_2 = {
    'aes_act_bsclick, arrival 0 of drive A: selected':
        {"bench": (482664, 459558), "bench_shipped": (482664, 460002)},
    'aes_act_bsclick, arrival 0 of A: opened':
        {"bench": (482642, 459538), "bench_shipped": (482642, 459982)},
    'aes_act_bsclick, arrival 0 of file: dragged to the trash, OK':
        {"bench": (24492, 18488), "bench_shipped": (24492, 18622)},
    "aes_act_bsclick, arrival 0 of drive A:'s object clicked at its corner, outside its image and its label":
        {"bench": (36518, 27952), "bench_shipped": (36518, 28850)},
    'aes_act_bsclick, arrival 0 of a rubber box on the desktop, round the trash':
        {"bench": (38428, 28616), "bench_shipped": (38428, 29038)},
    'aes_act_bsclick, arrival 0 of file: selected':
        {"bench": (457106, 436594), "bench_shipped": (457106, 436272)},
    'aes_act_bsclick, arrival 0 of file: double-clicked (the alert)':
        {"bench": (457084, 436574), "bench_shipped": (457084, 436252)},
}


def test_the_wave_2_rows_are_the_cases_at_arrivals_and_every_one_that_switches_is_pinned_by_its_door():
    """EVERY CASE AT AN ARRIVAL OF A FLIPPED ROUTINE A ROW; the plain ones exactly those named; EVERY ROW THAT SWITCHES
    PINNED ONCE — a door user's in `DOOR_USERS_*_WAVE_2` (read by `test_tier3.py`), any other here; the X flag declared
    on exactly the rows named."""
    import aes_switching
    switching = {aes_switching.row_name(row): name for name, row in ROWS_WAVE_2.items() if hasattr(row, "door")}
    assert {name for name, row in ROWS_WAVE_2.items() if not hasattr(row, "door")} == set()
    door_users = {row for row, name in switching.items() if ROWS_WAVE_2[name].door}
    assert {switching[row] for row in door_users} == set(DOOR_USERS_WAVE_2)
    assert set(DOOR_USERS_PRICED_WAVE_2) == set(DOOR_USERS_WHOLE_RUN_WAVE_2) == door_users
    assert set(NO_DOOR_PREMISES_WAVE_2) == set(NO_DOOR_PRICED_WAVE_2) == set(NO_DOOR_WHOLE_RUN_WAVE_2) == set(switching) - door_users
    assert {name for name, row in ROWS_WAVE_2.items() if getattr(row, "x_flag_differs", False)} == set(X_FLAG_DIFFERS_WAVE_2)
    assert (len(ROWS_WAVE_2), len(switching), len(door_users), len(X_FLAG_DIFFERS_WAVE_2)) == (30, 30, 23, 4)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES_WAVE_2)
def test_a_wave_2_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    import aes_switching
    aes_switching.vet_the_premise(aes_event.SWITCHING_ROWS[name].row, aes_switching.Premise(*NO_DOOR_PREMISES_WAVE_2[name]))


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN_WAVE_2)
def test_a_wave_2_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    import aes_switching
    premise = aes_switching.Premise(*NO_DOOR_PREMISES_WAVE_2[name])
    aes_switching.vet_on_a_blob(blob, aes_event.SWITCHING_ROWS[name].row, premise, NO_DOOR_PRICED_WAVE_2[name][3],
                                NO_DOOR_WHOLE_RUN_WAVE_2[name])


@pytest.mark.parametrize("name", NO_DOOR_PRICED_WAVE_2)
def test_a_wave_2_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    import aes_switching
    aes_switching.vet_the_table_s_price(aes_event.SWITCHING_ROWS[name].row, aes_switching.Priced(*NO_DOOR_PRICED_WAVE_2[name]))
