"""The two ACIA SERVICE ROUTINES @ $fc29fc / $fc2a0c, and everything one byte out of a 6850 reaches.

`test_bios_ikbd.py` proves the HANDLER that calls these two through KBDVECS; this proves the two
themselves, entered at their own addresses as the ordinary `rts` routines they are. Between them
they are the whole of TOS's input side: the 6850's status arms, MIDI's ring, and the 6301's packet
state machine with its five buffers and four dispatch vectors.

WHAT MADE THEM RUNNABLE is the declared SEQUENCE (`TRAP_MODEL.md`, Phase 16). Every read of a data
port POPS the receive register, so a per-run constant describes exactly one read and a routine that
reads twice — which the overrun arm does — was refused outright before a LIST could say what the two
reads yielded. `test/acia.py` is where a case says it.

A PACKET IS SEVERAL ENTRIES, NOT ONE. The 6301 raises the line once per byte, so a case here drives
ONE byte and says what state the previous one left; `test_bios_ikbd.py` drives whole packets end to
end through the handler's own loop, which is the other half of the same claim and the one that needs
nothing poked between bytes.
"""
import struct

import pytest

import acia
import case
import iorec
import isr
from harness import BASE_IMAGE, addrs, _lib

MIDI_STATUS, MIDI_DATA = acia.MIDI_PORTS
IKBD_STATUS, IKBD_DATA = acia.IKBD_PORTS

# Two bytes that are not scancodes, not packet headers and not each other, so a routine that served
# the wrong read — or the wrong chip — diverges on the value rather than by luck.
A_BYTE, ANOTHER_BYTE = 0x5A, 0xA5


def _service(routine):
    def glue(lib, buf):
        getattr(lib, routine)(buf)
    return glue


MIDI_GLUE = _service("midi_acia_service")
IKBD_GLUE = _service("ikbd_acia_service")


# The differential runner is `test/acia.py`'s: three batteries enter these routines over the same
# staged image, so it is spelt there once and named here for the call sites below.
run = acia.run


def packet_state(kind, remaining, buffer=None):
    """Pokes that say a packet of `kind` is in progress with `remaining` bytes still to come.

    The 6301 sends a packet one interrupt at a time, so the state the previous byte left IS the
    input of this one. `buffer` is (address, bytes) for a case that also stages what has arrived so
    far — the mouse packet's header, say — which is how the completed packet a vector is handed can
    be asserted whole.
    """
    pokes = {addrs.IKBD_PACKET_KIND: struct.pack(">BB", kind, remaining)}
    if buffer is not None:
        pokes[buffer[0]] = buffer[1]
    return pokes


# ---- the shared body: what the status register decides -------------------------------------------

@pytest.mark.parametrize("ports,entry,glue", ((acia.MIDI_PORTS, addrs.MIDI_ACIA_SERVICE, MIDI_GLUE),
                                              (acia.IKBD_PORTS, addrs.IKBD_ACIA_SERVICE, IKBD_GLUE)),
                         ids=("midi", "ikbd"))
@pytest.mark.parametrize("status", (acia.IDLE, 0x7F, acia.QUIET, acia.QUIET | 0x1E),
                         ids=("idle", "every other bit set", "interrupting", "interrupting, dirty"))
def test_the_data_port_is_read_only_when_the_status_says_so(ports, entry, glue, status):
    """`btst #7` then `btst #0`, and NOTHING declares the data port: a routine that read it anyway
    would be refused by address on both shores rather than served a byte.

    The four bytes cover both tests independently — bit 7 clear with every other bit set, and bit 7
    set with bits 1..4 set but 0 and 5 clear — so a reconstruction testing the whole byte, or the
    wrong bit, does not end where this one does.
    """
    info = run(entry, glue, io_seed=acia.declare(ports, status))
    assert not any(acia.called(info, name) for name, _offset, _kind in acia.SLOTS)


@pytest.mark.parametrize("ports,entry,glue,error_vector",
                         ((acia.MIDI_PORTS, addrs.MIDI_ACIA_SERVICE, MIDI_GLUE, "vmiderr"),
                          (acia.IKBD_PORTS, addrs.IKBD_ACIA_SERVICE, IKBD_GLUE, "vkbderr")),
                         ids=("midi", "ikbd"))
