"""BAND 6 W3a, THE CYCLE — ITS PREP (`test/aes_desk_w3a.py`), held before any of its C exists: the eighteen named and
declared TARGET-ONLY, the generator holding each entry the ROM's (DECLARED_NOT_LINKED), the split's stages leaf-up with
the one back-edge declared through the table (and red by name once it outlives its stage), hndl_button's store into its
own argument slot, and THE TARGET-ONLY ROW KIND — its census, its refusals, its budget slot — exercised on crafted
registrations alone. SINCE STAGE 1 (`test_desk_w3a_stage1.py`): its nine written, linked and flipped, their rows the
kind's first — the census below counts them by name.
"""
import functools
import re
import sys
from collections import namedtuple
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs
from recreate_kit import rom_bench

import aes
import aes_desk
import aes_desk_w3a as w3a
import aes_event
import aes_switch as switch
import aes_switching
import case
import layouts
import opcodes as op
import rom_data
import routines
import transcription
import vdi

RECREATE = Path(__file__).resolve().parents[1]


def _the_generator():
    """`bench/linef_table.py`, imported inside the tests that ask (it imports every battery's registry)."""
    bench = str(RECREATE / "bench")
    sys.path.insert(0, bench)
    try:
        import linef_table
    finally:
        sys.path.remove(bench)
    return linef_table


@pytest.fixture(scope="module", params=switch.BLOBS.values(), ids=switch.BLOBS)
def blob(request):
    return rom_bench.RomBench(request.param)


# ---- THE EIGHTEEN -------------------------------------------------------------------------------------------------------------
FILES = {w3a.DESKTOP: 6, w3a.DESKSUPP: 3, w3a.DESKINF: 7, w3a.DESKINS: 2}
CYCLE_AND_HNDL_BUTTON = 18
CARTRIDGE_PAIR = (0xFED554, 0xFED5C2)   # the table's two entries of the cartridge's (the W3a cut's §1.4), still the ROM's


def _unflipped():
    """W3a's routines of the stages not yet flipped: the ROM's still."""
    return [name for name in w3a.W3A if w3a.STAGE_OF[name] > FLIPPED_THROUGH_STAGE]


FLIPPED_THROUGH_STAGE = w3a.FLIPPED_THROUGH_STAGE    # its one home: the cycle's module (stage 3: the cycle whole)


def test_the_eighteen_are_band_6_s_routines_each_named_once_by_its_file_and_the_unflipped_ones_still_the_rom_s():
    """W3a's eighteen, each in ONE file of the split, each a band-6 routine and a target of the ROM's table — and with
    deskmain (W3b) and the cartridge pair, those of the stages not yet flipped EVERY band-6 routine the shipped blob
    still leaves the ROM's."""
    assert {file: len(names) for file, names in w3a.SIGNATURES_BY_FILE.items()} == FILES
    assert len(w3a.W3A) == len(set(w3a.W3A)) == CYCLE_AND_HNDL_BUTTON and set(w3a.FILE_OF) == set(w3a.W3A)
    addresses = {getattr(addrs, name) for name in w3a.W3A}
    assert addresses <= set(aes_desk.routines()) and addresses <= set(aes._line_f_call_index())
    unflipped = {getattr(addrs, name) for name in _unflipped()}
    assert aes_desk.still_the_rom_s() == {*unflipped, addrs.AES_ROM_DESKMAIN, *CARTRIDGE_PAIR}
    assert addrs.AES_ROM_DESK_INF_FOLDER not in addresses, "`$fde9ce` keeps its name: `$fded16` is the folder dialog"


def test_each_is_declared_target_only_and_the_host_library_has_no_core_of_any():
    """RULING O1: each signature declared TARGET-ONLY (`vdi.TARGET_ONLY`) as the module says it; no host core of any."""
    assert set(w3a.W3A) <= vdi.TARGET_ONLY
    assert {name: (vdi.ALCYON[name].restype, vdi.frame_argtypes(name)) for name in w3a.W3A} == w3a.SIGNATURES
    assert all(vdi.takes_image(name) and not vdi.ALCYON[name].host_arguments for name in w3a.W3A)
    assert not [name for name in w3a.W3A if w3a.host_twin_of(name) is not None]


FRAME_BASE = 8                          # an Alcyon routine's first argument, past its return address and its `link`
AN_ARGUMENT_READ = re.compile(r"^(\w+) .*%fp@\((\d+)\)")
BYTES_OF_A_SIZE = {"b": 1, "w": 2, "l": 4}


def _argument_bytes_read(entry):
    """The last byte (exclusive, from 8(a6)) of the frame `entry`'s ROM body reads by a direct `d(a6)` operand, 8 for
    none — the body to the next routine the AES map's inventory lists."""
    end = min(start for start in aes_desk.inventoried() if start > entry)
    last = FRAME_BASE
    for _at, text in rom_data.instructions(entry, end):
        found = text and AN_ARGUMENT_READ.match(text)
        if found:
            mnemonic, offset = found.groups()
            size = 1 if mnemonic.startswith("btst") else BYTES_OF_A_SIZE[mnemonic[-1]]
            last = max(last, int(offset) + size)
    return last


def test_each_declared_frame_ends_where_its_rom_body_s_last_argument_read_ends():
    """THE FRAMES, READ OFF THE ROM: each routine's body reads its frame's last argument and nothing past it — the
    declared frame's bytes are exactly as many as the furthest `d(a6)` operand of its body reaches (none for a routine
    of no argument)."""
    frames = {name: FRAME_BASE + sum(vdi.ARG_BYTES[argtype] for argtype in vdi.frame_argtypes(name)) for name in w3a.W3A}
    assert {name: _argument_bytes_read(getattr(addrs, name)) for name in w3a.W3A} == frames


def test_a_target_only_declaration_of_a_core_the_host_library_has_is_refused_by_name():
    """...AND ITS RED: a core the host library has, declared target-only, is refused by its name, nothing declared."""
    has_a_host_core = "AES_ROM_HNDL_KBD"
    before = dict(vdi.ALCYON), set(vdi.TARGET_ONLY)
    with pytest.raises(AssertionError, match=re.escape(f"{has_a_host_core}: {vdi.A_HOST_TWIN_OF_A_TARGET_ONLY_CORE}")):
        vdi.declare_alcyon(has_a_host_core, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG), target_only=True)
    assert (dict(vdi.ALCYON), set(vdi.TARGET_ONLY)) == before


# ---- THE GENERATOR: each entry the ROM's, by declaration, until the C links ---------------------------------------------------
def test_the_generator_holds_the_unflipped_stages_declared_and_not_linked_and_leaves_their_entries_the_rom_s(blob):
    """DECLARED_NOT_LINKED is W3a's routines of the stages not yet flipped; NO CORE OF ONE IS LINKED in either blob (a
    core linked while listed reds by name: it moves to LINKED_AND_NOT_FLIPPED) — and every flipped stage's core IS;
    none is a native entry, in another held list or ENTERED_BY_OURS_ALONE; every entry of the table naming one is THE
    ROM'S."""
    generator = _the_generator()
    assert set(generator.DECLARED_NOT_LINKED) == set(_unflipped())
    linked = {symbol.name for symbol in transcription.symbol_table(blob.elf)}
    assert not [name for name in _unflipped() if routines.core_symbol(name) in linked], (
        "a core of DECLARED_NOT_LINKED is linked: move it to LINKED_AND_NOT_FLIPPED")
    assert all(routines.core_symbol(name) in linked for name in w3a.W3A if name not in _unflipped())
    held = set(generator.DECLARED_NOT_LINKED)
    assert not held & {*generator.LINKED_AND_NOT_FLIPPED, *generator.LINKED_HELD_NO_TABLE_ENTRY, *generator.ENTERED_BY_OURS_ALONE}
    addresses = {getattr(addrs, name) for name in held}
    assert not addresses & set(generator.native_entries())
    verdicts = {entry.verdict for entry in generator.entries() if entry.target in addresses}
    assert verdicts == ({generator.THE_ROM_S} if addresses else set())     # (none held since stage 3: the cycle whole)


