"""NO PRICED ROW'S ROM-SHORE RUN READS THE BLOB'S ROOM — held by a poison differential (`room_poison.py` says why and
what it cannot see). Every row of the Tier-3 table is measured twice, cold: as the table measures it, and again with
`[bench_base, staging_base)` poisoned under every run that holds no blob. A row whose poisoned measurement is refused
(its own differential: the ROM's run answered or stored something else), or whose costs moved, is NAMED.

SHARDED over xdist by `chunk` (the shares of `tier3._shares`: a session's sliced rows stay together); the generation
of the shares is `shares_of`, the checking is `refused_under_poison`.
"""
import pytest

import harness
from harness import emu

tier3 = harness.bench_tier3()

import room_poison                                          # noqa: E402
import staging                                              # noqa: E402
import vdi                                                  # noqa: E402

CHUNKS = 32
NOT_HELD_ROWS = 16                                          # the our-boot stretches (`is_not_held`)


def shares_of(chunk):
    """Every CHUNKS-th share of the table's rows from `chunk`: each row in exactly one chunk."""
    return tier3._shares(tier3.ROWS)[chunk::CHUNKS]


def _named(index):
    row = tier3.ROWS[index]
    return f"{row.symbol} | {row.case}"


def _measured(bench, share):
    """`{index: its Measurement}` over one share, a session's rows off one pair of runs as the table makes them."""
    sessions = tier3.Sessions(bench)
    return {index: tier3.measure(tier3.ROWS[index], bench, sessions) for index in share}


def is_not_held(share):
    """A STRETCH OF OUR OWN START-UP (`tier3.is_a_stretch`) IS NOT HELD HERE, BY NAME: its ROM shore is the ROM's own
    boot from the pre-init capture, a run made once a process and remembered — made by the unpoisoned pass, before the
    guard is armed. (Reviewer B's read watch saw four ROM boots to the first idle read nothing of the room; that is a
    measurement of one day, not this guard.)"""
    return all(tier3.is_a_stretch(tier3.ROWS[index]) for index in share)


def refused_under_poison(bench, share):
    """Why `share`'s rows do not stand under the poison, a line each — none for a share that does."""
    plain = _measured(bench, share)
    with room_poison.armed() as poisoner:
        try:
            poisoned = _measured(bench, share)
        except Exception as refused:                        # the row's own differential: the ROM's run moved
            return [f"{' / '.join(map(_named, share))}: REFUSED under the poison — {type(refused).__name__}: {str(refused)[:400]}"]
    if bool(poisoner.runs) == is_not_held(share):
        return [f"{' / '.join(map(_named, share))}: {poisoner.runs} run(s) of the ROM's shore made under the poison — "
                + ("a stretch said to be NOT HELD is held now: drop it from `is_not_held`" if poisoner.runs
                   else "nothing was held, and the row is not one `is_not_held` names")]
    return [f"{_named(index)}: costs {tier3._costs(plain[index])} moved to {tier3._costs(poisoned[index])} under the poison"
            for index in share if tier3._costs(poisoned[index]) != tier3._costs(plain[index])]


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_no_priced_row_s_rom_shore_run_reads_the_blob_s_room(chunk, monkeypatch):
    """`monkeypatch`: the test patches the oracle's doors, so nothing is served from the kept derivations and no run
    is made in the zygote's fork (`conftest.py`) — both passes are made here, under what this test arms."""
    bench = tier3.RomBench()
    refused = [line for share in shares_of(chunk) for line in refused_under_poison(bench, share)]
    assert not refused, (
        f"{len(refused)} priced row(s) whose ROM-shore run READS THE BLOB'S ROOM [{room_poison.ROOM[0]:#x}, "
        f"{room_poison.ROOM[1]:#x}) — free RAM on the ROM's shore, the blob on ours, so the row measures the blob's "
        f"layout. Move the case's read into a span it registers (`staging.HIGH_BANDS`):\n  " + "\n  ".join(refused))


