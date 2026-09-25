"""The GEMDOS calls whose whole body is RAM — `src/gemdos/leaves.c`, eight routines and two halves.

Each is entered the way the dispatcher's `jsr` leaves it: A5 = 0 and the copied argument words above
the return address (`abi.py`), which is the ordinary shape of every battery in this project. What is
NOT ordinary is in three of them, and they are what this file is mostly about:

* `Fsetdta` WRITES NO RESULT. Alcyon emitted nothing for a `void` function, so the caller's own D0
  comes back out through the trap entry's save area as if it were the call's answer.
* `Dsetdrv` reaches BIOS `Drvmap` through a REAL `trap #13`, which in ROM mode the oracle takes into
  the ROM's own dispatcher. The HOST build of our C calls `bios_drvmap` directly, as ROM mode asks —
  and the difference between those two things is an image effect this battery DECLARES rather than
  waves at: `gemdos.machine()` puts the trap's register frame in the band the diff drops, and the
  trampoline's parked return address is a store the reconstruction makes itself.
* `Tsetdate` and `Tsettime` end in XBIOS `Settime`, which is NOT reconstructed, so only their
  REJECTING arms can be run. Between them those arms carry three of the ROM's own bounds and two
  DEAD ones, and the dead ones are the interesting half: TOS 1.02 cannot reject a year or an hour at
  all, and this file is where that is written down with a case beside it.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import gemdos

for _name in ("gemdos_sversion", "gemdos_unimplemented", "gemdos_fgetdta", "gemdos_fsetdta",
              "gemdos_dgetdrv", "gemdos_dsetdrv", "gemdos_tgetdate", "gemdos_tgettime",
              "gemdos_tsetdate", "gemdos_tsettime"):
    getattr(_lib, _name).restype = ctypes.c_uint32

# A distinctive D0 for the one routine that hands the caller's own back, and an equally distinctive
# DTA and drive, so that a reconstruction reading the wrong field has something to fail against.
ENTRY_D0 = 0xDEC0_DE00
A_DTA = 0x0001_2340
A_DRIVE = 0x0C                          # M:, which the snapshot's machine does not have


def basepage_at(offset):
    """Where a field of the RUNNING process's basepage is — what a case's default reads."""
    return gemdos.BASEPAGE + offset


# ---- the two constants ---------------------------------------------------------------------------

def test_sversion_is_the_roms_own_version_word():
    """`move.l #$1300,d0` — no image, no argument, and the smallest routine in this component."""
    info = case.run(addrs.GEMDOS_SVERSION, {"a5": 0}, lambda lib, buf: lib.gemdos_sversion())
    assert info["regs"]["d0"] == addrs.GEMDOS_VERSION


def test_the_undefined_selectors_handler_answers_einvfn():
    """38 of the 88 records name these three instructions. It is NOT the dispatcher's bound check —
    a selector past $57 never reaches a record at all — so a caller of `Gemdos($0c)` has had a whole
    dispatch, an argument frame and a `jsr` before it is told the function does not exist."""
    info = case.run(addrs.GEMDOS_UNIMPLEMENTED, {"a5": 0},
                    lambda lib, buf: lib.gemdos_unimplemented())
    assert info["regs"]["d0"] == addrs.GEMDOS_EINVFN


# ---- the DTA -------------------------------------------------------------------------------------

@pytest.mark.parametrize("dta", (0, A_DTA, 0xFFFF_FFFF, None))
def test_fgetdta_reports_the_whole_longword_from_the_basepage(dta):
    """`move.l $20(p_run),d0`. `None` is the snapshot's own DTA, which is where the desktop left it;
    the rest separate a reconstruction reading a longword from one reading a word."""
    pokes = {} if dta is None else gemdos.dta_poke(dta)
    info = case.run(addrs.GEMDOS_FGETDTA, {"a5": 0, "_pokes": pokes},
                    lambda lib, buf: lib.gemdos_fgetdta(buf))
    assert info["regs"]["d0"] == (case.long_in(BASE_IMAGE, basepage_at(addrs.BASEPAGE_DTA))
                                  if dta is None else dta)


@pytest.mark.parametrize("dta", (0, A_DTA, 0xFFFF_FFFF))
def test_fsetdta_stores_the_pointer_and_hands_back_the_callers_own_d0(dta):
    """THE RESULT IS NOT THIS ROUTINE'S. The ROM stores the longword and returns, writing no part of
    D0, so what the caller reads as `Fsetdta`'s answer is whatever it had in D0 when it trapped —
    which the trap entry restores out of the basepage. A reconstruction that returned 0, or the
    pointer, would agree with the ROM about every byte of the image and differ here alone.
    """
    info = case.run(addrs.GEMDOS_FSETDTA, {"a5": 0, "d0": ENTRY_D0, "_pokes": case.long_args(dta)},
                    lambda lib, buf: lib.gemdos_fsetdta(buf, ENTRY_D0, dta))
    assert info["regs"]["d0"] == ENTRY_D0
    assert case.written_long(info, gemdos.BASEPAGE + addrs.BASEPAGE_DTA) == dta


# ---- the current drive ---------------------------------------------------------------------------

@pytest.mark.parametrize("drive", (0, 1, A_DRIVE, 0x7F, 0x80, 0xFF, None))
def test_dgetdrv_sign_extends_the_basepage_byte(drive):
    """`move.b` / `ext.w` / `ext.l`, so a basepage holding $ff answers -1 rather than 255 — which is
    what $80 and $ff are here for. A reconstruction that zero-extended agrees on the first four."""
    pokes = {} if drive is None else gemdos.current_drive_poke(drive)
    info = case.run(addrs.GEMDOS_DGETDRV, {"a5": 0, "_pokes": pokes},
                    lambda lib, buf: lib.gemdos_dgetdrv(buf))
    stored = BASE_IMAGE[basepage_at(addrs.BASEPAGE_CURDRV)] if drive is None else drive
    assert info["regs"]["d0"] == (stored | 0xFFFF_FF00 if stored & 0x80 else stored)


# `Dsetdrv` REACHES THE BIOS, and that is what its three cases are shaped by.
#
# The ROM reaches `Drvmap` through `$fc4eac` — `move.l (sp)+,$eb0 / trap #13` — so the ORIGINAL, run
# to its own `rts`, leaves two marks that belong to the trap rather than to `Dsetdrv`: the
# trampoline's parked return address at `$eb0`, and the BIOS dispatcher's own 46-byte register frame
# under `savptr`. The reconstruction makes the FIRST of them itself, from a named constant, because
# the trampoline is not transcribed; the second is the host build's alone — on target it takes the
# same trap — and `gemdos.machine()` is what declares where it lands, by poking `savptr` into the
# band the differential already drops (`test/gemdos.py`).
#
# So this is an ordinary whole-routine differential, and `poison=False` for the reason that staging
# has: the oracle writes `savptr` itself, and an inverted one would send its frame to an address the
# case never chose. `gemdos.FILL` under the return slot is the attribution in its place.


# What the basepage's current drive is staged holding, so that the store this routine makes MOVES a
# byte for every drive below — the snapshot's own is A:, and a case for drive 0 over it would be a
# case a candidate that skipped the store still passed. It is not one of the drives tested.
STALE_DRIVE = 0x5A


def dsetdrv_pokes(drive):
    """The machine a `Dsetdrv` case starts from: the trap frame's, its argument, and that byte."""
    return gemdos.machine({**case.word_arg(drive), **gemdos.current_drive_poke(STALE_DRIVE)})


