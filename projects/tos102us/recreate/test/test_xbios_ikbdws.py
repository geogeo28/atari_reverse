"""XBIOS Ikbdws ($19) @ $fc2212 and Midiws ($0c) @ $fc2030 — bytes out of the two 6850 ACIAs.

One shape twice. Each takes a COUNT and a pointer, sends `count + 1` bytes, and sends each one by
spinning on its ACIA's status register until the transmit register is empty and then storing to the
data port next door. The IKBD's sender has one thing the MIDI's has not: 951 iterations of nothing
between the poll and the store, which is the settling time the 6301 keyboard controller needs.

NOTHING EITHER ROUTINE DOES IS IN MEMORY, so the image diff proves nothing here at all and the two
OFF-IMAGE ledgers are the whole of the case: the ordered hardware WRITE stream says which bytes went
to which port in which order (TRAP_MODEL.md, Phase 10), and the ordered READ streams say the status
register really was polled, once per byte, at the right ACIA. A reconstruction that sent the bytes
backwards, sent one twice, or aimed the IKBD's at the MIDI port leaves memory identical.

THE TWO STATUS REGISTERS COME THROUGH DIFFERENT DOORS, and a case has to know which: `$fffc00` is one
of the seeded model's NAMED slots (os.h, `OS_HW_ACIA_STATUS`) and `$fffc04` is an ordinary byte of
the declared I/O map. `emu.seed_split` routes a named slot written into `io_seed` to its own model,
so a case can declare both in one dict and read the two streams back separately — which is what the
cases below assert, because a reconstruction that called the wrong door would be REFUSED rather than
compared, and the refusal is a worse message than a stream mismatch.

WHAT A PER-RUN CONSTANT CANNOT SAY. The status byte is declared once and answers every read of it, so
`TDRE set` means the send loop leaves on its first poll — every time, for every byte. The sequence
that actually happens on a machine (not ready, then ready) needs two different bytes out of one
address in one run, which os.h names as beyond this model; declared the other way, with the bit
clear, both sides would spin identically until the instruction cap. So what these cases prove of the
poll is that it HAPPENS, in order, once per byte, at the right port — not how long it would wait.
"""
import ctypes
import struct

import pytest

from harness import (_lib, addrs, arm_candidate, candidate_image, differential, emu,
                     in_diff, make_image)

import abi
import case
import staging

_lib.xbios_ikbdws.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint32]
_lib.xbios_ikbdws.restype = None
_lib.xbios_midiws.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint32]
_lib.xbios_midiws.restype = None

# Where a case stages the bytes to send. The routines read the caller's own memory, so this is an
# ordinary staged buffer in the band `project.toml` reserves.
BYTES_AT = staging.SCRATCH

# What a case declares each ACIA held: the transmit register empty, which is the only declaration
# under which either send loop terminates (see the module docstring).
#
# THE TWO DICTS ARE DIFFERENT SIZES AND THAT IS THE POINT. The MIDI status byte is nobody's model's,
# so a case has to say what it held. The IKBD's is a Phase-7 NAMED slot, and the seeded model
# DECLARES IT ITSELF — `os_hw_default_slots` installs `OS_ACIA_TX_RDY` for it when a case says
# nothing — so the byte is a declared input either way and there is nothing here to add. The case
# below pins that default rather than leaving the claim implicit; a run declaring it explicitly is
# also refused by the BENCH door, whose `io_seed` carries no named slot (`emu.run_bench`).
IKBD_READY = {}
MIDI_READY = {addrs.MIDI_ACIA_STATUS: addrs.ACIA_TRANSMIT_READY}


def ready(entry):
    """...and which of the two a case for `entry` needs."""
    return dict(IKBD_READY) if entry == addrs.XBIOS_IKBDWS else dict(MIDI_READY)

# Byte strings whose ORDER and REPEATS are both visible: a single byte, a pair that is not a
# palindrome, a run with a repeat in the middle, and the two extreme byte values at the ends.
PAYLOADS = (b"\x80", b"\x01\x02", b"\x12\x34\x34\x56", b"\x00\xff\x00", b"\x1b\x89\x01\x20\x10\x51")


