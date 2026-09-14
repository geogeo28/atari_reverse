"""XBIOS Protobt (function 18) @ $fc15f8 — build a floppy boot sector in the caller's buffer.

The routine behind the desktop's Format: it writes a three-byte serial number at buf[8], a 19-byte
BPB for the geometry asked for at buf[11], and the word at buf[510] that makes the sector's 256 words
sum to $1234 — which is what the ROM's boot code tests before executing one.

Compiled by Alcyon C, and it MODIFIES ITS OWN ARGUMENTS in the caller's frame: `serial` is rewritten
with the random number it invented, and `executable` with the answer it worked out.

HOW THOSE TWO OUTPUTS ARE CHECKED needs saying, because they are the one part of this routine that
does not go through the ordinary diff. They land at 12(a6) and 18(a6), which is the argument frame
the case staged just above the oracle's stack pointer — inside the band `differential` drops (the
oracle uses it as a real machine stack and the C candidate has no analogue) and exempt from the
stray-write guard because the case poked those bytes itself. So the candidate's copies are compared
against HAND-DERIVED expectations, which is weaker than a differential; what strengthens it is that
the same cases also read the ORACLE's own write ledger at those two addresses and assert the same
values, so at least the ROM's half of each claim rests on the run rather than on arithmetic done
here (`frame_serial`, `frame_executable`).

FIVE THINGS THE CASES SEPARATE, none of them visible from the checksum alone:

* the final sum runs over words 0..254 and NOT 255 — `cmp.l buf+510,cursor / bhi` stops strictly
  below the checksum word, so the word it writes is not part of what it balances;
* the `executable < 0` probe sums 256 words instead, checksum included, because there it is reading
  a sector somebody else built;
* `executable == 0` writes the balancing word and then adds ONE to it, which is how a sector is made
  deliberately non-executable;
* a serial above $ffffff is replaced by XBIOS Random's next value — a call into another verified
  function, in the ROM and in the C alike, and the one case here whose output moves with `_hz_200`;
* the BPB row is `muls.w #19` taken as a WORD and then SIGN-EXTENDED (`include/m68k_idioms.h`), so a
  disk type above 1724 reads BELOW the prototype table rather than above it.

Each of `serial`, `disk_type` and `executable` has its own "leave it alone" value, and they are
INDEPENDENT (unlike Kbrate's pair next door), so the battery walks the combinations.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case
import staging

_lib.xbios_protobt.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_uint32), ctypes.c_int16,
                               ctypes.POINTER(ctypes.c_int16)]
_lib.xbios_protobt.restype = None

BUFFER_AT = staging.SCRATCH
KEEP_SERIAL = 0xFFFFFFFF        # a negative serial: leave buf[8..10] alone
KEEP_DISK_TYPE = -1             # ...and a negative type: leave buf[11..29] alone
PROBE_EXECUTABLE = -1           # ...and a negative flag: work it out from the buffer as it stands

# The four geometries the ROM's prototype table describes, and the media byte each carries at
# BPB offset 10 — the field that makes them distinguishable by eye.
DISK_TYPES = (0, 1, 2, 3)
MEDIA_BYTE_IN_BPB = 10
# A disk type whose row product goes NEGATIVE as a word: 1725 * 19 is $8007.
NEGATIVE_INDEX_DISK_TYPE = 1725
SIGN_BIT16 = 0x8000
WORD_MODULUS = 0x1_0000

# The argument frame Alcyon leaves at 8(a6): buffer, serial, disk type, executable.
ARGUMENT_FORMAT = ">IIhh"
# ...and where the two IN/OUT arguments sit in it, which is where the ROM rewrites them.
FRAME_SERIAL = abi.FIRST_ARG + 4
FRAME_EXECUTABLE = abi.FIRST_ARG + 10


def argument_poke(buffer, serial, disk_type, executable):
    return {abi.FIRST_ARG: struct.pack(ARGUMENT_FORMAT, buffer, serial & 0xFFFFFFFF, disk_type,
                                       executable)}


def run(serial=KEEP_SERIAL, disk_type=KEEP_DISK_TYPE, executable=0, sector=None,
        buffer=BUFFER_AT, poison=True, pokes=None):
    """One differential. Returns (info, the buffer the CANDIDATE produced, serial, executable).

    The in/out arguments are built PER CALL rather than once: `differential`'s attribution pass runs
    the glue a second time, and a `serial` the first run had already shifted down would make the
    second write different bytes — which would read as the candidate failing to attribute its own
    store. Only the FIRST run's results are reported, because the second one's image is poisoned.
    """
    runs = []

    def glue(lib, buf):
        out_serial = ctypes.c_uint32(serial & 0xFFFFFFFF)
        out_executable = ctypes.c_int16(executable)
        lib.xbios_protobt(buf, buffer, ctypes.byref(out_serial), disk_type,
                          ctypes.byref(out_executable))
        runs.append((bytes(bytearray(buf[buffer:buffer + addrs.BOOT_SECTOR_BYTES])),
                     out_serial.value, out_executable.value))

    staged = {**argument_poke(buffer, serial, disk_type, executable), **(pokes or {})}
    if sector is not None:
        staged[buffer] = sector
    info = case.run(addrs.XBIOS_PROTOBT, {"a5": 0, "_pokes": staged}, glue,
                    width=case.NO_RESULT, poison=poison)
    return (info, *runs[0])


def frame_serial(info):
    """What the ORACLE left in the caller's `serial` slot, out of its own write ledger."""
    return case.written_long(info, FRAME_SERIAL)


