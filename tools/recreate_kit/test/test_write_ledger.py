"""Pin the WRITE ledger's truncation: reported by `emu.run`, refused by `harness.differential`.

`shim.c` records the address of every byte a run stores into `g_waddr`, and `logw` SATURATES at
`MAX_WRITES` — it stops recording and counts nothing. `emu.run` hands the addresses back as a dict
keyed by ADDRESS, so a caller counting them sees distinct BYTES and cannot tell a capped run from a
complete one: a write-band check made against that dict would read as "the run wrote nowhere else"
while being blind past the cap. The PSG and hardware ledgers each count what they dropped and
`emu.run` names the drop as a cause; this is the third ledger and, until now, the only one that
truncated in silence.

WHY IT IS REPORTED AND NOT REFUSED — the half of this worth reading. Truncation FABRICATES nothing:
the final memory is the run's own and so is every register, and only one ancillary product is
incomplete. So a bare `emu.run` caller that never looks at the write set is served, which is not a
hypothetical — a Copylock run into the protection blob fills the ledger honestly and is compared on
its MEMORY. `harness.differential` is where a write set becomes a CLAIM, so that is where it is
refused. Both halves are cases below, because a "fix" in either direction looks like tidying.

WHY THE CAP IS LOWERED RATHER THAN THE COUNTER RAISED. Filling the ledger honestly means a run that
stores four million bytes — minutes of emulation for a case about one comparison. The branch is
`osh_num_writes() >= MAX_WRITES`, so moving either side of it exercises the same code; lowering the
Python mirror is the cheap side and leaves the oracle untouched. It is lowered to ZERO, which is the
one value that holds for ANY routine: a ledger with no room is full before the run starts, so the
case does not also depend on how many bytes its .PRG routine happens to store. The mirror's own
VALUE is not this file's to check — `emu` refuses to import against a `liboracle.so` whose
`osh_max_writes()` disagrees with it, which is a stronger guard than a case could be.

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).
"""
import pytest

from kit_smoke_project import RMW_ENTRY, MIXER_REG, PORT_DIR_BITS, SILENCED, bind

harness = bind()
emu = harness.emu

# A ledger with no room at all: `osh_num_writes() >= 0` holds for every run, so the branch is taken
# here and not under the real mirror, whatever the routine below stores.
CAP_NOTHING_FITS = 0


def _emu_run():
    """The .PRG's read-modify-write through a bare `emu.run` — the caller shape that is SERVED."""
    return emu.run(harness.make_image(), RMW_ENTRY, psg_seed={MIXER_REG: PORT_DIR_BITS})


def _differential():
    """...and the same routine through the layer that turns a write set into a claim."""
    return harness.differential(RMW_ENTRY, {}, lambda lib, buf: lib.g_psg_rmw(buf),
                                psg_seed={MIXER_REG: PORT_DIR_BITS})


def test_a_bare_run_reports_the_truncation_instead_of_refusing_it(monkeypatch):
    """The report. `emu.run` returns the run — its memory is not in question — and says in
    `out_regs` that the write set it handed back is short."""
    monkeypatch.setattr(emu, "MAX_WRITES", CAP_NOTHING_FITS)
    _, _, out_regs = _emu_run()
    assert out_regs["writes_truncated"] is True, (
        "a run past the cap did not report its write ledger as truncated, so a caller reading the "
        "write set has no way to learn it is incomplete")
    assert out_regs["psg"] == [(MIXER_REG, SILENCED)], (
        "the run itself did not happen, so this case is about nothing")


def test_a_differential_whose_oracle_filled_the_ledger_is_refused_by_name(monkeypatch):
    """The refusal, and the message that tells the reader which knob moves it."""
    monkeypatch.setattr(emu, "MAX_WRITES", CAP_NOTHING_FITS)
    with pytest.raises(AssertionError, match="filled the write ledger"):
        _differential()


def test_both_run_clean_under_the_real_cap():
    """The control for both. Without it either case above would pass on a run that was refused for
    some other reason entirely, or on a differential that never compared anything."""
    _, _, out_regs = _emu_run()
    assert out_regs["writes_truncated"] is False, (
        "a routine that stores no image byte reports its write ledger full — MAX_WRITES has "
        "drifted from the shim's cap, or the counter is not being reset between runs")
    diffs, _ = _differential()
    assert diffs == [], "the differential this file refuses when truncated does not pass otherwise"