def frame(count, at):
    """The frame the dispatcher's caller leaves: the count WORD, then the pointer longword."""
    return {abi.FIRST_ARG: struct.pack(">HI", count & 0xFFFF, at)}


def run(entry, payload, at=BYTES_AT, count=None, io_seed=None, poison=False):
    """One send of `payload`, with the ROM's own count convention: ONE LESS than the byte count.

    POISON IS OFF, AND IT IS OFF BECAUSE THERE IS NOTHING FOR IT TO ATTRIBUTE. The attribution pass
    inverts every byte the ORACLE wrote to the image and re-runs both cores, which catches a
    candidate that skipped a store whose value the image already held. Neither of these routines
    writes the image at all — the first case below asserts that rather than leaving it to the module
    docstring — so the pass has no canary to plant and buys a second pair of runs for nothing. On
    `Ikbdws` that is not free either: its settling delay costs the oracle ~2,900 instructions a byte,
    and doubling every case in this file would be the most expensive thing in the suite.

    What takes poison's place here is the two OFF-IMAGE ledgers, which are compared on every case
    whether or not anybody opts in (`harness._vet_hw_write_state`): a candidate that sent nothing has
    an empty write stream where the oracle's has one entry per byte.
    """
    count = len(payload) - 1 if count is None else count
    send = _lib.xbios_ikbdws if entry == addrs.XBIOS_IKBDWS else _lib.xbios_midiws

    def glue(lib, buf):
        del lib
        send(buf, count & 0xFFFF, at)

    declared = ready(entry) if io_seed is None else io_seed
    return case.run(entry, {"a5": 0, "_pokes": {**frame(count, at), at: payload}}, glue,
                    width=case.NO_RESULT, poison=poison, io_seed=declared)


def sent(info):
    """The bytes the run really put on a data port, out of the ordered hardware write ledger."""
    return [(address, value) for address, _width, value in info["regs"]["hw_writes"]]


ROUTINES = ((addrs.XBIOS_IKBDWS, addrs.IKBD_ACIA_DATA), (addrs.XBIOS_MIDIWS, addrs.MIDI_ACIA_DATA))
ROUTINE_IDS = ("ikbdws", "midiws")


@pytest.mark.parametrize("entry,port", ROUTINES, ids=ROUTINE_IDS)
@pytest.mark.parametrize("payload", PAYLOADS)
def test_the_bytes_reach_the_data_port_in_order(entry, port, payload):
    """The whole of what either routine leaves behind, on both ACIAs and five byte strings.

    The payloads are chosen so that ORDER and REPEATS are separable: a reconstruction that sent the
    string backwards passes only the palindrome, and one that sent the first byte `n` times passes
    only the single.
    """
    info = run(entry, payload)
    assert sent(info) == [(port, byte) for byte in payload]
    # The premise `run` leaves the attribution pass off on: neither routine writes a byte the
    # differential compares. (The oracle's ledger still holds its own machine stack, which
    # `diff_spans` drops on both sides — `in_diff` is the same question the diff asks.)
    assert [at for at in info["writes"] if in_diff(at)] == [], (
        "the routine wrote the compared image, so `run`'s reason for leaving the attribution pass "
        "off has stopped being true")


@pytest.mark.parametrize("entry,port", ROUTINES, ids=ROUTINE_IDS)
def test_the_count_is_one_less_than_the_bytes_sent(entry, port):
    """`dbf`'s `+ 1`, which is the routine's calling convention and the thing a port gets wrong.

    The body runs before the test, so a count of 0 sends ONE byte. A reconstruction with a `for
    (i = 0; i < count; i++)` loop sends none for count 0 and is one short everywhere else.
    """
    payload = b"\x41\x42\x43"
    for count in range(len(payload)):
        info = run(entry, payload, count=count)
        assert sent(info) == [(port, byte) for byte in payload[:count + 1]], (
            f"a count of {count} sent {len(sent(info))} byte(s) rather than {count + 1}")


