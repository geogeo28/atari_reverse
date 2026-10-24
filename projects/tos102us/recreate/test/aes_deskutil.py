"""THE DESK'S UTILITIES — unit M (`src/desk/deskutil.c`; band 6 wave 2, group G2, ruling R-W2-1): the cartridge's
directory search `$fed522` / `$fed534` — their declared Alcyon frames and the unit's wave-2 list. The rest of the unit
is wave 4's."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG

# ---- band 6 wave 2, group G2 (unit M) ----
import aes_deskbind as _db
import layouts

UTIL = layouts.parse_constants((aes.INCLUDE / "desk" / "deskutil.h",), known=aes.CONSTANTS)
FPD = layouts.parse_constants((_db.GLOBALS_HEADER, aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)
# GROUP G2'S BAND of the AES's staged window (`$7ae80..$7b000`, the wave's G2 window): a laid cartridge chain.
BAND_OFFSET, BAND_BYTES = 0x2E80, 0x80
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_deskutil.py: group G2's laid cartridge chain")
# cart_sfirst's second word is the attribute word its caller hands as to dos_sfirst, read by nothing.
SIGNATURES_WAVE_2 = {
    "AES_ROM_CART_SFIRST": (aes.WORD_ANSWER, (LONG, WORD)),
    "AES_ROM_CART_SNEXT": (aes.WORD_ANSWER, ()),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_M_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# ---- end of group G2's wave-2 ----
# ---- band 6 wave 4, group G1 (unit M) ---- the show / print engine: its two built-ins with a table entry; the
# engine's eight `bsr`-only parts are static C with no signature (ruling R-W4-5)
SIGNATURES_WAVE_4 = {
    "AES_ROM_DESK_SHOW_FILE": (aes.WORD_ANSWER, (LONG,)),
    "AES_ROM_DESK_PRINT_FILE": (aes.WORD_ANSWER, (LONG,)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_4.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_M_WAVE_4 = tuple(SIGNATURES_WAVE_4)
UNIT_M_WAVE_4_HELD_AT_F4 = ()             # none: both built-ins FLIPPED at band 6 slice F4
SHOW_FILE, PRINT_FILE = UNIT_M_WAVE_4

# THE ENGINE'S GEMDOS, REPLAYED — wave 2's one mechanism: `aes_deskdir.in_place`'s walk (its named STOPS: the viewer
# waits for a key in a Crawio poll that never idles, so a wake is taken in at the stop where the chain's own hand
# gives it; its CAPTURES: what each Fread read), `aes_gemdosif.Recorder`'s trap, `aes_gemdosif.opened_record`'s
# handles — over THE ENGINE'S OWN FUNCTION TABLE: its nine functions, four of them the console's (Crawio, Cconws,
# Cprnout, Cauxout), which the copy engine's recorder (`aes_deskdir.ENGINE`) has no frame for — so a Recorder of the same
# class over this table, in the same band (`aes_loader.REPLAYED_AT`: a machine holds one replay). (One function table
# for both — the shared Recorder — is DEFERRED: the band's room, the fix pass's record.)
#   * WHAT Fread READ: the viewer and the printer read the buffer itself, which the copy engine never does, and the
#     recorder answers Fread's count but lays no byte: the bytes the ROM's Fread read are LAID where it read them,
#     before the run (`BUFFER_LAID`, in the case's id) — every model file is under 4,096 bytes, so a run reads once;
#   * PAST THE SCRIPT AND ITS SPARES the twin REFUSES BY NAME (`address_hook.RefusedAnswering`) and answers a WAY OUT
#     (`WAYS_OUT`: a key that ends the viewer and the print, a one-byte short read that ends the file), so a C that
#     calls on ends — and its case fails by that assertion, never by the watchdog's timeout.
import struct
from collections import namedtuple

from harness import addrs

import aes_deskdir as _cdir
import aes_event
import aes_gemdosif as _gd
import aes_loader
import case
import gemdos
from address_hook import RefusedAnswering

W, L = aes.WORD_BYTES, aes.LONG_BYTES
FOPEN, FREAD, FCLOSE = addrs.GEMDOS_FOPEN_FN, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FCLOSE_FN
MALLOC, MFREE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN
CRAWIO, CCONWS, CPRNOUT, CAUXOUT = (addrs.GEMDOS_CRAWIO_FN, addrs.GEMDOS_CCONWS_FN, addrs.GEMDOS_CPRNOUT_FN,
                                    addrs.GEMDOS_CAUXOUT_FN)
SHOW_FRAME_BYTES = {FOPEN: L + W, MALLOC: L, FREAD: W + 2 * L, FCLOSE: W, MFREE: L, CRAWIO: W, CCONWS: L, CPRNOUT: W,
                    CAUXOUT: W}
SHOW_HANDLER_ROOM = 0x98                # the handler over this table: 150 bytes
SHOW_BAND_END = _gd.BAND_AT + _gd.BAND_BYTES
SHOW_CALLS = 46                         # the most the band holds; the long file shown makes 38 (measured)
SHOW = _gd.Recorder(addrs.VECTOR_TRAP_GEMDOS, aes_loader.REPLAYED_AT, SHOW_HANDLER_ROOM, SHOW_FRAME_BYTES,
                    entries=SHOW_CALLS, parked=_cdir.PARKED)
SPENT_AT = SHOW.end                     # a longword: the script's address past the last answer staged (its spares too)
assert SPENT_AT + L <= SHOW_BAND_END, "the engine's recorder runs out of the band it borrows"
ONE_BYTE_SHORT = 1                      # an Fread of one byte: a short read, the file's end at the next byte
# ...each function's, in turn, call after call: Q then ^C (either ends the viewer and the print — a C deaf to one hears
# the other), a one-byte short read, no buffer; every other function an error (Fopen's ends the engine)
WAYS_OUT = {CRAWIO: (UTIL["VIEWER_QUIT"], addrs.CON_ETX), FREAD: (ONE_BYTE_SHORT,), MALLOC: (0,)}
SPENT_ANSWERS = (_cdir.SPARE_ANSWER,)


def _refusing_once_spent(function):
    """`SHOW`'s twin for `function`, which REFUSES BY NAME a call past the script and its spares (`SPENT_AT`) and
    answers it the function's way out."""
    answering, ways_out, spent = SHOW.twin(function), WAYS_OUT.get(function, SPENT_ANSWERS), [0]

    def handler(buf, arguments, argument_bytes):
        if case.long_in(buf, SHOW.script.pointer_at) >= case.long_in(buf, SPENT_AT):
            spent[0] += 1
            raise RefusedAnswering(f"the C called GEMDOS function {function} past the ROM run's answers and their "
                                   f"spares: a call the ROM's run never made", ways_out[spent[0] % len(ways_out)])
        return answering(buf, arguments, argument_bytes)
    return handler


