"""THE ALERTS (`src/aes/fmdo.c`): an alert laid out from its string and run (fm_alert), one of the AES's own strings merged
and shown (fm_show), the critical error handler's (eralert) and a GEMDOS error's (fm_error) — every one run by fm_do,
through the event door (`test/aes_event.py`).

    fm_alert(def, str)    tree 1 (rs_gaddr) OUTLINED; fm_parse, fm_build; def: object def+6 DEFAULT; an icon: its BITBLK
            (rs_gaddr R_BITBLK icon-1) into object 1; rs_obfix x10; object 1 32 x 32; ob_center; wm_update(1); the clip
            saved, the box's screen saved and the tree drawn under it; ct_mouse(1); fm_do(tree, 0); ct_mouse(0); the
            screen and the clip put back; wm_update(0); the button, 1 for the first
    fm_show(n, vals, def) rs_str(n), merged with vals into $b99a when there are any; fm_alert(def, it)
    eralert(err, drv)     "A" + drv; the string $fefa14[err], its default the low byte of $fefa22[err] and the drive
            handed (%S) when its high byte is set; fm_show; 0 for the first button, 1 (retry) otherwise
    fm_error(n)           n > 63: 0. The string from the jump table $fefa68 over n - 2 (unsigned), "TOS error #%W" for
            every code it has no row for, merged over n's own word; fm_show(it, 1); 0 for the first button, else 1

THE DATA IS THE SNAPSHOT's: every alert string of both resources (the AES's own error alerts and the desk's), the
AES's alert tree and icons; an application's own string, staged in the band, for the shapes no resource string has (no
icon, three buttons, five lines at the 31-character cap). The machine is PD0 running (`aes_event.machine`), the cursor
hidden or shown; the user's answer is DELIVERED — Return in the keyboard's ring before the call, or a key typed or a
button clicked at the wait that takes it (`aes_event.interrupted`), each button's place read off the ROM's own run at
its first wait (the tree is laid out as the alert opens).
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_gsx as gsx
import aes_resource as rs
import case
import test_aes_fmdo as fmdo
import test_aes_fmlib as fmlib
import vdi
from case import merge_pokes

L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
ALERT, SHOW, ERALERT, ERROR = "AES_ROM_FM_ALERT", "AES_ROM_FM_SHOW", "AES_ROM_ERALERT", "AES_ROM_FM_ERROR"
SIGNATURES = {
    ALERT: (aes.WORD_ANSWER, (I, W, L)),
    SHOW: (aes.WORD_ANSWER, (I, W, L, W)),
    ERALERT: (aes.WORD_ANSWER, (I, W, W)),
    ERROR: (aes.WORD_ANSWER, (I, W)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

FM = aes.header_constants("fmdo.h")
THROUGH = gsx.THROUGH
ALERT_TREE = fmlib.ALERT_TREE
FIRST_BUTTON = fmlib.FM["ALERT_FIRST_BUTTON"]
OBJECTS = fmlib.FM["ALERT_OBJECTS"]
RETURN = aes_event.RETURN_KEY
key, Waits, move_to, press, release = aes_event.key, aes_event.Waits, fmdo.move_to, fmdo.press, fmdo.release
STALE_SLOTS = merge_pokes(*(aes.stale_host_slot(role) for role in ("AES_FM_ALERT_FRAME", "AES_ERALERT_FRAME",
                                                                     "AES_FM_ERROR_CODE", "AES_FM_PARSE_INDEX",
                                                                     "AES_FM_BUILD_RECTS")))
aes.declare_case_field(FM["AES_FM_SHOW_ALERT"], FM["AES_FM_SHOW_ALERT_BYTES"], "fm_show's merged string")


@functools.cache
def running(shown=False):
    """PD0 running (`test_aes_fmdo.running`), the alert's frames stale too."""
    return merge_pokes(fmdo.running(shown), STALE_SLOTS)


def answered(*codes, shown=False, onto=None):
    """`running()` with the keys of `codes` in the keyboard's ring before the call."""
    return aes_event.typed_ahead(merge_pokes(running(shown), onto), *codes)


door_run = fmdo.door_run


