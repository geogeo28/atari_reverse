"""GEMDOS Cconin / Crawcin / Cnecin / Cauxin and `Crawio`'s read arm, over the typeahead queue.

BETWEEN A GEMDOS READ AND `Bconin` THERE IS A QUEUE, and it is the thing this file is about. Every
output GEMDOS makes polls the keyboard first (`drain_typeahead`) and moves whatever is waiting into
80 four-byte slots of its own; every read takes from there before it asks the BIOS. So a key typed
while the program was printing is already out of the IKBD's ring by the time the program asks for
it, and a reconstruction that only ever called `Bconin` would block for a key it already had.

THAT POLL IS ALSO WHERE FLOW CONTROL LIVES, and it is the only place in TOS that reads a key without
being asked to. ^S makes it read on, blocking, until ^Q; ^X empties the queue and leaves itself in
it for the line editor; ^C ends the process; and a queue with no room answers with a BEL.

THE FOUR READS DIFFER IN TWO BITS EACH — whether they ECHO and whether they POLL afterwards:

    Cconin   echoes (RAW, to the INPUT device), no poll
    Crawcin  neither
    Cnecin   no echo, polls AFTERWARDS — so ^C bites one call late rather than not at all
    Cauxin   neither, and does not touch the queue at all: straight to `Bconin`

`Cauxin` ON THE CAPTURED MACHINE REACHES A BIOS DRIVER THIS PROJECT DEFERS — `Bconin(AUX:)`
($fc2150), which `src/bios/bcon.c` halts on — so the case below moves stdaux to the CONSOLE handle.
That verifies the LEAF (read p_uft[2], add three, trap) over a driver that is reconstructed; what it
does not reach is the RS232 reader, and that is the BIOS's deferral rather than this group's.
"""
import struct

import pytest

from harness import addrs

import case
import gemdos_console as console
import iorec
import vt52

# IKBD records, as the keyboard handler builds them: a scancode word over an ASCII word. The LOW
# BYTE is what the poll classifies (`and.l #255,d0`) and the WHOLE LONGWORD is what gets queued, so
# the scancode half survives the queue and comes back out of a later `Cconin`.
A_KEY = 0x001E0061                      # 'a'
CTRL_S = 0x001F0013                     # hold
CTRL_Q = 0x00100011                     # release
CTRL_X = 0x002D0018                     # kill the queue
ANOTHER_KEY = 0x00300062                # 'b'

ECHOED_COLUMN = 3                       # where the echo lands, in both layers' idea of the column
RING = addrs.IOREC_IKBD
RECORD = addrs.IOREC_KEY_BYTES

# The queue's own bound. 79 records still fit; 80 do not, and the poll answers a BEL.
NEARLY_FULL = addrs.GEMDOS_TYPEAHEAD_MAX - 1


def _keys(*records):
    """The IKBD ring holding `records`, staged as the interrupt handler would have left it.

    The reader ADVANCES the head before it reads, so the first record sits one slot IN — which is
    `test_bios_bconin.py`'s own staging and the reason this is not `[(0, ...)]`.
    """
    laid = [((index + 1) * RECORD, struct.pack(">I", record))
            for index, record in enumerate(records)]
    return iorec.staged(RING, 0, len(records) * RECORD, laid)


def _machine(queue_records=(), ring_records=(), *, count=None, read=None, device=None, pokes=None):
    """The console as a reading program finds it: a queue, a ring, and both columns in step."""
    device = console.DEVICE_CONSOLE if device is None else device
    return {**_keys(*ring_records),
            **console.queue(device, queue_records, count=count, read=read),
            **console.column(device, ECHOED_COLUMN),
            **vt52.staged(ECHOED_COLUMN, 0, cursor_depth=1, extra_flags=vt52.WRAP),
            **(pokes or {})}


# ---- the specs -----------------------------------------------------------------------------------

CCONIN_FROM_RING = {"name": "gemdos_cconin, from the BIOS ring", "leaf": console.CCONIN,
                    "pokes": _machine(ring_records=(A_KEY,))}
CCONIN_FROM_QUEUE = {"name": "gemdos_cconin, from the typeahead queue", "leaf": console.CCONIN,
                     "pokes": _machine(queue_records=(A_KEY,))}
