"""gemdosif's BAND-5 LEFTOVERS and their users — the doors (`src/aes/gemdosif.c`'s dos_gdrv, dos_chdir, dos_sdrv,
isdrive; the desk's memory and leaves built on them) are proved through, on both shores at once.

TWO WAYS TO ANSWER A `trap #1`, `test/aes_shell.py`'s two (which says why Tier 3 prices over the second alone):

  * REAL GEMDOS (`run_real`): the ROM's glue traps into the ROM's GEMDOS; our C hands the same frame to the
    reconstructed dispatcher, its handlers bound to the reconstructed leaves (`HANDLERS`: Dgetdrv, Dsetdrv, Dsetpath
    over the staged RAM disk, Malloc, Mfree). The GEMDOS door's windows dropped, as the shell's file calls drop them.
  * A RECORDING, SCRIPTED TRAP (`run_scripted`): the `trap #1` vector pointed at a 68000 handler staged in this
    module's band that RECORDS each call — its function word and ITS FRAME'S OWN BYTES — in a ledger and answers the
    next longword of a script; the host twin is the same effect over the candidate's image.

WHY NOT `aes_shell`'s HANDLER: it tells apart the frames of the file calls; these are other functions with other
frames — Dgetdrv's is the function word ALONE, and what lies above it on the ROM's stack is its caller's (a return
address, an Alcyon slot), which no C build reproduces: recorded, it would differ by nature. So this handler records
`FRAME_BYTES[function]` bytes and zeros after them, and a new compare in the shell's stub would move every priced row
over it. The tables are `aes_shell.Table`'s, the layout helper `aes_shell.laid_out`.

NOTHING HERE POISONS, for `aes_shell`'s two reasons (real GEMDOS chases what it stores; the handler stores back the
ledger's and the script's pointers). What stands in is staging: the glue's four words STALE.
"""
import ctypes
import functools
import os
import struct
import sys

from harness import _lib, addrs

import aes
import aes_event
import aes_shell as shell
from address_hook import bind_pointer
import case
import gemdos
import gemdos_fs as fs
import isr
import routines
import vdi
import vdi_helpers
from case import merge_pokes
from opcodes import BEQ_S, BRA_S, CLR_W_A0_POSTINC, CMPI_W_STACK, MOVE_L_A0_POSTINC_D0, MOVE_W_STACK_TO_A0_POSTINC, RTE
from vdi_helpers import FRAME_WORDS_AT, MOVEA_L_ABSOLUTE_A0, POP_A0, PUSH_A0, STORE_A0_ABSOLUTE

WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ---------------------------------------------------------------------------
DOS_GDRV, DOS_CHDIR, DOS_SDRV, ISDRIVE = "AES_ROM_DOS_GDRV", "AES_ROM_DOS_CHDIR", "AES_ROM_DOS_SDRV", "AES_ROM_ISDRIVE"
# The three through $fe3c28 park their CALLER's return address — the machine's, carried by no frame: a host argument.
aes.declare_alcyon(DOS_GDRV, aes.LONG_ANSWER, (IMAGE, LONG), host_arguments=1)
aes.declare_alcyon(DOS_CHDIR, aes.LONG_ANSWER, (IMAGE, LONG, LONG), host_arguments=1)
aes.declare_alcyon(DOS_SDRV, aes.LONG_ANSWER, (IMAGE, LONG, WORD), host_arguments=1)
aes.declare_alcyon(ISDRIVE, aes.LONG_ANSWER, (IMAGE,))
PGMLD = "AES_ROM_PGMLD"
aes.declare_alcyon(PGMLD, aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG))

DGETDRV, DSETDRV, DSETPATH = addrs.GEMDOS_DGETDRV_FN, addrs.GEMDOS_DSETDRV_FN, addrs.GEMDOS_DSETPATH_FN
MALLOC, MFREE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN

# The glue's verdict and its parking, staged STALE so a skipped store shows (`aes_shell.STALE_DOS`, the same four).
DOS_FIELDS = shell.DOS_FIELDS
STALE_DOS = shell.STALE_DOS

