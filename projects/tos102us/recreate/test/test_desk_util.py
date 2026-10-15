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


# ==== BAND 6 WAVE 4, group G1: THE SHOW / PRINT ENGINE — desk_show_file `$fed61e`, desk_print_file `$fed624` ======
# HELD AT TIER 1 THROUGH ITS TWO BUILT-INS ALONE (ruling R-W4-5): the engine `$fed632` and its seven other `bsr`-only
# parts are static C with no signature, pinned by these cases' arms.
#   * EVERY ARRIVAL IS A CHAIN'S, ITS GEMDOS REPLAYED from the ROM's own run in place (`aes_deskutil.in_place` over
#     `aes_deskdir.in_place`, the REPLAYED label): the viewer's waits taken in AT ITS NAMED STOPS — the chain's own
#     blank, or (the fix pass) another key typed there, as a hand types it —, the printer's alert answered at its idles
#     by a click, the bytes the ROM's Fread read LAID where it read them (BUFFER_LAID). A case that reaches the
#     printer's alert is a row that switches; the rest are the plain differential.
#   * A LABELLED CLASS (SCRIPTED, in the id) is the same machine with GEMDOS answering a script of the case's own: the
#     arms no file of the model's disks and no run reaches — a file of 4,096 bytes and more, the printer's PRINTED
#     arm (reached by slice H's two "printed" chains, NOT REPLAYABLE AT TIER 1: a printed file is two calls a byte, the
#     ~1,060 of DESKTOP.INF past the recorder's 46), a printer answering 99, the RS232 port, a failed Malloc — and one
#     STATE NO ROM RUN LEAVES (the stale words with a full count). What the script makes the ROM do is read back off
#     its own ledger (`made`).
#   * THE BIOS AND THE XBIOS ARE REAL on both shores (Bconout, Setprt): the ROM's trap's register-save frame under
#     savptr is dropped (`aes_deskleaves.savptr_frame`, as the door cases drop it).
import functools                        # noqa: E402
from collections import namedtuple      # noqa: E402

import aes_boot                         # noqa: E402
import aes_desk                         # noqa: E402
import aes_deskarrive as arrive         # noqa: E402
import aes_deskfun as fun               # noqa: E402
import aes_deskleaves                   # noqa: E402
import aes_event                        # noqa: E402
from harness import addrs               # noqa: E402

SHOW_FILE, PRINT_FILE = du.UNIT_M_WAVE_4
SHOWN, NOT_READY = "file: shown, a key at its end", aes_desk.NOT_READY
LONG_SHOWN = "files: the long file shown, a blank at each page's end and at its end"
SHOWN_AGAIN = aes_desk.SHOWN_AGAIN
UTIL = du.UTIL
AT_A_PAGE_S_END = aes_desk.STOPS[aes_desk.VIEWER_AT_A_PAGE_S_END]
AT_THE_FILE_S_END = aes_desk.STOPS[aes_desk.VIEWER_AT_THE_FILE_S_END]
W = aes.WORD_BYTES
SCAN_SPACE, SCAN_C, SCAN_Q = aes_desk.SCAN_SPACE, aes_desk.SCAN_C, aes_desk.SCAN_Q
# Crawio's answers for a key: its scan code in the high word, its ASCII in the low byte (the ROM's own run's own: a
# blank answers $390020).
def crawio_key(scan, ascii_):
    return scan << 16 | ascii_


BLANK_KEY = crawio_key(SCAN_SPACE, UTIL["VIEWER_NEXT_PAGE"])
LOWER_Q, CONTROL_C = crawio_key(SCAN_Q, ord("q")), crawio_key(SCAN_C, addrs.CON_ETX)
PRINTED, NOT_PRINTED, NO_KEY = -1, 0, 0                 # Cprnout's answers; Crawio's where no key is there
EFILNF = aes.signed(addrs.parse(aes.INCLUDE / "gemdos" / "process.h")["GEMDOS_EFILNF"], bits=32)
FULL_BUFFER_BUDGET = 40_000_000        # ...a whole buffer of 4,096 bytes drawn in one line
RETRIED_BUDGET = 2_500_000             # the printer retried, then cancelled: the derivation spent 359,926 (5 N..10 N)


