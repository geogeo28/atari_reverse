"""XBIOS Vsync (function $25) @ $fc07d0 — wait for the next vertical blank.

THE FIRST RECONSTRUCTION IN THIS PROJECT THAT DOES NOT TERMINATE ON ITS OWN. The whole routine is a
spin on `_frclock` ($466), the longword the VBL handler at $fc06de opens by incrementing — and
nothing in this body writes it. Under the oracle no interrupt fires and the candidate is
single-threaded C, so the loop is infinite on BOTH sides and the routine is not runnable at all until
a case says what the interrupt did.

THE SCHEDULED-WRITE MODEL IS THAT CASE (TRAP_MODEL.md, Phase 8). An external agent stores the new
`_frclock` just before the Nth execution of the spin's own `cmp.l` at VSYNC_WAIT_SITE ($fc07dc), from
one list installed on both shores; the candidate, which has no program counter, polls once per
iteration NAMING that site, and `harness._vet_schedule_ran_the_same_wait` compares the oracle's
arrivals against the candidate's polls site by site. That comparison is the whole cross-check: the
store lands on both sides from the same list, so a port that spun a different number of times — or
did not spin at all — ends with byte-identical memory and is separable by nothing else.

WHAT IS PINNED IS "GIVEN THAT THE BLANK CAME AT ITERATION N, BOTH CORES AGREE", which is the model's
stated limit and not a claim about when a real VBL arrives. Driven at more than one `nth` because the
model documents one hole at exactly one: a port that polls twice per iteration is invisible at an
`nth` that is a multiple of its polling rate.

IT WAITS FOR A CHANGE AND NOT FOR AN INCREMENT. `cmp.l`/`beq` releases on anything that makes the
longword differ from the sample, so a counter that went BACKWARDS ends the wait exactly as the
handler's `addq.l #1` does. That is reachable — a program may reset `_frclock` — and is its own case
below.

WHAT IT LEAVES IN D0 is the `_frclock` sampled BEFORE the wait: `move.l $466,d0` is the last
instruction to touch the register. Not a documented return value, and exactly what the differential
compares.

NOT IN `test_boot_snapshot.VERIFIED_CASES` AND WITH NO TIER 3 ROW, and the reason is structural
rather than an omission: that list's entries carry an entry, registers, pokes and the two seeds, with
nowhere to put a `schedule`, and `emu.run_bench` — Tier 3's numerator door — has no schedule door at
all, so the m68k build's own spin could never be released. Both would have to grow one; the
orchestrator carries that as the next kit item, and until it lands **TIER 3 CANNOT PRICE THIS
ROUTINE** — the cycle count below is the ORIGINAL's alone, a denominator with no numerator beside
it. That also leaves this core's `os_ipl_unmask`/`os_ipl_restore` pair with no Tier 3 row to move
when it vanishes, which is where every other `ipl.h` bracket is pinned; what stands in for it is the
kit's `test_ipl_target_half.py`, which compiles the target header and pins the two instructions the
unmask emits and their ORDER.

`$466` is outside `boot_snapshot.MASK` (asserted below), which is the coverage the snapshot list
would have added here; the function number this routine answers to is read out of the ROM's own
XBIOS table below, which is the other thing that list's entries buy.
"""
import ctypes
import sys
from pathlib import Path

import pytest

from harness import BASE_IMAGE, _lib, addrs, differential, emu, in_diff, make_image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import boot_snapshot                                       # noqa: E402

import case                                                # noqa: E402

_lib.xbios_vsync.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.xbios_vsync.restype = ctypes.c_uint32

# The frame clock the captured snapshot holds — the capture stops inside the VBL handler itself, so
# it is a real count rather than a number this file invented. Asserted in its own case below.
SNAPSHOT_FRCLOCK = 0x35D
FRCLOCK_BYTES = 4


def clock_poke(clock):
    return {addrs.SYSVAR_FRCLOCK: clock.to_bytes(FRCLOCK_BYTES, "big")}


def blank_at(iteration, new_clock):
    """The external agent's store: `new_clock` into `_frclock`, just before the `iteration`th
    execution of the spin's own compare. One entry, which is one vertical blank."""
    return [{"pc": addrs.VSYNC_WAIT_SITE, "nth": iteration, "addr": addrs.SYSVAR_FRCLOCK,
             "width": FRCLOCK_BYTES, "value": new_clock}]


