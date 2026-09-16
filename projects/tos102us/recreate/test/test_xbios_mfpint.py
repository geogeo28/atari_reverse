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

AND WHAT A `write_through` DECLARATION ADDS, which is what makes `Mfpint` a whole differential.
`Mfpint`'s enable half RE-READS the IERA and IMRA its disable half has already written. A declaration
describing only the chip on ENTRY could not serve that — the oracle counted two stale reads, the
first at `$fffa07`, and `harness._vet_io_reads_are_declared` refused the case, so the routine used to
be proved as a slice with its enable half pinned only by address identity with `Jenabint`. The mask
and enable pairs are LATCHES, so `mfp.seed()` declares them write-through (TRAP_MODEL.md, Phase 15)
and the second read is served the byte the first write left, on both shores. `mfp.Chip` is where this
file computes what that comes to, independently of the core.

WHAT THAT DOES AND DOES NOT MOVE: the bytes STORED are unchanged — clearing a bit and then setting
the same bit gives the entry byte with the bit set either way — so what the arm buys is the READ
stream, and the composition claim it carries. There are no candidate-only cases left in this file.
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
    """`Mfpint`'s first half on its own: `[$fc2658, $fc267a)`, up to the enable's `bsr`.

    Kept as a `stop_pc` case now that the whole routine runs, because it is the one instant at which
    the vector slot has been replaced and the channel is still OFF — which is the window the disable
    exists to open, and the only place a case can compare the image in it.
    """
    def glue(lib, buf):
        lib.mfp_install_vector(buf, channel & 0xFFFF, handler)

    return case.run(addrs.XBIOS_MFPINT, {"a5": 0, "_pokes": channel_arg(channel, handler)}, glue,
                    width=case.NO_RESULT, poison=poison, stop_pc=addrs.MFPINT_ENABLE_HALF,
                    io_seed=io_seed or mfp.seed())


def run_mfpint(channel, handler, io_seed=None, poison=True):
    """...and the whole of it, entered at `$fc2658`: the argument fetch, the disable, the vector
    store and the enable."""
    def glue(lib, buf):
        return lib.xbios_mfpint(buf, channel & 0xFFFF, handler)

    return case.run(addrs.XBIOS_MFPINT, {"a5": 0, "_pokes": channel_arg(channel, handler)}, glue,
                    poison=poison, io_seed=io_seed or mfp.seed())


# ---- the two register pairs' order, which is the behaviour ---------------------------------------
# `mfp.py`'s, because the timer programmer's five clears walk the same four registers for the timer's
# own channel and the two batteries may not hold two ideas of what that order is.

DISABLE_ORDER, ENABLE_ORDER = mfp.DISABLE_ORDER, mfp.ENABLE_ORDER


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


# ---- Mfpint: the slice, and then the whole routine -------------------------------------------

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


def mfpint_chip(channel, declared=None):
    """What `mfp.Chip` says `Mfpint` should leave: the disable, then the enable, on one channel.

    Composed out of the two bodies' own orders rather than out of the core, so the composition claim
    — that `Mfpint` performs BOTH, on the same channel, disable first — is this file's and not the
    reconstruction's. The ROM's own `bsr` targets are what say it does, and the two decode cases at
    the bottom of this file read them out of the mapped image.
    """
    chip = mfp.Chip(declared)
    chip.disable_channel(channel)
    chip.enable_channel(channel)
    return chip


@pytest.mark.parametrize("channel", CHANNELS)
def test_mfpint_is_the_disable_the_store_and_the_enable_in_that_order(channel):
    """The whole routine, over all sixteen channels: four `bclr` stores, the vector longword, then
    two `bset` stores — one ordered stream, against the ORIGINAL's own.

    This is what the write-through arm bought. A composition is the one thing a slice leaves open —
    `Jdisint`'s body and `Jenabint`'s are each proved at their own entry, and neither says that
    `Mfpint` performs both on the same channel, disable first — and until the enable half's two
    re-reads could be served there was no original run to compare against at all.
    """
    info = run_mfpint(channel, A_HANDLER)
    chip = mfpint_chip(channel)
    assert info["regs"]["hw_writes"] == chip.writes
    assert info["regs"]["io_events"] == chip.reads
    assert case.written_long(info, vector_slot(channel)) == A_HANDLER


def test_mfpint_s_enable_half_is_served_what_its_disable_half_wrote():
    """THE READ-BACK ITSELF, asserted as the two bytes it is rather than through the model.

    The enable half re-reads IERA and IMRA. With the registers declared write-through it is served
    the bytes the disable half's two `bclr` stores left — the entry byte with the channel's bit
    CLEARED — where a declaration describing only the machine on entry would have served the entry
    byte itself, and the oracle would have counted two stale reads.

    Spelt from `mfp.INTERRUPT_REGISTERS` and the bit, so it is a claim about the chip rather than a
    re-run of `mfp.Chip`: this is the case that would red if the arm stopped latching.
    """
    channel = CHANNEL_TIMER_B
    info = run_mfpint(channel, A_HANDLER)
    bit = 1 << mfp.bit_of(channel)
    expected = [(mfp.register_of(register_a, channel), 1,
                 mfp.INTERRUPT_REGISTERS[mfp.register_of(register_a, channel)] & ~bit & 0xFF)
                for register_a in ENABLE_ORDER]
    assert info["regs"]["io_events"][len(DISABLE_ORDER):] == expected, (
        "the enable half was not served the bytes the disable half wrote — the declared map's "
        "write-through arm is not reaching these registers")
    assert info["regs"]["io_stale_reads"] == 0, (
        "the oracle still counts the read back as STALE, so `_vet_io_reads_are_declared` is one "
        "change away from refusing every case in this file")


@pytest.mark.parametrize("argument,channel", ALIASED_ARGUMENTS)
def test_the_whole_routine_masks_its_argument_and_returns_the_masked_channel(argument, channel):
    """`andi.l #15,d0` at `Mfpint`'s own entry, and the D0 its `movem.l (sp)+` restores — the same
    pair `Jdisint` and `Jenabint` are pinned on, now that the whole routine runs. `Mfpint($fffd)`
    installs on channel 13 and hands 13 back; `Xbtimer` is what enters PAST this mask."""
    info = run_mfpint(argument, ANOTHER_HANDLER, poison=False)
    assert info["ret"] == channel
    assert case.written_long(info, vector_slot(channel)) == ANOTHER_HANDLER
    assert info["regs"]["hw_writes"] == mfpint_chip(channel).writes


@pytest.mark.parametrize("held", LOADED_REGISTERS)
def test_the_whole_routine_preserves_the_bits_it_does_not_name(held):
    """...and the declared read made load-bearing over the COMPOSITION, which is where it is easiest
    to get wrong: the enable half's `bset` must merge into the byte the disable half's `bclr` left,
    not into the byte the case declared. With `$ff` held the two bytes differ in exactly the
    channel's bit, which is the smallest thing that separates them."""
    declared = {register: held for register in mfp.INTERRUPT_REGISTERS}
    info = run_mfpint(CHANNEL_TIMER_C, A_HANDLER, io_seed=mfp.seed(declared), poison=False)
    chip = mfpint_chip(CHANNEL_TIMER_C, declared)
    assert info["regs"]["hw_writes"] == chip.writes
    assert info["regs"]["io_events"] == chip.reads


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
