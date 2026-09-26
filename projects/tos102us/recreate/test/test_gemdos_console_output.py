"""GEMDOS Cconout / Cauxout / Cprnout / Cconws, and `Crawio`'s write arm ($02, $04, $05, $09, $06).

FOUR WAYS OUT OF GEMDOS AND ONLY ONE OF THEM IS THE CONSOLE'S. `Cconout` and `Cconws` go through
`device_put` — poll the keyboard, hand the byte to `Bconout`, move a COLUMN COUNTER of GEMDOS's own —
and expand a TAB to the next multiple of eight on the way. `Cauxout`, `Cprnout` and `Crawio`'s write
arm are three instructions and a trap: no poll, no tab, no column. So a program that printed through
`Cprnout` and then asked `Cconout` for a TAB gets a tab measured from wherever the CONSOLE's column
was, which is the point of there being three counters.

THE COLUMN COUNTER IS NOT THE CURSOR. GEMDOS's counter ($68f4) and the VT52 driver's own cursor
column ($297e) are different words of RAM maintained by different layers, and nothing keeps them in
step: an `ESC Y` through `Bconout` moves the cursor and not the counter. Every case below that cares
stages both, and `test_the_column_counter_is_gemdos_s_own_word` is the one that says they are two.

THREE FINDINGS.

*`Cconws` SIGN-EXTENDS AND `Cconout` DOES NOT.* The string loop is `move.b (a0),d0 / ext.w d0`, so a
byte with bit 7 set arrives as $ff80..$ffff — NEGATIVE to `device_put`'s `cmp.w #32 / bge` — and the
column counter is not advanced. The same value as `Cconout`'s argument word is $0080 and does
advance it. The BIOS gets the same byte either way; GEMDOS's idea of the column does not.

*A TAB ALWAYS COSTS AT LEAST ONE SPACE.* The expansion loop is a do-while: at column 8 it emits eight
more spaces rather than none, because the test is made after the space and not before it.

*LF DOES NOT TOUCH THE COUNTER AND CR RESETS IT.* `device_put`'s three arms are `>= 32` (forward),
CR (zero) and BS (back); everything else, LF included, leaves the word alone. So the counter is only
right across a line feed because the CR that TOS pairs it with is what zeroes it.
"""
import pytest

from harness import addrs, emu

import case
import gemdos
import gemdos_console as console
import iorec
import test_bios_bconout as bconout
import vt52

A_CHARACTER = 0x41                              # 'A'
HIGH_BYTE = 0xE9                                # a byte with bit 7 set — the sign-extension finding
START_COLUMN = 3                                # ...and somewhere in a tab stop's middle

# The strings a `Cconws` case writes, in the staging band. Spelt as bytes because that is what a
# poke takes and what the ROM reads.
TEXT = b"Hi!"
LONG_TEXT = b"abcdef"                           # ...long enough to cross the last column


def _string(text):
    return {console.STRING_AT: text + b"\0"}


def console_machine(column=START_COLUMN, row=0, *, cursor_depth=1, pokes=None):
    """The console as a program finds it, with the IKBD ring empty and both columns in step.

    `cursor_depth=1` keeps the cursor OFF the screen, which is what makes a glyph case about the
    glyph: with the cursor drawn, every write also inverts a cell.
    """
    return {**iorec.staged(addrs.IOREC_IKBD, head=0, tail=0),
            **console.queue(console.DEVICE_CONSOLE),
            **console.column(console.DEVICE_CONSOLE, column),
            **vt52.staged(column, row, cursor_depth=cursor_depth, extra_flags=vt52.WRAP),
            **(pokes or {})}


# ---- the specs -----------------------------------------------------------------------------------

CCONOUT_GLYPH = {"name": "gemdos_cconout, a glyph", "leaf": console.CCONOUT,
                 "argument": A_CHARACTER,
                 "pokes": console_machine(pokes=vt52.canary(START_COLUMN, 0))}
CCONOUT_TAB = {"name": "gemdos_cconout, TAB mid-stop", "leaf": console.CCONOUT,
               "argument": addrs.CON_TAB, "pokes": console_machine()}
