"""Shared driver for the game's LEAF routines — the ones with no callee, no hardware and a write
set small enough to name.

`test_effects.py` and `test_input.py` are both batteries of such functions, so the two things they
would otherwise each restate live here: where a function starts (looked up in `../names.txt`, the
workspace's source of truth for names, rather than restated as a number) and what counts as a write
it was not entitled to make.

NOT a general harness — the kit is that. This module assumes what a leaf gives it: a run short
enough for a tight instruction cap, and a write set the caller can enumerate up front.
"""
import ctypes

import harness
from harness import differential, report

import emu                                                       # noqa: E402

# These functions are 8 to 38 bytes long and execute at most six instructions. The cap is deliberately
# far below the kit's default: a case that entered the wrong address and ran off into the game would
# otherwise return a plausible-looking result instead of failing.
LEAF_INSN_CAP = 64

# Every address in ../names.txt that carries a name, inverted. Two functions sharing a name would
# make `entry_of` ambiguous, so the inversion is checked rather than assumed.
_ADDRS_BY_NAME = {}
for _addr, _name in harness.NAME_MAP.items():
    _ADDRS_BY_NAME.setdefault(_name, []).append(_addr)


def entry_of(name):
    """The runtime address ``../names.txt`` gives ``name``.

    The tests take entry points from the name map rather than from a table of their own, so a
    function that moves or is renamed there fails as a missing name at collection time instead of
    running the oracle at a stale address. The map is only half the pin: each battery also compares
    the bytes AT the address against the instruction it believes is there.
    """
    addrs = _ADDRS_BY_NAME.get(name, [])
    assert len(addrs) == 1, (
        f"{name!r} names {len(addrs)} address(es) in {harness.NAMES} ({[hex(a) for a in addrs]}) — "
        f"a leaf case needs exactly one entry point")
    return addrs[0]


def bind(name, argtypes, restype=None):
    """Bind one candidate symbol's ctypes signature and return it."""
    fn = getattr(harness._lib, name)
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


IMAGE_ARG = [ctypes.POINTER(ctypes.c_uint8)]


def image_glue(name):
    """Differential glue for a reconstruction whose only argument is the image.

    The kit calls glue as ``glue(lib, image)`` and most leaves take the image and nothing else, so
    binding one is the same line every time. The bound symbol is captured by this call rather than
    by a comprehension's loop variable, which is the idiom this replaces.
    """
    fn = bind(name, IMAGE_ARG)
    return lambda _lib, image: fn(image)


def stray_writes(writes, allowed):
    """Oracle writes outside ``allowed`` (an iterable of (addr, length) the function may touch).

    The machine stack is the one implicit permission: the oracle enters with A7 at
    ``emu.STACK_TOP`` and the stack grows DOWN, so the band is bounded on BOTH sides — a write at or
    above STACK_TOP is not a call frame however close to the stack it looks. (test_rad_depack.py
    calls this as well; STATUS.md registers the family and the kit as its proper home.)
    """
    def permitted(addr):
        if emu.STACK_TOP - emu.STACK_SCRATCH <= addr < emu.STACK_TOP:
            return True
        return any(lo <= addr < lo + length for lo, length in allowed)

    return sorted(a for a in writes if not permitted(a))


def run(name, glue, allowed, what, regs=None, poison=True):
    """Run ``name``'s original under the oracle and the reconstruction on the same image.

    Requires the two to agree byte for byte over the whole image, and the original to have written
    nothing outside ``allowed``. Returns the differential's ``info`` so a caller can also assert on
    the returned d0. ``poison`` runs the kit's attribution pass, which is what stops a case passing
    because the destination already held the value the function writes; a caller turns it off only
    when inverting an output would corrupt an ADDRESS the run then stores through.
    """
    diffs, info = differential(entry_of(name), dict(regs or {}), glue,
                               max_insns=LEAF_INSN_CAP, poison=poison)
    assert not diffs, f"{what}\n{report(diffs)}"
    stray = stray_writes(info["writes"], allowed)
    assert not stray, (
        f"{what}: {len(stray)} write(s) outside {[(hex(a), n) for a, n in allowed]}, e.g. "
        f"{harness.label(stray[0])} @ {stray[0]:#x}")
    return info


def assert_entry_is(name, expected):
    """Pin the bytes at ``name``'s entry against the instruction(s) the battery believes are there.

    This is what makes a wrong constant fail where it is wrong: the encodings below carry the
    destination address and the immediate as operands, so one assert covers the entry point from
    ../names.txt, the global from include/wonderboy.h, the value, and the operand size all at once.
    """
    entry = entry_of(name)
    actual = bytes(harness.BASE_IMAGE[entry:entry + len(expected)])
    assert actual == expected, (
        f"{name} @ {entry:#x} is {actual.hex()}, not the {expected.hex()} this battery reconstructs")
