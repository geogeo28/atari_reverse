"""UNIT A, THE DESK'S APPLICATION LIST (`src/desk/deskapp.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE
ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY ROUTINE HAS ITS CASES AT ITS ARRIVALS (`aes_deskapp.arrival`): a chain of the hands — or the DESKTOP.INF
    machine's own boot — stopped at the routine's first instruction, the arguments read off its caller's frame. A
    routine that never yields is the kit's differential over the arrival's megabyte; app_tran, whose rsrc_gaddr binding
    yields, the row that switches. A routine that traps runs over the recording trap SCRIPTED WITH THE ANSWERS THE
    ROM'S OWN RUN IN PLACE GOT (`SCRIPTED` in the id).
  * WHERE NO CHAIN TAKES AN ARM, A LABELLED ARGUMENT CLASS (`__an_argument_class` in the id, what is laid said there):
    the same routine over an arrival's machine with other arguments — or a text laid in the group's band, or another
    script.
  * D0 AT RETURN: where the core answers it is held to the ROM's — and the ROM's own run in place, on the desk's
    stack, is held to leave the same word. snap_disk and app_revit answer nothing in C: the ROM's leftover is a COUNTED
    divergence, READ BY NO CALLER (`aes_deskbind.answer_readers`).

WHAT IS NOT HELD: any row, any price, anything of a blob's run.
"""
import pytest

import aes
import aes_deskapp as da
import aes_deskbind as db
import case
from harness import addrs

BOOT = da.THE_BOOT
INSTALL = "A: Options > Install Disk Drive, 'C' typed, Install pressed"
SHOWN = "file: shown, a key at its end"
SAVED = "Options > Save Desktop, Return"
BARE_SPOT = "drive A: dragged to a bare spot of the desktop"       # group G3's chain: an icon put down where it began
SNAP_DISK, SCAN_STR, SAVE_STR = "AES_ROM_SNAP_DISK", "AES_ROM_SCAN_STR", "AES_ROM_SAVE_STR"
APP_PARSE, APP_REVIT, APP_TRAN, APP_GETFH = "AES_ROM_APP_PARSE", "AES_ROM_APP_REVIT", "AES_ROM_APP_TRAN", "AES_ROM_APP_GETFH"
APP_RDICON, APP_BLDDESK = "AES_ROM_APP_RDICON", "AES_ROM_APP_BLDDESK"
REMOVED = "A: Options > Install Disk Drive, Remove pressed"
PATH_SAVE, PATH_RESTORE = "AES_ROM_APP_PATH_SAVE", "AES_ROM_APP_PATH_RESTORE"

# ---- THE ARRIVALS: `{routine: ((chain, how many of its arrivals), ...)}` — every one the chains reach ------------------------
ARRIVALS = {
    SNAP_DISK: ((BOOT, 1), (INSTALL, 1), (SHOWN, 9), (BARE_SPOT, 1)),
    SCAN_STR: ((BOOT, 1), (SHOWN, 18)),
    SAVE_STR: ((SAVED, 18),),
    APP_PARSE: ((BOOT, 1), (SHOWN, 9)),
    APP_REVIT: ((SAVED, 2), (SHOWN, 1)),
    APP_TRAN: ((BOOT, 1), (SHOWN, 1)),
    APP_RDICON: ((BOOT, 1), (SHOWN, 1)),
    APP_BLDDESK: ((BOOT, 1), (REMOVED, 1), (INSTALL, 1), (SHOWN, 1)),
    APP_GETFH: ((SAVED, 1),),
    PATH_SAVE: ((SAVED, 1),),
    PATH_RESTORE: ((SAVED, 1),),
}
# THE GEMDOS CALLS EACH TRAPPING ROUTINE MAKES (the glue's, and set_defdrv's isdrive: Dgetdrv, Dsetdrv, then its own).
TRAPS = {APP_GETFH: 1, PATH_SAVE: 7, PATH_RESTORE: 2}
# EVERY STORE OF THESE IS THROUGH A POINTER THE ROUTINE READ FIRST (g_pbuff, a node's link): the attribution pass
# would invert a pointer the next instruction follows.
POINTERS_IT_FOLLOWS = {"poison": False}
STEERS = {SCAN_STR: POINTERS_IT_FOLLOWS, APP_PARSE: POINTERS_IT_FOLLOWS, APP_REVIT: POINTERS_IT_FOLLOWS}


