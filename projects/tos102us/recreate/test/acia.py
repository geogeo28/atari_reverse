"""How a case drives the ACIA INPUT CHAIN: the two 6850s' declared bytes, and KBDVECS' seven vectors.

`test/isr.py` says how a case enters an interrupt HANDLER. This says how it enters the routines that
handler calls through RAM — `midi_acia_service`, `ikbd_acia_service` and everything under them — and
they are ordinary `rts` routines rather than exception handlers, so they need none of that module's
frame machinery. What they DO need is the same two things every case here does:

* **the bytes the chips yielded, declared.** A 6850's data port is a TRANSFER register: every read
  POPS it, so one byte describes exactly one read and a whole packet is a declared SEQUENCE
  (`TRAP_MODEL.md`, Phase 16). `declare` below builds the `io_seed` for one chip out of a status
  byte (or list) and the bytes behind it, through the one door — the IKBD's pair are Phase 7 NAMED
  slots and the MIDI's are ordinary declared bytes, and `emu.seed_split` routes each.
* **the seven KBDVECS vectors, staged.** Every completed packet, every MIDI byte and every overrun
  leaves through a longword in RAM, so what runs there is an INPUT of these routines. `stage` plants
  a RECORDER at each — a 68000 stub for the oracle and the same effect in Python for the candidate,
  through `staged_call.h`'s hook — so a case can say which vector was called AND what it was handed.

WHY EVERY VECTOR IS STAGED ON EVERY CASE, not just the one the case is about: the attribution
(poison) pass re-runs both cores on an image whose oracle-written bytes are INVERTED, and the byte it
inverts here is `IKBD_PACKET_KIND` — so a poisoned run enters the packet machine in a state the plain
run never reaches and calls a different vector. Staging the lot means that pass proves attribution
instead of tripping the unstaged-routine guard.

WHAT THE RECORDERS CAN AND CANNOT SEE. A packet vector is handed its packet BOTH ways round — pushed
as a longword and in A0 — and the hook carries that one address, so both shores write it and the
comparison is real. A BYTE vector (`midivec`, the two error vectors) is handed the byte in D0 and the
IOREC in A0, and the hook carries only the byte: A0 is the ORACLE's claim alone here, and what pins
it on our side is the REAL-`midivec` case, where the ROM's own `$fc2e3a` is left in the slot and the
byte can only land in the ring A0 named.
"""
import ctypes
import struct

import case
import isr
from harness import addrs, _lib

# ---- where this module's stubs and their reports live -------------------------------------------
# Inside `isr.STUB_BAND`, above the three stubs `test_bios_ikbd.py` stages at its foot (+0x00, +0x10
# and +0x20) and below `isr.MARKS`, which begins 0x100 bytes in. One stub per slot, 0x10 bytes each:
# the widest recorder below is sixteen bytes exactly.
STUB_STRIDE = 0x10
STUB_BASE = isr.STUB_BAND + 0x30
# ...and where a recorder writes what it was handed: one longword per vector, in the marks region
# and clear of the three single bytes that battery marks at its foot.
REPORT_BASE = isr.MARKS + 0x10
REPORT_BYTES = 4

# THE SEVEN SLOTS, in KBDVECS' own order, with what each is handed. `packet` means the vector takes a
# buffer address — pushed and in A0 — and `byte` means it takes a raw byte in D0 with the IOREC in
# A0. `Kbdvbase`'s two service vectors are NOT here: they are the ACIA handler's, `test/isr.py`'s
# battery stages them, and nothing below `acia_take_byte` calls one.
PACKET_VECTOR, BYTE_VECTOR = "packet", "byte"
SLOTS = (
    ("midivec", addrs.KBDVECS_MIDIVEC, BYTE_VECTOR),
    ("vkbderr", addrs.KBDVECS_VKBDERR, BYTE_VECTOR),
    ("vmiderr", addrs.KBDVECS_VMIDERR, BYTE_VECTOR),
    ("statvec", addrs.KBDVECS_STATVEC, PACKET_VECTOR),
    ("mousevec", addrs.KBDVECS_MOUSEVEC, PACKET_VECTOR),
    ("clockvec", addrs.KBDVECS_CLOCKVEC, PACKET_VECTOR),
    ("joyvec", addrs.KBDVECS_JOYVEC, PACKET_VECTOR),
)
STUB_AT = {name: STUB_BASE + index * STUB_STRIDE for index, (name, _off, _kind) in enumerate(SLOTS)}
REPORT_AT = {name: REPORT_BASE + index * REPORT_BYTES
             for index, (name, _off, _kind) in enumerate(SLOTS)}
