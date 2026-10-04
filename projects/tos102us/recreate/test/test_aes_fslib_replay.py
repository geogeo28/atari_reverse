r"""THE FILE SELECTOR over GEMDOS REPLAYED (`test/aes_fslib.py`, "GEMDOS REPLAYED") — the runs Tier 3 prices, and the
arms of the glue no disk gives.

A replayed run's `trap #1` reaches a staged handler that answers the ROM's own GEMDOS's answers, in order — D0 and, for
a search, the DTA — and records each call's frame in a ledger. So these cases hold three things the real disk's cannot:

  * the FRAMES fs_active and the glue trap with (the ledger: Fsetdta's DTA, Fsfirst's path and its attribute word,
    Fsnext's none, the bell's BEL), every call in order;
  * that the replay IS the disk's run where the selector can see it: the same names, index, count and list;
  * dos_snext's and the Cconout glue's verdicts for answers GEMDOS gives on no staged disk.

And the REGISTRY: each routine's rows, the worst realistic one of each measured by `make bench`.
"""
import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import aes_fslib as fsl
import aes_objdraw as od
import aes_shell as sh
import case
import gemdos_fs as fs
import gemdos_process as process
import test_aes_fslib as real
from case import merge_pokes
from opcodes import DROP_STACK_LONG

FS = fsl.FS
ACTIVE, NEWDIR, SNEXT, CCONOUT = fsl.ACTIVE, fsl.NEWDIR, fsl.SNEXT, fsl.CCONOUT
COUNT_AT = fsl.COUNT_AT
folder_path, ROOT_PATH = real.folder_path, real.ROOT_PATH
DTA_GLOBAL, NAMES_GLOBAL, INDEX_GLOBAL = FS["AES_AD_FSDTA"], FS["AES_AD_FSNAMES"], FS["AES_AD_FSINDEX"]
ENMFIL, EFILNF, EPTHNF = (aes.signed(code, 32) for code in (fs.GEMDOS_ENMFIL, process.GEMDOS_EFILNF,
                                                              fs.GEMDOS_EPTHNF))
AX_NO_MORE_FILES = sh.GEMDOSIF["DOS_AX_NO_MORE_FILES"]


def active(path, **kwargs):
    machine, frame = fsl.replayed(ACTIVE, path)
    return fsl.run_replayed(ACTIVE, fsl.active_arguments(frame), machine, **kwargs), frame


REPLAYED = (ROOT_PATH, *(folder_path(folder) for folder in ("SUBDIR", "ONE", "NINE", "TEN", "NINETY9", "HUNDRED", "BIG",
                                                             "REVERSE", "NOWHERE")),
            folder_path("MIXED", "*.T?T"))


@pytest.mark.parametrize("path", REPLAYED, ids=lambda path: path)
def test_fs_active_over_the_replay_leaves_what_the_disk_s_run_leaves(path):
    """The count, the names in the index's order, the blocks and both scratches: byte for byte the real GEMDOS run's."""
    replayed, _frame = active(path)
    disk = real.active(path)
    count = aes.signed(disk.word(COUNT_AT))
    assert replayed.word(COUNT_AT) == disk.word(COUNT_AT)
    assert fsl.kept_names(replayed.final, count) == fsl.kept_names(disk.final, count)
    names, index = disk.long(NAMES_GLOBAL), disk.long(INDEX_GLOBAL)
    for at, size in ((names, FS["FS_NAMES_BLOCK_BYTES"]), (index, FS["FS_INDEX_BLOCK_BYTES"]), (fsl.TEXT, fsl.TEXT_ROOM),
                     (fsl.NAME, fsl.NAME_ROOM)):
        assert replayed.after(at, size) == disk.after(at, size)


@pytest.mark.parametrize("path", (ROOT_PATH, folder_path("SUBDIR"), folder_path("NOWHERE")), ids=lambda path: path)
def test_fs_active_traps_with_the_dta_then_the_path_and_folders_too_then_nothing(path):
    """Fsetdta(the DTA block); Fsfirst(the path, 16); an Fsnext, of no argument, after every entry found."""
    result, frame = active(path)
    calls = fsl.replay_calls(result.final)
    assert calls[:2] == [fsl.call(fsl.FSETDTA, ("l", result.long(DTA_GLOBAL))),
                         fsl.call(fsl.FSFIRST, ("l", frame(fsl.ACTIVE_PATH)), ("w", FS["FS_SEARCH_ATTRIBUTES"]))]
    entries_found = sum(fsl.found(answer) for answer, _dta in fsl.whole_search(path)[1:])
    assert calls[2:] == [fsl.call(fsl.FSNEXT)] * entries_found


