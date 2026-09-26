"""The DISPATCHER'S OWN I/O — what `test_gemdos_dispatch_device.py` and `test_gemdos_dispatch_redirect.py`
share: the three arms of `src/gemdos/dispatch.c` that serve a call WITHOUT its handler.

  * the DEVICE-NAME arm ($fc9aca): `Fopen`/`Fcreate` of "CON:", "AUX:" or "PRN:";
  * the DEVICE arm ($fc99bc): an `Fread`/`Fwrite` whose handle resolves to a character device;
  * the REDIRECTED arms ($fd328a): a character-device call whose standard handle names a FILE.

Every case is a dispatcher SLICE (`gemdos_fs.slice_run`) over the staged disk — the file-system arms
need it, and the device arms reach the BIOS, so nothing here poisons (`gemdos_fs.run`'s note). What this
adds is the OPEN FILES a redirection points at, the character devices' machines, and one thing no other
battery needs: the termination record a NESTED dispatch arms (`NESTED_RECORD`).
"""
from harness import addrs, emu, make_image

import fs_file as ff
import fs_io as io
import gemdos
import gemdos_console as console
import gemdos_fs as fs
import gemdos_process as process
import test_bios_bconout as bconout
# The console as a program finds it — the IKBD ring empty, the typeahead queue empty and the two columns
# in step — is the console output battery's own machine, reused rather than restaged.
from test_gemdos_console_output import console_machine

# ---- open files ------------------------------------------------------------------------------------
# Two handle records, each naming an OFD over one of the disk's own files: the first two record slots
# (`ff.A_HANDLE`, `ff.ANOTHER_HANDLE`), which `test/fs_io.py` stages its open files in.


