"""XBIOS Xbtimer (function $1f) @ $fc2ff2, and the MFP timer programmer at $fc25b0 it shares with
`Rsconf`'s baud arm.

`Xbtimer` is three steps: program one of the MFP's four timers, look its interrupt channel up in a
four-byte ROM table, and install a handler on it through `Mfpint`'s body. The programmer is the part
with the arithmetic in it, and it is table-driven — eight adjacent four-byte tables in the ROM,
every one indexed by the timer number.

WHAT THIS BATTERY PROVES is the programmer whole — the five CLEARS as a slice `[$fc25b0, $fc2600)`
and then `$fc25b0` to its `rts` — plus `Xbtimer` itself end to end, and the eight ROM tables the
routine indexes. The data-register write used to be out of reach: the 68901 needs a settling time on
those registers, so the ROM stores the byte and re-reads it until the chip agrees, and a declaration
describing what a register held on ENTRY could serve neither half of that (undeclared the loop never
ended; declared, the read back was refused as stale). A case declares the register WRITE-THROUGH now
(TRAP_MODEL.md, Phase 15) — which is TRUE of it because the fifth clear STOPS the timer first, and
a stopped timer's data register is a reload latch rather than the live counter. That order is pinned
below, because it is what the claim rests on.

THE FIVE CLEARS ARE `Jdisint` PLUS ONE, and the "plus one" is the whole reason the tables exist. The
four interrupt registers are cleared exactly as `Jdisint` clears them for the timer's own MFP
channel — same registers, same bits, same order — which this file asserts by computing them from the
CHANNEL rather than from the tables. The fifth is the timer's CONTROL register, and that one is not
a bit in a pair: timers A and B own a whole byte each and have it wiped, while timers C and D SHARE
`$fffa1d` and each clears only its own three bits. A reconstruction that wiped the shared byte for
timer D would stop the 200 Hz tick dead, and the only thing that separates the two is the value in
the hardware write ledger.

AND THE LAST SECTION IS STILL CANDIDATE-ONLY, for a different reason. `Xbtimer`'s `bsr.w $fc3024`
enters `Mfpint` at `$fc2666` — past its `andi.l #15,d0` — so the channel it installs on is the raw
byte out of `$fc302a`, unmasked and unbounded. The four REAL timers reach that through the whole
routine now and are differentials above; what stays candidate-only is the out-of-range shapes, where
the programmer would first index its own tables past their end and program a register that is not a
timer. Those cases compare the candidate's own ledger and image against arithmetic taken from the
disassembly, and every one of them says CANDIDATE-ONLY in its first line.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case
import mfp

_lib.mfp_timer_clear.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.mfp_timer_clear.restype = None
_lib.mfp_timer_program.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint16,
                                   ctypes.c_uint16]
_lib.mfp_timer_program.restype = None
_lib.xbios_xbtimer.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint16,
                               ctypes.c_uint16, ctypes.c_uint32]
_lib.xbios_xbtimer.restype = ctypes.c_uint32
_lib.mfp_install_vector_and_enable.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                                               ctypes.c_uint32]
_lib.mfp_install_vector_and_enable.restype = ctypes.c_uint32
_lib.xbtimer_install_handler.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16,
                                         ctypes.c_uint32]
_lib.xbtimer_install_handler.restype = ctypes.c_uint32

TIMERS = (addrs.MFP_TIMER_A, addrs.MFP_TIMER_B, addrs.MFP_TIMER_C, addrs.MFP_TIMER_D)
TIMER_IDS = ("A", "B", "C", "D")
# The four tables' worth of facts about the timers, from `test/mfp.py` — the MFP channel each raises
# (`$fc302a`), its control register and that register's clearing mask, and its data register. Every
# one of them is asserted against the mapped ROM below rather than taken on trust, and they are used
# here to compute the registers INDEPENDENTLY of the tables the reconstruction reads.
TIMER_CHANNELS = mfp.TIMER_CHANNELS
CONTROL_REGISTERS, CONTROL_MASKS = mfp.TIMER_CONTROL_OF, mfp.TIMER_CONTROL_MASK_OF
DATA_REGISTERS = mfp.TIMER_DATA_OF
# The order the programmer clears them in, which is `Jdisint`'s: mask, enable, pending, in-service.
CLEAR_ORDER = mfp.DISABLE_ORDER

A_CONTROL, A_DIVIDER = 0x07, 0x40      # a /200 prescaler field, and a reload count of 64
A_HANDLER = 0x0006_1234
# ...and a second pair, so every case below is driven at more than one control byte and divider: the
# 200 Hz tick's own setup ($fc0522 programs timer C with these). They differ from the pair above in
# every bit that matters — a different prescaler field AND a different reload count, which is what
# makes a case parametrized over the two of them able to separate the control byte from the divider.
# (Both dividers were $c0 until wave 4's review: a swap of the two arguments was invisible in every
# case that used this pair, since the byte written and the byte compared were the same number.)
ANOTHER_CONTROL, ANOTHER_DIVIDER = 0x50, 0xC0
CONTROL_VALUES = (A_CONTROL, ANOTHER_CONTROL, 0xFF, 0x00)


def run_clear(timer, io_seed=None, poison=True):
    """The programmer's five clears on their own: `[$fc25b0, $fc2600)`, up to the data write.

    Still a `stop_pc` case now that the whole routine runs, because this is the instant at which the
    timer is STOPPED and not yet reprogrammed — which is what makes the data register a latch, and
    therefore what the whole routine's write-through declaration rests on.
    """
    def glue(lib, buf):
        lib.mfp_timer_clear(buf, timer & 0xFFFF)

    return case.run(addrs.MFP_TIMER_PROGRAM,
                    {"a5": 0, "d0": timer, "d1": A_CONTROL, "d2": A_DIVIDER}, glue,
                    width=case.NO_RESULT, poison=poison, stop_pc=addrs.MFP_TIMER_DATA_WRITE,
                    io_seed=io_seed or mfp.seed())


def run_program(timer, control=A_CONTROL, data=A_DIVIDER, io_seed=None, poison=True):
    """...and the whole programmer, `$fc25b0` to its `rts`: the five clears, the data register
    written and read back until the 68901 agrees, and the control bits ORed in last.

    Its arguments are REGISTERS, which is how the two callers pass them (`bsr.w $fc25b0` with the
    timer in D0, the control byte in D1 and the divider in D2), and it leaves them alone: the
    `movem.l (sp)+,d0-d4/a0-a3` restores every one, so there is no result to compare and the C is
    `void`.
    """
    def glue(lib, buf):
        lib.mfp_timer_program(buf, timer & 0xFFFF, control, data)

    return case.run(addrs.MFP_TIMER_PROGRAM,
                    {"a5": 0, "d0": timer, "d1": control, "d2": data}, glue,
                    width=case.NO_RESULT, poison=poison, io_seed=io_seed or mfp.seed())


def run_xbtimer(timer, control=A_CONTROL, data=A_DIVIDER, vector=A_HANDLER, io_seed=None,
                poison=True):
    """...and `Xbtimer` itself, end to end: the programmer, the channel table, and the install."""
    def glue(lib, buf):
        return lib.xbios_xbtimer(buf, timer & 0xFFFF, control, data, vector)

    return case.run(addrs.XBIOS_XBTIMER,
                    {"a5": 0, "_pokes": xbtimer_frame(timer, control, data, vector)}, glue,
                    poison=poison, io_seed=io_seed or mfp.seed())


def program_chip(timer, control=A_CONTROL, data=A_DIVIDER, declared=None):
    """What `mfp.Chip` says the programmer should leave, walked from the disassembly."""
    chip = mfp.Chip(declared)
    chip.program_timer(timer, control, data)
    return chip


def xbtimer_frame(timer, control=A_CONTROL, data=A_DIVIDER, vector=A_HANDLER):
    return {abi.FIRST_ARG: struct.pack(">HHHI", timer & 0xFFFF, control, data, vector)}


@pytest.mark.parametrize("timer", TIMERS, ids=TIMER_IDS)
def test_the_four_interrupt_registers_are_cleared_as_jdisint_clears_the_timer_s_channel(timer):
    """The identity the tables encode, computed from the CHANNEL rather than read from them.

    Timer A is MFP channel 13, B is 8, C is 5 and D is 4 — so the registers and bits the programmer
    clears are the ones `mfp.register_of`/`mfp.bit_of` give, in `Jdisint`'s own order. Reading them
    out of the ROM's tables instead would agree with any table.
    """
    channel = TIMER_CHANNELS[timer]
    writes = run_clear(timer)["regs"]["hw_writes"]
    assert writes[:len(CLEAR_ORDER)] == [mfp.bit_cleared(reg, channel) for reg in CLEAR_ORDER]


@pytest.mark.parametrize("timer", TIMERS, ids=TIMER_IDS)
def test_the_control_register_is_cleared_with_the_mask_that_names_only_this_timer(timer):
    """THE PART THAT IS NOT A BIT IN A PAIR. Timers A and B have their whole control byte wiped
    ($00); timers C and D share `$fffa1d`, so C keeps bit 7 and bits 0-3 ($8f) and D keeps bits 3-7
    ($f8) — each clearing only its own three-bit field."""
    register, mask = CONTROL_REGISTERS[timer], CONTROL_MASKS[timer]
    assert run_clear(timer)["regs"]["hw_writes"][-1] == \
        (register, 1, mfp.ENTRY_BYTES[register] & mask)


def test_the_two_timers_that_share_a_control_byte_clear_different_halves_of_it():
    """...said as the comparison it is, because this is the case the shared byte exists for: C and D
    write the SAME address with DIFFERENT values, each preserving what the other set."""
    held = mfp.ENTRY_BYTES[addrs.MFP_TCDCR]
    c_write = run_clear(addrs.MFP_TIMER_C, poison=False)["regs"]["hw_writes"][-1]
    d_write = run_clear(addrs.MFP_TIMER_D, poison=False)["regs"]["hw_writes"][-1]
    assert c_write[0] == d_write[0] == addrs.MFP_TCDCR
    assert c_write[2] != d_write[2]
    assert c_write[2] == held & CONTROL_MASKS[addrs.MFP_TIMER_C]
    assert d_write[2] == held & CONTROL_MASKS[addrs.MFP_TIMER_D]


@pytest.mark.parametrize("timer", TIMERS, ids=TIMER_IDS)
def test_each_clear_reads_the_register_it_is_about_to_write(timer):
    """The read half of every `and.b d3,(a3)`, in order — which is what makes the masks provable at
    all. Without it both sides would compute from a fabricated 0 and a reconstruction that wiped
    every register would be indistinguishable from one that kept the right bits."""
    channel = TIMER_CHANNELS[timer]
    reads = [(address, value) for address, _width, value in run_clear(timer)["regs"]["io_events"]]
    expected = [(mfp.register_of(reg, channel), mfp.INTERRUPT_REGISTERS[
        mfp.register_of(reg, channel)]) for reg in CLEAR_ORDER]
    expected.append((CONTROL_REGISTERS[timer], mfp.ENTRY_BYTES[CONTROL_REGISTERS[timer]]))
    assert reads == expected


# ---- the eight ROM tables the routine indexes ----------------------------------------------------

ROM_TABLES = (
    (addrs.MFP_TIMER_IER_OFFSETS, bytes([0x06, 0x06, 0x08, 0x08])),
    (addrs.MFP_TIMER_IPR_OFFSETS, bytes([0x0A, 0x0A, 0x0C, 0x0C])),
    (addrs.MFP_TIMER_ISR_OFFSETS, bytes([0x0E, 0x0E, 0x10, 0x10])),
    (addrs.MFP_TIMER_IMR_OFFSETS, bytes([0x12, 0x12, 0x14, 0x14])),
    (addrs.MFP_TIMER_INTERRUPT_MASKS, bytes([0xDF, 0xFE, 0xDF, 0xEF])),
    (addrs.MFP_TIMER_CONTROL_OFFSETS, bytes([0x18, 0x1A, 0x1C, 0x1C])),
    (addrs.MFP_TIMER_CONTROL_MASKS, bytes([0x00, 0x00, 0x8F, 0xF8])),
    (addrs.MFP_TIMER_DATA_OFFSETS, bytes([0x1E, 0x20, 0x22, 0x24])),
)


@pytest.mark.parametrize("table,expected", ROM_TABLES)
def test_each_table_is_where_addrs_h_says_and_holds_what_it_says(table, expected):
    """Read out of the mapped ROM. The reconstruction indexes these in place, so a wrong address in
    `addrs.h` would make it read the neighbouring table and agree with itself."""
    assert bytes(BASE_IMAGE[table:table + addrs.MFP_TIMERS]) == expected


def test_the_tables_are_adjacent_which_is_what_an_out_of_range_timer_reads():
    """Eight four-byte tables in one run, so a timer of 4 reads the FIRST byte of the next table
    rather than whatever lies past a C array. That is why the reconstruction indexes the image."""
    ordered = [table for table, _ in ROM_TABLES]
    assert ordered == sorted(ordered)
    assert all(b - a == addrs.MFP_TIMERS for a, b in zip(ordered, ordered[1:])), (
        "the eight tables are no longer contiguous, so an out-of-range timer reads something else")


def test_the_channel_table_says_which_interrupt_each_timer_raises():
    """`$fc302a`, which `Xbtimer` indexes to decide which channel to install the handler on — and
    the independent source for `TIMER_CHANNELS` above, so the identity every case here rests on is
    read from the ROM rather than written down twice."""
    assert bytes(BASE_IMAGE[addrs.XBTIMER_CHANNEL_TABLE:
                            addrs.XBTIMER_CHANNEL_TABLE + addrs.MFP_TIMERS]) == \
        bytes(TIMER_CHANNELS)
    assert all(channel <= addrs.MFP_CHANNEL_MASK for channel in TIMER_CHANNELS)


# ---- the whole programmer, and the write-and-verify loop that used to stop it -------------------

@pytest.mark.parametrize("timer", TIMERS, ids=TIMER_IDS)
@pytest.mark.parametrize("control,data", ((A_CONTROL, A_DIVIDER),
                                          (ANOTHER_CONTROL, ANOTHER_DIVIDER)))
def test_the_programmer_writes_the_data_register_then_ors_the_control_bits_in(timer, control, data):
    """`$fc25b0` whole, over all four timers at two control/divider pairs.

    The five clears, then `.st: move.b d2,(a0,d3.w) / cmp.b (a0,d3.w),d2 / bne.s .st`, then
    `or.b d1,(a3)`. Both streams are walked from the disassembly by `mfp.Chip` — the four interrupt
    registers computed from the timer's CHANNEL, the control register and mask from the timer, the
    data register from the timer — so the tables the reconstruction indexes are not what says the
    expectation is right.
    """
    info = run_program(timer, control, data)
    chip = program_chip(timer, control, data)
    assert info["regs"]["hw_writes"] == chip.writes
    assert info["regs"]["io_events"] == chip.reads


@pytest.mark.parametrize("timer", TIMERS, ids=TIMER_IDS)
def test_the_data_register_is_written_and_then_read_back_exactly_once(timer):
    """THE LOOP'S SHAPE, which is the one thing only the ordered read stream can pin.

    The ROM stores the byte and re-reads it until the chip agrees; with the register declared
    WRITE-THROUGH it agrees on the first pass, so the ledger carries ONE store of the divider and
    ONE read of the same address serving it back. A reconstruction that read twice, that read before
    it stored, or that skipped the verify entirely leaves a different stream and touches no image
    byte at all — nothing else in the differential could see it.

    Asserted against the timer's own data register spelt in `addrs.h`, not against `mfp.Chip`, so
    this is the case that reds if the register or the count moves.
    """
    register = DATA_REGISTERS[timer]
    info = run_program(timer, data=ANOTHER_DIVIDER)
    stores = [entry for entry in info["regs"]["hw_writes"] if entry[0] == register]
    reads = [entry for entry in info["regs"]["io_events"] if entry[0] == register]
    assert stores == [(register, 1, ANOTHER_DIVIDER)], "the reload byte did not reach the latch"
    assert reads == [(register, 1, ANOTHER_DIVIDER)], (
        "the verify did not read back exactly once what the store left — the loop's shape is not "
        "the ROM's")
    assert info["regs"]["io_stale_reads"] == 0, (
        "the read back was counted STALE, so the data register is not declared write-through and "
        "`_vet_io_reads_are_declared` is one change away from refusing this case")


@pytest.mark.parametrize("control", CONTROL_VALUES)
def test_the_control_bits_are_ored_into_the_byte_the_clear_left(control):
    """`or.b d1,(a3)` on timer D, which is the case the OR exists for: `$fffa1d` is SHARED with
    timer C, so the clear kept C's three bits and this must merge into them rather than store.

    The read it makes is of a register the routine itself wrote three instructions earlier — the
    second demand site the write-through arm serves — so the byte it merges into is the MASKED entry
    byte and not the entry byte. A reconstruction that ORed into the declaration would set C's field
    back up on a machine that had just had it cleared.
    """
    timer = addrs.MFP_TIMER_D
    register = CONTROL_REGISTERS[timer]
    cleared = mfp.ENTRY_BYTES[register] & CONTROL_MASKS[timer]
    info = run_program(timer, control=control)
    control_traffic = [entry for entry in info["regs"]["hw_writes"] if entry[0] == register]
    assert control_traffic == [(register, 1, cleared), (register, 1, cleared | control)]
    assert [entry for entry in info["regs"]["io_events"] if entry[0] == register] == \
        [(register, 1, mfp.ENTRY_BYTES[register]), (register, 1, cleared)], (
        "the OR was not served the byte the clear wrote")


def test_the_programmer_stops_the_timer_before_it_writes_the_data_register():
    """WHY THE WRITE-THROUGH CLAIM IS TRUE HERE, as an order read off the run rather than a
    paragraph.

    A 68901 timer's data register is a reload LATCH while the timer is stopped and the live
    down-counter while it runs, so "it reads back what was stored" holds only in the first case. The
    ROM's own order is what puts it there: the fifth clear zeroes the timer's field of its control
    register — a control field of zero is a stopped timer — and only then is the data register
    written. If a future change moved the data write ahead of that clear, the declaration in
    `test/mfp.py` would become a false claim about the chip while every case above stayed green.
    """
    timer = addrs.MFP_TIMER_C
    writes = run_program(timer)["regs"]["hw_writes"]
    control, data = CONTROL_REGISTERS[timer], DATA_REGISTERS[timer]
    stopped_at = next(i for i, (address, _w, value) in enumerate(writes)
                      if address == control and value == mfp.ENTRY_BYTES[control] & CONTROL_MASKS[timer])
    written_at = next(i for i, (address, _w, _v) in enumerate(writes) if address == data)
    assert stopped_at < written_at, (
        "the data register is written before the timer's control field is cleared, so the register "
        "the case declares write-through is a running counter rather than a latch")


# ---- Xbtimer end to end --------------------------------------------------------------------------

@pytest.mark.parametrize("timer,channel", tuple(zip(TIMERS, TIMER_CHANNELS)))
def test_xbtimer_programs_the_timer_and_installs_on_the_channel_the_table_names(timer, channel):
    """The whole routine at its own entry: program the timer, look its channel up in `$fc302a`, and
    install the handler through `Mfpint`'s body — which is itself a disable, a vector store and an
    enable on that channel.

    One ordered stream against the ORIGINAL's, composed out of the programmer's walk and `Mfpint`'s,
    plus the vector longword in the image. This is the case the data-register loop was blocking.
    """
    info = run_xbtimer(timer)
    chip = program_chip(timer)
    chip.disable_channel(channel)
    chip.enable_channel(channel)
    assert info["regs"]["hw_writes"] == chip.writes
    assert info["regs"]["io_events"] == chip.reads
    assert case.written_long(info, addrs.MFP_VECTOR_TABLE + channel * addrs.VECTOR_BYTES) \
        == A_HANDLER
    assert info["ret"] == channel, "Xbtimer did not return the channel Mfpint's body left in D0"


@pytest.mark.parametrize("control,data", ((A_CONTROL, A_DIVIDER), (ANOTHER_CONTROL, ANOTHER_DIVIDER)))
def test_xbtimer_with_a_negative_vector_programs_the_timer_and_installs_nothing(control, data):
    """`tst.l 10(sp)` / `bmi` — the arm that re-times an interrupt a caller has already hooked.

    Nothing after the programmer runs, so the stream is the programmer's exactly and D0 is still the
    timer the programmer's own `movem` restored.
    """
    timer = addrs.MFP_TIMER_B
    info = run_xbtimer(timer, control, data, vector=NEGATIVE_VECTOR)
    chip = program_chip(timer, control, data)
    assert info["regs"]["hw_writes"] == chip.writes
    assert info["regs"]["io_events"] == chip.reads
    assert info["ret"] == timer


def test_the_vector_install_is_mfpint_s_own_body_past_its_channel_mask():
    """What pins the half of `Xbtimer` past the halt, and the one thing about it that surprises.

    `Xbtimer` does not install a vector itself, it `bsr`s into `Mfpint` at `$fc2666` — which is past
    `move.w 4(sp),d0`, past `movea.l 6(sp),a2` AND PAST `andi.l #15,d0`. So the channel `Mfpint`'s
    body works on is whatever byte `Xbtimer` left in D0, unmasked; the mask `test_xbios_mfpint.py`
    exercises sixteen times belongs to the ENTRY the trap dispatcher uses and not to this path.
    Decoded out of the mapped ROM, and the `andi` is decoded too rather than counted in bytes: that
    is the instruction this case is really about.
    """
    at = XBTIMER_MFPINT_CALL
    opcode = int.from_bytes(bytes(BASE_IMAGE[at:at + 2]), "big")
    displacement = int.from_bytes(bytes(BASE_IMAGE[at + 2:at + 4]), "big", signed=True)
    assert opcode == BSR_WORD_OPCODE, "Xbtimer's last call is not a word `bsr`"
    target = at + BSR_WORD_OPCODE_BYTES + displacement
    assert target == addrs.XBIOS_MFPINT + MFPINT_ARGUMENT_FETCH_BYTES
    channel_mask = addrs.XBIOS_MFPINT + MFPINT_ARGUMENT_FETCH_BYTES - len(ANDI_L_15_D0)
    assert bytes(BASE_IMAGE[channel_mask:channel_mask + len(ANDI_L_15_D0)]) == ANDI_L_15_D0, (
        f"the instruction `Xbtimer` jumps over at {channel_mask:#x} is not `andi.l #15,d0`")
    assert target > channel_mask, "Xbtimer now enters Mfpint at or before its channel mask"


# `bsr.w` and the length of its opcode word, which the displacement that follows is relative to.
BSR_WORD_OPCODE, BSR_WORD_OPCODE_BYTES = 0x6100, 2
# `bsr.w $fc2666` — the last instruction of Xbtimer's vector arm...
XBTIMER_MFPINT_CALL = 0xFC3024
# ...and what Mfpint does before the body it enters: `move.w 4(sp),d0` (4 bytes), `movea.l 6(sp),a2`
# (4) and `andi.l #15,d0` (6). Xbtimer has done the first two for itself — a word argument and a
# handler longword — and has NOT done the third: its own mask is `andi.l #255,d0`, and what follows
# it is a table read whose byte nothing narrows again.
MFPINT_ARGUMENT_FETCH_BYTES = 14
ANDI_L_15_D0 = bytes([0x02, 0x80, 0x00, 0x00, 0x00, 0x0F])


# ---- the channel byte that mask would have narrowed, and what the ROM does with it instead -------
#
# CANDIDATE-ONLY, and what that means here has MOVED. The four real timers are differentials, up in
# "Xbtimer end to end": the write-through arm runs the data-register loop, so the whole routine has
# an ORIGINAL run to compare against and does. What has no original run is the OUT-OF-RANGE shapes
# below, and for a reason that is about the machine rather than about the harness — a timer past the
# table indexes the programmer's own offset tables past their end too, so the ORACLE programs a byte
# that is not a timer's data register, waits for it to read back what it stored, and never leaves the
# loop. So these compare the reconstruction's own ledger and image against arithmetic taken from the
# disassembly. Each assertion below says which side it is about, and the four-timer case among them
# is the cheap cross-check that the candidate-only door agrees with the differential next door.
#
# TIMER 4 IS THE ONE THE ROM'S OWN TABLE PRODUCES. `$fc302a` is four bytes long and nothing bounds
# the index, so a timer of 4 reads `$fc302e` — the first byte of the `tst.l 10(sp)` that follows —
# and hands `Mfpint`'s body a "channel" of $4a. $8a is SYNTHETIC: no timer reaches it, and it is here
# because it is the smallest thing that separates a signed byte compare from an unsigned one.
OUT_OF_RANGE_TIMER = 4
SYNTHETIC_NEGATIVE_CHANNEL = 0x8A
# ...and a vector argument the `tst.l 10(sp)` / `bmi` reads as "leave the handler alone".
NEGATIVE_VECTOR = 0xFFFF_FFFF


def run_install_candidate_only(channel):
    """`Mfpint`'s body over a channel byte, as `Xbtimer` would hand it one."""
    def call(lib, buf):
        assert lib.mfp_install_vector_and_enable(buf, channel, A_HANDLER) == channel

    return mfp.candidate_only(call)


