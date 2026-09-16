"""The MFP 68901 as a case declares it: which register a channel's bit lives in, and what to seed.

Two batteries need this — the interrupt routines' (`test_xbios_mfpint.py`) and the timer
programmer's (`test_xbios_xbtimer.py`) — and both need the same two things: a declaration of what
the chip's registers held on entry, and the independent arithmetic to say which byte a given channel
should have changed. Spelt here rather than twice, so the two cannot drift.

THE SEED IS A DISTINCT BYTE PER REGISTER, and that is the whole reason it is a table rather than a
constant: eight registers seeded alike would let a reconstruction that cleared the right bit of the
WRONG register produce the right byte. Each byte below also has a mix of set and clear bits, so
clearing a bit that was already clear — or setting one already set — is separable from doing nothing.
"""
from harness import _lib, addrs, arm_candidate, candidate_image, make_image

# The four interrupt-register PAIRS the three interrupt routines walk, in the ROM's own displacement
# order off `$fffa01`, with a distinct entry byte each.
INTERRUPT_REGISTERS = {
    addrs.MFP_IERA: 0x5A, addrs.MFP_IERB: 0xA5,
    addrs.MFP_IPRA: 0x3C, addrs.MFP_IPRB: 0xC3,
    addrs.MFP_ISRA: 0x0F, addrs.MFP_ISRB: 0xF0,
    addrs.MFP_IMRA: 0x69, addrs.MFP_IMRB: 0x96,
}

# ...and the timer control registers, which the timer programmer clears as well. Separate because
# the interrupt routines never touch them, and a declaration is a claim about what the run READS.
TIMER_CONTROL_REGISTERS = {
    addrs.MFP_TACR: 0x17, addrs.MFP_TBCR: 0x71, addrs.MFP_TCDCR: 0x77,
}


def seed(overrides=None):
    """The declaration a case passes as `io_seed`: every register above, plus anything it names.

    `overrides` is a dict rather than keywords because its keys are ADDRESSES: `mfp.seed({MFP_IERA:
    0xff})` reads as the declaration it is, where a keyword form would need a second set of names
    for the registers `addrs.h` has already named once.
    """
    return {**INTERRUPT_REGISTERS, **TIMER_CONTROL_REGISTERS, **(overrides or {})}


def in_register_a(channel):
    """`move.b d0,d1 / cmpi.b #8,d1 / blt.s` — the ROM's `$fc26e6`, written independently.

    Channels 8..15 are the A register's bits and 0..7 are the B register's, which sits two bytes
    above it. Spelt as the comparison the ROM makes rather than by calling the reconstruction's own
    helper: a case that asked the core which register it meant would agree with any answer.

    AND THE COMPARE IS SIGNED, over the low BYTE. Over the sixteen channels an `andi.l #15` can
    produce that makes no difference at all, which is why every case at `Jdisint`'s own entry reads
    the same either way; it decides the answer only for `Xbtimer`, which enters the same subroutine
    with an unmasked table byte (`test_xbios_xbtimer.py`, the raw-byte cases).
    """
    low_byte = channel & 0xFF
    return (low_byte - 0x100 if low_byte >= 0x80 else low_byte) >= addrs.MFP_CHANNELS_PER_HALF


def register_of(register_a, channel):
    """Which half of a register PAIR holds `channel`, given the pair's "A" half."""
    return register_a if in_register_a(channel) else register_a + addrs.MFP_HALF_B_STEP


def bit_of(channel):
    """...and which bit of it: the channel itself, or the channel less eight — and then `bclr`'s own
    bound, because a bit number on a MEMORY destination is modulo 8."""
    bit = channel - addrs.MFP_CHANNELS_PER_HALF if in_register_a(channel) else channel
    return bit & addrs.MFP_BIT_NUMBER_MASK


def bit_cleared(register_a, channel, declared=None):
    """`(address, 1, value)` — the ledger entry a `bclr` of `channel` in this pair should leave."""
    declared = INTERRUPT_REGISTERS if declared is None else declared
    reg = register_of(register_a, channel)
    return (reg, 1, declared[reg] & ~(1 << bit_of(channel)) & 0xFF)


def bit_set(register_a, channel, declared=None):
    """...and the one a `bset` should leave."""
    declared = INTERRUPT_REGISTERS if declared is None else declared
    reg = register_of(register_a, channel)
    return (reg, 1, declared[reg] | (1 << bit_of(channel)))


def read(register_a, channel, declared=None):
    """...and the READ that preceded either: the byte the case declared, at the same address."""
    declared = INTERRUPT_REGISTERS if declared is None else declared
    reg = register_of(register_a, channel)
    return (reg, 1, declared[reg])


# ---- running the CANDIDATE with no oracle beside it ---------------------------------------------
#
# TWO CLAIMS IN THIS PAIR OF BATTERIES HAVE NO ORACLE SIDE AT ALL, and both are about code the ROM
# reaches only by falling into a register read-back the declared I/O map refuses (`src/xbios/mfp.c`
# and `src/xbios/xbtimer.c` carry the measurements): the whole of `Mfpint`, and the raw channel byte
# `Xbtimer` hands `Mfpint`'s body. What a case CAN still do is run the reconstruction on its own and
# compare what it did against what the ROM's instructions say — which is a weaker thing than a
# differential and is labelled as such at every assertion that uses it.
#
# It is deliberately NOT a second differential in disguise: the expected ledgers below are composed
# out of slices the ORACLE did verify (`run_install`'s four writes, `run_enabint`'s two) or computed
# from the disassembly, never from the core being run.


def _candidate_ledger(count_of, columns_of):
    """One of the candidate's ordered ledgers, out of the parallel C arrays `src/hw.c` exports —
    `[(address, width, value), ...]`, which is the shape the oracle reports its own in."""
    count = count_of()
    columns = [column() for column in columns_of]
    return [tuple(column[i] for column in columns) for i in range(count)]


def candidate_only(call, pokes=None, declared=None):
    """Run `call(lib, buf)` on a freshly armed candidate and report what it did, with no oracle.

    Returns `{"image", "ret", "hw_writes", "io_events"}` in the shapes `harness.differential`'s
    `info` reports the ORACLE's in, so a case can be written against one and read beside the other.
    """
    buf = candidate_image(make_image(pokes))
    arm_candidate(io_seed=seed() if declared is None else declared)
    returned = call(_lib, buf)
    # The same check `differential` makes of every candidate run: a refused `io_read8` answers a
    # sentinel and goes UNLEDGERED, so without this a case whose declaration was short would read as
    # a reconstruction that made fewer accesses rather than as a case that declared too little.
    assert _lib.g_os_refusal_count() == 0, (
        f"the candidate made {_lib.g_os_refusal_count()} refused os_* call(s) — this run proves "
        f"nothing; declare the addresses it read (`mfp.seed({{...}})`)")
    return {
        "image": bytes(buf),
        "ret": returned,
        "hw_writes": _candidate_ledger(_lib.g_hw_write_count,
                                       (_lib.g_hw_write_addrs, _lib.g_hw_write_widths,
                                        _lib.g_hw_write_vals)),
        "io_events": _candidate_ledger(_lib.g_io_log_count,
                                       (_lib.g_io_log_addrs, _lib.g_io_log_widths,
                                        _lib.g_io_log_vals)),
    }
