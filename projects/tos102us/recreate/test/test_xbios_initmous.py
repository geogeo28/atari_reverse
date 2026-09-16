"""XBIOS Initmous (function $00) @ $fc2f28 — the IKBD's mouse mode, and the handler its packets go to.

Reconstructed from the DISASSEMBLY: this is one of `COMPONENTS.md`'s 73 functions the decompiler
cannot express (the Alcyon write-to-`(sp)` idiom), like `Setexc` before it.

WHAT IT DOES is build a whole IKBD command packet in a fixed RAM buffer at `$e6e` and hand it to
`Ikbdws`'s own loop at `$fc221c`. So its effects are of two kinds and both are compared: the packet
is IMAGE (the byte diff sees every one of it), and the bytes that leave for the 6301 are the ordered
hardware WRITE ledger. A reconstruction that built the right packet and sent the wrong number of
bytes passes one and fails the other, which is why the count is a case of its own here.

THE PACKET IS BUILT INDEPENDENTLY IN THIS FILE, from the disassembly rather than by calling the
reconstruction: `packet()` below is the claim, and the differential is what says the ROM agrees with
it. A helper that asked the core what it had built would agree with any answer.

TWO THINGS ARE EASY TO GET WRONG AND EACH HAS ITS OWN CASE. The VECTOR is stored BEFORE the mode is
known to be valid, so mode 3 installs the caller's handler and then returns 0 having sent nothing;
and `16 - topmode` is a BYTE subtract (`moveq #16,d1` / `sub.b (a3),d1`), so a topmode above 16
sends a byte that wrapped rather than a negative number.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import abi
import case
import staging

_lib.xbios_initmous.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16,
                                ctypes.c_uint32, ctypes.c_uint32]
_lib.xbios_initmous.restype = ctypes.c_uint32

PARAM_AT = staging.SCRATCH
# A parameter block whose every field is a different byte, so a reconstruction that copied the wrong
# one — xparam for yparam, ymax for xmax — diverges on the packet rather than by luck.
PARAM = bytes([0x01, 0x02,              # topmode, buttons
               0x03, 0x04,              # xparam, yparam
               0x11, 0x12, 0x13, 0x14,  # xmax, ymax
               0x21, 0x22, 0x23, 0x24])  # xinitial, yinitial
A_HANDLER = 0x0006_1234
# The modes the ROM's three `cmpi.w` tests do NOT name. 3 is the documented gap between absolute and
# keycode; 5 and $1234 are past the last of them; and the ROM checks the WHOLE word, so $0100 — whose
# low byte is 0, the disable mode — is not the disable mode.
UNKNOWN_MODES = (3, 5, 0x0100, 0x1234, 0xFFFF)
# The IKBD's status byte is a Phase-7 NAMED slot the seeded model declares itself (see
# test_xbios_ikbdws.py, which pins that default), so a case here declares nothing at all.
READY = {}
# `rts`, which is the whole of the handler mode 0 parks `mousevec` on.
RTS = b"\x4e\x75"


def common_parameters(param=PARAM):
    """`$fc2fd8` — the five bytes every reporting mode ends with, spelt from the disassembly."""
    return bytes([param[addrs.MOUSE_PARAM_XPARAM],
                  param[addrs.MOUSE_PARAM_YPARAM],
                  (addrs.MOUSE_TOPMODE_ORIGIN - param[addrs.MOUSE_PARAM_TOPMODE]) & 0xFF,
                  addrs.IKBD_SET_BUTTON_ACTION,
                  param[addrs.MOUSE_PARAM_BUTTONS]])


def packet(mode, param=PARAM):
    """The whole IKBD command packet one mode builds, from the disassembly."""
    if mode == addrs.INITMOUS_RELATIVE:
        return bytes([addrs.IKBD_SET_RELATIVE_MOUSE,
                      addrs.IKBD_SET_MOUSE_THRESHOLD]) + common_parameters(param)
    if mode == addrs.INITMOUS_ABSOLUTE:
        return (bytes([addrs.IKBD_SET_ABSOLUTE_MOUSE]) + param[addrs.MOUSE_PARAM_XMAX:
                                                               addrs.MOUSE_PARAM_XMAX + 4]
                + bytes([addrs.IKBD_SET_MOUSE_SCALE]) + common_parameters(param)
                + bytes([addrs.IKBD_SET_MOUSE_POSITION, addrs.MOUSE_POSITION_FILLER])
                + param[addrs.MOUSE_PARAM_XINITIAL:addrs.MOUSE_PARAM_XINITIAL + 4])
    if mode == addrs.INITMOUS_KEYCODE:
        return bytes([addrs.IKBD_SET_KEYCODE_MOUSE]) + common_parameters(param)
    raise AssertionError(f"mode {mode} builds no packet")


REPORTING_MODES = (addrs.INITMOUS_RELATIVE, addrs.INITMOUS_ABSOLUTE, addrs.INITMOUS_KEYCODE)
# The `Ikbdws` count each mode passes, which is ONE LESS than its packet — read from the ROM's own
# `moveq` rather than derived, so a packet and a count that both moved together still reds.
MODE_COUNTS = {addrs.INITMOUS_RELATIVE: addrs.INITMOUS_RELATIVE_COUNT,
               addrs.INITMOUS_ABSOLUTE: addrs.INITMOUS_ABSOLUTE_COUNT,
               addrs.INITMOUS_KEYCODE: addrs.INITMOUS_KEYCODE_COUNT}


def frame(mode, param=PARAM_AT, vector=A_HANDLER):
    return {abi.FIRST_ARG: struct.pack(">HII", mode & 0xFFFF, param, vector)}


def run(mode, param=PARAM, param_at=PARAM_AT, vector=A_HANDLER, poison=True):
    def glue(lib, buf):
        return lib.xbios_initmous(buf, mode & 0xFFFF, param_at, vector)

    return case.run(addrs.XBIOS_INITMOUS,
                    {"a5": 0, "_pokes": {**frame(mode, param_at, vector), param_at: param}},
                    glue, poison=poison, io_seed=READY)


def sent(info):
    """The bytes that left for the 6301, out of the ordered hardware write ledger."""
    return bytes(value for address, _width, value in info["regs"]["hw_writes"]
                 if address == addrs.IKBD_ACIA_DATA)


def mousevec(info):
    return case.written_long(info, addrs.KBDVECS + addrs.KBDVECS_MOUSEVEC)


@pytest.mark.parametrize("mode", REPORTING_MODES)
def test_each_reporting_mode_sends_the_packet_it_builds(mode):
    """The three modes that talk to the mouse, byte for byte and in order."""
    info = run(mode)
    assert sent(info) == packet(mode)
    assert info["ret"] == addrs.INITMOUS_DONE


@pytest.mark.parametrize("mode", REPORTING_MODES)
def test_the_packet_is_left_in_the_buffer_it_was_built_in(mode):
    """...and the other half of the same fact, which the SEND ledger cannot show: the bytes are
    written into `$e6e` first. A reconstruction that sent the packet without building it agrees with
    the case above and leaves memory unchanged, which the byte diff catches — but only if the buffer
    is where `addrs.h` says, so it is read back out of the ORACLE's own write ledger here."""
    info = run(mode, poison=False)
    built = bytes(case.written(info, addrs.INITMOUS_PACKET + i, 1) for i in range(len(packet(mode))))
    assert built == packet(mode)


