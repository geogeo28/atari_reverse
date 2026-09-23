"""TOS's KEYBOARD @ $fc2b5c and $fc2c42 — the shift machine, and a scancode into the IKBD IOREC.

`test_bios_acia_service.py` proves the byte gets here; this proves what happens to it. Both routines
are entered with the registers their callers leave — the scancode in D0, the IOREC in A0 — because
each has two callers that set them up for themselves: `acia_take_byte` for a key the 6301 sent, and
TIMER C's auto-repeat for one it is repeating.

THE ASCII IS NEVER WRITTEN DOWN HERE. Every expectation reads the byte out of the `Keytbl` table the
snapshot's own pointers name, which is what makes these cases claims about the ROM's INDEXING rather
than a second copy of its three 128-byte tables.

WHAT IS NOT IN THE RING. Three of the ALTERNATE arms queue nothing at all — ALT+Help bumps `_dumpflg`
and the mouse-emulation keys call `mousevec` — so a case for one of those asserts an EMPTY ring as
well as its own effect, or a reconstruction that also queued would pass.
"""
import struct

import pytest

import acia
import case
import iorec
import isr
from harness import BASE_IMAGE, addrs

RING = addrs.IOREC_IKBD
RING_BUFFER = iorec.buffer_of(RING)
RING_BYTES = iorec.size_of(RING)
RECORD = addrs.IOREC_KEY_BYTES

# The IKBD's own table pointers, as the captured machine holds them: the three ROM tables `Bioskeys`
# installs. Read rather than assumed, so a capture whose `Keytbl` had been replaced fails loudly.
TABLE_AT = {field: isr.long_in_snapshot(addrs.KEYTBL_STRUCT + field)
            for field in (addrs.KEYTBL_FIELD_UNSHIFTED, addrs.KEYTBL_FIELD_SHIFTED,
                          addrs.KEYTBL_FIELD_CAPSLOCK)}


def ascii_of(scancode, field=addrs.KEYTBL_FIELD_UNSHIFTED):
    """What one of the three tables gives for a scancode, out of the image the case runs over."""
    return BASE_IMAGE[TABLE_AT[field] + (scancode & addrs.SCANCODE_INDEX_MASK)]


def scancode_glue(routine, scancode):
    def glue(lib, buf):
        getattr(lib, routine)(buf, scancode, RING)
    return glue


def spec(name, entry, scancode, *, pokes=None, io_seed=None, vectors=None, routines=None,
         kbshift=0, conterm=None, head=0, tail=0):
    """ONE case of this battery, in `test/acia.py`'s spec vocabulary.

    `kbshift` and `conterm` are the two bytes every arm here branches on, so they are named
    arguments rather than pokes: a case that left either at whatever the capture holds would be
    describing one machine's idle desktop instead of the state it means.

    Both routines are entered with the registers their callers leave — the scancode in D0, the IOREC
    in A0 — and our C takes the same two as parameters, so the glue and the registers are built here
    together (`bench/tier3.py`'s `ENTRY_D0`/`ENTRY_A0` read them back off the row).
    """
    routine = "kbd_scancode" if entry == addrs.KBD_SCANCODE else "kbd_queue_key"
    staged = {**iorec.staged(RING, head, tail), addrs.KBSHIFT: bytes([kbshift]), **(pokes or {})}
    if conterm is not None:
        staged[addrs.SYSVAR_CONTERM] = bytes([conterm])
    return {"name": name, "entry": entry, "glue": scancode_glue(routine, scancode),
            "regs": {"d0": scancode, "a0": RING}, "pokes": staged, "io_seed": io_seed,
            "vectors": vectors or {}, "routines": routines or {}}


def run(entry, scancode, *, poison=True, **staging):
    """...and the differential of one, over the staged image `test/acia.py` builds for the chain."""
    return acia.run_spec(spec("", entry, scancode, **staging), poison=poison)