def run_dsetdrv(drive):
    """One `Dsetdrv` differential, over the machine every GEMDOS routine that traps starts from."""
    return case.run(addrs.GEMDOS_DSETDRV, {"a5": 0, "_pokes": dsetdrv_pokes(drive)},
                    lambda lib, buf: lib.gemdos_dsetdrv(buf, drive), poison=False)


@pytest.mark.parametrize("drive", (0, 1, A_DRIVE, 0xFF))
def test_dsetdrv_stores_the_low_byte_of_its_argument(drive):
    """The byte goes in the basepage with no bound check at all: the word argument's LOW BYTE is
    stored whatever it is, which $ff and $0c are here for — a drive the machine has not got is
    accepted exactly as one it has."""
    info = run_dsetdrv(drive)
    assert case.written(info, gemdos.BASEPAGE + addrs.BASEPAGE_CURDRV, 1) == (drive & 0xFF)


def test_dsetdrv_answers_with_the_drive_map():
    """...and the other half, which is what makes "set the drive" also "tell me which drives exist".

    `case.run` has already required our D0 to be the ROM's; this says WHICH longword that is —
    `_drvbits` itself, the variable `test_bios_drvmap.py` proves that routine reads.
    """
    assert run_dsetdrv(A_DRIVE)["ret"] == case.long_in(BASE_IMAGE, addrs.SYSVAR_DRVBITS)


def test_dsetdrv_parks_a_return_address_the_rom_really_has_a_jsr_at():
    """The trampoline's store, which the reconstruction makes from a constant of its own — so this
    is what says that constant is a call site: the six bytes before it must be `jsr $fc4eac`.

    `src/gemdos/console.c` makes the same claim about its own thirteen sites; this is the
    fourteenth, and the only one outside that file.
    """
    assert gemdos.bios_call_site(run_dsetdrv(A_DRIVE)) > addrs.GEMDOS_DSETDRV


