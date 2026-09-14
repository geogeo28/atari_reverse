"""One ROM case, spelt once: what every battery in this project does around `harness.differential`.

A case is always the same four steps — run both cores over the same image, refuse any byte that
differs, check the candidate's return value against the D0 the ROM left, and hand the oracle's report
back for the battery's own claims. Sixteen batteries kept a private copy of those four lines, and the
copies had already started to differ: one compared `ret` against the whole of D0 where the core
returned a word, another did not compare it at all. The check belongs where it cannot drift.

WHAT STAYS IN THE BATTERY is everything that is a claim about the routine — which registers it is
entered with, what its arguments are, and what the result should be. This module only removes the
staging that is the same for all of them.
"""
import struct

import abi
from harness import differential, report

# The width of a result, as the C signature declares it. A core that returns nothing (`void` — the
# ROM routine sets no result, or reports only through memory) says so with `None`, which is a claim
# too: the case then requires the candidate glue to return nothing rather than skipping the check.
FULL_D0 = 32
NO_RESULT = None


def run(entry, regs, glue, *, width=FULL_D0, poison=True):
    """One differential at `entry`. Returns the oracle's `info` once everything always-checked holds.

    `regs` are the oracle's input registers plus the case's `_pokes`; `glue(lib, buf)` runs the
    candidate over the same image. `width` is the result width — see `assert_result_is_d0`. `poison`
    runs the attribution pass, which is what makes a store the candidate SKIPPED visible when the
    byte already held the right value; it is on by default because these are leaf routines, and a
    battery that turns it off says why.
    """
    diffs, info = differential(entry, regs, glue, poison=poison)
    assert not diffs, report(diffs)
    assert_result_is_d0(info, width)
    return info


def assert_result_is_d0(info, width=FULL_D0):
    """The candidate's return value against the D0 the ORIGINAL left, at the declared width.

    The image diff says nothing about a register, so this is the only thing that compares the two
    results at all. At `FULL_D0` it is the whole of D0, which is the honest width for every core
    here: a routine that writes only D0's low word takes the caller's D0 as an argument and returns
    the whole register, so that the high half it did NOT write is compared too. A narrower width
    would agree with a reconstruction that cleared what the ROM left alone.
    """
    if width is NO_RESULT:
        assert info["ret"] is None, (
            f"the candidate returned {info['ret']!r} where the ROM routine sets no result — either "
            f"the glue is returning something it should not, or the core is not `void`")
        return
    mask = (1 << width) - 1
    assert info["ret"] == (info["regs"]["d0"] & mask), (
        f"the candidate returned {info['ret']:#x} where the ROM left {info['regs']['d0']:#x} in D0")


def written(info, address, size):
    """The `size`-byte big-endian value the ORACLE left at `address`, out of its own write ledger.

    Deliberately not a read of the final image: a field the routine never stored is then a KeyError
    naming it, rather than a stale byte that happens to read right.
    """
    return int.from_bytes(bytes(info["writes"][address + i] for i in range(size)), "big")


def written_long(info, address):
    """...the longword, which is what most of these routines store."""
    return written(info, address, 4)


def word_args(*values):
    """The argument WORDS a case stages, where the dispatcher's caller would have left them.

    `abi.FIRST_ARG` is 4(A7) — one longword of return address above the stack pointer `emu.run`
    plants, which is the frame a `jsr` leaves and therefore the frame every BIOS/XBIOS routine reads
    its arguments out of.
    """
    return {abi.FIRST_ARG: struct.pack(f">{len(values)}H", *(value & 0xFFFF for value in values))}


def word_arg(value):
    """...and the single-word case, which is most of them."""
    return word_args(value)
