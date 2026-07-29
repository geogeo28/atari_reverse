"""Pin the kit's Dosound-ledger cap check (`harness.differential`).

XBIOS `Dosound(A0)` writes the YM2149, not the image, so the only thing that catches a wrong or
missing command list is the ordered ledger the harness diffs against the oracle's trap stream. Both
ledgers are fixed-size arrays that stop recording SILENTLY at `OS_DOSOUND_LOG_MAX` — so two streams
that agree for the first 256 calls and diverge at 257 truncate to the same list and compare EQUAL.
`differential()` refuses to compare a saturated ledger at all rather than report that false green.

Joust issues no `Dosound` of its own; the stub below manufactures the overflow. (Its candidate does
link the kit's `dosound_log.c`, so the harness takes the ledger path.)
"""
import pytest

import abi
import harness
from recreate_kit import harness as kit_harness   # OS_DOSOUND_LOG_MAX is a kit constant

_NO_OP_GLUE = lambda lib, buf: None   # noqa: E731 — the cap check fires before any list comparison

DOSOUND_CALLS = kit_harness.OS_DOSOUND_LOG_MAX + 4   # enough to saturate, cheap to run
LIST_ADDR = 0x40300     # only ever logged as a pointer; the model never dereferences the list


def dosound_stub(calls, list_addr):
    """A stub that issues `calls` XBIOS Dosound(list_addr) traps back to back, then returns:

        move.w #calls-1,d1
      loop:
        pea  list_addr ; move.w #$20,-(a7) ; trap #14 ; lea 6(a7),a7 ; dbf d1,loop
        rts

    `dbf` runs the body once more than its counter, hence `calls - 1`. The counter lives in D1
    because every serviced trap returns a result in D0 (0 for Dosound), which would reset it.
    A `dbf` displacement is measured from the word after its opcode, i.e. from `loop + len(body) + 2`.
    """
    body = (b"\x48\x79" + list_addr.to_bytes(4, "big")   # pea  list_addr.l
            + b"\x3f\x3c\x00\x20"                        # move.w #$20,-(a7)   (XBIOS Dosound)
            + b"\x4e\x4e"                                # trap #14
            + b"\x4f\xef\x00\x06")                       # lea  6(a7),a7       (drop fn + arg)
    dbf_disp = -(len(body) + 2) & 0xffff                 # back to `loop`, from just past `51c9`
    return (b"\x32\x3c" + (calls - 1).to_bytes(2, "big") # move.w #calls-1,d1
            + body
            + b"\x51\xc9" + dbf_disp.to_bytes(2, "big")  # dbf  d1,loop
            + b"\x4e\x75")                               # rts


def test_a_saturated_dosound_ledger_is_refused_rather_than_compared():
    with pytest.raises(AssertionError, match="hit its cap"):
        harness.differential(abi.STUB,
                             {"_pokes": {abi.STUB: dosound_stub(DOSOUND_CALLS, LIST_ADDR)}},
                             _NO_OP_GLUE)


def test_a_dosound_stream_below_the_cap_still_compares():
    """The cap check must not swallow the ordinary mismatch report one call short of saturating."""
    calls = kit_harness.OS_DOSOUND_LOG_MAX - 1
    with pytest.raises(AssertionError, match="Dosound ledger mismatch"):
        harness.differential(abi.STUB,
                             {"_pokes": {abi.STUB: dosound_stub(calls, LIST_ADDR)}},
                             _NO_OP_GLUE)
