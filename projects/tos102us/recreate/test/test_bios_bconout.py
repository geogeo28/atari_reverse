"""BIOS Bconout (function 3) @ $fc099c — one character out of one device.

The same four-instruction walk as its three neighbours, over the table at $057e, with a CHARACTER
WORD at 6(sp) above the device word. This file is the four drivers that are not the console; CON:
and RAW: are `test_bios_vt52.py`, because the VT52 driver is a subsystem rather than a leaf.

    0 PRT:   $fc2090  the parallel port through the YM2149, with a BUSY wait and a timeout
    1 AUX:   $fc21b4  the RS232 output ring, and the MFP USART if it is idle
    4 IKBD:  $fc21ee  `Ikbdws`' own single-byte sender, 951-iteration settling delay and all
    3 MIDI:  $fc2016  `Midiws`' own, which has none
    6, 7             the shared `rts`

THREE FINDINGS THIS FILE IS BUILT ON.

*THE PRINTER'S SERIAL TEST READS THE WRONG BYTE.* `btst #4,PRINTER_CONFIG` is a BYTE operation on a
WORD field, so it tests bit 4 of the config's HIGH byte — bit 12 of the word — where every other
reader of the same field takes bit 4 of the word itself (the screen dump at $fc0da2 does `lsr.w #4 /
and.w #1`). A machine configured the documented way for a serial printer still prints through the
parallel port here, and `$1000` is what really redirects it. Both are driven below.

*ITS TWO TIME COMPARES ARE NOT THE SAME COMPARE.* The five-second hold-off after a failure is
`cmpi.l / bcs`, UNSIGNED; the thirty-second BUSY timeout is `cmpi.l / blt`, SIGNED.

*NONE OF THE FOUR ANSWERS WHAT A CALLER WOULD EXPECT.* The two ACIA senders never write D0 at all,
so `Bconout(MIDI:)` hands back the DISPATCH's own scratch — the caller's high half over the table
offset, byte for byte what a device with no driver answers; the printer answers `moveq #-1` or
`moveq #0`; and the RS232's answer is whatever fell out of the flow-control half it ran — a ring
index, a pending character, or the byte it sent.

WHAT EACH CASE DECLARES. Three of the four drivers read the machine, and every byte of it is a
declaration the case writes: the two 6850 status registers, the MFP's GPIP (the Centronics BUSY
line) and the MFP USART's transmitter status. A LIST is what says "busy, then ready" — the shape a
poll is a loop for (TRAP_MODEL.md, Phase 16) — and the printer's BUSY wait and both ACIA sends are
driven through one.
"""
import struct

import pytest

from harness import OS_PSG_EVENT_READ, OS_PSG_EVENT_WRITE, _lib, addrs

import bcon
import case
import iorec
import isr

DEVICE_PRINTER = 0
DEVICE_RS232 = 1
DEVICE_CONSOLE = 2
DEVICE_MIDI = 3
DEVICE_IKBD = 4
DEVICE_RAW = 5
NO_DRIVER_DEVICES = (6, 7)

# The 6850 status bytes a case declares: every bit but TDRE set in the "busy" one and clear in the
# "ready" one, so a reconstruction testing another bit cannot pass both halves of a sweep.
ACIA_BUSY = 0xFF & ~addrs.ACIA_TRANSMIT_READY
ACIA_READY = addrs.ACIA_TRANSMIT_READY
# ...and the MFP's GPIP, whose bit 0 is BUSY: set means the printer cannot take a byte.
PRINTER_BUSY_BIT = 1 << addrs.MFP_GPIP_PRINTER_BUSY_BIT
GPIP_BUSY = PRINTER_BUSY_BIT
GPIP_READY = 0xFF & ~PRINTER_BUSY_BIT
# ...and the USART's transmitter status, whose bit 7 is BUFFER EMPTY.
TSR_EMPTY = 1 << addrs.MFP_TSR_BUFFER_EMPTY_BIT
TSR_SENDING = 0xFF & ~TSR_EMPTY
# EVERY RS232 CASE DECLARES THE TSR AS A LIST, even where it describes a single read, and that is
# the difference between a red and a hung worker. `rs232_prime_transmitter` spins on this byte
# through `io_poll8`, whose give-up is the DECLARATION running out — so a CONSTANT is a byte the
# model can serve for ever, and a core that reached the spin when it should not have (a mutant, a
# transcription slip) would hang the suite instead of failing it. A list of N is also the case's own
# statement that the driver reads the register exactly N times.
ONE_TSR_READ = 1
PRIME_TSR_READS = 3             # the decision, the spin's own look, and the copy saved into RAM

