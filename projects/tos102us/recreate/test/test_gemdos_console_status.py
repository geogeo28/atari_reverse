"""GEMDOS Cconis / Cconos / Cprnos / Cauxis / Cauxos ($0b, $10, $11, $12, $13) — "is it ready?".

Five one-screen leaves and one finding between them: THE INPUT PAIR AND THE OUTPUT TRIO ARE NOT THE
SAME SHAPE. `Cconos`, `Cprnos` and `Cauxos` are `Bcostat` on their own standard handle and nothing
else — three instructions and a trap. `Cconis` and `Cauxis` are `Bconstat` only when GEMDOS's own
TYPEAHEAD QUEUE is empty: a record the output poll took off the BIOS's ring and put in that queue is
input as far as these two are concerned, and a reconstruction that asked the BIOS would answer no
for a key the program can immediately read.

THE HANDLE IS THE WHOLE INTERFACE, and every case below says which one it is driving. `handle + 3` is
the only arithmetic in the group, so a `Cconos` whose stdout is the AUX handle is `Bcostat(AUX:)` —
same leaf, different driver — and the only way to see that the leaf reads its OWN handle and not
some other one is to move them independently. The stdin/stdout pair is moved apart in
`test_each_leaf_reads_its_own_standard_handle`.
"""
import pytest

from harness import BASE_IMAGE, addrs

import bcon
import case
import gemdos
import gemdos_console as console
import iorec

# The three standard handle values, and what each answers on each of the five leaves. Named here
# rather than inline because every case in this file is one row of that table.
CON_READY = 0xFFFFFFFF                      # `moveq #-1` — the console is never busy, and a ring
NOT_READY = 0                               # with a record in it says the same
A_KEY = 0x1E006100                          # one IKBD record: scancode 'A' over ASCII 'a'

# `Bconstat` and `Bcostat` on the PRINTER are not the same question: the printer has an OUTPUT status
# driver (the MFP's BUSY line) and no INPUT one at all, so `Cconis` over the PRN: handle reaches the
# shared `rts` and hands back the dispatch's own scratch.
NO_INPUT_DRIVER = bcon.no_driver_result(addrs.BIOS_BCONSTAT, console.DEVICE_PRINTER)

# The MFP GPIP byte `Bcostat(PRT:)` reads, both ways round, with every other bit inverted between
# them so that a driver testing another bit cannot pass both.
PRINTER_BUSY_BIT = 1 << addrs.MFP_GPIP_PRINTER_BUSY_BIT
GPIP_BUSY = PRINTER_BUSY_BIT
GPIP_IDLE = 0xFF & ~PRINTER_BUSY_BIT


def _ikbd_ready():
    """The console's input ring with one record in it — an interrupt's work, staged."""
    ring = addrs.IOREC_IKBD
    return iorec.staged(ring, 0, addrs.IOREC_KEY_BYTES,
                        [(0, A_KEY.to_bytes(4, "big"))])


# ---- the specs, which are both the runs and the registry rows ------------------------------------

CCONIS_RING_EMPTY = {"name": "gemdos_cconis, ring empty", "leaf": console.CCONIS,
                     "pokes": console.queue(console.DEVICE_CONSOLE)}
CCONIS_RING_READY = {"name": "gemdos_cconis, ring ready", "leaf": console.CCONIS,
                     "pokes": {**console.queue(console.DEVICE_CONSOLE), **_ikbd_ready()}}
CCONIS_QUEUED = {"name": "gemdos_cconis, a record already in the typeahead queue",
                 "leaf": console.CCONIS,
                 "pokes": console.queue(console.DEVICE_CONSOLE, [A_KEY])}
CCONIS_ON_PRINTER = {"name": "gemdos_cconis, stdin redirected to PRN:", "leaf": console.CCONIS,
                     "pokes": {**console.handles(stdin=console.HANDLE_PRN),
                               **console.queue(console.DEVICE_PRINTER)}}
CAUXIS_RING_EMPTY = {"name": "gemdos_cauxis, ring empty", "leaf": console.CAUXIS,
                     "pokes": console.queue(console.DEVICE_RS232)}
CCONOS = {"name": "gemdos_cconos", "leaf": console.CCONOS}
CCONOS_ON_AUX = {"name": "gemdos_cconos, stdout redirected to AUX:", "leaf": console.CCONOS,
                 "pokes": {**console.handles(stdout=console.HANDLE_AUX),
                           **iorec.staged(addrs.IOREC_RS232_OUT, 0, 0)}}