CCONIN_SECOND_OF_TWO = {"name": "gemdos_cconin, the second record of a queue of two",
                        "leaf": console.CCONIN,
                        "pokes": _machine(queue_records=(A_KEY, ANOTHER_KEY), count=1,
                                          read=console.queue_at(console.DEVICE_CONSOLE) + RECORD)}
CRAWCIN = {"name": "gemdos_crawcin", "leaf": console.CRAWCIN,
           "pokes": _machine(ring_records=(A_KEY,))}
CNECIN = {"name": "gemdos_cnecin, and the poll it makes afterwards", "leaf": console.CNECIN,
          "pokes": _machine(ring_records=(A_KEY, ANOTHER_KEY))}
CAUXIN_ON_CONSOLE = {"name": "gemdos_cauxin, stdaux redirected to CON:", "leaf": console.CAUXIN,
                     "pokes": {**_machine(ring_records=(A_KEY,)),
                               **console.handles(stdaux=console.HANDLE_CON)}}
CRAWIO_READ_EMPTY = {"name": "gemdos_crawio, read with nothing waiting", "leaf": console.CRAWIO,
                     "argument": addrs.GEMDOS_CRAWIO_READ, "pokes": _machine()}
CRAWIO_READ_QUEUED = {"name": "gemdos_crawio, read from the queue", "leaf": console.CRAWIO,
                      "argument": addrs.GEMDOS_CRAWIO_READ,
                      "pokes": _machine(queue_records=(A_KEY,))}
CRAWIO_READ_RING = {"name": "gemdos_crawio, read from the BIOS ring", "leaf": console.CRAWIO,
                    "argument": addrs.GEMDOS_CRAWIO_READ, "pokes": _machine(ring_records=(A_KEY,))}

# The poll itself, driven through the one leaf that makes it: `Cconout`.
DRAIN_QUEUES = {"name": "gemdos_cconout, the poll queues a waiting key", "leaf": console.CCONOUT,
                "argument": 0x41, "pokes": _machine(ring_records=(A_KEY,))}
DRAIN_HOLDS = {"name": "gemdos_cconout, the poll holds on ^S until ^Q", "leaf": console.CCONOUT,
               "argument": 0x41, "pokes": _machine(ring_records=(CTRL_S, CTRL_Q))}
DRAIN_CANCELS = {"name": "gemdos_cconout, ^X empties the queue and stays in it",
                 "leaf": console.CCONOUT, "argument": 0x41,
                 "pokes": _machine(queue_records=(A_KEY, ANOTHER_KEY), ring_records=(CTRL_X,))}
DRAIN_LAST_SLOT = {"name": "gemdos_cconout, the poll fills the queue's last slot",
                   "leaf": console.CCONOUT, "argument": 0x41,
                   "pokes": _machine(queue_records=tuple(A_KEY + n for n in range(NEARLY_FULL)),
                                     ring_records=(ANOTHER_KEY,))}
DRAIN_RINGS_THE_BELL = {"name": "gemdos_cconout, a full queue answers with a bell",
                        "leaf": console.CCONOUT, "argument": 0x41,
                        "pokes": _machine(
                            queue_records=tuple(A_KEY + n for n in range(addrs.GEMDOS_TYPEAHEAD_MAX)),
                            ring_records=(ANOTHER_KEY,),
                            pokes={addrs.SYSVAR_CONTERM: bytes([1 << addrs.CONTERM_BELL_BIT])})}

REGISTERED = (CCONIN_FROM_RING, CCONIN_FROM_QUEUE, CCONIN_SECOND_OF_TWO, CRAWCIN, CNECIN,
              CAUXIN_ON_CONSOLE, CRAWIO_READ_EMPTY, CRAWIO_READ_QUEUED, CRAWIO_READ_RING,
              DRAIN_QUEUES, DRAIN_HOLDS, DRAIN_CANCELS, DRAIN_LAST_SLOT, DRAIN_RINGS_THE_BELL)
VERIFIED_CASES = tuple(console.registered(spec) for spec in REGISTERED)

QUEUE_AT = console.queue_at(console.DEVICE_CONSOLE)


