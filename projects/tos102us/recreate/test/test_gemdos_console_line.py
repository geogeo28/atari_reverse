"""GEMDOS Cconrs ($0a) — the line editor, and every editing key TOS 1.02 really implements.

THE KEY SET IS TWO NINE-ENTRY TABLES IN THE ROM and not a `cmp`-chain anyone can add to: the codes
at `GEMDOS_LINE_EDITOR_KEYS` are searched with `cmp.l (a0)+` under a `dbeq`, and the arm is read at
`32(a0)` from wherever that search stopped. `test_the_rom_s_own_key_table_is_the_set_this_file_drives`
reads both tables out of the mapped ROM, so a key this file did not drive would be a red rather than
a silence. What is there:

    ^C    end the process (`Pterm(-32)`) — the one arm this wave does not reconstruct
    BS    rub out the last character... and so does DEL
    LF    end the line — and so does CR; ONE carriage return is echoed, and no line feed
    ^R    print `#`, start a fresh indented line, and RETYPE what has been entered
    ^U    print `#`, start a fresh indented line, and FORGET it
    ^X    rub the whole line out, one character at a time
    0     the table's ninth entry, whose arm IS the default arm

THAT NINTH ENTRY IS THE FINDING. "Matched the ninth" and "matched nothing" leave A0 in the same
place, so they take the same branch — which means a key whose ASCII half is 0 (a cursor key, say) is
an ordinary character, stored as a NUL and echoed as `^@`. The table's zero is what makes the two
answers agree; it is not an arm of its own.

TWO MORE THINGS THE ROM DOES THAT THE MANUAL DOES NOT SAY.

*THE ERASE MEASURES THE LINE, IT DOES NOT COUNT IT.* Rubbing out re-walks the characters before the
one being deleted and adds up how wide each one PRINTS — a TAB to the next multiple of eight, a
control code two columns (`^` and a letter), anything else one — then backspaces until GEMDOS's own
column counter has come back to that width. So one BS after a TAB takes back the whole tab.

*THE MAXIMUM IS AN UNSIGNED BYTE AND THE LINE IS NEVER TERMINATED.* `buffer[0]` is read with
`ext.w` and then masked to a byte; `buffer[1]` is where the length goes back; and nothing writes a
NUL after the characters — the length is the whole of what says where the line ends.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import gemdos
import gemdos_console as console
import iorec
import vt52

START_COLUMN = 3
MAXIMUM = 10                            # ...and how long a line any case here may type
RING = addrs.IOREC_IKBD

# The editing keys, as IKBD records. The scancode half is deliberately NOT 0 on the printable ones:
# `ext.l d0` throws it away before the table search, and a reconstruction that compared the whole
# longword would match nothing and send every key to the default arm.
def key(ascii_code, scancode=0x1E):
    return (scancode << 16) | ascii_code


LETTER_A = key(0x61)
LETTER_B = key(0x62, 0x30)
LETTER_C = key(0x63, 0x2E)
RETURN = key(addrs.CON_CR, 0x1C)
LINE_FEED = key(addrs.CON_LF, 0x1C)
BACKSPACE = key(addrs.CON_BS, 0x0E)
DELETE = key(addrs.CON_DEL, 0x53)
CANCEL = key(addrs.CON_CAN, 0x2D)       # ^X
KILL = key(addrs.CON_NAK, 0x16)         # ^U
RETYPE = key(addrs.CON_DC2, 0x13)       # ^R
CONTROL_A = key(0x01, 0x1E)
TAB = key(addrs.CON_TAB, 0x0F)
NO_ASCII = key(0x00, 0x48)              # a cursor key: the ninth table entry's value


def _buffer(maximum=MAXIMUM):
    """The length-prefixed buffer, with everything but the maximum filled for attribution."""
    return {console.LINE_AT: bytes([maximum]) + bytes([gemdos.FILL]) * (MAXIMUM + 1)}


def _typed(*keys, maximum=MAXIMUM, column=START_COLUMN, row=0):
    """The whole machine for one edited line: the keys already in GEMDOS's typeahead queue.

    A case stages the queue rather than the BIOS's ring because the editor reads through
    `device_get`, which takes the queue first — and because a line is several keys, where the ring
    would also have to survive the echo's own poll of it. The ring is staged EMPTY, so that poll
    finds nothing and the case is about the editor.
    """
    return {**iorec.staged(RING, 0, 0),
            **console.queue(console.DEVICE_CONSOLE, keys),
            **console.column(console.DEVICE_CONSOLE, column),
            **vt52.staged(column, row, cursor_depth=1, extra_flags=vt52.WRAP),
            **_buffer(maximum)}


def _spec(name, *keys, **staging):
    return {"name": f"gemdos_cconrs, {name}", "leaf": console.CCONRS,
            "argument": console.LINE_AT, "pokes": _typed(*keys, **staging)}


# ---- the specs -----------------------------------------------------------------------------------

LINE = _spec("two characters and a return", LETTER_A, LETTER_B, RETURN)
EMPTY_MAXIMUM = _spec("a maximum of zero", RETURN, maximum=0)
FILLED_TO_THE_MAXIMUM = _spec("the buffer's bound", LETTER_A, LETTER_B, LETTER_C, maximum=2)
ENDED_BY_LINE_FEED = _spec("a line feed ends it too", LETTER_A, LINE_FEED)
BACKSPACED = _spec("a backspace", LETTER_A, LETTER_B, BACKSPACE, RETURN)
DELETED = _spec("DEL, which is the same arm", LETTER_A, LETTER_B, DELETE, RETURN)
BACKSPACE_ON_AN_EMPTY_LINE = _spec("a backspace with nothing to rub out", BACKSPACE, RETURN)
CANCELLED = _spec("^X rubs the whole line out", LETTER_A, LETTER_B, CANCEL, RETURN)
KILLED = _spec("^U forgets it", LETTER_A, LETTER_B, KILL, RETURN)
RETYPED = _spec("^R redraws it", LETTER_A, LETTER_B, RETYPE, RETURN)
CONTROL_CHARACTER = _spec("a control character, echoed as ^ and a letter", CONTROL_A, RETURN)
# THE ERASE MEASURES THE CHARACTERS BEFORE THE ONE IT DELETES, so a line one character long never
# runs its width walk at all — which is how the first version of these two cases came to be green
# over a mutated width table. Both type a SECOND character and rub THAT one out, so the walk runs
# over the first; and both end by reaching the maximum rather than with a RETURN, so the column
# counter this file reads back is the one the erase left rather than the 0 a CR would write.
CONTROL_CHARACTER_ERASED = _spec("a control character rubbed out from BEHIND, which takes two "
                                 "columns back", CONTROL_A, LETTER_B, BACKSPACE, LETTER_C, LETTER_A,
                                 maximum=3)
TAB_ERASED = _spec("a TAB rubbed out from behind, which takes the whole tab back",
                   TAB, LETTER_B, BACKSPACE, LETTER_C, LETTER_A, maximum=3)

# What the counter must stand at when each of those lines ends, worked from the ROM's own width
# table: the start column, plus the width of what is still on the screen.
CONTROL_ECHO_WIDTH = addrs.CON_CONTROL_WIDTH        # `^` and a letter
AFTER_CONTROL_ERASE = START_COLUMN + CONTROL_ECHO_WIDTH + 2      # ^A, then 'c' and 'a'
AFTER_TAB_ERASE = addrs.CON_TAB_WIDTH + 2                        # the tab stop, then 'c' and 'a'
KEY_WITH_NO_ASCII = _spec("a key whose ASCII half is 0", NO_ASCII, RETURN)
KILLED_FROM_COLUMN_ZERO = _spec("^U from the first column", LETTER_A, KILL, RETURN, column=0)

REGISTERED = (LINE, EMPTY_MAXIMUM, FILLED_TO_THE_MAXIMUM, ENDED_BY_LINE_FEED, BACKSPACED, DELETED,
              BACKSPACE_ON_AN_EMPTY_LINE, CANCELLED, KILLED, RETYPED, CONTROL_CHARACTER,
              CONTROL_CHARACTER_ERASED, TAB_ERASED, KEY_WITH_NO_ASCII, KILLED_FROM_COLUMN_ZERO)
VERIFIED_CASES = tuple(console.registered(spec) for spec in REGISTERED)


def _line(info):
    """`(length, characters)` as the run left them in the caller's buffer."""
    final = info["final"]
    length = final[console.LINE_AT + addrs.GEMDOS_CCONRS_LENGTH]
    text = console.LINE_AT + addrs.GEMDOS_CCONRS_TEXT
    return length, bytes(final[text:text + length])