ENTRY_D0 = addrs.BIOS_BCONOUT
A_CHARACTER = 0x41                      # 'A', and the byte every send case expects to see
CHARACTERS = (0x00, 0x01, A_CHARACTER, 0x7F, 0xFF, 0x1234)

run = bcon.output_runner(addrs.BIOS_BCONOUT, _lib.bios_bconout)


# The two ordered chip streams, projected in `test/case.py` because four batteries want them.
hardware_reads = case.hardware_reads
hardware_writes = case.hardware_writes


def test_the_table_in_ram_is_the_one_this_file_describes():
    """Every entry, because every entry is a driver some case here claims. A device that stopped
    being the routine named here would send its case down another arm and pass."""
    entries = bcon.table_entries(addrs.XCONOUT_TABLE)
    assert entries[DEVICE_PRINTER] == addrs.XCONOUT_PRT
    assert entries[DEVICE_RS232] == addrs.XCONOUT_RS232
    assert entries[DEVICE_CONSOLE] == addrs.XCONOUT_CON
    assert entries[DEVICE_MIDI] == addrs.XCONOUT_MIDI
    assert entries[DEVICE_IKBD] == addrs.XCONOUT_IKBD
    assert entries[DEVICE_RAW] == addrs.XCONOUT_RAW
    assert all(entries[device] == addrs.ROM_BARE_RTS for device in NO_DRIVER_DEVICES)


@pytest.mark.parametrize("device", NO_DRIVER_DEVICES)
def test_a_device_with_no_driver_returns_the_dispatch_s_own_scratch(device):
    bcon.assert_no_driver(lambda number, entry_d0: run(number, A_CHARACTER, entry_d0=entry_d0),
                          device)


def test_the_device_index_is_computed_in_a_word():
    """`lsl.w #2`: device $4006 is device 6, which has no driver — the one arm of this entry that
    changes nothing, so the claim is about the walk and not about a driver."""
    assert run(0x4006, A_CHARACTER, entry_d0=bcon.MARKED_D0)["regs"]["d0"] == \
        bcon.no_driver_result(bcon.MARKED_D0, 6)


# ---- the two 6850s: `Ikbdws` and `Midiws`, one byte each -----------------------------------------

ACIA_DEVICES = {DEVICE_MIDI: (addrs.MIDI_ACIA_STATUS, addrs.MIDI_ACIA_DATA),
                DEVICE_IKBD: (addrs.IKBD_ACIA_STATUS, addrs.IKBD_ACIA_DATA)}


@pytest.mark.parametrize("device", sorted(ACIA_DEVICES))
@pytest.mark.parametrize("character", CHARACTERS)
def test_an_acia_sender_puts_the_low_byte_on_its_own_data_port(device, character):
    """One status read, one data write, and the LOW BYTE of the character word — `move.b d1,2(a1)`
    over a `move.w 6(sp),d1`, so $1234 sends $34."""
    status, data = ACIA_DEVICES[device]
    info = run(device, character, io_seed={status: ACIA_READY})
    assert hardware_reads(info) == [(status, ACIA_READY)]
    assert hardware_writes(info) == [(data, character & 0xFF)]


