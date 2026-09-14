"""XBIOS Random ($11) @ $fc1510 — the ROM's pseudo-random generator, run in place.

The first Tier 1 differential of this project, and the one that says the ROM-mode harness works at
all: the ORIGINAL executes at its $fc1510 address out of the mapped ROM, over a real post-boot RAM
image, reading the machine's own `_hz_200` and its own seed in the OS's BSS; the C candidate runs
over a copy of the same image; and the two must leave identical memory and return the same D0.

The routine also calls the Alcyon C runtime's `lmul` at $fc4b28, which the oracle executes IN THE
ROM like any other instruction — so a green case here is also evidence that ROM-internal calls work,
which nothing about a .PRG project could have shown.

THE REGISTER GLUE: every XBIOS function is entered from the dispatcher at $fc07fc, which pops the
function number and does `suba.l a5,a5` — so A5 is 0 and the routine reaches low RAM and the I/O
page through 16-bit displacements off it. Random itself never touches A5; it is passed anyway,
because entering a ROM function any other way than the dispatcher does is how a case ends up proving
something about a machine that does not exist.
"""
import ctypes
import random

import pytest

from harness import BASE_IMAGE, _lib, addrs, differential, report

_lib.xbios_random.restype = ctypes.c_uint32

# The seed the captured snapshot holds. The desktop never calls Random, so it is still zero there —
# which means the DEFAULT image exercises the seeding branch and a case that wants the other one has
# to poke a seed in. Asserted rather than assumed, in its own case below: a future snapshot whose
# desktop had called Random would silently stop testing the branch this file thinks it tests.
UNSEEDED = 0


def seed_poke(seed):
    """The image poke that puts `seed` in the OS's own random state."""
    return {addrs.RANDOM_SEED: seed.to_bytes(4, "big")}


def tick_poke(tick):
    """...and the one that sets the 200 Hz system tick the seeding branch draws its entropy from."""
    return {addrs.SYSVAR_HZ_200: tick.to_bytes(4, "big")}


def _glue(lib, buf):
    return lib.xbios_random(buf)


def run(pokes=None, poison=True):
    """One differential of XBIOS Random over the snapshot, optionally perturbed. Returns its info."""
    diffs, info = differential(addrs.XBIOS_RANDOM, {"a5": 0, "_pokes": pokes or {}}, _glue,
                               poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] == info["regs"]["d0"], (
        f"the candidate returned {info['ret']:#x} where the ROM left {info['regs']['d0']:#x} in D0")
    return info


def test_the_snapshot_still_has_an_unseeded_generator():
    """The premise of the seeding case below: it is only a seeding case while this holds."""
    # Sliced in place rather than through make_image(), which would copy 16 MB to read four
    # bytes; BASE_IMAGE is the snapshot as captured, which is what the claim is about.
    seed = int.from_bytes(bytes(BASE_IMAGE[addrs.RANDOM_SEED:addrs.RANDOM_SEED + 4]), "big")
    assert seed == UNSEEDED, (
        f"the snapshot's random state is {seed:#x}, not 0 — something in this boot called XBIOS "
        f"Random, so the default image no longer exercises the seeding branch")


def test_it_seeds_from_the_system_tick_when_the_state_is_zero():
    """The snapshot's own machine: state 0, so the routine takes the `tst.l` branch and builds one."""
    run()


@pytest.mark.parametrize("tick", (0, 1, 0x0B32, 0x8000, 0xFFFF, 0x1234_5678, 0xFFFF_FFFF))
def test_the_seeding_branch_over_a_range_of_system_ticks(tick):
    """`asl.l #16` then `or.l` the WHOLE longword back in — a tick with high bits set is where a
    reconstruction that masked the `or` to 16 bits would diverge."""
    run(tick_poke(tick))


@pytest.mark.parametrize("seed", (1, 2, 0x7FFF_FFFF, 0x8000_0000, 0x8000_0001, 0xFFFF_FFFF,
                                  0xBB40_E62D, 0x0000_0100))
def test_the_advance_branch_over_the_signed_multiply_s_edge_cases(seed):
    """The ROM multiplies through a SIGNED 32x32 helper that negates the operands and the result;
    the C is a plain unsigned multiply. These are the inputs where that argument has to hold —
    either operand negative, both negative, and the two values `neg.l` leaves alone."""
    run(seed_poke(seed))


def test_the_returned_value_is_24_bits_of_the_new_state_and_not_the_state():
    """`asr.l #8` then `and.l #$ffffff`. The state itself is compared byte-for-byte by the
    differential; this is the projection of it the caller sees."""
    info = run(seed_poke(0x1234_5678))
    assert info["regs"]["d0"] <= addrs.RANDOM_MASK, "the result is wider than 24 bits"
    assert info["regs"]["d0"] != 0x1234_5678, "the state came back unadvanced"


def test_a_fuzz_over_seeds_and_ticks():
    """Random inputs to both branches, so the parametrized pairs above are a floor and not the whole
    claim. The attribution pass is off here — it is pinned by the cases above, and re-running both
    cores over a 16 MB image 64 more times buys nothing."""
    rng = random.Random(0x1102)
    for _ in range(64):
        run({**seed_poke(rng.getrandbits(32)), **tick_poke(rng.getrandbits(32))}, poison=False)