# ---- the date and the time -----------------------------------------------------------------------

# A DOS date word is `(year - 1980) << 9 | month << 5 | day` and a time word
# `hour << 11 | minute << 5 | second / 2`. Spelt as functions rather than as literals, because every
# bound case below is ONE FIELD out of range and a reader has to be able to see which.
def dos_date(year, month, day):
    return ((year & 0x7F) << addrs.GEMDOS_DATE_YEAR_SHIFT) | \
           ((month & 0x0F) << addrs.GEMDOS_DATE_MONTH_SHIFT) | (day & addrs.GEMDOS_DATE_DAY_MASK)


def dos_time(hour, minute, second):
    return ((hour & 0x1F) << 11) | ((minute & 0x3F) << 5) | (second & addrs.GEMDOS_TIME_SECOND_MASK)


@pytest.mark.parametrize("date", (None, 0, 0x7FFF, 0x8000, 0xFFFF, dos_date(7, 4, 22)))
def test_tgetdate_sign_extends_gemdos_own_date_word(date):
    """`move.w $8840,d0 / ext.l d0` — and the sign extension is the whole claim: a date in 2044 or
    later sets bit 15 and comes back as a NEGATIVE long."""
    pokes = {} if date is None else gemdos.date_poke(date)
    info = case.run(addrs.GEMDOS_TGETDATE, {"a5": 0, "_pokes": pokes},
                    lambda lib, buf: lib.gemdos_tgetdate(buf))
    stored = case.word_in(BASE_IMAGE, addrs.GEMDOS_DATE) if date is None else date
    assert info["regs"]["d0"] == (stored | 0xFFFF_0000 if stored & 0x8000 else stored)


@pytest.mark.parametrize("time", (None, 0, 0x7FFF, 0x8000, 0xFFFF, dos_time(11, 59, 58)))
def test_tgettime_sign_extends_gemdos_own_time_word(time):
    """...and the same routine over the other word. Every afternoon sets bit 11 and every hour from
    16 sets bit 15, so a caller reading `Tgettime` into a `long` sees a negative number after 4pm."""
    pokes = {} if time is None else gemdos.time_poke(time)
    info = case.run(addrs.GEMDOS_TGETTIME, {"a5": 0, "_pokes": pokes},
                    lambda lib, buf: lib.gemdos_tgettime(buf))
    stored = case.word_in(BASE_IMAGE, addrs.GEMDOS_TIME) if time is None else time
    assert info["regs"]["d0"] == (stored | 0xFFFF_0000 if stored & 0x8000 else stored)


# The dates the ROM REFUSES, one field at a time. There is no accepted date here and there cannot be:
# an accepted one stores the word and calls XBIOS `Settime`, which is not reconstructed, so the
# oracle would talk to the IKBD where the candidate could only halt (`gemdos.py`'s clock door).
REFUSED_DATES = (
    ("month 13, which the four-bit field can hold", dos_date(7, 13, 1)),
    ("month 15, the widest the field goes", dos_date(7, 15, 1)),
    ("month 0, whose table length is 0", dos_date(7, 0, 1)),
    ("31 April", dos_date(7, 4, 31)),
    ("31 September", dos_date(7, 9, 31)),
    ("30 February in a leap year", dos_date(8, 2, 30)),
    ("29 February in a year that is not one", dos_date(7, 2, 29)),
)


@pytest.mark.parametrize("what,date", REFUSED_DATES, ids=lambda arg: arg)
def test_tsetdate_refuses_a_date_out_of_range(what, date):
    """-1, and NOTHING STORED — which is what the whole-image diff says and the clock door confirms.

    The two February cases are the pair that separate the leap arm from the table: 1988 is divisible
    by four, so its February is computed at 29 days and 30 is refused; 1987's falls through to the
    table's 28 and 29 is refused there.
    """
    with gemdos.bound_handlers({}):
        info = case.run(addrs.GEMDOS_TSETDATE, {"a5": 0, "_pokes": case.word_arg(date)},
                        lambda lib, buf: lib.gemdos_tsetdate(buf, date))
    assert info["regs"]["d0"] == addrs.GEMDOS_RANGE_ERROR
    gemdos.assert_the_clock_was_not_published()


REFUSED_TIMES = (
    ("second field 30, i.e. 60 seconds", dos_time(11, 30, 30)),
    ("second field 31", dos_time(0, 0, 31)),
    ("minute 60", dos_time(11, 60, 0)),
    ("minute 63, the widest the field goes", dos_time(0, 63, 0)),
)