def test_the_two_acia_senders_name_different_ports():
    """...which is what makes the case above a claim about ONE device rather than about a sender the
    two share: they are one register block apart and differ in nothing else but the IKBD's settling
    delay. NO DIFFERENTIAL — the two runs this used to make are the two the parametrized case above
    already makes, and all that was left over was this, which is a fact about the addresses."""
    assert len(set(ACIA_DEVICES.values())) == len(ACIA_DEVICES)


@pytest.mark.parametrize("device", sorted(ACIA_DEVICES))
def test_an_acia_sender_answers_what_a_device_with_no_driver_does(device):
    """NEITHER SENDER WRITES D0 — there is no `moveq` anywhere in either — so what a caller gets
    back is the DISPATCH's own scratch: `move.w 4(sp),d0 / lsl.w #2,d0` replaced the caller's low
    word with the table offset on the way in, and nothing since has touched it. Byte for byte the
    same answer as a device with no driver at all, four entries along.

    A reconstruction answering 0, or the byte, or -1, or the caller's own D0 back whole is
    indistinguishable from this one on every other case in this file."""
    status, _data = ACIA_DEVICES[device]
    info = run(device, A_CHARACTER, entry_d0=bcon.MARKED_D0, io_seed={status: ACIA_READY})
    assert info["regs"]["d0"] == bcon.no_driver_result(bcon.MARKED_D0, device)


@pytest.mark.parametrize("device", sorted(ACIA_DEVICES))
def test_an_acia_sender_waits_for_tdre_and_only_then_writes(device):
    """THE POLL, as a DECLARED SEQUENCE: busy, then ready. A constant could only say one of the two,
    so before Phase 16 what a case proved of this loop was that it happened once; this says it goes
    round, and that the data write comes after the second read rather than the first."""
    status, data = ACIA_DEVICES[device]
    info = run(device, A_CHARACTER, io_seed={status: [ACIA_BUSY, ACIA_READY]})
    assert hardware_reads(info) == [(status, ACIA_BUSY), (status, ACIA_READY)]
    assert hardware_writes(info) == [(data, A_CHARACTER)]


# ---- the printer: the YM2149's port B, a BUSY line and two timeouts ------------------------------

# The PSG registers the send path touches, and what the case declares each holds on entry. Register
# 7 is the mixer, whose bit 7 is port B's direction; 14 and 15 are the two I/O ports.
PSG_MIXER_ON_ENTRY = 0x3F
PSG_PORT_A_ON_ENTRY = 0xF8
PRINTER_PSG_SEED = {addrs.PSG_MIXER_REGISTER: PSG_MIXER_ON_ENTRY,
                    addrs.PSG_PORT_A: PSG_PORT_A_ON_ENTRY, addrs.PSG_PORT_B: 0x00}
STROBE_BIT = addrs.PRINTER_STROBE_SET_MASK
SNAPSHOT_HZ_200 = isr.long_in_snapshot(addrs.SYSVAR_HZ_200)


def printer_pokes(config=0, last_failure=None):
    """The printer's two words of RAM: the configuration Setprt keeps, and the instant of the last
    timeout. The default `last_failure` is far enough back that the hold-off has expired."""
    failed_at = SNAPSHOT_HZ_200 - addrs.PRINTER_RETRY_HOLDOFF_TICKS if last_failure is None \
        else last_failure
    return {addrs.PRINTER_CONFIG: struct.pack(">H", config & 0xFFFF),
            addrs.PRINTER_RETRY_AT: struct.pack(">I", failed_at & 0xFFFFFFFF)}


# THE WAIT SITE IS NOT OPTIONAL ON THIS DRIVER. Its busy loop re-reads `_hz_200` through
# `sched_poll32`, because nothing inside a differential run advances the 200 Hz tick. A poll at an
# UNDECLARED site is TALLIED AND REFUSED — `sched_tick_wide` counts the poll, records the refusal and
# returns 0, so the reconstruction's loop leaves at once and the run reds on the refusal rather than
# hanging a worker. So a case that left the site out fails loudly; declaring it is what lets the
# case be about the timeout instead. Every printer case below goes through `printer_run`, which
# declares it, so none of them can be written without it.
PRINTER_WAIT_SITES = [addrs.PRINTER_WAIT_SITE]


