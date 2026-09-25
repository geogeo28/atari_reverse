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
from harness import differential, make_image, report

# The width of a result, as the C signature declares it. A core that returns nothing (`void` — the
# ROM routine sets no result, or reports only through memory) says so with `None`, which is a claim
# too: the case then requires the candidate glue to return nothing rather than skipping the check.
FULL_D0 = 32
NO_RESULT = None


def run(entry, regs, glue, *, width=FULL_D0, poison=True, **seeds):
    """One differential at `entry`. Returns the oracle's `info` once everything always-checked holds.

    `regs` are the oracle's input registers plus the case's `_pokes`; `glue(lib, buf)` runs the
    candidate over the same image. `width` is the result width — see `assert_result_is_d0`. `poison`
    runs the attribution pass, which is what makes a store the candidate SKIPPED visible when the
    byte already held the right value; it is on by default because these are leaf routines, and a
    battery that turns it off says why.

    `seeds` are `harness.differential`'s remaining keyword arguments — `io_seed`, `psg_seed`,
    `schedule`, `wait_sites` — forwarded rather than enumerated. Every one of them is a DECLARATION
    the case makes about the machine, and the four steps around it are the same whichever is
    present, so naming them here would be a second list to keep level with the kit's.
    """
    diffs, info = differential(entry, regs, glue, poison=poison, **seeds)
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


def hardware_reads(info):
    """The ORACLE's two ordered read streams as one list, `[(address, value), ...]`.

    WHICH of them a byte lands in is the kit's bookkeeping — a Phase-7 NAMED slot goes through
    `hw_read8` and an ordinary declared byte through `io_read8` — and a case declares both through
    the one `io_seed` door, so a battery that cared which would be asserting the kit's routing
    rather than the routine's traffic.
    """
    return (list(info["regs"]["hw_events"])
            + [(address, value) for address, _width, value in info["regs"]["io_events"]])


def hardware_writes(info):
    """...and the ordered WRITE ledger (Phase 10), which is the whole of what a data port leaves."""
    return [(address, value) for address, _width, value in info["regs"]["hw_writes"]]


def long_in(image, address):
    """The big-endian LONGWORD `image` holds at `address` — a snapshot, a staged image or a run's
    final one, all of which are byte sequences a battery indexes.

    The GEMDOS wave alone had six private copies of this and its word twin, under three names and
    two argument orders. It is not about any routine, so it belongs where a battery can reach it
    without importing another battery's module; the spelling is `test/isr.py`'s `long_in_snapshot`,
    which is this function with `BASE_IMAGE` bound.
    """
    return int.from_bytes(bytes(image[address:address + 4]), "big")


def word_in(image, address):
    """...and the word."""
    return int.from_bytes(bytes(image[address:address + 2]), "big")


def args(fmt, *values):
    """The argument frame a case stages, as `struct` spells it — for the shapes the three helpers
    below do not cover (`Mshrink`'s reserved word and then two longwords is the one).

    `abi.FIRST_ARG` is 4(A7) — one longword of return address above the stack pointer `emu.run`
    plants, which is the frame a `jsr` leaves and therefore the frame every BIOS/XBIOS/GEMDOS
    routine reads its arguments out of.
    """
    return {abi.FIRST_ARG: struct.pack(fmt, *values)}


def word_args(*values):
    """The argument WORDS a case stages, where the dispatcher's caller would have left them."""
    return args(f">{len(values)}H", *(value & 0xFFFF for value in values))


def word_arg(value):
    """...and the single-word case, which is most of them."""
    return word_args(value)


def long_args(*values):
    """The argument LONGWORDS, which is what GEMDOS takes where the BIOS takes words — a DTA
    pointer, a block address, the MPB the allocator core is handed beside its own argument."""
    return args(f">{len(values)}I", *(value & 0xFFFF_FFFF for value in values))


def final_image(info, pokes):
    """The image the ORACLE ended with: the staged one, with its own write ledger laid over it.

    `harness.differential` hands a battery the write LEDGER rather than the final image, which is the
    sharper thing for a field the routine stores — a `KeyError` names a field nothing wrote — but a
    case that asserts about a LIST, a queue or a whole sector is mostly reading bytes it poked and
    the routine left alone. The ledger IS the final value at every address it names, so the two
    layers together are the run's last state.

    A run that overflowed the ledger would make that false SILENTLY, so it is refused here rather
    than quietly reconstructed from a partial list. Six batteries had a private copy of these four
    lines and only one of them carried that refusal.
    """
    assert not info["regs"].get("writes_truncated"), (
        "the oracle's write ledger overflowed, so the image rebuilt from it would be missing stores "
        "— shorten the run or read the fields this case needs out of `info[\"writes\"]` directly")
    image = make_image(pokes)
    for at, value in info["writes"].items():
        image[at] = value
    return image