def _cases():
    return [(routine, chain, nth) for routine, takes in ARRIVALS.items() for chain, count in takes for nth in range(count)]


AT_ARRIVALS = _cases()


def _id(routine, chain, nth):
    scripted = f" — {da.SCRIPTED}" if routine in TRAPS else ""
    return f"{routine[len('AES_ROM_'):].lower()} — arrival {nth} of {chain}{scripted}"


def run_at(arrived):
    """THE CASE at an arrival: `(the differential, the ROM's own run in place)`."""
    routine = arrived.routine
    if routine in TRAPS:
        answers, back = da.dos_answers_in_place(arrived, TRAPS[routine])
        return da.scripted(arrived, answers), back
    return da.plain(arrived, **STEERS.get(routine, {})), da.returned_in_place(arrived)


WIDTH = {aes.WORD_ANSWER: aes.WORD_MASK, aes.LONG_ANSWER: aes.LONG_MASK}


SWITCHES = (APP_TRAN, APP_RDICON, APP_BLDDESK)          # their binding's yield under them: rows that switch, below
PLAIN_ARRIVALS = [case_ for case_ in AT_ARRIVALS if case_[0] not in SWITCHES]


@pytest.mark.parametrize("routine, chain, nth", PLAIN_ARRIVALS, ids=[_id(*case_) for case_ in PLAIN_ARRIVALS])
def test_a_routine_at_its_arrival_is_the_rom_s_and_leaves_its_word_in_place(routine, chain, nth):
    """THE CASE: the C core against the ROM's routine from the arrival (the megabyte, the answer at the declared width
    — the kit's differential) — and THE ROM'S OWN RUN IN PLACE, on the desk's stack, leaves the D0 the harness's run
    leaves: the C's word is the one the ROM's caller reads."""
    arrived = da.arrival(routine, chain, nth)
    result, back = run_at(arrived)
    restype = da.SIGNATURES[routine][0]
    assert back is not None, f"{routine} idles before it returns"
    if restype is not None:
        assert back.registers["d0"] & WIDTH[restype] == result.info["regs"]["d0"] & WIDTH[restype]


@pytest.mark.parametrize("chain", [chain for chain, _count in ARRIVALS[APP_TRAN]])
def test_app_tran_at_its_arrival_is_the_rom_s_through_the_binding_s_yield(chain):
    """app_tran's rsrc_gaddr is the desk's binding, which YIELDS: the row that switches — the C through the host's
    scheduler held to the ROM's scheduled run, nothing dropped, gsx_trans's word the ROM's D0 — and the run in place
    leaves the same word. Its one caller (app_rdicon) hands BITBLK 0."""
    arrived = da.arrival(APP_TRAN, chain)
    row = da.row_of(arrived)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert arrived.arguments == (0,) and not the_rom_s.idles
    assert ran.answer & aes.WORD_MASK == the_rom_s.d0 & aes.WORD_MASK == da.returned_in_place(arrived).registers["d0"] & aes.WORD_MASK


RDICON_MALLOCS = 2                      # the images' block, the masks'


@pytest.mark.parametrize("chain", [chain for chain, _count in ARRIVALS[APP_RDICON]], ids=lambda chain: f"{chain} — {da.SCRIPTED}")
def test_app_rdicon_at_its_arrival_is_the_rom_s_through_its_mallocs_and_app_tran_s_yield(chain):
    """app_rdicon TRAPS (its two Mallocs) AND SWITCHES (app_tran's binding): the row over the arrival's megabyte with
    band 5's recording trap SCRIPTED WITH THE TWO BLOCKS THE ROM'S RUN IN PLACE GOT — the two ICONBLK lists, the image
    kinds, both blocks' images and masks turned, the ledger of the two calls; its 1 the ROM's D0 and the run in
    place's."""
    arrived = da.arrival(APP_RDICON, chain)
    answers, back = da.dos_answers_in_place(arrived, RDICON_MALLOCS)
    row = da.scripted_row(arrived, answers)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert not the_rom_s.idles and ran.answer == the_rom_s.d0 & aes.WORD_MASK == back.registers["d0"] & aes.WORD_MASK == 1