CCONOUT_TAB_ON_A_STOP = {"name": "gemdos_cconout, TAB already on a stop", "leaf": console.CCONOUT,
                         "argument": addrs.CON_TAB,
                         "pokes": console_machine(column=addrs.CON_TAB_WIDTH)}
CCONOUT_CR = {"name": "gemdos_cconout, CR", "leaf": console.CCONOUT, "argument": addrs.CON_CR,
              "pokes": console_machine()}
CCONOUT_LF = {"name": "gemdos_cconout, LF", "leaf": console.CCONOUT, "argument": addrs.CON_LF,
              "pokes": console_machine()}
CCONOUT_BS = {"name": "gemdos_cconout, BS", "leaf": console.CCONOUT, "argument": addrs.CON_BS,
              "pokes": console_machine()}
CCONOUT_HIGH_BYTE = {"name": "gemdos_cconout, a byte with bit 7 set", "leaf": console.CCONOUT,
                     "argument": HIGH_BYTE, "pokes": console_machine()}
CCONOUT_ON_AUX = {"name": "gemdos_cconout, stdout redirected to AUX:", "leaf": console.CCONOUT,
                  "argument": A_CHARACTER,
                  "pokes": {**console.handles(stdout=console.HANDLE_AUX),
                            **console.queue(console.DEVICE_RS232),
                            **console.column(console.DEVICE_RS232, START_COLUMN),
                            **iorec.staged(addrs.IOREC_RS232, head=0, tail=0),
                            **bconout.rs232_pokes()},
                  "io_seed": {addrs.MFP_TSR: bconout.TSR_SENDING}}

CAUXOUT = {"name": "gemdos_cauxout", "leaf": console.CAUXOUT, "argument": A_CHARACTER,
           "pokes": {**console.column(console.DEVICE_RS232, START_COLUMN),
                     **bconout.rs232_pokes()},
           "io_seed": {addrs.MFP_TSR: bconout.TSR_SENDING}}
CPRNOUT = {"name": "gemdos_cprnout", "leaf": console.CPRNOUT, "argument": A_CHARACTER,
           "pokes": {**console.column(console.DEVICE_PRINTER, START_COLUMN),
                     **bconout.printer_pokes()},
           "psg_seed": bconout.PRINTER_PSG_SEED,
           "io_seed": {addrs.MFP_GPIP: bconout.GPIP_READY}}
# ...and the AUX leaf over the CONSOLE handle: the same character, the same device and the same BIOS
# driver as a `Cconout`, reached by the leaf that has no column counter and no poll in front of it.
CAUXOUT_ON_CONSOLE = {"name": "gemdos_cauxout, stdaux redirected to CON:", "leaf": console.CAUXOUT,
                      "argument": A_CHARACTER,
                      "pokes": {**console_machine(pokes=vt52.canary(START_COLUMN, 0)),
                                **console.handles(stdaux=console.HANDLE_CON)}}
CRAWIO_WRITE = {"name": "gemdos_crawio, write", "leaf": console.CRAWIO, "argument": A_CHARACTER,
                "pokes": console_machine()}
CRAWIO_WRITE_HIGH_HALF = {"name": "gemdos_crawio, write with a high half", "leaf": console.CRAWIO,
                          "argument": 0x40FF, "pokes": console_machine()}

CCONWS_TEXT = {"name": "gemdos_cconws, a string", "leaf": console.CCONWS,
               "argument": console.STRING_AT,
               "pokes": {**console_machine(), **_string(TEXT)}}
CCONWS_EMPTY = {"name": "gemdos_cconws, the empty string", "leaf": console.CCONWS,
                "argument": console.STRING_AT,
                "pokes": {**console_machine(), **_string(b"")}}
CCONWS_HIGH_BYTE = {"name": "gemdos_cconws, a byte with bit 7 set", "leaf": console.CCONWS,
                    "argument": console.STRING_AT,
                    "pokes": {**console_machine(), **_string(bytes([HIGH_BYTE]))}}
CCONWS_WRAPS_AND_SCROLLS = {"name": "gemdos_cconws, over a wrap and a scroll",
                            "leaf": console.CCONWS, "argument": console.STRING_AT,
                            "pokes": {**console_machine(column=vt52.MAX_COLUMN - 1,
                                                         row=vt52.MAX_ROW),
                                      **_string(LONG_TEXT)}}
