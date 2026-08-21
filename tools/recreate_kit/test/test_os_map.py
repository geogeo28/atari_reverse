"""The geometry the poked-input guards are built on (``recreate_kit/os_map.py``).

Three guards refuse a run or a poke that would put the harness-poked input block on top of a
project's own program — ``harness.make_image``, ``harness._vet_poked_input_available`` and
``emu._vet_no_poked_input_read`` — and all three ask os_map the same two questions: does the block
overlap the loaded program, and does this poke land in the block. Those questions are pinned here.

Why here rather than only in a project's suite: the kit's own tests must run in a bare checkout, and
both ``harness`` and ``emu`` load a compiled ``.so`` at import, so neither can be exercised from
this directory. Before os_map existed the arithmetic lived inside them and the shared kit's
protection was tested **only** by ``projects/wonderboy/recreate/test/test_poked_input_guard.py`` —
deleting both guard calls left this suite entirely green. It no longer does.

WHAT IS STILL NOT COVERED HERE: that the three guards actually *call* these predicates. That wiring
needs a bound project with a built candidate, and Wonder Boy is the only project the overlap exists
for, so it stays pinned there. The block's agreement with ``include/os.h`` is pinned by
``test_os_memory_map.py``, which owns this directory's one ``#define`` scraper.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # reverse/tools, so `recreate_kit` imports
from recreate_kit import os_map   # noqa: E402  (only importable after the path insert)

# Two real projects' geometry, so the cases below are not free-invented numbers.
WONDERBOY_LOAD_BASE, WONDERBOY_PROGRAM_END = 0x3f8, 0x218d0     # runs at the absolute address 0x400
DEFAULT_LOAD_BASE, DEFAULT_PROGRAM_END = 0x10000, 0x30000       # BuggyBoy / Joust: the kit default

POKE_LEN = 4                     # every longword the block holds (pending flag, char, Random value)


def test_a_program_loaded_below_the_block_overlaps_it():
    assert os_map.poked_input_overlaps_program(WONDERBOY_LOAD_BASE, WONDERBOY_PROGRAM_END)


def test_a_program_loaded_clear_of_the_block_does_not():
    """The property the waiver flag must NOT be able to override: it is the layout that decides.

    A project whose load_base already clears the block has nothing to collide with, so it keeps
    console_key()/psg_regs() however its project.toml is written.
    """
    assert not os_map.poked_input_overlaps_program(DEFAULT_LOAD_BASE, DEFAULT_PROGRAM_END)
    assert not os_map.poked_input_overlaps_program(os_map.OS_POKE_BLOCK_END, DEFAULT_PROGRAM_END)


def test_the_last_load_base_that_overlaps_is_one_below_the_block_end():
    """The boundary, both sides of it — an off-by-one here silently disarms or over-arms a guard."""
    assert os_map.poked_input_overlaps_program(os_map.OS_POKE_BLOCK_END - 1, DEFAULT_PROGRAM_END)
    assert not os_map.poked_input_overlaps_program(os_map.OS_POKE_BLOCK_END, DEFAULT_PROGRAM_END)


def test_no_program_loaded_overlaps_nothing():
    """loader.PROGRAM_END is None until load_image() has run; there is nothing to collide with."""
    assert not os_map.poked_input_overlaps_program(WONDERBOY_LOAD_BASE, None)


def test_a_program_ending_below_the_block_does_not_overlap_it():
    assert not os_map.poked_input_overlaps_program(0x100, os_map.OS_CON_PENDING)


@pytest.mark.parametrize("addr", (os_map.OS_CON_PENDING, os_map.OS_CON_CHAR,
                                  os_map.OS_RANDOM_VALUE, os_map.OS_PSG_REGS))
def test_every_kind_of_staged_state_is_seen_as_a_poke_into_the_block(addr):
    """All three kinds, including the XBIOS Random value the kit ships no builder for."""
    assert os_map.poke_hits_poked_input(addr, POKE_LEN)


def test_the_whole_psg_register_file_is_seen():
    assert os_map.poke_hits_poked_input(os_map.OS_PSG_REGS, os_map.OS_PSG_NREGS)


@pytest.mark.parametrize("addr, length", (
    (os_map.OS_CON_PENDING - POKE_LEN, POKE_LEN),      # ends where the block starts
    (os_map.OS_POKE_BLOCK_END, POKE_LEN),              # starts where the block ends
    (0x10000, 0x100),                                  # an ordinary poke into a program
    (os_map.OS_PSG_REGS, 0),                           # writes nothing, so it hits nothing
))
def test_a_poke_clear_of_the_block_is_not_flagged(addr, length):
    assert not os_map.poke_hits_poked_input(addr, length)


@pytest.mark.parametrize("addr, length", (
    (os_map.OS_CON_PENDING - 1, 2),                    # straddles the low edge
    (os_map.OS_POKE_BLOCK_END - 1, 2),                 # straddles the high edge
    (0, os_map.OS_POKE_BLOCK_END),                     # swallows the block whole
))
def test_a_poke_straddling_an_edge_is_flagged(addr, length):
    """Keyed on the RANGE, not on the start address: a poke that merely reaches into the block
    corrupts it just as thoroughly as one aimed at it."""
    assert os_map.poke_hits_poked_input(addr, length)


# ---------------------------------------------------------------------------------------------
# ...and the one way past that guard: a span the PROJECT declares to be its own program's data
# ---------------------------------------------------------------------------------------------
# `poke_hits_poked_input` above answers "does this touch the block", which is all the kit can know
# by itself. `poke_is_declared_program_data` is the project's answer to "and are those bytes MINE" —
# the fact nothing here can derive. It is pinned in this module for the module's own stated reason:
# the shared kit's protection must not live entirely inside one project's tests.
DECLARED = ((os_map.OS_CON_CHAR, os_map.OS_CON_CHAR + POKE_LEN),)


@pytest.mark.parametrize("addr, length", (
    (os_map.OS_CON_CHAR, POKE_LEN),                    # exactly the span
    (os_map.OS_CON_CHAR, 1),                           # its first byte
    (os_map.OS_CON_CHAR + POKE_LEN - 1, 1),            # ...and its last
    (os_map.OS_CON_CHAR + 1, 2),                       # wholly within
))
def test_a_poke_wholly_inside_a_declared_span_is_program_data(addr, length):
    assert os_map.poke_is_declared_program_data(addr, length, DECLARED)


@pytest.mark.parametrize("addr, length, why", (
    (os_map.OS_CON_CHAR - 1, POKE_LEN, "straddles the low edge"),
    (os_map.OS_CON_CHAR + 1, POKE_LEN, "straddles the high edge"),
    (os_map.OS_CON_PENDING, POKE_LEN, "a different part of the block entirely"),
    (os_map.OS_RANDOM_VALUE, POKE_LEN, "the neighbour the span deliberately excludes"),
    (os_map.OS_CON_CHAR, 0, "writes nothing, so it declares nothing"),
))
def test_a_poke_that_is_not_WHOLLY_inside_is_refused(addr, length, why):
    """WHOLLY inside or not at all: a poke that straddles the boundary is half the game's data and
    half the model's, and serving it would write the model's half from a value nobody declared."""
    assert not os_map.poke_is_declared_program_data(addr, length, DECLARED), why


def test_a_project_that_declares_nothing_gets_nothing():
    """Every project but the declaring one passes an empty tuple, and must be refused as before —
    the predicate's first `not` is what makes that the cheap path as well as the safe one."""
    assert not os_map.poke_is_declared_program_data(os_map.OS_CON_CHAR, POKE_LEN, ())