# ---- this module's band ----------------------------------------------------------------------------------------------
BAND_OFFSET = 0x2800                    # into the AES's window: clear of every band claimed (the registry refuses one)
BAND_BYTES = 0x500
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_gemdosif.py: three recording traps, a path, a basepage")
PATH_AT = BAND_AT                       # a path a case hands dos_chdir, a program's name pgmld is handed
PATH_BYTES = 0x40
ARGUMENTS_IN_FRAME = FRAME_WORDS_AT + WORD_BYTES
MOVE_L_ABSOLUTE_TO_A0_POSTINC = b"\x20\xf9"   # move.l  <xxx>.l,(a0)+
PEXEC, MSHRINK = addrs.GEMDOS_PEXEC_FN, addrs.GEMDOS_MSHRINK_FN


class Recorder:
    """ONE RECORDING, SCRIPTED TRAP: the `vector` it is staged behind, the room its 68000 handler has at `at`, and
    `frame_bytes` — `{function: how many bytes of its frame a call is recorded with}`, the frame's OWN (nothing for
    Dgetdrv, a drive word, a longword, Pexec's fourteen). Its two tables (`aes_shell.Table`) follow the handler: the
    LEDGER of `entries` calls, each the function word then its frame zero-padded to the widest; the SCRIPT of as
    many answers. `parked`: longwords of RAM whose value AT EACH CALL is recorded behind the frame — the sites the glue
    parks before it traps (AES_DOS_RETURN, AES_TRAP1_RETURN): a routine that makes several calls overwrites each
    park with the next, and only the ledger shows the ones before the last."""

    def __init__(self, vector, at, room, frame_bytes, entries, parked=()):
        self.vector, self.at, self.frame_bytes, self.parked = vector, at, dict(frame_bytes), tuple(parked)
        self.recorded_bytes = max(self.frame_bytes.values())
        self.ledger = shell.Table(at + room, entries, WORD_BYTES + self.recorded_bytes + len(self.parked) * LONG_BYTES, "ledger")
        self.script = shell.Table(self.ledger.first + entries * self.ledger.stride, entries, LONG_BYTES, "script")
        self.end = self.script.first + entries * LONG_BYTES
        assert len(self.stub()) <= room, f"the handler is {len(self.stub())} bytes: more than its room of {room}"

    def stub(self):
        """The handler: the function word into the ledger, then its frame a word at a time — each function whose
        frame ends there branching out to the zeros that pad its entry; the ledger's pointer stored back; D0 the
        script's next longword, its pointer stored back; `rte`. Every register but D0 as found."""
        pieces = [PUSH_A0 + MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", self.ledger.pointer_at),
                  vdi.pack_words(MOVE_W_STACK_TO_A0_POSTINC, FRAME_WORDS_AT)]
        for recorded in range(0, self.recorded_bytes, WORD_BYTES):
            for function in (function for function, size in self.frame_bytes.items() if size == recorded):
                pieces += [vdi.pack_words(CMPI_W_STACK, function, FRAME_WORDS_AT), (BEQ_S, f"pad {recorded}")]
            pieces.append(vdi.pack_words(MOVE_W_STACK_TO_A0_POSTINC, ARGUMENTS_IN_FRAME + recorded))
        pieces.append((BRA_S, "done"))
        for recorded in range(0, self.recorded_bytes, WORD_BYTES):      # each falls through into the shorter pads
            pieces += [("label", f"pad {recorded}"), vdi.pack_words(CLR_W_A0_POSTINC)]
        pieces.append(("label", "done"))
        pieces += [MOVE_L_ABSOLUTE_TO_A0_POSTINC + struct.pack(">I", at) for at in self.parked]
        pieces += [STORE_A0_ABSOLUTE + struct.pack(">I", self.ledger.pointer_at) + MOVEA_L_ABSOLUTE_A0
                   + struct.pack(">I", self.script.pointer_at) + vdi.pack_words(MOVE_L_A0_POSTINC_D0) + STORE_A0_ABSOLUTE
                   + struct.pack(">I", self.script.pointer_at) + POP_A0 + RTE]
        return shell.laid_out(pieces)

    def pokes(self, answers):
        """The vector at the handler, an empty ledger (its entries FILLed) and the script of `answers`."""
        script = b"".join(struct.pack(">I", answer & aes.LONG_MASK) for answer in answers)
        return {self.vector: struct.pack(">I", self.at), self.at: self.stub(),
                **self.ledger.staged(), **self.script.staged(script)}

    def twin(self, function):
        """The handler's HOST TWIN for `function`: the same ledger entry, the same answer, both pointers bounded."""
        def handler(buf, arguments, _argument_bytes):
            entry, answer_at = self.ledger.next(buf), self.script.next(buf)
            self.ledger.record(buf, entry, function, arguments, self.frame_bytes[function])
            for nth, at in enumerate(self.parked):          # ...over the zeros its padding left behind the frame
                isr.poke(buf, entry + WORD_BYTES + self.recorded_bytes + nth * LONG_BYTES, bytes(buf[at:at + LONG_BYTES]))
            self.script.step(buf, answer_at)
            return case.long_in(buf, answer_at)
        return handler

    def calls(self, image):
        """The ledger in `image` as `[(function, frame bytes), ...]`, in the order the calls were made — the frame
        alone (`parked_at` reads what was parked at each)."""
        return [(function, entry[:self.recorded_bytes]) for function, entry in self.ledger.recorded(image)]

    def call(self, function, *fields):
        """A ledger entry as `calls` reads one: `function` over a frame of ('w', value) / ('l', value) fields."""
        return function, self.ledger.frame(*fields)[:self.recorded_bytes]

    def parked_at(self, image):
        """What the `parked` longwords held AT EACH CALL, in order: `[(value, ...), ...]`."""
        return [tuple(int.from_bytes(entry[self.recorded_bytes + nth * LONG_BYTES:][:LONG_BYTES], "big")
                      for nth in range(len(self.parked))) for _function, entry in self.ledger.recorded(image)]