def _queued(info, index=0):
    """The longword the run left in the queue's `index`th slot, out of the write ledger — so a
    record the reconstruction never stored is a KeyError naming the slot and not a stale byte."""
    return case.written_long(info, QUEUE_AT + index * RECORD)


def _echoed_bytes(info):
    return sorted(at for at in info["writes"] if at in set(vt52.cell_bytes(ECHOED_COLUMN, 0)))


def _column_moved(info):
    return console.column_slot(console.DEVICE_CONSOLE) in info["writes"]


# ---- the four reads ------------------------------------------------------------------------------

# Records whose halves are deliberately awkward: a key with no ASCII half, one whose ASCII half is a
# control code, and one whose whole longword has every bit set. A read that masked or rebuilt the
# record rather than handing back the BIOS's own longword passes a single-value case and fails these.
AWKWARD_RECORDS = (0x00000000, 0xFFFFFFFF, 0x00480000, CTRL_X, 0x1234_5678)


@pytest.mark.parametrize("record", AWKWARD_RECORDS)
@pytest.mark.parametrize("spec", (CRAWCIN, CNECIN, CAUXIN_ON_CONSOLE))
def test_the_three_reads_that_do_not_echo_hand_back_the_bios_record_whole(spec, record):
    """...including `Cnecin`, whose poll afterwards classifies the record's LOW BYTE — so ^X here
    empties the queue and queues itself, and the ANSWER is still the record that was read first."""
    pokes = {**spec["pokes"], **_keys(record)}
    assert console.run(spec, pokes=pokes)["regs"]["d0"] == record


@pytest.mark.parametrize("record", AWKWARD_RECORDS)
def test_cconin_echoes_the_low_word_of_whatever_record_it_read(record):
    """The echo is `move.w d0,(sp)` on the longword, so a record with no ASCII half echoes a NUL and
    a record of all ones echoes $ffff — neither of which is a printable character, and neither of
    which may move the column counter."""
    info = console.run(CCONIN_FROM_RING, pokes={**CCONIN_FROM_RING["pokes"], **_keys(record)})
    # `cmp.w #32 / bge` on the echoed word, SIGNED — which is why $ffff is not printable here.
    printable = 0x20 <= (record & 0xFFFF) < 0x8000
    assert info["regs"]["d0"] == record
    assert _column_moved(info) == printable



def test_cconin_returns_the_whole_bios_record_and_echoes_its_low_word():
    """The scancode half comes back untouched and only the ASCII half is printed — `move.w d0,(sp)`
    on a longword, which is also why the echo of a key with no ASCII is a NUL."""
    info = console.run(CCONIN_FROM_RING)
    assert info["regs"]["d0"] == A_KEY
    assert _echoed_bytes(info) == sorted(vt52.cell_bytes(ECHOED_COLUMN, 0))
    assert case.written(info, console.column_slot(console.DEVICE_CONSOLE), 2) == ECHOED_COLUMN + 1


def test_cconin_takes_a_queued_record_without_asking_the_bios_and_rewinds_the_queue():
    """THE WHOLE POINT OF THE QUEUE. The record comes out of GEMDOS's own slots, and emptying them
    puts BOTH pointers back at the top — so the next 80 characters have room again."""
    info = console.run(CCONIN_FROM_QUEUE)
    assert info["regs"]["d0"] == A_KEY
    count, read, write = console.queue_state(info["final"], console.DEVICE_CONSOLE)
    assert (count, read, write) == (0, QUEUE_AT, QUEUE_AT)
    assert addrs.IOREC_IKBD + addrs.IOREC_HEAD not in info["writes"], (
        "the ring's head moved, so the record came from the BIOS and not from the queue")


def test_the_queue_is_first_in_first_out():
    """The second of two, read through a read pointer one record in — which is what says the queue
    is a queue and not a one-slot cache."""
    assert console.run(CCONIN_SECOND_OF_TWO)["regs"]["d0"] == ANOTHER_KEY


def test_crawcin_reads_without_echoing_and_without_polling():
    """Neither bit: no character on the screen, no column moved, and the only BIOS call it makes is
    the read itself."""
    info = console.run(CRAWCIN)
    assert info["regs"]["d0"] == A_KEY
    assert _echoed_bytes(info) == []
    assert not _column_moved(info)


