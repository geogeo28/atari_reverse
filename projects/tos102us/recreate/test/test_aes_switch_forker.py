"""forker PRICED — the fork functions' addresses in compared RAM, relocated for our blob.

A queue entry's CODE is a fork function's address: the ROM's in a queue the ROM's interrupts filled, the function's
own entry in what our build queues (`aes/evfork.h`). forker `jsr`s what the entry holds, and its RECORDER compares
it — and the code of the record before the cursor — with the entries our build links. So forker's own rows, whose
machine is a ROM-made queue and a ROM-made recording, could not run on our blob as they stand: its forker would run
the ROM's fork functions, and never merge a tick into the tick the ROM recorded before it. Tier 3 RELOCATES both as
the machine is laid into our blob — the queue's code longwords and the recording's, each ROM fork function to our
entry of the same function — and back before the compare (`bench/tier3.py`: `RomBench._call`), so nothing of either
is dropped and the compare is exact.

WHAT THIS FILE HOLDS, beside the rows themselves (`test_aes_evfork.py` registers them; `test_tier3.py` measures each):
  * our forker, over a ROM-made queue, runs NO INSTRUCTION OF THE AES'S ROM TEXT — the relocation's whole point, read
    off the oracle's cycle profile; on the kit's own bench, with no relocation, the same run does (the premise);
  * THE RECORDER'S THREE ARMS on target, each a row and each held here on both blobs: a tick COPIED into the
    recording, a second tick MERGED into the record before it, and Control-backslash ENDING the recording — the
    recording our run leaves the ROM's, byte for byte, its codes compared; and the merge arm's own premise: on the
    kit's bench, where the record before the cursor still holds the ROM's tchange, our forker does NOT merge.
"""
import pytest

from harness import addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_event
import case
import test_aes_evfork          # noqa: F401  (forker's rows are registered where its battery is imported)
import transcription

