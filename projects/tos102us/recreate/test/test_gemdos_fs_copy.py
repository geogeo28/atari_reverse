"""The file system's three byte copies — `src/gemdos/fs_copy.c`, one loop behind $fc55fa, $fc5622, $fc564a.

Each ROM entry is proved by its own differential, over its own argument order: the point of having
three entry points is that the transfer engine hands `copy_out` and `copy_in` the SAME (n, cache,
user) frame and gets opposite directions, so a reconstruction that swapped one pair would copy the
wrong way and this is where it reddens.
"""
import pytest

from harness import _lib, addrs

import case
import fs_records
import gemdos
import gemdos_fs as fs

for _name in ("gemdos_copy_out", "gemdos_copy_in", "gemdos_bcopy"):
    getattr(_lib, _name).restype = None

# Two buffers, the band's halves. The FIRST holds a ramp and the SECOND is pre-filled, so a byte
# copied from the wrong place, or a byte the copy should not have touched, is a wrong value in the diff.
COPY_BAND = fs.SPAN.claim(fs_records.COPY_BAND_AT, fs_records.COPY_BAND_BYTES, "test/test_gemdos_fs_copy.py")
BUFFER_BYTES = fs_records.COPY_BAND_BYTES // 2
LOW_AT = COPY_BAND
HIGH_AT = COPY_BAND + BUFFER_BYTES
RAMP_SEED = 0x31
OVERLAP_STEP = 0x10
# The ROM loop is nine instructions a byte, which a 0x8000-byte copy takes past the oracle's default cap.
LOOP_INSNS_PER_BYTE = 9
LOOP_INSNS_SLACK = 100
# A D0 whose high half the loop must leave standing — and a LOW word it must overwrite, with the
# last count it tested (0), which the shared value's zero low word could not show.
LOW_WORD_MARK = 0x77
ENTRY_D0 = fs.ENTRY_D0 | LOW_WORD_MARK

# Each routine and the ROLE of its second and third arguments.
SOURCE_FIRST = "source first"
DESTINATION_FIRST = "destination first"
ROUTINES = (
    (addrs.GEMDOS_COPY_OUT, "gemdos_copy_out", SOURCE_FIRST),
    (addrs.GEMDOS_COPY_IN, "gemdos_copy_in", DESTINATION_FIRST),
    (addrs.GEMDOS_BCOPY, "gemdos_bcopy", SOURCE_FIRST),
)


def _ramp(length):
    return bytes((RAMP_SEED + index) & 0xFF for index in range(length))


def _buffers():
    return {LOW_AT: _ramp(BUFFER_BYTES), HIGH_AT: bytes([fs.SLACK_FILL]) * BUFFER_BYTES}


def _frame(order, count, source, destination):
    """The (n.w, a.l, b.l) frame, `a`/`b` in the routine's own order."""
    first, second = (source, destination) if order == SOURCE_FIRST else (destination, source)
    return case.args(">HII", count, first, second)


def _run(entry, symbol, order, count, source, destination, pokes=None, **seeds):
    frame = _frame(order, count, source, destination)
    first, second = ((source, destination) if order == SOURCE_FIRST else (destination, source))
    return case.run(entry, {"d0": ENTRY_D0, "_pokes": {**_buffers(), **(pokes or {}), **frame}},
                    lambda lib, buf: getattr(lib, symbol)(buf, count, first, second),
                    width=case.NO_RESULT, **seeds)


@pytest.mark.parametrize("entry,symbol,order", ROUTINES, ids=[row[1] for row in ROUTINES])
@pytest.mark.parametrize("count", (0, 1, 2, 11, 0x100, BUFFER_BYTES))
def test_a_copy_moves_exactly_count_bytes_in_its_own_argument_order(entry, symbol, order, count):
    """LOW -> HIGH, `count` bytes and not one more: the pre-filled tail of HIGH must stand."""
    info = _run(entry, symbol, order, count, LOW_AT, HIGH_AT)
    final = case.final_image(info, _buffers())
    assert bytes(final[HIGH_AT:HIGH_AT + count]) == _ramp(count)
    assert bytes(final[HIGH_AT + count:HIGH_AT + BUFFER_BYTES]) == bytes(
        [fs.SLACK_FILL]) * (BUFFER_BYTES - count)
    # `move.w n,d0` last saw the count reach 0; the caller's high half is left standing.
    assert info["regs"]["d0"] == fs.callers_high_half(ENTRY_D0)


@pytest.mark.parametrize("entry,symbol,order", ROUTINES, ids=[row[1] for row in ROUTINES])
def test_an_overlapping_copy_upward_smears_forward_like_the_rom(entry, symbol, order):
    """A destination one byte above its source: a FORWARD byte loop re-reads what it just wrote, so
    the first byte is smeared along the whole span. A memmove would shift the ramp instead."""
    count = 0x40
    info = _run(entry, symbol, order, count, LOW_AT, LOW_AT + 1)
    final = case.final_image(info, _buffers())
    assert bytes(final[LOW_AT:LOW_AT + count + 1]) == bytes([RAMP_SEED]) * (count + 1)


@pytest.mark.parametrize("entry,symbol,order", ROUTINES, ids=[row[1] for row in ROUTINES])
def test_an_overlapping_copy_downward_shifts(entry, symbol, order):
    """...and one byte BELOW: the forward loop reads each byte before it is overwritten."""
    count = 0x40
    info = _run(entry, symbol, order, count, LOW_AT + 1, LOW_AT)
    final = case.final_image(info, _buffers())
    assert bytes(final[LOW_AT:LOW_AT + count]) == _ramp(count + 1)[1:]


@pytest.mark.parametrize("entry,symbol,order", ROUTINES, ids=[row[1] for row in ROUTINES])
def test_the_count_is_an_unsigned_word(entry, symbol, order):
    """A count with bit 15 set is not negative: `tst.w` is only ever asked "zero or not". A span that
    large does not fit the band, so it is copied inside the RAM disk's image span, left unstaged
    (zero in the capture, `test_gemdos_fs_disk.py`): the values are zeros and only the LENGTH is
    the claim — the attribution pass makes every one of the 0x8000 stores a compared fact."""
    count = 0x8000
    source = fs.IMAGE_AT
    assert source + OVERLAP_STEP + count <= fs.RAM_DISK_AT + fs.RAM_DISK_BYTES
    info = _run(entry, symbol, order, count, source, source + OVERLAP_STEP,
                max_insns=count * LOOP_INSNS_PER_BYTE + LOOP_INSNS_SLACK)
    assert info["regs"]["d0"] == fs.callers_high_half(ENTRY_D0)


# ---- the registry --------------------------------------------------------------------------------

for _entry, _symbol, _order in ROUTINES:
    gemdos.register(f"{_symbol}, 0x40 bytes", _entry, {"d0": ENTRY_D0},
                    {**_buffers(), **_frame(_order, 0x40, LOW_AT, HIGH_AT)})