# ---- the strings: the resources' own alerts, and an application's ------------------------------------------------------
ALERTS = fmlib.ALERTS
STRING_AT = fmlib.STRING_AT             # an application's alert string, in the blocks band
LONGEST_LINE = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ01234"   # 31 characters: the cap
LONGEST_BUTTONS = (b"ABCDEFGHIJ", b"KLMNOPQRST", b"UVWXYZ0123")   # three, 10 characters each
# THE DOCUMENTED MAXIMUM — five lines at the cap and three 10-character buttons — runs 200,973 ROM instructions (208,880
# with the cursor shown). That is past what an UNWATCHED original runs (emu.run's cap, which a row with its Return
# queued before the call is measured under), not past what the bench prices: so it is registered TAKEN THROUGH its
# Return (typed at its wait, `_register_rows`), whose original runs watched — a choice of how the key arrives, not a
# limit. Measured (`make bench`): fm_alert's worst, 0.687 with the cursor shown against 0.681 for the same lines with
# three short buttons, the pre-queued row below.
MAXIMUM_ALERT = b"[3][" + b"|".join([LONGEST_LINE] * 5) + b"][" + b"|".join(LONGEST_BUTTONS) + b"]"
APPLICATION_ALERTS = {
    "no icon, one button": b"[0][Nothing to see.][ OK ]",
    "three buttons": b"[1][Save the changes?][Save|Discard|Cancel]",
    "five lines at the cap, three buttons": b"[3][" + b"|".join([LONGEST_LINE] * 5) + b"][One|Two|Three]",
}


def application(name):
    return {STRING_AT: APPLICATION_ALERTS[name] + b"\0"}


def button_count(name):
    """How many buttons the application's alert `name` has: its last section's '|'s, and one."""
    return APPLICATION_ALERTS[name].rsplit(b"[", 1)[1].count(b"|") + 1


def alert(default, string, pokes, **kwargs):
    return door_run(ALERT, (default, string), pokes, **kwargs)


@pytest.mark.parametrize("name", sorted(ALERTS))
def test_fm_alert_over_each_real_alert(name):
    """Return, the first button the default: the alert drawn, run and put back, answering 1."""
    assert alert(1, ALERTS[name], answered(RETURN)).answer() == 1


@pytest.mark.parametrize("name", sorted(APPLICATION_ALERTS))
@pytest.mark.parametrize("shown", (False, True), ids=("the cursor hidden", "the cursor shown"))
def test_fm_alert_over_an_application_s_alert(name, shown):
    """Return, the LAST button the default: answered with its number."""
    buttons = button_count(name)
    assert alert(buttons, STRING_AT, answered(RETURN, shown=shown, onto=application(name))).answer() == buttons


def shown_lines(result, count):
    """The alert tree's first `count` message lines as the run left them."""
    return [fmlib.line_of(result, fmlib.FIRST_LINE + line) for line in range(count)]


def aes_string(number):
    """The AES resource's free string `number`, as the snapshot holds it: rsrc_gaddr(R_STRING)'s answer over the
    snapshot's resource globals (`aes_resource.model_get_addr`) — the AES's own resource, the one they name."""
    return fmlib.string_at(rs.model_get_addr(BASE_IMAGE, rs.R_STRING, number))


# ---- fm_alert's default button, keys and clicks -----------------------------------------------------------------------
THREE = application("three buttons")


def interrupted(name, values, machine, waits, **kwargs):
    return aes_event.interrupted(name, values, machine, Waits(waits), objects=True, **kwargs)


@pytest.mark.parametrize("default", (1, 2, 3), ids=("the first the default", "the second", "the third"))
def test_return_answers_the_default_button(default):
    assert alert(default, STRING_AT, answered(RETURN, onto=THREE)).answer() == default


# NO BUTTON THE DEFAULT, by the default asked for: the button the user then clicks, and the row's label.
NO_DEFAULT = {
    0: (2, "no button the default: Return taken, the next wait blocked; the second button clicked while it waits"),
    4: (3, "a default past the three buttons: Return taken, the next wait blocked; the third clicked while it waits"),
}


def _three_buttons():
    return merge_pokes(running(), THREE)


def no_default_then_clicked(default):
    """fm_alert with no button DEFAULT: Return, taken at the first wait, ends nothing and the next wait BLOCKS; the
    user then clicks a button WHILE IT WAITS — the press wakes fm_do's wait, the watch of the button blocks in its
    turn (the button still down, the mouse on it), and the rise ends the alert on that button."""
    number, label = NO_DEFAULT[default]
    values = (default, STRING_AT)
    clicked = (move_to(*button_middle(number, values=values)), press)
    return aes_event.woken_row(label, ALERT, values, _three_buttons, {0: clicked, 1: release}, Waits({0: key(RETURN)}),
                               objects=True)


