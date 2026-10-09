"""THE CARTRIDGE CHAIN (`src/aes/cart.c`): cart_init `$fed478` and cart_find `$fed4be`.

    cart_init():      cart_ptr = $fa0000; if (*cart_ptr == $abcdef42) { cart_ptr = $fa0004; return 1; }
                      cart_ptr = NULL; return 0
    cart_find(fill):  if (!cart_ptr) return NULL
                      if (fill) { bfill(42, 0, dta); dta[21] = 1; LBCOPY(dta + 22, cart_ptr + 12, 21); }
                      header = cart_ptr; cart_ptr = *cart_ptr; return header

WHAT REACHES EACH TODAY — THE CAPTURED MACHINE HAS NO CARTRIDGE, and neither can any machine the oracle makes: its
bus answers 0 at `$fa0000` whatever the image holds there (the kit serves the megabyte of RAM, the ROM and the I/O
page; a poke at the cartridge port is not read). So:

  * THE NO-CARTRIDGE ROAD is a ROM run's: cart_init over the snapshot leaves the cursor NULL — what the boot's own
    left in the capture — and cart_find over a NULL cursor answers NULL and stores nothing.
  * cart_find's WALK is an ARGUMENT CLASS, labelled: the cursor STAGED at a ROM-FORMAT CARTRIDGE HEADER IMAGE IN RAM
    (two headers chained, as TOS's CA_HEADER lays them: next, init, run, time, date, size, name) — bytes this battery
    wrote, in a place no cartridge can be; on a machine with one the cursor would be `$fa0004`. The routine reads
    the header through the cursor alone, so the staged chain is read as a cartridge's would be.
  * cart_init's CARTRIDGE-PRESENT ARM IS UNPINNED BY ANY DIFFERENTIAL: no ROM run reaches it. Its two constants
    are held to the ROM's own instructions (the immediates of `$fed496` and `$fed4a0`, read out of the text) against
    the C over a host image with the magic at the port — a READING, said as such, not a run of the ROM.

OWED when a machine with a cartridge exists (a kit change: the bus's `$fa0000..$fbffff` served from the image):
cart_init's present arm and cart_find from `$fa0004`, and their callers' (`$fdb700`, `$fe43a6`, `$fed55c`, `$fed5ca`).
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import case
import gemdos
import vdi
import vdi_helpers
from case import merge_pokes

CART_INIT, CART_FIND = "AES_ROM_CART_INIT", "AES_ROM_CART_FIND"
aes.declare_alcyon(CART_INIT, aes.WORD_ANSWER, (vdi.IMAGE_ARG,))
aes.declare_alcyon(CART_FIND, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG))
CART = aes.header_constants("cart.h")
CURSOR, DTA_POINTER = CART["AES_CART_CURSOR"], CART["AES_CART_DTA"]
for _at, _why in ((CURSOR, "the cartridge chain's cursor"), (DTA_POINTER, "the DTA cart_sfirst was handed")):
    aes.declare_case_field(_at, aes.LONG_BYTES, _why)
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
ARGUMENT_CLASS = "ARGUMENT CLASS (the cursor staged at a ROM-format cartridge header image in RAM)"
STALE_CURSOR = {CURSOR: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big")}


def long_poke(at, value):
    return {at: struct.pack(">I", value & aes.LONG_MASK)}


# ---- cart_init: the no-cartridge road ---------------------------------------------------------------------------------
@THROUGH
def test_cart_init_with_no_cartridge_leaves_the_cursor_null_and_answers_0(through_line_f):
    result = aes.run_function(CART_INIT, (), aes.leaf_machine(onto=STALE_CURSOR), through_line_f=through_line_f)
    assert (result.long(CURSOR), result.answer()) == (0, CART["CART_ABSENT"])


def test_the_snapshot_s_cursor_is_what_the_boot_s_own_cart_init_left():
    """THE ROM-RUN STATE: the capture holds a NULL cursor, and the port's first longword reads 0 on this machine."""
    assert case.long_in(BASE_IMAGE, CURSOR) == 0 == case.long_in(BASE_IMAGE, CART["CART_BASE"])