@pytest.mark.parametrize("folder, searches", (("HUNDRED", 103), ("BIG", 103)))
def test_fs_active_s_last_call_at_a_hundred_names_is_the_bell(folder, searches):
    """`.`, `..` and a hundred names found, one more Fsnext — whatever it answers — then Cconout(BEL), and no more."""
    result, _frame = active(folder_path(folder))
    calls = fsl.replay_calls(result.final)
    assert [entry.function for entry in calls[1:-1]] == [fsl.FSFIRST] + [fsl.FSNEXT] * (searches - 1)
    assert calls[-1] == fsl.call(fsl.CCONOUT_FN, ("w", addrs.CON_BEL))
    assert result.long(aes.AES_DOS_RETURN) == addrs.AES_FS_ACTIVE_BELL_RETURN


def test_a_filtered_hundred_and_one_names_are_searched_to_their_end_with_no_bell():
    """...and under a spec that keeps eleven of the 101 files, every entry is asked for — `.`, `..` and the 101, then
    the Fsnext that finds no more — and no Cconout follows: the hundred the search stops at is of names KEPT."""
    machine, frame = fsl.replayed(ACTIVE, folder_path("BIG", "F?0?.DAT"))
    result = fsl.run_replayed(ACTIVE, fsl.active_arguments(frame), machine)
    entries = len(fsl.FOLDERS["BIG"]) + fsl.DOT_ENTRIES
    assert [entry.function for entry in fsl.replay_calls(result.final)] == [fsl.FSETDTA, fsl.FSFIRST] + [fsl.FSNEXT] * entries
    assert aes.signed(result.word(COUNT_AT)) == len(real.names_of(real.active(folder_path("BIG", "F?0?.DAT"))))


def test_ninety_nine_names_ring_no_bell():
    result, _frame = active(folder_path("NINETY9"))
    assert fsl.CCONOUT_FN not in [entry.function for entry in fsl.replay_calls(result.final)]


def test_the_replay_s_script_is_the_rom_s_own_gemdos_s_answers():
    """Fsetdta answers whatever D0 the dispatcher was entered with; the root's search finds its thirteen names and
    two no listing shows (the volume label is none of them), then ENMFIL; the bell's Cconout answers the BIOS's."""
    whole = fsl.whole_search(ROOT_PATH)
    assert [aes.signed(answer, 32) for answer, _dta in whole[1:]] == [0] * len(fsl.ROOT) + [ENMFIL]
    names = [dta[fs.DTA_NAME:].split(b"\0")[0] for _answer, dta in whole[1:-1]]
    assert names == [fsl.listed_name(row)[1:] for row in fsl.ROOT]
    assert fsl.replay_script(folder_path("HUNDRED"))[-1] == (fsl.bell_answer(folder_path("HUNDRED")), fsl.NO_DTA)


@pytest.mark.parametrize("path", (ROOT_PATH, folder_path("SUBDIR"), folder_path("TEN")), ids=lambda path: path)
def test_fs_newdir_over_the_replay(path):
    machine, frame = fsl.replayed(NEWDIR, path)
    result = fsl.run_replayed(NEWDIR, fsl.newdir_arguments(frame), machine)
    disk, _frame = real.newdir(path)
    assert result.word(COUNT_AT) == disk.word(COUNT_AT)
    assert fsl.row_texts(result.final) == fsl.row_texts(disk.final)


# ---- dos_snext and the Cconout glue, an answer at a time ---------------------------------------------------------------
def at_the_first_fsnext(path, *script):
    """fs_input's run stopped at fs_active's first Fsnext (`real.snext_machine`), GEMDOS replayed from there: `script`
    the answers, the DTA the one Fsetdta named."""
    machine = real.snext_machine(path)
    dta = case.long_in(fsl.stopped(addrs.AES_ROM_DOS_SNEXT, path).final, DTA_GLOBAL)
    return merge_pokes(machine, fsl.replay_pokes(script, dta=dta)), dta