@pytest.mark.parametrize("default", NO_DEFAULT, ids=("no default", "a default past the three buttons"))
def test_return_with_no_default_button_waits_as_the_rom_s_and_a_click_then_answers(default):
    """No button DEFAULT — none asked for, or one past the last button, where find_obj's walk (by index, to the LASTOB
    fm_build puts on the last button) never reaches: Return is taken and the next wait blocks. The default past the
    buttons is set on object 10, which is AES tree 2's root (the trees lie end to end): the ROM marks THAT DEFAULT.
    Up to the wait that blocks the C is the ROM's run where it blocks (the whole image at dsptch, every frame
    handed) — AND ON THROUGH THE WAKES (`aes_event.blocked_then_woken`): a button clicked while the alert waits
    answers it, the C through the host's model held to the ROM's own run through its dispatcher."""
    held, ran = aes_event.blocked_then_woken(no_default_then_clicked(default))
    waited = [call.routine for call in held.calls].count(addrs.AES_ROM_EV_MULTI)
    assert held.calls[-1].routine == addrs.AES_ROM_EV_MULTI and waited == 2, "Return taken at the first wait: the SECOND blocks"
    assert ran.answer == NO_DEFAULT[default][0]
    assert set(ran.entered) == {ran.delivered.process} and ran.delivered.idles == len(ran.delivered.at_idles) == 2


# A NEGATIVE DEFAULT. fm_alert checks no `def`: an application's form_alert(-1, ...) sets DEFAULT on object 5 (def + 6),
# a MESSAGE LINE, and fm_build resets only the buttons' flags — so the bit stays on the AES's shared alert tree. From
# then on Return in ANY alert ends on that line (find_obj walks by index from the root and reaches object 5 before the
# real default button): fm_alert answers 5 - 6 = -1, fm_error 1 (its "first button" answer is not 1), eralert 1. The
# machine is the ROM's own run of that form_alert, Return answering it. A later alert with FEWER lines (object 5 not
# linked under its root) then waits on Return for good — ob_change of the unlinked line never returns, on both sides.
NEGATIVE_DEFAULT = -1
FOUR_LINES = {STRING_AT: b"[1][Line one|Line two|Line three|Line four][ OK ]\0"}
CANCEL_DEFAULT_ERROR = 3                # eralert's error 3: Cancel, its first button, the default (answers 0)


def test_a_negative_default_ends_the_alert_on_a_message_line():
    assert alert(NEGATIVE_DEFAULT, STRING_AT, answered(RETURN, onto=FOUR_LINES)).answer() == NEGATIVE_DEFAULT


@functools.cache
def after_a_negative_default():
    """What the ROM's own form_alert(-1, four lines), Return answering it, leaves — and Return in the ring again."""
    machine = answered(RETURN, onto=FOUR_LINES)
    written, _final, _regs = aes_event.derived(addrs.AES_ROM_FM_ALERT, machine,
                                               frame=aes_event.frame_of(("w", NEGATIVE_DEFAULT), ("l", STRING_AT)))
    after = merge_pokes(machine, written)
    return aes_event.typed_ahead(after, RETURN)


def test_a_negative_default_leaves_a_message_line_default():
    line = NEGATIVE_DEFAULT + FIRST_BUTTON - 1
    assert aes.read_object(make_image(after_a_negative_default()), ALERT_TREE, line)["FLAGS"] & fmlib.DEFAULT


def test_after_a_negative_default_fm_error_answers_1():
    assert door_run(ERROR, (FM["DOS_FILE_NOT_FOUND"],), after_a_negative_default()).answer() == 1


def test_after_a_negative_default_eralert_answers_1():
    """...where the same machine without that line's DEFAULT answers 0 (Cancel, the default)."""
    assert eralert_level(CANCEL_DEFAULT_ERROR) == 1
    assert door_run(ERALERT, (CANCEL_DEFAULT_ERROR, 0), after_a_negative_default()).answer() == 1


