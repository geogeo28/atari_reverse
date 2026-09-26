"""`Fread` ($3f), `Fwrite` ($40) and `Fseek` ($42) — the I/O engine's three GEMDOS leaves — each
entered at its own address and then THROUGH THE DISPATCHER, against the ROM's own leaf.

A leaf is `$fc51c0` (the handle's record, via `p_uft` for 0..5) and then the engine: EIHNDL for a
handle that names nothing, and otherwise `$fc5e9c`/`$fc5f1c`/`$fc7d2a` on the OFD it names. `Fseek`
makes the offset absolute first — from the start, the current position or the end — and answers
EINVFN for any other mode, AFTER the handle: a bad handle is EIHNDL whatever the mode.

THE DISPATCHED CASES are the other half of `test_gemdos_handles.py`'s file arm. That battery could
only say the ORIGINAL reaches the ordinary dispatch at `$fc9ac6` with a file handle, because the
handler behind it was the file system's; now both shores run a leaf, so the whole slice is one
differential — our dispatcher calling our `Fread` through the hook, bound by the address the ROM's
table holds.
"""
import ctypes
import struct

import pytest

from harness import _lib, addrs

import case
import fs_io as io
import gemdos
import gemdos_fs as fs
import gemdos_process as process

for _name in ("gemdos_fread", "gemdos_fwrite", "gemdos_fseek", "gemdos_dispatch_selector"):
    getattr(_lib, _name).restype = ctypes.c_uint32

EIHNDL = addrs.GEMDOS_EIHNDL
EINVFN = addrs.GEMDOS_EINVFN
ERANGE = fs.GEMDOS_ERANGE
A_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE
A_STANDARD = 1                              # a standard handle, redirected to `A_HANDLE`
OWNER = gemdos.BASEPAGE

NAMES_THE_FILE = process.descriptor_poke(A_HANDLE, io.OFD_AT, OWNER)
NAMES_NOTHING = process.descriptor_poke(A_HANDLE, 0, OWNER)
SPAN = io.open_file(fs.SPAN_CLUSTER, fs.SPAN_BYTES, **io.at_cursor(1100, 5, 76))


# Each leaf's C symbol and its frame, as the ROM's caller lays it: `Fseek`'s is the offset first.
FREAD = (addrs.GEMDOS_FREAD, "gemdos_fread", ">hII")
FWRITE = (addrs.GEMDOS_FWRITE, "gemdos_fwrite", ">hII")
FSEEK = (addrs.GEMDOS_FSEEK, "gemdos_fseek", ">IhH")


def _leaf_pokes(leaf, values, pokes):
    _entry, _symbol, frame = leaf
    return {**SPAN, **pokes, **case.args(frame, *values)}


def _leaf(leaf, values, pokes):
    entry, symbol, _frame = leaf
    return io.run(entry, lambda lib, buf: getattr(lib, symbol)(buf, *values),
                  _leaf_pokes(leaf, values, pokes))


def _fread(handle, count, pokes=NAMES_THE_FILE):
    return _leaf(FREAD, (handle, count, fs.USER_AT), pokes)


def _fwrite(handle, data, pokes=NAMES_THE_FILE):
    return _leaf(FWRITE, (handle, len(data), fs.USER_AT), {**fs.user_buffer(data), **pokes})


def _fseek(offset, handle, mode, pokes=NAMES_THE_FILE):
    return _leaf(FSEEK, (offset & 0xFFFF_FFFF, handle, mode), pokes)


# ---- Fread / Fwrite ----------------------------------------------------------------------------------

@pytest.mark.parametrize("handle,pokes,why", (
    (A_HANDLE, NAMES_THE_FILE, "a handle record naming the OFD"),
    (A_STANDARD, {**NAMES_THE_FILE, **gemdos.standard_handles_poke([0, A_HANDLE])},
     "a STANDARD handle whose p_uft byte names that record"),
))
def test_fread_reads_the_file_its_handle_names(handle, pokes, why):
    result = _fread(handle, 200, pokes)
    assert result.info["ret"] == 200, why
    assert result.after(fs.USER_AT, 200) == fs.SPAN_BODY[1100:1300], why


def test_fwrite_writes_through_the_cache():
    new = bytes(range(0x61, 0x61 + 26))
    result = _fwrite(A_HANDLE, new)
    head = result.order(1)[0]
    assert result.info["ret"] == len(new)
    assert result.after(fs.buffer_at(head) + 76, len(new)) == new


@pytest.mark.parametrize("leaf", ("read", "write"))
def test_a_handle_that_names_nothing_is_eihndl(leaf):
    result = _fread(A_HANDLE, 10, NAMES_NOTHING) if leaf == "read" \
        else _fwrite(A_HANDLE, b"x", NAMES_NOTHING)
    assert result.info["ret"] == EIHNDL
    assert not fs.DISK_CALLS