def printer_run(character=A_CHARACTER, *, gpip=GPIP_READY, pokes=None, schedule=None, **kwargs):
    """One `Bconout(PRT:)` over a machine whose BUSY line, chip and wait site are all declared."""
    return run(DEVICE_PRINTER, character, pokes={**printer_pokes(), **(pokes or {})},
               io_seed={addrs.MFP_GPIP: gpip}, psg_seed=PRINTER_PSG_SEED,
               schedule=schedule, wait_sites=PRINTER_WAIT_SITES, **kwargs)


def tick_at(poll, clock):
    """The 200 Hz interrupt, as the scheduled write it is (`sched.h`; TRAP_MODEL.md, Phase 8):
    `clock` into `_hz_200` just before the `poll`th execution of the busy loop's own re-read.

    Without it the driver's thirty seconds are unreachable — the clock the loop measures against is
    advanced by an interrupt, and no interrupt fires under the oracle — so `PRINTER_TIMEOUT_TICKS`
    and the SIGNEDNESS of its compare would be carried by nothing at all.
    """
    return [{"pc": addrs.PRINTER_WAIT_SITE, "nth": poll, "addr": addrs.SYSVAR_HZ_200,
             "width": 4, "value": clock & 0xFFFFFFFF}]


def read_modify_write(register, before, after):
    """What ONE `Giaccess` read-modify-write of a port leaves in the chip's ordered ledger.

    Three entries, not two: `Giaccess` reads the selected register back after writing it, whether or
    not the call asked for a write (`src/xbios/giaccess.c`), so the pair `Ongibit`/`Offgibit` make
    are a read, a write and the write's own read-back.
    """
    return [(OS_PSG_EVENT_READ, register, before),
            (OS_PSG_EVENT_WRITE, register, after),
            (OS_PSG_EVENT_READ, register, after)]


@pytest.mark.parametrize("character", CHARACTERS)
def test_the_printer_puts_the_byte_on_port_b_and_pulses_the_strobe(character):
    """THE WHOLE SEND, in the ROM's own order: read the mixer, write it back with port B turned
    into an output, write the byte to port B, then drive port A's strobe LOW TWICE and back HIGH.

    The two assertions of the strobe are the pulse width and are not a transcription slip — the ROM
    has `bsr .low / bsr .low / bsr .high` — and each of the three is a `Giaccess` read followed by a
    write, because port A is a read-modify-write.
    """
    info = printer_run(character)
    port_b_out = PSG_MIXER_ON_ENTRY | addrs.PSG_PORT_B_OUTPUT
    strobe_low = PSG_PORT_A_ON_ENTRY & (addrs.PRINTER_STROBE_CLEAR_MASK & 0xFF)
    assert info["regs"]["psg_events"] == [
        *read_modify_write(addrs.PSG_MIXER_REGISTER, PSG_MIXER_ON_ENTRY, port_b_out),
        (OS_PSG_EVENT_WRITE, addrs.PSG_PORT_B, character & 0xFF),
        (OS_PSG_EVENT_READ, addrs.PSG_PORT_B, character & 0xFF),
        *read_modify_write(addrs.PSG_PORT_A, PSG_PORT_A_ON_ENTRY, strobe_low),
        *read_modify_write(addrs.PSG_PORT_A, strobe_low, strobe_low),
        *read_modify_write(addrs.PSG_PORT_A, strobe_low, strobe_low | STROBE_BIT),
    ]
    assert info["regs"]["d0"] == addrs.PRINTER_SENT
    # ...and the BUSY line read exactly ONCE when it is already clear, through the same driver
    # `Bcostat(PRT:)` uses — so the read is in the named set's ordered stream and a core that
    # remembered the answer instead of asking reds. Asserted here rather than in a case of its own,
    # which would be this same differential run a second time.
    assert hardware_reads(info) == [(addrs.MFP_GPIP, GPIP_READY)]


