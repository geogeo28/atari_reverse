"""UNIT J, drive_check (`src/desk/desksupp.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE ARRIVALS OF ROM
RUNS — AND, SINCE BAND 6 SLICE F2, FLIPPED: the Line-F table's entry is its thunk, and every case at an arrival is a
Tier 3 row (`ROWS`, below). Every case a row that switches (desk_wait's yields), THE ROM'S FLOPPY DRIVER REPLAYED
(`aes_desksupp`: `DRIVER_REPLAYED` and band 5's scripted GEMDOS in the id).

D0 AT RETURN: drive_check answers nothing in C — the word the ROM leaves (desk_wait's binding's yield leftover, or
fm_error's) is a COUNTED divergence, READ BY NO CALLER (`aes_deskbind.answer_readers`).
"""
import re

import pytest

import aes
import aes_deskapp as da
import aes_deskbind as db
import aes_desksupp as ds
import aes_event
import case

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


# ---- band 6 slice F2 (group G2): THE UNIT'S ROWS — each case at an arrival a row that switches with no door
# (`aes_desksupp.register_row`: MEASURED, the table's second count — no call of the event layer's door), AES_BIOS_RETURN
# named by nature (`aes_desksupp.BIOS_DOOR_PARKED`); its classes stay Tier 1's. Its pins — DATA, measured by the table's
# own measurement (`aes_switching.priced_by_the_table`) and each blob's second differential (`aes_switching.measured_on`)
# from the rows as registered; re-pinned from a recorded run, never by hand.
#   * NO ROW, by name (`NOT_A_ROW`): the two arrivals whose machine ALREADY HOLDS drive_check's own park in AES_BIOS_RETURN
#     (the chain's earlier drive_check left it: `RWABS_BACK`) — the ROM's run stores the value the machine holds. Until
#     band 6 slice F3 stage 2's third fix pass the census asked for a CHANGED value and refused the name there; it reads
#     the ROM run's STORES since (`aes_switching._its_own_by_nature`, the orchestrator's ruling (a)), and both arrivals
#     then register (MEASURED there: the companion and both blobs' second differentials pass) — held NOT A ROW all the
#     same, unregistered: the orchestrator ruled at F3 stage 2 that they register in a slice of their own (new rows,
#     outside that fix pass, which registered the four arrivals off the park alone). Tier 1 holds both cases; the three
#     other arrivals are rows, at the same price.
NOT_A_ROW = {chain: "AES_BIOS_RETURN already holds drive_check's own park, which the ROM's run stores again: registrable "
                    "under the stores census (measured), unregistered, held for a slice of their own"
             for chain in ("file: File > Show Info, Return", "window: A: opened again (two windows)")}
ROWS = {chain: ds.register_row(da.arrival(ds.DRIVE_CHECK, chain)) for chain in CHAINS if chain not in NOT_A_ROW}
NO_DOOR_PREMISES = {
    "aes_drive_check, arrival 0 of A: File > Open; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_drive_check, arrival 0 of A: File > Show Info, Return; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_drive_check, arrival 0 of A: opened; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED = {
    "aes_drive_check, arrival 0 of A: File > Open; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((15544, 23356), None, None, (0, 0, 0)),
    "aes_drive_check, arrival 0 of A: File > Show Info, Return; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((15544, 23356), None, None, (0, 0, 0)),
    "aes_drive_check, arrival 0 of A: opened; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((15544, 23356), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    "aes_drive_check, arrival 0 of A: File > Open; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (83132, 76728), "bench_shipped": (83132, 76736)},
    "aes_drive_check, arrival 0 of A: File > Show Info, Return; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (83132, 76728), "bench_shipped": (83132, 76736)},
    "aes_drive_check, arrival 0 of A: opened; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (83132, 76728), "bench_shipped": (83132, 76736)},
}


