"""The inputs an XBIOS case is built from, in one place — the images its pokes make and the chip
contents it declares.

Two kinds of caller need the same cases and must not keep a copy each: the Tier 1 differentials
(`test_xbios_random.py`, `test_xbios_giaccess.py`), which prove the reconstruction equals the ROM
over them, and Tier 3's bench, which measures what the SAME case costs on each side. A ratio taken
over a differently-poked machine than the one that was verified would be a number about a case nobody
proved, and two spellings of `seed_poke` is exactly how that happens.

The bench reaches these through `test_boot_snapshot.VERIFIED_CASES` rather than importing this file:
that list is the project's register of what has been verified, it is built from the batteries' own
constructors (which are built from these), and `../bench/tier3.py` prices exactly its entries. So
there is one chain from here to a ratio and no branch in it.

Only what is SHARED lives here. Each suite keeps its own parametrized value lists: those are that
file's claims about where a reconstruction could diverge, not inputs anything else reuses.
"""
import struct

import abi
from harness import addrs

# ---- XBIOS Random ($11) -------------------------------------------------------------------------

# The seed the captured snapshot holds. The desktop never calls Random, so it is still zero there —
# which means the DEFAULT image exercises the seeding branch and a case that wants the other one has
# to poke a seed in. `test_xbios_random.py` asserts it rather than assuming it.
UNSEEDED = 0


def seed_poke(seed):
    """The image poke that puts `seed` in the OS's own random state."""
    return {addrs.RANDOM_SEED: seed.to_bytes(4, "big")}


def tick_poke(tick):
    """...and the one that sets the 200 Hz system tick the seeding branch draws its entropy from."""
    return {addrs.SYSVAR_HZ_200: tick.to_bytes(4, "big")}


# ---- XBIOS Giaccess ($1c) -----------------------------------------------------------------------

# Every register the chip's four-bit select latch can name.
REGISTERS = tuple(range(addrs.GIACCESS_REGISTER_MASK + 1))
# What a case declares the chip held on entry, for the read-only path: a distinct byte per register,
# so a reconstruction that read the WRONG one diverges on the value rather than by luck.
ENTRY_FILE = {reg: (0xA0 ^ (reg * 0x11)) & 0xFF for reg in REGISTERS}


def argument_poke(data, reg_and_flag):
    """The two argument words, where the dispatcher's caller would have left them."""
    return {abi.FIRST_ARG: struct.pack(">HH", data & 0xFFFF, reg_and_flag & 0xFFFF)}