def test_the_printer_goes_round_the_busy_wait_until_the_line_clears():
    """A DECLARED SEQUENCE is the only thing that can say "busy, then ready" here, and the loop is
    what the driver's thirty seconds are for. Between the two reads it re-reads `_hz_200` and asks
    whether the timeout has run out — which under the oracle it never does, because nothing in a
    differential run advances the clock."""
    info = printer_run(gpip=[GPIP_BUSY, GPIP_BUSY, GPIP_READY])
    assert hardware_reads(info) == [(addrs.MFP_GPIP, GPIP_BUSY), (addrs.MFP_GPIP, GPIP_BUSY),
                                    (addrs.MFP_GPIP, GPIP_READY)]
    assert info["regs"]["d0"] == addrs.PRINTER_SENT


@pytest.mark.parametrize("since", (0, 1, addrs.PRINTER_RETRY_HOLDOFF_TICKS - 1))
def test_a_port_that_failed_recently_is_not_tried_at_all(since):
    """`move.l _hz_200,d2 / sub.l PRINTER_RETRY_AT,d2 / cmpi.l #1000,d2 / bcs` — and the arm it
    takes reads NO hardware, touches NO chip, and re-stamps the failure so the next call waits
    again from now."""
    # The BUSY line and the chip are declared although this arm reads neither: the POISON pass
    # inverts the failure stamp this arm writes and runs again, and the re-run takes the other arm.
    # A declaration is what the machine held, so saying so costs the claim below nothing.
    info = printer_run(pokes=printer_pokes(last_failure=SNAPSHOT_HZ_200 - since))
    assert (hardware_reads(info), info["regs"]["psg_events"]) == ([], [])
    assert info["regs"]["d0"] == addrs.PRINTER_TIMED_OUT
    assert case.written_long(info, addrs.PRINTER_RETRY_AT) == SNAPSHOT_HZ_200


def test_the_hold_off_compare_is_unsigned():
    """`bcs`, not `blt`: a failure stamp AHEAD of the clock — which a `Settime` moving `_hz_200`
    backwards would leave — makes the difference a huge UNSIGNED number and the port is tried,
    where a signed compare would read it as negative and refuse for ever."""
    info = printer_run(pokes=printer_pokes(last_failure=SNAPSHOT_HZ_200 + 1))
    assert info["regs"]["d0"] == addrs.PRINTER_SENT


# The pass the scheduled tick lands on: the loop has already made two, so the third is the first one
# that can see a clock the interrupt moved.
TIMEOUT_POLL = 3


@pytest.mark.parametrize("elapsed, gpip, gives_up, why", (
    (addrs.PRINTER_TIMEOUT_TICKS, [GPIP_BUSY] * TIMEOUT_POLL, True,
     "thirty seconds EXACTLY: `cmpi.l #6000,d3 / blt` falls through and the driver gives up"),
    (addrs.PRINTER_TIMEOUT_TICKS - 1, [GPIP_BUSY] * TIMEOUT_POLL + [GPIP_READY], False,
     "...one tick short of them, and it goes round again"),
    (0x8000_0000, [GPIP_BUSY] * TIMEOUT_POLL + [GPIP_READY], False,
     "`blt`, not `bcs`: a clock that has run past the sample by half the longword range reads as a "
     "NEGATIVE elapsed time and the driver keeps waiting, where an unsigned compare would give up"),
))
def test_the_printer_gives_up_thirty_seconds_after_it_started_waiting(elapsed, gpip, gives_up, why):
    """THE ARM NOTHING ELSE REACHES. `_hz_200` is advanced by the 200 Hz interrupt, so under the
    oracle it never moves and this loop can only ever end on the BUSY line — which leaves both the
    six-thousand-tick constant and the signedness of the compare carried by nothing. A scheduled
    write is what an interrupt is here (`tick_at`), and it is also what pins the count of passes:
    the store lands before the same pass on both shores and the harness compares the oracle's
    ARRIVALS at the re-read against the core's POLLS."""
    clock = SNAPSHOT_HZ_200 + elapsed
    info = printer_run(gpip=gpip, schedule=tick_at(TIMEOUT_POLL, clock))
    if gives_up:
        assert info["regs"]["d0"] == addrs.PRINTER_TIMED_OUT, why
        assert case.written_long(info, addrs.PRINTER_RETRY_AT) == clock & 0xFFFFFFFF, (
            "the failure is stamped with the clock as it stands AFTER the wait, not before it")
        assert info["regs"]["psg_events"] == [], "the byte never reached the port"
    else:
        assert info["regs"]["d0"] == addrs.PRINTER_SENT, why


