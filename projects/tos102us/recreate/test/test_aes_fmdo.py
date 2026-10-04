"""THE FORM LIBRARY's half that waits on the user (`src/aes/fmdo.c`): a dialog run (fm_do), a click on one of its objects
(fm_button), the screen given back round it (fm_dial), and the bell — through the event door (`test/aes_event.py`).

    fm_button(tree, obj, clicks, &next)   flags, state = ob_fs(obj); TOUCHEXIT: done (2 clicks: obj | $8000);
            SELECTABLE and not DISABLED: RBUTTON -> the group put down, obj selected; else gr_watchbox(obj, state^1,
            state) toggles it; the form going on, ev_button(1, 1, 0) waits for the rise; SELECTED and EXIT: done;
            going on and not EDITABLE: obj = 0. *next = obj | dbl; answers whether the form goes on
    fm_do(tree, start)    fm_own(1); fq; gsx_sclip(gl_rfull); next = fm_inifld(start); until done: a new field ->
            ob_edit(INIT); ev_multi(KEYBD | BUTTON, 2 clicks of any button down); a key -> fm_keybd, else ob_edit(CHAR);
            a press -> ob_find (-1: the bell) and fm_button; done or another field -> ob_edit(END). fm_own(0); next
    fm_dial(type, little, big)   gsx_sclip(gl_rscreen); 1 growbox, 2 shrinkbox, 3 w_drawdesk(big) + w_update; D0
            the type, or the D0 its last callee leaves (`aes/fmdo.h`)
    bell()                Bconout(CON:, BEL) through `trap #13`

THE MACHINES are the scheduler's own (`aes_event.machine`): PD0 running (woken by a key), the cursor hidden or shown.
fm_do and fm_button wait in the event layer, so every input is DELIVERED as the machine takes it — keys typed through
the BIOS's own keyboard handler, the mouse moved and the button pressed or released through the VDI's mouse interrupt —
either before the call (in the ring, `aes_event.keys`) or at the entry of the wait that takes it, on both shores
(`aes_event.interrupted`; `aes_event.typed` one key per wait). The dialogs are the snapshot's: the file selector (its
two fields, OK the DEFAULT, Cancel, the TOUCHEXIT arrows and file slots), and the desk's dialogs as the desk shows
them — centred by the ROM's own ob_center first — with their radio groups. The bell's BIOS trap saves the registers
below `savptr`, so a case that rings it stages `savptr` in the stack band (`aes_event.savptr_in_the_band`).
"""
import functools
import struct

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_gsx as gsx
import aes_objdraw as od
import case
import test_aes_fmlib as fmlib
import test_aes_grwait as grwait
import test_aes_wmlib as wmlib
import vdi
from case import merge_pokes

