"""XBIOS Jdisint ($1a) @ $fc2682, Jenabint ($1b) @ $fc26bc and Mfpint ($0d) @ $fc2658.

The MFP 68901's interrupt controller, as the three calls TOS offers onto it. They are ONE body in
the ROM entered at three points: `Mfpint` `bsr`s into `Jdisint` at `$fc268c` and into `Jenabint` at
`$fc26c6` — the instruction after each one's own argument fetch — so the composition the
reconstruction makes is the ROM's own control flow rather than a convenience.

WHAT EACH CASE HAS TO SAY, AND WHY IT IS A DECLARATION. Every one of these routines READS a register
before it writes it — `bclr`/`bset` on the 68000 is a read and a store — and those registers are
off-image, so a case declares what the chip held with `io_seed` (TRAP_MODEL.md, Phase 15) and the
byte stored is a function of it. That is what makes the BIT arithmetic provable at all: with the
read half fabricated as 0 (which is what `hw.h`'s `hw_bclr8` is for, and what a case would get
without a declaration) the store's value would be the bit alone on both sides, and a reconstruction
that wiped the register would be indistinguishable from one that cleared one bit of it.

WHAT NO CASE HERE CAN SAY: the declaration is a per-run CONSTANT describing the chip on ENTRY. So a
routine that stores to a register and then reads it back is refused outright — which is exactly
`Mfpint`, whose enable half re-reads the IERA and IMRA its disable half has already written. That is
measured below rather than asserted, and it is why `Mfpint` is proved as a SLICE.

WHAT IS LEFT OVER, AND HOW IT IS LABELLED. A slice leaves the COMPOSITION open — that `Mfpint` is
the disable, the store and the enable, in that order, on one channel — and no differential here can
close it, because there is no original run to compare against. The last section of this file runs
the reconstruction ALONE and checks it against ledgers composed out of the slices the oracle did
verify. That is weaker than everything above it, so every one of those cases says CANDIDATE-ONLY in
its first line; none of them is evidence that the ROM does what it does, only that this code does.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, differential, emu, make_image

import abi
import case
import mfp

_lib.xbios_jdisint.argtypes = [ctypes.c_uint16]
_lib.xbios_jdisint.restype = ctypes.c_uint32
_lib.xbios_jenabint.argtypes = [ctypes.c_uint16]
_lib.xbios_jenabint.restype = ctypes.c_uint32
_lib.mfp_install_vector.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint32]
_lib.mfp_install_vector.restype = None
_lib.xbios_mfpint.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint32]
_lib.xbios_mfpint.restype = ctypes.c_uint32

CHANNELS = tuple(range(addrs.MFP_CHANNEL_MASK + 1))
# The four MFP channels this ROM really uses, named so a case reads as the machine: the two 6850s
# share channel 6, timer C is the 200 Hz tick, and timer B is the horizontal blank.
CHANNEL_ACIA, CHANNEL_TIMER_C, CHANNEL_TIMER_B = 6, 5, 8
# A handler address to install, and a second one so a case can prove the slot is rewritten.
A_HANDLER, ANOTHER_HANDLER = 0x0006_1234, 0x00FC_5678


def channel_arg(channel, handler=None):
    """The frame the dispatcher's caller leaves: a channel WORD, and Mfpint's handler longword."""
    if handler is None:
        return case.word_arg(channel)
    return {abi.FIRST_ARG: struct.pack(">HI", channel & 0xFFFF, handler)}


def run_disint(channel, io_seed=None, poison=True):
    def glue(lib, buf):
        del buf                      # the whole effect is the chip; see the module docstring
        return lib.xbios_jdisint(channel & 0xFFFF)

    return case.run(addrs.XBIOS_JDISINT, {"a5": 0, "_pokes": channel_arg(channel)}, glue,
                    poison=poison, io_seed=io_seed or mfp.seed())


def run_enabint(channel, io_seed=None, poison=True):
    def glue(lib, buf):
        del buf
        return lib.xbios_jenabint(channel & 0xFFFF)

    return case.run(addrs.XBIOS_JENABINT, {"a5": 0, "_pokes": channel_arg(channel)}, glue,
                    poison=poison, io_seed=io_seed or mfp.seed())


def run_install(channel, handler, io_seed=None, poison=True):
    """`Mfpint` as far as a case can carry it: `[$fc2658, $fc267a)`, up to the enable's `bsr`."""
    def glue(lib, buf):
        lib.mfp_install_vector(buf, channel & 0xFFFF, handler)

    return case.run(addrs.XBIOS_MFPINT, {"a5": 0, "_pokes": channel_arg(channel, handler)}, glue,
                    width=case.NO_RESULT, poison=poison, stop_pc=addrs.MFPINT_ENABLE_HALF,
                    io_seed=io_seed or mfp.seed())