def next_entry(path):
    """...and what the ROM's own GEMDOS answers that Fsnext: the search's third call."""
    return fsl.whole_search(path)[2]


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_dos_snext_over_the_replay_finds_what_the_disk_s_finds(through_line_f):
    machine, dta = at_the_first_fsnext(ROOT_PATH, next_entry(ROOT_PATH))
    result = fsl.run_replayed(SNEXT, (), machine, through_line_f=through_line_f)
    disk = fsl.run(SNEXT, (), real.snext_machine(ROOT_PATH))
    assert result.answer() == disk.answer() == 1
    assert result.after(dta, fsl.DTA_BYTES) == disk.after(dta, fsl.DTA_BYTES)
    assert fsl.replay_calls(result.final) == [fsl.call(fsl.FSNEXT)]
    assert result.long(aes.AES_TRAP1_RETURN) == addrs.AES_DOS_SNEXT_TRAP_RETURN


# (the answer, dos_snext's own, AES_DOS_ERR, AES_DOS_AX) — the word decides "found", the LONG's sign the error.
SNEXT_VERDICTS = {
    "found": (0, 1, 0, 0),
    "no more files": (ENMFIL, 0, 1, AX_NO_MORE_FILES),
    "file not found": (EFILNF, 0, 1, AX_NO_MORE_FILES),
    "another error: its own word": (EPTHNF, 0, 1, EPTHNF & 0xFFFF),
    "a positive answer": (18, 0, 0, 18),
    "a zero word under a set high word: found": (0x0001_0000, 1, 0, 0),
    "a zero word under a negative long: found, and failed": (-0x1_0000, 1, 1, 0),
    "ENMFIL's word under a clear high word: no more, and no error": (0x0000_FFCF, 0, 0, AX_NO_MORE_FILES),
}


@pytest.mark.parametrize("answer, found, err, ax", SNEXT_VERDICTS.values(), ids=SNEXT_VERDICTS)
def test_dos_snext_s_verdict(answer, found, err, ax):
    machine, _dta = at_the_first_fsnext(ROOT_PATH, (answer, next_entry(ROOT_PATH)[1]))
    result = fsl.run_replayed(SNEXT, (), machine)
    assert (result.answer(), result.word(aes.AES_DOS_ERR), result.word(aes.AES_DOS_AX)) == (found, err, ax)


LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("answer", (0xFC0008, 0, -1), ids=("the BIOS's own", "0", "an error"))
def test_the_cconout_glue_traps_with_its_caller_s_word(answer, through_line_f):
    """ONE word under the function — the ledger records it alone — and the verdict of any other call."""
    machine, _dta = at_the_first_fsnext(ROOT_PATH, (answer, fsl.NO_DTA))
    return_site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    result = fsl.run_replayed(CCONOUT, (addrs.CON_BEL,), machine, host_arguments=(return_site,),
                              through_line_f=through_line_f)
    assert fsl.replay_calls(result.final) == [fsl.call(fsl.CCONOUT_FN, ("w", addrs.CON_BEL))]
    assert result.long_answer() == answer & 0xFFFF_FFFF
    assert [result.long(aes.AES_DOS_RETURN), result.long(aes.AES_TRAP1_RETURN), result.word(aes.AES_DOS_ERR),
            result.word(aes.AES_DOS_AX)] == [return_site, addrs.AES_DOS_TRAP_RETURN, int(answer < 0), answer & 0xFFFF]


def test_the_replay_handler_records_what_the_rom_s_glue_traps_with():
    """The handler under the ROM's own glue alone: what it records, fills and answers is the handler's, no claim
    about the C."""
    entry = next_entry(folder_path("ONE"))
    machine, dta = at_the_first_fsnext(folder_path("ONE"), entry)
    final, _writes, registers = emu.run(make_image(machine), addrs.AES_ROM_DOS_SNEXT)
    assert fsl.replay_calls(final) == [fsl.call(fsl.FSNEXT)]
    assert bytes(final[dta:dta + fsl.DTA_BYTES]) == entry[1] and registers["d0"] & 0xFFFF == 1
    assert case.long_in(final, fsl.SCRIPT_AT) == fsl.SCRIPT_ENTRIES_AT + fsl.SCRIPT_ENTRY_BYTES