CCONWS_TAB = {"name": "gemdos_cconws, a TAB in the string", "leaf": console.CCONWS,
              "argument": console.STRING_AT,
              "pokes": {**console_machine(), **_string(bytes([addrs.CON_TAB]))}}

REGISTERED = (CCONOUT_GLYPH, CCONOUT_TAB, CCONOUT_TAB_ON_A_STOP, CCONOUT_CR, CCONOUT_LF,
              CCONOUT_BS, CCONOUT_HIGH_BYTE, CCONOUT_ON_AUX, CAUXOUT, CPRNOUT, CRAWIO_WRITE,
              CAUXOUT_ON_CONSOLE, CRAWIO_WRITE_HIGH_HALF, CCONWS_TEXT, CCONWS_EMPTY,
              CCONWS_HIGH_BYTE,
              CCONWS_WRAPS_AND_SCROLLS, CCONWS_TAB)
VERIFIED_CASES = tuple(console.registered(spec) for spec in REGISTERED)


def _column_after(info, device=console.DEVICE_CONSOLE):
    return case.written(info, console.column_slot(device), addrs.GEMDOS_DEVICE_COLUMN_BYTES)


def _console_bytes(info):
    """Every screen byte the run wrote, which is what "the same pixels" means for these cases."""
    return sorted(at for at in info["writes"]
                  if vt52.SCREEN <= at < vt52.SCREEN + vt52.ROW_BYTES * (vt52.MAX_ROW + 1))


# ---- the column counter --------------------------------------------------------------------------

def test_the_column_counter_is_gemdos_s_own_word():
    """Not the VT52 driver's cursor: two different addresses, and only one of them is in the block
    the console driver keeps. A reconstruction that read the cursor instead would pass every case
    whose two are staged in step, so this is what says they are two."""
    assert console.column_slot(console.DEVICE_CONSOLE) != addrs.CON_CURSOR_COLUMN
    assert not (addrs.CON_CELL_HEIGHT <= console.column_slot(console.DEVICE_CONSOLE)
                < addrs.CON_CELL_HEIGHT + 0x2A)


def test_a_glyph_moves_the_column_counter_on_by_one():
    info = console.run(CCONOUT_GLYPH)
    assert _column_after(info) == START_COLUMN + 1
    assert _console_bytes(info) == sorted(vt52.cell_bytes(START_COLUMN, 0)), (
        "the glyph did not land in the cell both layers say the cursor is in")


def test_carriage_return_zeroes_it_and_line_feed_leaves_it_alone():
    """`clr.w` against nothing at all — the whole of why the pair has to be sent in that order."""
    assert _column_after(console.run(CCONOUT_CR)) == 0
    assert console.column_slot(console.DEVICE_CONSOLE) not in console.run(CCONOUT_LF)["writes"]


def test_backspace_moves_it_back():
    assert _column_after(console.run(CCONOUT_BS)) == START_COLUMN - 1


@pytest.mark.parametrize("spec,column,spaces",
                         ((CCONOUT_TAB, START_COLUMN, addrs.CON_TAB_WIDTH - START_COLUMN),
                          (CCONOUT_TAB_ON_A_STOP, addrs.CON_TAB_WIDTH, addrs.CON_TAB_WIDTH)))
def test_a_tab_is_spaces_to_the_next_stop_and_never_none(spec, column, spaces):
    """The do-while is the finding: a TAB in column 8 costs eight spaces, not zero."""
    info = console.run(spec)
    assert _column_after(info) == column + spaces
    assert _console_bytes(info) == sorted(
        at for offset in range(spaces) for at in vt52.cell_bytes(column + offset, 0))


def test_the_tab_expansion_ends_on_a_stop_whatever_column_it_started_in():
    """Every column of one stop's width, each its own run — which is what says the loop's condition
    is the column's PHASE and not a count the reconstruction could have guessed."""
    for column in range(addrs.CON_TAB_WIDTH):
        info = console.run(CCONOUT_TAB, pokes=console_machine(column=column))
        assert _column_after(info) % addrs.CON_TAB_WIDTH == 0
        assert _column_after(info) == column + addrs.CON_TAB_WIDTH - column % addrs.CON_TAB_WIDTH