def _column(info):
    at = console.column_slot(console.DEVICE_CONSOLE)
    return int.from_bytes(bytes(info["final"][at:at + 2]), "big")


# ---- the ROM's own tables ------------------------------------------------------------------------

def test_the_rom_s_own_key_table_is_the_set_this_file_drives():
    """Read out of the mapped ROM, not written down: a key the ROM handles and this file does not
    drive would be a red here, which is the only thing that can say the set is complete."""
    keys = [int.from_bytes(bytes(BASE_IMAGE[addrs.GEMDOS_LINE_EDITOR_KEYS + 4 * index:
                                            addrs.GEMDOS_LINE_EDITOR_KEYS + 4 * index + 4]), "big")
            for index in range(addrs.GEMDOS_LINE_EDITOR_KEY_COUNT)]
    assert keys == [addrs.CON_ETX, addrs.CON_BS, addrs.CON_LF, addrs.CON_CR, addrs.CON_DC2,
                    addrs.CON_NAK, addrs.CON_CAN, addrs.CON_DEL, 0]


def test_the_ninth_arm_is_the_default_arm():
    """THE FINDING, as the two tables hold it: the entry the search falls off the end at and the
    entry for the key 0 are the SAME arm address, so "no match" and "matched 0" are one branch."""
    arms = [int.from_bytes(bytes(BASE_IMAGE[addrs.GEMDOS_LINE_EDITOR_ARMS + 4 * index:
                                            addrs.GEMDOS_LINE_EDITOR_ARMS + 4 * index + 4]), "big")
            for index in range(addrs.GEMDOS_LINE_EDITOR_KEY_COUNT)]
    assert arms[-1] not in arms[:-1], "the default arm is one of the eight keyed ones"
    assert arms[1] == arms[7], "BS and DEL are not the same arm"
    assert arms[2] == arms[3], "LF and CR are not the same arm"