def test_cart_init_stores_the_port_s_address_before_it_reads_through_it():
    """The cursor is SET to the port and the magic read THROUGH it ($fed47c, then $fed486 `movea.l $9ab8,a0`): the
    ROM's own run stopped at that read holds the port's address in the cursor."""
    from harness import emu
    final, _writes, _regs = emu.run(make_image(aes.leaf_machine(onto=STALE_CURSOR)), addrs.AES_ROM_CART_INIT, {},
                                    stop_pc=addrs.AES_ROM_CART_INIT + CURSOR_SET_BYTES)
    assert case.long_in(final, CURSOR) == CART["CART_BASE"]


CURSOR_SET_BYTES = 14                   # `link a6,#-4` and `move.l #$fa0000,$9ab8`: $fed478..$fed485


# ---- cart_init's present arm: A READING of the ROM's instructions, no run of them -------------------------------------
PRESENT_ARM_STORE = 0xFED496            # `move.l #$fa0004,$9ab8`
PRESENT_ARM_ANSWER = 0xFED4A0           # `moveq #1,d0`
MAGIC_COMPARE = 0xFED48E                # `cmp.l #$abcdef42,d0`
MOVEQ_1_D0 = 0x7001


def test_the_present_arm_s_constants_are_the_rom_s_own_instructions__a_reading_not_a_run():
    """UNPINNED BY A DIFFERENTIAL (no machine of the oracle's has a cartridge). What is held instead: the C over a
    HOST image with the application magic at the port answers 1 and leaves the cursor at the address the ROM's
    `move.l #` names — each constant read out of the ROM's text."""
    assert case.long_in(BASE_IMAGE, MAGIC_COMPARE + aes.WORD_BYTES) == CART["CART_APPLICATION_MAGIC"]
    first_header = case.long_in(BASE_IMAGE, PRESENT_ARM_STORE + aes.WORD_BYTES)
    assert case.long_in(BASE_IMAGE, PRESENT_ARM_STORE + aes.WORD_BYTES + aes.LONG_BYTES) == CURSOR
    assert case.word_in(BASE_IMAGE, PRESENT_ARM_ANSWER) == MOVEQ_1_D0
    pokes = merge_pokes(STALE_CURSOR, long_poke(CART["CART_BASE"], CART["CART_APPLICATION_MAGIC"]))
    answer, image = gemdos.run_candidate_only(lambda lib, buf: lib.aes_cart_init(buf), pokes)
    assert (answer, case.long_in(image, CURSOR)) == (1, first_header) == (CART["CART_PRESENT"], CART["CART_FIRST_HEADER"])


@pytest.mark.parametrize("magic", (0xABCDEF43, 0xABCD0000, 0x0000EF42, 0xFA52235F), ids=lambda value: f"{value:#x}")
def test_another_longword_at_the_port_is_no_application_cartridge__the_c_alone(magic):
    """...and any other longword there — the diagnostic cartridge's magic among them — is the absent arm (the C over
    a host image: the compare is of the whole longword)."""
    pokes = merge_pokes(STALE_CURSOR, long_poke(CART["CART_BASE"], magic))
    answer, image = gemdos.run_candidate_only(lambda lib, buf: lib.aes_cart_init(buf), pokes)
    assert (answer, case.long_in(image, CURSOR)) == (0, 0)


# ---- cart_find --------------------------------------------------------------------------------------------------------
# THE STAGED CHAIN: two headers in the staged blocks' band, the first naming the second, the second ending the chain.
HEADER_BYTES = CART["CA_ENTRY"] + 8 + 14            # next, init, run; time, date, size; a 14-byte name
FIRST, SECOND = aes.BLOCKS_AT, aes.BLOCKS_AT + 0x40
DTA_AT = aes.BLOCKS_AT + 0x80
DTA_BYTES = 44
DTA_ROOM = DTA_BYTES + 4                             # ...and four bytes past it, to show what is not written
DTA_FILL = 0x5C


def header(following, time, date, size, name):
    """A CA_HEADER: the next header's address, the init and run addresses (not read here), then its directory entry."""
    raw = struct.pack(">IIIHHI", following, 0x00FA_1000, 0x00FA_2000, time, date, size) + name.ljust(14, b"\0")
    assert len(raw) == HEADER_BYTES
    return raw