# GEMDOS's: the functions the glue's leftovers and their users trap with, each with its frame's own bytes.
GEMDOS = Recorder(addrs.VECTOR_TRAP_GEMDOS, PATH_AT + PATH_BYTES, 0x130, {
    DGETDRV: 0, DSETDRV: WORD_BYTES, DSETPATH: LONG_BYTES, MALLOC: LONG_BYTES, MFREE: LONG_BYTES,
    MSHRINK: WORD_BYTES + 2 * LONG_BYTES, PEXEC: WORD_BYTES + 3 * LONG_BYTES}, entries=16,
    parked=(aes.AES_DOS_RETURN, aes.AES_TRAP1_RETURN))
# (The sites alone — a handler's instructions are cycles in BOTH columns of every row recorded through it, so it
# records what the glue itself parks and nothing a single battery's ordering question wants: CALL ORDER across the
# doors has its own surface, `aes_trap_order`, which stages nothing.)


def sites_parked_at(image):
    """`[(AES_DOS_RETURN, AES_TRAP1_RETURN), ...]` as each GEMDOS call found them, in order."""
    return GEMDOS.parked_at(image)


# WHERE THIS LEDGER CAN HOLD AN ADDRESS OF THE GLUE'S OWN TEXT (`aes_event.TEXT_SITES`: pgmld's `.S` parks a site of
# its own, and hands Pexec the address of its own zero word): in each entry, the longword AES_TRAP1_RETURN was
# recorded into and the third longword of a frame (Pexec's command tail). Declared here, where the ledger is laid out.
def _ledger_longs(offset_in_an_entry):
    return tuple(GEMDOS.ledger.first + nth * GEMDOS.ledger.stride + offset_in_an_entry for nth in range(GEMDOS.ledger.entries))


