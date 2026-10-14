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


# ==== BAND 6 WAVE 2 (group G3): THE WINDOWS' OPENERS AND CLOSERS ======================================================
# Each case an arrival (`aes_deskwin.arrival`: a chain of the hands stopped at the routine's first instruction, its
# arguments off its caller's frame), every one a ROW THAT SWITCHES (`aes_deskwin.row`, held by the companion, nothing
# dropped). A routine whose run traps runs over GEMDOS REPLAYED — and, under drive_check, the floppy too
# (`aes_desksupp.replayed_row`: the ROM's run in place's answers, DTAs and driver, A LABELLED STAGING said in the id).
# THE MOVE16 STAND-IN: a folder of these chains is New Folder's (`$fe1ece`'s word, executed by `aes_boot.continued`'s
# stand-in) — the arrivals on "folder: …" chains stand on it.
import aes_deskwin as w                 # noqa: E402 — wave 2's, kept with its section
import case                             # noqa: E402
from harness import addrs               # noqa: E402

Case = w.Case
OPEN, OPENED, TWO_WINDOWS = "A: File > Open", "A: opened", "window: A: opened again (two windows)"
FILES, SHOWN = "files: A: opened", "file: shown, a key at its end"
FOLDER_OPENED, FOLDER_CLOSED = "folder: opened", "folder: File > Close"
CLOSE_WINDOW, CLOSER = "window: File > Close Window", "window: its closer clicked"
FORMAT_RETURN = "A: File > Format, Return (the warning answered)"
ONE_OF_TWO_CLOSED = "two windows: File > Close Window (one left on top)"
NO_PATH_NODE = ("no path node free (LAID: g_pavail 0 — every chain finds the pool's nodes free): pn_open answers 0, the "
                "alert raised (Return at the first idle), the window on top (none) the desk's current")
PATH_REFUSED = ("the folder's path refused (its Dsetpath REPLAYED answering EPTHNF, -34: every chain's path is the disk's "
                "own): the drive's root's spec in its place")
EPTHNF = addrs.parse(aes.INCLUDE / "gemdos" / "fs.h")["GEMDOS_EPTHNF"]     # GEMDOS's path-not-found, a longword
DESK_PATHS_FREE = db.DESK_GLOBALS["DESK_PATHS_FREE"]                         # g_pavail
# The cases whose run traps GEMDOS (do_wopen's win_top's pro_chdir, pn_active's searches) — replayed; and those whose
# run reaches drive_check — the floppy replayed too, at drive_check's first arrival in the case's own chain.
TRAPS_J = frozenset({"AES_ROM_DO_DIROPEN", "AES_ROM_DO_DOPEN", "AES_ROM_DO_FOPEN", "AES_ROM_CLOSE_WINDOW", "AES_ROM_CLOSE_FOLDER",
                     "AES_ROM_FUN_CLOSE"})
UNDER_DRIVE_CHECK = frozenset({"AES_ROM_DO_DOPEN", "AES_ROM_DO_FOPEN", "AES_ROM_CLOSE_FOLDER"})
STANDS_ON_THE_MOVE16_STAND_IN = frozenset({FOLDER_OPENED, FOLDER_CLOSED})
RETURN_AT_THE_FIRST_IDLE = {0: aes_event.key(aes_event.RETURN_KEY)}