@pytest.mark.parametrize("what,time", REFUSED_TIMES, ids=lambda arg: arg)
def test_tsettime_refuses_a_time_out_of_range(what, time):
    """...and the same for the time word. The seconds field counts TWO-second units, so 30 is 60
    seconds and is the first refused value."""
    with gemdos.bound_handlers({}):
        info = case.run(addrs.GEMDOS_TSETTIME, {"a5": 0, "_pokes": case.word_arg(time)},
                        lambda lib, buf: lib.gemdos_tsettime(buf, time))
    assert info["regs"]["d0"] == addrs.GEMDOS_RANGE_ERROR
    gemdos.assert_the_clock_was_not_published()


# ---- the two bounds TOS 1.02 CANNOT apply ---------------------------------------------------------

@pytest.mark.parametrize("what,word", (
    ("year 120, which `cmp.w #119` was meant to stop", dos_date(120, 1, 1)),
    ("year 127, the widest the field goes", dos_date(127, 12, 31)),
))
def test_the_year_bound_is_dead_code_in_this_rom(what, word):
    """`asr.w #9` on a word yields -64..63, so `<= 119` is true for every one of the 128 years the
    field can hold — and the year bound never refuses anything.

    Read as a SLICE rather than run to `rts`: an accepted date reaches XBIOS `Settime`, which is not
    reconstructed, so what this case can say is exactly that the bound was not taken. It stops at the
    STORE ($fc9e8a), which is the first instruction past every refusal in the routine.
    """
    from harness import emu, make_image

    _final, _writes, regs = emu.run(make_image(case.word_arg(word)), addrs.GEMDOS_TSETDATE,
                                    {"a5": 0}, stop_pc=addrs.GEMDOS_TSETDATE_STORE)
    assert regs["ninsns"] > 0, "the routine refused a date the year bound was supposed to refuse"


@pytest.mark.parametrize("what,word", (
    ("hour 24, which `cmp.l #$c000` was meant to stop", dos_time(24, 0, 0)),
    ("hour 31, the widest the field goes", dos_time(31, 59, 29)),
))
def test_the_hour_bound_is_dead_code_in_this_rom(what, word):
    """...and the same defect in the time word, by a different route: `$fc9ee4` sign-extends the
    masked word to a long before comparing it against 24 << 11, and a word whose only set bits are
    $f800 is below $c000 whether it extends positive or negative. Every hour 0..31 is accepted."""
    from harness import emu, make_image

    _final, _writes, regs = emu.run(make_image(case.word_arg(word)), addrs.GEMDOS_TSETTIME,
                                    {"a5": 0}, stop_pc=addrs.GEMDOS_TSETTIME_STORE)
    assert regs["ninsns"] > 0, "the routine refused a time the hour bound was supposed to refuse"


# ---- the registry ----------------------------------------------------------------------------------
# Every case above, as `test_boot_snapshot.VERIFIED_CASES` rows for the orchestrator to splat. Built
# from the same constructors the tests drive, so a registered row cannot describe a run nobody made.

def _register_all():
    gemdos.register("gemdos_sversion", addrs.GEMDOS_SVERSION, {"a5": 0}, {})
    gemdos.register("gemdos_unimplemented", addrs.GEMDOS_UNIMPLEMENTED, {"a5": 0}, {})
    gemdos.register("gemdos_fgetdta", addrs.GEMDOS_FGETDTA, {"a5": 0}, gemdos.dta_poke(A_DTA))
    gemdos.register("gemdos_fsetdta", addrs.GEMDOS_FSETDTA, {"a5": 0, "d0": ENTRY_D0},
                    case.long_args(A_DTA))
    gemdos.register("gemdos_dgetdrv", addrs.GEMDOS_DGETDRV, {"a5": 0},
                    gemdos.current_drive_poke(0xFF))
    gemdos.register("gemdos_dsetdrv", addrs.GEMDOS_DSETDRV, {"a5": 0}, dsetdrv_pokes(A_DRIVE))
    gemdos.register("gemdos_tgetdate", addrs.GEMDOS_TGETDATE, {"a5": 0},
                    gemdos.date_poke(dos_date(7, 4, 22)))
    gemdos.register("gemdos_tgettime", addrs.GEMDOS_TGETTIME, {"a5": 0},
                    gemdos.time_poke(dos_time(11, 59, 58)))
    gemdos.register("gemdos_tsetdate, a month the year has not got", addrs.GEMDOS_TSETDATE,
                    {"a5": 0}, case.word_arg(dos_date(7, 13, 1)))
    gemdos.register("gemdos_tsettime, a minute past 59", addrs.GEMDOS_TSETTIME, {"a5": 0},
                    case.word_arg(dos_time(11, 60, 0)))


_register_all()
