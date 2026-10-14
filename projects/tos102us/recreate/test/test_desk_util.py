"""THE CARTRIDGE'S DIRECTORY SEARCH (`src/desk/deskutil.c`; band 6 wave 2, group G2, unit M, ruling R-W2-1): cart_sfirst
`$fed522` and cart_snext `$fed534`, HELD AT TIER 1 — LINKED, AND NOTHING BOUND.

  * NO CHAIN REACHES EITHER: their one caller, pn_active `$fdfc3c`, takes them where a path's spec drive is 'c' — the
    cartridge's window, which no machine of ours opens (the oracle's bus answers 0 at the cartridge port, whatever the
    image holds: `test_aes_cart.py`). TRIED: every one of pn_active's 29 reaching chains hands it an "A:\\" spec. So
    EVERY CASE IS A LABELLED ARGUMENT CLASS over pn_active's own arrival ("A: File > Open"): the DTA pointer and the
    attribute word pn_active would hand cart_sfirst there — and for cart_snext's found arm the cursor LAID at a
    ROM-format cartridge header chain in RAM (test_aes_cart.py's staging; its id says LAID).
  * cart_sfirst's FOUND ARM IS UNPINNED BY A DIFFERENTIAL: cart_sfirst calls cart_init, which reads the port THROUGH
    the bus — 0 on the oracle — so every run of it ends at the chain's end. What is held instead is the C ALONE over
    a host image with the application magic at the port (a reading, said as such).
  * D0 AT RETURN: both answer a word, held to the ROM's D0.w on every case; cart_sfirst's own is cart_snext's.
  * NEITHER YIELDS: every case is the kit's plain differential over the arrival's megabyte.
"""
import struct

import pytest

from harness import BASE_IMAGE

import aes
import aes_deskact as da
import aes_deskbind as db
import aes_deskfpd  # noqa: F401 — pn_active's declared frame, whose arrival every case runs over
import aes_deskutil as du
import case
import gemdos

Case, UNPOISONED = da.Case, da.UNPOISONED
SFIRST, SNEXT, ACTIVE = "AES_ROM_CART_SFIRST", "AES_ROM_CART_SNEXT", "AES_ROM_PN_ACTIVE"
OPEN_A = "A: File > Open"
CART = aes.header_constants("cart.h")
CURSOR, DTA_KEPT = CART["AES_CART_CURSOR"], CART["AES_CART_DTA"]
DTA_POINTER = db.DESK_GLOBALS["DESK_DTA_POINTER"]
PNODE_ATTR, PNODE_SPEC = du.FPD["PNODE_ATTR"], du.FPD["PNODE_SPEC"]     # pn_active's path: its attributes, its spec
DTA_BYTES = 44


def _desk(arrived):
    return case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & da.BUS


def _the_dta(arrived):
    return case.long_in(arrived.boot.ram, _desk(arrived) + DTA_POINTER)


def _what_pn_active_hands(arrived):
    """cart_sfirst's frame as pn_active pushes it on drive 'c': the desk's DTA pointer, then the path's attributes."""
    path = arrived.arguments[0] & da.BUS
    return (_the_dta(arrived), case.word_in(arrived.boot.ram, path + PNODE_ATTR))


# THE STAGED CHAIN (test_aes_cart.py's shape, in group G2's band): two ROM-format headers, the first naming the second.
def _header(following, time, date, size, name):
    return struct.pack(">IIIHHI", following, 0x00FA_1000, 0x00FA_2000, time, date, size) + name.ljust(14, b"\0")


FIRST, SECOND = du.BAND_AT, du.BAND_AT + 0x40
CHAIN = {FIRST: _header(SECOND, 0x6A31, 0x1521, 0x0001_2345, b"CARTPRG.PRG"),
         SECOND: _header(0, 0x0842, 0x0E21, 77, b"ABCDEFGH.TOS")}       # a full 8.3 name: twelve bytes and its NUL


def _chain_laid(cursor):
    """LAID: the cursor at `cursor` of the staged chain, the kept DTA the desk's (as cart_sfirst keeps it)."""
    def laid(arrived):
        return {**CHAIN, CURSOR: struct.pack(">I", cursor), DTA_KEPT: struct.pack(">I", _the_dta(arrived))}
    return laid


AT_THE_HEAD, AT_THE_LAST = ("the cursor at a staged header chain's head", _chain_laid(FIRST)), \
    ("the cursor at its last header", _chain_laid(SECOND))
STALE_CURSOR = ("the cursor stale ($a5a5a5a5): cart_init sets it", lambda _arrived: {CURSOR: struct.pack(">I", 0xA5A5A5A5)})

