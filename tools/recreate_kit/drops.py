"""DROPPED SPANS: a documented divergence a differential leaves out of its compare, held as DATA.

A drop is for a difference BY NATURE between the original and a reconstruction — a return address each build
parks where the ROM parks its own, a trap frame's saved PC, a record the reconstruction documents it omits —
never for scratch (the kit's `exclude` is that, and is kept to stack bands). Both tiers drop through this module:
`harness.differential` (Tier 1) and `rom_bench.RomBench.measure` (Tier 3). It imports nothing, so neither tier
has to import the other to share the one rule a drop is held to (`vet_dropped`).

A drop has two shapes, and they differ in WHOSE run decides their extent:

* a SPAN — `(lo, hi, why)` — is fixed: the case names its bytes, and every one of them must be a byte the
  ORIGINAL's plain run stores.
* a WINDOW — the same shape — is cut per RUN to the bytes that run stores (`written_within`): a machine stack the
  ROM's frames land in (with the holes a `link` reserves), a record armed only on the path that nests. The rest
  of a window is compared like any other byte.
"""
from typing import NamedTuple


class Dropped(NamedTuple):
    """What one differential leaves out of its compare: fixed `spans` and per-run `windows`, each `(lo, hi, why)`."""
    spans: tuple = ()
    windows: tuple = ()


NOTHING_DROPPED = Dropped()


def within(address, spans):
    """Is `address` inside one of `spans` — `(lo, hi)` pairs, or `(lo, hi, why)` drops?"""
    return any(span[0] <= address < span[1] for span in spans)


def written_within(windows, writes):
    """Each `(lo, hi, why)` of `windows` cut down to the runs of it `writes` (a write ledger) covers."""
    spans = []
    for lo, hi, why in windows:
        start = None
        for address in range(lo, hi + 1):
            if address < hi and address in writes:
                start = address if start is None else start
            elif start is not None:
                spans.append((start, address, why))
                start = None
    return spans


def _vet_reasons(who, spans):
    """Every span and window names why it is dropped, and holds at least one byte."""
    for lo, hi, why in spans:
        if not why or not lo < hi:
            raise AssertionError(
                f"{who} drops [{lo:#x}, {hi:#x}) with {'no reason' if not why else 'no bytes'} — a "
                f"span is left out of the comparison only as a documented difference, and only a real one")


def vet_dropped(who, dropped, writes, truncated=False):
    """Each `(lo, hi, why)` a comparison drops must be a span the ORIGINAL writes, EVERY BYTE of it.

    THE ONE RULE for a drop, whichever differential makes it: `RomBench.measure`'s (`who` a row) and a
    project's Tier 1 case (`who` a case), each handing the ORIGINAL's write ledger (`emu.run`'s `writes`,
    `{address: byte}`) and whether that ledger overflowed — an incomplete one cannot vouch for a byte.

    The rule that tells a difference by nature from scratch is checked here rather than trusted: the original's
    run must STORE every dropped byte. A byte it never stores can only be hiding OUR stores, which is the output the
    comparison is for; so a span holding one is refused — PER BYTE, since a span the original writes only in part (a
    longword parked, the longword after it widened into the drop) hides ours in the rest — as a span with no reason
    or no bytes is.

    WHAT THIS CANNOT SEE is a wrong value ours writes INSIDE a span the original also writes — that is
    what dropping it means — so a project drops at Tier 3 only what its Tier 1 differential still
    compares, where the host build parks the value the ROM does.
    """
    if dropped and truncated:
        raise AssertionError(
            f"{who} drops {len(dropped)} span(s) over a run whose write ledger overflowed — the ledger cannot "
            f"say the original stores every byte of them. Shorten the run, or drop nothing")
    _vet_reasons(who, dropped)
    for lo, hi, why in dropped:
        unwritten = [address for address in range(lo, hi) if address not in writes]
        if unwritten:
            raise AssertionError(
                f"{who} drops [{lo:#x}, {hi:#x}) ({why}), {len(unwritten)} byte(s) of which the ORIGINAL "
                f"never writes, the first at {unwritten[0]:#x} — the drop can only hide our build's stores "
                f"there. Drop only what the original writes")


def plain_run_spans(who, dropped, writes, truncated):
    """The bytes the PLAIN run leaves out: the fixed spans and the windows cut by this run's `writes`, vetted.

    A window's reason is vetted even where the run stores none of it, so a reasonless window cannot pass by
    being empty on the path one case takes."""
    _vet_reasons(who, dropped.windows)
    spans = (*dropped.spans, *written_within(dropped.windows, writes))
    vet_dropped(who, spans, writes, truncated)
    return spans


def rerun_window_spans(who, dropped, writes, truncated):
    """The bytes a RE-RUN of the same case (an attribution pass over a poisoned image) leaves out BEYOND the plain
    run's: its windows cut by ITS `writes`, since poisoning can steer it to store a different part of a window.

    The fixed spans are not vetted again: they were vetted against the plain run, which is the run the case
    describes, and a re-run that poisoning steers past one of them would refuse a correct case for a path the case
    never takes."""
    spans = tuple(written_within(dropped.windows, writes))
    vet_dropped(who, spans, writes, truncated)
    return spans