def typed(*scans):
    """A key typed at a stop as a hand types it: each make code in turn (a modifier held first), the breaks after."""
    return (*(aes_boot.ikbd(scan) for scan in scans), *(aes_boot.ikbd(scan | aes_desk.KEY_RELEASED) for scan in reversed(scans)))


BLANK, Q, X = typed(SCAN_SPACE), typed(SCAN_Q), typed(aes_desk.SCAN_X)
RETURN, F1, CTRL_C = typed(aes_desk.SCAN_RETURN), typed(aes_desk.SCAN_F1), typed(aes_desk.SCAN_CONTROL, SCAN_C)
SHOWN_WAITS = (du.Wait(AT_THE_FILE_S_END, BLANK),)
LONG_SHOWN_WAITS = (du.Wait(AT_A_PAGE_S_END, BLANK), du.Wait(AT_A_PAGE_S_END, BLANK), du.Wait(AT_THE_FILE_S_END, BLANK))
WAITS = {SHOWN: SHOWN_WAITS, LONG_SHOWN: LONG_SHOWN_WAITS, SHOWN_AGAIN: SHOWN_WAITS}


def at_the_first_more(*keys):
    """The long file's keys: each of `keys` typed at a page's end in turn, from its first "-MORE-"."""
    return tuple(du.Wait(AT_A_PAGE_S_END, key) for key in keys)


def _button(text):
    return fun.clicked(fun.alert_button_point(text), -1)


def _clicks_waits(texts):
    return tuple(du.Wait(None, reception) for text in texts for reception in _button(text).receptions(NOT_READY))


def _clicks_at_idle(texts):
    at_idle = {}
    for text in texts:
        at_idle.update({len(at_idle) + idle: interrupt for idle, interrupt in _button(text).at_idle(NOT_READY).items()})
    return at_idle


@functools.cache
def engine_replay(name, chain, clicks=(), waits=None):
    """The arrival, and the ROM's own run of the engine in place — the chain's own keys at its stops (or `waits`, a
    case's own hand there), `clicks` (alert buttons) at its idles: `(arrival, aes_deskdir.Replay)`."""
    arrived = arrive.arrival(name, chain)
    return arrived, du.in_place(arrived, (WAITS.get(chain, ()) if waits is None else waits) + _clicks_waits(clicks))


EngineCase = namedtuple("EngineCase", "name chain clicks why script laid budget made waits hand",
                        defaults=((), None, None, None, None, None, None, None))
EngineCase.__doc__ = """A case of the engine: `name` at the arrival of `chain` — the printer's alert answered by its
`clicks` (button texts; a row that switches), its viewer's stops by `waits` (a hand of its own, said in `hand`;
None: the chain's own) —, or, A LABELLED CLASS where `why` says it, the same machine with GEMDOS answering
`script(the run in place's answers)` and `laid`: `(what, (arrival, buffer) -> pokes)`, machine state laid (`LAID` in
the id). `budget`: the plain run's instructions, or the row's derivation budget, where the chain step's own does not
serve. `made`: the GEMDOS calls, in order — the arm its hand or script takes, read off the ROM's ledger."""


def engine_label(each):
    scripted = ", SCRIPTED" if each.script else ""
    said = f"{short_of(each.name)} — " + (f"ARGUMENT CLASS ({each.why}{scripted}), over " if each.why else "")
    said += f"arrival 0 of {each.chain} [{du.REPLAYED}; {du.BUFFER_LAID}]"
    said += f"; {each.hand} (the chain's own key in its place)" if each.hand else ""
    said += f" [{da.LAID}: {each.laid[0]}]" if each.laid else ""
    said += f"; the alert's {' then '.join(each.clicks)} clicked" if each.clicks else ""
    return said + (da.ARGUMENT_CLASS if each.why else "")


def short_of(name):
    return name.removeprefix("AES_ROM_").lower()


def _the_buffer(replay):
    """The buffer the ROM's Malloc answered: where the engine reads."""
    return replay.answers[replay.functions.index(du.MALLOC)]


# What ends the ROM's run in place on the printer's machine where a class's own run never reaches the alert.
IN_PLACE_CLICKS = {NOT_READY: ("Cancel",)}