def test_the_list_is_what_keeps_them_the_rom_s(monkeypatch):
    """...AND WITHOUT IT each would be thunked (the signature declared): the list is the one thing that holds them (and
    the flipped stages' are thunked already)."""
    generator = _the_generator()
    monkeypatch.setattr(generator, "DECLARED_NOT_LINKED", {})
    addresses = {getattr(addrs, name) for name in w3a.W3A}
    thunked = {entry.routine for entry in generator.entries() if entry.target in addresses}
    assert thunked == set(w3a.W3A)


# ---- THE SPLIT, S2, AND ITS ONE BACK-EDGE ----------------------------------------------------------------------------------------
INVENTORY_FIELDS = "|"


def w3a_callees():
    """`{a W3a routine: its W3a callees}` off the AES map's inventory (its callees field: Line-F words and `jsr`s)."""
    ours = {getattr(addrs, name): name for name in w3a.W3A}
    callees = {}
    for line in aes_desk.INVENTORY.read_text().splitlines():
        try:
            start = int(line[:aes_desk.INVENTORY_ADDRESS_DIGITS], 16)
        except ValueError:
            continue
        if start in ours:
            called = line.rsplit(INVENTORY_FIELDS, 2)[1].split()
            callees[ours[start]] = {ours[int(each, 16)] for each in called if int(each, 16) in ours}
    return callees


def test_the_stages_are_the_eighteen_leaf_up_each_a_dag_but_the_one_back_edge_declared():
    """S2: the three stages partition the eighteen; every W3a callee of a routine flips at its stage or before, BUT the
    back-edges the split declared (inf_show -> hndl_msg, the cycle's one); a declared one is a back-edge indeed,
    retired at its callee's stage — and SINCE STAGE 3 EVERY ONE IS RETIRED: no call is made through the table."""
    staged = [name for names in w3a.STAGES.values() for name in names]
    assert sorted(staged) == sorted(w3a.W3A)
    callees = w3a_callees()
    assert set(callees) == set(w3a.W3A)
    upward = {(caller, callee) for caller, called in callees.items() for callee in called
              if w3a.STAGE_OF[callee] > w3a.STAGE_OF[caller]}
    assert upward == set(w3a.BACK_EDGES)
    assert all(call.retired_at == w3a.STAGE_OF[callee] for (_caller, callee), call in w3a.BACK_EDGES.items())
    assert w3a.FLIPPED_THROUGH_STAGE == max(w3a.STAGES) and w3a.CALLS_THROUGH_THE_TABLE == {}


DESKINF = layouts.parse_constants((aes.INCLUDE / "desk" / "deskinf.h",), known={**vdi.CONSTANTS, **aes.CONSTANTS})


RETIRED_CALL_WORD = "INF_SHOW_HNDL_MSG_CALL_WORD"     # the word inf_show's C was handed until stage 3 (`desk/deskinf.h`)


def test_the_back_edge_is_the_rom_s_own_call_word_at_its_site_and_the_header_hands_it_no_more():
    """THE DECLARED CALL WAS THE ROM'S: its word is the call word of the callee's entry of the ROM's table, it lies at
    the declared site, an instruction of the caller's body (before the next routine the inventory lists) — and since
    stage 3 retired it, the caller's C is handed that word no more (`desk/deskinf.h`: the C calls the C)."""
    starts = aes_desk.inventoried()
    for (caller, callee), call in w3a.BACK_EDGES.items():
        assert call.site in aes.line_f_call_sites(callee).get(call.word, ())
        entry = getattr(addrs, caller)
        assert entry < call.site < min(start for start in starts if start > entry)
    assert RETIRED_CALL_WORD not in DESKINF


def test_a_call_through_the_table_reds_by_name_once_its_callee_is_flipped():
    """THE RETIREMENT, standing: no call still made through the table has its callee flipped (`aes_desk.flipped`, the
    blob's own table) — and the back-edge the split declared, were it still made so, would be named: hndl_msg IS
    flipped (stage 3), which is why it is retired."""
    assert not w3a.calls_outliving_their_stage(aes_desk.flipped()), w3a.OUTLIVED_ITS_STAGE
    assert addrs.AES_ROM_HNDL_MSG in aes_desk.flipped()
    assert w3a.calls_outliving_their_stage(aes_desk.flipped(), w3a.BACK_EDGES) == [f"{w3a.INF_SHOW} -> {w3a.HNDL_MSG}"]


# ---- hndl_button's store into its own argument slot (ruling O5: do_fopen's, fat_mark's precedent) -------------------------------
HNDL_BUTTON_CALL_SITE = 0xFE2A1E        # deskmain's one Line-F call of hndl_button (read: `$fe272e`'s listing)
SLOT_HANDED_AT = 0xFE21F4               # `move.l a6,-(sp)`; `addi.l #14,(sp)`: graf_mkstate handed &14(a6)
MOVE_L_A6_PUSH, ADDI_L_TO_SP_INDIRECT = 0x2F0E, 0x0697
BUTTON_SLOT = 14                        # hndl_button's fourth argument word, 14(a6) — read back at `$fe220c` btst #0,15(a6)


def test_hndl_button_s_store_into_its_argument_slot_is_read_back_by_no_caller():
    """hndl_button hands graf_mkstate THE ADDRESS OF ITS OWN ARGUMENT SLOT 14(a6) (its caller's frame) and reads it
    back: its one caller, deskmain, pops the five words at once (`addq.l #8,sp` — the fifth in Alcyon's slot) and reads
    none of them. Ours stores into the thunk's copy: the same class as do_fopen's and fat_mark's."""
    sites = [at for found in aes.line_f_call_sites(w3a.HNDL_BUTTON).values() for at in found]
    assert sites == [HNDL_BUTTON_CALL_SITE]
    assert case.word_in(BASE_IMAGE, HNDL_BUTTON_CALL_SITE + aes.WORD_BYTES) == op.ADDQ_L_8_SP
    assert [case.word_in(BASE_IMAGE, SLOT_HANDED_AT + offset) for offset in (0, aes.WORD_BYTES)] == [MOVE_L_A6_PUSH, ADDI_L_TO_SP_INDIRECT]
    assert case.long_in(BASE_IMAGE, SLOT_HANDED_AT + 2 * aes.WORD_BYTES) == BUTTON_SLOT