def record_at(info, offset=RECORD):
    """The four-byte record the run left in the ring, out of the ORACLE's write ledger."""
    return case.written(info, RING_BUFFER + offset, RECORD)


def expected_record(scancode, ascii_byte, kbshift=0):
    """kbshift, scancode, a zero, ASCII — the record's own layout (`include/keyboard.h`)."""
    return (kbshift << 24) | ((scancode & 0xFF) << 16) | ascii_byte


def nothing_queued(info):
    """Did the run leave the ring and its tail alone?"""
    return not any(RING_BUFFER <= at < RING_BUFFER + RING_BYTES for at in info["writes"]) \
        and RING + addrs.IOREC_TAIL not in info["writes"]


# ---- the nine modifier arms ----------------------------------------------------------------------
# Each is a `cmpi.b` and a `bset`/`bclr` on a COPY of kbshift that is stored back at the end, so a
# modifier key never reaches the key path and never touches the ring.

MODIFIERS = (
    (addrs.SCANCODE_LEFT_SHIFT, addrs.KBSHIFT_LEFT_SHIFT_BIT, True),
    (addrs.SCANCODE_LEFT_SHIFT | addrs.SCANCODE_RELEASE, addrs.KBSHIFT_LEFT_SHIFT_BIT, False),
    (addrs.SCANCODE_RIGHT_SHIFT, addrs.KBSHIFT_RIGHT_SHIFT_BIT, True),
    (addrs.SCANCODE_RIGHT_SHIFT | addrs.SCANCODE_RELEASE, addrs.KBSHIFT_RIGHT_SHIFT_BIT, False),
    (addrs.SCANCODE_CONTROL, addrs.KBSHIFT_CONTROL_BIT, True),
    (addrs.SCANCODE_CONTROL | addrs.SCANCODE_RELEASE, addrs.KBSHIFT_CONTROL_BIT, False),
    (addrs.SCANCODE_ALTERNATE, addrs.KBSHIFT_ALTERNATE_BIT, True),
    (addrs.SCANCODE_ALTERNATE | addrs.SCANCODE_RELEASE, addrs.KBSHIFT_ALTERNATE_BIT, False),
)
# Every other bit set, so an arm that cleared the byte — or set the wrong bit — diverges.
BUSY_SHIFT = 0xFF


@pytest.mark.parametrize("scancode,bit,sets", MODIFIERS,
                         ids=[f"{code:#04x}" for code, _bit, _sets in MODIFIERS])
@pytest.mark.parametrize("entry_shift", (0x00, BUSY_SHIFT), ids=("from clear", "from every bit"))
def test_a_modifier_key_changes_one_bit_of_kbshift_and_nothing_else(scancode, bit, sets,
                                                                    entry_shift):
    info = run(addrs.KBD_SCANCODE, scancode, kbshift=entry_shift)
    expected = entry_shift | (1 << bit) if sets else entry_shift & ~(1 << bit)
    assert info["writes"].get(addrs.KBSHIFT, entry_shift) == expected
    assert nothing_queued(info)
    assert addrs.SYSVAR_KB_REPEAT_KEY not in info["writes"], (
        "a modifier key must not arm the auto-repeat — the chain returns before it")


@pytest.mark.parametrize("entry_shift", (0x00, 1 << addrs.KBSHIFT_CAPSLOCK_BIT, BUSY_SHIFT))
def test_capslock_toggles_rather_than_setting(entry_shift):
    """`bchg #4,d1`, which is why holding CapsLock down does not lock it on."""
    info = run(addrs.KBD_SCANCODE, addrs.SCANCODE_CAPSLOCK, kbshift=entry_shift)
    assert info["writes"][addrs.KBSHIFT] == entry_shift ^ (1 << addrs.KBSHIFT_CAPSLOCK_BIT)