# ICONS PAST THE AES's THREE: fm_alert's rs_gaddr(R_BITBLK, icon - 1) is unchecked — an application's "[4]".."[9]", and
# "[:]", reach whatever BITBLKs the resource holds past the three.
@pytest.mark.parametrize("digit", "4569:")
def test_an_icon_past_the_three(digit):
    onto = {STRING_AT: b"[" + digit.encode() + b"][An icon past three.][ OK ]\0"}
    assert alert(1, STRING_AT, answered(RETURN, onto=onto)).answer() == 1


def laid_out(name, values, machine):
    """The alert tree as the ROM's own `name` lays it out and centres it — read at its first wait (fm_do's ev_multi),
    where the run blocks with nothing delivered: ONE watched run."""
    calls, memory, returned = aes_event.rom_watched(name, values, machine, blocks=True)
    assert not returned and calls[-1].routine == addrs.AES_ROM_EV_MULTI
    return {ALERT_TREE: bytes(memory[ALERT_TREE:ALERT_TREE + OBJECTS * aes.OB_BYTES])}


def button_middle(number, name=ALERT, values=(1, STRING_AT), machine=None):
    """The middle of button `number` (1 for the first) as the alert shows it — over the three-button application's
    alert by default."""
    machine = machine or merge_pokes(running(), THREE)
    return fmdo.middle_of(ALERT_TREE, FIRST_BUTTON + number - 1, merge_pokes(machine, laid_out(name, values, machine)))


@pytest.mark.parametrize("number", (1, 2, 3), ids=("the first clicked", "the second", "the third"))
def test_a_button_clicked_answers_it(number):
    taken = interrupted(ALERT, (1, STRING_AT), merge_pokes(running(), THREE),
                        {0: (move_to(*button_middle(number)), press), 1: release})
    assert taken.answer == number


def test_with_no_default_button_a_click_answers():
    """No DEFAULT asked for: the alert is ended by a click alone."""
    taken = interrupted(ALERT, (0, STRING_AT), merge_pokes(running(), THREE),
                        {0: (move_to(*button_middle(2, values=(0, STRING_AT))), press), 1: release})
    assert taken.answer == 2


def test_a_key_no_move_takes_is_typed_into_no_field_then_return():
    """'a' typed into an alert, which has no field: fm_keybd leaves it and fm_do hands it to ob_edit as a key for
    object 0 — the root, whose spec is no TEDINFO — with ob_edit's index word never set; then Return."""
    taken = interrupted(ALERT, (1, STRING_AT), merge_pokes(running(), THREE),
                        {0: key(aes_event.scancode_of("a")), 1: key(RETURN)})
    assert taken.answer == 1


def test_tab_moves_to_no_field_then_return():
    taken = interrupted(ALERT, (1, STRING_AT), merge_pokes(running(), THREE), {0: key(fmdo.TAB), 1: key(RETURN)})
    assert taken.answer == 1


def test_a_click_off_the_alert_rings_the_bell_then_return():
    taken = interrupted(ALERT, (1, STRING_AT), merge_pokes(running(), THREE, fmdo.BELL_MACHINE),
                        {0: (move_to(0, 0), press), 1: (release, key(RETURN))})
    assert taken.answer == 1


@THROUGH
def test_fm_alert_through_its_callers_word(through_line_f):
    alert(1, ALERTS["AES string 19"], answered(RETURN), through_line_f=through_line_f)


def test_fm_alert_puts_the_string_on_the_bus():
    assert alert(2, STRING_AT | aes.BUS_TAG, answered(RETURN, onto=THREE)).answer() == 2


def eralert_entry(table, error):
    """Row `error` of one of eralert's two ROM tables (`aes/fmdo.h`)."""
    return case.word_in(BASE_IMAGE, FM[table] + error * aes.WORD_BYTES)


def eralert_level(error):
    """eralert's default button for `error`, 1 for the first."""
    return eralert_entry("AES_ERALERT_LEVELS", error) & FM["ERALERT_LEVEL_MASK"]