# ---- THE TARGET-ONLY ROW KIND: its census, by name (ruling O2) ---------------------------------------------------------------
TARGET_ONLY_ROWS_BY_NAME = {}            # `{registered name: its routine}` — of the plain kind: none (stage 1's rows all switch)
# ...and of the kind's rows that switch (the orchestrator's B2): stage 1's twenty (its fix pass's three among them), stage 2's fourteen,
# stage 3's fifty-one
TARGET_ONLY_SWITCHING_ROWS_BY_NAME = {
    "aes_desk_inf_show, arrival 0 of 'Desk > Desktop Info, Return'; Return at the first idle": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_SHOW,
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_SHOW,
    "aes_desk_inf_finish, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle": w3a.INF_FINISH,
    "aes_desk_inf_finish, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_FINISH,
    "aes_desk_inf_file, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_FILE,
    "aes_desk_inf_file, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_FILE,
    "aes_desk_inf_folder_dlg, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_FOLDER_DLG,
    "aes_desk_inf_disk, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search; Dfree's DISKINFO laid, every pointer recorded as handed]": w3a.INF_DISK,
    "aes_desk_inf_pref, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode]": w3a.INF_PREF,
    "aes_desk_ins_disk, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle": w3a.INS_DISK,
    "aes_desk_ins_app, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INS_APP,
    "aes_desk_opn_appl, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.OPN_APPL,
    "aes_desk_inf_folder_dlg, arrival 0 of 'files: the long file dragged onto the folder, then the folder selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INF_FOLDER_DLG,
    "aes_desk_ins_app, arrival 1 of 'files: the program installed as TOS-takes parameters, then Install Application again, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.INS_APP,
    # ...and stage 2's fourteen (`test_desk_w3a_stage2.py`): desksupp.c's three, do_optnmenu and do_deskmenu
    "aes_do_open, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_OPEN,
    "aes_do_open, arrival 0 of 'folder: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_OPEN,
    "aes_do_open, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.DO_OPEN,
    'aes_do_open, arrival 0 of "c: opened (LABELLED: F3 THE CARTRIDGE\'S LINE A DRIVE)"; no wait': w3a.DO_OPEN,
    "aes_do_open, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_OPEN,
    "aes_do_aopen, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.DO_AOPEN,
    "aes_do_info, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_INFO,
    "aes_do_info, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_INFO,
    "aes_do_info, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search; Dfree's DISKINFO laid, every pointer recorded as handed; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_INFO,
    "aes_do_optnmenu, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode]": w3a.DO_OPTNMENU,
    "aes_do_optnmenu, arrival 0 of 'Options > Save Desktop, Return'; Return at the first idle [GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers; the created handle's record the run's]": w3a.DO_OPTNMENU,
    "aes_do_optnmenu, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle": w3a.DO_OPTNMENU,
    "aes_do_optnmenu, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.DO_OPTNMENU,
    "aes_do_deskmenu, arrival 0 of 'Desk > Desktop Info, Return'; Return at the first idle": w3a.DO_DESKMENU,
    # ...and stage 3's forty-six (`test_desk_w3a_stage3.py`): hndl_msg, hndl_menu, do_filemenu and hndl_button
    "aes_hndl_msg, arrival 0 of 'Desk > Desktop Info, Return'; Return at the first idle": w3a.HNDL_MSG,
    "aes_hndl_msg, arrival 1 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "two windows: the lower one\'s title clicked (WM_TOPPED)"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    "aes_hndl_msg, arrival 0 of 'window: its closer clicked'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_MSG,
    "aes_hndl_msg, arrival 0 of 'window: its fuller clicked'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "files: the window\'s right arrow clicked"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "files: the window\'s horizontal slider dragged right"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "files: the window\'s down arrow clicked"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "files: the window\'s sizer pulled up and left (smaller)"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    'aes_hndl_msg, arrival 0 of "two windows: the top one\'s title dragged lower (WM_MOVED)"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_MSG,
    "aes_hndl_menu, arrival 0 of 'Desk > Desktop Info, Return'; Return at the first idle": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'Options > Save Desktop, Return'; Return at the first idle [GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers; the created handle's record the run's]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search; Dfree's DISKINFO laid, every pointer recorded as handed; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'A: File > Format, Return (the warning answered)'; Return at the first idle": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'window: View > Show as Text'; no wait": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'window: View > Sort by Size'; no wait": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'window: File > Close Window'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'folder: File > Close'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'window: View > Show as Icons (the view it has)'; no wait": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'files: View > Sort by Date'; no wait": w3a.HNDL_MENU,
    "aes_hndl_menu, arrival 0 of 'files: View > Sort by Type'; no wait": w3a.HNDL_MENU,
    "aes_do_filemenu, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search; Dfree's DISKINFO laid, every pointer recorded as handed; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'A: File > Format, Return (the warning answered)'; Return at the first idle": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'window: File > Close Window'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'window: its closer clicked'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.DO_FILEMENU,
    "aes_do_filemenu, arrival 0 of 'folder: File > Close'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.DO_FILEMENU,
    "aes_hndl_button, arrival 0 of 'drive A: selected'; no wait": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'a rubber box on the desktop, round the trash'; the box carried and let go at its door calls": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'window: A: opened again (two windows)'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'file: selected'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'folder: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]": w3a.HNDL_BUTTON,
    'aes_hndl_button, arrival 0 of "files: the long file shown, a blank at each page\'s end and at its end"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'files: the program selected, File > Show Info, Return'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 1 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'a rubber box on the desktop, round drive B: and the trash'; the box carried and let go at its door calls": w3a.HNDL_BUTTON,
    'aes_hndl_button, arrival 0 of "drive A:\'s object clicked at its corner, outside its image and its label"; no wait': w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'file: dragged to the trash, OK — then drive A: selected, File > Show Info, Return'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_BUTTON,
    "aes_hndl_button, arrival 0 of 'A: opened, the trash dragged into its window, Return'; the chain's own hands after the press [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]": w3a.HNDL_BUTTON,
    'aes_hndl_button, arrival 0 of "c: opened (LABELLED: F3 THE CARTRIDGE\'S LINE A DRIVE)"; no wait': w3a.HNDL_BUTTON,
    # ...and the stage's finish: the five classes ruled on (New Folder and the drag onto a folder over the frame-telling
    # replay; the text view's two under the G_USERDEF stack's window, the user's ruling of 2026-10-26)
    'aes_hndl_menu, arrival 0 of "folder: File > New Folder, \'A\', Return"; the chain\'s own hands after the item [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs; Dcreate\'s and Fclose\'s own frames told]': w3a.HNDL_MENU,
    'aes_do_filemenu, arrival 0 of "folder: File > New Folder, \'A\', Return"; the chain\'s own hands after the item [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs; Dcreate\'s and Fclose\'s own frames told]': w3a.DO_FILEMENU,
    "aes_hndl_button, arrival 0 of 'folder: the file dragged onto it, Return'; the chain's own hands after the press [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dcreate's and Fclose's own frames told]": w3a.HNDL_BUTTON,
    'aes_hndl_button, arrival 0 of "files: View > Show as Text, the long file\'s line clicked"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_BUTTON,
    'aes_hndl_button, arrival 0 of "text view: A: opened, the file\'s line dragged to the trash, Return (Cancel)"; the chain\'s own hands after the press [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]': w3a.HNDL_BUTTON,
}
NAMED_TARGET_ONLY_ROWS_DECLARING_A_BUDGET = 38    # the user's ruling of 2026-10-24: its own count, beside F4's (12 + 9 + 17)
TARGET_ONLY_ROWS_DECLARING_A_BUDGET = frozenset((   # ...and its rows BY NAME: the count pins how many, this which (RW3aP's F5)
    "aes_desk_inf_show, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_show, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_finish, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_file, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_file, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_folder_dlg, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_ins_app, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_opn_appl, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_inf_folder_dlg, arrival 0 of 'files: the long file dragged onto the folder, then the folder selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_desk_ins_app, arrival 1 of 'files: the program installed as TOS-takes parameters, then Install Application again, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    # ...stage 2's nine (`test_desk_w3a_stage2.ROW_INSNS`)
    "aes_do_open, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_open, arrival 0 of 'folder: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_open, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    'aes_do_open, arrival 0 of "c: opened (LABELLED: F3 THE CARTRIDGE\'S LINE A DRIVE)"; no wait',
    "aes_do_open, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_aopen, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_do_info, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_info, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_optnmenu, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    # ...stage 3's seventeen (`test_desk_w3a_stage3.ROW_INSNS`, `DIALOG_ROW_INSNS`)
    "aes_hndl_msg, arrival 0 of 'window: its fuller clicked'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    'aes_hndl_msg, arrival 0 of "files: the window\'s sizer pulled up and left (smaller)"; no wait [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]',
    "aes_hndl_menu, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_menu, arrival 0 of 'folder: File > Close'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_menu, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    "aes_do_filemenu, arrival 0 of 'A: File > Open'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_filemenu, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_do_filemenu, arrival 0 of 'folder: File > Close'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_button, arrival 0 of 'A: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_button, arrival 0 of 'window: A: opened again (two windows)'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_button, arrival 0 of 'folder: opened'; no wait [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged]",
    "aes_hndl_button, arrival 1 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]",
    'aes_hndl_button, arrival 0 of "c: opened (LABELLED: F3 THE CARTRIDGE\'S LINE A DRIVE)"; no wait',
    # ...and the stage's finish: four more (`ROW_INSNS`)
    'aes_hndl_menu, arrival 0 of "folder: File > New Folder, \'A\', Return"; the chain\'s own hands after the item [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs; Dcreate\'s and Fclose\'s own frames told]',
    'aes_do_filemenu, arrival 0 of "folder: File > New Folder, \'A\', Return"; the chain\'s own hands after the item [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs; Dcreate\'s and Fclose\'s own frames told]',
    "aes_hndl_button, arrival 0 of 'folder: the file dragged onto it, Return'; the chain's own hands after the press [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dcreate's and Fclose's own frames told]",
    'aes_hndl_button, arrival 0 of "text view: A: opened, the file\'s line dragged to the trash, Return (Cancel)"; the chain\'s own hands after the press [GEMDOS REPLAYED: the ROM\'s run in place\'s answers and DTAs]',
))


def _the_registries():
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    return w3a.the_registries()


def test_the_target_only_rows_are_their_own_census_line_by_name_and_it_holds():
    """THE KIND'S CENSUS LINE: its rows by name, each kind's (never in ROWS_THAT_SWITCH), and the census holds over the
    real registries — every companion-free row one of them, each plain row's runs reading its own budget, each
    switching row's drops its vouched ones, no W3a routine with a Tier 1."""
    registries = _the_registries()
    assert {name: row.name for name, row in registries.target_only.items()} == TARGET_ONLY_ROWS_BY_NAME
    assert {name: held.row.name for name, held in registries.switching_target_only.items()} == TARGET_ONLY_SWITCHING_ROWS_BY_NAME
    assert w3a.census_refusals(registries) == []


def test_the_named_target_only_budgets_are_their_own_count_each_read_by_every_run_of_its_original():
    """THE USER'S RULING OF 2026-10-24, ITS COUNT: the target-only rows declaring a budget, by name — none before the
    flip stages but stage 1's (all of the switching kind); each plain one's original run again as every consumer runs it (`test_boot_snapshot.run_original`,
    under `case.row_cap`): past the oracle's own cap, inside its budget by the margin."""
    import test_boot_snapshot
    _the_registries()
    named = w3a.named_budgets()
    assert set(named) == TARGET_ONLY_ROWS_DECLARING_A_BUDGET and len(named) == NAMED_TARGET_ONLY_ROWS_DECLARING_A_BUDGET
    for row_name in sorted(set(named) & set(w3a.TARGET_ONLY_ROWS)):
        _final, _writes, regs = test_boot_snapshot.run_original(case.registered_case(row_name))
        assert aes_event.DIFFERENTIAL_INSNS < regs["ninsns"] <= named[row_name] // aes_event.DERIVATION_MARGIN, row_name


A_ROW_OF = "aes_hndl_msg, a crafted arrival"
CRAFTED = w3a.TargetOnlyRow("a crafted arrival", w3a.HNDL_MSG, (), {}, True, None)
OUTSIDE = "aes_hndl_kbd, crafted"
A_BATTERY_S_CASE = "aes_do_open, a battery case"
CRAFTED_DROP = (0x100, 0x104, "a crafted drop")
CRAFTED_SWITCHING = namedtuple("CraftedRegistered", "row drops")(
    namedtuple("CraftedSwitchingRow", "name budget")(w3a.HNDL_MSG, None), (CRAFTED_DROP,))
NONE = w3a.Registries({}, {}, set(), set(), set(), {}, {})
BREACHES = {   # `{what: (the registries, the one refusal they read)}`
    "outside W3a": (NONE._replace(target_only={OUTSIDE: CRAFTED._replace(name="AES_ROM_HNDL_KBD")}, companion_free={OUTSIDE}),
                    f"{OUTSIDE}: {w3a.OUTSIDE_W3A} (AES_ROM_HNDL_KBD)"),
    "not registered companion-free": (NONE._replace(target_only={A_ROW_OF: CRAFTED}),
                                      f"{A_ROW_OF}: {w3a.NOT_REGISTERED_COMPANION_FREE}"),
    "in SWITCHING_ROWS": (NONE._replace(target_only={A_ROW_OF: CRAFTED}, companion_free={A_ROW_OF}, switching={A_ROW_OF}),
                          f"{A_ROW_OF}: {w3a.A_TARGET_ONLY_ROW_IN_SWITCHING_ROWS}"),
    "its runs read a budget it does not declare": (
        NONE._replace(target_only={A_ROW_OF: CRAFTED}, companion_free={A_ROW_OF}, budgets={A_ROW_OF: 1_000_000}),
        f"{A_ROW_OF}: {w3a.NOT_ITS_OWN_BUDGET}"),
    "its runs read another object than its declared constant": (
        NONE._replace(target_only={A_ROW_OF: CRAFTED._replace(budget=int("1000000"))}, companion_free={A_ROW_OF},
                      budgets={A_ROW_OF: int("1000000")}),
        f"{A_ROW_OF}: {w3a.NOT_ITS_OWN_BUDGET}"),
    "a switching row's drops not its vouched ones": (
        NONE._replace(switching_target_only={A_ROW_OF: CRAFTED_SWITCHING}, companion_free={A_ROW_OF}, dropped={A_ROW_OF: ()}),
        f"{A_ROW_OF}: {w3a.NOT_ITS_VOUCHED_DROPS}"),
    "a switching row outside W3a": (
        NONE._replace(switching_target_only={OUTSIDE: CRAFTED_SWITCHING._replace(row=CRAFTED_SWITCHING.row._replace(
            name="AES_ROM_HNDL_KBD"))}, companion_free={OUTSIDE}, dropped={OUTSIDE: (CRAFTED_DROP,)}),
        f"{OUTSIDE}: {w3a.OUTSIDE_W3A} (AES_ROM_HNDL_KBD)"),
    "companion-free, not the kind's": (NONE._replace(registered={OUTSIDE}, companion_free={OUTSIDE}),
                                       f"{OUTSIDE}: {w3a.NOT_THE_KIND_S}"),
    "a Tier 1 case of a W3a routine": (NONE._replace(registered={A_BATTERY_S_CASE}),
                                       f"{w3a.DO_OPEN}: {w3a.A_TIER_1_OF_W3A}: [{A_BATTERY_S_CASE!r}]"),
}


@pytest.mark.parametrize("what", BREACHES)
def test_the_census_reds_by_name_on_each_crafted_breach(what):
    registries, reads = BREACHES[what]
    assert w3a.census_refusals(registries) == [reads]


def test_the_census_holds_over_a_well_formed_crafted_row():
    """...AND ITS POSITIVE CONTROL: a target-only row of W3a's, registered companion-free, its runs reading its own
    budget — no refusal (its own registration is no Tier 1 of its routine)."""
    assert w3a.census_refusals(NONE._replace(target_only={A_ROW_OF: CRAFTED}, companion_free={A_ROW_OF}, registered={A_ROW_OF})) == []


def test_a_target_only_budget_no_registration_names_is_refused_by_name():
    """...AND UNNAMED: a target-only row's budget in the registry that no registration of the kind declares (one that
    went round `register_target_only`) — refused by its name by F4's own census (`test_aes_event.py`'s), which reads
    the kind's named budgets beside the batteries' plain ones."""
    import test_aes_event
    unnamed = "aes_hndl_msg, a budget no registration names"
    named = test_aes_event._named_plain_rows_declaring_a_budget() | set(w3a.named_budgets())
    with pytest.raises(AssertionError, match=re.escape(f"{test_aes_event.A_PLAIN_BUDGET_NOT_NAMED}: ['{unnamed}']")):
        test_aes_event.vet_every_plain_budget_is_named({**case.row_budgets(), unnamed: aes_event.DIFFERENTIAL_INSNS + 1}, named)


# ---- ...ITS REGISTRAR'S REFUSALS, each before anything is registered ------------------------------------------------------------
@pytest.fixture
def nothing_registered(monkeypatch):
    """`aes.register` made a refusal of its own: a registration that gets past the kind's refusals reds here."""
    def registered(*_args, **_kwargs):
        raise AssertionError("REGISTERED: the kind's refusal let the row through")
    monkeypatch.setattr(aes, "register", registered)
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {})
    yield
    assert w3a.TARGET_ONLY_ROWS == {}