# ---- Fseek -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("offset,mode,position,why", (
    (1500, fs.GEMDOS_SEEK_FROM_START, 1500, "from the start"),
    (600, fs.GEMDOS_SEEK_FROM_CURRENT, 1700, "from the CURRENT position, 1100"),
    (-100, fs.GEMDOS_SEEK_FROM_END, fs.SPAN_BYTES - 100, "from the END, the length"),
    (-1200, fs.GEMDOS_SEEK_FROM_CURRENT, ERANGE, "...to before the start: ERANGE"),
    (1, fs.GEMDOS_SEEK_FROM_END, ERANGE, "...past the end: ERANGE"),
    (0, 3, EINVFN, "any other mode"),
))
def test_fseek_makes_the_offset_absolute_then_seeks(offset, mode, position, why):
    result = _fseek(offset, A_HANDLE, mode)
    assert result.info["ret"] == position, why


def test_fseek_with_a_bad_handle_is_eihndl_before_the_mode_is_read():
    result = _fseek(0, A_HANDLE, 3, NAMES_NOTHING)
    assert result.info["ret"] == EIHNDL


# ---- through the dispatcher -------------------------------------------------------------------------

def _argument_values(buf, arguments, frame):
    """The words the dispatcher copied, read back out of the CANDIDATE's image in `frame`'s shape —
    which is what proves our dispatcher passed the frame the leaf reads, rather than the case
    handing the leaf the values it hoped were there."""
    raw = ctypes.string_at(ctypes.addressof(buf.contents) + arguments, struct.calcsize(frame))
    return struct.unpack(frame, raw)


# Each leaf's handler as the dispatcher's hook reaches it: keyed by the address the ROM's table
# holds, which `test_each_leaf_is_what_the_table_names` checks is the leaf's own.
LEAVES = {addrs.GEMDOS_FREAD_FN: FREAD, addrs.GEMDOS_FWRITE_FN: FWRITE, addrs.GEMDOS_FSEEK_FN: FSEEK}


def _handler(symbol, frame):
    return lambda buf, arguments, _width: getattr(_lib, symbol)(
        buf, *_argument_values(buf, arguments, frame))


HANDLERS = {entry: _handler(symbol, frame) for entry, symbol, frame in LEAVES.values()}


@pytest.mark.parametrize("selector", sorted(LEAVES))
def test_each_leaf_is_what_the_table_names(selector):
    assert gemdos.rom_handler(selector) == LEAVES[selector][0]


def _dispatch(selector, words, pokes):
    """A dispatcher slice (`gemdos.slice_pokes`) over the staged disk. Not `gemdos.run_slice`: that
    policy poisons, and a run that reaches the BIOS cannot (`test/gemdos_fs.py`, `run`). The one fs
    case that is not `gemdos_fs.run`'s shape: its glue is the dispatcher's, with the leaves bound
    behind it, and the handler calls it records are part of the claim."""
    def glue(lib, buf):
        return lib.gemdos_dispatch_selector(buf, gemdos.ARGUMENTS_AT)

    with gemdos.bound_handlers(HANDLERS):
        result = io.run(gemdos.TRAMPOLINE_AT, gemdos.recording(glue),
                        {**SPAN, **pokes, **gemdos.slice_pokes(selector, words)})
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [gemdos.rom_handler(selector)]
    return result


def test_a_dispatched_fread_on_a_file_handle_runs_the_leaf():
    result = _dispatch(addrs.GEMDOS_FREAD_FN,
                       (A_HANDLE, *gemdos.long_words(300), *gemdos.long_words(fs.USER_AT)),
                       NAMES_THE_FILE)
    assert result.info["ret"] == 300
    assert result.after(fs.USER_AT, 300) == fs.SPAN_BODY[1100:1400]


def test_a_dispatched_fwrite_on_a_standard_handle_runs_the_leaf():
    new = b"through the dispatcher"
    result = _dispatch(addrs.GEMDOS_FWRITE_FN,
                       (A_STANDARD, *gemdos.long_words(len(new)), *gemdos.long_words(fs.USER_AT)),
                       {**NAMES_THE_FILE, **gemdos.standard_handles_poke([0, A_HANDLE]),
                        **fs.user_buffer(new)})
    assert result.info["ret"] == len(new)


def test_a_dispatched_fseek_takes_its_handle_from_the_third_word():
    result = _dispatch(addrs.GEMDOS_FSEEK_FN,
                       (*gemdos.long_words(2100), A_HANDLE, fs.GEMDOS_SEEK_FROM_START),
                       NAMES_THE_FILE)
    assert result.info["ret"] == 2100


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("Fread, a handle record", addrs.GEMDOS_FREAD,
                _leaf_pokes(FREAD, (A_HANDLE, 200, fs.USER_AT), NAMES_THE_FILE))
    io.register("Fwrite, a handle record", addrs.GEMDOS_FWRITE,
                _leaf_pokes(FWRITE, (A_HANDLE, 26, fs.USER_AT), {**fs.user_buffer(b"x" * 26), **NAMES_THE_FILE}))
    io.register("Fseek, from the end", addrs.GEMDOS_FSEEK,
                _leaf_pokes(FSEEK, ((-100) & 0xFFFF_FFFF, A_HANDLE, fs.GEMDOS_SEEK_FROM_END), NAMES_THE_FILE))


_register_all()
