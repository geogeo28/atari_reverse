"""Shared driver for the game's LEAF routines — the ones with no callee, no hardware and a write
set small enough to name.

`test_effects.py`, `test_hud.py`, `test_input.py` and `test_scroll.py` are all batteries of such
functions, so what they would otherwise each restate lives here: where a function starts (looked up
in `../names.txt`, the workspace's source of truth for names, rather than restated as a number),
what counts as a write it was not entitled to make, the operand encodings a battery pins its entry
points against, and how a case reads a value back out of the oracle's write set.

NOT a general harness — the kit is that. This module assumes what a leaf gives it: a run short
enough for a tight instruction cap, and a write set the caller can enumerate up front.
"""
import ctypes

import harness
from harness import differential, report

import emu                                                       # noqa: E402

# The straight-line leaves are 8 to 38 bytes long and execute at most six instructions. The cap is
# deliberately far below the kit's default: a case that entered the wrong address and ran off into
# the game would otherwise return a plausible-looking result instead of failing. A battery whose
# routines LOOP (the panel blits move up to 32 rows) passes `run(..., max_insns=)` with its own cap,
# derived from that routine's own geometry for the same reason.
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


def register_glue(name, argtypes, restype=None):
    """Glue factory for a leaf whose ENTRY REGISTERS are its arguments.

    ``image_glue`` covers the routines that take only the image. These take the image plus the 68000
    registers the original is entered with — a source pointer in a0, a packed-BCD addend in d0 — so
    the symbol is bound once and each case supplies its own register values:

        blit = leaf.register_glue("hud_blit_cell_or", [ctypes.c_uint32] * 2)
        leaf.run("hud_blit_cell_or", blit(source, destination), ...)

    The C takes one ``uint32_t`` per register whatever operand size the original uses, so the
    truncation the original does (`move.w d0,...` on a longword register) happens in the
    reconstruction where a case can pin it, and not in the glue where it could not.
    """
    fn = bind(name, IMAGE_ARG + list(argtypes), restype)

    def with_registers(*values):
        return lambda _lib, image: fn(image, *values)

    return with_registers


def on_machine_stack(addr):
    """Whether ``addr`` is inside the band the run's own call frames occupy.

    The oracle enters with A7 at ``emu.STACK_TOP`` and the stack grows DOWN, so the band is bounded
    on BOTH sides: a write at or above STACK_TOP is not a call frame however close to the stack it
    looks — the longword AT STACK_TOP is the return address the runner planted, which a routine that
    rewrites it (`addq.l #4,(a7)`) is being watched for rather than excused for.
    """
    return emu.STACK_TOP - emu.STACK_SCRATCH <= addr < emu.STACK_TOP


def stray_writes(writes, allowed):
    """Oracle writes outside ``allowed`` (an iterable of (addr, length) the function may touch).

    The machine stack is the one implicit permission, per ``on_machine_stack``. (test_rad_depack.py
    calls this as well; STATUS.md registers the family and the kit as its proper home.)
    """
    def permitted(addr):
        if on_machine_stack(addr):
            return True
        return any(lo <= addr < lo + length for lo, length in allowed)

    return sorted(a for a in writes if not permitted(a))


def run(name, glue, allowed, what, regs=None, poison=True, max_insns=LEAF_INSN_CAP, stop_pc=0):
    """Run ``name``'s original under the oracle and the reconstruction on the same image.

    Requires the two to agree byte for byte over the whole image, and the original to have written
    nothing outside ``allowed``. Returns the differential's ``info`` so a caller can also assert on
    the returned d0. ``poison`` runs the kit's attribution pass, which is what stops a case passing
    because the destination already held the value the function writes; a caller turns it off only
    when inverting an output would corrupt an ADDRESS the run then stores through. ``max_insns``
    raises the cap for a routine that loops — state the number the routine's own geometry gives, so
    it stays a cap and not a formality.

    ``stop_pc`` is the kit's second stop condition, and one family of routine needs it: the scroll
    steps ADD to their own return address (`addq.l #4,(a7)`) to skip the caller's next `bsr`, so
    their `rts` lands past the oracle's sentinel and the run would otherwise never stop. A case
    passes the sentinel plus that skip distance and both arms then terminate — see test_scroll.py,
    which also reads the decision back out of the write set rather than inferring it from this.
    """
    diffs, info = differential(entry_of(name), dict(regs or {}), glue,
                               max_insns=max_insns, poison=poison, stop_pc=stop_pc)
    assert not diffs, f"{what}\n{report(diffs)}"
    stray = stray_writes(info["writes"], allowed)
    assert not stray, (
        f"{what}: {len(stray)} write(s) outside {[(hex(a), n) for a, n in allowed]}, e.g. "
        f"{harness.label(stray[0])} @ {stray[0]:#x}")
    return info


# --- building an entry pin -----------------------------------------------------------------------
# The operand encoders, the branch displacements and the opcodes MORE THAN ONE battery spells. A
# battery keeps its own single-use encodings next to the routines that need them; these are here
# because two files would otherwise carry the same four bytes and could disagree about them.
#
# Both encoders MASK to their width, which is the 68000's own behaviour: an operand field holds
# exactly two or four bytes, so a caller passing a negative displacement (`word(-18)` for a `dbf`) or
# a value with rubbish above the field gets what the instruction stream would hold. Without the mask
# `to_bytes` would raise OverflowError on the negative case and hide the readable failure.
WORD_MASK = 0xffff
LONGWORD_MASK = 0xffffffff

