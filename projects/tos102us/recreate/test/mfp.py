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
from harness import _lib, addrs, arm_candidate, candidate_image, emu, make_image

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


# The timers' DATA registers — the reload latch a programmer writes and reads back. Separate again
# because only the timer programmer reaches them, and because they are the sharpest instance of the
# claim below: a data register reads back what was stored only while the timer is STOPPED.
TIMER_DATA_REGISTERS = {
    addrs.MFP_TADR: 0x1A, addrs.MFP_TBDR: 0xB2, addrs.MFP_TCDR: 0xC3, addrs.MFP_TDDR: 0xD4,
}

# The three tables above are keyed by REGISTER, because a declaration is about an address. The three
# below are the same registers keyed by TIMER, because the programmer is: it indexes every one of its
# tables by the timer number, and timers C and D share a control byte, so "which register" is a
# function of the timer and not a set.

# THE FOUR TIMERS, as the ROM's own tables describe them — spelt here because both the timer
# programmer's battery and `Rsconf`'s baud arm compose an expectation out of them, and because every
# one of these is checked against the mapped ROM by `test_xbios_xbtimer.py` rather than trusted.
TIMER_CHANNELS = (13, 8, 5, 4)                 # `$fc302a`: which MFP channel each timer raises
# ...and each timer's CONTROL register with the mask that clears just its own field. A and B own a
# byte each; C and D share one, which is the whole reason the programmer is table-driven.
TIMER_CONTROL_OF = (addrs.MFP_TACR, addrs.MFP_TBCR, addrs.MFP_TCDCR, addrs.MFP_TCDCR)
TIMER_CONTROL_MASK_OF = (0x00, 0x00, 0x8F, 0xF8)
# ...and its DATA register, the reload latch the programmer writes and reads back.
TIMER_DATA_OF = (addrs.MFP_TADR, addrs.MFP_TBDR, addrs.MFP_TCDR, addrs.MFP_TDDR)

# WHICH OF THOSE REGISTERS THE CASES CLAIM LATCH A STORE AND READ IT BACK (TRAP_MODEL.md, Phase 15,
# "The write-through arm"). It is a claim about the 68901 and it is this project's to get right:
#
#   * the MASK and ENABLE pairs are latches outright — `Mfpint`'s enable half re-reads the IERA and
#     IMRA its disable half wrote, and on the chip it sees the cleared bit;
#   * so are the timer CONTROL registers, which the programmer clears and then re-reads to OR the
#     caller's control bits into ($fc261a's `or.b d1,(a3)`);
#   * and so is a timer's DATA register — BUT ONLY BECAUSE THE TIMER IS STOPPED when the programmer
#     writes it. The five clears run first and the fifth zeroes the timer's own control field, which
#     on a 68901 stops it; a running timer's data register reads the live down-counter instead, and
#     the claim would be false. `test_xbios_xbtimer.py` pins that order out of the ROM.
#
# PENDING and IN-SERVICE ARE THE NARROW ONES, AND THEY ARE HERE BECAUSE `Xbtimer` READS THEM BACK.
# Its programmer clears the timer's channel in all four pairs with `and.b mask,(reg)`, and the
# `Mfpint` body it then calls clears the SAME channel again with `bclr d1,(a1)` — whose read half is
# of a register this run has already written. On the chip those two registers are WRITE-TO-CLEAR: a
# 0 bit drops the channel's request and a 1 bit is IGNORED, so a read-back is the chip's state and
# not, in general, the byte stored. It is the byte stored here for a reason that is the ROM's own
# instruction rather than the register's: every store these routines make is `read & mask`, a pure
# clear, so every 1 bit written was already 1 in the byte read and every 0 bit clears. The claim
# would be FALSE for a store that SET a bit of one of these (the chip would ignore it and the
# read-back would differ), and it is false on a live machine the moment a new request arrives between
# the write and the read — which is the same "quiescent chip" assumption every declared byte here
# rests on. TRAP_MODEL.md, "Phase 15" ("The honest limit of a write-through byte") carries it.
WRITE_THROUGH_REGISTERS = frozenset({
    addrs.MFP_IERA, addrs.MFP_IERB, addrs.MFP_IMRA, addrs.MFP_IMRB,
    addrs.MFP_IPRA, addrs.MFP_IPRB, addrs.MFP_ISRA, addrs.MFP_ISRB,
    addrs.MFP_TACR, addrs.MFP_TBCR, addrs.MFP_TCDCR,
    *TIMER_DATA_REGISTERS,
})

# ...and the entry byte of every register a case may declare, in one table, so `seed` and the
# expected-ledger helpers below read the same claim.
ENTRY_BYTES = {**INTERRUPT_REGISTERS, **TIMER_CONTROL_REGISTERS, **TIMER_DATA_REGISTERS}


