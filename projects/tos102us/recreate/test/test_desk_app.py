"""UNIT A, THE DESK'S APPLICATION LIST (`src/desk/deskapp.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE
ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2, FLIPPED: the Line-F table's entry for each is its thunk, and every
case at an arrival is a Tier 3 row (`ROWS`, below; the group's flip pins are here too — units K and J).

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

WHAT IS NOT HELD: the argument classes' prices (Tier 1's alone).
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


# ---- THE GROUP'S ROUTINES (units A, K and J) ----------------------------------------------------------------------
import sys                                                                          # noqa: E402
from pathlib import Path                                                            # noqa: E402

import aes_desksupp                                                                 # noqa: E402
import aes_desktop                                                                  # noqa: E402
import aes_deskwin                                                                  # noqa: E402
import aes_event                                                                    # noqa: E402
import routines                                                                     # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "bench"
GROUP_G2 = (*da.UNIT_A, *aes_desktop.UNIT_K, *aes_desksupp.UNIT_J)
CORES = frozenset(routines.core_symbol(name) for name in GROUP_G2)


def _linef_table():
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


# ---- FLIPPED (band 6 slice F2, group G2): the fifteen — i_find since slice F2b, men_update since F2c (`aes_desktop.HELD_AT_F2`) --
HELD_G2 = aes_desktop.HELD_AT_F2
FLIPPED_G2 = tuple(name for name in GROUP_G2 if name not in HELD_G2)


def test_each_flipped_routine_s_thunk_calls_its_core_and_nothing_outside_the_unbound_desk_refers_to_a_held_core(blob):
    """THE FLIP: every flipped routine's core CALLED BY ITS OWN THUNK of the table — and the desk's one unbound pin
    (`aes_deskbind.bound_referrers`) holds for the cores still held, the group's two among them (men_update would be a
    bound referrer of i_find: measured, so it is held with it)."""
    assert not aes_deskwin.thunks_not_calling_their_core(blob, FLIPPED_G2)
    assert not db.bound_referrers(blob, HELD_G2)


def test_the_table_s_entries_are_the_flipped_routines_thunks_and_the_held_ones_the_rom_s():
    """...the generator's verdict for each of the fifteen is OURS, THROUGH ITS THUNK; the two held THE ROM'S, held by
    `LINKED_AND_NOT_FLIPPED` as `HELD_AT_F2` says — and no registered row is a held one's."""
    assert aes_deskwin.table_verdicts(GROUP_G2) == aes_deskwin.flipped_verdicts(GROUP_G2, HELD_G2)
    assert set(GROUP_G2) & set(_linef_table().LINKED_AND_NOT_FLIPPED) == set(HELD_G2)
    held = frozenset(routines.core_symbol(name) for name in HELD_G2)
    assert not [name for name in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS)
                if name.split(",")[0] in held]


# ---- band 6 slice F2: THE UNIT'S ROWS — every case at an arrival registered (`aes_deskapp.register_plain` /
# `register_switching`, R6's kind: the arrival's machine taken over at the arrival): a plain row, or for the three that
# yield a row that switches with NO DOOR (MEASURED, the table's second count: none makes a call of the event layer's
# door). app_getfh, app_path_save and app_path_restore traps answered by band 5's recording trap, app_rdicon's two
# Mallocs too (`aes_deskwin.ROW_SCRIPTED`, in the row's name). The classes stay Tier 1's.
#   * THE X FLAG (`aes_switching.THE_X_FLAG_ALONE`; MEASURED, each row's blob differential at `$8995`, `$00` ours / `$10`
#     the ROM's): app_tran's and app_rdicon's (the rsrc_gaddr binding's yield after the C's own arithmetic, ini_tree's kind).
#   * AES_XBIOS_RETURN NAMED BY NATURE on app_blddesk's (`XBIOS_DOOR_PARKED`; N16, R9 declared — the user's): its C reaches
#     trp14's `.S` through the shipped blob's glue, whose `jsr` parks THE GLUE'S return there where the ROM's door parks
#     its caller's; no ROM instruction but trp14's own two reads it (`test_aes_lineftable.py`,
#     `test_the_xbios_door_s_parked_return_is_named_by_trp14_alone`). Its three low bytes: the high byte is 0 on both
#     shores, an address under 16 MB, which the ROM's run never changes — a name over it is refused
#     (`aes_switching._its_own_by_nature`).
X_FLAG_DIFFERS = frozenset((APP_TRAN, APP_RDICON))
XBIOS_DOOR_PARKED = ((aes.AES_XBIOS_RETURN + 1, aes.AES_XBIOS_RETURN + aes.LONG_BYTES,
                      "AES_XBIOS_RETURN: the shipped glue parks its own return, the ROM's door its caller's — read by trp14 alone"),)