# ---- the two register pairs' order, which is the behaviour ---------------------------------------

DISABLE_ORDER = (addrs.MFP_IMRA, addrs.MFP_IERA, addrs.MFP_IPRA, addrs.MFP_ISRA)
ENABLE_ORDER = (addrs.MFP_IERA, addrs.MFP_IMRA)


@pytest.mark.parametrize("channel", CHANNELS)
def test_disabling_clears_one_bit_of_four_registers_in_the_rom_s_order(channel):
    """Every one of the sixteen channels, over both halves of all four pairs.

    The ORDER is the claim a ledger can make and memory cannot: mask, then enable, then pending,
    then in-service — the channel is masked off before it is disarmed, so nothing can be latched in
    the window, and only then are a pending request and an in-service acknowledgement discarded. A
    reconstruction that wrote the same four registers in any other order leaves the same four bytes
    behind and is a different program on a live machine.
    """
    info = run_disint(channel)
    assert info["regs"]["hw_writes"] == [mfp.bit_cleared(reg, channel) for reg in DISABLE_ORDER]
    assert info["regs"]["io_events"] == [mfp.read(reg, channel) for reg in DISABLE_ORDER], (
        "the read half of each `bclr` is not in the ledger, so the bit arithmetic rests on nothing")


@pytest.mark.parametrize("channel", CHANNELS)
def test_enabling_sets_one_bit_of_two_registers_in_the_other_order(channel):
    """...and the opposite order, which is the other half of the same claim: ARM the channel, then
    unmask it. Doing it the other way round opens a window in which an already-pending request is
    taken through a handler the caller has not finished installing."""
    info = run_enabint(channel)
    assert info["regs"]["hw_writes"] == [mfp.bit_set(reg, channel) for reg in ENABLE_ORDER]
    assert info["regs"]["io_events"] == [mfp.read(reg, channel) for reg in ENABLE_ORDER]


# The words a caller can pass that are NOT a channel number in 0..15: the mask is `andi.l #15`, so
# every one of them names one anyway. $fffd and 13 are the same call, which is what these pin.
ALIASED_ARGUMENTS = ((0xFFFD, 13), (0x0010, 0), (0x7FFF, 15), (0xFFFF, 15), (0x00F5, 5))


@pytest.mark.parametrize("argument,channel", ALIASED_ARGUMENTS)
def test_only_the_low_four_bits_of_the_argument_name_the_channel(argument, channel):
    """`andi.l #15,d0` and no bounds test at all, so the routine cannot be given a bad channel.

    AND THE RESULT SAYS THE SAME THING, which is why it is asserted here rather than in a case of
    its own: the `andi` masks D0 itself and the `movem.l (sp)+` at the end restores that masked
    value, so `Jdisint($fffd)` hands back 13. `case.run` compares the candidate's return against the
    ORACLE's whole D0 on every case in this file; what this line adds is the independent statement
    of WHICH value that is, so a reconstruction returning the caller's argument — or the caller's
    entry D0, which several routines in this wave really do return — reds here.
    """
    disabled, enabled = run_disint(argument, poison=False), run_enabint(argument, poison=False)
    assert disabled["regs"]["hw_writes"] == [mfp.bit_cleared(reg, channel) for reg in DISABLE_ORDER]
    assert enabled["regs"]["hw_writes"] == [mfp.bit_set(reg, channel) for reg in ENABLE_ORDER]
    assert disabled["ret"] == enabled["ret"] == channel, (
        f"the argument {argument:#x} named channel {channel}, but the routines report "
        f"{disabled['ret']:#x} / {enabled['ret']:#x}")


# Four declarations that make the READ half load-bearing: all bits clear, all set, and the two
# patterns that separate "cleared the bit" from "cleared the register" and "set the bit" from
# "stored the bit". A reconstruction ignoring the byte it read passes the first of these only.
LOADED_REGISTERS = (0x00, 0xFF, 0xAA, 0x55)