# ---- the registry: Tier 3's rows ------------------------------------------------------------------------------------------
# Each routine's WORST realistic row and its distinct arms, from `make bench` (a routine that reaches the VDI is priced
# on its own cycles: "net", and with its thunks counted back "with thunks"). Measured as Tier 3 measures a row and left
# out, none any routine's worst:
#   * fs_back and fs_pspec of a name alone 0.85 / 0.69, of "A:*.*" 0.66 / 0.55, of 60 characters with no separator
#     1.03 / 0.93. Their worst is the longest scan: 70 cycles a byte against the ROM's 64, so 1.094 at the limit. The
#     row registered is the longest path the selector HOLDS — LONGEST_PATH_HELD characters, the path field's text
#     being that and a NUL short of the selection field's (a longer one runs on over it); past it, 120 characters
#     measure 1.059 / 0.999 and 250 measure 1.077 / 1.045;
#   * fs_1scroll at the last page 0.37 and over nine names 0.40;
#   * fs_format of ten names from the second and of a hundred from the 50th and the 91st: 0.876-0.878, against the
#     first nine's 0.88;
#   * fs_nscroll a page down 0.793 (the cursor shown 0.793), eight rows up 0.795, seven down 0.797, three up 0.80;
#   * fs_active of one name 0.82, of thirteen in reverse order 0.82, of folders and files under *.T?T 0.79, of a
#     hundred short names in order 0.79, shuffled 0.775, of sixty and eighty names of eight and three shuffled 0.816
#     and 0.815, of a hundred of them in reverse 0.818;
#   * fs_newdir of twenty-nine and of forty short names in order 0.808 and 0.804.
# THE BENCH's CAP (200,000 instructions of the original) bounds three routines' rows: fs_nscroll's page with the cursor
# shown runs 192,598; fs_newdir's largest directory of full-length names under it is thirty-four (198,740) — a hundred
# names run 274,097 over the replay, so fs_active's own rows price that read and sort; and a hundred full-length names
# SHUFFLED are past it for fs_active itself (the hundred in order run 154,325).
# The bell's Cconout takes the return site no frame carries (a host argument, as dos_sdta's): its cases are verified and
# it has no row — priced inside fs_active's row that rings it.
SELECTOR, ROWS, UP, DOWN, SELECTED = real.SELECTOR, real.ROWS, real.UP, real.DOWN, real.SELECTED
ROW_AT = fsl.ROW_AT
NO_ROW = {ROW_AT: bytes(aes.WORD_BYTES)}
A_FOLDER_S_PATH = b"A:\\FOLDER\\*.*"
# The longest path the selector holds whole: the path field's text runs to the selection field's, so that many bytes
# less its NUL (fs_sset copies with no bound of its own).
def _field_s_text(field):
    """Where the selector's field `field` keeps its text."""
    return aes.read_field(BASE_IMAGE, "TE", "PTEXT", od.object_long(fsl.SELECTOR, FS[field], "SPEC"))


LONGEST_PATH_HELD = _field_s_text("FS_SELECTION") - _field_s_text("FS_DIRECTORY") - len(b"\0")
START_MACHINE = aes.leaf_machine(onto=aes.stale_host_slot("AES_FS_START_TREE"))


def _string_row(label, name, text, **kwargs):
    aes.register(label, name, (real.STRING_AT, real.STRING_AT + len(text)), real.string_machine(text), **kwargs)


def _listed_row(label, name, arguments, folder, pokes=None, *, door=None, shown=False, **kwargs):
    made = fsl.listed(folder_path(folder), shown=shown)
    fsl.register(label, name, arguments(made), made.machine, pokes, door=door, **kwargs)


def _replayed_row(label, name, path, **kwargs):
    machine, frame = fsl.replayed(name, path)
    arguments = fsl.active_arguments(frame) if name == ACTIVE else fsl.newdir_arguments(frame)
    fsl.register(label, name, arguments, machine, door=fsl.replay_doors(), **kwargs)