# ---- the three that skip all of it ---------------------------------------------------------------

@pytest.mark.parametrize("spec,device", ((CAUXOUT, console.DEVICE_RS232),
                                         (CPRNOUT, console.DEVICE_PRINTER)))
def test_cauxout_and_cprnout_leave_their_device_s_column_alone(spec, device):
    """Three instructions and a trap. The counter is staged at a value neither of them may touch,
    so a reconstruction that had reused `device_put` would move it and redden here."""
    info = console.run(spec)
    assert console.column_slot(device) not in info["writes"]
    gemdos.bios_call_site(info)


@pytest.mark.parametrize("character", (0x00, A_CHARACTER, 0x7F, 0xFF, 0x1234))
@pytest.mark.parametrize("spec", (CAUXOUT, CPRNOUT, CRAWIO_WRITE))
def test_the_three_that_go_straight_to_the_bios_pass_the_whole_word_on(spec, character):
    """Driven over the width of the argument, because `Bconout` takes a WORD and sends its low byte:
    $1234 is the same byte on the wire as $34, and a leaf that masked it here would still pass a
    single-value case. `$00ff` is the one value `Crawio` reads instead of writing, so it is not in
    this sweep — `test_crawio_writes_...` drives that boundary."""
    if spec is CRAWIO_WRITE and character == addrs.GEMDOS_CRAWIO_READ:
        pytest.skip("Crawio's read arm; driven by its own case")
    console.run(spec, argument=character)


def test_the_same_character_through_cauxout_and_cconout_reaches_the_same_driver():
    """`Cauxout` over the CONSOLE handle draws the same glyph a `Cconout` does — and leaves the
    console's column counter where it was, which is the whole of the difference between the two
    leaves said in one run."""
    info = console.run(CAUXOUT_ON_CONSOLE)
    assert _console_bytes(info) == sorted(vt52.cell_bytes(START_COLUMN, 0))
    assert console.column_slot(console.DEVICE_CONSOLE) not in info["writes"]


def test_cauxout_and_cprnout_do_not_poll_the_keyboard():
    """...and the second half of the same claim: `device_put` opens with `drain_typeahead`, which
    asks `Bconstat` first. With a record staged in the CONSOLE's ring, a leaf that polled would take
    it; these two leave it where it is."""
    ring = iorec.staged(addrs.IOREC_IKBD, 0, addrs.IOREC_KEY_BYTES,
                        [(0, b"\x1e\x00\x61\x00")])
    for spec in (CAUXOUT, CPRNOUT):
        info = console.run(spec, pokes={**spec["pokes"], **ring})
        assert addrs.IOREC_IKBD + addrs.IOREC_HEAD not in info["writes"]


def test_crawio_writes_through_the_bios_and_ignores_the_arguments_high_half():
    """`cmp.w #255` is the WHOLE word, so `$40ff` is a write of $ff and not a read."""
    for spec in (CRAWIO_WRITE, CRAWIO_WRITE_HIGH_HALF):
        info = console.run(spec)
        assert gemdos.bios_call_site(info)
        assert console.column_slot(console.DEVICE_CONSOLE) not in info["writes"], (
            "Crawio's write arm went through device_put, which tracks the column")


# ---- Cconws ---------------------------------------------------------------------------------------

def test_a_string_prints_one_character_at_a_time_and_moves_the_counter_by_its_length():
    info = console.run(CCONWS_TEXT)
    assert _column_after(info) == START_COLUMN + len(TEXT)
    assert _console_bytes(info) == sorted(
        at for offset in range(len(TEXT)) for at in vt52.cell_bytes(START_COLUMN + offset, 0))


