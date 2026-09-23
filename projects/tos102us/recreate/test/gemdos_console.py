"""The GEMDOS character-device group's case shape: one machine, four staged tables, one runner.

Four batteries share this — `test_gemdos_console_status.py`, `..._output.py`, `..._input.py` and
`..._line.py`. What it owns is what all of them need and none of them should spell twice: where the
ROM's own `trap #13` frame goes, how a case says which BIOS device each standard handle names, and
how the typeahead queue and the column counter are staged.

---------------------------------------------------------------------------------------------------
THE `savptr` DECLARATION IS `test/gemdos.py`'S, and every case here rests on it: a console leaf
reaches the BIOS through `GEMDOS_BIOS_TRAMPOLINE`'s `trap #13`, the oracle's trap dispatcher frames
46 bytes below `savptr`, and `gemdos.machine()` pokes `savptr` into the band the differential
already drops so that the frame lands in memory both sides treat as scratch. That module's own note
says what keeps it honest, and why NOTHING HERE POISONS — the oracle writes `savptr` itself, so an
inverted one would send its next frame somewhere the case never staged.

What stands in for the poison pass is staging, and it is this file's job: `gemdos.FILL` is written
under every field a case expects the routines to store — the trampoline's return slot, the typeahead
buffers, the `Cconrs` line — so a candidate that skipped a store leaves the fill where the oracle
left a value, and the ordinary byte diff says so.
"""
import ctypes
import struct
from collections import namedtuple

from harness import BASE_IMAGE, _lib, addrs

import case
import gemdos
import staging

# The D0 a case enters with. `Cconws` over an empty string and `Cconrs` with a zero maximum hand it
# straight back, and every other leaf must NOT — so it is marked rather than zero, and distinct from
# any address or count in this group.
MARKED_D0 = 0xC0DE_0000

# ---- the band this battery stages buffers in, inside the one `staging.py` describes ---------------
# The other tenants fill it from the bottom (Getmpb's and Protobt's buffers at +0, Keytbl's tables at
# +0x100..+0x300) and the top (+0x800 the trap dispatcher's, +0xd00 the interrupt handlers'), and
# `gemdos.py`'s shared argument list took the first half of the gap between them. This is the second
# half, and the two asserts are what say so rather than a comment nobody re-reads: a band that grew
# into either neighbour would stage a case's buffer over another battery's words.
BAND_BYTES = 0x200
BAND = staging.band(0x600, BAND_BYTES, "test/gemdos_console.py")

STRING_AT = BAND                    # `Cconws`' string
LINE_AT = BAND + 0x100              # ...and `Cconrs`' length-prefixed buffer

# ---- the running process's standard handles ------------------------------------------------------
# The basepage is READ OUT OF THE SNAPSHOT rather than written down — `GEMDOS_P_RUN` is a pointer the
# boot set up — and `gemdos.py` already does that reading for the whole wave, so this is its name
# rather than a second `int.from_bytes` of the same four bytes.
BASEPAGE = gemdos.BASEPAGE

HANDLE_INDEX = {"stdin": addrs.GEMDOS_STDIN, "stdout": addrs.GEMDOS_STDOUT,
                "stdaux": addrs.GEMDOS_STDAUX, "stdprn": addrs.GEMDOS_STDPRN}

# The three standard handle values, by the device each becomes. `handle + 3` is the whole of GEMDOS's
# device model (`src/gemdos/console.c`), so these are the only three a leaf is ever entered with.
HANDLE_CON = -1
HANDLE_AUX = -2
HANDLE_PRN = -3
DEVICE_PRINTER = 0
DEVICE_RS232 = 1
DEVICE_CONSOLE = 2


def handle_slot(which):
    """The byte in the basepage a leaf reads — `p_uft[which]`, by the name a case uses for it."""
    return BASEPAGE + addrs.BASEPAGE_HANDLES + HANDLE_INDEX[which]


def snapshot_handle(which):
    """...and what the captured machine holds there, which every case not about redirection uses."""
    return BASE_IMAGE[handle_slot(which)]


def handles(**values):
    """Pokes putting ONE standard handle somewhere else: `handles(stdout=HANDLE_AUX)`.

    `gemdos.standard_handles_poke` is the same bytes as a PREFIX — handle 0 upwards — which is the
    shape a case setting the whole table wants. Every case here moves one handle and leaves the rest
    as the boot left them, so this names them instead of counting to them.
    """
    return {handle_slot(which): bytes([value & 0xFF]) for which, value in values.items()}


def device_of(handle):
    """`addq.w #3` on the sign-extended handle byte — the BIOS device the leaf will reach."""
    return (handle + addrs.GEMDOS_HANDLE_TO_DEVICE) & 0xFFFF


# ---- GEMDOS's own per-device state ---------------------------------------------------------------

def column_slot(device):
    return addrs.GEMDOS_DEVICE_COLUMN + device * addrs.GEMDOS_DEVICE_COLUMN_BYTES