def test_capslock_is_the_one_modifier_that_clicks():
    """...and it is the same click the key path makes, gated on the same `conterm` bit."""
    clicking = run(addrs.KBD_SCANCODE, addrs.SCANCODE_CAPSLOCK,
                   conterm=1 << addrs.CONTERM_CLICK_BIT)
    assert case.written_long(clicking, addrs.SOUND_LIST_POINTER) == addrs.KEYCLICK_SOUND_LIST
    assert clicking["writes"][addrs.SOUND_LIST_DELAY] == 0
    silent = run(addrs.KBD_SCANCODE, addrs.SCANCODE_CAPSLOCK, conterm=0)
    assert addrs.SOUND_LIST_POINTER not in silent["writes"]


def test_the_capslock_RELEASE_is_not_in_the_chain_at_all():
    """$ba is not one of the nine `cmpi.b`s, so it goes down the key path like any other break —
    which is what makes the CapsLock arm a toggle on the MAKE rather than a press-and-release."""
    info = run(addrs.KBD_SCANCODE, addrs.SCANCODE_CAPSLOCK | addrs.SCANCODE_RELEASE,
               pokes={addrs.SYSVAR_KB_REPEAT_KEY: b"\x01"})
    assert addrs.KBSHIFT not in info["writes"]
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_KEY] == 0, "the break disarmed the auto-repeat"


# ---- the auto-repeat state -----------------------------------------------------------------------

A_KEY = 0x1E                    # `A` — an ordinary letter, in every table and in no arm


def test_a_make_with_no_key_held_arms_the_repeat_from_kbrate_s_own_bytes():
    info = run(addrs.KBD_SCANCODE, A_KEY, pokes={addrs.SYSVAR_KB_REPEAT_KEY: b"\x00"})
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_KEY] == A_KEY
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_DELAY] == BASE_IMAGE[addrs.KBRATE_DELAY]
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_LEFT] == BASE_IMAGE[addrs.KBRATE_REPEAT]


def test_a_second_key_silences_the_first_rather_than_replacing_it():
    """Both countdowns go to zero and the HELD scancode is left alone, so the first key stops
    repeating and the second never starts. A reconstruction that stored the new scancode would be
    indistinguishable on every other case here."""
    held = 0x20
    info = run(addrs.KBD_SCANCODE, A_KEY, pokes={addrs.SYSVAR_KB_REPEAT_KEY: bytes([held, 5, 3])})
    assert addrs.SYSVAR_KB_REPEAT_KEY not in info["writes"]
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_DELAY] == 0
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_LEFT] == 0
    assert record_at(info) == expected_record(A_KEY, ascii_of(A_KEY))


def test_a_break_disarms_the_repeat_and_queues_nothing():
    """The release of a key is not a key. Everything below the disarm is skipped by the two
    `cmpi.b`s that let only $c7 and $d2 through."""
    info = run(addrs.KBD_SCANCODE, A_KEY | addrs.SCANCODE_RELEASE,
               pokes={addrs.SYSVAR_KB_REPEAT_KEY: bytes([A_KEY, 5, 3])})
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_KEY] == 0
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_DELAY] == 0
    assert nothing_queued(info)


@pytest.mark.parametrize("scancode", (addrs.SCANCODE_HOME_BREAK, addrs.SCANCODE_INSERT_BREAK))
def test_the_two_mouse_button_breaks_reach_the_key_path_but_only_under_alt(scancode):
    """The one place a BREAK is a key: ALT+Home and ALT+Insert are the emulated mouse's buttons, and
    a button has to come back up. Without ALT the same two codes return like every other break."""
    with_alt = run(addrs.KBD_SCANCODE, scancode, kbshift=1 << addrs.KBSHIFT_ALTERNATE_BIT,
                   vectors={"mousevec": acia.A0_STUB},
                   routines={acia.A0_STUB: acia.a0_recorder(acia.A0_REPORT)})
    assert case.written(with_alt, acia.A0_REPORT, 4) == addrs.KBD_MOUSE_PACKET
    without = run(addrs.KBD_SCANCODE, scancode, kbshift=0)
    assert nothing_queued(without)
    assert acia.A0_REPORT not in without["writes"]