def open_file(cluster, length, position=0, handle=ff.A_HANDLE, at=io.OFD_AT):
    """The file starting at `cluster`, `length` bytes long, open on `handle` with its cursor at `position`
    — at 0, the cursor a fresh open leaves (no cluster yet)."""
    cursor = io.at_cursor(position, cluster + position // fs.CLUSTER_BYTES, position % fs.CLUSTER_BYTES) \
        if position else {}
    return {**io.open_file(cluster, length, at=at, **cursor), **ff.handle_naming(at, handle)}


def open_span(position=0, handle=ff.A_HANDLE, at=io.OFD_AT):
    """SPAN.DAT (three clusters of the 0x40 ramp)."""
    return open_file(fs.SPAN_CLUSTER, fs.SPAN_BYTES, position, handle, at)


def open_short(position=0, handle=ff.A_HANDLE, at=io.OFD_AT):
    """SHORT.TXT (one cluster, 100 bytes)."""
    return open_file(fs.SHORT_CLUSTER, fs.SHORT_BYTES, position, handle, at)


def short_text(text):
    """The disk with SHORT.TXT's first bytes replaced by `text` — the rest of its ramp, its length and its
    directory entry as they were."""
    return fs.disk(clusters={fs.SHORT_CLUSTER: text + fs.SHORT_BODY[len(text):]})


def written(result, length):
    """The first `length` bytes of the data buffer a write left at the head of the cache's data list."""
    return result.after(fs.buffer_at(result.order(1)[0]), length)


# ---- the character devices -----------------------------------------------------------------------------
# AUX: and PRN: as `test_bios_bconout.py` stages them for one `Bconout` each, which is also what several
# in a row need: the RS232 transmitter always busy (so every byte goes to the ring), the printer always
# ready. Each is `(pokes, seeds)`.
RS232 = (bconout.rs232_pokes(), {"io_seed": {addrs.MFP_TSR: bconout.TSR_SENDING}})
PRINTER = (bconout.printer_pokes(), {"psg_seed": bconout.PRINTER_PSG_SEED,
                                     "io_seed": {addrs.MFP_GPIP: bconout.GPIP_READY}})


def keys_queued(*records):
    """The console machine with `records` in GEMDOS's own typeahead queue — what a read takes first."""
    return console_machine(pokes=console.queue(console.DEVICE_CONSOLE, records))


# ---- running a slice -----------------------------------------------------------------------------------
# The staging under every slice here is `fs_io.engine`'s: the drive, an empty cache and the user buffer,
# then the case's own.


def run(selector, words, pokes, leaves=(), **seeds):
    """One dispatcher slice over `io.engine(pokes)`, with `leaves` bound as handlers (none: the arm under
    test calls no handler, and one it reached anyway is refused by name)."""
    return fs.slice_run(selector, words, io.engine(pokes), leaves, **seeds)


def _slice_machine(selector, words, pokes):
    """The whole machine a slice runs over, as a row registers it and the oracle-only run reads it."""
    return fs.machine({**io.engine(pokes), **gemdos.slice_pokes(selector, words)})


def register(name, selector, words, pokes, **seeds):
    """...and the same slice as a `VERIFIED_CASES` row."""
    return gemdos.register(f"gemdos_dispatch_selector, {name}", gemdos.TRAMPOLINE_AT, {"a5": 0},
                           _slice_machine(selector, words, pokes), **seeds)


# ---- a NESTED dispatch's termination record ---------------------------------------------------------
# The redirected `Cconrs` echoes each character through `$fc5078`, which calls the WHOLE dispatcher — so
# the ROM arms the termination record at `GEMDOS_TERMINATION_JMPBUF` again, with the nested frame's A6,
# its stack pointer and the resume address. That record is the one thing `src/gemdos/dispatch.c` omits
# (its header says why), and a slice that dispatches in a nested call is the one place it lands INSIDE a
# compared run: the original leaves it pointing into a nested frame that is dead once the echo returns,
# and the reconstruction leaves it as it was. A REAL DIVERGENCE, so such a case DROPS the twelve bytes
# from its compare by name (`NESTED_RECORD`, `case.run`'s `dropped`), and
# `test_a_nested_echo_arms_the_record_with_its_own_frame` holds what the original writes there to being
# that frame and nothing else.
NESTED_RECORD = ((addrs.GEMDOS_TERMINATION_JMPBUF, addrs.GEMDOS_TERMINATION_JMPBUF + process.JMPBUF_BYTES,
                  "the termination record a nested dispatch re-arms: the original writes it, and the "
                  "reconstruction omits the record (src/gemdos/dispatch.c)"),)


def nested_record(selector, words, pokes, max_insns):
    """The record the ORIGINAL's nested dispatch leaves, as `(A6, SP, resume)`, and the poke staging it —
    `(None, {})` for a run that made no nested dispatch (a line that echoed nothing)."""
    image = make_image(_slice_machine(selector, words, pokes))
    _final, writes, _regs = emu.run(image, gemdos.TRAMPOLINE_AT, {"a5": 0}, max_insns=max_insns)
    if addrs.GEMDOS_TERMINATION_JMPBUF not in writes:
        return None, {}
    record = bytes(writes[addrs.GEMDOS_TERMINATION_JMPBUF + offset] for offset in range(process.JMPBUF_BYTES))
    longs = tuple(int.from_bytes(record[at:at + 4], "big") for at in range(0, process.JMPBUF_BYTES, 4))
    return longs, {addrs.GEMDOS_TERMINATION_JMPBUF: record}


def record_mask(selector, words, pokes, max_insns):
    """`pokes` with the nested record staged as the original arms it — the TIER 3 ROW's stand-in for
    `NESTED_RECORD`, and a MASK rather than an input: the bench's second differential compares the whole
    image with no per-row exclusion, so the row puts the original's own twelve bytes in both images, the
    original's store over them changes nothing, and the span agrees by construction. Only a registered
    row uses it; a case drops the span instead, and says why."""
    return {**pokes, **nested_record(selector, words, pokes, max_insns)[1]}


# ---- the registry ---------------------------------------------------------------------------------
# The one span these cases poke outside every staged band: the byte a redirected `Cconout('\n')` really
# writes, at `('\n' << 16) | $7ef4` — free TPA the snapshot leaves zero.
LINE_FEED_BUFFER = (addrs.CON_LF << 16) | (addrs.GEMDOS_TERMINATION_JMPBUF & 0xFFFF)
CASE_FIELDS = (
    (LINE_FEED_BUFFER, 1, "the byte a redirected Cconout of LF writes from"),
)