@pytest.mark.parametrize("config, redirected, why", (
    (0x0000, False, "the snapshot's own configuration: the parallel port"),
    (0x0010, False, "bit 4 of the WORD — what Setprt's callers set for a serial printer, and this "
                    "driver does not look at it"),
    (0x1000, True, "bit 4 of the HIGH BYTE, which is the bit the `btst` really tests"),
    (0xEFFF, False, "...every other bit of the word set, and it still prints"),
))
def test_the_serial_redirect_tests_bit_four_of_the_configuration_s_high_byte(config, redirected,
                                                                             why):
    """THE FINDING. `btst #4,PRINTER_CONFIG` is byte-wide on a word field, so the bit it reaches is
    the word's bit 12. Redirected means the RS232 driver ran — which is visible as the USART's
    transmitter status being read and the YM2149 never being touched at all."""
    pokes = {**printer_pokes(config=config),
             **iorec.staged(addrs.IOREC_RS232_OUT, head=RS232_POISON_SAFE_HEAD,
                            tail=RS232_POISON_SAFE_HEAD)}
    info = run(DEVICE_PRINTER, A_CHARACTER, pokes=pokes,
               io_seed={addrs.MFP_GPIP: GPIP_READY,
                        addrs.MFP_TSR: [TSR_SENDING] * ONE_TSR_READ},
               psg_seed=PRINTER_PSG_SEED, wait_sites=PRINTER_WAIT_SITES)
    reads = hardware_reads(info)
    assert ((addrs.MFP_TSR, TSR_SENDING) in reads) is redirected, why
    assert (info["regs"]["psg_events"] == []) is redirected, why


# ---- the RS232: an output ring, and the USART when it is idle ------------------------------------

RS232_SIZE = iorec.size_of(addrs.IOREC_RS232_OUT)
RS232_BUFFER = iorec.buffer_of(addrs.IOREC_RS232_OUT)


# THE POISON PASS PICKS THE RING'S INDICES, which is worth saying out loud because nothing else in
# this file constrains them. `case.run` re-runs both cores with every byte the oracle WROTE inverted,
# and one of those bytes is the tail this driver advances: an inverted tail is $ff00..$ffff, which
# wraps to 0 on every ring smaller than that — so a case staged with the HEAD at 0 comes back, in the
# poisoned run, as a ring the ROM's own put says is full, and both shores then spin on it for ever.
# Two slots in is clear of that whichever way the inversion lands.
RS232_POISON_SAFE_HEAD = 2


def rs232_pokes(head=RS232_POISON_SAFE_HEAD, tail=RS232_POISON_SAFE_HEAD, *,
                flow=0, stopped=0, pending=0):
    """The output ring plus the three flow-control bytes above the two IOREC records."""
    return {**iorec.staged(addrs.IOREC_RS232_OUT, head=head, tail=tail),
            addrs.RSCONF_FLOW_CONTROL: bytes([flow]),
            addrs.RS232_REMOTE_STOPPED: bytes([stopped]),
            addrs.RS232_PENDING_CHARACTER: bytes([pending])}


