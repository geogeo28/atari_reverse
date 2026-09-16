"""XBIOS Xbtimer (function $1f) @ $fc2ff2, and the MFP timer programmer at $fc25b0 it shares with
`Rsconf`'s baud arm.

`Xbtimer` is three steps: program one of the MFP's four timers, look its interrupt channel up in a
four-byte ROM table, and install a handler on it through `Mfpint`'s body. The programmer is the part
with the arithmetic in it, and it is table-driven — eight adjacent four-byte tables in the ROM,
every one indexed by the timer number.

WHAT THIS BATTERY PROVES is the programmer's five CLEARS, as a slice `[$fc25b0, $fc2600)`, plus the
three ROM tables the rest of the routine indexes. What it does NOT prove, and cannot today, is the
data-register write that follows: the 68901 needs a settling time on those registers, so the ROM
stores the byte and re-reads it until the chip agrees — and the declared I/O map serves a per-run
CONSTANT describing what a register held on ENTRY, so a read-back of a byte the run itself stored is
refused outright. That is measured below, and `src/xbios/xbtimer.c` carries what would unblock it.

THE FIVE CLEARS ARE `Jdisint` PLUS ONE, and the "plus one" is the whole reason the tables exist. The
four interrupt registers are cleared exactly as `Jdisint` clears them for the timer's own MFP
channel — same registers, same bits, same order — which this file asserts by computing them from the
CHANNEL rather than from the tables. The fifth is the timer's CONTROL register, and that one is not
a bit in a pair: timers A and B own a whole byte each and have it wiped, while timers C and D SHARE
`$fffa1d` and each clears only its own three bits. A reconstruction that wiped the shared byte for
timer D would stop the 200 Hz tick dead, and the only thing that separates the two is the value in
the hardware write ledger.

AND THE VECTOR ARM IS PAST THE HALT, so the last section of this file runs the RECONSTRUCTION ALONE.
`Xbtimer`'s `bsr.w $fc3024` enters `Mfpint` at `$fc2666` — past its `andi.l #15,d0` — so the channel
it installs on is the raw byte out of `$fc302a`, unmasked and unbounded; but nothing on either side
ever reaches that instruction, because the programmer above it refuses the oracle's run and halts
ours. What those cases compare is the candidate's own ledger and image against arithmetic taken from
the disassembly, and every one of them says CANDIDATE-ONLY in its first line.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, differential, emu, make_image

import abi
import case
import mfp

_lib.mfp_timer_clear.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.mfp_timer_clear.restype = None
_lib.mfp_install_vector_and_enable.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                                               ctypes.c_uint32]
_lib.mfp_install_vector_and_enable.restype = ctypes.c_uint32
_lib.xbtimer_install_handler.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16,
                                         ctypes.c_uint32]
_lib.xbtimer_install_handler.restype = ctypes.c_uint32

TIMERS = (addrs.MFP_TIMER_A, addrs.MFP_TIMER_B, addrs.MFP_TIMER_C, addrs.MFP_TIMER_D)
TIMER_IDS = ("A", "B", "C", "D")
# The MFP channel each timer raises, from `$fc302a` — asserted against the ROM below rather than
# taken on trust, and used here to compute the four interrupt registers INDEPENDENTLY of the tables
# the reconstruction reads.
TIMER_CHANNELS = (13, 8, 5, 4)
# ...and each timer's control register with the mask that clears just its own field. A and B own a
# byte each; C and D share one.
CONTROL_REGISTERS = (addrs.MFP_TACR, addrs.MFP_TBCR, addrs.MFP_TCDCR, addrs.MFP_TCDCR)
CONTROL_MASKS = (0x00, 0x00, 0x8F, 0xF8)
# The order the programmer clears them in, which is `Jdisint`'s: mask, enable, pending, in-service.
CLEAR_ORDER = (addrs.MFP_IMRA, addrs.MFP_IERA, addrs.MFP_IPRA, addrs.MFP_ISRA)

A_CONTROL, A_DIVIDER = 0x07, 0xC0      # a real timer C setup: /200 prescaler, count 192
A_HANDLER = 0x0006_1234


def run_clear(timer, io_seed=None, poison=True):
    """The programmer's five clears, as far as a case can carry them: `[$fc25b0, $fc2600)`."""
    def glue(lib, buf):
        lib.mfp_timer_clear(buf, timer & 0xFFFF)

    return case.run(addrs.MFP_TIMER_PROGRAM,
                    {"a5": 0, "d0": timer, "d1": A_CONTROL, "d2": A_DIVIDER}, glue,
                    width=case.NO_RESULT, poison=poison, stop_pc=addrs.MFP_TIMER_DATA_WRITE,
                    io_seed=io_seed or mfp.seed())


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
    declared = mfp.seed()
    register, mask = CONTROL_REGISTERS[timer], CONTROL_MASKS[timer]
    assert run_clear(timer)["regs"]["hw_writes"][-1] == (register, 1, declared[register] & mask)


def test_the_two_timers_that_share_a_control_byte_clear_different_halves_of_it():
    """...said as the comparison it is, because this is the case the shared byte exists for: C and D
    write the SAME address with DIFFERENT values, each preserving what the other set."""
    declared = mfp.seed()
    held = declared[addrs.MFP_TCDCR]
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
    expected.append((CONTROL_REGISTERS[timer], mfp.seed()[CONTROL_REGISTERS[timer]]))
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


def test_the_whole_of_xbtimer_cannot_be_run_under_a_declared_map_and_this_is_why():
    """THE MEASUREMENT THE HALT RESTS ON, so the limit is a red rather than a paragraph.

    Undeclared, the timer's data register answers a fabricated 0, the `move.b`/`cmp.b`/`bne` loop
    never agrees and the run dies at the instruction cap. Declared equal to the byte the routine
    writes, the run completes and the ORACLE reports STALE reads — the data register it wrote and
    read back, and the control register it cleared and then re-read to OR the control bits in.
    Either way the case is void, and no bigger declaration is the remedy.
    """
    timer = addrs.MFP_TIMER_A
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(xbtimer_frame(timer)), addrs.XBIOS_XBTIMER, {"a5": 0},
                io_seed=mfp.seed(), max_insns=20_000)

    declared = mfp.seed({addrs.MFP_TADR: A_DIVIDER})
    _final, _writes, o_regs = emu.run(make_image(xbtimer_frame(timer)), addrs.XBIOS_XBTIMER,
                                      {"a5": 0}, io_seed=declared)
    assert o_regs["io_stale_reads"] and o_regs["io_stale_first"] == addrs.MFP_TADR, (
        f"Xbtimer's first stale read is now at {o_regs['io_stale_first']:#x} — the halt's premise "
        f"has moved")
    with pytest.raises(AssertionError, match="already STORED to"):
        def glue(lib, buf):
            lib.mfp_timer_clear(buf, timer)
        differential(addrs.XBIOS_XBTIMER, {"a5": 0, "_pokes": xbtimer_frame(timer)}, glue,
                     io_seed=declared)


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
# CANDIDATE-ONLY, ALL OF IT. `Xbtimer` halts in the timer programmer long before it reaches the
# install (the case above measures why), so there is no original run to compare these against — what
# is compared is the reconstruction's own ledger and image against arithmetic taken from the
# disassembly. Each assertion below says which side it is about.
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
    """...and the arm that CHOOSES the byte, which is the half `xbios_xbtimer`'s halt puts out of
    reach of every case: the table read at `$fc3014` and the `bsr` at `$fc3024`, together."""
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