CAUXOS = {"name": "gemdos_cauxos, room in the ring", "leaf": console.CAUXOS,
          "pokes": iorec.staged(addrs.IOREC_RS232_OUT, 0, 0)}
# ...and the same ring with no room: the driver steps the TAIL one record and finds the head there.
CAUXOS_RING_FULL = {"name": "gemdos_cauxos, the ring is full", "leaf": console.CAUXOS,
                    "pokes": iorec.staged(addrs.IOREC_RS232_OUT, addrs.IOREC_RS232_BYTES, 0)}
CPRNOS_IDLE = {"name": "gemdos_cprnos, printer idle", "leaf": console.CPRNOS,
               "io_seed": {addrs.MFP_GPIP: GPIP_IDLE}}
CPRNOS_BUSY = {"name": "gemdos_cprnos, printer busy", "leaf": console.CPRNOS,
               "io_seed": {addrs.MFP_GPIP: GPIP_BUSY}}
CCONOS_ON_PRINTER = {"name": "gemdos_cconos, stdout redirected to PRN:", "leaf": console.CCONOS,
                     "pokes": console.handles(stdout=console.HANDLE_PRN),
                     "io_seed": {addrs.MFP_GPIP: GPIP_IDLE}}

REGISTERED = (CCONIS_RING_EMPTY, CCONIS_RING_READY, CCONIS_QUEUED, CCONIS_ON_PRINTER,
              CAUXIS_RING_EMPTY, CCONOS, CCONOS_ON_AUX, CAUXOS, CAUXOS_RING_FULL, CPRNOS_IDLE,
              CPRNOS_BUSY, CCONOS_ON_PRINTER)
VERIFIED_CASES = tuple(console.registered(spec) for spec in REGISTERED)


# ---- what the machine is, before any of them run -------------------------------------------------

def test_the_captured_machine_holds_the_three_standard_handles_the_rom_writes():
    """`GEMDOS_CONSOLE_INIT` stores -1, -1, -2, -3 into p_uft[0..3], and every case here rests on
    stdin and stdout naming the CONSOLE: a capture whose desktop had redirected one would send the
    default cases down another driver and pass."""
    assert console.snapshot_handle("stdin") == console.HANDLE_CON & 0xFF
    assert console.snapshot_handle("stdout") == console.HANDLE_CON & 0xFF
    assert console.snapshot_handle("stdaux") == console.HANDLE_AUX & 0xFF
    assert console.snapshot_handle("stdprn") == console.HANDLE_PRN & 0xFF


def test_the_three_standard_handles_name_three_different_devices():
    """...which is what makes a redirection case a claim about the leaf rather than about the BIOS:
    move a handle and a different driver runs."""
    devices = {console.device_of(handle)
               for handle in (console.HANDLE_CON, console.HANDLE_AUX, console.HANDLE_PRN)}
    assert devices == {console.DEVICE_CONSOLE, console.DEVICE_RS232, console.DEVICE_PRINTER}


def test_gemdos_initialises_exactly_three_devices_worth_of_console_state():
    """THE PREMISE OF THE ONE HALT in `src/gemdos/console.c`, read out of the captured machine.

    `GEMDOS_CONSOLE_INIT` ($fc9356) is straight-line code: three typeahead counts cleared, three read
    pointers and three write pointers stored, at $83c0, $8500 and $8640. So the fourth entry of each
    table is not a fourth device — it is whatever happens to follow — and a standard handle of 0 or
    more would index it. That is what the reconstruction refuses, and this is the evidence.
    """
    for device in range(addrs.GEMDOS_CONSOLE_DEVICES):
        count, read, write = console.queue_state(BASE_IMAGE, device)
        assert read == write == console.queue_at(device), (
            f"device {device}'s queue does not start at its own buffer")
        assert count == 0
    beyond = addrs.GEMDOS_CONSOLE_DEVICES
    assert console.queue_state(BASE_IMAGE, beyond)[1] != console.queue_at(beyond), (
        "a fourth read pointer holds the address a fourth device would need, which would make the "
        "halt in src/gemdos/console.c a guess rather than a reading of the ROM's own init")


# ---- the five leaves -----------------------------------------------------------------------------

def test_cconis_asks_the_bios_when_the_typeahead_queue_is_empty():
    info = console.run(CCONIS_RING_EMPTY)
    assert info["regs"]["d0"] == NOT_READY
    gemdos.bios_call_site(info)        # ...and it really did trap, at a site the ROM has a `jsr` at


def test_cconis_answers_yes_when_the_ring_has_a_record():
    assert console.run(CCONIS_RING_READY)["regs"]["d0"] == CON_READY