RTS = b"\x4e\x75"
BSR_W = b"\x61\x00"                 # bsr.w <d16>
MOVE_W_ABS_L_D0 = b"\x30\x39"       # move.w <abs>.l,d0
MOVE_W_D0_ABS_L = b"\x33\xc0"       # move.w d0,<abs>.l
MOVE_W_ABS_L_ABS_L = b"\x33\xf9"    # move.w <abs>.l,<abs>.l
MOVE_W_IMM_ABS_L = b"\x33\xfc"      # move.w #imm,<abs>.l


def word(value):
    return (value & WORD_MASK).to_bytes(2, "big")


def longword(value):
    return (value & LONGWORD_MASK).to_bytes(4, "big")


# A 68000 branch counts its displacement from the EXTENSION WORD, which sits two bytes after the
# opcode the branch is written as — so a displacement is always the bytes the branch spans plus that
# 2. Spelling it once is what lets a pin's displacements come out of the geometry of the pieces they
# jump over instead of being transcribed. Each battery keeps its own branch OPCODES (they spell them
# differently — byte constants in test_hud.py, built from an integer in test_scroll.py); `bsr.w` has
# only the one encoding, so that one is assembled whole here.
BRANCH_EXTENSION = 2


def forward_branch(spanned_bytes):
    """The displacement word of a `bcc.w`/`bra.w` that skips forward over ``spanned_bytes``."""
    return word(spanned_bytes + BRANCH_EXTENSION)


def backward_branch(body_bytes):
    """The displacement word of a `dbf`/`bra.w` that jumps BACK over the ``body_bytes`` it tails."""
    return word(-(body_bytes + BRANCH_EXTENSION))


def bsr_w(here, target):
    """`bsr.w target` as assembled AT ``here`` — a call's displacement depends on where it sits, so
    a pin aimed at the wrong callee (or built at the wrong offset) fails on the bytes."""
    return BSR_W + word(target - (here + BRANCH_EXTENSION))


def assert_entry_is(name, expected):
    """Pin the bytes at ``name``'s entry against the instruction(s) the battery believes are there.

    This is what makes a wrong constant fail where it is wrong: a battery builds ``expected`` out of
    the encodings above and its own geometry constants, so one assert covers the entry point from
    ../names.txt, the global from include/wonderboy.h, the value, and the operand size all at once.
    """
    entry = entry_of(name)
    actual = bytes(harness.BASE_IMAGE[entry:entry + len(expected)])
    assert actual == expected, (
        f"{name} @ {entry:#x} is {actual.hex()}, not the {expected.hex()} this battery reconstructs")


def assert_batch_is_complete(entry_bytes, recorded):
    """Guard a battery's own scope: the entry-pin table must still hold the routines it was written
    for. ``recorded`` is a number the battery states rather than derives, so a routine dropped from a
    table shrinks the battery loudly instead of silently."""
    assert len(entry_bytes) == recorded, (
        f"{len(entry_bytes)} routines are reconstructed here, not the recorded {recorded} — a table "
        f"lost an entry, or gained one nothing else knows about")


# --- reading a value back out of the oracle's write set -------------------------------------------

def read_bytes(info, addr, length, what=""):
    """The bytes the original left at ``addr``, taken from the oracle's write set.

    This is what lets a case say WHICH value it expects rather than only that both sides agree. A
    byte the original never wrote is a failure and not a fallback to the image: the case would
    otherwise pass on whatever was already there.
    """
    writes = info["writes"]
    missing = [addr + i for i in range(length) if addr + i not in writes]
    assert not missing, (
        f"{what}: the original did not write {[hex(a) for a in missing]}; it wrote "
        f"{[hex(a) for a in sorted(writes)][:8]}...")
    return bytes(writes[addr + i] for i in range(length))


def read_int(info, addr, length, what=""):
    """``read_bytes`` as the big-endian number those bytes spell."""
    return int.from_bytes(read_bytes(info, addr, length, what), "big")


def assert_rows(info, rows, expected, what, skip=()):
    """Compare a blit's rows against the bytes the case says should have moved.

    ``rows`` is the [(address, length)] the run was allowed to write — the same list the caller hands
    ``run()`` — and ``expected`` the bytes for each of them. The rectangular blits all compare their
    result this way, so the row index and the differing bytes are named in one place.

    ``skip`` is a set of addresses to leave out, for the case where a SECOND draw lands inside the
    first one's rectangle and those bytes belong to that draw's own assert (test_hud.py's record
    display stamps two digits into the bitmap it just blitted). A ``skip`` that swallowed the whole
    rectangle would turn this into a no-op, so the bytes actually compared are counted and required
    to be a majority of them — the row/length check above does not cover that on its own.
    """
    assert len(expected) == len(rows), (
        f"{what}: {len(expected)} expected rows against {len(rows)} written ones — a case whose two "
        f"geometries disagree would leave the surplus rows unchecked")
    compared = 0
    for row, (addr, length) in enumerate(rows):
        actual = read_bytes(info, addr, length, what)
        # Per ROW as well as per row COUNT: `expected` is normally sliced out of the loaded image,
        # and a slice that ran past the end comes back short — which would be an IndexError inside
        # this loop rather than a failure naming the case.
        assert len(expected[row]) == length, (
            f"{what}: expected row {row} is {len(expected[row])} bytes against the {length} written "
            f"— the case's source geometry and its destination geometry disagree")
        for index in range(length):
            if addr + index in skip:
                continue
            compared += 1
            assert actual[index] == expected[row][index], (
                f"{what}: row {row} byte {index} at {addr + index:#x} is {actual[index]:#04x}, not "
                f"{expected[row][index]:#04x} (row is {actual.hex()}, not {expected[row].hex()})")
    total = sum(length for _addr, length in rows)
    assert compared * 2 > total, (
        f"{what}: only {compared} of {total} bytes were compared — the skip set has swallowed the "
        f"blit, so this assert is holding almost nothing")