def column(device, value):
    """Where GEMDOS thinks this device's cursor is — what TAB expansion and the line editor's
    erase both measure against, and an ordinary word of RAM a case may set."""
    return {column_slot(device): struct.pack(">H", value & 0xFFFF)}


def queue_at(device):
    """The device's typeahead buffer, as `GEMDOS_CONSOLE_INIT` lays the three of them out."""
    return addrs.GEMDOS_TYPEAHEAD_BUFFER + device * addrs.GEMDOS_TYPEAHEAD_BUFFER_BYTES


def queue(device, records=(), *, count=None, read=None, write=None):
    """The whole typeahead queue for one device: its buffer, its count and its two pointers.

    The default is the queue an interrupt-driven machine would have left after `records` were polled
    into it — count and write pointer following the records, read pointer at the top — and the three
    are separately overridable because two cases need a queue no sequence of polls could produce: one
    whose count disagrees with its pointers, and one whose pointers are mid-buffer.

    The buffer is filled with `gemdos.FILL` first, so a record the candidate did not store shows as
    fill byte (see the module docstring on why this group does not poison).
    """
    base = queue_at(device)
    records = tuple(records)
    pokes = {base: bytes([gemdos.FILL]) * addrs.GEMDOS_TYPEAHEAD_BUFFER_BYTES}
    for index, record in enumerate(records):
        pokes[base + index * addrs.GEMDOS_TYPEAHEAD_RECORD_BYTES] = struct.pack(">I", record)
    pokes[addrs.GEMDOS_TYPEAHEAD_COUNT + device * addrs.GEMDOS_TYPEAHEAD_COUNT_BYTES] = \
        bytes([(len(records) if count is None else count) & 0xFF])
    step = addrs.GEMDOS_TYPEAHEAD_POINTER_BYTES
    after = base + len(records) * addrs.GEMDOS_TYPEAHEAD_RECORD_BYTES
    pokes[addrs.GEMDOS_TYPEAHEAD_READ + device * step] = \
        struct.pack(">I", base if read is None else read)
    pokes[addrs.GEMDOS_TYPEAHEAD_WRITE + device * step] = \
        struct.pack(">I", after if write is None else write)
    return pokes


def queue_state(final, device):
    """`(count, read, write)` as a run LEFT them — read out of the final image, so a battery can say
    what a routine did to the queue rather than only that both sides agree about it."""
    step = addrs.GEMDOS_TYPEAHEAD_POINTER_BYTES
    return (final[addrs.GEMDOS_TYPEAHEAD_COUNT + device * addrs.GEMDOS_TYPEAHEAD_COUNT_BYTES],
            case.long_in(final, addrs.GEMDOS_TYPEAHEAD_READ + device * step),
            case.long_in(final, addrs.GEMDOS_TYPEAHEAD_WRITE + device * step))


# ---- the leaves, and how a case enters one -------------------------------------------------------
# THREE SHAPES, because the ROM's fifteen entries read three different frames: nothing at all, one
# argument WORD, or one argument LONGWORD (a pointer). The C signatures follow the same three, so the
# shape decides the ctypes declaration and the frame the case pokes at once — which is what stops a
# case staging a word for a routine whose C takes a pointer.
NO_ARGUMENT = "none"
WORD = "word"
POINTER = "pointer"

Leaf = namedtuple("Leaf", "entry core shape")


def _leaf(name, shape):
    """One entry, bound to its `include/addrs.h` address and its C core of the same name.

    The C symbol is the `addrs.h` constant lower-cased, which is also `bench/tier3.py`'s own rule for
    resolving a row's core — so a leaf named here and a leaf priced there cannot be two functions.
    """
    entry = getattr(addrs, f"GEMDOS_{name.upper()}")
    core = getattr(_lib, f"gemdos_{name}")
    image = ctypes.POINTER(ctypes.c_ubyte)
    core.argtypes = {NO_ARGUMENT: [image],
                     WORD: [image, ctypes.c_uint16],
                     POINTER: [image, ctypes.c_uint32, ctypes.c_uint32]}[shape]
    core.restype = ctypes.c_uint32
    return Leaf(entry, core, shape)


CCONIN = _leaf("cconin", NO_ARGUMENT)
CRAWCIN = _leaf("crawcin", NO_ARGUMENT)
CNECIN = _leaf("cnecin", NO_ARGUMENT)
CAUXIN = _leaf("cauxin", NO_ARGUMENT)
CCONIS = _leaf("cconis", NO_ARGUMENT)
CAUXIS = _leaf("cauxis", NO_ARGUMENT)
CCONOS = _leaf("cconos", NO_ARGUMENT)
CPRNOS = _leaf("cprnos", NO_ARGUMENT)
CAUXOS = _leaf("cauxos", NO_ARGUMENT)
CCONOUT = _leaf("cconout", WORD)
CAUXOUT = _leaf("cauxout", WORD)
CPRNOUT = _leaf("cprnout", WORD)
CRAWIO = _leaf("crawio", WORD)
CCONWS = _leaf("cconws", POINTER)
CCONRS = _leaf("cconrs", POINTER)