def engine_layers(each):
    """The case's arrival, the ROM's run of it in place, and what is laid over the arrival's megabyte: the replay
    (or the class's script) and the class's own machine state."""
    arrived, replay = engine_replay(each.name, each.chain, each.clicks or IN_PLACE_CLICKS.get(each.chain, ()), each.waits)
    script = each.script(replay.answers) if each.script else None
    laid = each.laid[1](arrived, _the_buffer(replay)) if each.laid else {}
    return arrived, replay, case.merge_pokes(du.replayed(replay, script), laid)


def engine_run(each):
    """THE CASE AT TIER 1 — the row through the companion (its idles the clicks'), or the plain differential (its
    budget the chain step's own, where the case declares none): the image the C left."""
    arrived, _replay, layers = engine_layers(each)
    pokes = case.merge_pokes(da.machine_of(arrived), layers)
    if not each.clicks:
        budget = each.budget or arrived.budget
        return aes.run_function(each.name, arrived.arguments, pokes, hook=du.show_hook, poison=False, max_insns=budget,
                                dropped_windows=(*aes.LINE_F_MASK_WINDOW, *aes_deskleaves.savptr_frame(arrived.boot.ram))).final
    at_idle = _clicks_at_idle(each.clicks)
    row = aes_event.woken_row(engine_label(each), each.name, arrived.arguments, lambda: pokes, at_idle, objects=True,
                              answered=True, budget=each.budget)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert the_rom_s.idles == len(at_idle), f"{engine_label(each)}: the ROM's run idles {the_rom_s.idles} time(s)"
    return ran.image


# ---- the calls each arm makes ------------------------------------------------------------------------------------------
MORE_PROMPT = len(b"-MORE-")
END_PROMPT = len(b"-END OF FILE-")


@functools.cache
def _to_the_first_more_key():
    """The long file's run in place: its calls up to the key wait of its first "-MORE-" (past the six Crawios of its
    text)."""
    replay = engine_replay(SHOW_FILE, LONG_SHOWN)[1]
    at = [index for index, called in enumerate(replay.functions) if called == du.CRAWIO][MORE_PROMPT]
    return replay.functions[:at]


def _made_past_the_first_more(*calls):
    return lambda: (*_to_the_first_more_key(), *calls)


ERASED, CLOSED, FREED = 0, 0, 0
# EACH SCRIPT RUNS ON PAST ITS ARM: answers the ROM's run never asks for (both shores leave them unread), so that a C
# taking ANOTHER arm comes to its return too — its ledger then differs, an assertion. (Past the script and its spares
# the replay's twin refuses by name and answers a way out besides: `aes_deskutil.WAYS_OUT`.)
CRAWIO, CCONWS, CPRNOUT, CAUXOUT = du.CRAWIO, du.CCONWS, du.CPRNOUT, du.CAUXOUT
FOPEN, MALLOC, FREAD, FCLOSE, MFREE = du.FOPEN, du.MALLOC, du.FREAD, du.FCLOSE, du.MFREE
QUIT_MADE = (CRAWIO, CCONWS, FCLOSE, MFREE)             # the key, the line erased, the file closed, the buffer freed
MORE_AGAIN = (CRAWIO, CCONWS, *(CRAWIO,) * MORE_PROMPT)  # a key that goes on: erased, then "-MORE-" again
MORE_MADE = (*(CRAWIO,) * MORE_PROMPT, CRAWIO, CCONWS)  # "-MORE-", its key, the line erased
PRINT_OPENED = (FOPEN, MALLOC, FREAD)
DONE_MADE = (FCLOSE, MFREE)
ENDED = (0, 0, *(0,) * END_PROMPT)                      # CR, LF and "-END OF FILE-" by Crawio
MORE_SAID = (0,) * MORE_PROMPT                          # "-MORE-" written, its six Crawios answered


A_LINE_S_BYTES = bytes((0x41, 0xC4, 0xFF, 0x42))      # 'A', a byte >= $80, $FF (-1 as a signed byte), 'B'
BUFFER_BYTES = UTIL["SHOW_BUFFER_BYTES"]