@pytest.mark.parametrize("mode", REPORTING_MODES)
def test_the_count_is_one_less_than_the_packet(mode):
    """`moveq #6/#16/#5,d3` against packets of 7, 17 and 6 bytes — `Ikbdws`'s `dbf` convention, and
    the one place a byte can be dropped or one too many sent without the buffer showing it."""
    assert MODE_COUNTS[mode] + 1 == len(packet(mode))
    assert len(sent(run(mode, poison=False))) == MODE_COUNTS[mode] + 1


def test_disabling_sends_one_byte_and_parks_the_vector_on_the_rom_s_own_rts():
    """Mode 0 is the odd one: one command byte straight through the single-byte sender, no buffer at
    all, and `mousevec` set to a ROM `rts` rather than to the caller's handler — "no mouse" here
    means a handler that discards the packet, not a null pointer nothing checks."""
    info = run(addrs.INITMOUS_DISABLE)
    assert sent(info) == bytes([addrs.IKBD_DISABLE_MOUSE])
    assert mousevec(info) == addrs.MOUSE_DISCARD_HANDLER
    # ...AND THE ORDER OF THOSE TWO IS UNPINNED, which is worth saying because every other ordering
    # claim in this wave is pinned. The ROM sends the byte and THEN stores the vector
    # (`src/xbios/initmous.c`), but the byte lands in the hardware WRITE ledger and the vector in the
    # image, and the differential compares each stream against its own: there is no cross-stream
    # order, so a reconstruction that stored first would pass every case in this file. Nothing here
    # can close it; what would is a single ordered stream over both, in the kit.
    assert info["ret"] == addrs.INITMOUS_DONE
    assert not any(addrs.INITMOUS_PACKET <= at < addrs.INITMOUS_PACKET + len(packet(2))
                   for at in info["writes"]), "mode 0 touched the packet buffer"