def frame_executable(info):
    """...and in the `executable` slot, which only the probe branch writes."""
    return case.written(info, FRAME_EXECUTABLE, 2)


def word_sum(sector, words):
    return sum(struct.unpack(f">{words}H", sector[:2 * words])) & 0xFFFF


def bpb_source(disk_type):
    """Where a disk type's 19 bytes come from: `muls.w #19,d6` then `movea.w d6,a1` on every pass, so
    the row is a WORD off the table and SIGN-EXTENDED into the address."""
    row = (disk_type * addrs.BOOT_BPB_BYTES) & 0xFFFF
    signed = row - WORD_MODULUS if row & SIGN_BIT16 else row
    return (addrs.PROTOBT_BPB_TABLE + signed) & 0xFFFF_FFFF


def bpb_prototype(disk_type):
    at = bpb_source(disk_type)
    return bytes(BASE_IMAGE[at:at + addrs.BOOT_BPB_BYTES])


# ---- the checksum, which every call writes ---------------------------------------------------------

@pytest.mark.parametrize("fill", (b"\x00", b"\xff", b"\x5a", b"\x12"))
def test_an_executable_sector_sums_to_1234(fill):
    """The whole point of the routine: 256 words summing to $1234 in 16 bits."""
    _info, sector, _serial, _executable = run(executable=1, sector=fill * addrs.BOOT_SECTOR_BYTES)
    assert word_sum(sector, addrs.BOOT_SECTOR_WORDS) == addrs.BOOT_EXECUTABLE_SUM


@pytest.mark.parametrize("fill", (b"\x00", b"\xff", b"\x5a"))
def test_a_non_executable_sector_misses_it_by_exactly_one(fill):
    """`addq.w #1,(a0)` on the word just written. Not "any other value" — one."""
    _info, sector, _serial, _executable = run(executable=0, sector=fill * addrs.BOOT_SECTOR_BYTES)
    assert word_sum(sector, addrs.BOOT_SECTOR_WORDS) == addrs.BOOT_EXECUTABLE_SUM + 1


