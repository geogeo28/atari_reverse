"""The HOST SLOTS — `include/gemdos/gemdos.h`'s one table of the fixed addresses that stand in, off
target, for a ROM frame local whose ADDRESS a GEMDOS routine hands on (the FAT routines' word, the
directory search's pattern, the walk's name and cursor, the delete's mark byte, `Fattrib`'s attribute
byte, and `create`'s free-slot search name and new entry's FCB name).

Every slot must sit where the differential drops bytes on both shores — the oracle's stack band, above
its guard — and below both the deepest frame the kit calls legitimate and the `savptr` frame the
GEMDOS batteries declare, so nothing the ORACLE writes can land on one. And no two may overlap: the C
asserts a slot is never claimed twice, but two ROLES live at once (a walk's name and cursor while it
searches, a search's pattern while the FAT word is taken beneath it) are two different slots, and only
their addresses keep them apart.
"""
from harness import emu

import gemdos
import gemdos_fs as fs

SLOT_PREFIX = "GEMDOS_HOST_SLOT_"
WIDTH_SUFFIX = "_BYTES"


def host_slots(constants):
    """`{role: (address, bytes)}` for every slot the header names — each address with its width."""
    return {name[len(SLOT_PREFIX):]: (value, constants[name + WIDTH_SUFFIX])
            for name, value in constants.items()
            if name.startswith(SLOT_PREFIX) and not name.endswith(WIDTH_SUFFIX)}


def misplaced(slots):
    """What is wrong with a slot table: overlaps between neighbours, and spans outside the band."""
    ceiling = min(emu.STACK_TOP - emu.STACK_SCRATCH, gemdos.FRAME_AT)
    spans = sorted((at, at + width, role) for role, (at, width) in slots.items())
    faults = [f"{role} {at:#x}..{end:#x} is outside {emu.STACK_GUARD_LO:#x}..{ceiling:#x}"
              for at, end, role in spans if not emu.STACK_GUARD_LO <= at < end <= ceiling]
    faults += [f"{role} runs into {next_role}" for (_at, end, role), (next_at, _end, next_role)
               in zip(spans, spans[1:]) if end > next_at]
    return faults


def test_every_host_slot_is_inside_the_dropped_band_and_apart():
    slots = host_slots(fs.CONSTANTS)
    assert set(slots) == {"SEARCH_PATTERN", "WALK_NAME", "WALK_CURSOR", "DELETE_MARK", "ATTRIBUTE", "FRAME_WORD",
                          "CREATE_FREE_NAME", "CREATE_FCB"}
    assert not misplaced(slots)


def test_the_check_refuses_a_slot_moved_onto_another():
    """...and the check is not vacuous: the frame word moved onto the delete mark, or out of the band,
    is refused by name."""
    slots = host_slots(fs.CONSTANTS)
    mark_at, _width = slots["DELETE_MARK"]
    word_bytes = slots["FRAME_WORD"][1]
    assert misplaced({**slots, "FRAME_WORD": (mark_at, word_bytes)})
    assert misplaced({**slots, "FRAME_WORD": (gemdos.FRAME_AT, word_bytes)})