def _a_full_buffer_of_one_line(arrived, buffer):
    """LAID: the buffer's 4,096 bytes one line — A_LINE_S_BYTES over and over, no line feed."""
    return {buffer: A_LINE_S_BYTES * (BUFFER_BYTES // len(A_LINE_S_BYTES))}


LINE_BYTES = 128                        # a line of 127 'A's and its line feed: 32 to the buffer, so a page and a half


def _a_full_buffer_of_lines(arrived, buffer):
    """LAID: the buffer's 4,096 bytes 32 lines of LINE_BYTES — the second page runs past its end."""
    return {buffer: (b"A" * (LINE_BYTES - 1) + bytes((addrs.CON_LF,))) * (BUFFER_BYTES // LINE_BYTES)}


STALE_WORD = 0xA5A5


def _the_engine_s_words_stale(arrived, buffer):
    """LAID — A STATE NO ROM RUN LEAVES (reviewer A): the index and the end-of-file flag stale, the count a whole
    buffer's (4,096, the index the engine starts at). The ROM sets `$9558` only where an Fread answered short
    (`$fed710 cmp.w a6,d0`), so a flag set with a full count is no run's; the run that DOES leave them stale is
    SHOWN_AGAIN's arrival (an arrival case) — but only this state shows the engine's own clear of the flag: one left
    set would end the file before its first read."""
    first = db.DESK_GLOBALS["AES_SHOW_INDEX"]
    assert (db.DESK_GLOBALS["AES_SHOW_AT_EOF"], db.DESK_GLOBALS["AES_SHOW_COUNT"]) == (first + W, first + 2 * W)
    return {first: struct.pack(">3H", STALE_WORD, STALE_WORD, BUFFER_BYTES)}


def _three_bytes(arrived, buffer):
    """LAID: the buffer's first three bytes 'A', $C4, a line feed."""
    return {buffer: bytes((0x41, 0xC4, addrs.CON_LF))}


def _the_rs232_port(arrived, buffer):
    """LAID: the printer's configuration with its RS232 bit (Setprt's word) — the three bytes laid too."""
    config = case.word_in(arrived.boot.ram, addrs.PRINTER_CONFIG)
    return {addrs.PRINTER_CONFIG: struct.pack(">H", config | UTIL["SETPRT_RS232"]), **_three_bytes(arrived, buffer)}


def PRINTED_ON(left):
    """The way out of a print: a key check and a byte printed for each of the `left` bytes, then CR and LF printed."""
    return (*(NO_KEY, PRINTED) * left, PRINTED, PRINTED)


def _print_script(*per_byte_then):
    """Over the printer's arrival: Fopen, Malloc and an Fread of three, then `per_byte_then`."""
    def script(answers):
        return (*answers[:2], 3, *per_byte_then)
    return script


ENGINE_CASES = (
    # ---- ARRIVALS: the INF shown, a key at its end; the long file shown a page at a time; the printer not ready —
    # Cancel, and Retry (not ready again) then Cancel; the INF shown AGAIN, the engine's words as the first show left
    # them (-1, 1, 529)
    EngineCase(SHOW_FILE, SHOWN), EngineCase(SHOW_FILE, LONG_SHOWN),
    EngineCase(PRINT_FILE, NOT_READY, ("Cancel",)),
    EngineCase(PRINT_FILE, NOT_READY, ("Retry", "Cancel"), budget=RETRIED_BUDGET),
    EngineCase(SHOW_FILE, SHOWN_AGAIN),
    # ---- THE VIEWER'S KEYS at its first "-MORE-", TYPED AT THE STOP (the long file's chain, arrivals): q (upcased: Q),
    # ^C (Control held), Return (a line, then "-MORE-" again: q), F1 (ASCII 0: the wait goes on — `tst.w` — then q),
    # x (nothing: "-MORE-" again — q)
    EngineCase(SHOW_FILE, LONG_SHOWN, waits=at_the_first_more(Q), hand="q typed at the first -MORE-",
               made=_made_past_the_first_more(*QUIT_MADE)),
    EngineCase(SHOW_FILE, LONG_SHOWN, waits=at_the_first_more(CTRL_C), hand="^C typed at the first -MORE-",
               made=_made_past_the_first_more(*QUIT_MADE)),
    EngineCase(SHOW_FILE, LONG_SHOWN, waits=at_the_first_more(RETURN, Q), hand="Return typed at the first -MORE-, then q",
               made=_made_past_the_first_more(*MORE_AGAIN, *QUIT_MADE)),
    EngineCase(SHOW_FILE, LONG_SHOWN, waits=at_the_first_more(F1, Q), hand="F1 (ASCII 0) typed at the first -MORE-, then q",
               made=_made_past_the_first_more(CRAWIO, *QUIT_MADE)),
    EngineCase(SHOW_FILE, LONG_SHOWN, waits=at_the_first_more(X, Q), hand="x typed at the first -MORE-, then q",
               made=_made_past_the_first_more(*MORE_AGAIN, *QUIT_MADE)),
    # ---- THE BUFFER: a file of 4,096 bytes and one more (two Freads: the buffer read whole, then one byte short), its
    # bytes >= $80 and $FF among them; a file of EXACTLY 4,096 (its refill reads 0 — and the ROM shows the buffer
    # again from its first byte, `$fed6f6..$fed734`, the index never compared with the new count: reviewer A's A1)
    EngineCase(SHOW_FILE, SHOWN, why="a file of 4,097 bytes, one line",
               script=lambda answers: (*answers[:3], BUFFER_BYTES, 1, *ENDED, BLANK_KEY, CLOSED, FREED),
               laid=("a full buffer of one line", _a_full_buffer_of_one_line), budget=FULL_BUFFER_BUDGET,
               made=lambda: (FOPEN, MALLOC, CCONWS, FREAD, FREAD, *(CRAWIO,) * len(ENDED), CRAWIO, *DONE_MADE)),
    EngineCase(SHOW_FILE, SHOWN, why="a file of 4,096 bytes: its refill reads 0, the buffer shown again",
               script=lambda answers: (*answers[:3], BUFFER_BYTES, *MORE_SAID, BLANK_KEY, ERASED, 0, *MORE_SAID, LOWER_Q,
                                       ERASED, CLOSED, FREED),
               laid=("a full buffer of 32 lines", _a_full_buffer_of_lines), budget=FULL_BUFFER_BUDGET,
               made=lambda: (FOPEN, MALLOC, CCONWS, FREAD, *MORE_MADE, FREAD, *MORE_MADE, *DONE_MADE)),
    # ---- THE ENGINE'S WORDS STALE at its entry: a state no ROM run leaves (above); and the run that leaves them
    # stale (SHOWN_AGAIN's, the flag 1) with Fopen failing — the flag cleared before the open (reviewer A's A6)
    EngineCase(SHOW_FILE, SHOWN, why="GEMDOS the run in place's own",
               laid=("the engine's words stale, its count 4,096: a state no ROM run leaves", _the_engine_s_words_stale)),
    EngineCase(SHOW_FILE, SHOWN_AGAIN, why="Fopen answering EFILNF", script=lambda answers: (EFILNF, 0),
               made=lambda: (FOPEN,)),
    # ---- THE ENGINE'S FAILURES: not opened; opened, no buffer (the file left open: the ROM's)
    EngineCase(SHOW_FILE, SHOWN, why="Fopen answering EFILNF", script=lambda answers: (EFILNF, 0), made=lambda: (FOPEN,)),
    EngineCase(SHOW_FILE, SHOWN, why="Malloc answering 0", script=lambda answers: (answers[0], 0),
               made=lambda: (FOPEN, MALLOC)),
    # ---- THE PRINTER (the not-ready machine): three bytes printed, then CR LF; q and ^C between two bytes; a printer
    # answering 99 (PRINT_ABANDONED: abandoned, no alert) — at a byte, and at the CR (the LF tried all the same: A2);
    # the RS232 port
    EngineCase(PRINT_FILE, NOT_READY, why="three bytes printed", laid=("three bytes", _three_bytes),
               script=_print_script(*(NO_KEY, PRINTED) * 3, PRINTED, PRINTED, CLOSED, FREED),
               made=lambda: (*PRINT_OPENED, *(CRAWIO, CPRNOUT) * 3, CPRNOUT, CPRNOUT, *DONE_MADE)),
    EngineCase(PRINT_FILE, NOT_READY, why="q after the first byte", laid=("three bytes", _three_bytes),
               script=_print_script(NO_KEY, PRINTED, LOWER_Q, PRINTED, *PRINTED_ON(1), CLOSED, FREED),
               made=lambda: (*PRINT_OPENED, CRAWIO, CPRNOUT, CRAWIO, *DONE_MADE)),
    EngineCase(PRINT_FILE, NOT_READY, why="^C before the first byte", laid=("three bytes", _three_bytes),
               script=_print_script(CONTROL_C, PRINTED, *PRINTED_ON(2), CLOSED, FREED),
               made=lambda: (*PRINT_OPENED, CRAWIO, *DONE_MADE)),
    EngineCase(PRINT_FILE, NOT_READY, why="Cprnout answering 99", laid=("three bytes", _three_bytes),
               script=_print_script(NO_KEY, UTIL["PRINT_ABANDONED"], *PRINTED_ON(2), CLOSED, FREED),
               made=lambda: (*PRINT_OPENED, CRAWIO, CPRNOUT, *DONE_MADE)),
    EngineCase(PRINT_FILE, NOT_READY, why="Cprnout answering 99 at the CR, the LF printed", laid=("three bytes", _three_bytes),
               script=_print_script(*(NO_KEY, PRINTED) * 3, UTIL["PRINT_ABANDONED"], PRINTED, CLOSED, FREED),
               made=lambda: (*PRINT_OPENED, *(CRAWIO, CPRNOUT) * 3, CPRNOUT, CPRNOUT, *DONE_MADE)),
    EngineCase(PRINT_FILE, NOT_READY, why="the RS232 port", laid=("the RS232 bit and three bytes", _the_rs232_port),
               script=_print_script(*(NO_KEY, PRINTED) * 3, PRINTED, PRINTED, CLOSED, FREED),     # (Cauxout's answer unread)
               made=lambda: (*PRINT_OPENED, *(CRAWIO, CAUXOUT) * 3, CAUXOUT, CAUXOUT, *DONE_MADE)),
)
ENGINE_BY_LABEL = {engine_label(each): each for each in ENGINE_CASES}
assert len(ENGINE_BY_LABEL) == len(ENGINE_CASES), "two engine cases of one name"


@pytest.mark.parametrize("name", ENGINE_BY_LABEL)
def test_the_engine_from_its_arrival_with_gemdos_replayed_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine from the same entry, GEMDOS replayed on both shores — its answer
    at its width, every byte of the megabyte (the ledger among them) — and THE CALLS MADE: an arrival's the ROM's run
    in place's own, a class's the arm it names."""
    each = ENGINE_BY_LABEL[name]
    made = each.made() if each.made else engine_layers(each)[1].functions
    assert du.calls(engine_run(each)) == tuple(made)


def test_a_call_past_the_replay_s_script_and_its_spares_is_refused_by_name_and_answered_a_way_out():
    """THE SPENT REPLAY (the fix pass): where the script's pointer has reached SPENT_AT's longword — the run's answers
    and the spares all given — the engine's twin raises `address_hook.RefusedAnswering` (the case's failure, by name)
    and answers the function's way out in turn: Crawio Q, then ^C (a C deaf to one hears the other); and the hook
    hands the C that answer, not REFUSED_ANSWER."""
    import address_hook
    image = bytearray(du.SPENT_AT + aes.LONG_BYTES)
    spent = struct.pack(">I", du.SHOW.script.first)
    image[du.SHOW.script.pointer_at:du.SHOW.script.pointer_at + aes.LONG_BYTES] = spent
    image[du.SPENT_AT:du.SPENT_AT + aes.LONG_BYTES] = spent
    twin = du.SHOW_HANDLERS[gemdos.rom_handler(CRAWIO)]
    raised = []
    answers = [address_hook.answered_or_recorded(lambda: twin(image, 0, 0), "Crawio", raised) for _turn in range(2)]
    assert sorted(answers) == sorted(du.WAYS_OUT[CRAWIO]) and len(raised) == 2
    assert all(isinstance(why, address_hook.RefusedAnswering) and "past the ROM run's answers" in str(why) for _key, why in raised)


def test_every_built_in_has_a_case_at_an_arrival_of_its_own():
    assert {each.name for each in ENGINE_CASES if not each.why} == set(du.UNIT_M_WAVE_4)


# THE ENGINE'S EIGHT PARTS (R-W4-5): static C — no core of their own in the library, no table entry, held in neither
# list — and every one entered by a chain the cases' arrivals are taken from (`aes_desk.reach()`, never by a name).
ENGINE_PARTS = tuple(f"AES_ROM_DESK_{part}" for part in ("SHOW_OR_PRINT", "SHOW_NEXT_BYTE", "VIEWER_LOOP", "VIEWER_MORE",
                                                         "VIEWER_PAGE", "VIEWER_LINE", "RAWCIO_STRING", "PRINT_CHAR"))


def test_the_engine_s_parts_are_static_c_held_through_the_built_ins_cases():
    from harness import _lib
    import routines
    _verdicts, linef_table = da.table_verdicts(du.UNIT_M_WAVE_4)
    assert not [part for part in ENGINE_PARTS if hasattr(_lib, routines.core_symbol(part))]
    held = set(linef_table.LINKED_AND_NOT_FLIPPED) | set(linef_table.LINKED_HELD_NO_TABLE_ENTRY)
    assert not set(ENGINE_PARTS) & held
    assert not {entry.target for entry in linef_table.entries()} & {getattr(addrs, part) for part in ENGINE_PARTS}
    table, arrived_from = aes_desk.reach(), {SHOWN, LONG_SHOWN, NOT_READY, SHOWN_AGAIN}
    assert all(set(table[getattr(addrs, name)]) & arrived_from for name in (*ENGINE_PARTS, *du.UNIT_M_WAVE_4))


# THE PRINTER'S MACHINE is made from the Show / Print / Cancel alert's chain (`aes_desk.MACHINES`).
MADE_FROM = {aes_desk.PRINTER_ON_LINE: aes_desk.SHOW_PRINT_ALERT}


def _chains_under(chain):
    """The chain and every chain its machine was walked from."""
    under = []
    while chain is not None:
        if chain in aes_desk.CHAINS:
            under.append(chain)
            chain = aes_desk.CHAINS[chain].after
        else:
            chain = MADE_FROM.get(chain)
    return under


def test_no_arrival_of_the_engine_stands_on_the_move16_stand_in():
    """MEASURED (the MOVE16 rule): no chain under any arrival the cases take took a Line-F word by hand."""
    assert not {chain: aes_desk.taken_by_hand(chain) for arrived_from in (SHOWN, LONG_SHOWN, NOT_READY, SHOWN_AGAIN)
                for chain in _chains_under(arrived_from) if aes_desk.taken_by_hand(chain)}


def test_the_built_ins_answer_a_word_read_by_no_rom_caller():
    """D0: each answers the engine's word (held on every case); sh_cmd's two `jsr`s read neither (`answer_readers`)."""
    assert not any(db.answer_readers(getattr(addrs, name)) for name in du.UNIT_M_WAVE_4)


def test_the_strings_the_engine_names_are_the_rom_s_and_the_printer_s_alert_merges_nothing():
    """The viewer's four strings; and the alert fm_show is handed `$00000001` as its values: its text (17, merged
    into AES_FM_SHOW_ALERT on the not-ready machine) holds no conversion, so the pointer is never read — buttons
    Cancel, Retry (PRINTER_ALERT_CANCEL is the first)."""
    def text(at, ram=BASE_IMAGE):
        return bytes(ram[at:at + 64]).split(b"\0")[0]
    assert [text(UTIL[name]) for name in ("VIEWER_WRAP_ON", "VIEWER_ERASE_LINE", "VIEWER_MORE", "VIEWER_END")] == [
        b"\x1bv", b"\x1bl", b"-MORE-", b"-END OF FILE-"]
    fmdo = aes.header_constants("fmdo.h")
    alert = bytes(aes_desk.walked(NOT_READY).machine.ram[fmdo["AES_FM_SHOW_ALERT"]:][:fmdo["AES_FM_SHOW_ALERT_BYTES"]])
    alert = alert.split(b"\0")[0]
    assert b"%" not in alert and alert.endswith(b"[Cancel|Retry]")


def test_the_engine_is_linked_and_unbound(blob):
    arrive.unbound(blob, du.UNIT_M_WAVE_4)