def run_vector_arm_candidate_only(timer, vector=A_HANDLER):
    """...and the arm that CHOOSES the byte: the table read at `$fc3014` and the `bsr` at `$fc3024`,
    together. Reachable at a timer the oracle cannot run — see the section note above."""
    def call(lib, buf):
        return lib.xbtimer_install_handler(buf, timer & 0xFFFF, vector)

    return mfp.candidate_only(call)


def test_a_timer_past_the_table_reads_the_instruction_after_it():
    """THE ROM's SIDE: `$fc302e` holds $4a, so `Xbtimer(4, ...)` installs on "channel $4a".

    ...AND THE CANDIDATE'S: the vector arm really does carry that byte through to `Mfpint`'s body
    unmasked, which is the whole of what separates it from `xbios_mfpint`. $4a & 15 is 10, so a
    reconstruction that went through the masked door would report 10 here.
    """
    assert BASE_IMAGE[addrs.XBTIMER_CHANNEL_TABLE + OUT_OF_RANGE_TIMER] == 0x4A
    assert run_vector_arm_candidate_only(OUT_OF_RANGE_TIMER)["ret"] == 0x4A


@pytest.mark.parametrize("timer,channel", tuple(zip(TIMERS, TIMER_CHANNELS)))
def test_each_timer_installs_on_the_channel_the_table_names(timer, channel):
    """CANDIDATE-ONLY, over the four timers the table really is for: the arm reads `$fc302a` at the
    timer and hands `Mfpint`'s body what it found, so timer C installs on MFP channel 5."""
    assert run_vector_arm_candidate_only(timer)["ret"] == channel