CASES = (
    Case(SFIRST, OPEN_A, over=ACTIVE, why="the DTA and attributes pn_active hands on 'c': no cartridge, the chain's end",
         arguments=_what_pn_active_hands),
    Case(SFIRST, OPEN_A, over=ACTIVE, why="...over a stale cursor: cart_init's, then cart_find's at NULL",
         arguments=_what_pn_active_hands, laid=STALE_CURSOR),
    Case(SFIRST, OPEN_A, over=ACTIVE, why="...over a cursor at a staged chain: cart_init's NULL, the chain not searched",
         arguments=_what_pn_active_hands, laid=AT_THE_HEAD, steered=UNPOISONED),
    Case(SNEXT, OPEN_A, over=ACTIVE, why="the machine's own cursor NULL: the chain's end, AES_DOS_AX 18", arguments=()),
    Case(SNEXT, OPEN_A, over=ACTIVE, why="a header found: its entry laid into the kept DTA, the cursor moved on",
         arguments=(), laid=AT_THE_HEAD, steered=UNPOISONED),
    Case(SNEXT, OPEN_A, over=ACTIVE, why="the last header found: the cursor NULL after it", arguments=(), laid=AT_THE_LAST,
         steered=UNPOISONED),
)
BY_LABEL = da.by_label(CASES)
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)


@EVERY_CASE
def test_a_routine_of_the_unit_over_pn_active_s_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine over pn_active's arrival's megabyte — every byte, the answer at
    its width."""
    da.held_plain(BY_LABEL[name])


def test_every_case_is_a_class_and_each_routine_has_cases():
    """No chain reaches the pair (the docstring): every case a labelled class, both routines held."""
    assert all(each.why for each in CASES)
    assert {each.name for each in CASES} == set(du.UNIT_M_WAVE_2)


def test_no_chain_reaches_either_routine_nor_hands_pn_active_a_cartridge_s_spec():
    """TRIED (lesson 1): the hands' reach table names no chain for either, and every arrival of pn_active the chains
    make is a GEMDOS drive's spec (the cartridge's arm, `$fdfc48 cmpi.b #'c'`, untaken). The first arrival of each
    chain is read: the spec's drive byte."""
    import aes_desk
    from harness import addrs
    table = aes_desk.reach()
    assert not table[addrs.AES_ROM_CART_SFIRST] and not table[addrs.AES_ROM_CART_SNEXT]

    def drive(chain):
        arrived = da.arrival(ACTIVE, chain)
        return arrived.boot.ram[(arrived.arguments[0] & da.BUS) + PNODE_SPEC]
    assert {drive(chain) for chain in table[addrs.AES_ROM_PN_ACTIVE]} == {ord("A")}


# ---- THE FOUND ARM OF cart_sfirst: A READING, THE C ALONE ----------------------------------------------------------------
def test_cart_sfirst_over_a_cartridge_at_the_port_finds_its_first_header__the_c_alone():
    """UNPINNED BY A DIFFERENTIAL (the oracle's port reads 0): the C over a HOST image with the application magic at the
    port and a chain behind it answers 1, keeps the DTA, lays the first header's entry there and moves the cursor to
    the header the first names."""
    dta = aes.BLOCKS_AT
    first = CART["CART_FIRST_HEADER"]
    following = first + 0x40
    pokes = case.merge_pokes({CART["CART_BASE"]: struct.pack(">I", CART["CART_APPLICATION_MAGIC"])},
                             {first: _header(following, 0x6A31, 0x1521, 0x1234, b"CARTPRG.PRG")})
    answer, image = gemdos.run_candidate_only(lambda lib, buf: lib.aes_cart_sfirst(buf, dta, 0x10), pokes)
    entry = CART["CART_DTA_ENTRY"]
    assert (answer, case.long_in(image, DTA_KEPT), case.long_in(image, CURSOR)) == (du.UTIL["CART_SNEXT_FOUND"], dta, following)
    assert bytes(image[dta + entry:dta + entry + 11]) == bytes.fromhex("6a31 1521 00001234") + b"CAR"


def test_the_port_reads_zero_on_the_oracle_s_machine():
    """WHY the found arm has no differential: the snapshot's port longword is 0, and no image byte reaches the bus there
    (`test_aes_cart.py` holds that by a run)."""
    assert case.long_in(BASE_IMAGE, CART["CART_BASE"]) == 0


# ---- D0 AT RETURN --------------------------------------------------------------------------------------------------------------
def test_both_answer_a_word_and_pn_active_reads_cart_sfirst_s_and_cart_snext_s():
    """D0: each answers a word (the C has it: held on every case); its one caller reads both (`answer_readers`)."""
    from harness import addrs
    assert all(db.answer_readers(getattr(addrs, name)) for name in du.UNIT_M_WAVE_2)


# ---- LINKED AND UNBOUND --------------------------------------------------------------------------------------------------------
def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_the_pair(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk)."""
    assert not db.bound_referrers(blob, du.UNIT_M_WAVE_2)


def test_the_table_s_entries_for_the_pair_stay_the_rom_s_and_no_registry_names_one():
    verdicts, linef_table = da.table_verdicts(du.UNIT_M_WAVE_2)
    assert verdicts == {name: linef_table.THE_ROM_S for name in du.UNIT_M_WAVE_2}
    assert set(du.UNIT_M_WAVE_2) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    assert not da.registered(du.UNIT_M_WAVE_2)