# ---- the three key tables ------------------------------------------------------------------------

# One scancode per row of the keyboard, so a reconstruction that indexed the wrong table is caught by
# the VALUE rather than by luck: each of these spells something different in all three tables.
TABLE_KEYS = (0x10, 0x1E, 0x2C, 0x02, 0x39)


@pytest.mark.parametrize("scancode", TABLE_KEYS)
@pytest.mark.parametrize("kbshift,field", (
    (0, addrs.KEYTBL_FIELD_UNSHIFTED),
    (1 << addrs.KBSHIFT_LEFT_SHIFT_BIT, addrs.KEYTBL_FIELD_SHIFTED),
    (1 << addrs.KBSHIFT_RIGHT_SHIFT_BIT, addrs.KEYTBL_FIELD_SHIFTED),
    (1 << addrs.KBSHIFT_CAPSLOCK_BIT, addrs.KEYTBL_FIELD_CAPSLOCK),
), ids=("unshifted", "left shift", "right shift", "capslock"))
def test_each_shift_state_reads_its_own_keytbl_table(scancode, kbshift, field):
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=kbshift)
    assert record_at(info) == expected_record(scancode, ascii_of(scancode, field))


@pytest.mark.parametrize("scancode", TABLE_KEYS)
def test_shift_overrides_capslock_rather_than_the_other_way_round(scancode):
    """The ROM picks the CapsLock table first and either shift replaces it, which is why holding
    shift with CapsLock on gives the shifted table and not the capslocked one."""
    both = (1 << addrs.KBSHIFT_CAPSLOCK_BIT) | (1 << addrs.KBSHIFT_LEFT_SHIFT_BIT)
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=both)
    assert record_at(info) == expected_record(scancode,
                                              ascii_of(scancode, addrs.KEYTBL_FIELD_SHIFTED))


FUNCTION_KEYS = tuple(range(addrs.SCANCODE_FUNCTION_FIRST, addrs.SCANCODE_FUNCTION_LAST + 1))


@pytest.mark.parametrize("scancode", FUNCTION_KEYS)
def test_shift_renumbers_the_function_keys_instead_of_reading_a_table(scancode):
    """F1..F10 under shift never reach a table at all: the scancode moves up by ten keys and the
    record carries no ASCII. Every key of the run, so both boundaries are covered."""
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=1 << addrs.KBSHIFT_LEFT_SHIFT_BIT)
    assert record_at(info) == expected_record(scancode + addrs.SCANCODE_FUNCTION_SHIFTED, 0)


@pytest.mark.parametrize("scancode", (addrs.SCANCODE_FUNCTION_FIRST - 1,
                                      addrs.SCANCODE_FUNCTION_LAST + 1))
def test_the_keys_either_side_of_the_function_run_read_the_shifted_table(scancode):
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=1 << addrs.KBSHIFT_LEFT_SHIFT_BIT)
    assert record_at(info) == expected_record(scancode,
                                              ascii_of(scancode, addrs.KEYTBL_FIELD_SHIFTED))


def test_the_function_key_test_is_on_the_MASKED_scancode():
    """`andi.w #127,d0` comes first, so a shifted F-key RELEASE is renumbered too — the record
    carries $bb + 25 rather than the break code the table would have looked up."""
    scancode = addrs.SCANCODE_FUNCTION_FIRST | addrs.SCANCODE_RELEASE
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=1 << addrs.KBSHIFT_LEFT_SHIFT_BIT)
    assert record_at(info) == expected_record(scancode + addrs.SCANCODE_FUNCTION_SHIFTED, 0)


# ---- CONTROL -------------------------------------------------------------------------------------

CONTROL = 1 << addrs.KBSHIFT_CONTROL_BIT


def test_control_masks_the_ascii_to_its_low_five_bits():
    """The default arm: CTRL+A is 1, which is the whole of how a control character is made."""
    info = run(addrs.KBD_QUEUE_KEY, A_KEY, kbshift=CONTROL)
    assert record_at(info) == expected_record(A_KEY, ascii_of(A_KEY) & addrs.CONTROL_MASK)