def test_an_overrun_alone_reads_the_byte_that_was_lost_and_calls_the_error_vector(
        ports, entry, glue, error_vector):
    """`andi.b #$20,d2 / move.b 2(a1),d0 / jmp (a2)` — the arm that runs when a byte was LOST and no
    byte is waiting. Each chip has its OWN error vector, which is the only thing that separates the
    two entries here besides their port and their IOREC."""
    info = run(entry, glue, io_seed=acia.declare(ports, acia.OVERRAN, [A_BYTE]))
    assert acia.reported_byte(info, error_vector) == A_BYTE
    assert not acia.called(info, "vmiderr" if error_vector == "vkbderr" else "vkbderr")


def test_a_byte_and_an_overrun_read_the_port_twice_in_the_rom_s_order():
    """THE CASE THE SEQUENCE MODEL EXISTS FOR. Both arms run on one entry, so the data port is
    popped TWICE — once for the byte that arrived and once for the one that was lost — and only a
    LIST can say the two reads yielded different bytes. A reconstruction that read once and reused
    the value leaves the second list entry unspent and the first byte in the wrong place."""
    info = run(addrs.MIDI_ACIA_SERVICE, MIDI_GLUE,
               io_seed=acia.declare(acia.MIDI_PORTS, acia.READY_AND_OVERRAN,
                                    [A_BYTE, ANOTHER_BYTE]))
    assert acia.reported_byte(info, "midivec") == A_BYTE
    assert acia.reported_byte(info, "vmiderr") == ANOTHER_BYTE
    assert info["regs"]["io_events"] == [(MIDI_STATUS, 1, acia.READY_AND_OVERRAN),
                                         (MIDI_DATA, 1, A_BYTE),
                                         (MIDI_DATA, 1, ANOTHER_BYTE)]


def test_the_error_vector_is_the_one_kbdvecs_held_on_entry():
    """`movea.l $e1a(a5),a2` is the routine's FIRST instruction, before the status register is even
    read — so a handler that replaced its own error vector would not be answered until the next
    interrupt. A decoy in the slot proves the read happens; this proves WHEN, by having the byte's
    own vector overwrite the error vector before the overrun arm reaches it.

    NO ATTRIBUTION PASS, and the reason is this case's own output: the byte the run writes IS a
    vector, so poisoning it leaves both cores jumping to its complement. `poison=False` here is the
    documented shape for exactly that (`harness._attribution_check`), and what the pass would have
    added — that the store really happened — is already the decoy's job.
    """
    replace_vmiderr = isr.store_long(acia.DECOY_STUB, acia.SLOT_AT["vmiderr"]) + isr.RTS

    def effect(buf, _argument):
        isr.poke(buf, acia.SLOT_AT["vmiderr"], struct.pack(">I", acia.DECOY_STUB))

    info = run(addrs.MIDI_ACIA_SERVICE, MIDI_GLUE, poison=False,
               routines={acia.STUB_AT["midivec"]: (replace_vmiderr, effect),
                         acia.DECOY_STUB: acia.byte_recorder(acia.DECOY_REPORT)},
               io_seed=acia.declare(acia.MIDI_PORTS, acia.READY_AND_OVERRAN,
                                    [A_BYTE, ANOTHER_BYTE]))
    assert acia.reported_byte(info, "vmiderr") == ANOTHER_BYTE, (
        "the overrun arm followed the vector the RUN installed, not the one it was entered with")
    assert acia.DECOY_REPORT not in info["writes"]


def test_each_entry_names_its_own_chip_and_its_own_iorec():
    """The three instructions that are all the two entries are: a byte declared on ONE chip with the
    other chip idle. If `ikbd_acia_service` read `$fffc04` the case would be refused for a read the
    MIDI declaration cannot serve twice, and if it filed the byte under the MIDI IOREC the scancode
    would go to `midivec` instead of the keyboard."""
    info = run(addrs.IKBD_ACIA_SERVICE, IKBD_GLUE,
               pokes=packet_state(0, 0),
               io_seed=acia.declare(acia.IKBD_PORTS, acia.READY, [addrs.IKBD_FIRST_HEADER]))
    assert info["regs"]["hw_events"] == [(IKBD_STATUS, acia.READY), (IKBD_DATA,
                                                                     addrs.IKBD_FIRST_HEADER)]
    assert info["regs"]["io_events"] == [], (
        "the IKBD's pair is Phase 7's NAMED slots, so its reads belong in the named stream alone")
    assert not acia.called(info, "midivec")