SHOW_HANDLERS = {gemdos.rom_handler(function): _refusing_once_spent(function) for function in SHOW_FRAME_BYTES}
REPLAYED = _cdir.REPLAYED_ANSWERS
BUFFER_LAID = "the bytes the ROM's Fread read, laid where it read them"


def show_hook():
    """The host twins bound as `aes.run_function`'s `hook`."""
    return gemdos.bound_handlers(SHOW_HANDLERS)


def bind_show_in_a_child(lib):
    """...and in a row's child (`aes_gemdosif.bind_handlers_in_a_child`)."""
    _gd.bind_handlers_in_a_child(lib, SHOW_HANDLERS, "the engine's replay")


for _name in UNIT_M_WAVE_4:
    aes_event.declare_child_doors(_name, "import aes_deskutil; aes_deskutil.bind_show_in_a_child(lib); ")

Wait = namedtuple("Wait", "stop reception")
Wait.__doc__ = """Where the run in place takes a hand in: at the named stop `stop` (an address of `aes_desk.STOPS`), or
at its next idle (None) — `reception`, as a chain's step gives it."""


def in_place(arrived, waits=()):
    """THE ROM'S OWN RUN of the engine from `arrived` to its return (`aes_deskdir.in_place`), each of `waits` taken in
    where it says, what each Fread read captured: an `aes_deskdir.Replay`."""
    return _cdir.in_place(arrived, tuple(wait.reception for wait in waits), tuple(wait.stop for wait in waits),
                          captures=_cdir.FREAD_READ)


def read_laid(replay):
    """`{the buffer: the bytes the run's Fread read into it}` — refused by name for a second Fread into one buffer:
    only the last would be laid."""
    read = {}
    for _function, at, data in replay.written:
        assert at not in read, "a second Fread into one buffer: only the last is laid"
        read[at] = data
    return read


def replayed(replay, answers=None):
    """The recorder's pokes for the run in place — its answers (or `answers`, a class's script), the spares and where
    they end (`SPENT_AT`) — its handles laid open, and the bytes its Fread read laid where it read them."""
    script = (*(replay.answers if answers is None else answers), *(_cdir.SPARE_ANSWER,) * _cdir.SPARE_ANSWERS)
    spent = struct.pack(">I", SHOW.script.first + len(script) * L)
    return case.merge_pokes(SHOW.pokes(script), {SPENT_AT: spent}, replay.handles, read_laid(replay))


def calls(image):
    """The ledger read back: the functions called, in order."""
    return tuple(function for function, _frame in SHOW.calls(image))
# ---- end of group G1's wave-4 ----