def seed(overrides=None):
    """The declaration a case passes as `io_seed`: every register above, plus anything it names.

    `overrides` is a dict rather than keywords because its keys are ADDRESSES: `mfp.seed({MFP_IERA:
    0xff})` reads as the declaration it is, where a keyword form would need a second set of names
    for the registers `addrs.h` has already named once. Its values are plain BYTES — the marking is
    this function's, out of `WRITE_THROUGH_REGISTERS`, so a case that overrides an entry byte cannot
    accidentally change what the project claims about the register.
    """
    declared = {**ENTRY_BYTES, **(overrides or {})}
    return {address: emu.write_through(byte) if address in WRITE_THROUGH_REGISTERS else byte
            for address, byte in declared.items()}


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


# The two orders that ARE the behaviour, spelt once because three routines walk them: `Jdisint`'s
# body, `Mfpint` (which calls it), and the timer programmer's five clears, whose first four are these
# four registers for the timer's own channel. Disabling goes mask, enable, pending, in-service — the
# channel is masked off before it is disarmed, so nothing can be latched in the window; enabling goes
# the other way, so the channel is armed before it is unmasked.
DISABLE_ORDER = (addrs.MFP_IMRA, addrs.MFP_IERA, addrs.MFP_IPRA, addrs.MFP_ISRA)
ENABLE_ORDER = (addrs.MFP_IERA, addrs.MFP_IMRA)


class Chip:
    """The MFP's registers as a CASE declares them, so a COMPOSITE routine's expected ledgers are
    computed from the declaration rather than listed by hand.

    The stateless helpers above are enough while a routine touches each register once — every case
    at `Jdisint`'s or `Jenabint`'s own entry. They are not enough for a routine that writes a
    register and then READS IT BACK, which is what the declared map's write-through arm now serves:
    `Mfpint`'s enable half is handed the IERA and IMRA its disable half cleared a bit of, and the
    timer programmer's `or.b d1,(a3)` is handed the control byte its own clear just wrote. What the
    second read is served depends on what the first write left, so the expectation has to be walked.

    IT IS NOT THE RECONSTRUCTION'S ARITHMETIC. What it models is the DECLARATION — which registers
    the case claims latch a store (`WRITE_THROUGH_REGISTERS`) and what each held on entry — and the
    caller still spells the registers, the order and the bit itself, which is the claim about the
    ROM. A case that asked the core which register it meant would agree with any answer.
    """

    def __init__(self, declared=None):
        self.held = dict(ENTRY_BYTES if declared is None else declared)
        self.reads = []      # the (address, width, value) stream `io_events` should hold...
        self.writes = []     # ...and the one `hw_writes` should

    def read(self, register):
        """`move.b (a1),d` — served the byte the register holds NOW, and ledgered."""
        value = self.held[register]
        self.reads.append((register, 1, value))
        return value

    def write(self, register, value):
        """...and the store, which a WRITE-THROUGH register latches for the next read of it."""
        self.writes.append((register, 1, value))
        if register in WRITE_THROUGH_REGISTERS:
            self.held[register] = value

    def change_bit(self, register, bit, set_it):
        """`bset`/`bclr d1,(a1)` — a read of the register and a store of the modified byte."""
        held = self.read(register)
        self.write(register, held | 1 << bit if set_it else held & ~(1 << bit) & 0xFF)

    def keep_bits(self, register, mask):
        """...and `and.b d3,(a3)`, the timer programmer's shape: keep the bits `mask` names."""
        self.write(register, self.read(register) & mask)

    def set_bits(self, register, bits):
        """...and `or.b d1,(a3)`, which is how the control bits go in after the data register."""
        self.write(register, self.read(register) | bits)

    def disable_channel(self, channel):
        """`$fc268c` — `Jdisint`'s body over one channel, in the ROM's order."""
        for register_a in DISABLE_ORDER:
            self.change_bit(register_of(register_a, channel), bit_of(channel), set_it=False)

    def enable_channel(self, channel):
        """...and `$fc26c6`, `Jenabint`'s, in the other one."""
        for register_a in ENABLE_ORDER:
            self.change_bit(register_of(register_a, channel), bit_of(channel), set_it=True)

    def program_timer(self, timer, control, data):
        """`$fc25b0` — the shared timer programmer, from the disassembly rather than from the tables.

        Five clears, then the data register written and read back, then the control bits ORed in:

          * the first four clears are `Jdisint`'s own four registers for the TIMER's channel, in
            `Jdisint`'s own order — which is the identity the ROM's four offset tables encode, so
            they are spelt by CALLING `disable_channel` rather than by a loop of their own: the
            claim is "the programmer's first four clears ARE Jdisint over this timer's channel", and
            a second copy of that loop here would assert it of itself;
          * the fifth is the timer's CONTROL register, masked so that only its own field goes. For
            timers C and D that byte is shared, so the mask keeps the other timer's three bits;
          * the data register is then written and READ BACK once, which is the whole loop when the
            register latches — and it does, because the clear above stopped the timer;
          * and `or.b d1,(a3)` re-reads the control register the clear wrote, and puts the caller's
            control bits into it.
        """
        self.disable_channel(TIMER_CHANNELS[timer])
        self.keep_bits(TIMER_CONTROL_OF[timer], TIMER_CONTROL_MASK_OF[timer])
        self.write(TIMER_DATA_OF[timer], data)
        self.read(TIMER_DATA_OF[timer])
        self.set_bits(TIMER_CONTROL_OF[timer], control)


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