def _register_rows():
    drawing, replay = fsl.drawing_doors(), fsl.replay_doors()
    aes.register("the selector's tree, centred", fsl.START, (), START_MACHINE)
    _string_row("a folder's path, from its end", fsl.BACK, A_FOLDER_S_PATH)
    _string_row("a drive and a spec: the separator put in", fsl.BACK, b"A:*.*")
    for name in (fsl.BACK, fsl.PSPEC):
        _string_row(f"a path of {LONGEST_PATH_HELD} characters with no separator: the longest the selector holds", name,
                    b"N" * LONGEST_PATH_HELD)
    _string_row("a folder's path", fsl.PSPEC, A_FOLDER_S_PATH)
    aes.register("down", fsl.ONE_SCROLL, (3, 20, DOWN), aes.leaf_machine())
    aes.register("up at the top", fsl.ONE_SCROLL, (0, 20, UP), aes.leaf_machine())
    for label, folder in (("a hundred names, the first nine", "BIG"), ("an empty list", "SUBDIR"),
                          ("folders and files", "MIXED")):
        _listed_row(label, fsl.FORMAT, lambda made: (SELECTOR, 0, made.count), folder)
    _listed_row("a row selected", fsl.SEL, lambda made: (1, SELECTED), "TEN", door=drawing)
    _listed_row("a row selected, the cursor shown", fsl.SEL, lambda made: (5, SELECTED), "TEN", door=drawing, shown=True)
    _listed_row("row 0: none", fsl.SEL, lambda made: (0, SELECTED), "TEN", door=drawing)
    for label, folder, arrow, rows, shown in (("one row down", "TEN", DOWN, 1, False),
                                              ("a page down: the whole list drawn", "BIG", DOWN, ROWS, False),
                                              ("up at the top: nothing moves", "TEN", UP, 1, False),
                                              ("one row down, the cursor shown", "TEN", DOWN, 1, True),
                                              ("a page down, the cursor shown", "BIG", DOWN, ROWS, True),
                                              ("eight rows down, the cursor shown: one row copied", "BIG", DOWN, ROWS - 1,
                                               True)):
        _listed_row(label, fsl.NSCROLL, lambda made, arrow=arrow, rows=rows: (SELECTOR, ROW_AT, 0, made.count, arrow, rows),
                    folder, NO_ROW, door=drawing, shown=shown)
    for label, path in (("an empty folder", folder_path("SUBDIR")), ("the root: its folders and three files", ROOT_PATH),
                        ("nine names", folder_path("NINE")), ("a hundred names: the bell", folder_path("HUNDRED")),
                        ("a hundred names of eight characters and three: the bell", folder_path("EIGHT3")),
                        ("a missing folder", folder_path("NOWHERE"))):
        _replayed_row(label, ACTIVE, path)
    _replayed_row("the root", NEWDIR, ROOT_PATH)
    _replayed_row("an empty folder", NEWDIR, folder_path("SUBDIR"))
    _replayed_row("twenty-eight names in no order", NEWDIR, folder_path("SHUFFLED"))
    _replayed_row("thirty-four names of eight characters and three", NEWDIR, folder_path("THIRTY4"))
    found, _dta = at_the_first_fsnext(ROOT_PATH, next_entry(ROOT_PATH))
    fsl.register("found", SNEXT, (), found, door=replay)
    no_more, _dta = at_the_first_fsnext(ROOT_PATH, (ENMFIL, next_entry(ROOT_PATH)[1]))
    fsl.register("no more files", SNEXT, (), no_more, door=replay)
    # ...and each through its call word: verified, unpriced.
    aes.register("the selector's tree", fsl.START, (), START_MACHINE, through_line_f=True)
    for name in (fsl.BACK, fsl.PSPEC):
        _string_row("a folder's path", name, A_FOLDER_S_PATH, through_line_f=True)
    aes.register("down", fsl.ONE_SCROLL, (3, 20, DOWN), aes.leaf_machine(), through_line_f=True)
    _listed_row("ten names", fsl.FORMAT, lambda made: (SELECTOR, 1, made.count), "TEN", through_line_f=True)
    _listed_row("a row selected", fsl.SEL, lambda made: (1, SELECTED), "TEN", door=drawing, through_line_f=True)
    _listed_row("one row down", fsl.NSCROLL, lambda made: (SELECTOR, ROW_AT, 0, made.count, DOWN, 1), "TEN", NO_ROW,
                door=drawing, through_line_f=True)
    _replayed_row("the root", ACTIVE, ROOT_PATH, through_line_f=True)
    _replayed_row("an empty folder", NEWDIR, folder_path("SUBDIR"), through_line_f=True)
    fsl.register("found", SNEXT, (), found, door=replay, through_line_f=True)


_register_rows()