def _registered(routine, chain, nth):
    arrived = da.arrival(routine, chain, nth)
    if routine == APP_TRAN:
        return da.register_switching(arrived, door_user=False, x_flag_differs=True)
    if routine == APP_RDICON:
        answers, _back = da.dos_answers_in_place(arrived, RDICON_MALLOCS)
        return da.register_switching(arrived, door_user=False, x_flag_differs=True, answers=answers)
    if routine == APP_BLDDESK:
        return da.register_switching(arrived, door_user=False, layers=(da.getrez_layer(arrived),), said=da.GETREZ_STAGED,
                                     also_dropped=XBIOS_DOOR_PARKED)
    answers = da.dos_answers_in_place(arrived, TRAPS[routine])[0] if routine in TRAPS else None
    return da.register_plain(arrived, answers)


ROWS = {_id(*each): _registered(*each) for each in AT_ARRIVALS}
NO_DOOR_PREMISES = {
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, 'C' typed, Install pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), 1, ()),
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, Remove pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    "aes_app_blddesk, arrival 0 of file: shown, a key at its end; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), 1, ()),
    "aes_app_blddesk, arrival 0 of the boot of the DESKTOP.INF machine; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), 1, ()),
    "aes_app_rdicon, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    "aes_app_rdicon, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    "aes_app_tran, arrival 0 of file: shown, a key at its end":
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
    "aes_app_tran, arrival 0 of the boot of the DESKTOP.INF machine":
        ((), 0, 0xae5e, (0xae5e,), 0, ()),
}
NO_DOOR_PRICED = {
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, 'C' typed, Install pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((28430, 42478), None, None, (0, 0, 0)),
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, Remove pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((15162, 22616), None, None, (0, 0, 0)),
    "aes_app_blddesk, arrival 0 of file: shown, a key at its end; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((21548, 32022), None, None, (0, 0, 0)),
    "aes_app_blddesk, arrival 0 of the boot of the DESKTOP.INF machine; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        ((21548, 32022), None, None, (0, 0, 0)),
    "aes_app_rdicon, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((84042, 104984), None, None, (0, 0, 0)),
    "aes_app_rdicon, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((84042, 104984), None, None, (0, 0, 0)),
    "aes_app_tran, arrival 0 of file: shown, a key at its end":
        ((6030, 9986), None, None, (0, 0, 0)),
    "aes_app_tran, arrival 0 of the boot of the DESKTOP.INF machine":
        ((6030, 9986), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, 'C' typed, Install pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        {"bench": (69550, 60766), "bench_shipped": (69550, 57990)},
    "aes_app_blddesk, arrival 0 of A: Options > Install Disk Drive, Remove pressed; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        {"bench": (36164, 31414), "bench_shipped": (36164, 30094)},
    "aes_app_blddesk, arrival 0 of file: shown, a key at its end; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        {"bench": (52332, 45842), "bench_shipped": (52332, 43794)},
    "aes_app_blddesk, arrival 0 of the boot of the DESKTOP.INF machine; THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode":
        {"bench": (52332, 45842), "bench_shipped": (52332, 43794)},
    "aes_app_rdicon, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (168998, 207878), "bench_shipped": (168998, 154488)},
    "aes_app_rdicon, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (168998, 207878), "bench_shipped": (168998, 154488)},
    "aes_app_tran, arrival 0 of file: shown, a key at its end":
        {"bench": (21900, 18484), "bench_shipped": (21900, 18632)},
    "aes_app_tran, arrival 0 of the boot of the DESKTOP.INF machine":
        {"bench": (21900, 18484), "bench_shipped": (21900, 18632)},
}


def test_every_case_at_an_arrival_is_a_row_and_its_pins_are_the_switching_ones():
    """EVERY ROUTINE OF THE UNIT HAS A ROW AT EACH OF ITS ARRIVALS — a plain row but the three that yield, whose rows switch
    with no door, pinned here; the X flag declared on exactly app_tran's and app_rdicon's."""
    import aes_switching
    switching = [row for row in ROWS.values() if hasattr(row, "door")]
    assert len(ROWS) == len(AT_ARRIVALS) == 73 and {row.name for row in switching} == set(SWITCHES) and len(switching) == 8
    assert all(row.door is None for row in switching)
    assert {row.name for row in switching if row.x_flag_differs} == X_FLAG_DIFFERS
    names = {aes_switching.row_name(row) for row in switching}
    assert names == set(NO_DOOR_PREMISES) == set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_that_switches_has_its_premise_on_the_rom_s_run(name):
    da.vet_the_premise(name, NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_that_switches_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    da.vet_on_a_blob(blob, name, NO_DOOR_PREMISES, NO_DOOR_PRICED, NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_that_switches_is_priced_as_pinned_and_under_the_bar(name):
    da.vet_the_price(name, NO_DOOR_PRICED)


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


# ==== BAND 6 WAVE 2, GROUP G4: app_start ($fdb5fc), DESKTOP.INF READ AND PARSED ====================================
# app_start TRAPS AND SWITCHES: each case is a row over the arrival's megabyte with THE UNIT'S recording trap
# (`aes_deskapp.unit_scripted_row`) SCRIPTED WITH THE ANSWERS THE ROM'S OWN RUN IN PLACE GOT — isdrive's Dgetdrv and
# Dsetdrv at every drive line, app_rdicon's two Mallocs. Every arrival parses THE SHELL'S BUFFER (deskmain's restart
# re-reads what app_save put there; the boot reads what the AES read at its start): the file-read and ROM arms of the
# read, and the arms no INF of the chains holds, are labelled classes — the buffer, or the script, laid.
import aes_boot                                                                     # noqa: E402
import gemdos_process                                                               # noqa: E402
import struct                                                                       # noqa: E402
import layouts                                                                      # noqa: E402

APP_START = "AES_ROM_APP_START"
LONG_SHOWN = "files: the long file shown, a blank at each page's end and at its end"
START_ARRIVALS = (BOOT, da.BOOT_AS_TEXT, SHOWN, LONG_SHOWN)
SHELL_INF = aes.AES_SHELL_GEM_BUFFER
INF_BYTES = aes.header_constants("geminit.h")["INF_BUFFER_BYTES"]
DRIVE_LINES = (b"#M", b"#T")
MAP_CALLS = 2                           # isdrive: Dgetdrv, then Dsetdrv of its drive (the map)
MAP_A_B, MAP_A_B_C, MAP_EMPTY = 0x0003, 0x0007, 0
EFILNF_ANSWER = aes.signed(addrs.parse(aes.INCLUDE / "gemdos" / "process.h")["GEMDOS_EFILNF"], bits=32)
INF_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE     # the first file handle GEMDOS gives: DESKTOP.INF's
STALE_BYTE = 0xA5                       # a byte as no store of the run's leaves it
GEMDOS_ERROR = -1                       # GEMDOS's ERROR: a code above -32, which d_errmsg shows no alert for


def shell_inf(ram):
    """THE SHELL'S BUFFER in `ram`, to its NUL: the INF shel_get hands app_start."""
    return bytes(ram[SHELL_INF:SHELL_INF + INF_BYTES]).split(b"\0")[0]


def start_traps(inf):
    """The GEMDOS calls app_start makes over a shell's buffer holding `inf`, an INF: the map at each drive line, and
    app_rdicon's two Mallocs."""
    return MAP_CALLS * sum(line.startswith(DRIVE_LINES) for line in inf.split(b"\r\n")) + RDICON_MALLOCS


def start_case(arrived, answers, *layers):
    row = da.unit_scripted_row(arrived, answers, layers)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert not the_rom_s.idles and ran.answer == the_rom_s.d0 & aes.WORD_MASK == da.CONSTANTS["APP_START_DONE"]
    return ran


@pytest.mark.parametrize("chain", START_ARRIVALS, ids=lambda chain: f"app_start — arrival 0 of {chain} — {da.SCRIPTED}")
def test_app_start_at_its_arrival_is_the_rom_s_through_its_traps_and_yields(chain):
    """THE CASE: the C through the host's scheduler held to the ROM's scheduled run (the pool, every ANODE, the
    window entries, the #E fields, the grid, both outlines, the ledger of every call) — and its 1 the run in place's."""
    arrived = da.arrival(APP_START, chain)
    answers, back = da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))
    start_case(arrived, answers)
    assert back.registers["d0"] & aes.WORD_MASK == da.CONSTANTS["APP_START_DONE"]


def test_app_start_s_arrivals_take_the_arms_their_inf_reaches():
    """WHAT THE ARRIVALS' INFs HOLD (read off the shell's buffer at each): the #E view bit set (the text boot) and
    clear; #W lines with a path (the shows: deskmain's app_save(0) wrote A:'s window) and without; a width past the
    columns (halved) and within them; a drive C: line dropped (no C: in the map) and a cartridge line (no cartridge);
    the AES's own lower-case lines, past the switch's table."""
    infs = {chain: shell_inf(da.arrival(APP_START, chain).boot.ram) for chain in START_ARRIVALS}
    every = b"".join(infs.values())
    environment = {line[3:5] for inf in infs.values() for line in inf.split(b"\r\n") if line.startswith(b"#E")}
    assert {int(field, 16) & da.CONSTANTS["INF_E_VIEW_BIT"] != 0 for field in environment} == {True, False}
    assert b"A:\\*.*@" in every and b"#W 00 00 04 03 43 10 09 @" in every
    widths = {int(line[15:17], 16) for line in every.split(b"\r\n") if line.startswith(b"#W")}
    columns = case.word_in(da.arrival(APP_START, BOOT).boot.ram, aes.AES_GL_NCOLS)
    assert any(width > columns for width in widths) and any(width <= columns for width in widths)
    assert b"#M 00 02 00 FF C HARD DISK" in every and b"#C 01 06 00 FF c CARTRIDGE" in every and b"#a000000" in every


def _shell_laid(edit):
    """LAID: the shell's buffer at the arrival, `edit(text) -> text` — machine state, outside the AES's window."""
    return lambda arrived: {SHELL_INF: edit(shell_inf(arrived.boot.ram)) + b"\0"}


NOT_AN_INF = _shell_laid(lambda inf: b" " + inf[1:])          # its first byte a blank: no line begins the buffer
# THE HOST'S GEMDOS DISPATCHER RESOLVES Fread's and Fwrite's HANDLE before it reaches the scripted handler (the ROM's
# staged trap answers at the vector, ahead of it): a handle the machine never opened resolves to nothing there and the
# call is EIHNDL on the host alone. So a script that opens one also LAYS its record in GEMDOS's handle table — named,
# owned by none: the dispatcher reads its value's sign and nothing else (`src/gemdos/dispatch.c`, resolve_handle).
HANDLE_NAMED = 1                        # a file system's pointer stand-in: positive, a file's (not a device's)


def _with_the_handle_open(layer):
    return lambda arrived: {**layer(arrived), **gemdos_process.descriptor_poke(INF_HANDLE, HANDLE_NAMED, 0)}


def _inf_read_answers(arrived, *opened):
    """The script for a buffer that is no INF: the map, `opened` (Fopen and what follows it), then the in-place run's
    two Mallocs."""
    answers, _back = da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))
    return (0, MAP_A_B, *opened, *answers[-RDICON_MALLOCS:])