def test_the_disabled_vector_is_a_bare_rts_in_the_rom():
    """...read out of the mapped ROM, so `MOUSE_DISCARD_HANDLER` naming the wrong address reds here
    rather than agreeing with itself. `$4e75` is `rts`."""
    at = addrs.MOUSE_DISCARD_HANDLER
    assert bytes(BASE_IMAGE[at:at + len(RTS)]) == RTS


@pytest.mark.parametrize("mode", UNKNOWN_MODES)
def test_an_unknown_mode_installs_the_handler_and_then_refuses(mode):
    """THE CASE THE ROM's ORDER MAKES: the vector is stored before the three `cmpi.w`, so a caller
    that checks the result and gives up has still replaced `mousevec`. Nothing is sent."""
    info = run(mode)
    assert info["ret"] == addrs.INITMOUS_UNKNOWN_MODE
    assert mousevec(info) == A_HANDLER
    assert sent(info) == b""


def test_the_handler_is_the_caller_s_and_goes_in_mousevec():
    """...and for the modes that do work, over two different handlers so a reconstruction that stored
    a constant — or stored into the wrong slot of KBDVECS — diverges.

    ONE MODE, because the store is the ROM's single `move.l 10(sp),$e22` at `$fc2f2e`, ahead of the
    three `cmpi.w` that choose an arm: the claim is mode-independent by construction, and the case
    above has already run it over the three modes that refuse. Sweeping the reporting modes here
    would re-run the same instruction three times.
    """
    for vector in (A_HANDLER, 0x00FC_5678):
        assert mousevec(run(addrs.INITMOUS_RELATIVE, vector=vector, poison=False)) == vector


# Topmodes that make the byte subtract visible: the origin itself, one below it, the value that
# makes it zero, and two above it — where a WORD subtract would leave a negative number and this
# leaves a byte that has wrapped.
TOPMODES = (0x00, 0x01, 0x10, 0x11, 0x20, 0xFF)


@pytest.mark.parametrize("topmode", TOPMODES)
def test_the_y_origin_is_a_byte_subtract(topmode):
    """`moveq #16,d1 / sub.b (a3),d1` — and the ROM bounds neither side of it."""
    param = bytes([topmode]) + PARAM[1:]
    info = run(addrs.INITMOUS_RELATIVE, param=param, poison=False)
    assert sent(info) == packet(addrs.INITMOUS_RELATIVE, param)
    assert sent(info)[4] == (addrs.MOUSE_TOPMODE_ORIGIN - topmode) & 0xFF


def test_the_parameter_block_is_read_from_wherever_the_caller_points():
    """The pointer is the caller's, so two blocks a page apart send their own bytes. A reconstruction
    that read a fixed address would agree with every case above and with nothing else."""
    elsewhere = PARAM_AT + 0x100
    assert elsewhere + len(PARAM) <= staging.SCRATCH + staging.SCRATCH_BYTES
    other = bytes(0x40 + i for i in range(len(PARAM)))
    info = run(addrs.INITMOUS_ABSOLUTE, param=other, param_at=elsewhere, poison=False)
    assert sent(info) == packet(addrs.INITMOUS_ABSOLUTE, other)


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominators for this row's two cases, measured rather than estimated."""
    costs = {}
    for mode in (addrs.INITMOUS_DISABLE, addrs.INITMOUS_ABSOLUTE):
        _final, _writes, regs = emu.run(make_image({**frame(mode), PARAM_AT: PARAM}),
                                        addrs.XBIOS_INITMOUS, {"a5": 0}, io_seed=READY)
        costs[mode] = (regs["ninsns"], regs["cycles"])
    assert costs == {addrs.INITMOUS_DISABLE: (2869, 42064),
                     addrs.INITMOUS_ABSOLUTE: (48709, 713890)}, (
        f"Initmous now costs {costs} — STATUS.md's Tier 3 denominators are stale")