@pytest.mark.parametrize("chain", [chain for chain, _count in ARRIVALS[APP_BLDDESK]], ids=lambda chain: f"{chain} — {da.GETREZ_STAGED}")
def test_app_blddesk_at_its_arrival_is_the_rom_s_through_obj_ialloc_s_yields(chain):
    """app_blddesk SWITCHES (G1's obj_ialloc adds each icon by unit D's objc_add, which yields) and asks GETREZ: the row
    over the arrival's megabyte, the XBIOS answered with the arrival's own mode (low: the colour pattern), every icon
    object, ICONBLK and the drive vector the ROM's — bvset's 1 the ROM's D0 and the run in place's."""
    arrived = da.arrival(APP_BLDDESK, chain)
    row = da.row_of(arrived, layers=(da.getrez_layer(arrived),))
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert not the_rom_s.idles and ran.answer == the_rom_s.d0 & aes.WORD_MASK == da.returned_in_place(arrived).registers["d0"] & aes.WORD_MASK


# ---- THE ARMS THE ARRIVALS TAKE, AND THE LABELLED CLASSES FOR THE REST -----------------------------------------------------------
CLASS = "__an_argument_class"


def desk_word(ram, offset):
    """A word of the desk's global block in the megabyte `ram`."""
    return case.word_in(ram, (case.long_in(ram, aes.AES_DESK_GLOBALS) & da.BUS) + offset)


def snap_arms(arrived):
    """Which arms of the two axes the arrival's arguments take: `{(axis, arm)}` — the remainder past half the grid
    (`up`), the grid's multiple past the span less a grid (`clamped`), past the span's middle (`moved on`)."""
    ram, (x, y, *_outs) = arrived.boot.ram, arrived.arguments
    top = desk_word(ram, da.CONSTANTS["DESK_AREA_Y"])
    taken = set()
    axes = (("x", aes.signed(x), desk_word(ram, da.CONSTANTS["DESK_GRID_W"]), case.word_in(ram, aes.AES_GL_WIDTH)),
            ("y", aes.signed(y) - top, desk_word(ram, da.CONSTANTS["DESK_GRID_H"]), desk_word(ram, da.CONSTANTS["DESK_AREA_H"])))
    for axis, at, grid, span in axes:
        cells, remainder = int(at / grid), at - int(at / grid) * grid
        up = remainder > int(grid / 2)
        snapped = (cells + up) * grid
        clamped = snapped > span - grid
        snapped = min(snapped, span - grid)
        taken |= {(axis, arm) for arm, took in (("up", up), ("clamped", clamped), ("moved on", snapped > int(span / 2))) if took}
    return taken


def test_snap_disk_s_arrivals_take_the_arms_their_data_reaches():
    """THE ARMS THE CHAINS REACH: down, the remainder rounded UP (the Install dialog's icon at y 53) and the snapped
    point PAST THE DESKTOP'S MIDDLE moved on by g_hdesk % g_ich (the INF's seventh icon at y 152, 189 % 47 = 1).
    Across, the boot's and the dialogs' x are 0 or 80 — a multiple of the grid; group G3's drive put down on a bare
    spot (x 246) is the one past the screen's middle — MOVED ON, by 0: THE SCREEN'S 320 IS A MULTIPLE OF THE GRID'S
    80, so a mutant of that store across alone is unobservable here (the one helper serves both axes). Across, the
    remainder past half and the clamp are the classes below."""
    taken = set().union(*(snap_arms(da.arrival(SNAP_DISK, chain, nth)) for chain, count in ARRIVALS[SNAP_DISK]
                          for nth in range(count)))
    assert taken == {("y", "up"), ("y", "moved on"), ("x", "moved on")}