def test_cnecin_does_not_echo_but_polls_afterwards():
    """Two keys waiting: the first is the answer, and the SECOND is swept into the queue by the poll
    `Cnecin` makes after it. A reconstruction that skipped that poll returns the same value and
    leaves the queue empty."""
    info = console.run(CNECIN)
    assert info["regs"]["d0"] == A_KEY
    assert _echoed_bytes(info) == []
    assert _queued(info) == ANOTHER_KEY


def test_cauxin_is_its_own_handle_and_nothing_else():
    """No queue, no echo — the leaf is `Bconin(p_uft[2] + 3)` and three instructions."""
    info = console.run(CAUXIN_ON_CONSOLE)
    assert info["regs"]["d0"] == A_KEY
    assert _echoed_bytes(info) == []
    assert QUEUE_AT not in info["writes"]


# ---- Crawio's read arm ---------------------------------------------------------------------------

def test_crawio_answers_a_plain_zero_when_nothing_is_waiting():
    """`clr.l d0` — not the `$ffffffff` the status call answers with, and not the caller's D0."""
    assert console.run(CRAWIO_READ_EMPTY)["regs"]["d0"] == 0


@pytest.mark.parametrize("spec", (CRAWIO_READ_QUEUED, CRAWIO_READ_RING))
def test_crawio_reads_through_the_queue_and_never_echoes(spec):
    info = console.run(spec)
    assert info["regs"]["d0"] == A_KEY
    assert _echoed_bytes(info) == []


# ---- the poll, and the flow control in it --------------------------------------------------------

def test_the_poll_moves_a_waiting_key_out_of_the_ring_and_into_the_queue():
    info = console.run(DRAIN_QUEUES)
    assert _queued(info) == A_KEY
    count, read, write = console.queue_state(info["final"], console.DEVICE_CONSOLE)
    assert (count, read, write) == (1, QUEUE_AT, QUEUE_AT + RECORD)
    assert case.written(info, RING + addrs.IOREC_HEAD, 2) == RECORD, "the ring's head did not move"


def test_a_hold_reads_on_until_the_release_and_queues_neither():
    """^S sets the flag and goes STRAIGHT back to `Bconin` — no status call in between, which is why
    this case needs a second record staged or both cores would block. ^Q clears it and the loop
    ends; neither key is queued, so a program never sees them."""
    info = console.run(DRAIN_HOLDS)
    count, _read, write = console.queue_state(info["final"], console.DEVICE_CONSOLE)
    assert (count, write) == (0, QUEUE_AT)
    assert case.written(info, RING + addrs.IOREC_HEAD, 2) == 2 * RECORD, (
        "the poll did not read both records, so the hold did not hold")


def test_cancel_empties_the_queue_and_then_queues_itself():
    """^X is the one key that is both a command and a character: the queue is reset and the ^X is
    put back into it, where `Cconrs` will find it and kill the line."""
    info = console.run(DRAIN_CANCELS)
    assert _queued(info) == CTRL_X
    count, read, write = console.queue_state(info["final"], console.DEVICE_CONSOLE)
    assert (count, read, write) == (1, QUEUE_AT, QUEUE_AT + RECORD)


def test_the_last_slot_of_the_queue_is_usable_and_the_next_key_is_refused():
    """The bound is `cmpi.b #80` on the COUNT, so 79 records still leave room and 80 do not. Both
    sides of it, one run each, and the refusing one plants the ROM's own bell list instead."""
    filled = console.run(DRAIN_LAST_SLOT)
    assert _queued(filled, NEARLY_FULL) == ANOTHER_KEY
    assert console.queue_state(filled["final"], console.DEVICE_CONSOLE)[0] == \
        addrs.GEMDOS_TYPEAHEAD_MAX

    belled = console.run(DRAIN_RINGS_THE_BELL)
    assert console.queue_state(belled["final"], console.DEVICE_CONSOLE)[0] == \
        addrs.GEMDOS_TYPEAHEAD_MAX
    assert case.written_long(belled, addrs.SOUND_LIST_POINTER) == addrs.BELL_SOUND_LIST, (
        "a full queue did not ring the bell")
