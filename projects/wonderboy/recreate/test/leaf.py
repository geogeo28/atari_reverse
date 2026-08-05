"""Shared driver for the game's LEAF routines — the ones with no callee, no hardware and a write
set small enough to name.

`test_effects.py`, `test_hud.py`, `test_input.py`, `test_scroll.py`, `test_actor.py`, `test_map.py`
and `test_text.py` are all batteries of such functions, so what they would otherwise each restate
lives here: where a function starts (looked up in `../names.txt`, the workspace's source of truth for
names, rather than restated as a number), what counts as a write it was not entitled to make, the
operand encodings a battery pins its entry points against, how a case seeds an image it can tell
apart afterwards, and how it reads a value back out of the oracle's write set.

NOT a general harness — the kit is that. This module assumes what a leaf gives it: a run short
enough for a tight instruction cap, and a write set the caller can enumerate up front.
"""
import ctypes
import zlib

import harness
from harness import differential, report

import emu                                                       # noqa: E402

# The straight-line leaves are 8 to 38 bytes long and execute at most six instructions. The cap is
# deliberately far below the kit's default: a case that entered the wrong address and ran off into
# the game would otherwise return a plausible-looking result instead of failing. A battery whose
# routines LOOP (the panel blits move up to 32 rows) passes `run(..., max_insns=)` with its own cap,
# derived from that routine's own geometry for the same reason.
LEAF_INSN_CAP = 64

# The game's own two screen buffers (../names.txt: screen_back starts at $70000, screen_front
# $78000, and clear_both_screens clears $70000..$7fd00 — exactly the two back to back). Every
# battery whose routines DRAW takes its destination from one of them, because a destination comes
# out of memory and nothing may be hardcoded; it lives here rather than in one of them because two
# files would otherwise carry the same pair and could disagree about it.
SCREEN_BUFFERS = (0x70000, 0x78000)

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


def program_writes(info):
    """The oracle's write set with the MACHINE STACK left out.

    A `bsr`'s pushed return address is not program output, and a battery that states its write set
    EXACTLY compares against a model of what the routine draws. The band is `on_machine_stack`'s,
    the same one `stray_writes` permits; this is the other side of it, for the cases that state the
    write set rather than bound it. Its upper bound EXCLUDES the return slot at STACK_TOP, which IS
    program output: it is what a scroll step rewrites to consume its caller's `bsr`.
    """
    return {addr: value for addr, value in info["writes"].items() if not on_machine_stack(addr)}


def merge_bands(addresses):
    """Adjacent addresses collapsed into (start, length) bands, for `run`'s `allowed`."""
    bands = []
    for addr in sorted(addresses):
        if bands and addr == bands[-1][0] + bands[-1][1]:
            bands[-1] = (bands[-1][0], bands[-1][1] + 1)
        else:
            bands.append((addr, 1))
    return bands


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


def opcode(value):
    """One 68000 opcode word, as the two bytes the instruction stream holds.

    Every battery that builds its pins from numbers rather than from byte literals spells this;
    it is here so the three of them cannot disagree about the width or the byte order.
    """
    return value.to_bytes(2, "big")


def lea_abs_l(reg, addr):
    """`lea <abs>.l,An` — how every one of these routines names a global."""
    return opcode(0x41f9 | (reg << 9)) + longword(addr)


def lea_d16(reg, displacement, source=None):
    """`lea d16(As),Ad` — how every one of them steps a cursor.

    Usually one register advancing itself, so the source defaults to it. The scroll's pre-shift is
    the exception: it steps from one buffer copy to the next by `lea $5800(a0),a1`.
    """
    return opcode(0x41e8 | (reg << 9) | (reg if source is None else source)) + word(displacement)


def movea_l_abs_w(reg, addr):
    """`movea.l <abs>.w,An` — how a routine loads a pointer held BELOW $8000 (WB_SCREEN_BACK is,
    so the scroll's blit and the message box's both name it short)."""
    return opcode(0x2078 | (reg << 9)) + word(addr)


def lea_indexed(reg, index, displacement=0, longword_index=False):
    """`lea d8(An,Dn.w),An` — the extension word is the whole of the index encoding.

    ONE spelling for what test_scroll.py and test_text.py each had half of: the scroll needs the
    LONGWORD index bit (a tile offset it has already shifted into the high half), the text plotter
    and the map probes need the 8-bit DISPLACEMENT, and no caller needs a base register other than
    the destination. A displacement is masked to its byte because that is the field's width.
    """
    return opcode(0x41f0 | (reg << 9) | reg) + word(
        (index << 12) | (0x800 if longword_index else 0) | (displacement & 0xff))


def move_w_ind_dn(reg, base, displacement=0):
    """`move.w (An),Dn` and its `d16(An)` form — how every one of these routines reads a field."""
    if displacement == 0:
        return opcode(0x3010 | (reg << 9) | base)
    return opcode(0x3028 | (reg << 9) | base) + word(displacement)


def move_w_abs_l_dn(reg, addr):
    return opcode(0x3039 | (reg << 9)) + longword(addr)


def tst_w_abs_w(addr):
    """`tst.w <abs>.w` — the mode flags and the scroll's gate are all below $8000, so the original
    spells them short."""
    return opcode(0x4a78) + word(addr)


def subi_w_dn(reg, value):
    return opcode(0x0440 | reg) + word(value)


def sub_w_dn_dn(destination, source):
    return opcode(0x9040 | (destination << 9) | source)