def run(iteration, entry_clock=SNAPSHOT_FRCLOCK, new_clock=None):
    """One differential of XBIOS Vsync whose blank arrives at `iteration`. Returns its info.

    POISON IS OFF and the model requires it: the attribution pass inverts every oracle-written byte
    and re-runs, but the agent's store is applied from the same list on both sides and overwrites the
    canary, so the pass would report an attribution it did not make. `differential` refuses the
    combination rather than serving it.
    """
    new_clock = entry_clock + 1 if new_clock is None else new_clock
    return case.run(addrs.XBIOS_VSYNC, {"a5": 0, "_pokes": clock_poke(entry_clock)},
                    lambda lib, buf: lib.xbios_vsync(buf),
                    schedule=blank_at(iteration, new_clock), poison=False)


def test_the_snapshot_holds_the_frame_clock_the_capture_stopped_at():
    assert int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_FRCLOCK:
                                           addrs.SYSVAR_FRCLOCK + FRCLOCK_BYTES]),
                          "big") == SNAPSHOT_FRCLOCK


def test_the_xbios_table_still_dispatches_function_0x25_here():
    """WHAT A `VERIFIED_CASES` ROW WOULD HAVE BOUGHT, part two: every other reconstruction is held to
    its dispatch-table entry by `test_boot_snapshot.py`, which derives that list from the register
    this routine cannot be in. So the same read is made here, once, out of the mapped ROM — a wrong
    `XBIOS_VSYNC` in `addrs.h` would otherwise leave this whole battery verifying some other routine.

    `test_boot_snapshot._trap_table` is imported rather than copied: the table's shape (a count, then
    that many longwords) is that file's claim, and a second reading of it is what drifts."""
    import test_boot_snapshot as snapshot

    count, entries = snapshot._trap_table(addrs.XBIOS_FUNCTION_TABLE)
    assert count > addrs.XBIOS_VSYNC_FN, "Vsync's function number is past the table's own count"
    assert entries[addrs.XBIOS_VSYNC_FN] == addrs.XBIOS_VSYNC


def test_the_frame_clock_is_not_a_byte_the_capture_disagrees_about():
    """What a `VERIFIED_CASES` row would have bought, said directly. Two captures of the same boot
    differ in 1,929 bytes of AES and desktop scratch; a routine resting on one of them is verified
    against one particular boot. `_frclock` is not among them — the stop is at a fixed vertical-blank
    count — and this is what says so for the one function that reads it."""
    for address, length, _name in boot_snapshot.MASK:
        assert max(address, addrs.SYSVAR_FRCLOCK) >= min(address + length,
                                                         addrs.SYSVAR_FRCLOCK + FRCLOCK_BYTES), (
            f"boot_snapshot.MASK covers _frclock at {addrs.SYSVAR_FRCLOCK:#x}, which Vsync spins on")


# ---- the wait itself ------------------------------------------------------------------------------

@pytest.mark.parametrize("iteration", (1, 2, 3, 7))
def test_it_returns_on_the_iteration_the_blank_arrives_and_not_before(iteration):
    """THE CASE THIS BATTERY EXISTS FOR, at four arrival counts.

    `nth = 1` fires the store before the very first compare, so the wait ends in one iteration; every
    other `nth` spins exactly that many times. The claim is the COUNT, compared against the
    candidate's polls by the harness on every case here — and driven at more than one value because
    the model's one measured hole is an `nth` that aliases a port's polling rate.
    """
    info = run(iteration)
    assert info["regs"]["sched_site_arrivals"] == (iteration,), (
        f"the ROM's spin re-read _frclock {info['regs']['sched_site_arrivals']} time(s) where the "
        f"blank was scheduled for iteration {iteration}")
    assert info["regs"]["sched_applied"] == 1, "the scheduled blank never came due"


@pytest.mark.parametrize("iteration", (1, 2, 3, 7))
def test_it_reports_the_frame_clock_it_sampled_before_the_wait(iteration):
    """`move.l $466,d0` happens once, above the loop, and nothing touches D0 afterwards — so the
    result is the clock BEFORE the blank and never the one after it. A reconstruction that returned
    what the wait had seen would differ by exactly one on every case here."""
    info = run(iteration)
    assert info["regs"]["d0"] == SNAPSHOT_FRCLOCK