# (a row's own budget where its run is long — a window opened and drawn: 6 x the measured run, `aes_event`'s rule)
CASES_WAVE_2 = (
    Case("AES_ROM_DO_DIROPEN", OPEN, budget=2_900_000), Case("AES_ROM_DO_DIROPEN", TWO_WINDOWS, budget=3_200_000),
    Case("AES_ROM_DO_DIROPEN", FILES, budget=2_900_000), Case("AES_ROM_DO_DIROPEN", SHOWN, budget=2_600_000),
    Case("AES_ROM_DO_DIROPEN", FOLDER_OPENED, budget=2_160_000), Case("AES_ROM_DO_DIROPEN", FOLDER_CLOSED),
    Case("AES_ROM_DO_DOPEN", OPEN, budget=2_950_000), Case("AES_ROM_DO_DOPEN", TWO_WINDOWS, budget=3_300_000),
    Case("AES_ROM_DO_DOPEN", FILES, budget=3_000_000),
    Case("AES_ROM_DO_FOPEN", FOLDER_OPENED, budget=2_250_000), Case("AES_ROM_DO_FOPEN", FOLDER_CLOSED),
    Case("AES_ROM_DESK_DO_FORMAT", FORMAT_RETURN),
    Case("AES_ROM_CLOSE_WINDOW", CLOSE_WINDOW), Case("AES_ROM_CLOSE_WINDOW", CLOSER),
    Case("AES_ROM_CLOSE_FOLDER", FOLDER_CLOSED, budget=2_100_000),
    Case("AES_ROM_FUN_CLOSE", CLOSE_WINDOW), Case("AES_ROM_FUN_CLOSE", CLOSER), Case("AES_ROM_FUN_CLOSE", FOLDER_CLOSED, budget=2_100_000),
    Case("AES_ROM_CLOSE_WINDOW", ONE_OF_TWO_CLOSED, budget=2_450_000), Case("AES_ROM_FUN_CLOSE", ONE_OF_TWO_CLOSED, budget=2_500_000),
    # (the two arms no chain makes: each a labelled staging over an arrival's own machine, said in the id)
    Case("AES_ROM_DO_DIROPEN", OPEN, arguments=lambda a: a.arguments, why=NO_PATH_NODE),
    Case("AES_ROM_DO_FOPEN", FOLDER_OPENED, arguments=lambda a: a.arguments, why=PATH_REFUSED, budget=2_250_000),
)
WAITS_J = {("AES_ROM_DESK_DO_FORMAT", FORMAT_RETURN): RETURN_AT_THE_FIRST_IDLE, ("AES_ROM_DO_DIROPEN", OPEN, NO_PATH_NODE): RETURN_AT_THE_FIRST_IDLE}


def _path_refused(each):
    """The case's script with the SECOND Dsetpath — pro_chdir of the folder's own path — answering EPTHNF."""
    script = list(ds.gemdos_script(each.name, each.chain, each.nth))
    arrived, ran = ds.watched(each.name, each.chain, each.nth)
    second = [nth for nth, call in enumerate(ran.calls) if call.function == ds.DSETPATH][1]
    script[second] = (EPTHNF & aes.LONG_MASK, script[second][1])
    return tuple(script)


def _waits(each):
    return WAITS_J.get((each.name, each.chain) if not each.why else (each.name, each.chain, each.why), {})
TRAPS_J_CASE = lambda each: each.name in TRAPS_J and each.why != NO_PATH_NODE      # noqa: E731
BY_LABEL_WAVE_2 = {w.label(each) + (f"; {ds.REPLAYED}" if TRAPS_J_CASE(each) else "") + (" [LAID]" if each.why else ""): each
                   for each in CASES_WAVE_2}
assert len(BY_LABEL_WAVE_2) == len(CASES_WAVE_2), "two cases of one name"