def test_a_negative_vector_leaves_the_channel_alone_and_reports_the_timer():
    """CANDIDATE-ONLY. `tst.l 10(sp)` / `bmi` — the arm that programs the timer and installs no
    handler at all, which is how a caller re-times an interrupt it has already hooked. Nothing is
    read, nothing is stored, and D0 is still the timer the programmer's `movem` restored."""
    info = run_vector_arm_candidate_only(addrs.MFP_TIMER_C, vector=NEGATIVE_VECTOR)
    assert info["ret"] == addrs.MFP_TIMER_C
    assert info["hw_writes"] == [] and info["io_events"] == []


@pytest.mark.parametrize("channel", (0x4A, SYNTHETIC_NEGATIVE_CHANNEL))
def test_an_unmasked_channel_byte_picks_its_half_by_a_signed_compare(channel):
    """CANDIDATE-ONLY. $4a is 74 and lands in the A registers; $8a is NEGATIVE as an `int8_t` and
    lands in the B registers, where masking to four bits would have left it in A's. The bit is
    `bclr`'s own, which on a memory destination is modulo 8 — both of these come out as bit 2, and
    the ADDRESSES are what separate them."""
    writes = run_install_candidate_only(channel)["hw_writes"]
    assert writes == ([mfp.bit_cleared(reg, channel) for reg in CLEAR_ORDER]
                      + [mfp.bit_set(reg, channel) for reg in (addrs.MFP_IERA, addrs.MFP_IMRA)])
    in_a = channel == 0x4A
    assert all(address == reg + (0 if in_a else addrs.MFP_HALF_B_STEP)
               for (address, _width, _value), reg in zip(writes, CLEAR_ORDER))


@pytest.mark.parametrize("channel,slot", ((0x4A, 0x228), (SYNTHETIC_NEGATIVE_CHANNEL, 0x328)))
def test_an_unmasked_channel_byte_puts_the_vector_outside_the_mfp_s_sixteen_slots(channel, slot):
    """CANDIDATE-ONLY. `asl.w #2` then `addi.l #256` over the WHOLE byte: $4a * 4 + $100 is $228,
    which is exception vector $8a and not one of the MFP's $40..$4f at all. The product is at most
    1020, so the ROM's word shift cannot wrap — which is why this is plain arithmetic and not a
    `word_index`."""
    assert slot == addrs.MFP_VECTOR_TABLE + channel * addrs.VECTOR_BYTES
    image = run_install_candidate_only(channel)["image"]
    assert int.from_bytes(image[slot:slot + addrs.VECTOR_BYTES], "big") == A_HANDLER