@pytest.mark.parametrize("entry,port", ROUTINES, ids=ROUTINE_IDS)
def test_the_bytes_come_from_wherever_the_caller_points(entry, port):
    """The pointer is the caller's and the routine does not look at it twice: two buffers a page
    apart in the staging band send their own bytes, so a reconstruction that read a fixed address —
    the IKBD command buffer `Initmous` uses, say — diverges."""
    first, second = b"\x11\x22", b"\x33\x44"
    elsewhere = BYTES_AT + 0x100
    assert elsewhere + len(second) <= staging.SCRATCH + staging.SCRATCH_BYTES
    assert sent(run(entry, first)) == [(port, byte) for byte in first]
    assert sent(run(entry, second, at=elsewhere)) == [(port, byte) for byte in second]


@pytest.mark.parametrize("entry,port", ROUTINES, ids=ROUTINE_IDS)
def test_one_status_poll_per_byte_at_its_own_acia(entry, port):
    """The read stream, which is the only witness that the loop looked at the chip at all.

    The two ACIAs answer through DIFFERENT models — `$fffc00` through the seeded named set and
    `$fffc04` through the declared I/O map — so each routine's polls land in its own stream and the
    other's is empty. That is the claim: a reconstruction polling the wrong ACIA would be refused
    rather than compared, and one polling none would leave both streams empty.
    """
    payload = b"\x01\x02\x03"
    info = run(entry, payload)
    ikbd_polls = info["regs"]["hw_events"]
    midi_polls = [(address, value) for address, _width, value in info["regs"]["io_events"]]
    expected = [(addrs.IKBD_ACIA_STATUS, addrs.ACIA_TRANSMIT_READY)] * len(payload)
    if port == addrs.IKBD_ACIA_DATA:
        assert ikbd_polls == expected and midi_polls == []
    else:
        assert ikbd_polls == [] and \
            midi_polls == [(addrs.MIDI_ACIA_STATUS, addrs.ACIA_TRANSMIT_READY)] * len(payload)


# The instruction cap a spinning case is run under: high enough that a byte would have been sent
# several times over, low enough that the suite does not pay 200,000 instructions to learn nothing.
SPIN_CAP = 5000


@pytest.mark.parametrize("declared,what", ((None, "undeclared"), ({addrs.MIDI_ACIA_STATUS: 0},
                                                                 "declared with TDRE clear")))
def test_a_status_register_that_is_never_ready_spins_the_oracle_to_its_cap(declared, what):
    """WHAT THE CONSTANT CANNOT SAY, measured — and why the usual refusal has nothing to fire on.

    Everywhere else in this project an undeclared I/O byte REFUSES the case by address. Not here:
    the fabricated 0 that stands in for the undeclared byte has TDRE clear, so the ROM's own send
    loop never leaves and the run ends at the instruction cap instead — the refusal is a check made
    after the oracle returns, and this oracle does not. Declaring the byte with the bit clear is the
    same program, which is the point: a per-run constant can describe a transmitter that is ready or
    one that never becomes ready, and the machine's own "not yet, now" is neither.

    THE ORACLE ALONE, and the name says so: the reconstruction reaches the same loop through
    `io_poll8`, which ends it the moment the model cannot serve another read — so on the UNDECLARED
    row it leaves at once where the oracle here does not, and the case below pins that. On the
    DECLARED row both really do spin, because a constant serves every poll for ever. Either way
    there is no bounded number of polls for the two to be compared over: what a case can prove is
    the poll that DOES happen, which every case above does.
    """
    del what
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image({**frame(0, BYTES_AT), BYTES_AT: b"\x55"}), addrs.XBIOS_MIDIWS,
                {"a5": 0}, io_seed=declared, max_insns=SPIN_CAP)


# A status byte with TDRE CLEAR: the transmitter is busy and the send loop goes round again.
ACIA_NOT_READY = 0