# ---- fm_show: an AES string, merged when it is handed values ---------------------------------------------------------
# A merge_str argument list (a longword per %S, a word per %W) in the blocks band past an application's string, and the
# name a %S points at past it.
VALUES_AT = fmlib.STRING_AT + fmlib.STRING_BYTES
VALUES_BYTES = 8
DRIVE_NAME_AT = VALUES_AT + VALUES_BYTES
BAD_FUNCTION_STRING = 27                # the dispatcher's default arm's alert ($fe64ac move.l #$1b0000)
INSERT_DISK_ERROR = 6                   # eralert's last error, "insert a disk" (`aes/fmdo.h`)...
INSERT_DISK_STRING = eralert_entry("AES_ERALERT_STRINGS", INSERT_DISK_ERROR)   # ...and its string, "%S"
FILE_NOT_FOUND_ERROR = -33              # GEMDOS EFILNF: an error word as a %W shows it, unsigned
SHOWN = {
    "Bad Function #, no values (an unimplemented call's)": (BAD_FUNCTION_STRING, 0, None),
    "TOS error #%W, a word": (FM["FM_ERROR_TOS_ERROR"], VALUES_AT, {VALUES_AT: vdi.pack_words(FILE_NOT_FOUND_ERROR)}),
    "insert disk %S, a name": (INSERT_DISK_STRING, VALUES_AT, {VALUES_AT: DRIVE_NAME_AT.to_bytes(aes.LONG_BYTES, "big"),
                                                          DRIVE_NAME_AT: b"B\0"}),
}


@pytest.mark.parametrize("string, values, pokes", SHOWN.values(), ids=SHOWN)
def test_fm_show(string, values, pokes):
    assert door_run(SHOW, (string, values, 1), answered(RETURN, onto=pokes)).answer() == 1


@THROUGH
def test_fm_show_through_its_callers_word(through_line_f):
    door_run(SHOW, (BAD_FUNCTION_STRING, 0, 1), answered(RETURN), through_line_f=through_line_f)


def test_fm_show_puts_its_values_on_the_bus():
    _string, values, pokes = SHOWN["insert disk %S, a name"]
    door_run(SHOW, (INSERT_DISK_STRING, values | aes.BUS_TAG, 1), answered(RETURN, onto=pokes))


# ---- eralert: the critical error handler's seven errors ----------------------------------------------------------------
ERALERT_ERRORS = FM["ERALERT_ERRORS"]


@pytest.mark.parametrize("drive", (0, 1), ids=("drive A", "drive B"))
@pytest.mark.parametrize("error", range(ERALERT_ERRORS))
def test_eralert(error, drive):
    """Return: the error's default — Retry (the second) for those that offer it, answered 1; the first, answered 0. The
    alert's text its string's, the drive's letter merged where it names the drive."""
    level = eralert_entry("AES_ERALERT_LEVELS", error)
    result = door_run(ERALERT, (error, drive), answered(RETURN))
    assert result.answer() == (0 if eralert_level(error) == 1 else 1)
    lines, _buttons = fmlib.sections(aes_string(eralert_entry("AES_ERALERT_STRINGS", error)))
    if level & FM["ERALERT_NAMES_DRIVE"]:
        lines = [line.replace(b"%S", bytes([FM["ERALERT_DRIVE_LETTER"] + drive])) for line in lines]
    assert shown_lines(result, len(lines)) == lines


def test_eralert_s_first_button_clicked_answers_0():
    """Cancel, the first of a Retry alert's buttons, clicked: 0, the error taken as it is."""
    cancel = button_middle(1, ERALERT, (0, 0), running())
    taken = interrupted(ERALERT, (0, 0), running(), {0: (move_to(*cancel), press), 1: release})
    assert taken.answer == 0


@THROUGH
def test_eralert_through_its_callers_word(through_line_f):
    door_run(ERALERT, (1, 0), answered(RETURN), through_line_f=through_line_f)


# ---- fm_error: every code it maps, and every other ---------------------------------------------------------------------
# (code: its string): the MS-DOS errors GEM was written against (`aes/fmdo.h`'s DOS_*) — and the codes between them,
# past them, below them, each "TOS error #%W".
ERROR_STRINGS = {
    **{code: FM["FM_ERROR_TOS_ERROR"] for code in (0, 1, 6, 7, 9, 12, 13, 14, 16, 17, 19, FM["FM_ERROR_LAST_CODE"], -1,
                                                   -32768)},
    **{FM[code]: FM["FM_ERROR_NOT_FOUND"] for code in ("DOS_FILE_NOT_FOUND", "DOS_PATH_NOT_FOUND", "DOS_NO_MORE_FILES")},
    **{FM[code]: FM["FM_ERROR_NO_MEMORY"] for code in ("DOS_NO_MEMORY", "DOS_BAD_ENVIRONMENT", "DOS_BAD_FORMAT")},
    FM["DOS_NO_HANDLES"]: FM["FM_ERROR_NO_HANDLES"], FM["DOS_ACCESS_DENIED"]: FM["FM_ERROR_DENIED"],
    FM["DOS_BAD_DRIVE"]: FM["FM_ERROR_NO_DRIVE"],
}