def test_a_target_only_row_outside_w3a_is_refused_by_name(nothing_registered):
    with pytest.raises(AssertionError, match=re.escape(f"{OUTSIDE}: {w3a.OUTSIDE_W3A}")):
        w3a.register_target_only("crafted", "AES_ROM_HNDL_KBD", (0,), {})


def test_a_w3a_routine_with_a_host_core_is_refused_by_name(nothing_registered, monkeypatch):
    monkeypatch.setattr(w3a, "host_twin_of", lambda _name: object())
    with pytest.raises(AssertionError, match=re.escape(f"{A_ROW_OF}: {w3a.A_TIER_1_OF_W3A}: ['its host core']")):
        w3a.register_target_only("a crafted arrival", w3a.HNDL_MSG, (), {})


# ---- ...A NAMED ROW'S BUDGET (the user's ruling of 2026-10-24), held both ways at a real arrival ------------------------------
# hndl_msg at its first arrival of two chains (`aes_deskarrive.arrival`), its ROM run plain to its return: WM_TOPPED's
# past the oracle's own cap, WM_MOVED's inside it (measured, `$S/b6/W3a/PREP2/scripts/probe_n.py`). Each declaration the
# rule refuses is refused by the row's name, before anything is registered; the one it admits is recorded as ITSELF —
# the very object the row declared — where every run of the original reads it.
TOPPED_RUN, MOVED_RUN = 225_267, 120_227
PROBED = "a budget probed"
PROBED_ROW = f"aes_hndl_msg, {PROBED}"


