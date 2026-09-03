"""The frame family's CALLBACK-DOOR SLOT NAMESPACE, pinned across all five twins at once.

`src/asm/frame*.S` assemble into ONE blob and jump into ONE band, so a slot number is a
family-wide name for a host C function. Each file spells the slots it uses as `.equ ZY_DOOR_<name>`;
`asm_frame_common.DOOR_TABLE` is what `AsmTwins` looks those addresses up in. Nothing in a single
suite can see the two ways that pair goes wrong across files:

  * two files claiming ONE slot for DIFFERENT callees. Green until the day a twin reaches the other
    file's stub — and then it is a real `jsr` to the wrong core with arguments meant for another,
    which off target is a pixel diff and on target is whatever that core does to the image.
  * a file naming a slot the table does not declare, or the table carrying a slot no file jumps to.
    The first fails as a refusal naming the slot rather than the omission; the second is dead weight
    that makes the table look like coverage it is not.

Four twins each pinning their own `.equ`s against the table would catch neither. This file asks the
question once, of the whole family.
"""
import collections

import pytest

import asm_frame_common as common
from recreate_kit import asm_twin


def _declarations():
    """[(path, callee name, slot)] for every `.equ ZY_DOOR_*` in the family, flattened."""
    return [(path, name, slot)
            for path, doors in common.door_equates_by_file().items()
            for name, slot in sorted(doors.items())]


def test_the_door_table_fits_the_band_it_jumps_into():
    """THE BAND HAS A CEILING AND THE TABLE IS NEAR IT — 62 of the kit's 64 slots after wave E.

    A slot past `DOOR_SLOTS` assembles into a `jsr` one stride beyond the address `AsmTwins` arms,
    so the run never stops at a door at all: it executes whatever is there and dies as a sentinel
    timeout naming neither the door nor the callee — verbatim the outcome the rest of this file's
    pins exist to prevent. The kit's own slot-range `ValueError` is never reached, because the PC
    never lands in the band.

    Nothing checked this until wave E took the table to 61; the next wave that adds three doors
    would have been the one to find out.
    """
    highest = max(common.DOOR_TABLE)
    assert highest < asm_twin.DOOR_SLOTS, (
        f"the family's door table reaches slot {highest}, but the kit watches only "
        f"{asm_twin.DOOR_SLOTS} slots ({asm_twin.DOOR_BASE:#x} + {asm_twin.DOOR_SLOTS} * "
        f"{asm_twin.DOOR_STRIDE}). A stub for slot {highest} jumps outside the band, so no callback "
        f"is ever serviced and the case dies as a sentinel timeout. Raise DOOR_SLOTS in "
        f"tools/recreate_kit/asm_twin.py, which owns the band.")


def test_the_scan_found_the_familys_door_declarations():
    """The scan's own positive control: every assertion below is vacuous over an empty list, and the
    `.equ` spelling it depends on is a convention rather than something the assembler enforces."""
    files = common.door_equates_by_file()
    assert files, f"no frame*.S in {common.ASM_DIR} — the family's twins are gone or renamed"
    declaring = {path.name: len(doors) for path, doors in files.items() if doors}
    assert declaring, (
        f"none of {sorted(path.name for path in files)} declares an `.equ ZY_DOOR_*`, so this "
        f"whole file is testing an empty list. The operand shape changed, or the twins stopped "
        f"reaching their cores through the door")


@pytest.mark.parametrize("path,name,slot", _declarations(),
                         ids=lambda value: getattr(value, "name", value))
def test_every_declared_door_is_the_table_s(path, name, slot):
    """One file's `.equ ZY_DOOR_<name>, <slot>` against the table's row for that slot.

    The two are the two halves of one address: the stub jumps to `DOOR_BASE + slot * STRIDE` and
    `AsmTwins._service_door` looks that slot up. Renumber one and every case calls the WRONG HOST
    FUNCTION with the arguments meant for another.
    """
    assert slot in common.DOOR_TABLE, (
        f"{path.name} jumps to door slot {slot} for {name!r}, which DOOR_TABLE does not declare — "
        f"a case reaching it fails as a refusal naming the slot rather than the omission")
    assert common.DOOR_TABLE[slot].name == name, (
        f"{path.name} puts {name!r} in slot {slot}; DOOR_TABLE puts "
        f"{common.DOOR_TABLE[slot].name!r} there")


def test_no_two_twins_claim_one_slot_for_different_cores():
    """THE CROSS-FILE DEFECT, which is the reason this file exists rather than four per-suite checks.

    The blob is one and the band is one, so `frame_head.S` claiming slot 18 for `playfield_clear`
    and `frame_spawn.S` claiming it for `rand16` assembles, links and passes both their suites — the
    two never call each other's stubs. It breaks the day one of them does.
    """
    claimants = collections.defaultdict(set)
    for path, name, slot in _declarations():
        claimants[slot].add(name)
    conflicts = {slot: sorted(names) for slot, names in claimants.items() if len(names) > 1}
    assert not conflicts, (
        f"one door slot names two different cores: {conflicts}. The slot IS the address, so "
        f"whichever twin reaches the other's stub calls the wrong host function")


@pytest.mark.parametrize("slot", sorted(common.DOOR_TABLE),
                         ids=lambda slot: f"{slot}-{common.DOOR_TABLE[slot].name}")
def test_every_tabled_slot_is_one_a_twin_jumps_to(slot):
    """...and the other direction, SLOT BY SLOT rather than over the set of names.

    Comparing name sets is not enough, and the first revision of this file made exactly that
    mistake: a second row for an ALREADY-TABLED callee — `60: DoorCallback("rand16", 1)` beside the
    real `39` — leaves the two name sets equal, and no `.equ` names slot 60 for the other direction
    to catch. The dead row then sits in the table looking like coverage, and a row added with the
    wrong `nargs` alongside a right one is the same shape with teeth: whichever slot a stub actually
    jumps to decides how many arguments the door reads off the stack.

    So every slot the table declares must be a slot some twin's `.equ` names, for that same callee.
    """
    declared = {(name, at): path for path, name, at in _declarations()}
    callee = common.DOOR_TABLE[slot].name
    reaching = [path.name for (name, at), path in declared.items() if name == callee and at == slot]
    assert reaching, (
        f"DOOR_TABLE declares slot {slot} for {callee!r}, and no frame*.S has an "
        f"`.equ ZY_DOOR_{callee}, {slot}`. Either the row is dead weight — a table that carries a "
        f"slot no twin jumps to is not the map of the doors it reads as — or a stub jumps at a "
        f"DIFFERENT slot for the same core, in which case the arguments are read off the stack by "
        f"whichever row that other slot carries. Declared for {callee!r}: "
        f"{sorted(at for name, at in declared if name == callee)}")


def test_the_table_names_no_core_the_family_lacks():
    """The set-level half of the same question, kept because it names the WHOLE discrepancy at once
    where the slot-by-slot case above names one row per failure."""
    reached = {name for _path, name, _slot in _declarations()}
    tabled = {callback.name for callback in common.DOOR_TABLE.values()}
    assert tabled == reached, (
        f"DOOR_TABLE and the family's `.equ`s name different cores: only in the table "
        f"{sorted(tabled - reached)}, only in the assembly {sorted(reached - tabled)}")