def test_every_row_is_in_one_chunk_and_the_rows_not_held_are_the_stretches_alone():
    shares = [share for chunk in range(CHUNKS) for share in shares_of(chunk)]
    assert sorted(index for share in shares for index in share) == list(range(len(tier3.ROWS)))
    not_held = sorted(index for share in shares if is_not_held(share) for index in share)
    assert not_held == [index for index, row in enumerate(tier3.ROWS) if tier3.is_a_stretch(row)]
    assert len(not_held) == NOT_HELD_ROWS


def test_the_poison_is_no_byte_of_either_blob_and_never_zero():
    blobs = [room_poison._blob_bytes(elf) for elf in (room_poison.transcription.BENCH_ELF, room_poison.transcription.SHIPPED_ELF)]
    poison = room_poison.poison_of(blobs)
    assert len(poison) == room_poison.ROOM_BYTES and 0 not in poison
    for blob in blobs:
        assert any(blob[:room_poison.BLOB_HEAD_BYTES]), "a blob whose head is zero would be taken for no blob"
        assert not any(byte == poisoned for byte, poisoned in zip(blob, poison))


# ---- the guard's own reds --------------------------------------------------------------------------------------------
# A READ PLANTED IN THE ROOM: a four-instruction routine staged in the declared band — `move.b ROOM_READ_AT,d0`,
# `move.b d0,ANSWER_AT`, `rts` — run through the oracle's first door as a case's ROM-shore run is.
ROOM_READ_AT = room_poison.ROOM[0] + 0x2345E
ROUTINE_AT = staging.POINTER_ARGUMENTS
ANSWER_AT = staging.POINTER_ARGUMENTS + 0x40
MOVE_B_ABSOLUTE_LONG_TO_D0, MOVE_B_D0_TO_ABSOLUTE_LONG, RTS = 0x1039, 0x13C0, 0x4E75
PLANTED_READ = (vdi.pack_words(MOVE_B_ABSOLUTE_LONG_TO_D0) + ROOM_READ_AT.to_bytes(4, "big")
                + vdi.pack_words(MOVE_B_D0_TO_ABSOLUTE_LONG) + ANSWER_AT.to_bytes(4, "big") + vdi.pack_words(RTS))


def _planted_read_s_answer():
    final, _writes, _registers = emu.run(harness.make_image({ROUTINE_AT: PLANTED_READ}), ROUTINE_AT)
    return final


def test_a_read_planted_in_the_room_answers_the_poison_and_the_room_is_put_back():
    assert _planted_read_s_answer()[ANSWER_AT] == 0
    with room_poison.armed() as poisoner:
        final = _planted_read_s_answer()
    assert poisoner.runs == 1
    assert final[ANSWER_AT] == poisoner.poison[ROOM_READ_AT - room_poison.ROOM[0]] != 0, "the read was not served the poison"
    assert bytes(final[room_poison.ROOM[0]:room_poison.ROOM[1]]) == bytes(room_poison.ROOM_BYTES), "the room was left poisoned"
    assert emu.run.__module__ == emu.__name__, "the doors were not put back"


def test_a_machine_that_holds_a_blob_is_not_poisoned():
    blob = room_poison._blob_bytes(room_poison.transcription.SHIPPED_ELF)
    with room_poison.armed() as poisoner:
        final, _writes, _registers = emu.run(harness.make_image({ROUTINE_AT: PLANTED_READ, room_poison.ROOM[0]: blob}), ROUTINE_AT)
    assert poisoner.runs == 0 and final[ANSWER_AT] == blob[ROOM_READ_AT - room_poison.ROOM[0]]


def test_a_byte_a_case_staged_in_the_room_is_read_as_staged_and_stays():
    """The slow path of both halves: a byte the case itself staged in the room is NOT poisoned over — the run reads
    it as staged — and is there when the run ends, every other byte of the room put back."""
    staged = 0x7E
    with room_poison.armed() as poisoner:
        final, _writes, _registers = emu.run(harness.make_image({ROUTINE_AT: PLANTED_READ, ROOM_READ_AT: bytes((staged,))}), ROUTINE_AT)
    assert poisoner.runs == 1 and final[ANSWER_AT] == staged == final[ROOM_READ_AT]
    assert bytes(final[room_poison.ROOM[0]:room_poison.ROOM[1]]).count(0) == room_poison.ROOM_BYTES - 1