@functools.cache
def _arrival_machine(chain):
    import aes_deskarrive as arrive
    return arrive.row_machine_of(arrive.arrival(w3a.HNDL_MSG, chain))


@pytest.fixture
def nothing_priced(monkeypatch):
    """`aes.ROWS.register` made a refusal: `aes.register` runs every vet of its own, and a row past them reds here."""
    def priced(*_args, **_kwargs):
        raise AssertionError("REGISTERED: the budget's refusal let the row through")
    monkeypatch.setattr(aes.ROWS, "register", priced)
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {})
    yield
    assert w3a.TARGET_ONLY_ROWS == {}


BUDGET_REFUSED = {
    "unneeded (the oracle's own cap covers the run)": (aes_desk.TOP_WINDOW_MOVED, MOVED_RUN * aes_event.DERIVATION_MARGIN,
                                                       r"declared budget refused — .* the oracle's own cap .* covers it"),
    "not fitted (under five times the run)": (aes_desk.LOWER_WINDOW_TOPPED, TOPPED_RUN * aes_event.DERIVATION_MARGIN - 1,
                                              r"declared budget refused — .* margin of 5: raise"),
    "stale (over ten times the run)": (aes_desk.LOWER_WINDOW_TOPPED,
                                       TOPPED_RUN * aes_event.DERIVATION_MARGIN * aes_event.DERIVATION_STALE + 1,
                                       r"declared budget refused — .* the declaration is stale — .* at most"),
}


@pytest.mark.parametrize("which", BUDGET_REFUSED)
def test_a_target_only_row_s_budget_is_refused_by_name_where_the_rule_refuses_it(which, nothing_priced):
    chain, budget, said = BUDGET_REFUSED[which]
    with pytest.raises(AssertionError, match=rf"^{re.escape(PROBED_ROW)}: a plain row's {said}"):
        w3a.register_target_only(PROBED, w3a.HNDL_MSG, (), _arrival_machine(chain), budget=budget)


PAST_ITS_CAP_REFUSED = {
    "undeclared (the oracle's own cap)": (None, aes_event.DIFFERENTIAL_INSNS),
    "declared below the run": (TOPPED_RUN - 1, TOPPED_RUN - 1),
}


@pytest.mark.parametrize("which", PAST_ITS_CAP_REFUSED)
def test_a_target_only_row_whose_run_passes_its_cap_is_refused_by_name(which, nothing_priced):
    budget, cap = PAST_ITS_CAP_REFUSED[which]
    with pytest.raises(RuntimeError, match=rf"^{re.escape(PROBED_ROW)}: .* did not reach rts within {cap} "):
        w3a.register_target_only(PROBED, w3a.HNDL_MSG, (), _arrival_machine(aes_desk.LOWER_WINDOW_TOPPED), budget=budget)


def test_a_target_only_row_whose_run_stores_no_mask_word_is_priced_companion_free_with_no_drop(monkeypatch):
    """`aes.register`'s OTHER BRANCH — a run that never stores the mask word (`aes.settled_mask_word` None): the row
    priced companion-free all the same, and nothing dropped."""
    handed = {}
    monkeypatch.setattr(aes, "settled_mask_word", lambda *_asked: None)
    monkeypatch.setattr(aes.ROWS, "register", lambda name, *_args, **named: handed.setdefault(name, named))
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {})
    w3a.register_target_only("a crafted arrival", w3a.HNDL_MSG, (), {})
    assert handed[A_ROW_OF]["companion_free"] is True and "dropped" not in handed[A_ROW_OF]


def test_a_fitted_budget_is_recorded_as_the_one_named_constant_every_run_reads(monkeypatch):
    """ADMITTED: five times the run — the row's registration hands the registry THE VERY OBJECT it declared (one
    named constant: `is`, not equal), which is what `case.row_cap` hands every run of its original."""
    topped_budget = int(str(TOPPED_RUN * aes_event.DERIVATION_MARGIN))      # an object of its own, as a constant is
    handed = {}
    monkeypatch.setattr(aes.ROWS, "register", lambda name, *_args, **named: handed.setdefault(name, named))
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {})
    w3a.register_target_only(PROBED, w3a.HNDL_MSG, (), _arrival_machine(aes_desk.LOWER_WINDOW_TOPPED), budget=topped_budget)
    assert handed[PROBED_ROW]["budget"] is topped_budget and handed[PROBED_ROW]["companion_free"]
    assert w3a.TARGET_ONLY_ROWS[PROBED_ROW].budget is topped_budget


# ---- ...ITS SWITCHING KIND (the orchestrator's B2): every drop vouched for by the ROM run's own write ledger -----------------
# ...a changed one INSIDE A BY-NATURE WINDOW, BY ADDRESS — never by its reason (the orchestrator's ruling on RW3aP's F1)
A_REASON = "a crafted reason no class declares"
LO, HI = 0x200, 0x204
STAGED = bytes(0x400)
CHANGED = bytes(LO) + b"\x01" * (HI - LO) + bytes(0x400 - HI)
LAST_BYTE_CHANGED = bytes(HI - 1) + b"\x01" + bytes(0x400 - HI)
STORED = frozenset(range(LO, HI))
NO_WINDOW = ()
AROUND = ((LO - 2, HI + 2, "a crafted class's window"),)
SHORT_OF_ITS_END = ((LO, HI - 1, "a crafted class's window"),)
PAST_ITS_START = ((LO + 1, HI + 2, "a crafted class's window"),)
VOUCH = {   # `{what: (drop's why, the run's final memory, its ledger, the run's windows, vouched)}`
    "stored unchanged, in no window": (A_REASON, STAGED, STORED, NO_WINDOW, True),
    "stored changed, inside a window, whatever its reason": (A_REASON, CHANGED, STORED, AROUND, True),
    "stored changed, its reason the mask word's, outside the mask word's window": (aes.LINE_F_MASK_WHY, CHANGED, STORED,
                                                                                 aes.LINE_F_MASK_WINDOW, False),
    "stored changed, past a window's end": (A_REASON, CHANGED, STORED, SHORT_OF_ITS_END, False),
    "stored changed, before a window's start": (A_REASON, CHANGED, STORED, PAST_ITS_START, False),
    "stored changed, in no window": (A_REASON, CHANGED, STORED, NO_WINDOW, False),
    "unstored, inside a window": (A_REASON, STAGED, frozenset(), AROUND, False),
    "half stored, unchanged": (A_REASON, STAGED, frozenset(range(LO, LO + 2)), NO_WINDOW, False),
    "all but its last byte stored, unchanged": (A_REASON, STAGED, frozenset(range(LO, HI - 1)), NO_WINDOW, False),
    "its last byte alone changed, in no window": (A_REASON, LAST_BYTE_CHANGED, STORED, NO_WINDOW, False),
}