def row_of_wave_2(each):
    """The case's row that switches: replayed where its run traps, woken where it waits."""
    if TRAPS_J_CASE(each):
        return ds.replayed_row(each, (each.chain, 1) if each.name in UNDER_DRIVE_CHECK or (
            each.name == "AES_ROM_FUN_CLOSE" and each.chain == FOLDER_CLOSED) else None,
            script=_path_refused(each) if each.why == PATH_REFUSED else None)
    arrived = w.arrival_of(each)
    pokes = w.megabyte(arrived)
    if each.why == NO_PATH_NODE:
        pokes = case.merge_pokes(pokes, {case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) + DESK_PATHS_FREE: bytes(aes.LONG_BYTES)})
    return aes_event.woken_row(w.label(each), each.name, arrived.arguments, lambda: pokes, _waits(each), None, objects=True,
                               budget=each.budget)


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core held to the ROM's routine from the same entry (the companion: every dispatch, the image
    where it returns, the answer); the ROM's run idles only where the case's wake says."""
    each = BY_LABEL_WAVE_2[name]
    the_row = row_of_wave_2(each)
    w.held(the_row)
    assert bool(w.the_rom_s_run(the_row).idles) == bool(_waits(each))


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 20, 2


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    """The seven, each with a case at its own arrival; the two labelled stagings do_diropen's and do_fopen's."""
    at_its_own = [each for each in CASES_WAVE_2 if not each.why]
    assert {each.name for each in at_its_own} == set(ds.UNIT_J_WAVE_2)
    assert {each.name for each in CASES_WAVE_2 if each.why} == {"AES_ROM_DO_DIROPEN", "AES_ROM_DO_FOPEN"}
    assert (len(at_its_own), len(CASES_WAVE_2) - len(at_its_own)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)
    assert set(UNPINNED_WAVE_2) <= set(ds.UNIT_J_WAVE_2)


def test_the_arrivals_on_a_session_folder_stand_on_the_move16_stand_in():
    """THE MOVE16 RULE (cut §4): do_fopen and close_folder are reached ONLY through a folder New Folder made — the
    File menu's `$fe1ece` word, which the oracle executes as MOVE16 and `aes_boot.continued`'s stand-in takes: every
    case of theirs is on such a chain (said here, and in the hand-back)."""
    assert {each.chain for each in CASES_WAVE_2 if each.name in ("AES_ROM_DO_FOPEN", "AES_ROM_CLOSE_FOLDER")} \
        <= STANDS_ON_THE_MOVE16_STAND_IN


UNPINNED_WAVE_2 = {
    "AES_ROM_DO_DIROPEN": "the cartridge's drive 'c' (its window named \"Cartridge\", the name kept as the root's): no cartridge "
                          "in the model (W6-R8)",
    "AES_ROM_DO_DOPEN": "no window free (a fifth: four open — no chain opens four); the drive's check failing (a read error, "
                        "W3-R7; every icon's drive is in the map); the cartridge's icon (W6-R8)",
    "AES_ROM_DO_FOPEN": "the drive's check failing (as do_dopen's)",
    "AES_ROM_DESK_DO_FORMAT": "a window current (selecting a desktop icon makes none current); an icon not a disk (Format is "
                              "enabled for disks alone)",
}
# D0: every routine of the seven answers a word in C, compared on every case (the companion); WHO READS IT
# (`aes_deskbind.answer_readers`, every call site): do_diropen's 1 and fun_close's word by nothing.
READ_AT_WAVE_2 = {"AES_ROM_DO_DOPEN": 2, "AES_ROM_DO_FOPEN": 1, "AES_ROM_DESK_DO_FORMAT": 1, "AES_ROM_CLOSE_WINDOW": 1,
                  "AES_ROM_CLOSE_FOLDER": 1}


# THE WARNING'S OK (the fix pass's, Reviewer B's probe): clicked — the click wake of unit H's cases
# (`aes_deskfun.clicked` over `alert_button_point`, the alert up after the chain's step before its last): FORMAT's
# command and tail kept, pro_run — and pro_cmd's 252 tail. AN ARRIVAL: the chain's own, its wake another hand.
import aes_desk                         # noqa: E402
import aes_deskfun                      # noqa: E402

FORMAT_BUDGET = 2_300_000               # pro_run's launch set-up after the OK: ~380,000 instructions (6 x, `aes_event`'s rule)
FORMAT_OK = aes_deskfun.clicked(aes_deskfun.alert_button_point("OK"), len(aes_desk.CHAINS[FORMAT_RETURN].steps) - 2)


def _format_row(label, at_idle, *layers, budget=None):
    each = Case("AES_ROM_DESK_DO_FORMAT", FORMAT_RETURN, budget=budget)
    arrived = w.arrival_of(each)
    pokes = case.merge_pokes(w.megabyte(arrived), *layers)
    return aes_event.woken_row(f"{w.label(each)}; {label}", each.name, arrived.arguments, lambda: pokes, at_idle, None,
                               objects=True, budget=each.budget)


def test_desk_do_format_s_warning_answered_ok_by_a_click_is_the_rom_s():
    row = _format_row("the warning's OK clicked", FORMAT_OK.at_idle(FORMAT_RETURN), budget=FORMAT_BUDGET)
    w.held(row)
    assert w.the_rom_s_run(row).idles


def test_desk_do_format_over_a_stale_host_slot__a_labelled_staging():
    """A LABELLED STAGING — THE GROUP'S HOST SLOT LAID STALE (every case finds it zeroed; on target the local is the
    stack's garbage): the letter's NUL is written, not found."""
    row = _format_row("Return; the SUPP frame's slot LAID stale __a_labelled_staging",
                      RETURN_AT_THE_FIRST_IDLE, aes.stale_host_slot("AES_DESK_SUPP_FRAME"))
    w.held(row)


def test_the_wave_2_answers_are_read_where_the_reading_says():
    read = {name: len(db.answer_readers(da.entry_of(name))) for name in ds.UNIT_J_WAVE_2}
    assert {name: sites for name, sites in read.items() if sites} == READ_AT_WAVE_2
    assert all(restype is aes.WORD_ANSWER for restype, _frame in ds.SIGNATURES_WAVE_2.values())


def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_a_wave_2_one(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`), asked of unit J's wave-2 seven."""
    assert not db.bound_referrers(blob, ds.UNIT_J_WAVE_2)


def test_the_wave_2_table_s_entries_stay_the_rom_s_and_no_registry_names_one():
    assert w.verdicts_not_the_rom_s(ds.UNIT_J_WAVE_2) == (set(), [])