def test_the_three_flow_control_bytes_sit_where_the_rom_addresses_them():
    """`30(a0)`..`33(a0)` off the INPUT record, which is how the ROM reaches all four. Spelling them
    as absolute addresses in `addrs.h` is what `tools/addrs.py` needs; this is what keeps the two
    spellings from drifting."""
    assert addrs.RS232_TRANSMIT_STATUS == addrs.IOREC_RS232 + 29
    assert addrs.RS232_REMOTE_STOPPED == addrs.IOREC_RS232 + 31
    assert addrs.RSCONF_FLOW_CONTROL == addrs.IOREC_RS232 + 32
    assert addrs.RS232_PENDING_CHARACTER == addrs.IOREC_RS232 + 33
    assert addrs.IOREC_RS232_OUT == addrs.IOREC_RS232 + 14


# ...and where a byte queued on an empty ring at that head lands: one slot on from the tail.
RS232_FIRST_SLOT = RS232_POISON_SAFE_HEAD + 1


@pytest.mark.parametrize("character", CHARACTERS)
def test_the_rs232_puts_the_byte_in_the_ring_and_leaves_a_busy_transmitter_alone(character):
    """The byte goes into the ring WHATEVER the USART is doing; the prime below is only for an idle
    one, because a transmitter mid-character fetches the next byte through its own interrupt.

    The tail is advanced FIRST and the byte stored at the advanced slot, which is the mirror of the
    reader in `test_bios_bconin.py` — a reconstruction storing at the old tail passes nothing here.
    """
    info = run(DEVICE_RS232, character, pokes=rs232_pokes(),
               io_seed={addrs.MFP_TSR: [TSR_SENDING] * ONE_TSR_READ})
    assert case.written(info, RS232_BUFFER + RS232_FIRST_SLOT, 1) == (character & 0xFF)
    assert case.written(info, addrs.IOREC_RS232_OUT + addrs.IOREC_TAIL, 2) == RS232_FIRST_SLOT
    assert hardware_reads(info) == [(addrs.MFP_TSR, TSR_SENDING)]
    assert hardware_writes(info) == []
    assert info["regs"]["d0"] == bcon.no_driver_result(addrs.BIOS_BCONOUT, DEVICE_RS232) \
        & 0xFFFF_0000 | character, "`move.w 6(sp),d0` over the dispatch's own low word"


@pytest.mark.parametrize("head, tail, stored_at, why", (
    (2, 2, 3, "an empty ring: the tail advances one slot and the byte lands there"),
    (2, 5, 6, "...and a ring with bytes already in it is no different"),
    (2, RS232_SIZE - 1, 0, "the tail at the last slot WRAPS to 0, not to size"),
    (1, RS232_SIZE - 2, RS232_SIZE - 1, "...and the slot before it does not wrap"),
))
def test_the_output_ring_wraps_at_its_size_rather_than_modulo_it(head, tail, stored_at, why):
    """`addq.w #1,d1 / cmp.w 4(a0),d1 / bcs` — UNSIGNED, and the arm it skips is `moveq #0,d1`."""
    info = run(DEVICE_RS232, A_CHARACTER, pokes=rs232_pokes(head=head, tail=tail),
               io_seed={addrs.MFP_TSR: [TSR_SENDING] * ONE_TSR_READ})
    assert case.written(info, RS232_BUFFER + stored_at, 1) == A_CHARACTER, why
    assert case.written(info, addrs.IOREC_RS232_OUT + addrs.IOREC_TAIL, 2) == stored_at, why


def test_an_idle_transmitter_is_handed_the_byte_the_ring_just_took():
    """THE WHOLE PRIME, and it is a round trip: the byte goes in at the tail, comes straight back
    out at the head, and is stored in the USART's data register. The transmitter status is read
    TWICE on the way — once as the poll's own look and once to be SAVED in RAM — which is why the
    declaration here is a list of two."""
    info = run(DEVICE_RS232, A_CHARACTER, pokes=rs232_pokes(),
               io_seed={addrs.MFP_TSR: [TSR_EMPTY] * PRIME_TSR_READS})
    assert hardware_writes(info) == [(addrs.MFP_UDR, A_CHARACTER)]
    assert case.written(info, addrs.RS232_TRANSMIT_STATUS, 1) == TSR_EMPTY
    assert case.written(info, addrs.IOREC_RS232_OUT + addrs.IOREC_HEAD, 2) == RS232_FIRST_SLOT
    assert info["regs"]["d0"] == A_CHARACTER, "`moveq #0,d0 / move.b` — the WHOLE register"