# ---- the ordinary line ---------------------------------------------------------------------------

def test_a_line_comes_back_length_prefixed_and_unterminated():
    info = console.run(LINE)
    assert _line(info) == (2, b"ab")
    assert info["final"][console.LINE_AT + addrs.GEMDOS_CCONRS_TEXT + 2] == gemdos.FILL, (
        "something was written past the line, so the buffer is terminated after all")


def test_the_result_is_the_length_in_d0s_low_word_and_the_high_half_is_never_written():
    """`move.w d5,d0` is the WHOLE of the answer, so what is above it is whatever the editor's last
    call left — and on a line that made no call at all, the CALLER'S OWN high half. That second
    half is why `entry_d0` is an argument; the first is why a battery cannot simply assert it.
    `move.b d0,1(a5)` puts the same number in the buffer, which is the half a program reads."""
    assert console.run(EMPTY_MAXIMUM)["regs"]["d0"] == console.MARKED_D0 & 0xFFFF0000
    assert console.run(LINE)["regs"]["d0"] & 0xFFFF == 2


def test_a_maximum_of_zero_reads_nothing_at_all():
    """The test is made BEFORE the first read, so an empty buffer costs no keystroke — and the key
    staged in the queue is still there afterwards."""
    info = console.run(EMPTY_MAXIMUM)
    assert _line(info) == (0, b"")
    assert console.queue_state(info["final"], console.DEVICE_CONSOLE)[0] == 1, (
        "Cconrs consumed a key for a line it had no room for")


def test_the_line_stops_at_the_maximum_without_a_return():
    """...and the key that did not fit stays in the queue for the next call."""
    info = console.run(FILLED_TO_THE_MAXIMUM)
    assert _line(info) == (2, b"ab")
    assert console.queue_state(info["final"], console.DEVICE_CONSOLE)[0] == 1


def test_a_line_feed_ends_the_line_exactly_as_a_return_does():
    assert _line(console.run(ENDED_BY_LINE_FEED)) == (1, b"a")


def test_the_end_echoes_one_carriage_return_and_no_line_feed():
    """`device_put(CR)` and nothing else: GEMDOS's counter is zeroed and the CONSOLE'S CURSOR is
    still on the row the line was typed on. Moving to the next line is the caller's business, which
    is why every TOS prompt sends its own line feed."""
    info = console.run(LINE)
    assert _column(info) == 0
    assert int.from_bytes(bytes(info["final"][addrs.CON_CURSOR_ROW:addrs.CON_CURSOR_ROW + 2]),
                          "big") == 0


# ---- rubbing out ---------------------------------------------------------------------------------

@pytest.mark.parametrize("spec", (BACKSPACED, DELETED))
def test_backspace_and_delete_are_one_arm(spec):
    """Both drop the last character and leave the column where it was before it — the erase is
    `BS`, a space and `BS` until GEMDOS's counter has come back."""
    info = console.run(spec)
    assert _line(info) == (1, b"a")