def test_the_final_sum_excludes_the_checksum_word_itself():
    """`bhi` on `cursor < buf+510`: 255 words, not 256. A reconstruction that summed all 256 would
    fold the buffer's OLD checksum word into the balance, and this sector — whose last word is not
    zero — is where that shows."""
    sector = bytes(range(256)) * 2
    assert sector[addrs.BOOT_CHECKSUM_AT:] != b"\x00\x00"
    _info, produced, _serial, _executable = run(executable=1, sector=sector)
    expected = (addrs.BOOT_EXECUTABLE_SUM - word_sum(sector, addrs.BOOT_CHECKSUM_AT // 2)) & 0xFFFF
    assert struct.unpack(">H", produced[addrs.BOOT_CHECKSUM_AT:])[0] == expected


# ---- the executable probe ---------------------------------------------------------------------------

@pytest.mark.parametrize("executable", (0, 1))
def test_the_probe_reports_whether_the_sector_it_was_given_already_summed_to_1234(executable):
    """`executable < 0` sums all 256 words of the buffer AS GIVEN and answers 1 or 0 — then goes on
    to rebuild the checksum for that answer, so the sector it returns matches what it decided. The
    answer is read back twice: from the candidate's own out-parameter, and from the ORACLE's write
    ledger at the frame slot, which is what makes the ROM's half of the claim a measurement."""
    sector = bytearray(addrs.BOOT_SECTOR_BYTES)
    target = addrs.BOOT_EXECUTABLE_SUM if executable else addrs.BOOT_EXECUTABLE_SUM + 1
    sector[addrs.BOOT_CHECKSUM_AT:] = struct.pack(">H", target)
    info, produced, _serial, answered = run(executable=PROBE_EXECUTABLE, sector=bytes(sector))
    assert answered == executable, "the probe read the sector it was given differently"
    assert frame_executable(info) == executable, "...and the ROM wrote a different answer"
    assert word_sum(produced, addrs.BOOT_SECTOR_WORDS) == target


def test_the_probe_sums_the_checksum_word_too():
    """256 words, not 255 — which is the opposite of the loop at the end. A sector whose first 255
    words already sum to $1234 is NOT executable unless its last word is 0, and that is the case a
    reconstruction sharing one loop length gets wrong."""
    sector = bytearray(addrs.BOOT_SECTOR_BYTES)
    sector[0:2] = struct.pack(">H", addrs.BOOT_EXECUTABLE_SUM)
    sector[addrs.BOOT_CHECKSUM_AT:] = struct.pack(">H", 0x0001)
    info, _produced, _serial, answered = run(executable=PROBE_EXECUTABLE, sector=bytes(sector))
    assert answered == 0
    assert frame_executable(info) == 0


def test_a_flag_the_caller_supplied_is_not_written_back():
    """The probe branch is the ONLY writer of 18(a6) — `tst.w 18(a6) / bge` skips it — so a
    non-negative flag leaves the caller's own word alone. Read off the oracle's ledger, since the
    slot is in the band the byte diff drops."""
    info, _produced, _serial, _executable = run(executable=1,
                                                sector=bytes(addrs.BOOT_SECTOR_BYTES))
    assert FRAME_EXECUTABLE not in info["writes"], "a supplied `executable` was rewritten"


# ---- the serial number ------------------------------------------------------------------------------

@pytest.mark.parametrize("serial", (0, 1, 0x00FFFFFF, 0x00123456, 0x0000FF00))
def test_a_serial_that_fits_is_written_low_byte_first(serial):
    """Three bytes at buf[8], least significant first, and the fourth byte of the argument never
    reaches the sector — $00ffffff is the largest that is taken as given. The frame slot is left
    holding what the `asr.l #8` loop shifted it down to, asserted on both sides."""
    info, sector, out_serial, _executable = run(serial=serial, executable=1,
                                                sector=bytes(addrs.BOOT_SECTOR_BYTES))
    expected = serial.to_bytes(4, "little")[:addrs.BOOT_SERIAL_BYTES]
    at = addrs.BOOT_SERIAL_AT
    assert sector[at:at + addrs.BOOT_SERIAL_BYTES] == expected
    shifted = serial >> (8 * addrs.BOOT_SERIAL_BYTES)
    assert out_serial == shifted, "the argument slot is left holding what the shifting loop left"
    assert frame_serial(info) == shifted, "...and the ROM left something else there"


@pytest.mark.parametrize("serial", (0x01000000, 0x7FFFFFFF, 0x0100_0001))
def test_a_serial_too_wide_for_three_bytes_is_replaced_by_random(serial):
    """`cmp.l #$ffffff,d0 / ble` — above it the routine calls XBIOS Random at $fc1510 and uses its
    24-bit answer. So this case's output moves with `_hz_200`, and the C makes the same call."""
    _info, sector, _out_serial, _executable = run(serial=serial, executable=1,
                                                  sector=bytes(addrs.BOOT_SECTOR_BYTES))
    at = addrs.BOOT_SERIAL_AT
    assert sector[at:at + addrs.BOOT_SERIAL_BYTES] != serial.to_bytes(4, "little")[:3]


@pytest.mark.parametrize("tick", (0, 0x0B32, 0x1234_5678, 0xFFFF_FFFF))
def test_the_random_serial_follows_the_machine_s_own_tick(tick):
    """Random seeds from `_hz_200` on an unseeded machine, so the serial a Format writes depends on
    when it was asked for. Poked to several values so the case is about the mechanism rather than
    about the one instant the snapshot holds."""
    run(serial=0x0100_0000, executable=1, sector=bytes(addrs.BOOT_SECTOR_BYTES),
        pokes={addrs.SYSVAR_HZ_200: tick.to_bytes(4, "big")})


@pytest.mark.parametrize("serial", (KEEP_SERIAL, 0x80000000, 0xFFFFFFFE))
def test_a_negative_serial_leaves_the_sector_s_own_bytes_alone(serial):
    sector = bytearray(addrs.BOOT_SECTOR_BYTES)
    sector[addrs.BOOT_SERIAL_AT:addrs.BOOT_SERIAL_AT + 3] = b"\xaa\xbb\xcc"
    info, produced, _out_serial, _executable = run(serial=serial, executable=1,
                                                   sector=bytes(sector))
    at = addrs.BOOT_SERIAL_AT
    assert produced[at:at + 3] == b"\xaa\xbb\xcc"
    assert FRAME_SERIAL not in info["writes"], "a negative serial was rewritten in the frame"


# ---- the BPB ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("disk_type", DISK_TYPES)
def test_each_disk_type_copies_its_own_19_byte_prototype(disk_type):
    """The four geometries: 40/80 tracks, single/double sided. Their media bytes differ, so copying
    the WRONG row diverges on the value rather than by luck."""
    _info, sector, _serial, _executable = run(disk_type=disk_type, executable=1,
                                              sector=bytes(addrs.BOOT_SECTOR_BYTES))
    at = addrs.BOOT_BPB_AT
    assert sector[at:at + addrs.BOOT_BPB_BYTES] == bpb_prototype(disk_type)


def test_the_four_prototypes_are_distinct():
    """...which is what makes the case above a case at all."""
    media = {bpb_prototype(t)[MEDIA_BYTE_IN_BPB] for t in DISK_TYPES}
    assert len(media) == len(DISK_TYPES)


@pytest.mark.parametrize("disk_type", (KEEP_DISK_TYPE, -2, -0x8000))
def test_a_negative_disk_type_leaves_the_bpb_alone(disk_type):
    sector = bytearray(addrs.BOOT_SECTOR_BYTES)
    marker = bytes(range(addrs.BOOT_BPB_BYTES))
    sector[addrs.BOOT_BPB_AT:addrs.BOOT_BPB_AT + addrs.BOOT_BPB_BYTES] = marker
    _info, produced, _serial, _executable = run(disk_type=disk_type, executable=1,
                                                sector=bytes(sector))
    at = addrs.BOOT_BPB_AT
    assert produced[at:at + addrs.BOOT_BPB_BYTES] == marker


def test_there_is_no_bounds_check_on_the_disk_type():
    """Type 4 reads the 19 bytes after the fourth prototype and copies them as a BPB. Reproduced
    rather than clamped; the bytes come out of the mapped ROM on both sides."""
    _info, sector, _serial, _executable = run(disk_type=4, executable=1,
                                              sector=bytes(addrs.BOOT_SECTOR_BYTES))
    at = addrs.BOOT_BPB_AT
    assert sector[at:at + addrs.BOOT_BPB_BYTES] == bpb_prototype(4)


def test_a_disk_type_whose_row_goes_negative_reads_below_the_prototype_table():
    """THE SIGN EXTENSION, which every case above is blind to because their rows are small.

    Disk type 1725's row is $8007 — negative as a word — so `movea.w d6,a1` reaches $fcaf39, $7ff9
    BELOW the table. A reconstruction that zero-extended would read $fdaf39 instead, and the two
    spans are asserted to differ, so this is a case and not a coincidence.
    """
    row = (NEGATIVE_INDEX_DISK_TYPE * addrs.BOOT_BPB_BYTES) & 0xFFFF
    assert row & SIGN_BIT16, "the case is only a case while the row product's bit 15 is set"
    below = bpb_prototype(NEGATIVE_INDEX_DISK_TYPE)
    above_at = addrs.PROTOBT_BPB_TABLE + row
    above = bytes(BASE_IMAGE[above_at:above_at + addrs.BOOT_BPB_BYTES])
    assert below != above, "the two rows hold the same bytes, so this case could not tell them apart"
    _info, sector, _serial, _executable = run(disk_type=NEGATIVE_INDEX_DISK_TYPE, executable=1,
                                              sector=bytes(addrs.BOOT_SECTOR_BYTES))
    at = addrs.BOOT_BPB_AT
    assert sector[at:at + addrs.BOOT_BPB_BYTES] == below


# ---- the three arguments together --------------------------------------------------------------------

def test_a_whole_format_writes_serial_bpb_and_checksum_together():
    """The call the desktop's Format actually makes, and the composition case: all three fields, one
    buffer, one pass."""
    serial, disk_type = 0x00ABCDEF, 3
    _info, sector, _out_serial, _executable = run(serial=serial, disk_type=disk_type, executable=1,
                                                  sector=bytes(addrs.BOOT_SECTOR_BYTES))
    assert sector[addrs.BOOT_SERIAL_AT:addrs.BOOT_SERIAL_AT + 3] == b"\xef\xcd\xab"
    assert sector[addrs.BOOT_BPB_AT:addrs.BOOT_BPB_AT + addrs.BOOT_BPB_BYTES] == \
        bpb_prototype(disk_type)
    assert word_sum(sector, addrs.BOOT_SECTOR_WORDS) == addrs.BOOT_EXECUTABLE_SUM


@pytest.mark.parametrize("offset", (0, 0x200, 0x400))
def test_the_buffer_is_wherever_the_caller_points(offset):
    """The pointer is used unchecked, so the routine's whole effect moves with it."""
    buffer = BUFFER_AT + offset
    _info, sector, _serial, _executable = run(disk_type=1, executable=1, buffer=buffer,
                                              sector=bytes(addrs.BOOT_SECTOR_BYTES))
    assert sector[addrs.BOOT_BPB_AT:addrs.BOOT_BPB_AT + addrs.BOOT_BPB_BYTES] == bpb_prototype(1)