@pytest.mark.parametrize("entry_clock", (0, 1, 0x7FFF_FFFF, 0xFFFF_FFFE, SNAPSHOT_FRCLOCK))
def test_the_clock_is_compared_as_a_whole_longword(entry_clock):
    """`cmp.l`, not `cmp.w` or a byte test: the counter is bumped 50 or 60 times a second, so a
    reconstruction comparing a narrower slice of it is right for hours and then hangs. Each of these
    changes only a part of the longword when it is incremented — $7fffffff crosses the sign,
    $fffffffe the top byte, and 0 and 1 leave the high three bytes alone."""
    info = run(2, entry_clock=entry_clock)
    assert info["regs"]["d0"] == entry_clock
    assert info["regs"]["sched_site_arrivals"] == (2,)


def test_a_clock_that_goes_backwards_ends_the_wait_too():
    """`cmp`/`beq` is a test for DIFFERENCE. A program that resets `_frclock` while a caller is
    inside `Vsync` releases it, and a reconstruction written as `while (now <= start)` — the obvious
    C for "wait for the next frame" — spins on instead."""
    info = run(3, entry_clock=SNAPSHOT_FRCLOCK, new_clock=0)
    assert info["regs"]["sched_site_arrivals"] == (3,)
    assert info["regs"]["d0"] == SNAPSHOT_FRCLOCK


def test_it_writes_nothing_of_its_own_outside_the_stack():
    """The only memory this routine stores is its own `move.w sr,-(sp)` — inside the band the diff
    drops, which is where a machine stack belongs. Everything else that moved is the AGENT's store,
    and the chip is untouched: no palette, no shifter, no declared read.

    Said as "no write lands in compared image" rather than "no write at all", because the SR push IS
    a store and a case that claimed otherwise would be describing a different routine."""
    info = run(2)
    landed = sorted(address for address in info["writes"] if in_diff(address))
    assert landed == [], f"Vsync stored into compared image at {[hex(a) for a in landed]}"
    assert info["regs"]["hw_writes"] == [] and info["regs"]["io_events"] == []


# ---- what the model refuses, over this routine ------------------------------------------------------

def test_without_a_schedule_the_original_does_not_return():
    """THE STATE EVERY SUCH ROUTINE IS IN BEFORE THE MODEL, driven rather than described: with no
    scheduled blank the ROM's own loop runs to the oracle's instruction cap and the run is refused.

    It is the negative control the whole file rests on — without it, every case above would be
    compatible with a `Vsync` that never waited at all.
    """
    with pytest.raises(Exception) as raised:
        emu.run(make_image(), addrs.XBIOS_VSYNC, {"a5": 0}, max_insns=5000)
    assert "5000" in str(raised.value) or "cap" in str(raised.value).lower(), (
        f"the unreleased spin ended for a reason other than the instruction cap: {raised.value}")


def test_a_blank_that_does_not_change_the_clock_never_releases_the_wait():
    """...and the other half: an agent that stores the value already there is not a blank. The store
    comes due, the compare still matches, and the run hits the cap — which is what says the release
    is the COMPARISON's and not the store's."""
    with pytest.raises(Exception) as raised:
        differential(addrs.XBIOS_VSYNC,
                     {"a5": 0, "_pokes": clock_poke(SNAPSHOT_FRCLOCK)},
                     lambda lib, buf: lib.xbios_vsync(buf),
                     schedule=blank_at(2, SNAPSHOT_FRCLOCK), max_insns=5000)
    assert "5000" in str(raised.value) or "cap" in str(raised.value).lower(), str(raised.value)


def test_the_oracles_cost_is_what_status_reports():
    """The ORIGINAL's cost for one case — the Tier 3 DENOMINATOR this routine has no numerator for
    (see the module docstring). It is a function of the arrival count, so the case that pins it is
    the one-iteration wait; `ninsns` counts one more than the instructions executed."""
    _final, _writes, regs = emu.run(make_image(clock_poke(SNAPSHOT_FRCLOCK)), addrs.XBIOS_VSYNC,
                                    {"a5": 0}, schedule=blank_at(1, SNAPSHOT_FRCLOCK + 1))
    assert (regs["ninsns"], regs["cycles"]) == (8, 156), (
        f"Vsync's one-iteration wait now costs {regs['ninsns']} insns / {regs['cycles']} cycles — "
        f"STATUS.md's cost column for this row is stale")
