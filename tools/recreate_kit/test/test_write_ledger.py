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
import re
import struct
from types import SimpleNamespace

import pytest

from kit_smoke_project import HW_READ_ENTRY, MFP_GPIP, MIXER_REG, PORT_DIR_BITS, RMW_ENTRY, SILENCED, bind
from recreate_kit import rom_bench

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


# ---- a BENCH run's ledger (`emu.bench_writes`): its own stores, across its door ---------------------------------------
# A hand-assembled probe the real shim runs (`test_bench_door_stops.py`'s arrangement): two byte stores with a `nop`
# between them, and a second entry storing one other byte.
PROBE_AT = 0x20000                     # the probe's code, above the vector page and the poked block
STORED_AT = 0x20100                    # ...and the bytes it stores
MOVE_B_IMMEDIATE_TO_ABSOLUTE = 0x13FC  # move.b #<byte>,<xxx>.l
NOP, RTS = 0x4E71, 0x4E75
FIRST, SECOND, OTHER = 0x5A, 0xA5, 0x3C


def _store(value, at):
    return struct.pack(">HHI", MOVE_B_IMMEDIATE_TO_ABSOLUTE, value, at)


TWO_STORES = _store(FIRST, STORED_AT) + struct.pack(">H", NOP) + _store(SECOND, STORED_AT + 1) + struct.pack(">H", RTS)
BETWEEN_THE_STORES = PROBE_AT + len(_store(FIRST, STORED_AT))
OTHER_ENTRY = PROBE_AT + len(TWO_STORES)
ONE_STORE = _store(OTHER, STORED_AT + 2) + struct.pack(">H", RTS)


def _probe():
    image = harness.make_image()
    image[PROBE_AT:PROBE_AT + len(TWO_STORES) + len(ONE_STORE)] = TWO_STORES + ONE_STORE
    return image


def test_a_bench_run_s_ledger_holds_its_own_stores_alone():
    """`osh_run_bench` clears the ledger as `osh_run` does: after an `emu.run` that stored two bytes, a bench run that
    stores one reads back that one — not the run before's, and not its own sentinel and argument stores."""
    _final, writes, _regs = emu.run(_probe(), PROBE_AT)
    assert writes.keys() >= {STORED_AT, STORED_AT + 1}, "the premise: the run before stored the two bytes"
    image = _probe()
    emu.run_bench(image, OTHER_ENTRY, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL)
    assert emu.bench_writes(image) == ({STORED_AT + 2: OTHER}, False)


def test_a_bench_run_split_at_its_door_reads_one_ledger():
    """...and `osh_bench_resume` keeps it: a run stopped between its two stores and resumed holds both."""
    image = _probe()
    try:
        stopped = emu.run_bench(image, PROBE_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL,
                                door=frozenset({BETWEEN_THE_STORES}))
        assert stopped["status"] == emu.BENCH_DOOR
        emu.bench_door_arm(None)
        emu.bench_resume(PROBE_AT)
    finally:
        emu.bench_abort()
    assert emu.bench_writes(image) == ({STORED_AT: FIRST, STORED_AT + 1: SECOND}, False)


# ---- a WATCHED original declares no chip the run before it did (`rom_bench.original_entered`) --------------------------
# `emu.run` installs the PSG's and the named hardware set's declarations on EVERY run, "nothing" included; a bench run
# installs neither (an asm twin's run reads what its `run` declared). So a watched original — a bench run of ROM code —
# declares nothing itself, or a read nothing declared is served the previous case's seed and no refusal fires.
NO_STOPS = SimpleNamespace(first=None, stopped=None)    # a watch that never stops: the run is the unwatched one
GPIP_SEED = 0x01
STALE_SEEDS = {"PSG": (RMW_ENTRY, {"psg_seed": {MIXER_REG: PORT_DIR_BITS}},
                       f"read PSG register(s) whose contents nothing declared ({MIXER_REG})"),
               "named hardware": (HW_READ_ENTRY, {"hw_seed": {MFP_GPIP: GPIP_SEED}},
                                  f"read modelled hardware byte(s) nothing declared ({MFP_GPIP:#x}")}


@pytest.mark.parametrize("entry, seeds, refused", STALE_SEEDS.values(), ids=STALE_SEEDS)
def test_a_watched_original_reads_no_seed_the_run_before_it_declared(entry, seeds, refused):
    """RED without `emu.install_chip_seeds()` in the watched entry: right after a run declaring the chip, the watched
    original's read of it is refused as undeclared — exactly as `emu.run`'s own would be."""
    emu.run(harness.make_image(), entry, **seeds)
    rom_bench.watched_original(bytearray(harness.make_image()), entry, NO_STOPS)
    with pytest.raises(AssertionError, match=re.escape(refused)):
        rom_bench.vet_the_run_just_made("the watched original")