def test_the_empty_string_touches_nothing_and_leaves_the_sign_extended_handle_in_d0():
    """A FOURTH FINDING, and one only this case can make.

    The loop's test is made FIRST, so an empty string makes no call at all — and D0 is then what the
    leaf's own `move.b <handle>,d0 / ext.w d0` left there: the caller's high half over the SIGN-
    EXTENDED standard handle. Not the caller's low word (nothing else writes it), not 0, and not the
    device number — the `addq.w #3` that makes a device is made on the stack word. `$ffff` is a
    console. Every other leaf ends in a call that overwrites the whole register, so this is the one
    place in the group where the read of the basepage is visible in the answer.
    """
    info = console.run(CCONWS_EMPTY)
    handle = console.snapshot_handle("stdout")
    assert info["regs"]["d0"] == (console.MARKED_D0 & 0xFFFF0000) | (0xFF00 | handle)
    assert addrs.GEMDOS_BIOS_RETURN_SLOT not in info["writes"]
    assert _console_bytes(info) == []


def test_a_string_byte_with_bit_7_set_does_not_move_the_counter_but_the_same_value_as_cconout_does():
    """THE SIGN-EXTENSION FINDING, both halves in one case: `ext.w` makes $e9 negative to
    `device_put`'s signed compare, and `Cconout`'s argument word of the same value is positive."""
    assert console.column_slot(console.DEVICE_CONSOLE) not in console.run(CCONWS_HIGH_BYTE)["writes"]
    assert _column_after(console.run(CCONOUT_HIGH_BYTE)) == START_COLUMN + 1


def test_a_tab_inside_a_string_is_expanded_exactly_as_cconout_expands_one():
    """`Cconws` calls the SAME routine `Cconout` does, which is the only reason the two agree."""
    assert _column_after(console.run(CCONWS_TAB)) == addrs.CON_TAB_WIDTH


def test_a_string_that_crosses_the_last_column_wraps_and_scrolls():
    """The console driver's own wrap and scroll, reached from GEMDOS: six characters from two
    columns short of the end of the LAST row, so the line wraps and the screen moves up."""
    info = console.run(CCONWS_WRAPS_AND_SCROLLS)
    assert _column_after(info) == vt52.MAX_COLUMN - 1 + len(LONG_TEXT)
    assert case.written(info, addrs.CON_CURSOR_ROW, 2) == vt52.MAX_ROW, (
        "the cursor did not end on the last row, so nothing scrolled")
    assert len(_console_bytes(info)) > vt52.ROW_BYTES, "no scroll: too few screen bytes moved"


# ---- the trampoline's return slot ------------------------------------------------------------------

def test_every_bios_call_parks_a_return_address_the_rom_really_has_a_jsr_at():
    """`GEMDOS_BIOS_RETURN_SLOT` is ordinary RAM and the trampoline's store into it is ordinary
    output, so the reconstruction makes it too — from a named constant per call site. This is what
    says those constants are sites: the six bytes before each must be `jsr $fc4eac`."""
    for spec in (CCONOUT_GLYPH, CAUXOUT, CPRNOUT, CRAWIO_WRITE, CCONWS_TEXT):
        gemdos.bios_call_site(console.run(spec))


def test_the_slot_names_which_call_a_leaf_made_last():
    """A `Cconout` ends on `Bconout` and a `Cauxout` on a different `jsr` altogether, so the slot
    tells the two apart. A reconstruction that parked one constant everywhere would pass every case
    above and fail this one."""
    assert gemdos.bios_call_site(console.run(CCONOUT_GLYPH)) \
        != gemdos.bios_call_site(console.run(CAUXOUT))


def test_the_staged_savptr_is_where_the_roms_trap_frame_lands():
    """The one declaration this wave makes about the machine (`test/gemdos.py`): the ROM's
    register-save frame lands in the run's own stack band, `savptr` comes back exactly where the case
    put it, and NOTHING lands below the frame the case staged — which is also what
    `harness._stray_stack_writes` would refuse, so a second, nested frame could not pass quietly."""
    writes = console.run(CCONOUT_GLYPH)["writes"]
    assert case.written_long({"writes": writes}, addrs.SYSVAR_SAVPTR) == gemdos.SAVPTR_AT
    assert any(gemdos.FRAME_AT <= at < gemdos.SAVPTR_AT for at in writes), (
        "the ROM's trap #13 left no frame where savptr points — the declaration describes nothing")
    assert not [at for at in writes if emu.STACK_GUARD_LO <= at < gemdos.FRAME_AT]