@pytest.mark.parametrize("what", VOUCH)
def test_a_drop_is_vouched_for_by_a_store_unchanged_or_inside_a_window_stored_and_by_nothing_else(what):
    why, final, writes, windows, vouched = VOUCH[what]
    unvouched = w3a.drops_unvouched(((LO, HI, why),), STAGED, final, writes, windows)
    assert unvouched == ([] if vouched else [f"{LO:#x}..{HI:#x}: {why}"])


OWN_HAND = {   # `{what: (x_flag_differs, also_dropped)}`: what a crafted row names by its own hand
    "two spans of its own": (False, ((0x104, 0x108, aes.LINE_F_MASK_WHY), (0x10A, 0x10C, A_REASON))),
    "its declared X flag and a span of its own": (True, ((0x104, 0x108, aes.LINE_F_MASK_WHY),)),
}


@pytest.mark.parametrize("what", OWN_HAND)
def test_the_windows_are_the_drops_the_settling_derived_and_never_the_row_s_own(what):
    """THE WINDOWS a changed drop may lie in are what the settling derived off the ROM's run — every drop of the row
    but what it names by its own hand (`aes_switching.own_drops`: its spans, every one, and its declared X flag),
    whatever reason those give."""
    x_flag_differs, own = OWN_HAND[what]
    derived = (0x100, 0x110, "a span the settling derived")
    row = aes_switching.SwitchingRow("a crafted arrival", w3a.HNDL_MSG, (), dict, {}, x_flag_differs=x_flag_differs,
                                     also_dropped=own)
    flag = aes_switching.THE_X_FLAG_ALONE if x_flag_differs else ()
    held = namedtuple("CraftedRegistered", "row drops")(row, (derived, *flag, *own))
    assert w3a.by_nature_windows(row, held) == (derived,)


# The crafted settling's: the row's OWN span (`also_dropped`) — the mask word's reason, at no address of the mask word —
# its bytes stored by the run with a changed value; and, where it lies in one, the window the settling derived around it.
OWN_SPAN = (0x100, 0x104, aes.LINE_F_MASK_WHY)
DERIVED_AROUND_IT = (0x0FE, 0x108, "a span the settling derived")


@pytest.fixture
def a_crafted_settling(monkeypatch):
    """The switching registrar over a CRAFTED settling and replay of a hndl_msg row (`aes_switching.held_of`,
    `_replayed`): its own span `OWN_SPAN` stored by the run with a changed value, inside a derived window or not — and
    its registries empty and watched."""
    row = aes_switching.SwitchingRow("a crafted arrival", w3a.HNDL_MSG, (), dict, {}, also_dropped=(OWN_SPAN,))
    final = bytearray(STAGED)
    final[OWN_SPAN[0]:OWN_SPAN[1]] = b"\x01" * (OWN_SPAN[1] - OWN_SPAN[0])

    def settled(*, in_a_window):
        drops = ((DERIVED_AROUND_IT,) if in_a_window else ()) + (OWN_SPAN,)
        held = aes_switching.Registered(row, {0: STAGED}, drops, None, (aes.SHELL_PD,), None, {})
        monkeypatch.setattr(aes_switching, "held_of", lambda given: (given, held))
        return row
    monkeypatch.setattr(aes_switching, "_replayed", lambda _row, _pokes: (None, None, bytes(final), set(range(*DERIVED_AROUND_IT[:2]))))
    monkeypatch.setattr(w3a, "make_image", lambda pokes: pokes[0])
    monkeypatch.setattr(aes_event, "TARGET_ONLY_SWITCHING_ROWS", {})
    priced = {}
    monkeypatch.setattr(aes.ROWS, "register", lambda name, *_args, **named: priced.setdefault(name, named))
    return settled, priced


def test_a_switching_row_s_own_changed_span_in_no_window_is_refused_by_name_before_anything_is_registered(a_crafted_settling):
    """REFUSED: its own span, changed, inside no window the settling derived — whatever class its reason names."""
    settled, priced = a_crafted_settling
    with pytest.raises(AssertionError, match=re.escape(f"{A_ROW_OF}: {w3a.A_DROP_NO_STORE_VOUCHES_FOR}: "
                                                       f"{[f'{OWN_SPAN[0]:#x}..{OWN_SPAN[1]:#x}: {OWN_SPAN[2]}']}")):
        w3a.register_target_only_switching(settled(in_a_window=False))
    assert priced == {} and aes_event.TARGET_ONLY_SWITCHING_ROWS == {}


def test_a_vouched_switching_row_is_priced_companion_free_in_its_own_register(a_crafted_settling):
    """...and VOUCHED (its own span inside a derived window, stored): priced with no companion, its drops and deliveries
    the settling's, held in `aes_event.TARGET_ONLY_SWITCHING_ROWS` — never `SWITCHING_ROWS`."""
    settled, priced = a_crafted_settling
    w3a.register_target_only_switching(settled(in_a_window=True))
    assert priced[A_ROW_OF]["companion_free"] and "undropped" not in priced[A_ROW_OF]
    assert priced[A_ROW_OF]["dropped"] == (DERIVED_AROUND_IT, OWN_SPAN)
    assert set(aes_event.TARGET_ONLY_SWITCHING_ROWS) == {A_ROW_OF} and A_ROW_OF not in aes_event.SWITCHING_ROWS


def test_a_target_only_switching_row_s_deliveries_are_derived_again_by_its_own_register(monkeypatch):
    """The snapshot's noise sweep derives a registered row's deliveries again (`aes_event.rederived`): a target-only row
    that switches by ITS register's record, as a row of `SWITCHING_ROWS` by its."""
    again = object()
    monkeypatch.setattr(aes_event, "TARGET_ONLY_SWITCHING_ROWS",
                        {A_ROW_OF: namedtuple("Held", "rederived")(lambda: again)})
    assert aes_event.rederived(A_ROW_OF) is again


def test_a_switching_row_outside_w3a_is_refused_by_name(a_crafted_settling):
    settled, priced = a_crafted_settling
    outside = aes_switching.SwitchingRow("crafted", "AES_ROM_HNDL_KBD", (), lambda: {}, {})
    with pytest.raises(AssertionError, match=re.escape(f"{OUTSIDE}: {w3a.OUTSIDE_W3A}")):
        w3a.register_target_only_switching(outside)
    assert priced == {}


# ---- ...AND ITS REGISTRY'S SLOTS: a companion-free row's drop and budget, on a crafted registry -----------------------------------
DROP = ((0x100, 0x102, "a crafted drop"),)
A_NAMED_BUDGET = int("100000")          # an object of its own, as a battery's named constant is


def test_a_companion_free_row_keeps_its_drop_and_budget_with_no_companion_and_a_companion_is_refused(monkeypatch):
    """`case.Rows.register(companion_free=True)`: the drop recorded with NO companion and the row listed companion-free
    (`tier3_companion_free`: no consumer asks it for one); a declared budget recorded where every run of the original
    asks it (`row_cap`) — THE VERY OBJECT the row declared, `is`; a companion handed to it, or a row that is not priced,
    refused by name; and a drop of an ordinary row still needs its companion."""
    monkeypatch.setattr(case, "ROW_REGISTRIES", [])
    rows = case.Rows("a crafted registry")
    rows.register("crafted, free", 0x1000, {}, dropped=DROP, budget=A_NAMED_BUDGET, companion_free=True)
    assert case.tier3_dropped() == {"crafted, free": DROP} and case.tier3_undropped() == {}
    assert case.tier3_companion_free() == {"crafted, free"} and case.row_cap("crafted, free")["max_insns"] is A_NAMED_BUDGET
    for refused in ({"undropped": lambda: None}, {"priced": False}):
        with pytest.raises(AssertionError, match=re.escape(f"crafted, refused: {case.A_COMPANION_FREE_ROW_HAS_NONE}")):
            rows.register("crafted, refused", 0x1000, {}, dropped=DROP, companion_free=True, **refused)
    with pytest.raises(AssertionError, match="a Tier 3 drop needs the differential that drops nothing"):
        rows.register("crafted, ordinary", 0x1000, {}, dropped=DROP)