# The three characters ASCII puts outside the control run, which the ROM names one at a time. The
# scancode of each is found in the unshifted table rather than written down.
def scancode_for(character):
    return BASE_IMAGE[TABLE_AT[addrs.KEYTBL_FIELD_UNSHIFTED]:
                      TABLE_AT[addrs.KEYTBL_FIELD_UNSHIFTED] + 0x80].index(character)


@pytest.mark.parametrize("character,expected", ((addrs.ASCII_DIGIT_TWO, addrs.CONTROL_DIGIT_TWO),
                                                (addrs.ASCII_DIGIT_SIX, addrs.CONTROL_DIGIT_SIX),
                                                (addrs.ASCII_MINUS, addrs.CONTROL_MINUS)))
def test_control_names_the_three_characters_the_mask_would_get_wrong(character, expected):
    scancode = scancode_for(character)
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=CONTROL)
    assert record_at(info) == expected_record(scancode, expected)


def test_control_turns_a_carriage_return_into_a_line_feed():
    """...and it happens BEFORE the three scancode arms, so CTRL+Home carries whatever the table
    gave it rather than what the mask would have made."""
    scancode = scancode_for(addrs.ASCII_CARRIAGE_RETURN)
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=CONTROL)
    assert record_at(info) == expected_record(scancode, addrs.ASCII_LINE_FEED)


@pytest.mark.parametrize("scancode,code,ascii_kept", (
    (addrs.SCANCODE_HOME, addrs.SCANCODE_HOME + addrs.CONTROL_HOME_OFFSET, True),
    (addrs.SCANCODE_CURSOR_LEFT, addrs.CONTROL_CURSOR_LEFT, False),
    (addrs.SCANCODE_CURSOR_RIGHT, addrs.CONTROL_CURSOR_RIGHT, False),
), ids=("home", "left", "right"))
def test_control_renumbers_three_keys_outright(scancode, code, ascii_kept):
    """Home is an ADD and the two horizontal cursor keys are assignments, which is why Home's ASCII
    survives and theirs does not."""
    info = run(addrs.KBD_QUEUE_KEY, scancode, kbshift=CONTROL)
    expected_ascii = ascii_of(scancode) if ascii_kept else 0
    assert record_at(info) == expected_record(code, expected_ascii)


# ---- ALTERNATE -----------------------------------------------------------------------------------

ALTERNATE = 1 << addrs.KBSHIFT_ALTERNATE_BIT
MOUSE_VECTORS = {"mousevec": acia.A0_STUB}
MOUSE_ROUTINES = {acia.A0_STUB: acia.a0_recorder(acia.A0_REPORT)}


def run_alt(scancode, kbshift=ALTERNATE, **kwargs):
    return run(addrs.KBD_QUEUE_KEY, scancode, kbshift=kbshift, vectors=MOUSE_VECTORS,
               routines=MOUSE_ROUTINES, **kwargs)


def mouse_packet(info):
    """The three bytes the emulated mouse left, out of the write ledger."""
    return tuple(info["writes"][addrs.KBD_MOUSE_PACKET + i] for i in range(3))


def test_alt_help_asks_for_a_screen_dump_and_queues_nothing():
    """`addq.w #1,_dumpflg` — a WORD, and an increment rather than a store, so a request already
    pending is not lost."""
    for pending in (0, 0x1234):
        info = run_alt(addrs.SCANCODE_HELP, pokes={addrs.SYSVAR_DUMPFLG: struct.pack(">H", pending)})
        assert case.written(info, addrs.SYSVAR_DUMPFLG, 2) == (pending + 1) & 0xFFFF
        assert nothing_queued(info)


# The four codes the ROM's own table at $fc2ea0 holds, read out of it rather than typed: Home and
# Insert, each make and break, and which kbshift bit each drives.
ALT_BUTTON_KEYS = tuple(BASE_IMAGE[addrs.ALT_MOUSE_BUTTON_KEYS:
                                   addrs.ALT_MOUSE_BUTTON_KEYS + addrs.ALT_MOUSE_BUTTON_KEY_COUNT])