L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
BUTTON, DO, DIAL, BELL = "AES_ROM_FM_BUTTON", "AES_ROM_FM_DO", "AES_ROM_FM_DIAL", "AES_ROM_BELL"
SIGNATURES = {
    BUTTON: (aes.WORD_ANSWER, (I, L, W, W, L)),
    DO: (aes.WORD_ANSWER, (I, L, W)),
    DIAL: (aes.WORD_ANSWER, (I, W, L, L)),
    BELL: (None, (I,)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

FM = aes.header_constants("fmdo.h")
THROUGH = gsx.THROUGH
JUST_DRAW = aes.walkers(od.JUST_DRAW)
TREES = od.trees()
SELECTOR = fmlib.SELECTOR
PATH_FIELD, NAME_FIELD = fmlib.PATH_FIELD, fmlib.NAME_FIELD
OK, CANCEL, ARROW_UP = grwait.OK, grwait.CANCEL, grwait.ARROW
FILE_SLOT = 12                          # the selector's file slot under the snapshot's mouse
SELECTED = od.STATE_BITS["SELECTED"]
DISABLED = od.STATE_BITS["DISABLED"]
SELECTABLE, DEFAULT, EXIT, EDITABLE, RBUTTON, TOUCHEXIT = (
    od.FLAG_BITS[name] for name in ("SELECTABLE", "DEFAULT", "EXIT", "EDITABLE", "RBUTTON", "TOUCHEXIT"))

# The band the battery stages in: fm_button's answer word, fm_dial's two rectangles, the GRECT ob_center answers
# when a desk dialog is centred, and the two words ob_offset answers where an object is on the screen.
BAND_OFFSET = 0x3A00                    # past test_aes_grdrag.py's band (+$3900..+$3940)
BAND_BYTES = 0x20
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/test_aes_fmdo.py: an answer, two rectangles, a centred dialog's, an object's place")
NEXT_AT = BAND_AT
CENTRED_AT = BAND_AT + aes.WORD_BYTES
PLACE_X_AT = CENTRED_AT + aes.GRECT_BYTES
PLACE_Y_AT = PLACE_X_AT + aes.WORD_BYTES
RECTS_AT = BAND_AT + 0x10              # fm_dial's two rectangles, past the place words on a long boundary
LITTLE_AT, BIG_AT = RECTS_AT, RECTS_AT + aes.GRECT_BYTES
STALE_BAND = {BAND_AT: vdi.pack_words(*[aes.STALE_WORD] * (BAND_BYTES // aes.WORD_BYTES))}
STALE_SLOTS = merge_pokes(*(aes.stale_host_slot(role) for role in ("AES_FM_DO_FRAME", "AES_FM_BUTTON_FRAME",
                                                                     "AES_OB_EDIT_FRAME")))


@functools.cache
def running(shown=False):
    """PD0 running as the scheduler makes it, the cursor hidden (or `shown`), the band and the frames stale."""
    woken = (aes_event.shown_machine if shown else aes_event.machine)()
    return merge_pokes(woken, STALE_BAND, STALE_SLOTS)


def door_run(name, values, pokes, **kwargs):
    """A door user's run, its C first in a child (`aes_event.run_guarded`), the VDI's cores and just_draw served."""
    return aes_event.run_guarded(name, values, pokes, drawing=True, objects=JUST_DRAW, **kwargs)


# ---- where the objects are on the screen ------------------------------------------------------------------------------
def middle_of(tree, index, onto=None):
    """The middle of `index` on the screen over the machine `onto` (the snapshot's by default): where the ROM's own
    ob_offset places it, and half its size."""
    frame = aes_event.frame_of(("l", tree), ("w", index), ("l", PLACE_X_AT), ("l", PLACE_Y_AT))
    _written, final, _regs = aes_event.derived(addrs.AES_ROM_OB_OFFSET, onto, frame=frame)
    placed = aes.read_object(final, tree, index)
    return (aes.signed(case.word_in(final, PLACE_X_AT)) + placed["WIDTH"] // 2,
            aes.signed(case.word_in(final, PLACE_Y_AT)) + placed["HEIGHT"] // 2)


OFF_THE_SELECTOR = (5, 5)               # above the selector's root (it starts 29 rows down): ob_find's -1
move_to, press, release = aes_event.move_to, aes_event.press, aes_event.release


def clicked(tree, index):
    """A click on `index`: the mouse moved onto its middle and the left button pressed — two interrupts."""
    return move_to(*middle_of(tree, index)), press


# ---- fm_dial ---------------------------------------------------------------------------------------------------------
LITTLE = (100, 100, 20, 10)             # a desk icon's box, say
BIG = (40, 30, 200, 120)                # ...and the dialog grown out of it


def dial(type_, shown=False, onto=None, **kwargs):
    rects = {LITTLE_AT: struct.pack(">4h", *LITTLE), BIG_AT: struct.pack(">4h", *BIG)}
    return door_run(DIAL, (type_, LITTLE_AT, BIG_AT), merge_pokes(running(shown), onto, rects), **kwargs)


DIAL_TYPES = {"FMD_START": FM["FMD_START"], "FMD_GROW": FM["FMD_GROW"], "FMD_SHRINK": FM["FMD_SHRINK"],
              "FMD_FINISH": FM["FMD_FINISH"], "a type it does not know": 4, "-1": -1}


@pytest.mark.parametrize("shown", (False, True), ids=("the cursor hidden", "the cursor shown"))
@pytest.mark.parametrize("type_", DIAL_TYPES.values(), ids=DIAL_TYPES)
def test_fm_dial(type_, shown):
    """The D0 form_dial's binding stores: the type itself for FMD_START and a type it does not know; for the three it
    draws, gsx_mon's — 1 while the caller's hide nest stays open, v_show_c's 0 once it shows the cursor."""
    drawn = type_ in (FM["FMD_GROW"], FM["FMD_SHRINK"], FM["FMD_FINISH"])
    shown_answer = FM["FM_DIAL_SHOWN_ANSWER"] if shown else FM["FM_DIAL_NEST_OPEN_ANSWER"]
    assert dial(type_, shown).answer() == (shown_answer if drawn else type_)


@functools.cache
def window_opened(shown=False):
    """PD0 running (the cursor hidden or `shown`) with a window open where the dialog will be — the ROM's wm_create +
    wm_open: `(the machine, the window)`."""
    return aes_event.window_chain(aes_event.EVERY_GADGET, *BIG, onto=running(shown))


def window_open(shown=False):
    return window_opened(shown)[0]


@functools.cache
def drawing_held(shown=False):
    """...and window drawing then HELD by the application: the ROM's own wind_set(window, 13)."""
    machine, window = window_opened(shown)
    return wmlib.window_set(machine, window, wmlib.WM["WF_RESVD"], 0)


@pytest.mark.parametrize("shown", (False, True), ids=("the cursor hidden", "the cursor shown"))
def test_fm_dial_finish_while_drawing_is_held_answers_w_clipdraw_s_1(shown):
    """Window drawing HELD: w_drawdesk's w_clipdraw draws nothing and answers 1, and w_update leaves it — whatever the
    cursor, which no gsx_mon then shows."""
    machine = drawing_held(shown)
    assert case.word_in(make_image(machine), aes.AES_GL_WFROZEN) == 1
    assert dial(FM["FMD_FINISH"], shown, onto=machine).answer() == FM["FM_DIAL_HELD_ANSWER"]


def test_fm_dial_finish_over_an_open_window_redraws_it_through_its_owner():
    """FMD_FINISH over that window: its owner, PD0, is sent a redraw message (w_redraw, through ap_sendmsg's door call)
    beside the desktop's redraw — merged by ap_rdwr into the redraw wm_open left in its pipe, which stays one message
    long."""
    result = dial(FM["FMD_FINISH"], onto=window_open())
    assert [call.routine for call in aes_event.HANDED] == [addrs.AES_ROM_AP_RDWR]
    before = aes.read_field(make_image(merge_pokes(running(), window_open())), "PD", "QUEUE_INDEX", aes.SHELL_PD)
    assert result.field("PD", "QUEUE_INDEX", aes.SHELL_PD) == before


# ---- fm_do -----------------------------------------------------------------------------------------------------------
RETURN = aes_event.RETURN_KEY
TAB, BACKSPACE, ESCAPE, UNDO, ENTER = 0x0F, 0x0E, 0x01, 0x61, 0x72   # make codes
UP, DOWN, LEFT, RIGHT, DELETE = 0x48, 0x50, 0x4B, 0x4D, 0x53
key, typed, Waits = aes_event.key, aes_event.typed, aes_event.Waits


def form_do(tree, start=0, onto=None, **kwargs):
    return door_run(DO, (tree, start), merge_pokes(running(), onto), **kwargs)


def in_the_ring(*codes, onto=None):
    """`onto` (PD0 running) with the keys of `codes` already in the keyboard's ring when fm_do starts."""
    return aes_event.typed_ahead(merge_pokes(running(), onto), *codes)


def interrupted(tree, start, interrupts, onto=None, **kwargs):
    return aes_event.interrupted(DO, (tree, start), merge_pokes(running(), onto), interrupts, objects=True, **kwargs)


@pytest.mark.parametrize("codes", ((RETURN,), (ENTER,), tuple(aes_event.scancodes_of("abc\r"))), ids=("Return", "Enter", "abc, Return"))
def test_fm_do_over_keys_in_the_ring(codes):
    """The keys typed before the dialog: fm_do takes one per wait, the last ending it on the DEFAULT button."""
    result = door_run(DO, (SELECTOR, 0), in_the_ring(*codes))
    assert result.answer() == OK


# (start, keys typed one per wait, the answer): every key fm_keybd moves by, and every key ob_edit edits by, into the
# selector's two fields.
TYPED = {
    "Return": (0, (RETURN,), OK),
    "a path typed, then Return": (0, ("abc", RETURN), OK),
    "Tab to the name, typed, Return": (0, (TAB, "x", RETURN), OK),
    "Down, then Up, then Return": (0, (DOWN, UP, RETURN), OK),
    "typed, Backspace, Return": (0, ("ab", BACKSPACE, RETURN), OK),
    "typed, Escape, Return": (0, ("ab", ESCAPE, RETURN), OK),
    "typed, Left, Delete, Right, Return": (0, ("ab", LEFT, DELETE, RIGHT, RETURN), OK),
    "Undo, which no field takes, then Return": (0, (UNDO, RETURN), OK),
    "started in the name field": (NAME_FIELD, ("y", RETURN), OK),
    "Tab past the last field, Return": (NAME_FIELD, (TAB, RETURN), OK),
}


@pytest.mark.parametrize("start, codes, answer", TYPED.values(), ids=TYPED)
def test_fm_do_typed_into(start, codes, answer):
    taken = interrupted(SELECTOR, start, typed(*codes))
    assert taken.answer == answer


# A PATH IN THE FIELD, as the selector's caller fs_input copies it there before its fm_do: one character short of the
# field's room, so an edit moves the most text — the longest rows of the dialog's own editing.
PATH_TEXT_AT = aes.read_field(BASE_IMAGE, "TE", "PTEXT", od.object_long(SELECTOR, PATH_FIELD, "SPEC"))
PATH_ROOM = aes.read_field(BASE_IMAGE, "TE", "TXTLEN", od.object_long(SELECTOR, PATH_FIELD, "SPEC")) - 1
LONG_PATH = b"C:\\GAMES\\ARCADE\\SHOOTERS\\VERTICAL\\*.*"
LONG_PATH_TYPED = {f"a {len(LONG_PATH)}-character path: {label}": codes for label, codes in (
    ("Backspace, Return", (BACKSPACE, RETURN)),
    ("a key, Return", ("a", RETURN)),
    ("Left, Delete, Return", (LEFT, DELETE, RETURN)),
    ("Escape, Return", (ESCAPE, RETURN)),
)}


def long_path():
    assert len(LONG_PATH) == PATH_ROOM - 1
    return {PATH_TEXT_AT: LONG_PATH + b"\0"}


@pytest.mark.parametrize("codes", LONG_PATH_TYPED.values(), ids=LONG_PATH_TYPED)
def test_fm_do_typed_into_a_long_path(codes):
    taken = interrupted(SELECTOR, 0, typed(*codes), onto=long_path())
    assert taken.answer == OK


# ---- fm_do taken through clicks: the mouse moved and the button pressed or released at its waits -------------------------
BELL_MACHINE = aes_event.savptr_in_the_band()   # the bell's `trap #13` saves the registers where nothing compares them
ELSEWHERE = (300, 20)                   # on the selector's root, off every object of it


# (start, {ev_multi wait: interrupts}, the machine's pokes, the answer). A SELECTABLE object's click is released at
# gr_watchbox's wait, whose head runs forker — so the rise awaited after it is already the AES's.
CLICKED = {
    "OK clicked, released on it": (0, {0: clicked(SELECTOR, OK), 1: release}, None, OK),
    "Cancel clicked": (0, {0: clicked(SELECTOR, CANCEL), 1: release}, None, CANCEL),
    "OK pressed, the mouse taken off, released; then Return": (
        0, {0: clicked(SELECTOR, OK), 1: move_to(*ELSEWHERE), 2: release, 3: key(RETURN)}, None, OK),
    "the TOUCHEXIT arrow pressed": (0, {0: clicked(SELECTOR, ARROW_UP)}, None, ARROW_UP),
    "a file slot under the snapshot's mouse pressed": (0, {0: press}, None, FILE_SLOT),
    "the arrow double-clicked": (0, {0: (move_to(*middle_of(SELECTOR, ARROW_UP)), aes_event.double_click)}, None,
                                 ARROW_UP | FM["FM_DOUBLE_CLICKED"]),
    "the name field clicked, a key typed, Return": (
        0, {0: clicked(SELECTOR, NAME_FIELD), 1: (release, key(aes_event.scancode_of("z"))), 2: key(RETURN)}, None, OK),
    "off the dialog: the bell, then Return": (
        0, {0: (move_to(*OFF_THE_SELECTOR), press), 1: (release, key(RETURN))}, BELL_MACHINE, OK),
    "a DISABLED OK clicked, then Return": (
        0, {0: clicked(SELECTOR, OK), 1: (release, key(RETURN))}, od.state_pokes(SELECTOR, OK, DISABLED), OK),
    "the field being edited clicked: no new edit; then Return": (
        0, {0: clicked(SELECTOR, PATH_FIELD), 1: (release, key(RETURN))}, None, OK),
    # A key and a press taken by ONE wait: fm_keybd's verdict (Return: done) is overwritten by fm_button's (a field:
    # go on), so the form goes on — in the field clicked.
    "Return and a click on a field in one wait: the click's verdict wins; then Return": (
        0, {0: (key(RETURN), *clicked(SELECTOR, NAME_FIELD)), 1: (release, key(RETURN))}, None, OK),
}


@pytest.mark.parametrize("start, waits, pokes, answer", CLICKED.values(), ids=CLICKED)
def test_fm_do_taken_through_clicks(start, waits, pokes, answer):
    taken = interrupted(SELECTOR, start, Waits(waits), onto=pokes)
    assert taken.answer == answer


# ---- the desk's dialogs, as the desk shows them: centred by the ROM's own ob_center ------------------------------------
PREFERENCES = TREES["desk tree 13"]     # the desk's longest dialog: five radio groups, OK the DEFAULT, Cancel
PREFERENCES_OK = 17
RADIO, ITS_SIBLING = 5, 4               # a pair of radio buttons under one parent, 4 SELECTED in the snapshot
NONE_CHOSEN_RADIO = 13                  # ...one of a group of five (12..16) none of which the snapshot selects
LAST_RADIO = 23                         # ...the tree's last object, a radio button and LASTOB
FIELDS_DIALOG = TREES["desk tree 6"]    # two fields, OK the DEFAULT, Cancel
FIELDS_DIALOG_BUTTONS = FIRST_FIELD, SECOND_FIELD, FIELDS_DIALOG_OK, FIELDS_DIALOG_CANCEL = 2, 3, 4, 5
# The desk's dialog with a plain exit button beside its OK: the last button (SELECTABLE | EXIT | LASTOB), made an
# application's radio exit button by the cases below, and the OK left SELECTED from the last time it was shown.
PLAIN_EXITS = TREES["desk tree 1"]
PLAIN_EXIT, PLAIN_EXITS_OK = 11, 10


# As the desk shows the preferences: the current choice of each radio group selected (the desk's objc state sets).
SHOWN_CHOICE = od.state_pokes(PREFERENCES, ITS_SIBLING, SELECTED)


@functools.cache
def centred(tree):
    """PD0 running with `tree` centred on the screen — the ROM's own ob_center, as the desk calls it first."""
    written, _final, _regs = aes_event.derived(addrs.AES_ROM_OB_CENTER, running(),
                                               frame=aes_event.frame_of(("l", tree), ("l", CENTRED_AT)))
    return merge_pokes(running(), written, SHOWN_CHOICE if tree == PREFERENCES else None)


def middle_on_screen(tree, index):
    return middle_of(tree, index, centred(tree))


def flags_of(tree, index):
    return aes.read_object(BASE_IMAGE, tree, index)["FLAGS"]


def test_the_dialogs_are_what_the_cases_say():
    radio = SELECTABLE | RBUTTON
    assert [flags_of(PREFERENCES, index) for index in (RADIO, ITS_SIBLING, NONE_CHOSEN_RADIO)] == [radio] * 3
    assert flags_of(PREFERENCES, LAST_RADIO) == radio | aes.OB_FLAG_LASTOB
    assert aes.parent_of(PREFERENCES, RADIO) == aes.parent_of(PREFERENCES, ITS_SIBLING)
    assert [flags_of(FIELDS_DIALOG, index) for index in FIELDS_DIALOG_BUTTONS] == [
        EDITABLE, EDITABLE, SELECTABLE | DEFAULT | EXIT, SELECTABLE | EXIT], "two fields, OK the DEFAULT, Cancel"
    assert [flags_of(PLAIN_EXITS, index) for index in (PLAIN_EXITS_OK, PLAIN_EXIT)] == [
        SELECTABLE | DEFAULT | EXIT, SELECTABLE | EXIT | aes.OB_FLAG_LASTOB]


def quick_click(tree, index):
    """A click on `index` of the centred `tree`, the button down and up again before the AES looks: the mouse moved,
    pressed, released — so the rise a radio button's click awaits (ev_button, which runs no forker before it waits)
    is already the AES's when it asks."""
    return move_to(*middle_on_screen(tree, index)), press, release


# (tree, {ev_multi wait: interrupts}, the answer)
DIALOGS = {
    "a radio button clicked, its sibling put down; then Return": (
        PREFERENCES, {0: quick_click(PREFERENCES, RADIO), 1: key(RETURN)}, PREFERENCES_OK),
    "the radio button already selected clicked; then Return": (
        PREFERENCES, {0: quick_click(PREFERENCES, ITS_SIBLING), 1: key(RETURN)}, PREFERENCES_OK),
    "OK clicked": (PREFERENCES, {0: (move_to(*middle_on_screen(PREFERENCES, PREFERENCES_OK)), press), 1: release},
                   PREFERENCES_OK),
    "two fields typed, Tab between, Return": (FIELDS_DIALOG, {0: key(aes_event.scancode_of("a")), 1: key(TAB),
                                                              2: key(aes_event.scancode_of("b")), 3: key(RETURN)},
                                              FIELDS_DIALOG_OK),
}


@pytest.mark.parametrize("tree, waits, answer", DIALOGS.values(), ids=DIALOGS)
def test_fm_do_over_a_desk_dialog(tree, waits, answer):
    taken = aes_event.interrupted(DO, (tree, 0), centred(tree), Waits(waits), objects=True)
    assert taken.answer == answer


def test_a_radio_button_held_down_waits_as_the_rom_s():
    """The radio button pressed and held: taken at once, its group redrawn, then the wait for the rise — ev_button,
    which BLOCKS (it runs no forker; the machine switches away until the button rises). Up to it the C is the ROM's run
    stopped there: the whole image, the radio group's states in it, every frame handed."""
    machine = centred(PREFERENCES)
    taken = aes_event.interrupted(DO, (PREFERENCES, 0), machine,
                                  Waits({0: (move_to(*middle_on_screen(PREFERENCES, RADIO)), press)}), objects=True)
    assert not taken.returned and taken.calls[-1].routine == addrs.AES_ROM_EV_BUTTON
    assert [aes.read_object(taken.image, PREFERENCES, index)["STATE"] & SELECTED for index in (ITS_SIBLING, RADIO)] == \
        [0, SELECTED]


# ---- fm_do: the keys queued before it, a field that exits ------------------------------------------------------------
def field_text(image, tree, index):
    """The text of the field `index` (its TEDINFO's te_ptext) as `image` holds it."""
    return fmlib.string_at(aes.read_field(image, "TE", "PTEXT", od.object_long(tree, index, "SPEC", image)), image)


def test_a_key_queued_before_the_dialog_is_flushed():
    """'a' typed while the application ran and polled into PD0's key queue by its last wait (the ROM's own chkkbd and
    forker over this very machine, `test_aes_fmlib.polled`): fm_do's fq throws it away before it waits — the field
    is left as it was, and Return ends the form."""
    machine = fmlib.polled(running(), fmlib.KEY_A)
    taken = interrupted(SELECTOR, 0, Waits({0: key(RETURN)}), onto=machine)
    assert taken.answer == OK
    assert field_text(taken.image, SELECTOR, PATH_FIELD) == field_text(make_image(machine), SELECTOR, PATH_FIELD)


def test_a_touchexit_field_clicked_while_edited_ends_its_edit():
    """An application's field that also exits on a press (EDITABLE | TOUCHEXIT): clicked while it is the one edited,
    the form ends on it — and its edit is ended (the cursor taken off) though the object is the same."""
    exits = od.flags_pokes(SELECTOR, PATH_FIELD, EDITABLE | TOUCHEXIT)
    taken = interrupted(SELECTOR, 0, Waits({0: clicked(SELECTOR, PATH_FIELD)}), onto=exits)
    assert taken.answer == PATH_FIELD


# ---- fm_do: the wait nothing satisfies, the call word, the tree on the bus ---------------------------------------------
def test_fm_do_with_nothing_typed_waits_as_the_rom_s():
    """No key and no press: the first wait blocks; up to it the C is the ROM's run stopped there (the field's edit
    begun, the cursor drawn)."""
    taken = aes_event.refused_where_the_rom_blocks(DO, (SELECTOR, 0), running(), objects=True)
    assert [call.routine for call in taken.calls][-1] == addrs.AES_ROM_EV_MULTI


@THROUGH
def test_fm_do_through_its_callers_word(through_line_f):
    assert form_do(SELECTOR, onto=in_the_ring(RETURN), through_line_f=through_line_f).answer() == OK


def test_fm_do_puts_the_tree_on_the_bus():
    assert form_do(SELECTOR | aes.BUS_TAG, onto=in_the_ring(RETURN)).answer() == OK


# ---- fm_button, as form_button calls it: the click already the AES's, the button up ------------------------------------
def button(tree, index, clicks=1, onto=None, next_at=NEXT_AT, **kwargs):
    return door_run(BUTTON, (tree, index, clicks, next_at), merge_pokes(running(), onto), **kwargs)


RADIO_EXIT = od.flags_pokes(PLAIN_EXITS, PLAIN_EXIT, flags_of(PLAIN_EXITS, PLAIN_EXIT) | RBUTTON)
# (tree, object, clicks, pokes, answer, *next)
BUTTONS = {
    "OK: watched, selected, an exit": (SELECTOR, OK, 1, None, 0, OK),
    "Cancel": (SELECTOR, CANCEL, 1, None, 0, CANCEL),
    "the TOUCHEXIT arrow": (SELECTOR, ARROW_UP, 1, None, 0, ARROW_UP),
    "the arrow, two clicks": (SELECTOR, ARROW_UP, FM["FM_DOUBLE_CLICKS"], None, 0, ARROW_UP | FM["FM_DOUBLE_CLICKED"]),
    "OK, two clicks: no TOUCHEXIT, no top bit": (SELECTOR, OK, FM["FM_DOUBLE_CLICKS"], None, 0, OK),
    "a field: the form goes on in it": (SELECTOR, NAME_FIELD, 1, None, 1, NAME_FIELD),
    "the root: nothing": (SELECTOR, aes.OB_ROOT, 1, None, 1, 0),
    "a DISABLED OK: not taken": (SELECTOR, OK, 1, od.state_pokes(SELECTOR, OK, DISABLED), 1, 0),
    "a radio button: its group put down": (PREFERENCES, RADIO, 1, SHOWN_CHOICE, 1, 0),
    "the radio button already selected": (PREFERENCES, ITS_SIBLING, 1, SHOWN_CHOICE, 1, 0),
    "a radio button in a group with none selected": (PREFERENCES, NONE_CHOSEN_RADIO, 1, None, 1, 0),
    "a radio button that is LASTOB too": (PREFERENCES, LAST_RADIO, 1, None, 1, 0),
    # An application's shapes no resource has: a SELECTABLE TOUCHEXIT button (taken at once, no rise awaited), and a
    # radio EXIT button among the root's other children (every sibling but itself no radio button).
    "a SELECTABLE TOUCHEXIT button": (SELECTOR, OK, 1, od.flags_pokes(SELECTOR, OK, flags_of(SELECTOR, OK) | TOUCHEXIT),
                                      0, OK),
    "a radio exit button among plain siblings": (PLAIN_EXITS, PLAIN_EXIT, 1, RADIO_EXIT, 0, PLAIN_EXIT),
    # ...one of them, the dialog's OK, still SELECTED from the last time it was shown (an application that does not
    # deselect its exit button): not a radio button, so left as it is.
    "a radio exit button, a plain sibling left selected": (
        PLAIN_EXITS, PLAIN_EXIT, 1, merge_pokes(RADIO_EXIT, od.state_pokes(PLAIN_EXITS, PLAIN_EXITS_OK, SELECTED)), 0,
        PLAIN_EXIT),
}


@pytest.mark.parametrize("tree, index, clicks, pokes, answer, next_", BUTTONS.values(), ids=BUTTONS)
def test_fm_button(tree, index, clicks, pokes, answer, next_):
    result = button(tree, index, clicks, pokes)
    assert result.answer() == answer and result.word(NEXT_AT) == next_


def test_fm_button_puts_its_pointers_on_the_bus():
    button(SELECTOR | aes.BUS_TAG, OK, next_at=NEXT_AT | aes.BUS_TAG)


@THROUGH
def test_fm_button_through_its_callers_word(through_line_f):
    button(SELECTOR, OK, through_line_f=through_line_f)


def test_fm_button_held_down_on_ok_waits_as_the_rom_s():
    """The button still down over OK (the snapshot's mouse is not on it): gr_watchbox's first pass waits for the mouse
    to enter, which blocks — the C held to the ROM's run stopped there."""
    machine = merge_pokes(aes_event.machine(aes_event.button_down), STALE_BAND, STALE_SLOTS)
    taken = aes_event.refused_where_the_rom_blocks(BUTTON, (SELECTOR, OK, 1, NEXT_AT), machine, objects=True)
    assert taken.calls[-1].routine == addrs.AES_ROM_EV_MULTI


# ---- the bell ----------------------------------------------------------------------------------------------------------
# UNPOISONED, measured: the trap's dispatcher writes `savptr` itself on the way in and out, so the attribution pass
# inverts the band address a case stages there and sends the ROM's save frame off into memory no case staged — the
# run did not return within 200,000 instructions (`gemdos.py`, "NOTHING THAT STAGES THIS MAY POISON"). The console's
# own stores (the sound list, the bell's state) are compared on the plain pass.
SAVPTR_STEERS_THE_PASS = {"poison": False}


def bell_machine(conterm=None, onto=None):
    """PD0 running over the bell's machine, conterm the byte `conterm` (the snapshot's when None), then `onto`."""
    conterm_pokes = {addrs.SYSVAR_CONTERM: bytes([conterm])} if conterm is not None else None
    return merge_pokes(running(), BELL_MACHINE, conterm_pokes, onto)


def bell(conterm=None, onto=None, **kwargs):
    return aes.run_function(BELL, (), bell_machine(conterm, onto), **SAVPTR_STEERS_THE_PASS, **kwargs)


BELL_ON = 1 << addrs.CONTERM_BELL_BIT


@pytest.mark.parametrize("conterm", (BELL_ON, 0x00), ids=("the bell on (conterm bit 2)", "the bell off"))
def test_bell(conterm):
    result = bell(conterm)
    rings = case.long_in(result.final, addrs.SOUND_LIST_POINTER) == addrs.BELL_SOUND_LIST
    assert rings == bool(conterm & BELL_ON)


# THE CONSOLE MID-ESCAPE: a program that printed ESC (or ESC Y, ESC b) and then put up a dialog — the bell's BEL is then
# the escape's next character, taken by the state the console's con_state names. Its longest runs.
MID_ESCAPE = {"ESC": addrs.CON_STATE_ESCAPE, "ESC Y, its row": addrs.CON_STATE_AWAIT_Y_ROW,
              "ESC Y, its column": addrs.CON_STATE_AWAIT_Y_COLUMN, "ESC b": addrs.CON_STATE_AWAIT_FOREGROUND}


def mid_escape(state):
    return {addrs.CON_STATE_VECTOR: struct.pack(">I", state)}


@pytest.mark.parametrize("conterm", (BELL_ON, 0x00), ids=("the bell on", "the bell off"))
@pytest.mark.parametrize("state", MID_ESCAPE.values(), ids=MID_ESCAPE)
def test_bell_with_the_console_mid_escape(state, conterm):
    bell(conterm, onto=mid_escape(state))


@THROUGH
def test_bell_through_its_callers_word(through_line_f):
    bell(through_line_f=through_line_f)


# ---- a long typing session: ONE call, priced by its slices (`aes_event.register_slices`) -------------------------------
# The selector's path field typed full from empty, a key per wait, then Return: 728,664 ROM instructions (measured) —
# a call no row prices whole (past `emu.run`'s cap), and past what DERIVATION_INSNS admits under its margin: its budget
# is DECLARED, five times its spend and room. Its slices are the session's shapes: the dialog taken up to its first
# wait, a key (the last one typed moves the most text: fm_do's worst, measured), the Return that ends it — and the
# first key cut in two at a VDI call inside it, the cut a stretch with no door call would need.
SESSION_TEXT = "abcdefghijklmnopqrstuvwxyz0123456789a"
assert len(SESSION_TEXT) == PATH_ROOM - 1
SESSION_INSNS = 4_000_000
WAIT = addrs.AES_ROM_EV_MULTI
LAST_KEY = len(SESSION_TEXT) - 1        # the wait the last character is typed at; Return's is the next
VDI_TRAP = aes_event.VDI_TRAP
VDI_CALL_IN_THE_FIRST_KEY = 14          # the VDI call the first key is cut at: of its 17 (6..22), one near the middle
KEYS_IN_THE_SESSION = f"a {len(SESSION_TEXT) + 1}-key session"
SESSION_SLICES = {
    f"{KEYS_IN_THE_SESSION}: the dialog taken, to its first wait": (aes_event.ENTRY, aes_event.door_call(WAIT, 0)),
    f"{KEYS_IN_THE_SESSION}: the first key, to a VDI call inside it": (
        aes_event.door_call(WAIT, 0), aes_event.trap_taken(VDI_TRAP, VDI_CALL_IN_THE_FIRST_KEY)),
    f"{KEYS_IN_THE_SESSION}: the first key, from that VDI call to the next wait": (
        aes_event.trap_taken(VDI_TRAP, VDI_CALL_IN_THE_FIRST_KEY), aes_event.door_call(WAIT, 1)),
    f"{KEYS_IN_THE_SESSION}: the last character typed": (
        aes_event.door_call(WAIT, LAST_KEY), aes_event.door_call(WAIT, LAST_KEY + 1)),
    f"{KEYS_IN_THE_SESSION}: Return, to the return": (aes_event.door_call(WAIT, LAST_KEY + 1), aes_event.RETURN),
}


def session():
    """The long typing session: `(routine, arguments, machine, interrupts)`."""
    return DO, (SELECTOR, 0), running(), typed(SESSION_TEXT, RETURN)


# ---- the registry: Tier 3's rows (each routine's worst realistic shape measured, `make bench`) ------------------------
def register(label, name, values, pokes):
    aes_event.register(label, name, values, pokes, drawing=True, objects=JUST_DRAW)


def _register_rows():
    rects = {LITTLE_AT: struct.pack(">4h", *LITTLE), BIG_AT: struct.pack(">4h", *BIG)}
    for label, type_ in DIAL_TYPES.items():
        register(label, DIAL, (type_, LITTLE_AT, BIG_AT), merge_pokes(running(), rects))
    for label, onto in (("FMD_FINISH over an open window", window_open()), ("FMD_FINISH, drawing held", drawing_held())):
        register(label, DIAL, (FM["FMD_FINISH"], LITTLE_AT, BIG_AT), merge_pokes(running(), onto, rects))
    for label in ("OK: watched, selected, an exit", "the TOUCHEXIT arrow", "the arrow, two clicks",
                  "a field: the form goes on in it", "the root: nothing", "a DISABLED OK: not taken",
                  "a radio button: its group put down", "a radio exit button among plain siblings"):
        tree, index, clicks, pokes, _answer, _next = BUTTONS[label]
        register(label, BUTTON, (tree, index, clicks, NEXT_AT), merge_pokes(running(), pokes))
    register("Return in the ring", DO, (SELECTOR, 0), in_the_ring(RETURN))
    register("abc, then Return, in the ring", DO, (SELECTOR, 0), in_the_ring(*aes_event.scancodes_of("abc\r")))
    for label in ("OK clicked, released on it", "off the dialog: the bell, then Return",
                  "the name field clicked, a key typed, Return", "a DISABLED OK clicked, then Return"):
        start, waits, pokes, _answer = CLICKED[label]
        aes_event.register_interrupted(label, DO, (SELECTOR, start), merge_pokes(running(), pokes), Waits(waits),
                                       objects=True)
    for label in ("typed, Left, Delete, Right, Return", "Tab to the name, typed, Return"):
        start, codes, _answer = TYPED[label]
        aes_event.register_interrupted(label, DO, (SELECTOR, start), running(), typed(*codes), objects=True)
    for label, codes in LONG_PATH_TYPED.items():
        aes_event.register_interrupted(label, DO, (SELECTOR, 0), merge_pokes(running(), long_path()), typed(*codes),
                                       objects=True)
    tree, waits, _answer = DIALOGS["a radio button clicked, its sibling put down; then Return"]
    aes_event.register_interrupted("a radio button clicked, then Return", DO, (tree, 0), centred(tree), Waits(waits),
                                   objects=True)
    aes_event.register_slices(*session(), SESSION_SLICES, objects=True, budget=SESSION_INSNS)
    for label, conterm in (("the bell on", BELL_ON), ("the bell off", 0)):
        aes.register(label, BELL, (), bell_machine(conterm))
    for name in ("ESC", "ESC Y, its row"):
        aes.register(f"the bell on, the console mid-escape ({name})", BELL, (),
                     bell_machine(BELL_ON, mid_escape(MID_ESCAPE[name])))


_register_rows()
