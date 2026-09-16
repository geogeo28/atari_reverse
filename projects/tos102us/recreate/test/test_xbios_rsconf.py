"""XBIOS Rsconf (function $0f) @ $fc290e — the RS232 port's whole configuration in one call.

Six optional WORD arguments, each spelt TOS's way: a negative one means "leave this alone". Four of
them are the MFP's USART registers stored as their low byte; one is a handshake mode kept in the
RS232 IOREC; and the first is a baud rate, which on an ST is MFP timer D and is therefore a call into
the shared timer programmer.

THE RESULT IS THE PREVIOUS CONFIGURATION, read BEFORE anything is changed, and it is one `movep.l` —
the 68000's instruction for a peripheral wired to every other byte of the bus. So the longword a
caller gets back is UCR:RSR:TSR:UDR, high byte first, and its low byte is the USART's DATA register:
a byte of received traffic rather than a setting. Every case below declares four DIFFERENT bytes, so
a reconstruction that packed them in another order — or read three of them and invented the fourth —
diverges on the value rather than on luck.

THE BAUD ARM IS NOT RECONSTRUCTED, and the reason is measured here rather than asserted: the timer
programmer writes timer D's data register and reads it back until the 68901 agrees, which the
declared I/O map cannot serve (a declaration describes the byte a register held on ENTRY). The core
HALTS there, so no case in this file passes a non-negative baud to the candidate; what they do
instead is run the ORIGINAL and require the refusal, and pin the two baud tables the arm indexes.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, differential, emu, make_image

import abi
import case

_lib.xbios_rsconf.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.xbios_rsconf.restype = ctypes.c_uint32

KEEP = 0xFFFF
# What the case declares the USART held on entry: four bytes that are different from each other and
# from every argument any case stores, so the packing order is separable.
USART_ENTRY = {addrs.MFP_UCR: 0x8A, addrs.MFP_RSR: 0x5B, addrs.MFP_TSR: 0x3C, addrs.MFP_UDR: 0x6D}
PREVIOUS = ((USART_ENTRY[addrs.MFP_UCR] << 24) | (USART_ENTRY[addrs.MFP_RSR] << 16)
            | (USART_ENTRY[addrs.MFP_TSR] << 8) | USART_ENTRY[addrs.MFP_UDR])

# The four optional USART registers, in the ROM's own store order — which is not the order it read
# them in, and not the order of the argument list either (SCR is last but its register is lowest).
STORE_ORDER = ((addrs.MFP_UCR, "ucr"), (addrs.MFP_RSR, "rsr"),
               (addrs.MFP_TSR, "tsr"), (addrs.MFP_SCR, "scr"))
ARGUMENT_INDEX = {"baud": 0, "flow": 1, "ucr": 2, "rsr": 3, "tsr": 4, "scr": 5}


def frame(**arguments):
    """The six argument words, defaulting to KEEP — which is the call that changes nothing."""
    words = [KEEP] * len(ARGUMENT_INDEX)
    for name, value in arguments.items():
        words[ARGUMENT_INDEX[name]] = value & 0xFFFF
    return {abi.FIRST_ARG: struct.pack(">6H", *words)}


def run(pokes=None, poison=True, io_seed=None, **arguments):
    words = {name: KEEP for name in ARGUMENT_INDEX}
    words.update(arguments)
    assert words["baud"] & 0x8000, "the baud arm halts the candidate — see the module docstring"

    def glue(lib, buf):
        # The SAME words the oracle reads: the core takes the caller's argument block, as the ROM
        # does, so the case hands it the frame it staged rather than six values of its own.
        return lib.xbios_rsconf(buf, abi.FIRST_ARG)

    return case.run(addrs.XBIOS_RSCONF,
                    {"a5": 0, "_pokes": {**frame(**arguments), **(pokes or {})}}, glue,
                    poison=poison, io_seed=io_seed or dict(USART_ENTRY))


def stores(info):
    return [(address, value) for address, _width, value in info["regs"]["hw_writes"]]


def test_it_reports_the_four_usart_registers_as_one_longword_in_that_order():
    """UCR:RSR:TSR:UDR, which is what `movep.l 40(a1),d7` reads off every other byte of the bus."""
    info = run()
    assert info["regs"]["d0"] == PREVIOUS
    assert [(address, value) for address, _width, value in info["regs"]["io_events"]] == \
        [(addrs.MFP_UCR, USART_ENTRY[addrs.MFP_UCR]), (addrs.MFP_RSR, USART_ENTRY[addrs.MFP_RSR]),
         (addrs.MFP_TSR, USART_ENTRY[addrs.MFP_TSR]), (addrs.MFP_UDR, USART_ENTRY[addrs.MFP_UDR])]


def test_the_result_is_read_before_the_arguments_are_stored():
    """...so a call that CHANGES all four registers still reports what they held on entry.

    WHAT THIS CASE CAN AND CANNOT SAY. It says the REPORTED value is the entry configuration, which
    is the claim a caller cares about. It does NOT rule out a reconstruction that read the four
    registers at the END: the declared I/O map serves the byte an address held on ENTRY however late
    the read comes, so such a build would be handed the same four bytes and report the same
    longword. The surface that catches it is TIER 3's — our m68k build's read of a register it had
    just stored to is a STALE read, and `rom_bench._vet_no_refusals` refuses the row rather than
    measuring it ("read I/O byte(s) THIS run stored to"). So the ORDER is pinned by this routine's
    bench rows and not by the differential; `bench/tier3.py` carries them.
    """
    assert run(ucr=0x11, rsr=0x22, tsr=0x33, scr=0x44)["regs"]["d0"] == PREVIOUS


def test_every_argument_negative_changes_nothing_at_all():
    """The whole call is optional, which is how a program asks what the port is set to."""
    info = run()
    assert stores(info) == [] and info["writes"] == {}


@pytest.mark.parametrize("register,name", STORE_ORDER)
def test_each_usart_register_is_stored_on_its_own(register, name):
    """One argument at a time, so a reconstruction that stored the wrong register — or stored all
    four whenever any was given — diverges on the ledger's address."""
    info = run(**{name: 0x5A})
    assert stores(info) == [(register, 0x5A)]