# ---- ...AND THE ONE SWITCHING CENSUS READS THE KIND'S REGISTER (the orchestrator's ruling on RW3aP's F1) --------------------
# `test_aes_event._the_switching_census` over a PILOT's own ROM run (`test_aes_evdisp_model.WOKEN_ROWS[0]`: ev_block's key
# typed ahead), registered as a TARGET-ONLY row that switches with ONE SPAN OF ITS OWN (`also_dropped`): admitted inside a
# window the census reads off that run, or stored unchanged; refused by the row's name in no window — by its reason never,
# by its hand never (the companion kind's exemption of its own spans admits that very span: the contrast).
CRAFTED_TARGET_ONLY = "a crafted target-only arrival"
CHANGED_IN_NO_WINDOW = 0xB2A0           # measured: AES bytes the pilot's ROM run changes, in no by-nature window
CHANGED_IN_THE_CONTEXT = 0x9C84         # measured: bytes of the pilot's caller's saved context its ROM run changes
SPAN_BYTES = 4
STRADDLE = 2                            # bytes a straddling span reaches past a window's bound on either side


def _the_pilot():
    import test_aes_evdisp_model as model
    return model.WOKEN_ROWS[0]


def _the_pilot_s_routine():
    return routines.core_symbol(_the_pilot().name)


def _the_pilot_s_context():
    """The pilot's caller's saved context as its settling drops it: `(lo, hi, why)`."""
    context_why = switch.uda_context_drop(0)[0][2]
    (context,) = (drop for drop in aes_switching.settled(_the_pilot()).drops if drop[2] == context_why)
    return context


def _the_crafted_pilot(own_span, x_flag_differs=False):
    """The pilot relabelled, `own_span` its own and its X flag declared where `x_flag_differs`."""
    return _the_pilot()._replace(label=CRAFTED_TARGET_ONLY, also_dropped=(own_span,), x_flag_differs=x_flag_differs)


def _the_pilot_s_census(own_span, monkeypatch, *, target_only=True, x_flag_differs=False):
    """The census of the pilot with `own_span` its own (and its X flag declared where `x_flag_differs`), registered
    target-only (or, `target_only` False, of the companion kind): `(its census, its name)`."""
    import test_aes_event
    row, held = aes_switching.held_of(_the_crafted_pilot(own_span, x_flag_differs))
    name = aes_switching.row_name(row)
    monkeypatch.setattr(aes_event, "TARGET_ONLY_SWITCHING_ROWS", {name: held} if target_only else {})
    monkeypatch.setattr(aes_event, "SWITCHING_ROWS", {} if target_only else {name: held})
    monkeypatch.setattr(case, "tier3_dropped", lambda: {name: held.drops})
    return test_aes_event.the_census_of_every_switching_row(), name


def test_the_switching_census_admits_a_target_only_row_s_own_span_inside_a_window(monkeypatch):
    """ADMITTED BY THE WINDOW ALONE: a span inside the caller's context that the pilot's ROM run CHANGES — so no store
    unchanged admits it (that kind absent from the census), the context's window does."""
    import test_aes_event
    lo, hi, _why = _the_pilot_s_context()
    own = (CHANGED_IN_THE_CONTEXT, CHANGED_IN_THE_CONTEXT + SPAN_BYTES, A_REASON)
    row = _the_crafted_pilot(own)
    the_rom_s = aes_switching.scheduled(row, aes_switching._staged(row))
    assert lo <= own[0] and own[1] <= hi, "the premise: the span lies inside the caller's context"
    assert any(the_rom_s.memory[at] != the_rom_s.started[at] for at in range(*own[:2])), "the premise: the run changes it"
    census, _name = _the_pilot_s_census(own, monkeypatch)
    assert census[test_aes_event.THE_CALLER_S_CONTEXT] == {_the_pilot_s_routine(): 1}
    assert test_aes_event.A_TARGET_ONLY_ROW_S_OWN_STORED_UNCHANGED not in census


def test_the_switching_census_admits_a_target_only_row_s_own_span_its_run_stores_unchanged(monkeypatch):
    import test_aes_event
    census, _name = _the_pilot_s_census((addrs.SYSVAR_SAVPTR, addrs.SYSVAR_SAVPTR + SPAN_BYTES, A_REASON), monkeypatch)
    assert census[test_aes_event.A_TARGET_ONLY_ROW_S_OWN_STORED_UNCHANGED] == {_the_pilot_s_routine(): 1}


OUT_OF_EVERY_WINDOW = {   # `{what: the row's own span}`
    "the mask word's reason, at no address of the mask word (unstored)": (LO, HI, aes.LINE_F_MASK_WHY),
    "changed by the run, in no window": (CHANGED_IN_NO_WINDOW, CHANGED_IN_NO_WINDOW + SPAN_BYTES, A_REASON),
    "a parked wait's reason, at no EVB naming the desk's stack": (CHANGED_IN_NO_WINDOW, CHANGED_IN_NO_WINDOW + SPAN_BYTES,
                                                                   aes_switching.DESK_PARKED_WHY),
}


def _refused_by_name(own_span, monkeypatch, said="a drop of no kind this census knows", **crafted):
    """The census of the pilot with `own_span` its own (`crafted`: `_the_pilot_s_census`'s) red by the row's name."""
    name = aes_switching.row_name(_the_pilot()._replace(label=CRAFTED_TARGET_ONLY))
    with pytest.raises(AssertionError, match=re.escape(f"{name}: {said}")):
        _the_pilot_s_census(own_span, monkeypatch, **crafted)


@pytest.mark.parametrize("what", OUT_OF_EVERY_WINDOW)
def test_the_switching_census_refuses_a_target_only_row_s_own_span_in_no_window_by_name(what, monkeypatch):
    _refused_by_name(OUT_OF_EVERY_WINDOW[what], monkeypatch)


def test_the_switching_census_refuses_a_target_only_row_s_own_span_straddling_the_context_s_end_by_name(monkeypatch):
    """...and a span straddling the END of the caller's context (its last bytes changed by the run, the next unstored):
    inside no window, nor stored unchanged."""
    _lo, hi, _why = _the_pilot_s_context()
    _refused_by_name((hi - STRADDLE, hi + STRADDLE, A_REASON), monkeypatch)


@pytest.mark.parametrize("x_flag_differs", (True, False), ids=("beside the flag it declares", "the flag undeclared"))
def test_the_switching_census_refuses_a_target_only_row_s_own_span_on_the_x_flag_s_byte_by_name(x_flag_differs, monkeypatch):
    """THE X FLAG'S BYTE is named once, by the row's declaration, or not at all: a span of its own there (`$8995`, which
    the pilot's run stores unchanged — so no window is asked) is one Tier 3 would drop whole, N/Z/V/C with it."""
    import test_aes_event
    own = (aes_switching.X_FLAG_AT, aes_switching.X_FLAG_AT + 1, A_REASON)
    _refused_by_name(own, monkeypatch, said=test_aes_event.X_FLAG_NOT_AS_DECLARED, x_flag_differs=x_flag_differs)


def test_the_companion_kind_s_own_span_is_exempt_where_the_target_only_kind_s_is_not(monkeypatch):
    """THE CONTRAST: the very span refused above, of a row WITH a companion (its own spans exempt, held to a change
    alone: `_vet_a_row_s_own`) — admitted. So the run changes it, and only the target-only kind is held to a window."""
    import test_aes_event
    own = OUT_OF_EVERY_WINDOW["changed by the run, in no window"]
    census, _name = _the_pilot_s_census(own, monkeypatch, target_only=False)
    assert census[test_aes_event.A_ROW_S_OWN + A_REASON] == {_the_pilot_s_routine(): 1}