def move_w_imm_dn(reg, value):
    return opcode(0x303c | (reg << 9)) + word(value)


def moveq_0_dn(reg):
    return opcode(0x7000 | (reg << 9))


def mulu_w_imm_dn(reg, value):
    return opcode(0xc0fc | (reg << 9)) + word(value)


def tst_b_abs_l(addr):
    return opcode(0x4a39) + longword(addr)


def tst_w_abs_l(addr):
    return opcode(0x4a79) + longword(addr)


def clr_b_abs_l(addr):
    return opcode(0x4239) + longword(addr)


def clr_w_abs_l(addr):
    return opcode(0x4279) + longword(addr)


def st_abs_l(addr):
    """`st <abs>.l` — Scc with the always-true condition, which is how a flag byte is RAISED."""
    return opcode(0x50f9) + longword(addr)


def subq_w_abs_l(amount, addr):
    return opcode(0x5179 | ((amount & 7) << 9)) + longword(addr)


# A 68000 branch counts its displacement from the EXTENSION WORD, which sits two bytes after the
# opcode the branch is written as — so a displacement is always the bytes the branch spans plus that
# 2. Spelling it once is what lets a pin's displacements come out of the geometry of the pieces they
# jump over instead of being transcribed. Each battery still keeps its own branch OPCODES (they
# spell them differently — byte constants in test_hud.py, built from an integer in test_scroll.py);
# `bsr.w` and `dbf` have only the one encoding each, so those are assembled whole here.
BRANCH_EXTENSION = 2
DBF_DN = 0x51c8


def forward_branch(spanned_bytes):
    """The displacement word of a `bcc.w`/`bra.w` that skips forward over ``spanned_bytes``."""
    return word(spanned_bytes + BRANCH_EXTENSION)


def backward_branch(body_bytes):
    """The displacement word of a `dbf`/`bra.w` that jumps BACK over the ``body_bytes`` it tails."""
    return word(-(body_bytes + BRANCH_EXTENSION))


def branch_over(condition, spanned_bytes):
    """`bcc.w`/`bra.w` past ``spanned_bytes``, for a jump whose target is known by LENGTH rather
    than by the pieces — a loop's own closing branch, or a `beq` over one `bsr`."""
    return opcode(condition) + forward_branch(spanned_bytes)


def branch(condition, *over):
    """`bcc.w`/`bra.w` past exactly ``over`` — the pieces themselves give the displacement."""
    return branch_over(condition, sum(len(piece) for piece in over))


def dbf_over(reg, body_bytes):
    """`dbf Dn,<back over ``body_bytes``>`, for a loop whose body is known by LENGTH."""
    return opcode(DBF_DN | reg) + backward_branch(body_bytes)


def dbf(reg, *body):
    """`dbf Dn,<start of body>`: the displacement runs back over ``body`` and the opcode word."""
    return dbf_over(reg, sum(len(piece) for piece in body))


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


# --- seeding an image a case can tell apart afterwards --------------------------------------------
# Two arbitrary odd multipliers, so that neighbouring addresses and neighbouring salts diverge in
# every bit rather than in the low ones. Nothing depends on their values, only on the mixing.
ADDRESS_MULTIPLIER = 0x9d
SALT_MULTIPLIER = 0x4f1b


def keyed_byte(addr, salt):
    """A byte derived from the ADDRESS, not from a row index.

    Batch 4's restore walk learned this the hard way: two widened bands that overlap let an
    index-keyed filler silently rewrite the earlier one, and the case then passes on bytes it did
    not mean to seed. Keyed on the address, an over-run lands on a byte that is wrong for where it
    was written.
    """
    mixed = (addr * ADDRESS_MULTIPLIER) ^ (addr >> 5) ^ (salt * SALT_MULTIPLIER)
    return (mixed ^ (mixed >> 8)) & 0xff


def keyed_block(base, length, salt):
    """One seeded band of ``keyed_byte``, built per call rather than cached: every case salts from
    its own NAME, so a cache would mostly retain bands nothing asks for again (measured on the
    scroll battery: it served under a third of the calls, all of them 8-bit salt collisions between
    unrelated cases, for 3% of the battery's time)."""
    return bytes(keyed_byte(base + offset, salt) for offset in range(length))


def case_salt(case):
    """A salt derived from the case's NAME, and derived reproducibly.

    Python's `hash()` of a string is randomised per process unless PYTHONHASHSEED is pinned, which
    nothing here pins — seeding from it would give every run a different image, so a failure could
    not be replayed from its case id and a mutation sweep's red count could move between sweeps
    without the code changing. `crc32` is the same number in every process.
    """
    return zlib.crc32(case.encode()) & 0xff


# --- reading the image the same way the 68000 does ------------------------------------------------
# A battery that states its write set EXACTLY models the routine's own arithmetic in Python, and
# every such model reads words out of the image and sign-extends them. Three batteries spelt these
# (test_scroll.py, test_actor.py, test_map.py), which is a third place the sign extension could have
# been got wrong.
WORD_BYTES = 2


def u16(image, addr):
    """The word at ``addr``, as the big-endian number a `move.w` reads there."""
    return int.from_bytes(bytes(image[addr:addr + WORD_BYTES]), "big")


def s16(value):
    """``value``'s low word as the SIGNED number a word operand spells."""
    value &= WORD_MASK
    return value - (WORD_MASK + 1) if value & 0x8000 else value


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