@pytest.mark.parametrize("scancode", ALT_BUTTON_KEYS)
def test_an_alt_button_key_moves_its_own_kbshift_bit_and_sends_a_packet(scancode):
    """Bit 4 of the scancode picks the button and bit 7 picks press from release, so one four-entry
    table and two `btst`s cover all four codes. The packet is the emulated mouse's own at `$e5e`,
    with no movement — and its HEADER is what kbshift was just changed to."""
    pressing = not scancode & addrs.SCANCODE_RELEASE
    bit = (addrs.KBSHIFT_LEFT_BUTTON_BIT if scancode & (1 << addrs.ALT_MOUSE_BUTTON_SELECT_BIT)
           else addrs.KBSHIFT_RIGHT_BUTTON_BIT)
    entry_shift = ALTERNATE if pressing else ALTERNATE | (1 << bit)
    info = run_alt(scancode, kbshift=entry_shift)
    left = entry_shift | (1 << bit) if pressing else entry_shift & ~(1 << bit)
    assert info["writes"][addrs.KBSHIFT] == left
    assert mouse_packet(info) == ((left >> addrs.KBSHIFT_BUTTON_SHIFT)
                                  + addrs.KBD_MOUSE_HEADER_BIAS & 0xFF, 0, 0)
    assert case.written(info, acia.A0_REPORT, 4) == addrs.KBD_MOUSE_PACKET
    assert nothing_queued(info)


ARROWS = ((addrs.SCANCODE_CURSOR_UP, 0, -addrs.KBD_MOUSE_STEP, 0, -addrs.KBD_MOUSE_FINE_STEP),
          (addrs.SCANCODE_CURSOR_LEFT, -addrs.KBD_MOUSE_STEP, 0, -addrs.KBD_MOUSE_FINE_STEP, 0),
          (addrs.SCANCODE_CURSOR_RIGHT, addrs.KBD_MOUSE_STEP, 0, addrs.KBD_MOUSE_FINE_STEP, 0),
          (addrs.SCANCODE_CURSOR_DOWN, 0, addrs.KBD_MOUSE_STEP, 0, addrs.KBD_MOUSE_FINE_STEP))


@pytest.mark.parametrize("scancode,dx,dy,fine_dx,fine_dy", ARROWS,
                         ids=("up", "left", "right", "down"))
@pytest.mark.parametrize("shifted", (False, True), ids=("a step", "a pixel"))
def test_an_alt_arrow_key_moves_the_emulated_mouse(scancode, dx, dy, fine_dx, fine_dy, shifted):
    """Eight pixels a press, or one with either SHIFT held. The four keys are four separate arms in
    the ROM, each naming its own pair, so a reconstruction that swapped dx and dy — or a sign —
    passes on three of them."""
    kbshift = ALTERNATE | (1 << addrs.KBSHIFT_LEFT_SHIFT_BIT if shifted else 0)
    info = run_alt(scancode, kbshift=kbshift)
    moved = (fine_dx, fine_dy) if shifted else (dx, dy)
    header = (kbshift >> addrs.KBSHIFT_BUTTON_SHIFT) + addrs.KBD_MOUSE_HEADER_BIAS & 0xFF
    assert mouse_packet(info) == (header, moved[0] & 0xFF, moved[1] & 0xFF)
    assert nothing_queued(info)


DIGIT_KEYS = tuple(range(addrs.SCANCODE_DIGIT_FIRST, addrs.SCANCODE_DIGIT_LAST + 1))


@pytest.mark.parametrize("scancode", DIGIT_KEYS)
def test_alt_renumbers_the_number_row_and_drops_its_ascii(scancode):
    """`addi.b #118` — a BYTE add — over the whole run, so both boundaries are covered."""
    info = run_alt(scancode)
    assert record_at(info) == expected_record(scancode + addrs.ALT_DIGIT_OFFSET, 0)