SLOT_AT = {name: addrs.KBDVECS + offset for name, offset, _kind in SLOTS}
KIND_OF = {name: kind for name, _offset, kind in SLOTS}

# ...and three more stubs above them: a DECOY (staged, never meant to run), a recorder that reports
# A0 INSTEAD of the stack — the keyboard's own mouse emulation pushes nothing — and one that reports
# BOTH, which is what says the packet dispatch really passes its packet twice.
DECOY_STUB = STUB_BASE + len(SLOTS) * STUB_STRIDE
A0_STUB = DECOY_STUB + STUB_STRIDE
BOTH_STUB = A0_STUB + STUB_STRIDE
DECOY_REPORT = REPORT_BASE + len(SLOTS) * REPORT_BYTES
A0_REPORT = DECOY_REPORT + REPORT_BYTES
BOTH_REPORT = A0_REPORT + REPORT_BYTES           # two longwords: the pushed one, then A0
BOTH_REPORT_BYTES = 2 * REPORT_BYTES

assert BOTH_STUB + STUB_STRIDE <= isr.MARKS, "this module's stubs reach into the marks region"
assert BOTH_REPORT + BOTH_REPORT_BYTES <= isr.ISR_BAND + isr.ISR_BAND_BYTES, (
    "this module's reports reach past the band test/isr.py declares")
assert STUB_BASE >= isr.STUB_BAND, "this module's stubs start below the stub band"


# ---- the recorders -------------------------------------------------------------------------------
# One opcode this module assembles that `test/isr.py` does not already name: `move.b <long>.l,<long>.l`,
# which is how a stub reports a byte of the image rather than one of its own registers.
MOVE_B_ABSOLUTE_TO_ABSOLUTE = 0x13F9

def packet_recorder(report):
    """A stub that reports the LONGWORD its caller pushed: `move.l 4(sp),(report).l / rts`."""
    def effect(buf, argument):
        isr.poke(buf, report, struct.pack(">I", argument))
    return isr.store_frame_long(report) + isr.RTS, effect


def byte_recorder(report):
    """...and one that reports D0: `move.b d0,(report).l / rts`, for a vector handed a raw byte."""
    def effect(buf, argument):
        buf[report] = argument & 0xFF
    return isr.store_register(isr.MOVE_B_D0_ABSOLUTE, report) + isr.RTS, effect


def a0_recorder(report):
    """...and one that reports A0, for the call that pushes nothing at all (`$fc2e9a`)."""
    def effect(buf, argument):
        isr.poke(buf, report, struct.pack(">I", argument))
    return isr.store_register(isr.MOVE_L_A0_ABSOLUTE, report) + isr.RTS, effect


def state_recorder(report):
    """...and one that reports the PACKET STATE BYTE as its handler finds it: `move.b $e36,(report).l`.

    The ROM clears that byte AFTER the call, so a handler looking at it sees the packet still in
    progress — which is otherwise invisible, since the byte ends at 0 whichever order the two
    instructions are in.
    """
    def effect(buf, _argument):
        buf[report] = buf[addrs.IKBD_PACKET_KIND]
    return (struct.pack(">HII", MOVE_B_ABSOLUTE_TO_ABSOLUTE, addrs.IKBD_PACKET_KIND, report)
            + isr.RTS), effect