def test_cconis_answers_yes_for_a_record_gemdos_itself_queued_and_asks_no_one():
    """THE WHOLE DIFFERENCE between `Cconis` and `Bconstat`, and the case that shows it is not the
    answer — both arms answer $ffffffff — but the TRAMPOLINE'S RETURN SLOT. The queued arm is
    `tst.b` and `moveq #-1`: no trap is taken, so the longword $fc4eac would have parked is still
    the fill this case staged."""
    info = console.run(CCONIS_QUEUED)
    assert info["regs"]["d0"] == CON_READY
    assert addrs.GEMDOS_BIOS_RETURN_SLOT not in info["writes"], (
        "Cconis reached the BIOS for a record it already had queued")


def test_cconis_over_a_handle_whose_device_has_no_input_driver():
    """PRN: has an output status driver and no input one, so this is the BIOS dispatch's own
    scratch coming back — the caller's high half over the table offset — and not a 0."""
    assert console.run(CCONIS_ON_PRINTER)["regs"]["d0"] == NO_INPUT_DRIVER


def test_cauxis_reads_the_rs232_ring_and_its_own_queue():
    assert console.run(CAUXIS_RING_EMPTY)["regs"]["d0"] == NOT_READY


def test_cauxis_answers_yes_for_a_record_queued_on_the_aux_device():
    """...and it is the AUX device's queue, not the console's: the same record staged on device 2
    leaves this answering no."""
    assert console.run(CAUXIS_RING_EMPTY,
                       pokes=console.queue(console.DEVICE_RS232, [A_KEY]))["regs"]["d0"] == CON_READY
    assert console.run(CAUXIS_RING_EMPTY,
                       pokes={**console.queue(console.DEVICE_RS232),
                              **console.queue(console.DEVICE_CONSOLE, [A_KEY])}
                       )["regs"]["d0"] == NOT_READY


def test_cconos_is_bcostat_on_the_console_which_is_never_busy():
    assert console.run(CCONOS)["regs"]["d0"] == CON_READY


@pytest.mark.parametrize("spec,expected", ((CAUXOS, CON_READY), (CAUXOS_RING_FULL, NOT_READY)))
def test_cauxos_is_bcostat_on_the_rs232_output_ring(spec, expected):
    """No hardware at all: the driver steps the output ring's TAIL and compares it with the head,
    which is "is there room for one more byte?" — driven at both answers, one staged ring each."""
    info = console.run(spec)
    assert info["regs"]["d0"] == expected
    assert case.hardware_reads(info) == []


def test_cconos_follows_its_handle_to_whichever_driver_it_names():
    """The same leaf over all three standard handle values — the console's constant, the RS232's
    ring and the printer's BUSY line — which is the only way "reads p_uft[1]" is a claim about a
    table lookup rather than about one device."""
    assert console.run(CCONOS)["regs"]["d0"] == CON_READY
    assert console.run(CCONOS_ON_AUX)["regs"]["d0"] == CON_READY
    assert case.hardware_reads(console.run(CCONOS_ON_AUX)) == []
    assert case.hardware_reads(console.run(CCONOS_ON_PRINTER)) == [(addrs.MFP_GPIP, GPIP_IDLE)]


@pytest.mark.parametrize("spec,gpip,expected", ((CPRNOS_IDLE, GPIP_IDLE, CON_READY),
                                                (CPRNOS_BUSY, GPIP_BUSY, NOT_READY)))
def test_cprnos_reports_the_centronics_busy_line(spec, gpip, expected):
    """One declared byte, read once, and the answer is the OPPOSITE way round from the branch: the
    ROM keeps its `moveq #-1` when the bit is CLEAR, because the line means busy."""
    info = console.run(spec)
    assert info["regs"]["d0"] == expected
    assert case.hardware_reads(info) == [(addrs.MFP_GPIP, gpip)]


def test_each_leaf_reads_its_own_standard_handle():
    """The stdin/stdout pair moved APART, which is the only arrangement in which "reads p_uft[1]"
    and "reads p_uft[0]" are different claims. With stdout on PRN: and stdin left on CON:,
    `Cconos` must reach the printer's BUSY line and `Cconis` must not read hardware at all."""
    output = console.run(CCONOS_ON_PRINTER)
    assert case.hardware_reads(output) == [(addrs.MFP_GPIP, GPIP_IDLE)]
    assert output["regs"]["d0"] == CON_READY
    assert case.hardware_reads(console.run(CCONIS_RING_EMPTY)) == []