def test_the_four_are_stored_in_the_rom_s_order():
    """...and together, which is the only case that can see the ORDER. It is not the argument
    list's order in address terms — SCR ($fffa27) is stored last and sits lowest."""
    info = run(ucr=0x11, rsr=0x22, tsr=0x33, scr=0x44)
    assert stores(info) == [(addrs.MFP_UCR, 0x11), (addrs.MFP_RSR, 0x22),
                            (addrs.MFP_TSR, 0x33), (addrs.MFP_SCR, 0x44)]


# Words that separate a `tst.w` from a `tst.b`: $0080's low byte looks negative and it STORES, and
# $ff80's does not and it KEEPS. $7fff and $8000 are the sign boundary itself.
WIDTH_WORDS = ((0x0000, True), (0x0080, True), (0x7FFF, True), (0x8000, False), (0xFF80, False))


@pytest.mark.parametrize("argument,stored", WIDTH_WORDS)
def test_the_optional_test_is_of_the_word_and_the_store_is_of_its_low_byte(argument, stored):
    """`tst.w 8(sp)` then `move.b 9(sp)`: the WORD decides and the BYTE is written."""
    info = run(ucr=argument, poison=False)
    assert stores(info) == ([(addrs.MFP_UCR, argument & 0xFF)] if stored else [])


# The handshake byte's whole arithmetic, from the disassembly: it is stored, read back, and rewritten
# as 1 unless it is 0 or 2 (`andi.b #$fd` leaves only bit 1, so exactly $00 and $02 survive).
FLOW_MODES = ((0x00, 0x00), (0x01, 0x01), (0x02, 0x02), (0x03, 0x01), (0x04, 0x01),
              (0xFF, 0x01), (0x7F02, 0x02), (0x1234, 0x01))


@pytest.mark.parametrize("argument,kept", FLOW_MODES)
def test_the_handshake_byte_is_normalised_to_none_rts_cts_or_xon_xoff(argument, kept):
    """0 and 2 stand; everything else becomes 1 — so mode 3, "both kinds of handshake", is quietly
    demoted to XON/XOFF by this ROM. The argument's LOW BYTE is what is stored, which $7f02 and
    $1234 are here to separate from the word."""
    info = run(flow=argument, poison=False)
    assert case.written(info, addrs.RSCONF_FLOW_CONTROL, 1) == kept
    assert stores(info) == [], "the handshake arm wrote a hardware register"


def test_a_negative_handshake_word_leaves_the_iorec_byte_alone():
    assert run(flow=KEEP)["writes"] == {}