SNAP_CLASSES = {
    "x 150: across, the remainder 70 past half the grid — rounded up": (150, 53),
    "x 300: across, past the screen less a grid — clamped, and past its middle": (300, 53),
    "y 200: down, past the desktop less a grid — clamped": (80, 200),
    "x -30, y -40: two negative words — the divide's remainder signed": (0xFFE2, 0xFFD8),
    "x 40: across, the remainder EXACTLY half the grid — not rounded up (`bge`)": (40, 53),
    "y 105: down, the snapped 94 EXACTLY the desktop's middle — not moved on (`bge`)": (80, 105),
}


@pytest.mark.parametrize("which", SNAP_CLASSES, ids=[f"{which} {CLASS}" for which in SNAP_CLASSES])
def test_snap_disk_over_the_install_arrival_s_machine__an_argument_class(which):
    """A LABELLED ARGUMENT CLASS (the arms no chain's data takes, above): the Install dialog's arrival — its machine and
    its two answer pointers — with another point."""
    arrived = da.arrival(SNAP_DISK, INSTALL)
    x, y = SNAP_CLASSES[which]
    da.plain(da.with_arguments(arrived, x, y, *arrived.arguments[2:]))


# save_str: A NULL STRING ends the copy too (`move.l a4,d0 / bne`, tested after the byte it points at — address 0
# holds the ROM's first byte, not a NUL).
def test_save_str_of_a_null_string_writes_its_end_alone__an_argument_class():
    """A LABELLED ARGUMENT CLASS (every caller hands a text): the first Save Desktop arrival's cursor, the string 0."""
    arrived = da.arrival(SAVE_STR, SAVED)
    result = da.plain(da.with_arguments(arrived, arrived.arguments[0], 0))
    assert result.long_answer() == arrived.arguments[0] + 2


# app_parse: THE TYPE LETTERS THE INF HOLDS — M, T, F, D, G, P (the arrivals) — and the two it does not: the
# cartridge's C and a letter past the table. A LINE LAID in the group's band, the anode the arrival's own.
LINE_AT = da.GEMDOS.end + (-da.GEMDOS.end % aes.LONG_BYTES)
LINES = {"C: the cartridge's type and flags": b"C 00 00 03 FF   CART@ @ \r\n",
         "X: a letter past the table's — neither stored": b"X 00 00 03 FF   CART@ @ \r\n",
         "a letter field with a letter in it": b"G 03 FF Q *.APP@ @ \r\n",
         "a letter of $c1 — a signed byte, its word $ffc1": b"G 03 FF \xc1 *.APP@ @ \r\n"}
assert LINE_AT + max(len(line) for line in LINES.values()) <= da.BAND_AT + da.BAND_BYTES


def test_app_parse_s_arrivals_read_six_of_the_eight_letters():
    """The INF's lines at the arrivals: drives, the trash, and the five program / folder lines."""
    letters = {chr(arrived.boot.ram[arrived.arguments[0]]) for arrived in da.arrivals(APP_PARSE, SHOWN, 9)}
    assert letters == {"M", "T", "F", "D", "G", "P"}


@pytest.mark.parametrize("which", LINES, ids=[f"{which} — THE LINE LAID in the group's band {CLASS}" for which in LINES])
def test_app_parse_of_a_line_laid__an_argument_class(which):
    """A LABELLED ARGUMENT CLASS (the arms no INF of the chains holds): the boot's arrival — its anode — the cursor at a
    line laid in the band."""
    arrived = da.arrival(APP_PARSE, BOOT)
    da.plain(da.with_arguments(arrived, LINE_AT, arrived.arguments[1]), {LINE_AT: LINES[which]}, **POINTERS_IT_FOLLOWS)


def test_app_tran_of_another_bitblk__an_argument_class():
    """A LABELLED ARGUMENT CLASS (its one caller hands 0): BITBLK 1 of the desk's resource, over the boot's arrival."""
    arrived = da.arrival(APP_TRAN, BOOT)
    row = da.row_of(da.with_arguments(arrived, 1), label="app_tran — BITBLK 1, over the boot's arrival " + CLASS)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert ran.answer & aes.WORD_MASK == the_rom_s.d0 & aes.WORD_MASK