@pytest.mark.parametrize("scancode", (addrs.SCANCODE_DIGIT_FIRST - 1,
                                      addrs.SCANCODE_DIGIT_LAST + 1))
def test_the_keys_either_side_of_the_number_row_keep_their_scancode(scancode):
    info = run_alt(scancode)
    assert (record_at(info) >> 16) & 0xFF == scancode


@pytest.mark.parametrize("field", (addrs.KEYTBL_FIELD_UNSHIFTED, addrs.KEYTBL_FIELD_SHIFTED))
def test_alt_drops_the_ascii_of_every_letter_key_and_keeps_every_other(field):
    """Two ranges, upper and lower case, tested on the ASCII rather than on the scancode — so which
    keys lose their ASCII depends on the table in force, and a replaced `Keytbl` moves the set.

    The number row is left out because it never reaches this test: the digit arm above claims it
    first, whatever its ASCII is.
    """
    kbshift = ALTERNATE | (1 << addrs.KBSHIFT_LEFT_SHIFT_BIT
                           if field == addrs.KEYTBL_FIELD_SHIFTED else 0)
    for scancode in (key for key in TABLE_KEYS
                     if not addrs.SCANCODE_DIGIT_FIRST <= key <= addrs.SCANCODE_DIGIT_LAST):
        produced = ascii_of(scancode, field)
        is_letter = (addrs.ASCII_UPPER_FIRST <= produced <= addrs.ASCII_UPPER_LAST
                     or addrs.ASCII_LOWER_FIRST <= produced <= addrs.ASCII_LOWER_LAST)
        info = run_alt(scancode, kbshift=kbshift)
        assert record_at(info) == expected_record(scancode, 0 if is_letter else produced)


# ---- the record, and the ring --------------------------------------------------------------------

# Shift states that reach the PLAIN arm: no shift, control, alt or CapsLock bit among them, so the
# record differs only in the byte this test is about. The two emulated mouse buttons and bit 7 are
# the bits nothing in `kbd_queue_key` branches on.
UNBRANCHED_SHIFTS = (0x00, 1 << addrs.KBSHIFT_RIGHT_BUTTON_BIT, 0xE0)


@pytest.mark.parametrize("kbshift", UNBRANCHED_SHIFTS)
def test_conterm_bit_3_decides_whether_the_record_reports_the_shift_state(kbshift):
    """`btst #3,conterm` clear masks the top byte off, which is how a stock machine boots. The bit
    is the ONLY difference between the two records, so a reconstruction that always reported — or
    never did — passes one of these."""
    reporting = run(addrs.KBD_QUEUE_KEY, A_KEY, kbshift=kbshift,
                    conterm=1 << addrs.CONTERM_KBSHIFT_BIT)
    assert record_at(reporting) == expected_record(A_KEY, ascii_of(A_KEY), kbshift)
    silent = run(addrs.KBD_QUEUE_KEY, A_KEY, kbshift=kbshift, conterm=0)
    assert record_at(silent) == expected_record(A_KEY, ascii_of(A_KEY))


@pytest.mark.parametrize("tail", (0, RECORD, RING_BYTES - 2 * RECORD, RING_BYTES - RECORD))
def test_a_key_lands_one_record_past_the_tail(tail):
    # A head two records ahead of the tail is never the index the store lands on, at any of the
    # four tails — so this case is about the STORE and the full-ring rule is tested on its own.
    info = run(addrs.KBD_QUEUE_KEY, A_KEY, head=(tail + 2 * RECORD) % RING_BYTES, tail=tail)
    landed = 0 if tail == RING_BYTES - RECORD else tail + RECORD
    assert record_at(info, landed) == expected_record(A_KEY, ascii_of(A_KEY))
    assert case.written(info, RING + addrs.IOREC_TAIL, 2) == landed