def _read_up_to_the_drives(arrived):
    """Fread's answer: the shell's text up to its first drive line (the buffer is not written by the scripted read: what
    the parse then reads is the laid buffer, NUL-ended there)."""
    inf = shell_inf(arrived.boot.ram)
    return _inf_read_answers(arrived, INF_HANDLE, inf.index(b"#M"), 0)


def _rom_s_inf_answers(arrived, the_map, *opened):
    """...and for the ROM's own INF parsed (rom_ram): the map at each of its four drive lines."""
    answers, _back = da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))
    rom_s_drive_lines = sum(line.startswith(DRIVE_LINES) for line in aes_boot.default_inf().split(b"\r\n"))
    return (0, the_map, *opened, *(0, the_map) * rom_s_drive_lines, *answers[-RDICON_MALLOCS:])


def _every_map(the_map):
    """The in-place run's script, every Dsetdrv (each drive line's map) answering `the_map`."""
    def answers(arrived):
        script, _back = da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))
        return tuple(the_map if nth % MAP_CALLS and nth < len(script) - RDICON_MALLOCS else answer
                     for nth, answer in enumerate(script))
    return answers


def _replaced(old, new):
    def edit(inf):
        assert inf.count(old) == 1 and len(old) == len(new), (old, new)
        return inf.replace(old, new)
    return edit