# app_getfh: OPENED (no chain reads the INF from disk: the boot's is the ROM's own copy) and GEMDOS REFUSING the create.
FOPEN_HANDLE, EACCDN, EFILNF = 6, -36, -33
GETFH_CLASSES = {"opened — the script Fopen's handle 6": (1, (FOPEN_HANDLE,)),
                 "created, GEMDOS refusing (EACCDN) — the handle 0": (0, (EACCDN,)),
                 "opened, GEMDOS refusing (EFILNF) — the handle 0": (0x0100, (EFILNF,)),
                 "created, its third argument 7 — read and never used: Fcreate's attributes 0": (0, (FOPEN_HANDLE,))}
UNUSED_SEVEN = 7


@pytest.mark.parametrize("which", GETFH_CLASSES, ids=[f"{which} — THE SCRIPT LAID {CLASS}" for which in GETFH_CLASSES])
def test_app_getfh_opened_or_refused__an_argument_class(which):
    """A LABELLED ARGUMENT CLASS over Save Desktop's arrival, the recording trap SCRIPTED WITH ANOTHER ANSWER than the
    ROM's run got: Fopen instead of Fcreate (`open` a word with no bit in its low byte is still TRUE: `tst.w`), and
    the glue's verdict making the handle 0."""
    arrived = da.arrival(APP_GETFH, SAVED)
    opened, answers = GETFH_CLASSES[which]
    unused = UNUSED_SEVEN if "never used" in which else arrived.arguments[2]
    result = da.scripted(da.with_arguments(arrived, opened, arrived.arguments[1], unused), answers)
    assert result.answer() == (FOPEN_HANDLE if answers == (FOPEN_HANDLE,) else 0)
    assert da.dos_calls(result.final)[0][0] == (addrs.GEMDOS_FOPEN_FN if opened else addrs.GEMDOS_FCREATE_FN)


DRIVE_C_IN_THE_MAP = 0x0007             # Dsetdrv's answer: drives A:, B: and C:


def test_app_path_save_goes_to_drive_c_where_the_map_has_it__an_argument_class():
    """A LABELLED ARGUMENT CLASS (the chains' machine has no drive C:): Save Desktop's arrival, the script's DRIVE MAP
    (isdrive's Dsetdrv, the fourth call) answering C: — set_defdrv's C: arm, and the sdrv after it of drive 2."""
    arrived = da.arrival(PATH_SAVE, SAVED)
    answers, _back = da.dos_answers_in_place(arrived, TRAPS[PATH_SAVE])
    result = da.scripted(arrived, (*answers[:3], DRIVE_C_IN_THE_MAP, *answers[4:]))
    drives = [frame[:aes.WORD_BYTES] for function, frame in da.dos_calls(result.final) if function == addrs.GEMDOS_DSETDRV_FN]
    assert drives[-1] == bytes((0, 2))


# ---- D0 AT RETURN: THE TWO THAT ANSWER NOTHING IN C ------------------------------------------------------------------------------
VOID = (SNAP_DISK, APP_REVIT)


def test_no_caller_in_the_rom_reads_what_snap_disk_or_app_revit_leave_in_d0():
    """BY READING EVERY CALL SITE (`aes_deskbind.answer_readers`, through callers that return it): the word the ROM's
    snap_disk (g_ydesk's, under a divide's leftover) and app_revit (0) leave is read by nothing — the counted divergence
    of THE TWELVE AND THREE ARRIVALS where the C answers nothing."""
    for routine in VOID:
        assert db.calls_of(da.entry_of(routine)), f"{routine}: nothing calls it"
        assert not db.answer_readers(da.entry_of(routine)), f"{routine}'s D0 is read"
    assert sum(count for routine in VOID for _chain, count in ARRIVALS[routine]) == 15


# ---- THE GROUP'S ROUTINES, LINKED AND UNBOUND (units A, K and J) -----------------------------------------------
import sys                                                                          # noqa: E402
from pathlib import Path                                                            # noqa: E402

