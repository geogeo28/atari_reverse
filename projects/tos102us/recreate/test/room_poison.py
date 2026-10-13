"""THE BLOB'S ROOM POISONED ON THE ROM'S SHORE — the read guard a Tier-3 row is held to (`test_room_poison.py`).

WHY. A row is two runs of one case: the ROM's over the snapshot, ours over the same image WITH THE BLOB LAID at
`bench_base`. The kit refuses a case's POKE inside the blob's span and cuts the span out of what it compares — and
nothing vets a READ. A case whose ROM-shore run reads `[bench_base, staging_base)` reads the snapshot's zero there
while ours reads whatever the linker put at that address: the row is green or red by the blob's layout, and says so
in the codegen's name (band 6 wave 0: `vdi_vqt_width, ptsout over the font's HOR_TABLE` read one byte at $6040b,
green only because the shipped blob held $00 there). The kit keeps no ledger of RAM reads, and is not ours to edit.

WHAT THIS DOES INSTEAD: a POISON DIFFERENTIAL. While `armed()`, every run entered through the oracle's doors
(`emu.run`, `emu.run_bench`, `emu.bench_resume`) over a machine that HOLDS NO BLOB — a ROM-shore run — finds the
room filled with bytes that are non-zero and differ from BOTH blobs' own byte at every address; the room is put back
as each run stops, before anything reads the memory. Our shore is untouched. So a ROM-shore run that reads the room
answers, stores or costs something else — and the row's own differential, or its cost against the unpoisoned
measurement, says which row.

WHAT IT DOES NOT SEE (said where the guard is described, STATUS's UNPINNED): a read whose byte changes nothing the
run leaves or costs; an instruction single-stepped through the library directly (`aes_boot`'s by-hand steps); a run
served from a memo made before the guard was armed.
"""
import contextlib
import functools

import harness
from harness import emu

import staging
import transcription

_CFG = harness.project.current()
ROOM = (_CFG.bench_base, staging.SCRATCH)               # [lo, hi): where a blob lies, or may come to lie
ROOM_BYTES = ROOM[1] - ROOM[0]
POISONS = (0xA5, 0x5A, 0xC3)                            # three, so one is neither 0 nor either blob's byte
BLOB_HEAD_BYTES = 0x100                                 # a machine whose first bytes at `bench_base` are zero holds no blob
_NO_BLOB_HEAD = bytes(BLOB_HEAD_BYTES)
_EMPTY_ROOM = bytes(ROOM_BYTES)


def _blob_bytes(elf):
    return elf.with_suffix(".bin").read_bytes()


def poison_of(blobs):
    """The room's poison: at each address a byte that is not zero and is no byte either of `blobs` holds there."""
    padded = [blob.ljust(ROOM_BYTES, b"\0") for blob in blobs]
    assert all(len(blob) == ROOM_BYTES for blob in padded), "a blob runs past the room: `RomBench._vet_tenancy` refuses it"
    return bytes(next(poison for poison in POISONS if all(poison != blob[offset] for blob in padded))
                 for offset in range(ROOM_BYTES))


@functools.cache
def the_blobs_poison():
    """...of the build's two blobs, made once a process (a quarter of a megabyte, byte by byte)."""
    return poison_of([_blob_bytes(transcription.BENCH_ELF), _blob_bytes(transcription.SHIPPED_ELF)])


def holds_no_blob(memory):
    return bytes(memory[ROOM[0]:ROOM[0] + BLOB_HEAD_BYTES]) == _NO_BLOB_HEAD


class Poisoner:
    """The doors' wrapper: `runs` counts the ROM-shore runs (and resumed segments) made over a poisoned room."""

    def __init__(self, poison):
        self.poison, self.runs = poison, 0
        self._resumable = None                          # the memory `run_bench` was last handed: `bench_resume` runs over it

    def _laid(self, memory):
        """Poison laid over every byte of the room `memory` holds as zero (a case's own staging there stays, and what
        an earlier segment of the run stored). Answers what the room held, for `_put_back` — or None for a machine
        that holds a blob."""
        if not holds_no_blob(memory):
            return None
        found = bytes(memory[ROOM[0]:ROOM[1]])
        laid = self.poison if found == _EMPTY_ROOM else bytes(
            poison if byte == 0 else byte for byte, poison in zip(found, self.poison))
        memory[ROOM[0]:ROOM[1]] = laid
        self.runs += 1
        return found, laid

    def _put_back(self, memory, held):
        """The room as the run left it, less the poison: a byte the run did not store is what it was found as."""
        if held is None:
            return
        found, laid = held
        left = bytes(memory[ROOM[0]:ROOM[1]])
        memory[ROOM[0]:ROOM[1]] = found if left == laid else bytes(
            was if now == poisoned else now for was, now, poisoned in zip(found, left, laid))

    def run(self, door, image, /, *args, **kwargs):
        memory = bytearray(image)                       # `emu.run` runs a copy of its own: this one is the copy poisoned
        held = self._laid(memory)
        final, writes, registers = door(memory, *args, **kwargs)
        self._put_back(final, held)
        return final, writes, registers

    def run_bench(self, door, memory, /, *args, **kwargs):
        self._resumable = memory
        held = self._laid(memory)
        try:
            return door(memory, *args, **kwargs)
        finally:
            self._put_back(memory, held)

    def bench_resume(self, door, /, *args, **kwargs):
        memory = self._resumable
        held = None if memory is None else self._laid(memory)
        try:
            return door(*args, **kwargs)
        finally:
            self._put_back(memory, held)


DOORS = ("run", "run_bench", "bench_resume")            # every way a run enters the oracle but a by-hand single step


@contextlib.contextmanager
def armed(poison=None):
    """The oracle's doors wrapped for the block: answers the `Poisoner` (its `runs`)."""
    poisoner = Poisoner(the_blobs_poison() if poison is None else poison)
    doors = {name: getattr(emu, name) for name in DOORS}
    for name, door in doors.items():
        setattr(emu, name, lambda *args, _wrapped=getattr(poisoner, name), _door=door, **kwargs: _wrapped(_door, *args, **kwargs))
    try:
        yield poisoner
    finally:
        for name, door in doors.items():
            setattr(emu, name, door)