FIRST_HEADER = header(SECOND, 0x6A31, 0x1521, 0x0001_2345, b"FIRST.PRG")
SECOND_HEADER = header(0, 0x0842, 0x0E21, 77, b"ABCDEFGH.TOS")      # a full 8.3 name: twelve bytes and its NUL
CHAIN = {FIRST: FIRST_HEADER, SECOND: SECOND_HEADER}
DTA = merge_pokes({DTA_AT: bytes([DTA_FILL]) * DTA_ROOM}, long_poke(DTA_POINTER, DTA_AT))


def find_machine(cursor, *more):
    return aes.leaf_machine(onto=merge_pokes(CHAIN, DTA, long_poke(CURSOR, cursor), *more))


# THE ATTRIBUTION PASS IS STEERED BY THE CURSOR: cart_find reads the header THROUGH the longword it then stores, so
# the pass's inverted cursor is a wild pointer — every walking case names it, and the pass is made with that one
# longword left as it is (the DTA's bytes, which the run also stores, are inverted and must be stored again).
STEERS_THE_CURSOR = aes.steers("the chain's cursor: the header is read through the longword cart_find then stores",
                               (CURSOR, CURSOR + aes.LONG_BYTES))


def find(cursor, fill, *more, **kwargs):
    """cart_find(fill) over the staged chain with the cursor at `cursor` — steered by it wherever it walks."""
    steered = {"steered": STEERS_THE_CURSOR} if cursor else {}
    return aes.run_function(CART_FIND, (fill,), find_machine(cursor, *more), **steered, **kwargs)


@THROUGH
@pytest.mark.parametrize("fill", (0, 1), ids=("no fill", "fill"))
def test_cart_find_at_the_chain_s_end_answers_null_and_stores_nothing(fill, through_line_f):
    """THE NO-CARTRIDGE ROAD (the snapshot's own cursor): NULL answered, the DTA untouched even when asked to fill."""
    result = find(0, fill, through_line_f=through_line_f)
    assert result.long_answer() == CART["CART_CHAIN_END"]
    assert result.long(CURSOR) == 0 and result.after(DTA_AT, DTA_ROOM) == bytes([DTA_FILL]) * DTA_ROOM


WALKS = {"the first header": (FIRST, SECOND, FIRST_HEADER), "the last header": (SECOND, 0, SECOND_HEADER)}


@THROUGH
@pytest.mark.parametrize("which", WALKS)
def test_cart_find_answers_the_header_at_the_cursor_and_moves_it_on__no_fill(which, through_line_f):
    """ARGUMENT CLASS. The header answered, the cursor the header's own next (NULL after the last); with no fill
    asked the DTA is not touched."""
    cursor, following, _raw = WALKS[which]
    result = find(cursor, 0, through_line_f=through_line_f)
    assert (result.long_answer(), result.long(CURSOR)) == (cursor, following)
    assert result.after(DTA_AT, DTA_ROOM) == bytes([DTA_FILL]) * DTA_ROOM


@THROUGH
@pytest.mark.parametrize("fill", (1, -1, 0x0100), ids=("1", "-1", "a word whose low byte is 0"))
@pytest.mark.parametrize("which", WALKS)
def test_cart_find_fills_the_dta_as_a_search_s_answer(which, fill, through_line_f):
    """ARGUMENT CLASS. With `fill` (any nonzero WORD): the DTA's first 42 bytes cleared, read-only at 21, and the
    header's entry — time, date, size and THIRTEEN of its name's fourteen bytes — from 22 on: byte 42, the last the
    copy reaches, is the name's thirteenth; byte 43 and all past it are left."""
    cursor, following, raw = WALKS[which]
    result = find(cursor, fill, through_line_f=through_line_f)
    entry = raw[CART["CA_ENTRY"]:CART["CA_ENTRY"] + CART["CA_ENTRY_BYTES"]]
    expected = bytearray(CART["CART_DTA_ENTRY"]) + entry
    expected[CART["CART_DTA_ATTRIBUTE"]] = CART["CART_READ_ONLY"]
    assert result.after(DTA_AT, len(expected)) == bytes(expected)
    assert len(expected) == DTA_BYTES - 1 and result.after(DTA_AT + len(expected), DTA_ROOM - len(expected)) == (
        bytes([DTA_FILL]) * (DTA_ROOM - len(expected)))
    assert (result.long_answer(), result.long(CURSOR)) == (cursor, following)