TRAP1_SITES_IN_THE_LEDGER = _ledger_longs(WORD_BYTES + GEMDOS.recorded_bytes + GEMDOS.parked.index(aes.AES_TRAP1_RETURN) * LONG_BYTES)
PEXEC_TAILS_IN_THE_LEDGER = _ledger_longs(2 * WORD_BYTES + LONG_BYTES)       # past the function, the mode and the name
aes_event.declare_text_site_slots(*TRAP1_SITES_IN_THE_LEDGER, *PEXEC_TAILS_IN_THE_LEDGER)
# ...and the BIOS's, for the vector takes' `.S` (both shores 68000: no host twin is bound): Setexc's vector word and
# handler.
BIOS = Recorder(addrs.VECTOR_TRAP_BIOS, GEMDOS.end, 0x40, {addrs.BIOS_SETEXC_FN: WORD_BYTES + LONG_BYTES}, entries=4)
# ...and the XBIOS's, for the AES's XBIOS door (`trp14.S`, the same way): the shapes its ROM callers push — the
# function word alone (Getrez), one more word (Blitmode) — and A MADE-UP ONE, an ARGUMENT CLASS wherever it is run:
# a function word and ONE longword, the WIDTH of what `$fedaee..$fedaf4` pushes and no ROM caller's own frame (the
# number is Flopfmt's, whose real frame is nine fields — nothing here formats: the trap is the recorder's).
XBIOS_GETREZ, XBIOS_BLITMODE, XBIOS_A_MADE_UP_LONG = addrs.XBIOS_GETREZ_FN, 0x40, 10
XBIOS = Recorder(addrs.VECTOR_TRAP_XBIOS, BIOS.end, 0x60, {XBIOS_GETREZ: 0, XBIOS_BLITMODE: WORD_BYTES,
                                                         XBIOS_A_MADE_UP_LONG: LONG_BYTES}, entries=4)
# A basepage pgmld's scripted Pexec answers, past the three.
BASEPAGE_AT = XBIOS.end + (-XBIOS.end % LONG_BYTES)
BASEPAGE_BYTES = 0x40
BAND_END = BASEPAGE_AT + BASEPAGE_BYTES
assert BAND_END <= BAND_AT + BAND_BYTES
HANDLER_AT, LEDGER, SCRIPT, FRAME_BYTES = GEMDOS.at, GEMDOS.ledger, GEMDOS.script, GEMDOS.frame_bytes
scripted_pokes, calls, call, parked_at = GEMDOS.pokes, GEMDOS.calls, GEMDOS.call, GEMDOS.parked_at
SCRIPTED_HANDLERS = {gemdos.rom_handler(function): GEMDOS.twin(function) for function in FRAME_BYTES}


def scripted_hook():
    """The host twin bound as `aes.run_function`'s / `aes.register`'s `hook`."""
    return gemdos.bound_handlers(SCRIPTED_HANDLERS)


def scripted_machine(answers, pokes=None):
    return aes.leaf_machine(onto=merge_pokes(STALE_DOS, scripted_pokes(answers), pokes))


def run_scripted(name, arguments, answers, pokes=None, **kwargs):
    """`name` over the leaf machine with every `trap #1` answered by the script of `answers` — UNPOISONED."""
    return aes.run_function(name, arguments, scripted_machine(answers, pokes), hook=scripted_hook, poison=False,
                            **kwargs)


def scripted_over(machine, answers, pokes=None):
    """`machine` — a RUNNING process's, as the ROM's scheduler made it (never the leaf machine's lever) — with every
    `trap #1` answered by the script of `answers`: what a routine that traps AND leaves by the dispatcher runs over."""
    return merge_pokes(machine, STALE_DOS, scripted_pokes(answers), pokes)


# THE SCRIPT IN A CHILD (`aes_event.declare_child_doors`): a routine that also SWITCHES runs its C in a fork under the
# scheduler's model, where the dispatcher's GEMDOS hook is bound by source the fork runs first.
CHILD_GEMDOS_REFUSED = 7                # the child's exit status then (`aes_fslib`'s, for the same refusal)
GEMDOS_HANDLER_HOOK = "recreate_call_gemdos_handler"
_CHILD_TRAMPOLINES = []
CHILD_DOORS = "import aes_gemdosif; aes_gemdosif.bind_scripted_in_a_child(lib); "


# ...and in a FRESH interpreter (`aes_event.refusal`: a core run where its halt — or its crash — ends a child and
# fails a test, never the suite), which has this directory on no path of its own.
FRESH_CHILD_DOORS = f"import sys; sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r}); {CHILD_DOORS.rstrip('; ')}"