def both_recorder(report):
    """...and one that reports BOTH, which is what turns "the packet is passed twice" into a claim.

    The candidate writes the hook's one argument into both longwords, so the case is green only if
    the ORIGINAL's pushed longword and its A0 were the same address.
    """
    def effect(buf, argument):
        isr.poke(buf, report, struct.pack(">II", argument, argument))
    return (isr.store_frame_long(report)
            + isr.store_register(isr.MOVE_L_A0_ABSOLUTE, report + REPORT_BYTES) + isr.RTS), effect


def recorder_for(name, report=None):
    """The recorder one KBDVECS slot's contract asks for."""
    report = REPORT_AT[name] if report is None else report
    return packet_recorder(report) if KIND_OF[name] == PACKET_VECTOR else byte_recorder(report)


def stage(**overrides):
    """Every KBDVECS slot pointed at its own recorder, and the recorders themselves.

    Returns `(pokes, routines)` for `isr.staged_routines` and the case's own poke dict. An override
    names a slot and the address to point it at instead — a decoy, a stub of another shape, or a ROM
    routine the case wants run for real.
    """
    routines = {STUB_AT[name]: recorder_for(name) for name, _offset, _kind in SLOTS}
    pokes = {SLOT_AT[name]: struct.pack(">I", overrides.get(name, STUB_AT[name]))
             for name, _offset, _kind in SLOTS}
    return pokes, routines


# ---- one case of this chain: the image it stages, the differential, and the registry row ----------
# Every battery that enters these routines stages the SAME image — all seven slots pointed at their
# recorders, the recorder bytes poked, the candidate's hook told about them — so it is built once
# here rather than three times over (`test_bios_acia_service.py`, `test_bios_keyboard.py`, and the
# handler battery next door, which reaches them through `isr.run`).

def staged_image(vectors=None, routines=None, pokes=None):
    """`(pokes, routines)` for one case: the seven slots, the stubs they point at, and its own pokes.

    `vectors` points a slot somewhere else — a stub of another shape, or a ROM routine the case wants
    run for real — and `routines` stages what it points at.
    """
    slot_pokes, staged_routines = stage(**(vectors or {}))
    staged_routines.update(routines or {})
    return {**slot_pokes, **isr.routine_pokes(staged_routines), **(pokes or {})}, staged_routines


def run(entry, glue, *, pokes=None, routines=None, io_seed=None, regs=None, poison=True,
        vectors=None):
    """One differential over a routine of the input chain, with all seven KBDVECS vectors staged."""
    image_pokes, staged_routines = staged_image(vectors, routines, pokes)
    with isr.staged_routines(staged_routines):
        return case.run(entry, {"a5": 0, **(regs or {}), "_pokes": image_pokes},
                        isr.recording(glue), width=case.NO_RESULT, poison=poison, io_seed=io_seed)


# A case SPEC is a dict in `run`'s own vocabulary — `entry` and `glue`, plus any of the keys below —
# and the `name` a registry row needs. The two functions after it turn ONE spec into the two things
# this project asks of a case: the `VERIFIED_CASES` row Tier 3 and the snapshot mask read, and the
# differential that proves it. One object, so a priced row cannot come to describe a run nobody
# verified — which is `test/isr.py`'s arrangement for the handlers, said again for the routines
# those handlers call through RAM.
_SPEC_KEYS = ("regs", "pokes", "routines", "io_seed", "vectors")


def registered(spec):
    """One `test_boot_snapshot.VERIFIED_CASES` row for a case of this chain.

    Its ENTRY is the routine's own ROM address: unlike a handler, one of these is CALLED — by the
    handler, through a KBDVECS slot — so there is no exception frame to stage and nothing to
    trampoline through. `bench/tier3.py`'s `VECTOR_ROUTINE_NAMES` is how a row gets from that entry
    back to the `CALL` signature, since neither the trap tables nor the vector table names it.

    No PSG seed and no schedule: nothing here plays a sound list or waits on a byte.
    """
    image_pokes, _routines = staged_image(spec.get("vectors"), spec.get("routines"),
                                          spec.get("pokes"))
    return (spec["name"], spec["entry"], {"a5": 0, **spec.get("regs", {})},
            image_pokes, None, spec.get("io_seed"), ())