def test_the_transmitter_poll_goes_round_until_the_buffer_is_empty():
    """`tst.b TSR / bpl` is a LOOP, and the first read outside it is not: the driver's own test at
    $fc21c8 decides whether to prime at all, and only then does $fc2864 spin. So a declaration of
    three bytes describes three reads — the decision, the spin's second look, and the save."""
    info = run(DEVICE_RS232, A_CHARACTER, pokes=rs232_pokes(),
               io_seed={addrs.MFP_TSR: [TSR_EMPTY, TSR_SENDING, TSR_EMPTY, TSR_EMPTY]})
    assert hardware_reads(info) == [(addrs.MFP_TSR, TSR_EMPTY), (addrs.MFP_TSR, TSR_SENDING),
                                    (addrs.MFP_TSR, TSR_EMPTY), (addrs.MFP_TSR, TSR_EMPTY)]
    assert hardware_writes(info) == [(addrs.MFP_UDR, A_CHARACTER)]


@pytest.mark.parametrize("flow, stopped", ((1, 1), (2, 2), (0xFF, 0x01), (0x0F, 0xF0)))
def test_a_far_end_that_has_stopped_us_gets_nothing(flow, stopped):
    """`move.b FLOW,d0 / and.b STOPPED,d0 / bne` — the two bytes ANDed, so either being zero lets the
    byte through and a bit they SHARE holds it back. The ring is still filled; it is only the USART
    that is left alone."""
    held = (flow & stopped) != 0
    info = run(DEVICE_RS232, A_CHARACTER,
               pokes=rs232_pokes(flow=flow, stopped=stopped),
               io_seed={addrs.MFP_TSR: [TSR_EMPTY] * PRIME_TSR_READS})
    assert (hardware_writes(info) == []) is held
    assert case.written(info, RS232_BUFFER + RS232_FIRST_SLOT, 1) == A_CHARACTER


def test_the_flow_control_byte_that_holds_us_back_is_what_d0_comes_back_as():
    """`move.b` writes D0's low BYTE alone, over a low word that still holds the character's high
    byte and a high half that is the caller's. Three layers, and a reconstruction that answered the
    AND on its own, or 0, agrees with this one on nothing."""
    flow, stopped = 0x03, 0x02
    info = run(DEVICE_RS232, 0x1234, entry_d0=bcon.MARKED_D0,
               pokes=rs232_pokes(flow=flow, stopped=stopped),
               io_seed={addrs.MFP_TSR: [TSR_EMPTY] * ONE_TSR_READ})
    assert info["regs"]["d0"] == (bcon.MARKED_D0 & 0xFFFF_0000) | 0x1200 | (flow & stopped)


@pytest.mark.parametrize("pending", (0x11, 0x13, 0xFF))
def test_a_pending_flow_character_jumps_the_queue_and_is_cleared(pending):
    """XON and XOFF are sent AHEAD of the ring rather than through it — `move.b PENDING,d0 / beq
    .ring / clr.b PENDING` — so the character this call queued stays queued and the flow byte goes
    out instead."""
    info = run(DEVICE_RS232, A_CHARACTER,
               pokes=rs232_pokes(pending=pending),
               io_seed={addrs.MFP_TSR: [TSR_EMPTY] * PRIME_TSR_READS})
    assert hardware_writes(info) == [(addrs.MFP_UDR, pending)]
    assert case.written(info, addrs.RS232_PENDING_CHARACTER, 1) == 0
    assert case.written(info, RS232_BUFFER + RS232_FIRST_SLOT, 1) == A_CHARACTER
    assert addrs.IOREC_RS232_OUT + addrs.IOREC_HEAD not in info["writes"], \
        "the ring's head must not move: the pending character never came out of it"