def test_the_handshake_byte_is_the_rs232_iorec_s_own():
    """`$c74` is `$c54 + 32` — past the RS232 input record's five fields, in the pair's own block.
    Asserted against the IOREC `Iorec` already names, so the two constants cannot drift apart."""
    assert addrs.RSCONF_FLOW_CONTROL == addrs.IOREC_RS232 + addrs.IOREC_FLOW_CONTROL
    assert addrs.IOREC_RS232 < addrs.RSCONF_FLOW_CONTROL < addrs.IOREC_IKBD


# ---- the baud arm, which is not reconstructed ----------------------------------------------------

# The two 16-byte tables the arm indexes, read out of the mapped ROM. They are what a future wave
# needs once the data-register write can be run, and they pin both table addresses today.
BAUD_CONTROL = bytes([1] * 14 + [2, 2])
BAUD_DATA = bytes([0x01, 0x02, 0x04, 0x05, 0x08, 0x0A, 0x0B, 0x10,
                   0x20, 0x40, 0x60, 0x80, 0x8F, 0xAF, 0x40, 0x60])


def test_the_two_baud_tables_are_where_addrs_h_says_and_hold_what_it_says():
    """Timer D's control byte and divider, one pair per rate. The control table is $01 for the top
    fourteen rates and $02 for the two slowest — a different prescaler, which is what lets 75 and 50
    baud fit in a byte at all."""
    for table, expected in ((addrs.RSCONF_BAUD_CONTROL_TABLE, BAUD_CONTROL),
                            (addrs.RSCONF_BAUD_DATA_TABLE, BAUD_DATA)):
        assert bytes(BASE_IMAGE[table:table + addrs.RSCONF_BAUD_RATES]) == expected
    assert addrs.RSCONF_BAUD_DATA_TABLE == addrs.RSCONF_BAUD_CONTROL_TABLE + addrs.RSCONF_BAUD_RATES


def test_the_baud_arm_cannot_be_run_under_a_declared_map_and_this_is_why():
    """THE MEASUREMENT THE HALT RESTS ON, so the limit is a red rather than a paragraph.

    Undeclared, timer D's data register answers a fabricated 0 and the programmer's `move.b` /
    `cmp.b` / `bne` loop never ends — the run dies at the instruction cap. Declared equal to the
    byte the arm writes, the run completes and the ORACLE reports STALE reads, which
    `harness._vet_io_reads_are_declared` refuses: the declaration describes the register on ENTRY
    and an instruction of this very run has replaced it. Neither is a case anybody can verify, and
    no bigger declaration is the remedy — `src/xbios/xbtimer.c` says what would be.
    """
    fastest = 0
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(frame(baud=fastest)), addrs.XBIOS_RSCONF, {"a5": 0},
                io_seed=dict(USART_ENTRY), max_insns=20_000)

    written = BAUD_DATA[fastest]
    declared = {**USART_ENTRY, addrs.MFP_TDDR: written, addrs.MFP_TCDCR: 0x77,
                addrs.MFP_IERB: 0x49, addrs.MFP_IPRB: 0x4D, addrs.MFP_ISRB: 0x41,
                addrs.MFP_IMRB: 0x45}
    _final, _writes, o_regs = emu.run(make_image(frame(baud=fastest)), addrs.XBIOS_RSCONF,
                                      {"a5": 0}, io_seed=declared)
    assert o_regs["io_stale_reads"] == 2 and o_regs["io_stale_first"] == addrs.MFP_TDDR, (
        f"the baud arm now makes {o_regs['io_stale_reads']} stale read(s), the first at "
        f"{o_regs['io_stale_first']:#x} — the halt's premise has moved")


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominators for this row's two cases, measured rather than estimated."""
    costs = {}
    for label, arguments in (("report", {}), ("store four", dict(ucr=0x11, rsr=0x22, tsr=0x33,
                                                                scr=0x44))):
        _final, _writes, regs = emu.run(make_image(frame(**arguments)), addrs.XBIOS_RSCONF,
                                        {"a5": 0}, io_seed=dict(USART_ENTRY))
        costs[label] = (regs["ninsns"], regs["cycles"])
    assert costs == {"report": (19, 260), "store four": (23, 332)}, (
        f"Rsconf now costs {costs} — STATUS.md's Tier 3 denominators are stale")