def _frame(leaf, argument):
    """The words the GEMDOS dispatcher's caller left above the return address, per shape."""
    if leaf.shape is NO_ARGUMENT:
        return {}
    if leaf.shape is WORD:
        return case.word_arg(argument)
    return case.long_args(argument)


def _pokes(spec):
    return {**gemdos.machine(), **_frame(spec["leaf"], spec.get("argument", 0)),
            **spec.get("pokes", {})}


def _regs(spec):
    # A5 = 0 for this project's own reason (`test/abi.py`): every ROM routine here is entered the way
    # a dispatcher leaves it. None of these fifteen reads A5 — each saves and restores it — so the
    # value is a convention rather than a claim.
    return {"a5": 0, "d0": spec.get("entry_d0", MARKED_D0)}


def run(spec, **overrides):
    """One differential over a GEMDOS console leaf, entered at its own ROM address.

    A SPEC is a dict — `name`, `leaf`, and any of `argument`, `entry_d0`, `pokes`, `io_seed`,
    `psg_seed` — and `registered` below turns the same object into its `VERIFIED_CASES` row, so a
    priced row cannot come to describe a run nobody verified (`test/acia.py`'s arrangement).

    `overrides` REPLACE a spec's keys rather than merging into them, which is what lets a battery
    drive one spec's neighbour without writing a second spec: `run(SPEC, pokes=...)` is that spec
    with a different staged machine, not that spec with two.
    """
    spec = {**spec, **overrides}
    leaf, entry_d0 = spec["leaf"], spec.get("entry_d0", MARKED_D0)
    argument = spec.get("argument", 0)

    def glue(_harness_lib, buf):
        if leaf.shape is NO_ARGUMENT:
            return leaf.core(buf)
        if leaf.shape is WORD:
            return leaf.core(buf, argument & 0xFFFF)
        return leaf.core(buf, entry_d0, argument)

    # `poison=False`: see the module docstring — the oracle writes `savptr`, and an inverted one
    # sends the ROM's own save frame somewhere the case never staged.
    pokes = _pokes(spec)
    info = case.run(leaf.entry, {**_regs(spec), "_pokes": pokes}, glue, poison=False,
                    io_seed=spec.get("io_seed"), psg_seed=spec.get("psg_seed"))
    info["final"] = case.final_image(info, pokes)
    return info


def registered(spec):
    """One `VERIFIED_CASES` row for a spec, recorded in `gemdos.CASES` and returned.

    The registration goes through `gemdos.register` rather than into a list of this group's own:
    three waves are adding GEMDOS rows at once, and one list means the orchestrator splices
    `*gemdos.CASES` once instead of once per battery.

    No schedule: nothing in this group waits on a byte an external agent stores. The blocking wait
    these leaves DO have is the BIOS's own ring spin, and a case ends it by staging the record
    (`test/iorec.py`), exactly as `test_bios_bconin.py` does.
    """
    return gemdos.register(spec["name"], spec["leaf"].entry, _regs(spec), _pokes(spec),
                           psg_seed=spec.get("psg_seed"), io_seed=spec.get("io_seed"))


# Every span a case in this group reads or pokes, for `test_boot_snapshot.py`'s mask check. The
# per-device tables are declared whole — three entries each, which is what `GEMDOS_CONSOLE_INIT`
# initialises — because a case that moved a handle reaches a different one of the three.
# The standard handles themselves are NOT here, and neither is `p_run`: `gemdos.CASE_FIELDS`
# declares both spans for the whole wave, and two entries for one span would be two places to keep a
# width right.
CASE_SPANS = (
    (addrs.GEMDOS_DEVICE_COLUMN, addrs.GEMDOS_CONSOLE_DEVICES * addrs.GEMDOS_DEVICE_COLUMN_BYTES,
     "the per-device column counters"),
    (addrs.GEMDOS_TYPEAHEAD_COUNT,
     addrs.GEMDOS_CONSOLE_DEVICES * addrs.GEMDOS_TYPEAHEAD_COUNT_BYTES,
     "the per-device typeahead counts"),
    (addrs.GEMDOS_TYPEAHEAD_READ,
     addrs.GEMDOS_CONSOLE_DEVICES * addrs.GEMDOS_TYPEAHEAD_POINTER_BYTES,
     "the typeahead read pointers"),
    (addrs.GEMDOS_TYPEAHEAD_WRITE,
     addrs.GEMDOS_CONSOLE_DEVICES * addrs.GEMDOS_TYPEAHEAD_POINTER_BYTES,
     "the typeahead write pointers"),
    (addrs.GEMDOS_TYPEAHEAD_BUFFER,
     addrs.GEMDOS_CONSOLE_DEVICES * addrs.GEMDOS_TYPEAHEAD_BUFFER_BYTES,
     "the three typeahead queues themselves"),
    (addrs.GEMDOS_BIOS_RETURN_SLOT, 4, "the longword the BIOS trampoline parks its return in"),
)