def test_every_case_at_an_arrival_is_a_row_that_switches_with_no_door_and_its_pins_are_the_rows():
    import aes_switching
    names = {aes_switching.row_name(row) for row in ROWS.values()}
    assert len(ROWS) == len(CHAINS) - len(NOT_A_ROW) == 3 and all(row.door is None and row.also_dropped == ds.BIOS_DOOR_PARKED for row in ROWS.values())
    assert names == set(NO_DOOR_PREMISES) == set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN)


NEVER_STORED = aes.AES_BIOS_RETURN - 1     # $95ad: below the park's longword, a byte drive_check's ROM run never stores


def test_the_census_refuses_a_park_name_widened_onto_a_byte_the_rom_s_run_never_stores():
    """THE STORES CENSUS'S REFUSAL, standing (`aes_switching._its_own_by_nature`): every registered name is honest, so
    only a dishonest one shows the census can refuse. A registered row's own park name, widened one byte down onto
    `$95ad` — the companion refuses it by name, before its image is compared (a census that excused every name, or read its
    "stores" off the staged machine rather than the ROM's run, passes it)."""
    import aes_switching
    row = next(iter(ROWS.values()))
    widened = row._replace(also_dropped=((NEVER_STORED, NEVER_STORED + 1, "widened onto a byte the ROM never stores"),
                                         *row.also_dropped))
    with pytest.raises(AssertionError, match=re.escape(f"never stored by the ROM's run: ['{NEVER_STORED:#x}']")):
        aes_switching.companion(widened)