@pytest.mark.parametrize("code", ERROR_STRINGS, ids=[f"code {code}" for code in ERROR_STRINGS])
def test_fm_error(code):
    """Return: every one of these alerts' first button is its default — answered 0; the alert's first line its
    string's (the TOS error's with the code merged in)."""
    result = door_run(ERROR, (code,), answered(RETURN))
    assert result.answer() == 0
    lines, _buttons = fmlib.sections(aes_string(ERROR_STRINGS[code]))
    if ERROR_STRINGS[code] == FM["FM_ERROR_TOS_ERROR"]:      # merge_str's %W: the word UNSIGNED (-1 is #65535)
        lines = [line.replace(b"%W", str(code & 0xFFFF).encode()) for line in lines]
    assert shown_lines(result, len(lines)) == lines


PAST_THE_LAST = FM["FM_ERROR_LAST_CODE"] + 1


@pytest.mark.parametrize("code", (PAST_THE_LAST, 99, 0x7FFF), ids=("64", "99", "$7fff"))
def test_fm_error_past_63_shows_nothing(code):
    result = door_run(ERROR, (code,), running())
    assert result.answer() == 0 and aes.stored_nothing(result)


@THROUGH
def test_fm_error_through_its_callers_word(through_line_f):
    door_run(ERROR, (2,), answered(RETURN), through_line_f=through_line_f)


# ---- the registry: Tier 3's rows (each routine's worst realistic shape measured, `make bench`) ------------------------
def register(label, name, values, pokes):
    aes_event.register(label, name, values, pokes, drawing=True, objects=fmdo.JUST_DRAW)


def _register_rows():
    longest = max(ALERTS, key=lambda name: len(fmlib.string_at(ALERTS[name])))
    shortest = min(ALERTS, key=lambda name: len(fmlib.string_at(ALERTS[name])))
    register(f"the longest alert ({longest}), Return", ALERT, (1, ALERTS[longest]), answered(RETURN))
    register(f"the shortest alert ({shortest}), Return", ALERT, (1, ALERTS[shortest]), answered(RETURN))
    for name in APPLICATION_ALERTS:
        register(f"an application's: {name}, Return", ALERT, (button_count(name), STRING_AT),
                 answered(RETURN, onto=application(name)))
    aes_event.register_interrupted("the third of three buttons clicked", ALERT, (1, STRING_AT),
                                   merge_pokes(running(), THREE),
                                   Waits({0: (move_to(*button_middle(3)), press), 1: release}), objects=True)
    aes_event.register_interrupted("the documented maximum, the cursor shown, Return typed", ALERT,
                                   (len(LONGEST_BUTTONS), STRING_AT),
                                   merge_pokes(running(shown=True), {STRING_AT: MAXIMUM_ALERT + b"\0"}),
                                   aes_event.typed(RETURN), objects=True)
    # ...and THE ROWS THAT SWITCH: the wait no default leaves blocked, woken by a click (two waits blocked in turn).
    for default in NO_DEFAULT:
        aes_event.register_woken(no_default_then_clicked(default))
    for label, (string, values, pokes) in SHOWN.items():
        register(label, SHOW, (string, values, 1), answered(RETURN, onto=pokes))
    for error in range(ERALERT_ERRORS):
        register(f"error {error}, Return", ERALERT, (error, 0), answered(RETURN))
    for code in (*(FM[name] for name in ("DOS_FILE_NOT_FOUND", "DOS_NO_HANDLES", "DOS_ACCESS_DENIED", "DOS_NO_MEMORY",
                                          "DOS_BAD_DRIVE")), 0, -1):
        register(f"code {code}, Return", ERROR, (code,), answered(RETURN))
    register(f"code {PAST_THE_LAST}: nothing shown", ERROR, (PAST_THE_LAST,), running())


_register_rows()