def bind_scripted_in_a_child(lib):
    """The scripted trap's host twins (SCRIPTED_HANDLERS) bound into `lib`, the candidate the child loaded."""
    def dispatch(buf, handler, arguments, argument_bytes):
        try:
            assert handler in SCRIPTED_HANDLERS, f"the candidate called GEMDOS handler {handler:#x}, which the script does not serve"
            return SCRIPTED_HANDLERS[handler](buf, arguments, argument_bytes)
        except Exception as refused:    # a callback cannot raise into C: the child ends here, by name
            print(refused, file=sys.stderr, flush=True)
            os._exit(CHILD_GEMDOS_REFUSED)
    trampoline = gemdos.CALL_HANDLER(dispatch)
    _CHILD_TRAMPOLINES.append(trampoline)
    bind_pointer(GEMDOS_HANDLER_HOOK, trampoline, lib)


def register_unpriced(label, name, arguments, machine, **kwargs):
    """One case of `name` VERIFIED AND UNPRICED AT ITS OWN ROM ENTRY — swept with the registry, in no line of the
    table: for a twin Tier 3 cannot enter (a HOST ARGUMENT no frame carries) or does not price (the C twin of a
    routine that ships as its `.S`). Every such row is listed by name with its reason in the census
    (`test_tier3.UNPRICED_AT_A_ROM_ENTRY`), which reds until it is."""
    return aes.ROWS.register(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), aes.staged(name, arguments, machine),
                             priced=False, **kwargs)


def register_scripted(label, name, arguments, answers, pokes=None, *, dropped=(), priced=True):
    """One row of `name` over the scripted trap — priced, unless `priced` is False (verified, unpriced: said where it
    is registered). `dropped` (`(lo, hi, why)` each): what THIS row's two shores differ in by nature on target, by
    name — with the companion a drop needs, the row's own host differential with nothing dropped (`aes.undropped`);
    only for a routine whose ROM run stores no Line-F mask word (hand 68000)."""
    machine = scripted_machine(answers, pokes)
    if not dropped and priced:
        return aes.register(label, name, arguments, machine, hook=scripted_hook)
    assert aes.settled_mask_word(name, arguments, machine) is None, f"{name}: its run stores the mask word too"
    row_name, staged = f"{routines.core_symbol(name)}, {label}", aes.staged(name, arguments, machine)
    if not priced:
        return aes.ROWS.register(row_name, getattr(addrs, name), staged, priced=False)
    companion = functools.partial(aes.undropped, name, arguments, machine, scripted_hook)
    return aes.ROWS.register(row_name, getattr(addrs, name), staged, dropped=tuple(dropped), undropped=companion)


# ---- REAL GEMDOS ---------------------------------------------------------------------------------------------------------
_lib.gemdos_dgetdrv.restype = _lib.gemdos_dsetdrv.restype = ctypes.c_uint32
HANDLERS = {
    gemdos.rom_handler(DGETDRV): lambda buf, _arguments, _bytes: _lib.gemdos_dgetdrv(buf),
    gemdos.rom_handler(DSETDRV): lambda buf, arguments, _bytes: _lib.gemdos_dsetdrv(buf, case.word_in(buf, arguments)),
    gemdos.rom_handler(DSETPATH): fs.leaf_handler(fs.DSETPATH),
    **vdi_helpers.GEMDOS_HANDLERS,
}
REAL_WINDOWS = shell.REAL_WINDOWS


def real_machine(pokes=None):
    """The leaf machine on the staged drive A: (`aes_shell.disk_machine`: its root the current directory), the
    glue's words stale."""
    return fs.machine(shell.disk_machine(aes.leaf_machine(onto=merge_pokes(STALE_DOS, pokes))))


def run_real(name, arguments, pokes=None, **kwargs):
    """`name` with its `trap #1`s into REAL GEMDOS on both shores, over the staged drive — UNPOISONED."""
    doors = aes.doors(shell.staged_disk, functools.partial(gemdos.bound_handlers, HANDLERS))
    return aes.run_function(name, arguments, real_machine(pokes), hook=doors, poison=False,
                            dropped_windows=REAL_WINDOWS, result=shell.Result, **kwargs)