def test_the_cursor_is_answered_as_it_is_held_and_read_on_the_bus():
    """ARGUMENT CLASS. A cursor with a top byte (a header's `next` is whatever the cartridge holds): answered top
    byte and all, the header read through 24 bits."""
    result = find(FIRST | aes.BUS_TAG, 1)
    assert (result.long_answer(), result.long(CURSOR)) == (FIRST | aes.BUS_TAG, SECOND)
    assert result.after(DTA_AT + CART["CART_DTA_ENTRY"], 4) == FIRST_HEADER[CART["CA_ENTRY"]:CART["CA_ENTRY"] + 4]


def test_the_dta_s_pointer_is_put_on_the_bus():
    result = find(FIRST, 1, long_poke(DTA_POINTER, DTA_AT | aes.BUS_TAG))
    assert result.final[DTA_AT + CART["CART_DTA_ATTRIBUTE"]] == CART["CART_READ_ONLY"]


def test_a_dta_laid_over_the_header_is_cleared_before_the_entry_is_read():
    """THE ORDER (ARGUMENT CLASS): the DTA at the header itself — the clear runs first, so the entry copied is
    zeros and the header's `next`, read LAST, is the cleared longword: the chain ends."""
    result = find(FIRST, 1, long_poke(DTA_POINTER, FIRST))
    assert result.long(CURSOR) == 0 and result.long_answer() == FIRST


def test_the_entry_is_looked_for_through_the_cleared_cursor__held_in_a_child():
    """FIRST OF THE TWO, AND IN A CHILD: the case below, where a twin that looked for the entry through the cursor
    AS IT STOOD BEFORE THE CLEAR walks a wild chain under the attribution pass and is ended by the host's bus guard
    — the suite brought down, no verdict. Here it answers another header than the ROM's, in a child."""
    machine = find_machine(FIRST, long_poke(DTA_POINTER, CURSOR - CART["CART_DTA_ENTRY"]))
    returncode, stderr, _image = aes_event.refusal(CART_FIND, machine, (1,), bind=None, answered=True, read_back=False)
    assert returncode == 0 and vdi_helpers.answer_in(stderr) == case.long_in(BASE_IMAGE, CART["CA_ENTRY"]) != FIRST, stderr


def test_a_dta_laid_over_the_cursor_itself_is_cleared_before_the_entry_is_looked_for():
    """THE ORDER (ARGUMENT CLASS): the DTA placed so that the entry lands ON THE CURSOR. The clear comes first and
    zeroes the cursor; the entry is then looked for THROUGH THE CURSOR AS IT STANDS (`$fed4f0 move.l $9ab8,-(sp)`:
    NULL + 12, the vector page), and the header answered is read AFTER the fill (`$fed508 movea.l $9ab8,a4`): what
    the copy left in the cursor — the longword at address 12 — and the walk goes on through that."""
    result = find(FIRST, 1, long_poke(DTA_POINTER, CURSOR - CART["CART_DTA_ENTRY"]))
    left_by_the_copy = case.long_in(BASE_IMAGE, CART["CA_ENTRY"])
    assert result.long_answer() == left_by_the_copy != FIRST
    assert result.long(CURSOR) == case.long_in(BASE_IMAGE, left_by_the_copy & aes.OS_BUS_ADDR_MASK)


def test_the_whole_chain_walked_call_by_call():
    """ARGUMENT CLASS. Three calls, each starting where the one before ended (the ORACLE's end state carried):
    the first header, the second, NULL."""
    answered, pokes = [], find_machine(FIRST)
    for _call in range(3):
        walks = {"steered": STEERS_THE_CURSOR} if case.long_in(make_image(pokes), CURSOR) else {}
        result = aes.run_function(CART_FIND, (1,), pokes, **walks)
        answered.append(result.long_answer())
        pokes = case.continued(result)
    assert answered == [FIRST, SECOND, 0]


# ---- the registry -----------------------------------------------------------------------------------------------------
aes.register("no cartridge", CART_INIT, (), aes.leaf_machine(onto=STALE_CURSOR))
aes.register("the chain's end", CART_FIND, (1,), find_machine(0))
aes.register(f"{ARGUMENT_CLASS}: the first header, no fill", CART_FIND, (0,), find_machine(FIRST))
aes.register(f"{ARGUMENT_CLASS}: the first header into the DTA", CART_FIND, (1,), find_machine(FIRST))
aes.register(f"{ARGUMENT_CLASS}: the last header into the DTA", CART_FIND, (1,), find_machine(SECOND))