START_CLASSES = {
    "THE SHELL'S BUFFER LAID not an INF; the map A:+B:, DESKTOP.INF opened, read (to its first drive line) and closed — SCRIPTED,"
    " GEMDOS's handle 6 LAID open": (lambda arrived: _read_up_to_the_drives(arrived), _with_the_handle_open(NOT_AN_INF)),
    # (the fix pass's) the read FAILING: the INF's NUL stored at the SIGNED answer — a byte BEFORE g_afile (`$fdb6d6`'s
    # sign-extending `movea.w`) — that byte LAID stale, so the NUL is seen; the parse then reads the text shel_get left
    # in g_afile — the buffer, laid NUL-ended before its first drive line (the recorder's script holds no more maps)
    "THE SHELL'S BUFFER LAID not an INF and ended before its drive lines, the byte before g_afile LAID stale; the map "
    "A:+B:, DESKTOP.INF opened, its read failing (ERROR, -1) and closed — SCRIPTED, GEMDOS's handle 6 LAID open": (
        lambda arrived: _inf_read_answers(arrived, INF_HANDLE, GEMDOS_ERROR, 0),
        lambda arrived: {**_with_the_handle_open(_shell_laid(lambda inf: b" " + inf[1:inf.index(DRIVE_LINES[0])]))(arrived),
                         desk_of(arrived) + da.CONSTANTS["DESK_G_AFILE"] - 1: bytes((STALE_BYTE,))}),
    "THE SHELL'S BUFFER LAID not an INF; the map A:+B:, DESKTOP.INF refused (EFILNF): the ROM's own INF — SCRIPTED":
        (lambda arrived: _rom_s_inf_answers(arrived, MAP_A_B, EFILNF_ANSWER), NOT_AN_INF),
    "THE SHELL'S BUFFER LAID not an INF; the map EMPTY: the ROM's own INF, every drive line dropped — SCRIPTED":
        (lambda arrived: _rom_s_inf_answers(arrived, MAP_EMPTY), NOT_AN_INF),
    "drive C: in the map at every drive line: its line kept — SCRIPTED": (_every_map(MAP_A_B_C), None),
    "the map EMPTY at every drive line: each dropped — SCRIPTED": (_every_map(MAP_EMPTY), None),
    "a #W line LAID with its column AT the columns (halved) and its width AT them (not), two rows tall, scrolled a column and two rows": (
        None, _shell_laid(_replaced(b"#W 00 00 04 03 43 10 09 @", b"#W 01 02 28 03 28 02 09 @"))),
    "the first window entry's path LAID stale (its #W line's path is empty)": (
        None, lambda arrived: {desk_of(arrived) + da.CONSTANTS["DESK_G_WINDOW_SAVES"] + DESKTOP_CONSTANTS["SAVE_PATH"]: STALE_OUTLINE}),
    "a monochrome screen LAID (gl_height 400, gl_hchar 16): the tall screen's space, a row's own height": (
        None, lambda _arrived: {aes.AES_GL_HEIGHT: struct.pack(">H", TALL_HEIGHT), aes.AES_GL_HCHAR: struct.pack(">H", TALL_CELL)}),
    "the ANODE pool's links LAID stale: every one set again, the last cleared": (
        None, lambda arrived: {desk_of(arrived) + da.CONSTANTS["DESK_G_ALIST"] + nth * da.CONSTANTS["ANODE_BYTES"]: b"\xa5" * 4
                               for nth in range(da.CONSTANTS["DESK_ANODES"])}),
    "the #E line LAID: the sort 3, the second preference alone, the third 15": (
        None, _shell_laid(_replaced(b"#E 1B 10 ", b"#E 6B F0 "))),
    "a line LAID of the letter '@' (below the switch's table) and one of 'X' (past it)": (
        None, _shell_laid(_replaced(b"#a000000\r\n#b000000", b"#@000000\r\n#X000000"))),
    "both drag outlines LAID stale (every arrival's are zeros): each bfill clears HALF its outline, the rest kept": (
        None, lambda arrived: {desk_of(arrived) + da.CONSTANTS[outline]: STALE_OUTLINE for outline in ("DESK_G_XYICON", "DESK_G_XYTEXT")}),
}
TALL_HEIGHT, TALL_CELL = 400, 16
# Unit K's header (`include/desk/desktop.h`): a g_cnxsave entry's layout, read as unit A's constants are.
DESKTOP_CONSTANTS = layouts.parse_constants((da.HEADER.parent / "desktop.h",), known=da.CONSTANTS)
STALE_OUTLINE = bytes((0xA5,)) * (2 * 2 * da.CONSTANTS["ICON_OUTLINE_POINTS"])   # an outline's point pairs, every byte stale