def test_a_refused_status_poll_ends_the_recreate_s_spin_and_sends_anyway():
    """WHERE THE RECONSTRUCTION AND THE ORIGINAL PART COMPANY, and the only case that says so.

    The ROM's wait is unbounded: `btst #1,d2 / beq .poll`, and the case above measures the oracle
    running it to the instruction cap. The reconstruction's is `io_poll8`/`hw_poll8` — the read plus
    "could you still serve it?" — so a declaration that RUNS OUT ends the loop on this shore
    (`src/xbios/acia.c`). That asymmetry is deliberate: a hung pytest worker decides nothing where a
    refused run reds. What it costs is that the byte is then sent to a transmitter nobody said was
    ready, which is what this pins.

    NO DIFFERENTIAL, because there is nothing to compare against: the oracle does not return from
    this case at all. So the candidate is run on its own and its two ledgers are read directly — the
    refusal tally that makes the run void, and the hardware write that happened anyway.

    `Ikbdws` reaches the same primitive one door along (`hw_poll8`), and its status register cannot
    be under-declared: it is a Phase-7 NAMED slot the kit defaults to `OS_ACIA_TX_RDY`, which is
    what `test_the_ready_bit_is_the_one_the_kit_defaults_that_slot_to` above pins.
    """
    buf = candidate_image(make_image({**frame(0, BYTES_AT), BYTES_AT: b"\x55"}))
    arm_candidate(io_seed={addrs.MIDI_ACIA_STATUS: [ACIA_NOT_READY]})
    _lib.xbios_midiws(buf, 0, BYTES_AT)

    assert _lib.g_os_refusal_count() == 1, (
        "the list of one should have been spent by the first poll and the second poll refused")
    written = [(_lib.g_hw_write_addrs()[i], _lib.g_hw_write_vals()[i])
               for i in range(_lib.g_hw_write_count())]
    assert written == [(addrs.MIDI_ACIA_DATA, 0x55)], (
        "the send should leave the spin on the refusal and store the byte, which is what makes the "
        "run VOID rather than hung")


def test_the_ikbd_s_two_ports_are_the_ones_the_seeded_model_names():
    """`addrs.h` spells `$fffc00`/`$fffc02` itself, because `tools/addrs.py` reads integers only —
    so this is what stops that second spelling from drifting away from os.h's, read out of the
    oracle's own slot table. The MIDI pair is deliberately absent from it: nothing names those, which
    is why they go through the declared I/O map instead."""
    assert addrs.IKBD_ACIA_STATUS in emu.HW_ADDRS and addrs.IKBD_ACIA_DATA in emu.HW_ADDRS
    assert addrs.MIDI_ACIA_STATUS not in emu.HW_ADDRS


def test_the_ready_bit_is_the_one_the_kit_defaults_that_slot_to():
    """...and the BIT, pinned the same way. The seeded model installs `OS_ACIA_TX_RDY` for the IKBD
    status slot when a case declares nothing, so a run with no declaration is served exactly the
    byte `ACIA_TRANSMIT_READY` names — which is why `Ikbdws` terminates undeclared where `Midiws`
    does not."""
    _final, _writes, regs = emu.run(make_image({**frame(0, BYTES_AT), BYTES_AT: b"\x55"}),
                                    addrs.XBIOS_IKBDWS, {"a5": 0})
    assert regs["hw_events"] == [(addrs.IKBD_ACIA_STATUS, addrs.ACIA_TRANSMIT_READY)]


def test_the_ikbd_sender_waits_and_the_midi_sender_does_not():
    """THE ONE DIFFERENCE BETWEEN THE TWO, and the only surface it has is the cycle count.

    951 iterations of `bsr` to an `rts` sit between the IKBD's poll and its store, and nothing else
    in the differential can see them: they touch no memory, no register the case compares and no
    chip. What says they are there is that one IKBD byte costs about two thousand nine hundred
    instructions where a MIDI byte costs eleven — measured here, and priced by Tier 3 for the
    reconstruction's own loop.
    """
    costs = {}
    for label, entry in (("ikbd", addrs.XBIOS_IKBDWS), ("midi", addrs.XBIOS_MIDIWS)):
        _final, _writes, regs = emu.run(make_image({**frame(0, BYTES_AT), BYTES_AT: b"\x55"}),
                                        entry, {"a5": 0}, io_seed=ready(entry))
        costs[label] = (regs["ninsns"], regs["cycles"])
    assert costs["ikbd"][0] > costs["midi"][0] * 100, (
        f"the IKBD's settling delay has gone: {costs}")
    assert costs == ONE_BYTE_COST, (
        f"the ACIA senders now cost {costs} — STATUS.md's Tier 3 denominators are stale")


# One byte through each routine, as the oracle counts it (instructions, cycles) — the Tier 3
# denominators, and the measurement the case above rests on.
ONE_BYTE_COST = {"ikbd": (2868, 42054), "midi": (14, 198)}