def run_spec(spec, **overrides):
    """...and the DIFFERENTIAL of that same spec, entered through the `glue` the spec carries."""
    return run(spec["entry"], spec["glue"],
               **{key: spec[key] for key in _SPEC_KEYS if key in spec}, **overrides)


def reported(info, name):
    """The longword the recorder at `name` wrote, out of the ORACLE's write ledger."""
    report = REPORT_AT[name]
    return int.from_bytes(bytes(info["writes"][report + i] for i in range(REPORT_BYTES)), "big")


def reported_byte(info, name):
    """...and the single byte a BYTE vector's recorder wrote."""
    return info["writes"][REPORT_AT[name]]


def called(info, name):
    """Did the vector at `name` run at all? Its recorder writing is the whole of the evidence."""
    report = REPORT_AT[name]
    return report in info["writes"] if KIND_OF[name] == BYTE_VECTOR else (
        all(report + i in info["writes"] for i in range(REPORT_BYTES)))


# ---- what the two chips yielded ------------------------------------------------------------------
# The 6850's status bits a case sets, named here as the COMBINATIONS the service routine branches on
# rather than as the raw bits `addrs.h` carries: every case below is one of these four.
IDLE = 0                                                          # this chip did not raise the line
QUIET = addrs.ACIA_INTERRUPT                                      # ...it did, and has nothing to say
READY = addrs.ACIA_INTERRUPT | addrs.ACIA_RECEIVE_FULL            # a byte is waiting
OVERRAN = addrs.ACIA_INTERRUPT | addrs.ACIA_OVERRUN               # ...and one was lost
READY_AND_OVERRAN = READY | addrs.ACIA_OVERRUN

# The two chips, each as the (status register, data port) pair its service routine names.
IKBD_PORTS = (addrs.IKBD_ACIA_STATUS, addrs.IKBD_ACIA_DATA)
MIDI_PORTS = (addrs.MIDI_ACIA_STATUS, addrs.MIDI_ACIA_DATA)


def declare(ports, status, data=()):
    """`io_seed` for one 6850: what its status register answered, and what its data port yielded.

    `status` is a byte or a LIST of them (one per read — the routine reads it once per service
    call). `data` is the bytes the receive register popped, in order, and it is a list even when it
    is one byte long, because the length is the case's statement of how many reads it describes: a
    read past the end is refused on both shores rather than served a fabricated byte.
    """
    status_register, data_port = ports
    seed = {status_register: status}
    if data:
        seed[data_port] = list(data)
    return seed


def both_chips(midi_status=IDLE, midi_data=(), ikbd_status=IDLE, ikbd_data=()):
    """...and the pair, for a case that enters the ACIA HANDLER and reaches both service routines."""
    return {**declare(MIDI_PORTS, midi_status, midi_data),
            **declare(IKBD_PORTS, ikbd_status, ikbd_data)}


# ---- the cores, as the candidate's own entry points ----------------------------------------------
_IMAGE = ctypes.POINTER(ctypes.c_ubyte)
for _symbol, _args in (("midi_acia_service", [_IMAGE]),
                       ("ikbd_acia_service", [_IMAGE]),
                       ("acia_take_byte", [_IMAGE, ctypes.c_uint32, ctypes.c_uint32]),
                       ("midi_queue_byte", [_IMAGE, ctypes.c_uint32, ctypes.c_uint8]),
                       ("kbd_scancode", [_IMAGE, ctypes.c_uint8, ctypes.c_uint32]),
                       ("kbd_queue_key", [_IMAGE, ctypes.c_uint8, ctypes.c_uint32])):
    getattr(_lib, _symbol).argtypes = _args
    getattr(_lib, _symbol).restype = None