def desk_of(arrived):
    return case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & da.BUS


@pytest.mark.parametrize("which", START_CLASSES, ids=[f"app_start — {which}, over the boot's arrival {CLASS}" for which in START_CLASSES])
def test_app_start_over_the_boot_s_arrival__an_argument_class(which):
    """A LABELLED CLASS over the boot's arrival (the arms no arrival's INF or GEMDOS reaches): the row with the script
    and the shell's buffer said in its id."""
    arrived = da.arrival(APP_START, BOOT)
    answers_of, laid = START_CLASSES[which]
    answers = answers_of(arrived) if answers_of else da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))[0]
    start_case(arrived, answers, *((laid(arrived),) if laid else ()))


def test_app_start_s_answer_is_read_by_deskmain():
    """Its 1 (app_rdicon's 0 is its 0 — app_rdicon answers 1 at every return: that arm is DEAD in the ROM, unpinned by
    construction) is read by its one caller, deskmain."""
    assert db.answer_readers(da.entry_of(APP_START))


# ---- FLIPPED (band 6 slice F3, stage 1): app_start; app_save HELD, UNBOUND --------------------------------------------------
def test_app_start_is_flipped_and_app_save_held_unbound(blob):
    """THE FLIP PIN of app_start (`aes_deskarrive.flipped`) and THE UNBOUND PIN of app_save (`aes_deskarrive.unbound`: its
    entry the ROM's, no registry row, no function outside the unbound desk refers to a held core) — held to stage 2
    (`aes_deskapp.UNIT_A_WAVE_2_HELD_AT_F3`)."""
    import aes_deskarrive as dar
    dar.flipped(blob, da.UNIT_A_WAVE_2_FLIPPED)
    dar.unbound(blob, da.UNIT_A_WAVE_2_HELD_AT_F3)