def test_the_tail_wraps_at_the_ring_s_size_and_not_one_record_short_of_it():
    """Both boundaries of `cmp.w size,d1 / bcs`, because an off-by-one either way passes the other."""
    last = run(addrs.KBD_QUEUE_KEY, A_KEY, head=0, tail=RING_BYTES - 2 * RECORD)
    assert case.written(last, RING + addrs.IOREC_TAIL, 2) == RING_BYTES - RECORD
    wrapped = run(addrs.KBD_QUEUE_KEY, A_KEY, head=RECORD, tail=RING_BYTES - RECORD)
    assert case.written(wrapped, RING + addrs.IOREC_TAIL, 2) == 0


@pytest.mark.parametrize("head,tail", ((RECORD, 0),
                                       (0, RING_BYTES - RECORD),
                                       (RING_BYTES // 2 + RECORD, RING_BYTES // 2)))
def test_a_full_ring_drops_the_key_and_moves_nothing(head, tail):
    """THE OVERFLOW RULE: the NEWEST key is lost, not the oldest. The tail stays where it was and the
    head is not advanced to make room, so everything the reader has not taken yet survives.

    The click still happens — it is made before the ring is even looked at — so the write ledger is
    not empty; what must be untouched is the ring and its tail.
    """
    info = run(addrs.KBD_QUEUE_KEY, A_KEY, head=head, tail=tail)
    assert nothing_queued(info)


def test_the_key_click_is_made_before_the_ring_is_looked_at():
    """...which is why a key dropped by a full ring still clicks."""
    info = run(addrs.KBD_QUEUE_KEY, A_KEY, head=RECORD, tail=0,
               conterm=1 << addrs.CONTERM_CLICK_BIT)
    assert case.written_long(info, addrs.SOUND_LIST_POINTER) == addrs.KEYCLICK_SOUND_LIST
    assert nothing_queued(info)


def test_the_ring_the_record_goes_in_is_the_one_a0_names():
    """The IOREC is a PARAMETER, not a constant: timer C's auto-repeat enters this routine with the
    same `lea $c76,a0` the ACIA path makes, and a case may name another record entirely."""
    elsewhere = addrs.IOREC_MIDI

    def glue(lib, buf):
        lib.kbd_queue_key(buf, A_KEY, elsewhere)

    info = acia.run(addrs.KBD_QUEUE_KEY, glue,
                    pokes={**iorec.staged(elsewhere, 0, 0), addrs.KBSHIFT: b"\x00"},
                    regs={"d0": A_KEY, "a0": elsewhere})
    assert case.written(info, iorec.buffer_of(elsewhere) + RECORD, RECORD) == \
        expected_record(A_KEY, ascii_of(A_KEY))
    assert nothing_queued(info), "the IKBD's own ring must be untouched when A0 names another"


# ---- the cases this battery REGISTERS ------------------------------------------------------------
# TWO, one per routine, and each is a case above with a name. They are what gives these two Tier 3
# rows of their own: nothing CALLS either by name — `acia_take_byte` falls into `kbd_scancode` and
# timer C's auto-repeat jumps into `kbd_queue_key` — so `bench/tier3.py` reaches them through its
# `UNNUMBERED_ROUTINE_NAMES` relation. An ordinary letter with no modifier held is the arm both share
# and the one the machine runs most.
REGISTERED = (
    spec("kbd_scancode, a key", addrs.KBD_SCANCODE, A_KEY,
         pokes={addrs.SYSVAR_KB_REPEAT_KEY: b"\x00"}),
    spec("kbd_queue_key, a key", addrs.KBD_QUEUE_KEY, A_KEY),
)
VERIFIED_CASES = tuple(acia.registered(registered) for registered in REGISTERED)


@pytest.mark.parametrize("registered", REGISTERED, ids=lambda registered: registered["name"])
def test_every_registered_case_is_one_this_battery_proves(registered):
    """The row and the differential are the SAME spec (`acia.registered` / `acia.run_spec`)."""
    acia.run_spec(registered)