@pytest.mark.parametrize("held", LOADED_REGISTERS)
def test_the_bits_the_instruction_does_not_name_are_preserved(held):
    """What the declared read buys, over one channel and one byte in every register.

    With `$ff` declared, a reconstruction that stored the bit rather than the register-with-the-bit
    writes `$00` where the ROM writes `$df`; with `$00` declared the two agree, which is why the
    parametrization is the case and not one value.
    """
    declared = {register: held for register in mfp.INTERRUPT_REGISTERS}
    info = run_disint(CHANNEL_TIMER_C, io_seed=mfp.seed(declared), poison=False)
    assert info["regs"]["hw_writes"] == \
        [mfp.bit_cleared(reg, CHANNEL_TIMER_C, declared) for reg in DISABLE_ORDER]
    info = run_enabint(CHANNEL_TIMER_C, io_seed=mfp.seed(declared), poison=False)
    assert info["regs"]["hw_writes"] == \
        [mfp.bit_set(reg, CHANNEL_TIMER_C, declared) for reg in ENABLE_ORDER]


def test_an_undeclared_mfp_register_refuses_the_case():
    """The other half of the model, over this routine: without a declaration the ORACLE's own read
    is a fabricated 0, and the case would be verified against a chip that does not exist."""
    def glue(lib, buf):
        del buf
        lib.xbios_jdisint(CHANNEL_ACIA)

    with pytest.raises(AssertionError, match=f"{addrs.MFP_IMRB:#x}") as raised:
        differential(addrs.XBIOS_JDISINT, {"a5": 0, "_pokes": channel_arg(CHANNEL_ACIA)}, glue)
    assert "io_seed=" in str(raised.value)


# ---- Mfpint: the vector store, and the slice ------------------------------------------------------

def vector_slot(channel):
    """`$100 + channel * 4` — the 68000 vector the MFP's base register ($40) puts the channel on."""
    return addrs.MFP_VECTOR_TABLE + channel * addrs.VECTOR_BYTES


@pytest.mark.parametrize("channel", CHANNELS)
def test_installing_a_vector_disables_the_channel_and_stores_the_handler(channel):
    """The slice, over all sixteen channels: `Jdisint`'s four stores, then the longword.

    The vector slot is read out of the ORACLE's write ledger rather than out of the final image, so
    a channel whose slot already held the handler is still a case about a store that happened.
    """
    info = run_install(channel, A_HANDLER)
    assert info["regs"]["hw_writes"] == [mfp.bit_cleared(reg, channel) for reg in DISABLE_ORDER], (
        "the vector install did not disable the channel first, which is the window it exists to "
        "close: an interrupt taken here reaches a handler address only half replaced")
    assert case.written_long(info, vector_slot(channel)) == A_HANDLER


def test_the_vector_goes_in_the_slot_the_mfp_s_base_vector_register_names():
    """$100, not $0 and not $40: the base vector register holds $40, so the channels are exception
    vectors $40..$4f and their longwords start a quarter of the way into the vector table. Channel 0
    and channel 15 are the two ends, and a reconstruction off by one table or one entry misses both.
    """
    for channel, expected in ((0, 0x100), (15, 0x13C)):
        info = run_install(channel, ANOTHER_HANDLER)
        assert vector_slot(channel) == expected
        assert case.written_long(info, expected) == ANOTHER_HANDLER


def test_the_snapshot_s_own_handlers_are_rom_addresses_and_are_replaced():
    """The slots really are the machine's live MFP vectors: the boot filled them with ROM routines,
    and this replaces one. A slot holding something else would mean `MFP_VECTOR_TABLE` names the
    wrong table and every case above would be about arbitrary RAM."""
    for channel in (CHANNEL_ACIA, CHANNEL_TIMER_C):
        installed = int.from_bytes(bytes(BASE_IMAGE[vector_slot(channel):
                                                    vector_slot(channel) + addrs.VECTOR_BYTES]),
                                   "big")
        assert addrs.ROM_BASE <= installed < addrs.ROM_BASE + addrs.ROM_BYTES, (
            f"MFP channel {channel}'s vector is {installed:#x}, not a ROM handler")
    info = run_install(CHANNEL_ACIA, A_HANDLER)
    assert case.written_long(info, vector_slot(CHANNEL_ACIA)) == A_HANDLER