def test_a_backspace_on_an_empty_line_rubs_out_nothing():
    """`if (length != 0) length--` — a zero length stays zero, the measured width is the start
    column, and the loop that backspaces never runs."""
    info = console.run(BACKSPACE_ON_AN_EMPTY_LINE)
    assert _line(info) == (0, b"")


def test_cancel_rubs_out_every_character_one_at_a_time():
    """^X is the erase in a do-while, so the screen ends BLANK rather than redrawn — and the column
    comes back to where the line began before the closing return zeroes it."""
    assert _line(console.run(CANCELLED)) == (0, b"")


def test_kill_forgets_the_line_and_starts_a_fresh_indented_one():
    """^U prints `#`, then CR, LF and as many spaces as the line began indented — so the counter is
    back at the start column and the characters are simply not counted any more."""
    info = console.run(KILLED)
    assert _line(info) == (0, b"")
    assert info["final"][console.LINE_AT + addrs.GEMDOS_CCONRS_TEXT] == ord("a"), (
        "^U rubbed the buffer out; the ROM only forgets the COUNT")


def test_kill_from_the_first_column_indents_by_nothing():
    """The indent is the column the line BEGAN in, read once at entry — so a prompt-less line gets
    no spaces at all, and a reconstruction that used the current column would indent by two."""
    assert _line(console.run(KILLED_FROM_COLUMN_ZERO)) == (0, b"")


def test_retype_redraws_what_has_been_entered_and_keeps_it():
    """^R is ^U's redraw with the characters echoed back onto the new line — through the echoing
    put, so a control character in the line reappears as `^` and a letter."""
    info = console.run(RETYPED)
    assert _line(info) == (2, b"ab")


# ---- the two widths a character can have -----------------------------------------------------------

def test_a_control_character_is_stored_raw_and_echoed_as_a_caret_and_a_letter():
    info = console.run(CONTROL_CHARACTER)
    assert _line(info) == (1, bytes([0x01]))
    assert _column(info) == 0, "the closing return should have zeroed the counter"


def test_rubbing_out_the_character_after_a_control_code_measures_it_at_two_columns():
    """The erase's width table: a code `< 32` occupies two columns, because that is what the echo
    printed. The walk covers the ^A that is STILL on the line, so the counter must come back to the
    start column plus two — and a width of one would leave it one column short and backspace twice."""
    info = console.run(CONTROL_CHARACTER_ERASED)
    assert _line(info) == (3, bytes([0x01, ord("c"), ord("a")]))
    assert _column(info) == AFTER_CONTROL_ERASE


def test_rubbing_out_the_character_after_a_tab_measures_the_whole_tab():
    """`(column + 8) & ~7` in the width walk, against the counter the expansion really left: from
    column 3 the TAB printed five spaces to column 8, and the erase must measure it back to 8 —
    dropping the mask would measure it to 11, past where the cursor is, and rub out nothing."""
    info = console.run(TAB_ERASED)
    assert _line(info) == (3, bytes([addrs.CON_TAB, ord("c"), ord("a")]))
    assert _column(info) == AFTER_TAB_ERASE


def test_a_key_with_no_ascii_half_is_an_ordinary_character():
    """The ninth table entry's own case: stored as a NUL and echoed as `^@`, because its arm is the
    default arm."""
    info = console.run(KEY_WITH_NO_ASCII)
    assert _line(info) == (1, b"\0")


# ---- what is not reconstructed --------------------------------------------------------------------

def test_the_control_c_arm_is_the_only_key_this_wave_does_not_reconstruct():
    """Said as a test so that the halt is a recorded fact rather than a note: ^C's arm is
    `Pterm(-32)` ($fc8028), the process-termination group, and nothing here enters it. What this
    checks is that the ROM's own table still routes ^C there — a future wave that reconstructs
    `Pterm` has this case to delete."""
    arm = int.from_bytes(bytes(BASE_IMAGE[addrs.GEMDOS_LINE_EDITOR_ARMS:
                                          addrs.GEMDOS_LINE_EDITOR_ARMS + 4]), "big")
    pterm_call = bytes([0x4E, 0xB9]) + struct.pack(">I", addrs.GEMDOS_PTERM)
    assert bytes(BASE_IMAGE[arm + 4:arm + 4 + len(pterm_call)]) == pterm_call, (
        "^C's arm no longer calls Pterm, so the halt in src/gemdos/console.c names the wrong reason")
