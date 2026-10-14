"""UNIT J, drive_check (`src/desk/desksupp.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE ARRIVALS OF ROM
RUNS — LINKED, AND NOTHING BOUND. Every case a row that switches (desk_wait's yields), THE ROM'S FLOPPY DRIVER
REPLAYED (`aes_desksupp`: `DRIVER_REPLAYED` and band 5's scripted GEMDOS in the id).

D0 AT RETURN: drive_check answers nothing in C — the word the ROM leaves (desk_wait's binding's yield leftover, or
fm_error's) is a COUNTED divergence, READ BY NO CALLER (`aes_deskbind.answer_readers`).
"""
import pytest

import aes
import aes_deskapp as da
import aes_deskbind as db
import aes_desksupp as ds
import aes_event

CHAINS = ("A: File > Show Info, Return", "A: File > Open", "A: opened", "window: A: opened again (two windows)",
          "file: File > Show Info, Return")


@pytest.mark.parametrize("chain", CHAINS, ids=[f"drive_check — arrival 0 of {chain} — {ds.DRIVER_REPLAYED}; {da.SCRIPTED}" for chain in CHAINS])
def test_drive_check_at_its_arrival_reads_the_boot_sector_and_forces_the_change(chain):
    """THE CASE: drive A: — in the map, a floppy — its sector's buffer Malloc'ed, the boot sector read (the ROM's
    run's read, replayed: done at once), the media change forced, the buffer given back, the arrow again: the row
    over the arrival's megabyte, nothing dropped; Malloc's and Mfree's ledger the ROM's."""
    arrived = da.arrival(ds.DRIVE_CHECK, chain)
    replay = ds.in_place(arrived)
    row = ds.row_of(arrived, replay)
    assert arrived.arguments == (ord("A"),) and not da.the_rom_s_run(row).idles
    da.held(row)


MEDIA_CHANGED = 0xFFF2                   # Floprd's E_CHNG, -14


def test_drive_check_takes_a_media_change_for_a_read__an_argument_class():
    """A LABELLED STAGING — THE REPLAY ANSWERING E_CHNG (the arrivals' reads answer 0): the read is as good as done —
    no eralert, no AES_DOS_ERR."""
    arrived = da.arrival(ds.DRIVE_CHECK, CHAINS[0])
    replay = ds.in_place(arrived)._replace(floprd=MEDIA_CHANGED)
    da.held(ds.row_of(arrived, replay, label=f"drive_check — Floprd answering E_CHNG — {ds.DRIVER_REPLAYED} __an_argument_class"))


DRIVE_B = ord("B")


def test_drive_check_of_drive_b_reads_it_as_a_floppy__an_argument_class():
    """A LABELLED ARGUMENT CLASS — DRIVE B: (the device model has no drive B:, so no chain hands it), over the first
    arrival's machine, THE DRIVER'S ANSWERS A:'S RUN'S REPLAYED: in the machine's map by its DRIVE's bit (1, not its
    letter's) and a floppy (`<= 'B'`) — read and forced as A: is, Floprd and Rwabs framed for drive 1."""
    arrived = da.arrival(ds.DRIVE_CHECK, CHAINS[0])
    row = ds.row_of(da.with_arguments(arrived, DRIVE_B), ds.in_place(arrived),
                    label=f"drive_check — drive B:, A:'s answers — {ds.DRIVER_REPLAYED} __an_argument_class")
    assert not da.the_rom_s_run(row).idles
    da.held(row)


STALE_VERDICT = 1                       # AES_DOS_ERR as a failed GEMDOS call leaves it (0 at every arrival)


def test_drive_check_clears_a_stale_verdict_before_its_read__a_labelled_staging():
    """A LABELLED STAGING — AES_DOS_ERR LAID 1, a failure's verdict left standing (every arrival finds it 0: the chains'
    one failing call, the read-only file's delete, leaves it 0 by its alert): the first arrival's read, the verdict
    cleared first and left so."""
    arrived = da.arrival(ds.DRIVE_CHECK, CHAINS[0])
    row = ds.row_of(arrived, ds.in_place(arrived), label=f"drive_check — AES_DOS_ERR LAID 1 — {ds.DRIVER_REPLAYED} __a_labelled_staging",
                    laid=({aes.AES_DOS_ERR: STALE_VERDICT.to_bytes(aes.WORD_BYTES, "big")},))
    assert not da.the_rom_s_run(row).idles
    da.held(row)


NO_SUCH_DRIVE = ord("P")


def test_drive_check_of_a_drive_the_map_lacks_alerts__an_argument_class():
    """A LABELLED ARGUMENT CLASS (every caller hands the letter of a drive it shows): drive P:, which the machine's
    map lacks — fm_error(15) raised (its alert waits: Return at the first idle) and AES_DOS_ERR 1; no read, no
    desk_wait. Over the first arrival's machine; nothing replayed."""
    arrived = da.arrival(ds.DRIVE_CHECK, CHAINS[0])
    row = da.row_of(da.with_arguments(arrived, NO_SUCH_DRIVE), at_idle={0: aes_event.key(aes_event.RETURN_KEY)},
                    label="drive_check — drive P:, Return at the first idle __an_argument_class")
    assert da.the_rom_s_run(row).idles
    da.held(row)


def test_no_caller_in_the_rom_reads_what_drive_check_leaves_in_d0():
    """BY READING EVERY CALL SITE: drive_check's D0 is read by nothing — the counted divergence of its cases."""
    assert db.calls_of(da.entry_of(ds.DRIVE_CHECK)) and not db.answer_readers(da.entry_of(ds.DRIVE_CHECK))
    assert len(CHAINS) + 3 == 8