def test_the_whole_of_mfpint_cannot_be_run_under_a_declared_map_and_this_is_why():
    """THE MEASUREMENT THE SLICE RESTS ON, so the limit is a red rather than a paragraph.

    `Mfpint`'s enable half re-reads IERA and IMRA — the two registers its disable half has already
    stored to — and the declared I/O map describes the byte a register held on ENTRY. The oracle
    counts such a read as STALE and `harness._vet_io_reads_are_declared` refuses the case; nothing
    the reconstruction does can make it honest, because the ORACLE's own read was served a byte the
    run had invalidated. What would unblock it is a WRITE-THROUGH arm of that map, in the kit.

    The counts are asserted exactly: two stale reads and no others, the first at IERA, which is the
    ROM's own order. If a future kit serves the read-back, this case reds and `run_install`'s slice
    can become an ordinary whole-function differential.
    """
    _final, _writes, o_regs = emu.run(make_image(channel_arg(CHANNEL_TIMER_B, A_HANDLER)),
                                      addrs.XBIOS_MFPINT, {"a5": 0}, io_seed=mfp.seed())
    assert o_regs["io_stale_reads"] == 2, (
        f"Mfpint now makes {o_regs['io_stale_reads']} stale read(s) — the slice's premise has moved")
    assert o_regs["io_stale_first"] == addrs.MFP_IERA
    with pytest.raises(AssertionError, match="already STORED to"):
        def glue(lib, buf):
            lib.mfp_install_vector(buf, CHANNEL_TIMER_B, A_HANDLER)
        differential(addrs.XBIOS_MFPINT, {"a5": 0, "_pokes": channel_arg(CHANNEL_TIMER_B, A_HANDLER)},
                     glue, io_seed=mfp.seed())


# ---- and `xbios_mfpint` itself, which only the CANDIDATE can be made to run ----------------------

def run_mfpint_candidate_only(channel, handler, declared=None):
    """`xbios_mfpint` end to end on the reconstruction alone. THERE IS NO ORACLE SIDE TO THIS.

    The case above measures why: the ROM's own `Mfpint` cannot be carried past `$fc267a` under a
    declared map, so there is no D0, no image and no ledger from the original to compare against.
    What is left is a COMPOSITION claim — that the whole is the two halves the oracle DID verify,
    run back to back — and that is what the cases below make. Every expectation they use comes from
    `mfp.py`'s own arithmetic or from a slice the oracle verified, never from this run.
    """
    def call(lib, buf):
        assert lib.xbios_mfpint(buf, channel & 0xFFFF, handler) == (channel & addrs.MFP_CHANNEL_MASK)

    return mfp.candidate_only(call, pokes=channel_arg(channel, handler), declared=declared)


@pytest.mark.parametrize("channel", CHANNELS)
def test_mfpint_is_the_disable_the_store_and_the_enable_in_that_order(channel):
    """CANDIDATE-ONLY. The four writes `run_install`'s verified slice makes, then the two
    `run_enabint`'s verified case makes — one stream, in the ROM's order.

    A composition is the one thing a slice leaves open: `Jdisint`'s body and `Jenabint`'s body are
    each proved at their own entry over all sixteen channels, and what is NOT proved by either is
    that `Mfpint` performs both, on the same channel, disable first. The ROM's own `bsr` targets say
    it does — decoded out of the mapped image by the two cases below — and this says the
    reconstruction agrees.
    """
    info = run_mfpint_candidate_only(channel, A_HANDLER)
    assert info["hw_writes"] == ([mfp.bit_cleared(reg, channel) for reg in DISABLE_ORDER]
                                 + [mfp.bit_set(reg, channel) for reg in ENABLE_ORDER])
    assert info["io_events"] == ([mfp.read(reg, channel) for reg in DISABLE_ORDER]
                                 + [mfp.read(reg, channel) for reg in ENABLE_ORDER])


def test_mfpint_s_enable_half_reads_back_what_its_disable_half_wrote():
    """CANDIDATE-ONLY, and it is the same fact the ORACLE's refusal above reports.

    The declared map serves the byte a register held on ENTRY, so the reconstruction's enable half
    is handed the same IERA and IMRA its disable half already cleared a bit of — which is why the
    two `bset` values below are the DECLARED bytes with a bit set, and not the bytes the two `bclr`
    stores left. That is a statement about the MODEL, not about the machine: on a real MFP the
    read-back would see the cleared bit. Asserted so the bound is a case rather than a paragraph —
    if a future write-through arm of the map lands, this reds and the whole routine becomes an
    ordinary differential.
    """
    channel = CHANNEL_TIMER_B
    writes = run_mfpint_candidate_only(channel, A_HANDLER)["hw_writes"]
    enable_reads = [mfp.read(reg, channel) for reg in ENABLE_ORDER]
    assert writes[len(DISABLE_ORDER):] == \
        [(reg, width, value | (1 << mfp.bit_of(channel))) for reg, width, value in enable_reads]