import aes_desksupp                                                                 # noqa: E402
import aes_desktop                                                                  # noqa: E402
import aes_event                                                                    # noqa: E402
import routines                                                                     # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "bench"
GROUP_G2 = (*da.UNIT_A, *aes_desktop.UNIT_K, *aes_desksupp.UNIT_J)
CORES = frozenset(routines.core_symbol(name) for name in GROUP_G2)


def _linef_table():
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


def test_no_function_of_a_blob_outside_the_desk_s_linked_routines_refers_to_one_of_the_group_s(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every core of the group
    linked; and no function outside the unbound desk (the held cores and what only they reach — the group's own static
    helpers among them, by their callers, not their names) refers to ANY held core."""
    assert not db.bound_referrers(blob, GROUP_G2)


def test_the_table_s_entries_for_the_group_stay_the_rom_s_and_no_registry_names_one():
    """...the generator's verdict for each is THE ROM'S (`linef_table.LINKED_AND_NOT_FLIPPED`), and no registered row
    is one of them."""
    linef_table = _linef_table()
    ours = {getattr(addrs, name): name for name in GROUP_G2}
    verdicts = {ours[entry.target]: entry.verdict for entry in linef_table.entries() if entry.target in ours}
    assert verdicts == {name: linef_table.THE_ROM_S for name in GROUP_G2}
    assert set(GROUP_G2) <= set(linef_table.LINKED_AND_NOT_FLIPPED)
    registered = [name for name in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS)
                  if name.split(",")[0] in CORES]
    assert not registered


STALE_BYTES = bytes((0xA5,)) * 0x20             # the string buffer under g_pbuff laid stale (it is zeros at every arrival)


def test_scan_str_ends_its_text_with_a_nul_over_a_stale_buffer__an_argument_class():
    """A LABELLED STAGING — THE STRING BUFFER LAID STALE under g_pbuff (at every arrival it holds zeros, so the NUL the
    routine writes is no byte the arrivals can see): the boot's arrival, the text's NUL written over a stale byte."""
    arrived = da.arrival(SCAN_STR, BOOT)
    kept = case.long_in(arrived.boot.ram, (case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & da.BUS)
                        + da.CONSTANTS["DESK_STRING_CURSOR"]) & da.BUS
    da.plain(arrived, {kept: STALE_BYTES}, **POINTERS_IT_FOLLOWS)


def test_app_parse_s_folder_line_stores_its_type_alone__an_argument_class():
    """A LABELLED ARGUMENT CLASS (every arrival's ANODE is a fresh one, its flags 0): the INF's folder line ('D', the
    fifth arrival) parsed into AN ANODE IN USE whose flags are not 0 — the list's first such (a drive's): the folder's arm stores its
    type and leaves the flags as they were."""
    arrived = da.arrival(APP_PARSE, SHOWN, 4)
    assert chr(arrived.boot.ram[arrived.arguments[0]]) == "D"
    ram = arrived.boot.ram
    node = case.long_in(ram, (case.long_in(ram, aes.AES_DESK_GLOBALS) & da.BUS) + da.CONSTANTS["DESK_ANODES_IN_USE"]) & da.BUS
    while not case.word_in(ram, node + da.CONSTANTS["ANODE_FLAGS"]):
        node = case.long_in(ram, node) & da.BUS
        assert node, "no ANODE in use has flags"
    da.plain(da.with_arguments(arrived, arrived.arguments[0], node), **POINTERS_IT_FOLLOWS)


KEPT_DRIVE_B = 1


def test_app_path_restore_makes_the_kept_drive_current__an_argument_class():
    """A LABELLED STAGING — THE KEPT DRIVE LAID B: (every arrival's is A:, 0, which tells no word read from anything
    else): Save Desktop's arrival, the drive app_path_save kept laid 1 — Dsetdrv handed it."""
    arrived = da.arrival(PATH_RESTORE, SAVED)
    answers, _back = da.dos_answers_in_place(arrived, TRAPS[PATH_RESTORE])
    result = da.scripted(arrived, answers, {da.CONSTANTS["AES_DESK_KEPT_DRIVE"]: bytes((0, KEPT_DRIVE_B))})
    assert da.dos_calls(result.final)[0][1][:aes.WORD_BYTES] == bytes((0, KEPT_DRIVE_B))