# ---- MIDI: the byte goes to `midivec`, whatever is in it -----------------------------------------

@pytest.mark.parametrize("byte", (0x00, A_BYTE, ANOTHER_BYTE, 0xF6, 0xFF))
def test_a_midi_byte_reaches_midivec_whatever_it_looks_like(byte):
    """`cmpa.l #$c76,a0 / bne` is the WHOLE of the discriminant: a MIDI byte is never a scancode and
    never a packet header, so the five bytes here include both ends of the header range."""
    info = run(addrs.MIDI_ACIA_SERVICE, MIDI_GLUE,
               io_seed=acia.declare(acia.MIDI_PORTS, acia.READY, [byte]))
    assert acia.reported_byte(info, "midivec") == byte
    assert isr.CALLS == [(acia.STUB_AT["midivec"], byte)]


def rom_midivec():
    """The ROM's own `midivec` ($fc2e3a) left in the slot: the ORACLE runs it and the CANDIDATE
    calls the C that reconstructs it. Nothing is poked — the code is already in the image.

    THIS IS WHAT PINS A0. The hook the candidate reaches its vectors through carries one argument,
    so which register the ROM put the IOREC in is invisible to a staged stub; here the byte can only
    land in the ring A0 named, and our own C names `IOREC_MIDI`, so an A0 the ROM computed
    differently diverges in the ring.
    """
    def effect(buf, argument):
        _lib.midi_queue_byte(buf, addrs.IOREC_MIDI, argument & 0xFF)
    return b"", effect


def test_the_captured_machine_s_own_midivec_is_the_rom_s_ring_routine():
    """What the case below leaves in the slot, read out of the snapshot rather than assumed."""
    assert isr.vector_in_snapshot(addrs.KBDVECS + addrs.KBDVECS_MIDIVEC) == addrs.MIDI_QUEUE_BYTE


def test_a_midi_byte_reaches_the_midi_ring_through_the_rom_s_own_vector():
    """The whole MIDI path composed: service, take byte, `midivec`, ring — with the ROM's routine in
    the slot rather than a stub."""
    info = run(addrs.MIDI_ACIA_SERVICE, MIDI_GLUE,
               vectors={"midivec": addrs.MIDI_QUEUE_BYTE},
               routines={addrs.MIDI_QUEUE_BYTE: rom_midivec()},
               pokes=iorec.staged(addrs.IOREC_MIDI, 0, 0),
               io_seed=acia.declare(acia.MIDI_PORTS, acia.READY, [A_BYTE]))
    assert info["writes"][iorec.buffer_of(addrs.IOREC_MIDI) + addrs.IOREC_MIDI_BYTES] == A_BYTE
    assert case.written(info, addrs.IOREC_MIDI + addrs.IOREC_TAIL, 2) == addrs.IOREC_MIDI_BYTES


# ---- `midi_queue_byte` at its own entry: the ring's wrap and its full rule ------------------------
# Entered with the registers its caller leaves — the IOREC in A0 and the byte in D0 — which is what
# lets the ring's own arithmetic be driven without a 6850 in front of it.

def queue_byte(byte):
    def glue(lib, buf):
        lib.midi_queue_byte(buf, addrs.IOREC_MIDI, byte)
    return glue


def run_queue_byte(head, tail, byte=A_BYTE):
    return run(addrs.MIDI_QUEUE_BYTE, queue_byte(byte),
               pokes=iorec.staged(addrs.IOREC_MIDI, head, tail),
               regs={"d0": byte, "a0": addrs.IOREC_MIDI})


MIDI_RING_BYTES = iorec.size_of(addrs.IOREC_MIDI)


@pytest.mark.parametrize("tail", (0, 1, MIDI_RING_BYTES - 3, MIDI_RING_BYTES - 2))
def test_a_midi_byte_lands_one_record_past_the_tail(tail):
    info = run_queue_byte(head=0, tail=tail)
    buffer = iorec.buffer_of(addrs.IOREC_MIDI)
    assert info["writes"][buffer + tail + addrs.IOREC_MIDI_BYTES] == A_BYTE
    assert case.written(info, addrs.IOREC_MIDI + addrs.IOREC_TAIL, 2) == \
        tail + addrs.IOREC_MIDI_BYTES