# ---- band 6 slice F3: app_start's ROWS — every arrival registered, A ROW THAT SWITCHES (`aes_deskapp.register_switching`),
# its GEMDOS calls answered by band 5's recording trap with the answers the ROM's run in place got
# (`aes_deskwin.ROW_SCRIPTED`, in the row's name). The classes stay Tier 1's.
START_DOOR_USERS = frozenset()
START_X_FLAG_DIFFERS = frozenset(START_ARRIVALS)


def _start_row(chain):
    arrived = da.arrival(APP_START, chain)
    answers, _back = da.dos_answers_in_place(arrived, start_traps(shell_inf(arrived.boot.ram)))
    return da.register_switching(arrived, door_user=chain in START_DOOR_USERS, x_flag_differs=chain in START_X_FLAG_DIFFERS,
                                 answers=answers)


START_ROWS = {chain: _start_row(chain) for chain in START_ARRIVALS}
START_NO_DOOR_PREMISES = {
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine, as text; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    "aes_app_start, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    "aes_app_start, arrival 0 of files: the long file shown, a blank at each page's end and at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
}
START_NO_DOOR_PRICED = {
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((226644, 343706), None, None, (0, 0, 0)),
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine, as text; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((226644, 343698), None, None, (0, 0, 0)),
    "aes_app_start, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((221798, 338648), None, None, (0, 0, 0)),
    "aes_app_start, arrival 0 of files: the long file shown, a blank at each page's end and at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        ((221798, 338648), None, None, (0, 0, 0)),
}
START_NO_DOOR_WHOLE_RUN = {
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (416754, 413730), "bench_shipped": (416754, 308076)},
    "aes_app_start, arrival 0 of the boot of the DESKTOP.INF machine, as text; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (416746, 413730), "bench_shipped": (416746, 308076)},
    "aes_app_start, arrival 0 of file: shown, a key at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (411128, 408338), "bench_shipped": (411128, 302662)},
    "aes_app_start, arrival 0 of files: the long file shown, a blank at each page's end and at its end; GEMDOS SCRIPTED: band 5's recording trap answers the ROM's own run's answers":
        {"bench": (411128, 408338), "bench_shipped": (411128, 302662)},
}