@pytest.mark.parametrize("chain", NOT_A_ROW)
def test_a_case_with_no_row_arrives_with_drive_check_s_own_park_in_the_bios_return(chain):
    """WHY THERE IS NO ROW (`NOT_A_ROW`), READ OFF THE ARRIVAL: AES_BIOS_RETURN holds the return of drive_check's own BIOS
    door call already — and on every row's arrival it holds another."""
    held = lambda arrived: case.long_in(arrived.boot.ram, aes.AES_BIOS_RETURN) & da.BUS
    assert held(da.arrival(ds.DRIVE_CHECK, chain)) == ds.RWABS_BACK
    assert all(held(da.arrival(ds.DRIVE_CHECK, other)) != ds.RWABS_BACK for other in CHAINS if other not in NOT_A_ROW)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_has_its_premise_on_the_rom_s_run(name):
    da.vet_the_premise(name, NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    da.vet_on_a_blob(blob, name, NO_DOOR_PREMISES, NO_DOOR_PRICED, NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_is_priced_as_pinned_and_under_the_bar(name):
    da.vet_the_price(name, NO_DOOR_PRICED)


# ==== BAND 6 WAVE 2 (group G3): THE WINDOWS' OPENERS AND CLOSERS ======================================================
# Each case an arrival (`aes_deskwin.arrival`: a chain of the hands stopped at the routine's first instruction, its
# arguments off its caller's frame), every one a ROW THAT SWITCHES (`aes_deskwin.row`, held by the companion, nothing
# dropped). A routine whose run traps runs over GEMDOS REPLAYED — and, under drive_check, the floppy too
# (`aes_desksupp.replayed_row`: the ROM's run in place's answers, DTAs and driver, A LABELLED STAGING said in the id).
import aes_deskwin as w                 # noqa: E402 — wave 2's, kept with its section
import aes_desk                         # noqa: E402
import case                             # noqa: E402
from harness import addrs               # noqa: E402

Case = w.Case
OPEN, OPENED, TWO_WINDOWS = "A: File > Open", "A: opened", "window: A: opened again (two windows)"
FILES, SHOWN = "files: A: opened", "file: shown, a key at its end"
CARTRIDGE_OPENED = aes_desk.CARTRIDGE_OPENED                 # drive 'c' opened: the labelled class of disk's chain
# a folder opened, and a folder's window closed, in the window the desk restored after a show (the files machine)
SHOWN_THEN_FOLDER_OPENED, SHOWN_THEN_FOLDER_CLOSED = aes_desk.SHOWN_THEN_FOLDER_OPENED, aes_desk.SHOWN_THEN_FOLDER_CLOSED
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
    # (band 6 slice F3's fix pass) THE CARTRIDGE'S ICON OPENED, on the labelled class of disk whose cartridge line is a
    # drive's (`aes_desk.CARTRIDGE_OPENED`): do_dopen's arm for 'c' — no drive_check, no chdir: the ROM's quirk AS IT
    # SHIPS (`desksupp.c` aes_do_dopen) — and do_diropen's, its window named the cartridge's; no GEMDOS call, nothing
    # replayed (measured: both held with no replay)
    Case("AES_ROM_DO_DOPEN", CARTRIDGE_OPENED, budget=3_000_000), Case("AES_ROM_DO_DIROPEN", CARTRIDGE_OPENED, budget=3_000_000),
    # (band 6 slice F3 stage 2's fix pass, reviewer B's probe) A FOLDER'S ACTS IN A WINDOW THE DESK RESTORED AFTER A SHOW
    # (`aes_desk.SHOWN_THEN_FOLDER_*`): the viewer's BIOS door left its own return in AES_BIOS_RETURN and cnx_get's
    # restore ran no drive_check, so do_fopen, close_folder and fun_close's folder arm arrive NOT holding drive_check's
    # park — each a ROW (since the stage's third fix pass: below); each budget ~6 x its measured run where the
    # default's margin does not cover it (do_fopen's 413,074, close_folder's 376,647, fun_close's 383,549 instructions;
    # the folder close's do_fopen, 285,401, the default's)
    Case("AES_ROM_DO_FOPEN", SHOWN_THEN_FOLDER_OPENED, budget=2_500_000), Case("AES_ROM_DO_FOPEN", SHOWN_THEN_FOLDER_CLOSED),
    Case("AES_ROM_CLOSE_FOLDER", SHOWN_THEN_FOLDER_CLOSED, budget=2_100_000),
    Case("AES_ROM_FUN_CLOSE", SHOWN_THEN_FOLDER_CLOSED, budget=2_100_000),
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
TRAPS_J_CASE = lambda each: each.name in TRAPS_J and each.why != NO_PATH_NODE and each.chain != CARTRIDGE_OPENED  # noqa: E731
BY_LABEL_WAVE_2 = {w.label(each) + (f"; {ds.REPLAYED}" if TRAPS_J_CASE(each) else "") + (" [LAID]" if each.why else ""): each
                   for each in CASES_WAVE_2}
assert len(BY_LABEL_WAVE_2) == len(CASES_WAVE_2), "two cases of one name"


FOLDER_CLOSES = (FOLDER_CLOSED, SHOWN_THEN_FOLDER_CLOSED)     # fun_close's folder arm: close_folder, under drive_check


def _floppy(each):
    """drive_check's `(chain, nth)` where the case's run reaches it (the floppy replayed too), else None."""
    under = each.name in UNDER_DRIVE_CHECK or (each.name == "AES_ROM_FUN_CLOSE" and each.chain in FOLDER_CLOSES)
    return (each.chain, 1) if under else None


def row_of_wave_2(each):
    """The case's row that switches: replayed where its run traps, woken where it waits."""
    if TRAPS_J_CASE(each):
        return ds.replayed_row(each, _floppy(each), script=_path_refused(each) if each.why == PATH_REFUSED else None)
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


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 26, 2


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    """The seven, each with a case at its own arrival; the two labelled stagings do_diropen's and do_fopen's."""
    at_its_own = [each for each in CASES_WAVE_2 if not each.why]
    assert {each.name for each in at_its_own} == set(ds.UNIT_J_WAVE_2)
    assert {each.name for each in CASES_WAVE_2 if each.why} == {"AES_ROM_DO_DIROPEN", "AES_ROM_DO_FOPEN"}
    assert (len(at_its_own), len(CASES_WAVE_2) - len(at_its_own)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)
    assert set(UNPINNED_WAVE_2) <= set(ds.UNIT_J_WAVE_2)


UNPINNED_WAVE_2 = {
    "AES_ROM_DO_DIROPEN": "a cartridge in the port (W6-R8: the model's port reads 0 — its drive 'c' opened is pinned, empty, on "
                          "the labelled class's chain)",
    "AES_ROM_DO_DOPEN": "no window free (a fifth: four open — no chain opens four); the drive's check failing (a read error, "
                        "W3-R7; every icon's drive is in the map)",
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


# ---- FLIPPED (band 6 slice F3, stage 2): the seven whole ---------------------------------------------------------------------
def test_the_wave_2_routines_are_flipped(blob):
    """THE FLIP PIN (`aes_deskarrive.flipped`): each core called by its own thunk of the table, each entry OURS THROUGH
    THAT THUNK, none held — and no function outside the unbound desk refers to a core still held."""
    import aes_deskarrive as dar
    assert not ds.UNIT_J_WAVE_2_HELD_AT_F3
    dar.flipped(blob, ds.UNIT_J_WAVE_2)


# ---- band 6 slice F3, stage 2: THE SEVEN'S ROWS — every case at an arrival registered as A ROW THAT SWITCHES
# (`aes_desksupp.registered_row`: `aes_deskwin`'s row machine; where its run traps, over the replay its Tier 1 case runs —
# fslib's GEMDOS, and drive_check's floppy where it runs, AES_BIOS_RETURN then named by nature — said in the row's name;
# the format's warning answered by Return at its first idle). The classes stay Tier 1's.
#   * DOOR USERS, every row (MEASURED, the table's second count: 3 to 16 calls of a rebound entry — the windows' open,
#     close and redraw, the format's alert), pinned in `DOOR_USERS_*_WAVE_2` and read by `test_tier3.py`.
#   * A RUN PAST THE DEFAULT DERIVATION MARGIN DECLARES ITS OWN BUDGET — its Tier 1 case's (the user's ruling of
#     2026-10-21, "rows may declare budget"; held both ways by every derivation of the row): every case that opens or
#     reads a window anew.
#   * THE BIOS PARK NAMED BY NATURE where the run reaches drive_check (`aes_desksupp.BIOS_DOOR_PARKED`), each byte one
#     the ROM's run STORES (the census, `aes_switching._its_own_by_nature`, reads its write ledger since the stage's
#     third fix pass — the orchestrator's ruling (a)). So the arrivals in a window the desk restored after a show
#     (`SHOWN_THEN_FOLDER_*`: do_fopen ×2, close_folder, fun_close's folder arm) are rows: they do NOT hold the park —
#     the viewer's BIOS door left `$fed7de` — and its byte `$95af` is `$fe` in both values, a byte the old census (a
#     CHANGED value) refused, which the ROM's run stores all the same (read off each arrival: the class's test, below);
#     without the name the shipped glue's park (`$06`) differs there.
#   * NOT A ROW, by name (`PARKED_NOT_A_ROW_WAVE_2`): the arrivals under drive_check whose machine ALREADY HOLDS
#     drive_check's own park in AES_BIOS_RETURN — drive_check's own `NOT_A_ROW` class: the ROM's run stores the value the
#     machine holds. Registrable under the stores census (MEASURED at the third fix pass: each companion and both blobs'
#     second differentials pass), and held unregistered for a slice of their own (the orchestrator's ruling at F3 stage 2;
#     that pass registered the four arrivals off the park alone).
_PARKED = ("AES_BIOS_RETURN already holds drive_check's own park, which the ROM's run stores again: registrable under the "
           "stores census (measured), unregistered, held for a slice of their own (drive_check's NOT_A_ROW)")
PARKED_NOT_A_ROW_WAVE_2 = {f"{routine} — arrival 1 of {chain}; {ds.REPLAYED}": _PARKED
                           for routine, chain in (("do_dopen", TWO_WINDOWS), ("do_fopen", FOLDER_OPENED), ("do_fopen", FOLDER_CLOSED),
                                                  ("close_folder", FOLDER_CLOSED), ("fun_close", FOLDER_CLOSED))}
AT_ARRIVALS_WAVE_2 = [name for name, each in BY_LABEL_WAVE_2.items() if not each.why]
DOOR_USERS_WAVE_2 = frozenset(name for name in AT_ARRIVALS_WAVE_2 if name not in PARKED_NOT_A_ROW_WAVE_2)
X_FLAG_DIFFERS_WAVE_2 = frozenset()


def _registered_wave_2(name):
    each = BY_LABEL_WAVE_2[name]
    replayed = TRAPS_J_CASE(each)
    return ds.registered_row(each, replayed=replayed, floppy=_floppy(each) if replayed else None, at_idle=_waits(each),
                             door_user=name in DOOR_USERS_WAVE_2, x_flag_differs=name in X_FLAG_DIFFERS_WAVE_2, budget=each.budget)


ROWS_WAVE_2 = {name: _registered_wave_2(name) for name in AT_ARRIVALS_WAVE_2 if name in DOOR_USERS_WAVE_2}
# ---- THE WAVE-2 ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by
# each blob's second differential (`aes_switching.measured_on`), from the rows as registered (a recorded run, never by hand).
DOOR_USERS_PRICED_WAVE_2 = {
    "aes_do_diropen, arrival 1 of A: File > Open; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((960458, 1403986), (951720, 1387910), 16, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of window: A: opened again (two windows); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((1212804, 1734524), (1204066, 1718448), 16, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of files: A: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((1006138, 1469600), (997400, 1453524), 16, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of file: shown, a key at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((893548, 1316070), (884810, 1299994), 16, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of folder: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((715794, 1093320), (713658, 1089252), 12, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of folder: File > Close; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((448526, 764704), (446390, 760636), 12, (0, 0, 0)),
    "aes_do_dopen, arrival 1 of A: File > Open; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((999134, 1464402), (990396, 1448326), 16, (0, 0, 0)),
    "aes_do_dopen, arrival 1 of files: A: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((1044814, 1530016), (1036076, 1513940), 16, (0, 0, 0)),
    'aes_desk_do_format, arrival 1 of A: File > Format, Return (the warning answered)':
        ((201650, 296262), (180914, 262482), 7, (0, 0, 0)),
    "aes_close_window, arrival 1 of window: File > Close Window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((356026, 446228), (354532, 443128), 3, (0, 0, 0)),
    "aes_close_window, arrival 1 of window: its closer clicked; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((355150, 445310), (353656, 442210), 3, (0, 0, 0)),
    "aes_fun_close, arrival 1 of window: File > Close Window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((371322, 468614), (369828, 465514), 3, (0, 0, 0)),
    "aes_fun_close, arrival 1 of window: its closer clicked; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((370454, 467682), (368960, 464582), 3, (0, 0, 0)),
    "aes_close_window, arrival 1 of two windows: File > Close Window (one left on top); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((796498, 1158098), (788472, 1143378), 12, (0, 0, 0)),
    "aes_fun_close, arrival 1 of two windows: File > Close Window (one left on top); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((811794, 1180484), (803768, 1165764), 12, (0, 0, 0)),
    "aes_do_dopen, arrival 1 of c: opened (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE)":
        ((962458, 1415230), (953720, 1399154), 16, (0, 0, 0)),
    "aes_do_diropen, arrival 1 of c: opened (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE)":
        ((940728, 1380058), (931990, 1363982), 16, (0, 0, 0)),
    # (the stage's third fix pass: a folder's acts in a window restored after a show — the BIOS park named by nature)
    "aes_do_fopen, arrival 1 of files: the long file shown, then the folder AUTO double-clicked in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((792746, 1198474), (790610, 1194406), 12, (0, 0, 0)),
    "aes_do_fopen, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((547294, 900516), (545158, 896448), 12, (0, 0, 0)),
    "aes_close_folder, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((746008, 1137540), (743872, 1133472), 12, (0, 0, 0)),
    "aes_fun_close, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        ((762196, 1161474), (760060, 1157406), 12, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN_WAVE_2 = {
    "aes_do_diropen, arrival 1 of A: File > Open; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5566470, 5228690), "bench_shipped": (5566470, 5229990)},
    "aes_do_diropen, arrival 1 of window: A: opened again (two windows); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (6314658, 5926026), "bench_shipped": (6314658, 5927870)},
    "aes_do_diropen, arrival 1 of files: A: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5663328, 5311552), "bench_shipped": (5663328, 5310762)},
    "aes_do_diropen, arrival 1 of file: shown, a key at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5121544, 4798616), "bench_shipped": (5121544, 4800162)},
    "aes_do_diropen, arrival 1 of folder: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (4262924, 3962492), "bench_shipped": (4262924, 3960634)},
    "aes_do_diropen, arrival 1 of folder: File > Close; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (2566216, 2287178), "bench_shipped": (2566216, 2287414)},
    "aes_do_dopen, arrival 1 of A: File > Open; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (5752670, 5395912), "bench_shipped": (5752670, 5397678)},
    "aes_do_dopen, arrival 1 of files: A: opened; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (5849528, 5478774), "bench_shipped": (5849528, 5478450)},
    'aes_desk_do_format, arrival 1 of A: File > Format, Return (the warning answered)':
        {"bench": (1733966, 1668398), "bench_shipped": (1733966, 1656330)},
    "aes_close_window, arrival 1 of window: File > Close Window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (2662518, 2625370), "bench_shipped": (2662518, 2619284)},
    "aes_close_window, arrival 1 of window: its closer clicked; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (2654820, 2617664), "bench_shipped": (2654820, 2611536)},
    "aes_fun_close, arrival 1 of window: File > Close Window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (2743070, 2699810), "bench_shipped": (2743070, 2693746)},
    "aes_fun_close, arrival 1 of window: its closer clicked; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (2735358, 2692112), "bench_shipped": (2735358, 2686006)},
    "aes_close_window, arrival 1 of two windows: File > Close Window (one left on top); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (4717816, 4448002), "bench_shipped": (4717816, 4449556)},
    "aes_fun_close, arrival 1 of two windows: File > Close Window (one left on top); GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (4798368, 4522442), "bench_shipped": (4798368, 4524018)},
    "aes_do_dopen, arrival 1 of c: opened (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE)":
        {"bench": (5593594, 5249538), "bench_shipped": (5593594, 5248518)},
    "aes_do_diropen, arrival 1 of c: opened (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE)":
        {"bench": (5493494, 5161590), "bench_shipped": (5493494, 5160140)},
    "aes_do_fopen, arrival 1 of files: the long file shown, then the folder AUTO double-clicked in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (4880334, 4557720), "bench_shipped": (4880334, 4555958)},
    "aes_do_fopen, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (3133398, 2828600), "bench_shipped": (3133398, 2825724)},
    "aes_close_folder, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (4397548, 4082848), "bench_shipped": (4397548, 4077952)},
    "aes_fun_close, arrival 1 of files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged":
        {"bench": (4479648, 4158232), "bench_shipped": (4479648, 4153374)},
}


def test_the_wave_2_rows_are_the_cases_at_arrivals_but_the_parked_and_each_is_a_door_user():
    """EVERY CASE AT AN ARRIVAL A ROW THAT SWITCHES THROUGH ITS DOOR, pinned in `DOOR_USERS_*_WAVE_2`, its budget its Tier 1
    case's — but the parked ones; every routine of the seven with a row (do_fopen and close_folder since the stage's
    third fix pass)."""
    import aes_switching
    assert sorted(ROWS_WAVE_2) == sorted(DOOR_USERS_WAVE_2) and all(row.door for row in ROWS_WAVE_2.values())
    assert all(row.budget == BY_LABEL_WAVE_2[name].budget for name, row in ROWS_WAVE_2.items())
    names = {aes_switching.row_name(row) for row in ROWS_WAVE_2.values()}
    assert names == set(DOOR_USERS_PRICED_WAVE_2) == set(DOOR_USERS_WHOLE_RUN_WAVE_2)
    assert {name for name, row in ROWS_WAVE_2.items() if row.x_flag_differs} == set(X_FLAG_DIFFERS_WAVE_2)
    assert {BY_LABEL_WAVE_2[name].name for name in ROWS_WAVE_2} == set(ds.UNIT_J_WAVE_2)
    budgeted = [name for name, row in ROWS_WAVE_2.items() if row.budget]
    assert (len(ROWS_WAVE_2), len(budgeted), len(PARKED_NOT_A_ROW_WAVE_2)) == (21, 14, 5)


def _parks_drive_check_s_own(name):
    each = BY_LABEL_WAVE_2[name]
    return case.long_in(w.arrival_of(each).boot.ram, aes.AES_BIOS_RETURN) & da.BUS == ds.RWABS_BACK


def test_the_parked_cases_are_exactly_the_arrivals_under_drive_check_holding_its_own_park():
    """WHY THERE IS NO ROW (`PARKED_NOT_A_ROW_WAVE_2`), READ OFF EACH ARRIVAL: of the cases whose replay runs drive_check,
    those whose AES_BIOS_RETURN holds the return of drive_check's own BIOS door call already — and only those."""
    under = [name for name in AT_ARRIVALS_WAVE_2 if TRAPS_J_CASE(BY_LABEL_WAVE_2[name]) and _floppy(BY_LABEL_WAVE_2[name])]
    assert set(PARKED_NOT_A_ROW_WAVE_2) == {name for name in under if _parks_drive_check_s_own(name)} and len(under) > 5


def _the_park_s_bytes_held(name):
    """The bytes the BIOS park's name covers (`aes_desksupp.BIOS_DOOR_PARKED`) that the case's arrival holds as
    drive_check's own park (`RWABS_BACK`, what the ROM's run stores there) does: the bytes that run leaves as they were."""
    ram = w.arrival_of(BY_LABEL_WAVE_2[name]).boot.ram
    park = ds.RWABS_BACK.to_bytes(aes.LONG_BYTES, "big")
    return [at for lo, hi, _why in ds.BIOS_DOOR_PARKED for at in range(lo, hi) if ram[at] == park[at - aes.AES_BIOS_RETURN]]


SHOWN_THEN_FOLDER_ROWS = 4                # do_fopen x2, close_folder, fun_close's folder arm
A_BYTE_THE_ROM_STORES_UNCHANGED = [aes.AES_BIOS_RETURN + 1]    # $95af: `$fe` in the viewer's `$fed7de` and in the park


def test_the_rows_in_a_window_restored_after_a_show_name_the_park_over_a_byte_the_rom_stores_unchanged():
    """THE CLASS THE STORES CENSUS ADMITS (the stage's third fix pass), READ OFF EACH ARRIVAL: of the rows whose replay
    runs drive_check, those whose AES_BIOS_RETURN holds a byte the park's name covers as the park does without holding
    the park — exactly the four in a window the desk restored after a show, each over `$95af` alone, each a row naming
    the park (a value-change census refuses each of them there)."""
    under = [name for name in ROWS_WAVE_2 if TRAPS_J_CASE(BY_LABEL_WAVE_2[name]) and _floppy(BY_LABEL_WAVE_2[name])]
    shared = {name: _the_park_s_bytes_held(name) for name in under if _the_park_s_bytes_held(name)}
    assert len(shared) == SHOWN_THEN_FOLDER_ROWS and all(held == A_BYTE_THE_ROM_STORES_UNCHANGED for held in shared.values())
    assert {BY_LABEL_WAVE_2[name].chain for name in shared} == {SHOWN_THEN_FOLDER_OPENED, SHOWN_THEN_FOLDER_CLOSED}
    assert all(ROWS_WAVE_2[name].also_dropped == ds.BIOS_DOOR_PARKED for name in shared)