# ---- ...AND THE DOOR'S PARK, A WINDOW BY ADDRESS (the orchestrator's ruling at W3a's stage 2, R9's kind): the census half --------
# of its crafted refusals, over stage 2's real rows (`test_desk_w3a_stage2.py` holds the vouch's half and the window's own):
# a target-only row's own span inside a door's park ITS ROM RUN STORES INTO is counted under that door's line
# (`test_aes_event._its_own_in_a_door_s_park`); one byte wider, or on a run that never stores the cell, a drop of no kind.
def _the_census_of(name, row, drops):
    """The switching census of stage 2's registered row `name` held as `row` with `drops` its registered drops."""
    import test_aes_event
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
    return test_aes_event._the_switching_census({name: held._replace(row=row, drops=drops)}, {name: drops})


def _a_drop_of_no_kind(name):
    return re.escape(f"{name}: a drop of no kind this census knows")


def test_the_census_counts_a_target_only_row_s_park_its_run_stores_under_the_door_s_line():
    import test_aes_event
    import test_desk_w3a_stage2 as stage_2
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[stage_2.THE_DRIVE_S_OPEN]
    census = _the_census_of(stage_2.THE_DRIVE_S_OPEN, held.row, held.drops)
    assert census[test_aes_event.THE_BIOS_DOOR_S_PARK] == {"aes_do_open": 1}
    assert test_aes_event.A_TARGET_ONLY_ROW_S_OWN_STORED_UNCHANGED not in census


@pytest.mark.parametrize("what", ("a byte below the longword", "a byte past the longword"))
def test_the_census_refuses_a_span_one_byte_wider_than_the_park_by_name(what):
    """The vouch's twin (`test_desk_w3a_stage2.test_a_span_one_byte_wider_than_the_park_on_a_real_row_is_refused_by_the_vouch`,
    which asserts the premise): "past" is refused for the WIDTH; "below" because File > Open's run leaves its extra byte
    UNSTORED (it pins "an unstored byte refused") — the width below is pinned by the pure census test that follows
    (`test_the_census_counts_a_door_s_park_by_its_cell_and_refuses_a_span_across_the_two`) and the vouch's pure test."""
    import test_desk_w3a_stage2 as stage_2
    import aes_desksupp
    lo, hi = stage_2.A_BYTE_WIDER[what]
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[stage_2.THE_DRIVE_S_OPEN]
    wider = (lo, hi, aes_desksupp.BIOS_DOOR_PARKED[0][2])
    drops = tuple(drop for drop in held.drops if drop not in aes_desksupp.BIOS_DOOR_PARKED) + (wider,)
    with pytest.raises(AssertionError, match=_a_drop_of_no_kind(stage_2.THE_DRIVE_S_OPEN)):
        _the_census_of(stage_2.THE_DRIVE_S_OPEN, held.row._replace(also_dropped=(wider,)), drops)


def test_the_census_refuses_the_park_s_reason_on_a_row_whose_run_never_stores_the_cell_by_name():
    import test_desk_w3a_stage2 as stage_2
    import aes_desksupp
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[stage_2.DESK_INFO_ROW]
    parked_row = held.row._replace(also_dropped=aes_desksupp.BIOS_DOOR_PARKED)
    with pytest.raises(AssertionError, match=_a_drop_of_no_kind(stage_2.DESK_INFO_ROW)):
        _the_census_of(stage_2.DESK_INFO_ROW, parked_row, held.drops + aes_desksupp.BIOS_DOOR_PARKED)


def test_a_companion_row_s_park_is_counted_as_before_and_never_through_the_window(monkeypatch):
    """A COMPANION ROW'S CENSUS UNCHANGED: drive_check's row at File > Open (its ROM run stores its park over 0) counts
    its park under the door's line by its own span, as before — the window is never asked for a row of that kind."""
    import test_aes_event
    import test_desk_supp

    def never(_writes):
        raise AssertionError("the door's window asked for a companion row")
    monkeypatch.setattr(aes_switching, "door_parks_stored", never)
    name = aes_switching.row_name(test_desk_supp.ROWS["A: File > Open"])
    held = aes_event.SWITCHING_ROWS[name]
    census = test_aes_event._the_switching_census({name: held}, {name: held.drops})
    assert census[test_aes_event.THE_BIOS_DOOR_S_PARK] == {"aes_drive_check": 1}


THE_DOOR_S_LINE = {"the BIOS door": "THE_BIOS_DOOR_S_PARK", "the XBIOS door": "THE_XBIOS_DOOR_S_PARK"}


@pytest.mark.parametrize("door", THE_DOOR_S_LINE)
def test_the_census_counts_a_door_s_park_by_its_cell_and_refuses_a_span_across_the_two(door, monkeypatch):
    """THE KIND BY THE CELL, crafted (no real row's park drops the XBIOS twin): over a ledger storing both doors' parks
    and a byte each side, a target-only row's own longword at either cell is counted under ITS door's line
    (`test_aes_event.DOOR_PARK_KINDS`); the span one byte wider below or past — across the two abutting cells, or into
    a byte of no park — under none."""
    import test_aes_event
    import test_desk_w3a_stage2 as stage_2
    cells = stage_2.EACH_DOOR_S_PARK
    writes = {at: 1 for at in range(min(cells.values()) - 1, max(cells.values()) + aes.LONG_BYTES + 1)}
    monkeypatch.setattr(aes_switching, "_replay_of", lambda *_run: (None, None, writes))
    cell = cells[door]
    park = (cell, cell + aes.LONG_BYTES, A_REASON)
    wider = ((cell - 1, cell + aes.LONG_BYTES, A_REASON), (cell, cell + aes.LONG_BYTES + 1, A_REASON))
    row = namedtuple("CraftedRow", "also_dropped")((park, *wider))
    parked = test_aes_event._its_own_in_a_door_s_park(row, None, None, ())
    assert parked == {getattr(test_aes_event, THE_DOOR_S_LINE[door]): (park,)}


# ---- ...AND ITS BUDGETS, READ BY THE TWO CENSUSES THAT NAME A DECLARED BUDGET (crafted registrations) -----------------------------
def test_the_plain_budget_census_reads_a_target_only_row_s_named_budget(monkeypatch):
    """F4's plain census (`test_aes_event.vet_the_plain_budget_census`) admits a target-only row's budget its kind's
    registrar named — and only through that half (without it the row's budget is unnamed: refused by name)."""
    import test_aes_event
    _the_registries()
    budget, registered = int(str(TOPPED_RUN * aes_event.DERIVATION_MARGIN)), case.row_budgets()
    monkeypatch.setattr(case, "row_budgets", lambda: {**registered, PROBED_ROW: budget})
    with pytest.raises(AssertionError, match=re.escape(f"{test_aes_event.A_PLAIN_BUDGET_NOT_NAMED}: ['{PROBED_ROW}']")):
        test_aes_event.vet_the_plain_budget_census()
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {PROBED_ROW: w3a.TargetOnlyRow(PROBED, w3a.HNDL_MSG, (), {}, True, budget)})
    test_aes_event.vet_the_plain_budget_census()


def test_a_target_only_switching_row_s_budget_is_declared_and_named_through_its_own_register(monkeypatch):
    """The derivation budgets' census (`test_aes_event`'s) reads a target-only row that switches through the one accessor
    of both registers, and names its budget through the kind's own (`named_budgets`' switching half)."""
    import test_aes_event
    budget = int(str(TOPPED_RUN * aes_event.DERIVATION_MARGIN))
    held = namedtuple("CraftedRegistered", "row")(namedtuple("CraftedSwitchingRow", "budget")(budget))
    monkeypatch.setattr(aes_event, "TARGET_ONLY_SWITCHING_ROWS", {A_ROW_OF: held})
    monkeypatch.setattr(w3a, "TARGET_ONLY_ROWS", {})
    assert w3a.named_budgets() == {A_ROW_OF: budget}
    assert test_aes_event._declared_derivation_budgets()[A_ROW_OF] is budget
    assert test_aes_event._target_only_switching_rows_naming_a_budget() == {A_ROW_OF}