def test_app_start_s_rows_are_its_arrivals_each_a_row_that_switches_with_no_door():
    """EVERY ARRIVAL A ROW THAT SWITCHES, WITH NO DOOR (MEASURED, the table's second count: no call of a rebound entry),
    the X flag declared on each (MEASURED, each row's blob differential at `$8995`: the switch after the C's own
    arithmetic), pinned here."""
    import aes_switching
    assert all(row.door is None and row.x_flag_differs for row in START_ROWS.values()) and len(START_ROWS) == 4
    names = {aes_switching.row_name(row) for row in START_ROWS.values()}
    assert names == set(START_NO_DOOR_PREMISES) == set(START_NO_DOOR_PRICED) == set(START_NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", START_NO_DOOR_PREMISES)
def test_app_start_s_row_has_its_premise_on_the_rom_s_run(name):
    da.vet_the_premise(name, START_NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", START_NO_DOOR_WHOLE_RUN)
def test_app_start_s_row_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    da.vet_on_a_blob(blob, name, START_NO_DOOR_PREMISES, START_NO_DOOR_PRICED, START_NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", START_NO_DOOR_PRICED)
def test_app_start_s_row_is_priced_as_pinned_and_under_the_bar(name):
    da.vet_the_price(name, START_NO_DOOR_PRICED)


# ==== BAND 6 WAVE 2, GROUP G4: app_save ($fdbb34), DESKTOP.INF WRITTEN =============================================
# app_save SWITCHES (shel_get's and shel_put's bindings) and, TO DISK, TRAPS: app_path_save's seven calls, Fcreate,
# Fwrite, Fclose, app_path_restore's two — a row with the unit's recording trap SCRIPTED WITH THE ROM'S RUN IN PLACE'S
# ANSWERS, GEMDOS's record of the created handle LAID OPEN AS THE ROM'S RUN LEFT IT (`aes_gemdosif.opened_record`, off the
# run in place: the host's dispatcher resolves Fwrite's handle — above).
# deskmain's own call (before a file is shown, before a launch) writes to the shell's buffer alone: no trap.
# UNPINNED AT ITS ARRIVALS, by name: the TOP WINDOW'S ARM (win_ontop, then G2's fun_rebld) — the three Save Desktop
# chains with a window open reach it, but past Fclose they make 13 to 16 more calls (pro_chdir's, and pn_active's
# Fsetdta / Fsfirst / Fsnext), which neither recording trap serves (`aes_deskapp.DOS_FRAME_BYTES`, 13 entries).
APP_SAVE = "AES_ROM_APP_SAVE"
LAUNCHED = "files: the program double-clicked — launched"
SAVE_TO_DISK_TRAPS = TRAPS[PATH_SAVE] + 3 + TRAPS[PATH_RESTORE]      # ...and Fcreate, Fwrite, Fclose between
SAVE_ARRIVALS = {SAVED: SAVE_TO_DISK_TRAPS, SHOWN: 0, LONG_SHOWN: 0, LAUNCHED: 0}


def save_case(arrived, answers, *layers, at_idle=None):
    row = da.unit_scripted_row(arrived, answers, layers, answered=False, at_idle=at_idle)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert bool(the_rom_s.idles) == bool(at_idle)
    return ran


@pytest.mark.parametrize("chain", SAVE_ARRIVALS, ids=lambda chain: f"app_save — arrival 0 of {chain} — {da.SCRIPTED}")
def test_app_save_at_its_arrival_is_the_rom_s_through_its_traps_and_yields(chain):
    """THE CASE: the C through the host's scheduler held to the ROM's scheduled run — the INF in g_afile and in the
    shell's buffer, its length, the list turned round and back, the ledger of every call."""
    arrived = da.arrival(APP_SAVE, chain)
    assert arrived.arguments == ((1,) if SAVE_ARRIVALS[chain] else (0,))
    opened = {}
    answers, back = da.dos_answers_in_place(arrived, SAVE_ARRIVALS[chain], opened)
    assert back is not None and bool(opened) == bool(SAVE_ARRIVALS[chain])
    save_case(arrived, answers, opened)




def _anode_of_no_letter(arrived):
    """LAID: the list's first node in use of a type past the cartridge's (no INF letter)."""
    node = case.long_in(arrived.boot.ram, desk_of(arrived) + da.CONSTANTS["DESK_ANODES_IN_USE"]) & da.BUS
    return {node + da.CONSTANTS["ANODE_TYPE"]: struct.pack(">H", da.CONSTANTS["AT_ISCART"] + 1)}


def _created_refused(arrived):
    answers, _back = da.dos_answers_in_place(arrived, SAVE_TO_DISK_TRAPS)
    path_save, restore = TRAPS[PATH_SAVE], TRAPS[PATH_RESTORE]
    return (*answers[:path_save], GEMDOS_ERROR, *answers[-restore:])


EACCDN_ANSWER = aes.signed(addrs.parse(aes.INCLUDE / "gemdos" / "fs.h")["GEMDOS_EACCDN"], bits=32)   # d_errmsg's alert (at or below -32)
SPOT_X, SPOT_Y_PAST_THE_TOP = 216, 98   # a desktop spot whose grid cells differ by the grid's width / height (and by the
                                        # icon's width: 170 gave 2 under either divisor) and the top
GEM_BIT_ALONE = 0x0001                  # one of a GEM program's two flag bits


def _created_refused_with_an_alert(arrived):
    answers, _back = da.dos_answers_in_place(arrived, SAVE_TO_DISK_TRAPS)
    return (*answers[:TRAPS[PATH_SAVE]], EACCDN_ANSWER, *answers[-TRAPS[PATH_RESTORE]:])


def _first_node(arrived, wanted):
    """The first ANODE in use whose type is `wanted`'s and whose flags hold AF_ISDESK as `on_the_desktop` says."""
    ram, desk = arrived.boot.ram, desk_of(arrived)
    node = case.long_in(ram, desk + da.CONSTANTS["DESK_ANODES_IN_USE"]) & da.BUS
    while not wanted(ram, node):
        node = case.long_in(ram, node) & da.BUS
        assert node, "no node in use is the one asked"
    return node


def _settings_laid(arrived):
    """LAID: the #E fields the chains never set — the text view, the sort by type —, a desktop icon's spot off the grid's
    cells, a file node with one GEM flag bit alone, the cell 16 rows tall, and g_afile's kept part stale."""
    desk = desk_of(arrived)
    flags, kind = da.CONSTANTS["ANODE_FLAGS"], da.CONSTANTS["ANODE_TYPE"]
    on_desk = _first_node(arrived, lambda ram, node: case.word_in(ram, node + flags) & da.CONSTANTS["ANODE_ON_THE_DESKTOP"])
    a_file = _first_node(arrived, lambda ram, node: case.word_in(ram, node + kind) == da.CONSTANTS["AT_ISFILE"])
    return {desk + da.CONSTANTS["DESK_CNX_VIEW"]: struct.pack(">H", 1),
            desk + da.CONSTANTS["DESK_CNX_SORT"]: struct.pack(">H", da.CONSTANTS["SORT_BY_TYPE"]),
            on_desk + da.CONSTANTS["ANODE_XSPOT"]: struct.pack(">hh", SPOT_X, SPOT_Y_PAST_THE_TOP),
            a_file + flags: struct.pack(">H", GEM_BIT_ALONE),
            aes.AES_GL_HCHAR: struct.pack(">H", TALL_CELL),
            desk + da.CONSTANTS["DESK_G_AFILE"]: STALE_OUTLINE * 4}


def _text_view_sort_0(arrived):
    desk = desk_of(arrived)
    return {desk + da.CONSTANTS["DESK_CNX_VIEW"]: struct.pack(">H", db.DESK_GLOBALS["V_TEXT"]),
            desk + da.CONSTANTS["DESK_CNX_SORT"]: struct.pack(">H", 0)}


SAVE_CLASSES = {
    "DESKTOP.INF's Fcreate refused (EACCDN): d_errmsg's alert, answered by Return — SCRIPTED": (
        SAVED, _created_refused_with_an_alert, (), {0: aes_event.key(aes_event.RETURN_KEY)}),
    "the view, the sort, a spot, a file's flags, the cell and the kept part LAID": (SHOWN, None, (_settings_laid,), None),
    "DESKTOP.INF's Fcreate refused (-1, no alert) — the path given back, nothing written — SCRIPTED": (SAVED, _created_refused, (), None),
    "a node in use LAID of a type past the cartridge's: its line written with no letter": (SHOWN, None, (_anode_of_no_letter,), None),
    # (the fix pass's) the text view's own Save Desktop ("text view: Options > Save Desktop, Return") reaches app_save
    # with the view TEXT and the sort 0 — and then the top window's arm, unpinned: so its #E fields LAID
    "the view TEXT and the sort 0 LAID (the text view's Save Desktop's own: its #E view bit from the view alone)": (
        SHOWN, None, (_text_view_sort_0,), None),
}


@pytest.mark.parametrize("which", SAVE_CLASSES, ids=[f"app_save — {which} {CLASS}" for which in SAVE_CLASSES])
def test_app_save__an_argument_class(which):
    """A LABELLED CLASS: the arms no arrival's run reaches."""
    chain, answers_of, layers, at_idle = SAVE_CLASSES[which]
    arrived = da.arrival(APP_SAVE, chain)
    answers = answers_of(arrived) if answers_of else ()
    save_case(arrived, answers, *(layer(arrived) for layer in layers), at_idle=at_idle)


def test_no_caller_reads_what_app_save_leaves_in_d0():
    """app_save answers nothing in C: the ROM's D0 there (shel_put's, the path's, d_errmsg's 1, fun_rebld's) is read by
    neither of its callers — the Options menu's Save Desktop and deskmain's own — a COUNTED divergence of its cases."""
    assert db.calls_of(da.entry_of(APP_SAVE)) and not db.answer_readers(da.entry_of(APP_SAVE))
    assert len(SAVE_ARRIVALS) + len(SAVE_CLASSES) == 9
