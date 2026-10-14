"""THE COPY ENGINE AND ITS HELPERS — unit C (`src/desk/deskdir.c`, `test/test_desk_dir.py`): band 6 wave 1b's (group G4)
dialogs' drawing, path editors, DOS verdict and delete, and the check that a folder is not copied into itself; band 6
wave 2's (group G1) engine, d_dofcopy, d_doop and dir_op — their declared Alcyon frames and the unit's lists, and the
engine's GEMDOS replayed from the ROM's own run in place (the wave-2 block)."""
import ctypes
import struct
from collections import namedtuple
from pathlib import Path

from harness import addrs

import aes
import aes_boot
import aes_deskarrive as da
import aes_deskbind as db
import aes_event
import aes_gemdosif as gd
import aes_loader
import case
import gemdos
import isr
import layouts
import opcodes as op
import vdi
import vdi_helpers
from case import merge_pokes

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
PREFIX = "AES_ROM_DESK_"
HEADER = Path(__file__).resolve().parents[1] / "include" / "desk" / "deskdir.h"
CONSTANTS = layouts.parse_constants((HEADER.parent / "deskglobals.h", HEADER), known={**vdi.CONSTANTS, **aes.CONSTANTS})
# `{routine: (the core's answer, its frame in push order)}` — None where the core answers nothing
SIGNATURES = {
    PREFIX + "DRAW_DIAL": (None, (LONG,)),
    PREFIX + "DO_NAMECON": (None, ()),
    PREFIX + "HIDE_DIAL": (aes.WORD_ANSWER, (LONG,)),
    PREFIX + "SHOW_DIAL": (None, (LONG,)),
    PREFIX + "DRAW_FLD": (None, (LONG, WORD)),
    PREFIX + "ADD_PATH": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "SUB_PATH": (aes.LONG_ANSWER, (LONG,)),
    PREFIX + "ADD_FNAME": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "DEL_FNAME": (aes.LONG_ANSWER, (LONG,)),
    PREFIX + "GET_FNAME": (None, (LONG, LONG)),
    PREFIX + "D_ERRMSG": (aes.WORD_ANSWER, ()),
    PREFIX + "D_DOFDEL": (aes.WORD_ANSWER, (LONG,)),
    PREFIX + "PATH_PART": (aes.LONG_ANSWER, (LONG, LONG)),
    PREFIX + "PAR_CHK": (aes.WORD_ANSWER, (LONG, LONG, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_C = tuple(SIGNATURES)
# ---- band 6 wave 2, group G1 (unit C) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_C (and its count) stays as it is
SIGNATURES_WAVE_2 = {
    PREFIX + "D_DOFCOPY": (aes.WORD_ANSWER, (LONG, LONG, LONG, WORD)),
    PREFIX + "D_DOOP": (aes.WORD_ANSWER, (WORD, LONG, LONG, LONG, LONG, LONG)),
    PREFIX + "DIR_OP": (aes.WORD_ANSWER, (WORD, LONG, LONG, LONG, LONG, LONG, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_C_WAVE_2 = tuple(SIGNATURES_WAVE_2)
D_DOFCOPY, D_DOOP, DIR_OP = UNIT_C_WAVE_2


# ---- THE COPY ENGINE'S GEMDOS: A RECORDING TRAP REPLAYING THE ROM'S OWN RUN IN PLACE --------------------------------------
# d_dofcopy, d_doop and dir_op trap through the DOS glue (`__DOS`, dos_alloc's, dos_avail's own) and through
# gem_gemdos_call's Fread / Fwrite. On both shores of a case that `trap #1` is THIS recorder — `aes_gemdosif.Recorder`'s
# ledger (each call's function, its frame's own bytes, and the three returns parked AT that call: the glue's two and
# gem_gemdos_call's), answered call by call by a script — AND THE SCRIPT IS THE ROM'S OWN RUN IN PLACE (`in_place`): the
# answer each call got and, for a search, THE DTA IT LEFT, laid at that search into the DTA the run's last Fsetdta named
# (`aes_loader.DtaFilledAtItsSearches`, its cell set by each Fsetdta here: d_doop moves its DTA a folder level at a
# time). A LABELLED STAGING, said in every such case's id (`REPLAYED`). GEMDOS itself does not run: what it would
# have read into the copy buffer is read on neither shore — no routine here reads the buffer but through Fwrite.
# Fdatime's frame begins with the address of dos_setdt's OWN argument (its stack on the ROM's shore, a host slot on
# ours): the ledger keeps THE FOUR BYTES IT POINTS AT in that longword's place, so the stamp handed is held, not where.
# THE BAND: `aes_gemdosif`'s, where `aes_loader`'s replay is laid too (a machine holds one of them) — the group's own
# window (`$7b640..$7b800`, 448 B) cannot hold the 24-call ledger with eight DTAs the wave's longest run needs.

REPLAYED = "GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search"
FOPEN, FREAD, FWRITE, FCLOSE = (addrs.GEMDOS_FOPEN_FN, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FWRITE_FN,
                                addrs.GEMDOS_FCLOSE_FN)
FCREATE, FDATIME, FDELETE = addrs.GEMDOS_FCREATE_FN, addrs.GEMDOS_FDATIME_FN, addrs.GEMDOS_FDELETE_FN
DCREATE, DDELETE, FSETDTA = addrs.GEMDOS_DCREATE_FN, addrs.GEMDOS_DDELETE_FN, addrs.GEMDOS_FSETDTA_FN
FSFIRST, FSNEXT, MALLOC, MFREE = (addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FSNEXT_FN, addrs.GEMDOS_MALLOC_FN,
                                  addrs.GEMDOS_MFREE_FN)
SEARCHES = (FSFIRST, FSNEXT)
W, L = aes.WORD_BYTES, aes.LONG_BYTES
# Each function the engine reaches, with how many bytes of its frame are its own.
ENGINE_FRAME_BYTES = {FSNEXT: 0, FCLOSE: W, FDELETE: L, DCREATE: L, DDELETE: L, FSETDTA: L, MALLOC: L, MFREE: L,
                      FOPEN: L + W, FCREATE: L + W, FSFIRST: L + W, FDATIME: L + 2 * W, FREAD: W + 2 * L, FWRITE: W + 2 * L}
ENGINE_CALLS = 24                       # dir_op's copy of AUTO (a folder holding a file) as AUTB makes 20 (measured)
ENGINE_SEARCHES = 8                     # d_doop's delete of a folder holding a folder makes 7
ENGINE_HANDLER_ROOM = 0x150
PARKED = (aes.AES_DOS_RETURN, aes.AES_TRAP1_RETURN, aes.AES_GEMDOS_RETURN)
ARGUMENTS_IN_FRAME = gd.ARGUMENTS_IN_FRAME
MOVE_L_A1_TO_A0 = 0x2091                # move.l  (a1),(a0)
DTA_BYTES = aes_loader.DTA_BYTES


class EngineRecorder(aes_loader.DtaFilledAtItsSearches):
    """`aes_loader`'s recorder that lays the DTA at each search — its cell set BY EACH Fsetdta (the 68000 handler
    and its twin), and an Fdatime's pointer replaced in the ledger by the four bytes it points at."""

    def after_the_answer(self):
        cell, ledger = struct.pack(">I", self.dta_cell), struct.pack(">I", self.ledger.pointer_at)
        is_function = lambda function: vdi.pack_words(op.CMPI_W_STACK, function, vdi_helpers.FRAME_WORDS_AT)
        kept = [is_function(FSETDTA), (op.BNE_S, "kept"),
                vdi.pack_words(op.MOVE_L_STACK_TO_ABSOLUTE, ARGUMENTS_IN_FRAME) + cell, ("label", "kept")]
        stamped = [is_function(FDATIME), (op.BNE_S, "stamped"),
                   vdi_helpers.MOVEA_L_ABSOLUTE_A0 + ledger
                   + vdi.pack_words(op.LEA_D16_A0_A0, (W - self.ledger.stride) & aes.WORD_MASK, op.PUSH_A1,
                                    op.MOVEA_L_STACK_A1, ARGUMENTS_IN_FRAME + L, MOVE_L_A1_TO_A0, op.POP_A1),
                   ("label", "stamped")]
        return [*kept, *stamped, *super().after_the_answer()]

    def twin(self, function):
        answering = super().twin(function)
        if function not in (FSETDTA, FDATIME):
            return answering

        def handler(buf, arguments, argument_bytes):
            pointer = case.long_in(buf, arguments)
            if function == FSETDTA:
                isr.poke(buf, self.dta_cell, struct.pack(">I", pointer))
            answer = answering(buf, arguments, argument_bytes)
            if function == FDATIME:
                entry = case.long_in(buf, self.ledger.pointer_at) - self.ledger.stride
                isr.poke(buf, entry + W, ctypes.string_at(ctypes.addressof(buf.contents) + (pointer & db.BUS), L))
            return answer
        return handler


ENGINE = EngineRecorder(addrs.VECTOR_TRAP_GEMDOS, aes_loader.REPLAYED_AT, ENGINE_HANDLER_ROOM, ENGINE_FRAME_BYTES,
                        entries=ENGINE_CALLS, searches=ENGINE_SEARCHES, parked=PARKED)
assert ENGINE.end <= gd.BAND_AT + gd.BAND_BYTES, "the engine's recorder runs out of the band it borrows"
ENGINE_HANDLERS = {gemdos.rom_handler(function): ENGINE.twin(function) for function in ENGINE_FRAME_BYTES}


def engine_hook():
    """The host twins bound as `aes.run_function`'s `hook`."""
    return gemdos.bound_handlers(ENGINE_HANDLERS)


def bind_engine_in_a_child(lib):
    """...and in a row's child (`aes_gemdosif.bind_handlers_in_a_child`, over this recorder's twins)."""
    gd.bind_handlers_in_a_child(lib, ENGINE_HANDLERS, "the replay")


ENGINE_CHILD_DOORS = "import aes_deskdir; aes_deskdir.bind_engine_in_a_child(lib); "
for _name in UNIT_C_WAVE_2:
    aes_event.declare_child_doors(_name, ENGINE_CHILD_DOORS)

# ---- THE ROM'S OWN RUN IN PLACE, call by call ---------------------------------------------------------------------------
Replay = namedtuple("Replay", "answers fills functions handles returned")
Replay.__doc__ = """What the ROM's own run of a routine from its arrival got of GEMDOS: the `answers` (D0 at each of
its traps' returns, in order), the `fills` (the DTA each search left), the `functions` called, `handles` — `{the
handle record's address: its bytes}` as GEMDOS left each record an Fopen or Fcreate of the run opened —, and the
`Boot` it `returned` on (D0 there)."""
# THE HOST'S TRAP REACHES THE RECONSTRUCTED DISPATCHER, which resolves Fread's and Fwrite's handle before it calls the
# handler: each handle the run opened is LAID OPEN, its record as the ROM's GEMDOS left it at the open
# (`aes_gemdosif.opened_record`) — the ROM's side, whose recorder stands in for the whole of GEMDOS, reads it not at all.
handle_record = gd.handle_record


def _sp(boot):
    return db.stack_pointer(boot)


def _continued_to(boot, received, arrived, until, stands_at):
    """The run on to `until` — None where it idles first."""
    try:
        return aes_boot.continued(boot, received, arrived.budget, until, stands_at)
    except aes_boot.Refused:
        return None


def in_place(arrived, wakes=()):
    """THE ROM'S OWN RUN of the routine from `arrived` to its return, over the real disk: hopped from GEMDOS's handler
    entry to where each `trap #1` returns — a trap the run meets only AFTER its return (fewer instructions to the
    return) is its caller's —, and at each idle the next of `wakes` (receptions, as a chain's hand gives them) taken in.
    The DTA a search fills is the one the run's last Fsetdta named — refused by name where none did. `Replay`."""
    boot, stands_at, received, wakes = arrived.boot, da.entry_of(arrived.name), (), list(wakes)
    handler, sp0 = case.long_in(boot.ram, addrs.VECTOR_TRAP_GEMDOS) & db.BUS, _sp(arrived.boot)
    answers, fills, functions, handles, dta = [], [], [], {}, None
    while True:
        hop = _continued_to(boot, received, arrived, handler, stands_at)
        back = _continued_to(boot, received, arrived, arrived.returns_to, stands_at)
        if back is not None and (hop is None or back.instructions <= hop.instructions):
            assert _sp(back) == sp0 + L and not wakes, f"{da.label_of(arrived)}: not its own return, or wakes left"
            return Replay(tuple(answers), tuple(fills), tuple(functions), handles, back)
        if hop is None:
            assert wakes, f"{da.label_of(arrived)}: the run idles with no wake left to take in"
            boot, stands_at = aes_boot.continued(boot, received, arrived.budget, None, stands_at), None
            received = wakes.pop(0)
            continue
        sp = _sp(hop)
        function, returns = case.word_in(hop.ram, sp + gd.FRAME_WORDS_AT - L), case.long_in(hop.ram, sp + W) & db.BUS
        if function == FSETDTA:
            dta = case.long_in(hop.ram, sp + ARGUMENTS_IN_FRAME - L) & db.BUS
        boot = aes_boot.continued(hop, (), arrived.budget, returns, handler)
        answers.append(boot.registers["d0"])
        functions.append(function)
        if function in SEARCHES:
            assert dta is not None, f"{da.label_of(arrived)}: a search before any Fsetdta of its own"
            fills.append(bytes(boot.ram[dta:dta + DTA_BYTES]))
        handles.update(gd.opened_record(boot.ram, function, answers[-1]))
        stands_at, received = returns, ()


# SPARE ANSWERS AND A SPARE DTA behind the run's own: a C that makes MORE CALLS than the ROM's run is answered
# (ERROR) and recorded — the ledger and the script's pointer then differ, an assertion — where an empty script would
# end the host's run in its twin's refusal, a crash and no kill.
SPARE_ANSWER, SPARE_DTA = -1 & aes.LONG_MASK, bytes(DTA_BYTES)
SPARE_ANSWERS = 3                       # ...three: a C that loops on past a failure makes a read, a close and a write more


def replayed(replay, dta_at_first=None):
    """The recorder's pokes for `replay`: its answers and fills (and the spares), the cell first at `dta_at_first` (a
    stale longword where none: every routine here names its DTA before it searches), the handles laid open."""
    return merge_pokes(ENGINE.pokes((*replay.answers, *(SPARE_ANSWER,) * SPARE_ANSWERS),
                                    vdi.STALE_LONG if dta_at_first is None else dta_at_first,
                                    (*replay.fills, SPARE_DTA)), replay.handles)


def engine_calls(image):
    """The ledger read back: `[(function, frame bytes and the three parked returns)]`, in order."""
    return ENGINE.ledger.recorded(image)
# ---- end of group G1's wave-2 ----