FORKER_ROWS = {name: row for name, *row in aes.ROWS.cases if name.startswith("aes_forker, ")}
A_KEY_QUEUED = "aes_forker, a key to the desk's wait"
A_TICK_RECORDED = "aes_forker, a tick recorded"
A_TICK_MERGED = "aes_forker, the second tick, merged into the first"
THE_RECORDING_ENDED = "aes_forker, Control-backslash ends the recording"
RECORDER_ROWS = (A_TICK_RECORDED, A_TICK_MERGED, THE_RECORDING_ENDED)
BLOBS = {"the bench blob": None, "the shipped blob": transcription.SHIPPED_ELF.parent}
ENTRY_BYTES = aes.FORK_ENTRY_BYTES
# What a forker row may drop: the words that differ by nature (`aes_event.settled`) — never a byte of the queue or
# of the recording.
BY_NATURE = {(lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW + aes_event.sr_drops()}


def test_forker_s_rows_are_priced_and_drop_no_code():
    """Every row of forker is a PRICED row of the registry — the recorder's three arms among them — and none drops
    a fork function's address: the queue's and the recording's are relocated, not excused."""
    assert {A_KEY_QUEUED, *RECORDER_ROWS} <= set(FORKER_ROWS)
    assert not [name for name, *_row in aes.ROWS.unpriced if name.startswith("aes_forker, ") and "caller's call" not in name]
    dropped = case.tier3_dropped()
    for name in FORKER_ROWS:
        elsewhere = {(lo, hi) for lo, hi, _why in dropped.get(name, ())} - BY_NATURE
        assert not elsewhere, f"{name} drops {sorted(elsewhere)}: no word that differs by nature"


def _our_run(bench, name):
    """`name`'s row run on `bench`'s blob, the oracle's cycle profile on: `(the memory it left, the cycles it spent
    in the AES's ROM text)`."""
    _entry, _regs, pokes, *_seeds = FORKER_ROWS[name]
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        ran = bench._call(make_image(pokes), "aes_forker", (0,))
    finally:
        emu.prof_enable(False)
    return ran.image, emu.prof_cycles(*aes.AES_TEXT)


def _the_rom_s_run(name):
    entry, regs, pokes, *_seeds = FORKER_ROWS[name]
    started = make_image(pokes)
    final, _writes, _regs = emu.run(started, entry, dict(regs))
    return started, final


@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
def test_our_forker_runs_a_rom_made_queue_through_our_own_fork_functions(directory):
    """The queue of the row holds the ROM's kchange; our forker, on Tier 3's bench, spends NO cycle in the AES's ROM
    text — and on the kit's own bench (no relocation) it does: it runs the ROM's kchange and everything under it."""
    _entry, _regs, pokes, *_seeds = FORKER_ROWS[A_KEY_QUEUED]
    assert [code for code, _data in aes_event.fork_queue(make_image(pokes))] == [addrs.AES_ROM_KCHANGE]
    _image, in_the_rom = _our_run(bench_tier3().RomBench(directory), A_KEY_QUEUED)
    assert in_the_rom == 0, f"our forker spent {in_the_rom} cycles in the AES's ROM text"
    _image, unrelocated = _our_run(rom_bench.RomBench(directory), A_KEY_QUEUED)
    assert unrelocated > 0, "the premise: without the relocation our forker runs the ROM's fork function"


def _recorder(image):
    """The recorder's three globals: whether it records, how many records are left, where the next one goes."""
    return {"on": case.word_in(image, aes.AES_GL_RECD), "left": case.word_in(image, aes.AES_RECORD_LEFT),
            "cursor": case.long_in(image, aes.AES_RECORD_CURSOR)}


def _recording(image, lo, hi):
    return bytes(image[lo:hi])


# Each arm's PREMISE on the ROM's own run: what the recorder's globals do (the cursor on by a record, held, held with
# the recording off).
ARMS = {A_TICK_RECORDED: (ENTRY_BYTES, True), A_TICK_MERGED: (0, True), THE_RECORDING_ENDED: (0, False)}


@pytest.mark.parametrize("name", RECORDER_ROWS, ids=lambda name: name.removeprefix("aes_forker, "))
@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
def test_the_recorder_s_arm_leaves_the_rom_s_recording_on_target(directory, name):
    """EACH ARM OF THE RECORDER, ON TARGET: over the ROM-made queue and recording of the row, our forker on Tier 3's
    bench leaves the recording the ROM's run leaves — the record before the cursor (the one a merge adds to), every
    record written, their CODES compared (each shore's own address of the same fork function, mapped), the cursor,
    the count left and the recording's switch — and runs no cycle of the AES's ROM text."""
    started, final = _the_rom_s_run(name)
    moved, still_on = ARMS[name]
    found, left = _recorder(started), _recorder(final)
    assert left["cursor"] - found["cursor"] == moved and bool(left["on"]) == still_on, f"the premise of {name}: {found} -> {left}"
    ours, in_the_rom = _our_run(bench_tier3().RomBench(directory), name)
    assert in_the_rom == 0, f"our forker spent {in_the_rom} cycles in the AES's ROM text"
    assert _recorder(ours) == left
    lo, hi = found["cursor"] - ENTRY_BYTES, left["cursor"] + ENTRY_BYTES
    assert _recording(ours, lo, hi) == _recording(final, lo, hi), "the recording our forker leaves is not the ROM's"


@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
def test_without_the_recording_relocated_our_forker_does_not_merge(directory):
    """THE MERGE ARM'S PREMISE, on the kit's own bench: the record before the cursor holds the ROM's tchange, which
    our forker compares with OUR entry — so it COPIES the tick as a new record where the ROM's adds it to the one
    before: the cursor a record further than the ROM's run leaves it. The relocation is what the row rests on."""
    _started, final = _the_rom_s_run(A_TICK_MERGED)
    tchange = addrs.AES_ROM_TCHANGE
    _entry, _regs, pokes, *_seeds = FORKER_ROWS[A_TICK_MERGED]
    queue_as_ours = bench_tier3().map_fork_codes(make_image(pokes), bench_tier3().fork_relocation(
        bench_tier3().RomBench(directory).elf, "aes_forker"))
    assert case.long_in(queue_as_ours, _recorder(queue_as_ours)["cursor"] - ENTRY_BYTES + aes.FORK_CODE) == tchange
    ours = rom_bench.RomBench(directory)._call(queue_as_ours, "aes_forker", (0,)).image
    assert _recorder(ours)["cursor"] == _recorder(final)["cursor"] + ENTRY_BYTES