@pytest.mark.parametrize("channel", (0, CHANNEL_ACIA, 15))
def test_mfpint_stores_the_vector_between_the_two_halves(channel):
    """CANDIDATE-ONLY. The longword goes in `$100 + channel * 4`, which is the one effect of
    `Mfpint` that IS in memory — so it is read out of the image the candidate ran on rather than out
    of a ledger, and a run that stored it anywhere else leaves the slot holding the boot's handler.
    """
    image = run_mfpint_candidate_only(channel, ANOTHER_HANDLER)["image"]
    slot = vector_slot(channel)
    assert int.from_bytes(image[slot:slot + addrs.VECTOR_BYTES], "big") == ANOTHER_HANDLER


def test_there_is_no_tier_3_row_for_mfpint_and_this_is_why():
    """...so the gap in `bench/tier3.py` is a case rather than an omission somebody has to notice.

    A Tier 3 row runs the ORIGINAL's machine code beside our m68k build and compares both (
    `rom_bench.RomBench.measure`), and `Mfpint`'s cannot be run: `VERIFIED_CASES` carries no entry
    for `XBIOS_MFPINT`, because the only case this file has at that address is the `stop_pc` slice
    above and a slice has no `rts` to measure to. The routine's COST is therefore unmeasured; what
    is measured is both of its halves, at `xbios_jdisint` and `xbios_jenabint`.
    """
    import test_boot_snapshot                     # the register of verified cases (bench/tier3.py)

    entries = {entry for _label, entry, _regs, _pokes, _psg, _io in test_boot_snapshot.VERIFIED_CASES}
    assert addrs.XBIOS_MFPINT not in entries, (
        "Mfpint now has a verified case, so it can carry a Tier 3 row — add its CALL entry")
    assert {addrs.XBIOS_JDISINT, addrs.XBIOS_JENABINT} <= entries


def test_the_enable_half_of_mfpint_is_jenabint_s_own_body():
    """...and what pins the half the slice does not reach: it is not a copy, it is the same bytes.

    `Mfpint` ends `bsr.s $fc26c6`, and `$fc26c6` is the instruction after `Jenabint`'s own argument
    fetch — so the enable `Mfpint` performs is the code `test_enabling_...` above runs sixteen times
    at `Jenabint`'s entry. Read out of the mapped ROM, so a wrong address in `addrs.h` reds here.
    """
    at = addrs.MFPINT_ENABLE_HALF
    bsr_short = BASE_IMAGE[at]
    # SIGNED: a `bsr.s` displacement is an `int8_t`, so a backwards call — which this one is not,
    # and which a moved routine could make it — must decode as a negative rather than as $80..$ff.
    displacement = int.from_bytes(bytes(BASE_IMAGE[at + 1:at + 2]), "big", signed=True)
    assert bsr_short == BSR_SHORT_OPCODE, "Mfpint's last instruction is not a short `bsr`"
    target = at + BSR_SHORT_BYTES + displacement
    jenabint_body = addrs.XBIOS_JENABINT + JENABINT_ARGUMENT_FETCH_BYTES
    assert target == jenabint_body, (
        f"Mfpint calls {target:#x}, which is not Jenabint's body at {jenabint_body:#x}")


# `bsr.s` and its own length, so the case above reads as the decode it is rather than as two
# literals; the displacement is relative to the instruction AFTER it, which is what the 2 is.
BSR_SHORT_OPCODE, BSR_SHORT_BYTES = 0x61, 2
# `move.w 4(sp),d0` (4 bytes) + `andi.l #15,d0` (6) — what `Jenabint` does before the body `Mfpint`
# enters, and what `Mfpint` has already done for itself.
JENABINT_ARGUMENT_FETCH_BYTES = 10


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominators for these rows, measured rather than estimated."""
    costs = {}
    for label, entry, pokes in (("jdisint", addrs.XBIOS_JDISINT, channel_arg(CHANNEL_TIMER_C)),
                                ("jenabint", addrs.XBIOS_JENABINT, channel_arg(CHANNEL_TIMER_C))):
        _final, _writes, regs = emu.run(make_image(pokes), entry, {"a5": 0}, io_seed=mfp.seed())
        costs[label] = (regs["ninsns"], regs["cycles"])
    assert costs == {"jdisint": (39, 514), "jenabint": (23, 346)}, (
        f"the MFP interrupt routines now cost {costs} — STATUS.md's Tier 3 denominators are stale")