def test_the_tail_wraps_to_zero_at_the_ring_s_size_and_not_one_short_of_it():
    """`cmp.w size,d1 / bcs` — the index that EQUALS the size goes to 0, the one below it does not.
    Both boundaries, because an off-by-one either way passes the other case."""
    last = run_queue_byte(head=addrs.IOREC_MIDI_BYTES, tail=MIDI_RING_BYTES - 2)
    assert case.written(last, addrs.IOREC_MIDI + addrs.IOREC_TAIL, 2) == MIDI_RING_BYTES - 1
    wrapped = run_queue_byte(head=addrs.IOREC_MIDI_BYTES, tail=MIDI_RING_BYTES - 1)
    assert case.written(wrapped, addrs.IOREC_MIDI + addrs.IOREC_TAIL, 2) == 0


@pytest.mark.parametrize("head,tail", ((addrs.IOREC_MIDI_BYTES, 0),
                                       (0, MIDI_RING_BYTES - 1),
                                       (MIDI_RING_BYTES // 2 + addrs.IOREC_MIDI_BYTES,
                                        MIDI_RING_BYTES // 2)))
def test_a_full_midi_ring_drops_the_byte_and_moves_nothing(head, tail):
    """THE OVERFLOW RULE, and it is the newest byte that is lost: the tail is not advanced and the
    head is not either, so the reader keeps every byte it has not taken yet. The wrap boundary is one
    of the three, which is where a reconstruction that compared before wrapping would differ."""
    info = run_queue_byte(head=head, tail=tail)
    assert info["writes"] == {}, "a full ring must leave the record and both indices alone"


# ---- the packet state machine: a HEADER ----------------------------------------------------------
# Every claim below is over the IKBD entry, because only the IKBD's IOREC reaches the packet machine
# at all — `cmpa.l #$c76,a0`.

def take_ikbd_byte(byte, pokes=None, poison=True, routines=None):
    return run(addrs.IKBD_ACIA_SERVICE, IKBD_GLUE,
               pokes={**packet_state(0, 0), **(pokes or {})}, routines=routines, poison=poison,
               io_seed=acia.declare(acia.IKBD_PORTS, acia.READY, [byte]))


# The header byte, the kind it starts, and how many bytes follow it — read out of the ROM's own two
# tables by the case rather than written down, so this is a claim about the ROM's indexing and not a
# second copy of its data.
HEADERS = tuple(range(addrs.IKBD_FIRST_HEADER, 0x100))


@pytest.mark.parametrize("header", HEADERS)
def test_a_header_byte_starts_the_packet_its_two_tables_name(header):
    """`subi.b #$f6 / andi.l #255` and two indexed byte reads. All ten headers, so a reconstruction
    that indexed from the wrong base — or that masked to a word — lands on another row."""
    index = header - addrs.IKBD_FIRST_HEADER
    info = take_ikbd_byte(header)
    assert info["writes"][addrs.IKBD_PACKET_KIND] == \
        BASE_IMAGE[addrs.IKBD_PACKET_KIND_TABLE + index]
    assert info["writes"][addrs.IKBD_PACKET_REMAINING] == \
        BASE_IMAGE[addrs.IKBD_PACKET_COUNT_TABLE + index]


@pytest.mark.parametrize("header", HEADERS)
def test_only_two_families_of_header_are_kept_and_each_at_its_own_packet(header):
    """The two SIGNED byte compares, over every header: $f8..$fb store theirs at the relative mouse
    packet, $fd..$ff at the joystick packet, and $f6, $f7 and $fc store nothing at all — which is
    what makes their handlers' packets start with DATA rather than with a header."""
    info = take_ikbd_byte(header)
    kept = {at: value for at, value in info["writes"].items()
            if at in (addrs.IKBD_RELATIVE_MOUSE_PACKET, addrs.IKBD_JOYSTICK_PACKET)}
    if addrs.IKBD_RELATIVE_MOUSE_FIRST <= header <= addrs.IKBD_RELATIVE_MOUSE_LAST:
        assert kept == {addrs.IKBD_RELATIVE_MOUSE_PACKET: header}
    elif header >= addrs.IKBD_JOYSTICK_FIRST:
        assert kept == {addrs.IKBD_JOYSTICK_PACKET: header}
    else:
        assert kept == {}


@pytest.mark.parametrize("header", HEADERS)
def test_a_header_calls_no_vector_however_long_its_packet_is(header):
    """Not even the $f6 report, whose packet is seven bytes: a header only ARMS the machine."""
    info = take_ikbd_byte(header)
    assert not any(acia.called(info, name) for name, _offset, _kind in acia.SLOTS)


# ---- ...and every byte after it ------------------------------------------------------------------
# The five tabled kinds, as (kind, packet, end, vector) read out of the ROM's own descriptor table,
# so the case indexes the table the routine indexes.

def descriptor(kind):
    entry = addrs.IKBD_PACKET_TABLE + (kind - 1) * addrs.IKBD_PACKET_TABLE_STRIDE
    fields = struct.unpack_from(">III", bytes(BASE_IMAGE[entry:entry + 12]))
    return fields


TABLED_KINDS = (1, 2, 3, 4, 5)


@pytest.mark.parametrize("kind", TABLED_KINDS)
@pytest.mark.parametrize("outstanding", (1, 2))
def test_a_packet_byte_lands_at_its_end_less_what_is_still_outstanding(kind, outstanding):
    """The fill runs BACKWARDS from the packet's end, so the bytes land in the order they arrived.
    Two counts apiece, which is what separates "at the end" from "at the start"."""
    packet, end, _slot = descriptor(kind)
    info = take_ikbd_byte(A_BYTE, pokes=packet_state(kind, outstanding))
    assert info["writes"][end - outstanding] == A_BYTE
    assert packet <= end - outstanding < end


@pytest.mark.parametrize("kind", TABLED_KINDS)
def test_a_packet_that_still_wants_bytes_counts_down_and_calls_nothing(kind):
    info = take_ikbd_byte(A_BYTE, pokes=packet_state(kind, 2))
    assert info["writes"][addrs.IKBD_PACKET_REMAINING] == 1
    assert addrs.IKBD_PACKET_KIND not in info["writes"], "the kind is cleared only on the LAST byte"
    assert not any(acia.called(info, name) for name, _offset, _kind in acia.SLOTS)


# Which KBDVECS slot each tabled kind's descriptor names, derived from the ROM's third longword
# rather than typed: the table holds the ADDRESS OF A SLOT, and this is the slot's name.
VECTOR_OF_KIND = {kind: next(name for name, offset, _k in acia.SLOTS
                             if addrs.KBDVECS + offset == descriptor(kind)[2])
                  for kind in TABLED_KINDS}


@pytest.mark.parametrize("kind", TABLED_KINDS)
def test_the_last_byte_of_a_packet_dispatches_it_and_clears_the_state(kind):
    """`jsr (a2) / clr.b $e36`, in that order. The vector is handed the packet's own START address —
    which for the two kinds whose header was kept is the header, and for the other three is the
    first DATA byte — and the state byte is cleared afterwards, so a handler that looked would find
    the packet still in progress."""
    packet, _end, _slot = descriptor(kind)
    info = take_ikbd_byte(A_BYTE, pokes=packet_state(kind, 1))
    assert acia.called(info, VECTOR_OF_KIND[kind])
    assert acia.reported(info, VECTOR_OF_KIND[kind]) == packet
    assert info["writes"][addrs.IKBD_PACKET_KIND] == 0
    assert info["writes"][addrs.IKBD_PACKET_REMAINING] == 0


@pytest.mark.parametrize("kind,vector", ((3, "mousevec"), (6, "joyvec")),
                         ids=("a tabled kind", "an untabled one"))
def test_the_state_byte_is_cleared_AFTER_the_handler_runs_and_not_before(kind, vector):
    """`jsr (a2) / clr.b $e36`, and the ORDER is otherwise invisible — the byte ends at 0 either way.
    A stub that REPORTS what it finds there is what separates them, and both dispatch arms are
    driven, because the untabled one reaches the same two instructions by a different route."""
    state = acia.STUB_AT[vector]
    info = take_ikbd_byte(A_BYTE, pokes=packet_state(kind, 1),
                          routines={state: acia.state_recorder(acia.DECOY_REPORT)})
    assert info["writes"][acia.DECOY_REPORT] == kind
    assert info["writes"][addrs.IKBD_PACKET_KIND] == 0


def test_two_kinds_share_mousevec_and_the_packet_address_is_what_tells_them_apart():
    """Kinds 2 and 3 — absolute and relative mouse — name the SAME slot, so the only thing that says
    which report arrived is the address the handler is given. A reconstruction that read the
    descriptor's first longword from the wrong row passes every other case here."""
    assert VECTOR_OF_KIND[2] == VECTOR_OF_KIND[3] == "mousevec"
    assert descriptor(2)[0] != descriptor(3)[0]


def test_the_packet_is_passed_BOTH_pushed_and_in_a0():
    """The published KBDVECS contract: `move.l a0,-(sp) / jsr (a2)` with A0 still naming the packet,
    so an asm handler reads the register and a C one reads its argument. The recorder writes both,
    and the candidate writes its ONE argument into both — so the case is green only if the
    ORIGINAL's two were the same address."""
    packet, _end, _slot = descriptor(3)
    info = run(addrs.IKBD_ACIA_SERVICE, IKBD_GLUE,
               pokes=packet_state(3, 1), vectors={"mousevec": acia.BOTH_STUB},
               routines={acia.BOTH_STUB: acia.both_recorder(acia.BOTH_REPORT)},
               io_seed=acia.declare(acia.IKBD_PORTS, acia.READY, [A_BYTE]))
    assert case.written(info, acia.BOTH_REPORT, acia.BOTH_REPORT_BYTES) == \
        (packet << 32) | packet


@pytest.mark.parametrize("kind,slot", ((6, addrs.IKBD_JOYSTICK_DATA),
                                       (7, addrs.IKBD_JOYSTICK_DATA + 1)))
def test_the_two_single_stick_reports_store_beside_the_header_and_go_to_joyvec(kind, slot):
    """`cmpi.b #6 / bcc` — kinds 6 and 7 are not in the descriptor table at all. Their one data byte
    goes to `$e4e + kind - 6`, so joystick 0's lands next to the header and joystick 1's one further
    on, and both hand `joyvec` the header's own address."""
    info = take_ikbd_byte(A_BYTE,
                          pokes=packet_state(kind, 1, (addrs.IKBD_JOYSTICK_PACKET, b"\xfe")))
    assert info["writes"][slot] == A_BYTE
    assert acia.reported(info, "joyvec") == addrs.IKBD_JOYSTICK_PACKET
    assert info["writes"][addrs.IKBD_PACKET_KIND] == 0
    assert addrs.IKBD_PACKET_REMAINING not in info["writes"], (
        "the untabled arm never touches the count — it dispatches on the byte it is given")


def test_the_both_sticks_report_overwrites_its_own_header():
    """Kind 5 is two bytes ENDING at `$e4f`, so its first byte lands on the `$e4d` the header went
    to. That is the ROM's arrangement rather than an accident: `joyvec` is handed `$e4d` either way,
    and what it finds there is stick 0 for a $fd report and the header for a $fe/$ff one."""
    _packet, end, _slot = descriptor(5)
    assert end == addrs.IKBD_PACKET_END
    first = take_ikbd_byte(A_BYTE,
                           pokes=packet_state(5, 2, (addrs.IKBD_JOYSTICK_PACKET,
                                                     bytes([addrs.IKBD_JOYSTICK_FIRST]))))
    assert first["writes"][addrs.IKBD_JOYSTICK_PACKET] == A_BYTE


# ---- the scancode handoff, and the negative controls ---------------------------------------------

@pytest.mark.parametrize("byte", (0x00, 0x01, addrs.SCANCODE_LEFT_SHIFT,
                                  addrs.IKBD_FIRST_HEADER - 1))
def test_a_byte_below_the_first_header_is_a_scancode(byte):
    """`cmpi.b #$f6,d0 / bcs` is UNSIGNED, so every break scancode — $80 and up — is a key and not a
    packet. $f5, the byte below the first header, is the boundary."""
    info = take_ikbd_byte(byte, pokes={addrs.KBSHIFT: b"\x00"})
    assert addrs.IKBD_PACKET_KIND not in info["writes"], "a scancode must not arm the packet machine"


def test_a_data_port_with_no_declaration_refuses_the_case():
    """THE NEGATIVE CONTROL under every case above: the model does not answer a read nobody declared,
    so a case that forgot the data port is refused BY ADDRESS rather than served a fabricated 0."""
    with pytest.raises(Exception) as raised:
        run(addrs.IKBD_ACIA_SERVICE, IKBD_GLUE, pokes=packet_state(0, 0),
            io_seed=acia.declare(acia.IKBD_PORTS, acia.READY))
    assert "fffc02" in str(raised.value).lower() or "unmodel" in str(raised.value).lower(), (
        f"the case failed for a reason other than the undeclared data port: {raised.value}")


def test_a_list_that_runs_out_is_refused_by_address_and_by_read_index():
    """...and the other end of a declaration: the overrun arm pops the port a SECOND time, so a
    one-byte list describes a run this case does not make. The refusal names the address and WHICH
    read ran off the end, which is what tells "the list is short" from "the routine reads more times
    than the case expected"."""
    with pytest.raises(Exception) as raised:
        run(addrs.MIDI_ACIA_SERVICE, MIDI_GLUE,
            io_seed=acia.declare(acia.MIDI_PORTS, acia.READY_AND_OVERRAN, [A_BYTE]))
    message = str(raised.value).lower()
    assert "fffc06" in message and "1" in message, (
        f"the refusal named neither the address nor the read index: {raised.value}")


# ---- the cases this battery REGISTERS ------------------------------------------------------------
# THREE, one per routine this file enters at its own address, and each is a case above with a name.
# They are what gives these routines Tier 3 rows of their own: nothing CALLS one of them — the ACIA
# handler jumps through a KBDVECS slot — so `bench/tier3.py` reaches them through a relation of its
# own (`VECTOR_ROUTINE_NAMES`) and prices them against the ROM's. Before that they were measured only
# inside `isr_acia, real vectors`, where BOTH columns run the ROM's chain.
#
# `acia_take_byte` ($fc2a42) is NOT here and is DEFERRED: no case enters it directly, so nothing in
# this battery pins the registers it is entered with, and a row built on a guessed contract would be
# a number about a call the machine never makes (`recreate/STATUS.md`).
RELATIVE_MOUSE_KIND = 3         # the descriptor row `mousevec` takes a three-byte report through

REGISTERED = (
    # The MIDI entry at its plainest: the status says a byte is waiting, and it goes to `midivec`.
    {"name": "midi_acia_service, a byte", "entry": addrs.MIDI_ACIA_SERVICE, "glue": MIDI_GLUE,
     "io_seed": acia.declare(acia.MIDI_PORTS, acia.READY, [A_BYTE])},
    # ...and the IKBD entry over the arm that does the most: the byte that COMPLETES a packet, so the
    # descriptor is read, the packet filled, the vector dispatched and the state cleared.
    {"name": "ikbd_acia_service, a packet's last byte", "entry": addrs.IKBD_ACIA_SERVICE,
     "glue": IKBD_GLUE, "pokes": packet_state(RELATIVE_MOUSE_KIND, 1),
     "io_seed": acia.declare(acia.IKBD_PORTS, acia.READY, [A_BYTE])},
    # ...and the ROM's own `midivec`, entered with the registers its caller leaves.
    {"name": "midi_queue_byte, one byte into the ring", "entry": addrs.MIDI_QUEUE_BYTE,
     "glue": queue_byte(A_BYTE), "regs": {"d0": A_BYTE, "a0": addrs.IOREC_MIDI},
     "pokes": iorec.staged(addrs.IOREC_MIDI, 0, 0)},
)
VERIFIED_CASES = tuple(acia.registered(spec) for spec in REGISTERED)


@pytest.mark.parametrize("spec", REGISTERED, ids=lambda spec: spec["name"])
def test_every_registered_case_is_one_this_battery_proves(spec):
    """The row and the differential are the SAME spec (`acia.registered` / `acia.run_spec`)."""
    acia.run_spec(spec)
