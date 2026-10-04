r"""THE FILE SELECTOR's event-free half (`src/aes/fslib.c`) and the two pieces of the GEMDOS glue it reaches
(`src/aes/gemdosif.c`):

    fs_start()                       ad_fstree := rs_gaddr(R_TREE, 0); ob_center(ad_fstree, &gl_rfs)
    fs_back(path, end)               end-- until *end is ':' or '\' or end == path; on a ':' — ++end, a '\' inserted there
    fs_pspec(path, end)              fs_back; on a '\' the byte after it; else path := "A:\*.*", path + 3
    fs_active(path, spec, &count)    busy mouse; Fsetdta; Fsfirst(path, 16) / Fsnext: each entry not starting '.', a
            folder or a file wildcmp(spec) keeps, copied kind + name into the names block, its offset into the index;
            at 100 names the bell and no more; *count; a shell sort of the index by name; the arrow; 1
    fs_1scroll(top, count, arrow)    top - 1 for the up arrow, top + 1 for any other, kept in 0 .. count - 9; top itself
            when count <= 9
    fs_format(tree, top, count)      nine rows from name `top`: kind + the 8.3 name formatted, or a space; each row's
            text set and its state cleared; the elevator's height and place by mul_div; 1
    fs_sel(row, state)               row != 0: ob_change(ad_fstree, row + 11, state, drawn)
    fs_nscroll(tree, &row, top, count, arrow, n)   n x fs_1scroll; moved: the row deselected and forgotten, fs_format,
            the rows that stay copied on the screen, the new ones drawn under their own clip, the slider; the top
    fs_newdir(title, path, spec, tree, &count)     the path drawn; fs_active; fs_format from 0; the title " spec ";
            the title, the list and the slider drawn
    dos_snext()                      Fsnext; dos_sfirst's tail
    Cconout glue ($fe3bf6)           Cconout through $fe3c28 over the word its caller pushed

THE MACHINES ARE THE ROM's OWN fs_input's, stopped where it enters the routine (`test/aes_fslib.py`), over a staged disk
holding one folder per directory shape; a path an application hands fs_back or fs_pspec is staged in the window.
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import aes_event
import aes_fslib as fsl
import aes_objdraw as od
import aes_shell as sh
import aes_strings
import case
import vdi
import vdi_helpers
from case import merge_pokes
from aes_objects import screen_origin
from opcodes import DROP_STACK_LONG
from test_aes_gsx import screen_changed

FS = fsl.FS
START, BACK, PSPEC, ACTIVE, ONE_SCROLL = fsl.START, fsl.BACK, fsl.PSPEC, fsl.ACTIVE, fsl.ONE_SCROLL
FORMAT, SEL, NSCROLL, NEWDIR, SNEXT, CCONOUT = fsl.FORMAT, fsl.SEL, fsl.NSCROLL, fsl.NEWDIR, fsl.SNEXT, fsl.CCONOUT
SELECTOR = fsl.SELECTOR
ROWS = fsl.ROWS
UP, DOWN = fsl.UP_ARROW, fsl.DOWN_ARROW
STRING_AT = fsl.STRING_AT
COUNT_AT, ROW_AT = fsl.COUNT_AT, fsl.ROW_AT
SELECTED = od.STATE_BITS["SELECTED"]
ROOT_PATH, folder_path = fsl.ROOT_PATH, fsl.folder
NUL = b"\0"


# ---- fs_start -----------------------------------------------------------------------------------------------------------
# No fs_input here: start-up's own call (gem_main's), over the snapshot. The attribution pass shows its three stores —
# ad_fstree, gl_rfs and the root's x and y — which the snapshot already holds at the values a second run leaves.
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_fs_start_keeps_the_selector_s_tree_and_centres_it(through_line_f):
    pokes = aes.leaf_machine(onto=merge_pokes(aes.stale_host_slot("AES_FS_START_TREE"),
                                              {FS["AES_AD_FSTREE"]: vdi.pack_words(aes.STALE_WORD, aes.STALE_WORD)},
                                              {FS["AES_GL_RFS"]: vdi.pack_words(*[aes.STALE_WORD] * 4)}))
    result = aes.run_function(START, (), pokes, through_line_f=through_line_f)
    assert result.long(FS["AES_AD_FSTREE"]) == SELECTOR == aes.resource_tree(FS["FS_TREE_INDEX"])
    # ...and the box is the one start-up's own call left in the snapshot: the outlined root's, three pixels out.
    assert result.after(FS["AES_GL_RFS"], aes.GRECT_BYTES) == bytes(BASE_IMAGE[FS["AES_GL_RFS"]:FS["AES_GL_RFS"] + aes.GRECT_BYTES])


def test_fs_start_centres_the_tree_from_where_it_lies():
    """The root moved off-centre first (an application's objc_offset would see it there): centred again, the box
    answered from the root's new place."""
    moved = aes.object_pokes(SELECTOR, aes.OB_ROOT, X=3, Y=5)
    result = aes.run_function(START, (), aes.leaf_machine(onto=merge_pokes(aes.stale_host_slot("AES_FS_START_TREE"), moved)))
    snapshot = aes.read_object(BASE_IMAGE, SELECTOR, aes.OB_ROOT)
    assert (result.object(SELECTOR, aes.OB_ROOT)["X"], result.object(SELECTOR, aes.OB_ROOT)["Y"]) == (snapshot["X"],
                                                                                                      snapshot["Y"])


# ---- fs_back and fs_pspec -------------------------------------------------------------------------------------------------
PATH_ROOM = FS["FS_PATH_ROOM"]


def string_machine(text, before=b""):
    """An application's path at STRING_AT, FILLed after it, `before` staged in the bytes just below it."""
    return aes.leaf_machine(onto=merge_pokes(sh.text(STRING_AT + len(before), text, fsl.STRING_BYTES - len(before)),
                                              {STRING_AT: before} if before else None))


def back(text, end=None, *, before=b"", path_tag=0, end_tag=0, **kwargs):
    """fs_back over `text`, from `end` bytes into it (its NUL by default)."""
    path = STRING_AT + len(before)
    end = path + (len(text) if end is None else end)
    return aes.run_function(BACK, (path | path_tag, end | end_tag), string_machine(text, before), **kwargs), path


def text_at(result, at):
    """The NUL-ended string a run left at `at`."""
    return aes_strings.string_in(result.final, at)


# (the path, where fs_back starts — None its NUL —, where it answers, the path after)
BACKS = {
    "to the last separator": (b"A:\\FOLDER\\*.*", None, len(b"A:\\FOLDER"), None),
    "from a separator: there": (b"A:\\FOLDER\\*.*", len(b"A:\\FOLDER"), len(b"A:\\FOLDER"), None),
    "from below one: the one before": (b"A:\\ONE\\TWO\\*.*", len(b"A:\\ONE\\TW"), len(b"A:\\ONE"), None),
    "to the root's": (b"A:\\*.*", None, len(b"A:"), None),
    "a drive and a name: a separator put in after the colon": (b"A:*.*", None, len(b"A:"), b"A:\\*.*"),
    "a drive alone": (b"A:", None, len(b"A:"), b"A:\\"),
    "no separator: the path itself": (b"NAME.TXT", None, 0, None),
    "empty": (b"", None, 0, None),
    "a colon first": (b":X", None, 1, b":\\X"),
    "a separator first": (b"\\X", None, 0, None),
    "the last separator wins: a colon after a backslash": (b"\\A:B", None, len(b"\\A:"), b"\\A:\\B"),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("text, end, answer, after", BACKS.values(), ids=BACKS)
def test_fs_back(text, end, answer, after, through_line_f):
    result, path = back(text, end, through_line_f=through_line_f)
    assert result.long_answer() == path + answer
    assert text_at(result, path) == (text if after is None else after)


def test_fs_back_reads_nothing_below_the_path():
    """Separators just BELOW the path are not reached: the walk ends on the path's own first byte."""
    result, path = back(b"NAME", before=b"\\:")
    assert result.long_answer() == path


def test_fs_back_compares_the_two_pointers_whole():
    """A top byte on `end` alone: the two never compare equal, and the walk goes on below the path to the separator
    staged there — the answer the register, its top byte kept."""
    result, path = back(b"NAME", before=b"X\\YZ", end_tag=aes.BUS_TAG)
    assert result.long_answer() == (path - len(b"\\YZ")) | aes.BUS_TAG


def test_fs_back_puts_both_pointers_on_the_bus():
    result, path = back(b"A:*.*", path_tag=aes.BUS_TAG, end_tag=aes.BUS_TAG)
    assert result.long_answer() == (path + len(b"A:")) | aes.BUS_TAG and text_at(result, path) == b"A:\\*.*"


@pytest.mark.parametrize("tail", (PATH_ROOM - 2, PATH_ROOM - 1, PATH_ROOM, PATH_ROOM + 6),
                         ids=("two short of the room", "one short", "the room itself", "past it"))
def test_fs_back_s_separator_is_inserted_in_64_bytes_of_room(tail):
    """ins_char's room is FS_PATH_ROOM from the byte after the colon: a longer tail is cut there by its NUL, not moved."""
    text = b"A:" + b"x" * tail
    result, path = back(text)
    after = text_at(result, path)
    assert after[:len(b"A:\\")] == b"A:\\"
    assert len(after) == (len(text) + 1 if tail < PATH_ROOM - 1 else len(b"A:") + PATH_ROOM - 1)


# (the path, where the spec starts in it or None for the default, the path after)
DEFAULT_PATH = b"A:\\*.*"
PSPECS = {
    "a folder's spec": (b"A:\\FOLDER\\*.TXT", len(b"A:\\FOLDER\\")),
    "the root's": (b"A:\\*.*", len(b"A:\\")),
    "a path ending in its separator: an empty spec": (b"A:\\FOLDER\\", len(b"A:\\FOLDER\\")),
    "a drive and a spec: the separator put in, then past it": (b"B:*.PRG", len(b"B:\\")),
    "no separator: the ROM's default path": (b"NAME.TXT", None),
    "empty: the default": (b"", None),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("text, spec", PSPECS.values(), ids=PSPECS)
def test_fs_pspec(text, spec, through_line_f):
    path = STRING_AT
    result = aes.run_function(PSPEC, (path, path + len(text)), string_machine(text), through_line_f=through_line_f)
    if spec is None:
        assert result.long_answer() == path + FS["FS_DEFAULT_SPEC_AT"] and text_at(result, path) == DEFAULT_PATH
    else:
        assert result.long_answer() == path + spec


def test_the_default_path_is_the_rom_s_string():
    at = FS["AES_FS_DEFAULT_PATH"]
    assert bytes(BASE_IMAGE[at:at + len(DEFAULT_PATH) + 1]) == DEFAULT_PATH + NUL
    assert bytes(BASE_IMAGE[FS["AES_FS_TITLE_TAIL"]:FS["AES_FS_TITLE_TAIL"] + 2]) == b" " + NUL
    redrawn = FS["AES_FS_REDRAWN"]
    assert bytes(BASE_IMAGE[redrawn:redrawn + 4]) == bytes([5, FS["FS_FILE_BOX"], 7, 0])


def test_fs_pspec_puts_its_pointers_on_the_bus():
    text = b"A:\\FOLDER\\*.TXT"
    result = aes.run_function(PSPEC, (STRING_AT | aes.BUS_TAG, (STRING_AT + len(text)) | aes.BUS_TAG), string_machine(text))
    assert result.long_answer() == (STRING_AT + len(b"A:\\FOLDER\\")) | aes.BUS_TAG


def test_fs_pspec_s_default_keeps_the_path_s_top_byte():
    result = aes.run_function(PSPEC, (STRING_AT | aes.BUS_TAG, (STRING_AT + 4) | aes.BUS_TAG), string_machine(b"NAME"))
    assert result.long_answer() == (STRING_AT + FS["FS_DEFAULT_SPEC_AT"]) | aes.BUS_TAG
    assert text_at(result, STRING_AT) == DEFAULT_PATH


# ...and as fs_input itself calls them: its first fs_pspec — of the copy it compares paths in — and fs_back under it.
INPUT_PATHS = (ROOT_PATH, folder_path("MIXED", "*.T?T"), "NOSLASH", "A:*.RSC")


@pytest.mark.parametrize("name", (PSPEC, BACK), ids=("fs_pspec", "fs_back"))
@pytest.mark.parametrize("path", INPUT_PATHS, ids=lambda path: repr(path))
def test_fs_pspec_and_fs_back_as_fs_input_calls_them(path, name):
    machine, frame = fsl.entered(name, path)
    fsl.run(name, (frame(fsl.BACK_PATH), frame(fsl.BACK_END)), machine)


# ---- fs_1scroll -------------------------------------------------------------------------------------------------------------
TOPS = (-32768, -2, -1, 0, 1, 2, 5, 8, 9, 10, 11, 90, 91, 92, 32767)
# ...the last an arrow whose LOW BYTE alone is the up arrow's: `cmp.w #8,d5` ($fe7a12) compares the word — down.
UP_IN_THE_LOW_BYTE_ALONE = 0x0100 | UP
ARROWS = (UP, DOWN, 0, -1, 7, UP_IN_THE_LOW_BYTE_ALONE)


@pytest.mark.parametrize("count", (-1, 0, 1, 8, 9, 10, 11, 18, 100, 32767),
                         ids=lambda count: f"{count} names")
def test_fs_1scroll(count):
    """Every top a list can hold and some it cannot, under each arrow: the ROM's answer, a signed word."""
    for top in TOPS:
        for arrow in ARROWS:
            aes.run_function(ONE_SCROLL, (top, count, arrow), aes.leaf_machine())


@pytest.mark.parametrize("top, count, arrow, answer", (
    (0, 10, DOWN, 1), (1, 10, DOWN, 1), (1, 10, UP, 0), (0, 10, UP, 0), (0, 9, DOWN, 0), (5, 100, UP, 4),
    (91, 100, DOWN, 91), (90, 100, DOWN, 91), (3, 100, 0, 4), (5, 20, UP_IN_THE_LOW_BYTE_ALONE, 6)),
    ids=("down", "down at the last page: stays", "up", "up at the top: stays", "nine names: never moves", "up, mid-list",
         "the last page of a hundred", "onto it", "any arrow but the up one is down",
         "the up arrow's number in the low byte alone: the arrow is a WORD, and this one is down"))
def test_fs_1scroll_keeps_the_top_inside_the_list(top, count, arrow, answer):
    assert aes.run_function(ONE_SCROLL, (top, count, arrow), aes.leaf_machine()).answer() == answer


def test_fs_1scroll_through_its_call_word():
    assert aes.run_function(ONE_SCROLL, (4, 20, DOWN), aes.leaf_machine(), through_line_f=True).answer() == 5


# ---- fs_active ----------------------------------------------------------------------------------------------------------------
def active(path, *, shown=False, count_at=COUNT_AT, tags=(0, 0, 0), pokes=None, **kwargs):
    """fs_active as fs_input's first fs_newdir calls it over `path`: the ROM's own path and spec, the count moved
    out of fs_input's frame."""
    machine, frame = fsl.entered(ACTIVE, path, shown=shown)
    arguments = tuple(value | tag for value, tag in zip(fsl.active_arguments(frame, count_at), tags))
    return fsl.run(ACTIVE, arguments, machine, pokes, **kwargs)


def names_of(result, count_at=COUNT_AT):
    return fsl.kept_names(result.final, aes.signed(result.word(count_at)))


WHOLE_DIRECTORIES = (ROOT_PATH, *(folder_path(folder) for folder in ("SUBDIR", *fsl.FOLDERS)))
TWINS_PATH = folder_path("TWINS")


@pytest.mark.parametrize("path", WHOLE_DIRECTORIES, ids=lambda path: path)
def test_fs_active_reads_and_sorts_a_directory(path):
    """Every name but `.` and `..`, a hundred at most, in order: folders first, then files, each by its bytes."""
    result = active(path)
    assert names_of(result) == fsl.sorted_names(fsl.directory(path))
    assert result.answer() == FS["FS_ACTIVE_ANSWER"]


def test_fs_active_leaves_equal_names_in_the_order_it_found_them():
    """One name held three times: the sort swaps a pair only when the first is GREATER, so equal names keep their
    places — their offsets in the index rising."""
    result = active(TWINS_PATH)
    assert names_of(result) == [b" OTHER.TXT"] + [b" SAME.TXT"] * 3
    index = result.long(FS["AES_AD_FSINDEX"])
    offsets = [result.long(index + entry * FS["FS_INDEX_ENTRY_BYTES"]) for entry in range(1, 4)]
    assert offsets == sorted(offsets)


# THE BLOCKS ARE AS MALLOC HANDS THEM: GEMDOS clears nothing, and a TPA other programs ran in holds whatever they left.
# The three blocks staged FILLed: every longword of the index and every byte of a name fs_active uses is one it stored.
def uncleared_blocks(machine):
    image = make_image(machine)
    fill = bytes([vdi.FILL])
    return {case.long_in(image, FS[name]): fill * FS[size] for name, size in (
        ("AES_AD_FSNAMES", "FS_NAMES_BLOCK_BYTES"), ("AES_AD_FSINDEX", "FS_INDEX_BLOCK_BYTES"),
        ("AES_AD_FSDTA", "FS_DTA_BLOCK_BYTES"))}


@pytest.mark.parametrize("path", (ROOT_PATH, folder_path("NINE"), folder_path("SUBDIR")), ids=lambda path: path)
def test_fs_active_over_blocks_malloc_left_uncleared(path):
    machine, _frame = fsl.entered(ACTIVE, path)
    result = active(path, pokes=uncleared_blocks(machine))
    assert names_of(result) == fsl.sorted_names(fsl.directory(path))


# THE BUSY FORM IS SHOWN WHILE THE DIRECTORY IS READ, and gone when fs_active returns — so where it can be seen is the
# machine at fs_active's FIRST GEMDOS call: the C's image when its Fsetdta reaches the replay's twin, against the ROM's
# own run stopped at dos_sdta's entry.
MOUSE_FORM = (vdi.LINEA_M_POS_HX, aes.GSX_MOUSE_FORM_BYTES)


@pytest.mark.parametrize("shown", (False, True), ids=("the cursor hidden", "the cursor shown"))
def test_fs_active_shows_the_busy_form_before_its_first_gemdos_call(shown):
    machine, frame = fsl.replayed(ACTIVE, ROOT_PATH, shown=shown)
    arguments = fsl.active_arguments(frame)
    seen = []
    fsetdta = fsl.gemdos.rom_handler(fsl.FSETDTA)

    def at_the_first_call(buf, frame_at, frame_bytes):
        seen.append((bytes(buf[MOUSE_FORM[0]:MOUSE_FORM[0] + MOUSE_FORM[1]]), bytes(buf[vdi.SCREEN.base:vdi.SCREEN.base + vdi.SCREEN.bytes])))
        return fsl.REPLAY_HANDLERS[fsetdta](buf, frame_at, frame_bytes)

    door = aes.doors(functools.partial(fsl.gemdos.bound_handlers, {**fsl.REPLAY_HANDLERS, fsetdta: at_the_first_call}),
                     *fsl.drawing_hooks())
    fsl.run_replayed(ACTIVE, arguments, machine, door=door)
    rom, _writes, registers = emu.run(make_image(aes.staged(ACTIVE, arguments, machine)), addrs.AES_ROM_FS_ACTIVE,
                                      stop_pc=addrs.AES_ROM_DOS_SDTA)
    assert registers["checkpoint"]
    busy = case.long_in(BASE_IMAGE, FS["AES_AD_HGMICE"])
    (form, screen), = seen
    assert form == bytes(rom[MOUSE_FORM[0]:MOUSE_FORM[0] + MOUSE_FORM[1]])
    assert form[:aes.LONG_BYTES] == bytes(BASE_IMAGE[busy:busy + aes.LONG_BYTES])
    assert screen == bytes(rom[vdi.SCREEN.base:vdi.SCREEN.base + vdi.SCREEN.bytes])


def rang(result):
    """Whether the run left the BIOS's sound driver on the bell's list."""
    return result.long(addrs.SOUND_LIST_POINTER) == addrs.BELL_SOUND_LIST


@pytest.mark.parametrize("folder, rings", (("NINETY9", False), ("HUNDRED", True), ("BIG", True)))
def test_fs_active_rings_the_bell_at_a_hundred_names(folder, rings):
    """At the hundredth name kept the search ends and the bell is rung (GEMDOS Cconout of BEL, through the BIOS's
    console) — whether or not the directory holds more."""
    result = active(folder_path(folder))
    assert aes.signed(result.word(COUNT_AT)) == min(len(fsl.FOLDERS[folder]), fsl.NAMES_KEPT)
    assert rang(result) == rings
    if rings:
        assert result.long(aes.AES_DOS_RETURN) == addrs.AES_FS_ACTIVE_BELL_RETURN
    else:
        assert result.long(aes.AES_DOS_RETURN) == addrs.AES_FS_ACTIVE_SDTA_RETURN


def test_fs_active_s_hundred_is_of_the_names_it_keeps_not_of_the_entries_it_reads():
    """The 101-file folder under a spec that keeps eleven of its names: the count the search ends on ($fe78fe cmpi.w
    #100,-4(a6)) is of names KEPT — so the directory is read to its end, its last file is among the names, and no bell
    rings. (Under "*.*" kept and read reach a hundred together, and nothing tells them apart.)"""
    result = active(folder_path("BIG", "F?0?.DAT"))
    assert names_of(result) == [b" F%03d.DAT" % number for number in (*range(10), 100)]
    assert not rang(result)
    assert result.long(aes.AES_DOS_RETURN) == addrs.AES_FS_ACTIVE_SDTA_RETURN


# THE FOLDER TEST IS OF ONE BIT ($fe7874 btst #4,21(a0)): a folder that is also read-only ($11) or archived ($30) —
# ordinary disk data, which Fsfirst(..., 16) answers — is a folder all the same: listed with the folders, whatever
# the spec. (The root's read-only FILE tells a test of any bit from a test of this one; these tell a test of the
# whole byte from it.)
ATTRIBUTE_FOLDERS = [b"\x07ARCHIVED", b"\x07LOCKED", b"\x07NORMAL"]


@pytest.mark.parametrize("spec, files", (("*.*", [b" ARFILE.TXT", b" PLAIN.TXT", b" ROFILE.TXT"]), ("*.XYZ", [])),
                         ids=("every name", "a spec that matches no file"))
def test_fs_active_takes_a_folder_by_its_subdir_bit_whatever_other_bit_is_set(spec, files):
    path = folder_path("ATTRS", spec)
    assert {fsl.listed_name(row) for row in fsl.directory(path)} >= set(ATTRIBUTE_FOLDERS + files)
    assert names_of(active(path)) == ATTRIBUTE_FOLDERS + files


# (the spec, the FILES it keeps of MIXED — None where only the differential says)
MIXED_FOLDERS = [b"\x07AUTO", b"\x07TOOLS", b"\x07ZOO"]
SPECS = {
    "*.TXT": [b" AB.TXT", b" README.TXT", b" TEST.TXT"],
    "*.T?T": [b" AB.TXT", b" README.TXT", b" TEST.TXT"],
    "A*.*": [b" A.C", b" AB.TXT", b" ABC.TOS"],
    "*.PRG": [b" LONGNAME.PRG"],
    "READ*.*": [b" READ.ME", b" README.TXT"],
    "?.?": [b" A.C"],
    "*.XYZ": [],
    "*.": None,
    "*": None,
    "NOTES": None,
    "????????.???": None,
    "TEST.TXT": [b" TEST.TXT"],
    "": None,
}


@pytest.mark.parametrize("spec, files", SPECS.items(), ids=[repr(spec) for spec in SPECS])
def test_fs_active_keeps_every_folder_and_the_files_its_spec_matches(spec, files):
    result = active(folder_path("MIXED", spec))
    kept = names_of(result)
    assert kept[:len(MIXED_FOLDERS)] == MIXED_FOLDERS
    if files is not None:
        assert kept[len(MIXED_FOLDERS):] == files


@pytest.mark.parametrize("path", (folder_path("NOWHERE"), "A:\\SUBDIR\\DEEPER\\*.*", "B:\\*.*", "NOSLASH", "A:*.TXT",
                                  "C:\\*.*"),
                         ids=("a missing folder", "a missing folder under a folder", "a second drive",
                              "no separator: the default path", "a drive and a spec", "a drive that is not there"))
def test_fs_active_over_another_path(path):
    active(path)


def test_fs_active_of_a_missing_folder_keeps_nothing():
    result = active(folder_path("NOWHERE"))
    assert result.word(COUNT_AT) == 0 and result.word(aes.AES_DOS_ERR) == 1


def test_fs_active_over_the_shown_cursor():
    """The mouse form changed with the cursor on the screen: gsx_mfset hides and shows it round each."""
    result = active(ROOT_PATH, shown=True)
    assert names_of(result) == fsl.sorted_names(fsl.ROOT)


def test_fs_active_leaves_the_arrow_as_the_mouse_form():
    result = active(ROOT_PATH)
    form = case.long_in(BASE_IMAGE, aes.AES_AD_ARMICE)
    assert result.after(vdi.LINEA_M_POS_HX, 4) == bytes(BASE_IMAGE[form:form + 4])


def test_fs_active_puts_its_pointers_on_the_bus():
    result = active(folder_path("MIXED", "*.TXT"), tags=(0, aes.BUS_TAG, aes.BUS_TAG))
    assert names_of(result)[len(MIXED_FOLDERS):] == SPECS["*.TXT"]


# ORDER. The count is stored BEFORE the sort: laid over the index's first longword (its low word), the sort reads the
# count as the first name's offset; laid over the names block, it lands in a name before the sort copies it out.
def test_fs_active_stores_the_count_before_it_sorts():
    machine, _frame = fsl.entered(ACTIVE, folder_path("TEN"))
    index = case.long_in(make_image(machine), FS["AES_AD_FSINDEX"])
    result = active(folder_path("TEN"), count_at=index + aes.WORD_BYTES)
    assert result.word(index + aes.WORD_BYTES) != 0


def test_fs_active_stores_the_count_into_a_name_it_then_sorts_by():
    machine, _frame = fsl.entered(ACTIVE, folder_path("TEN"))
    names = case.long_in(make_image(machine), FS["AES_AD_FSNAMES"])
    active(folder_path("TEN"), count_at=names + 2)


def test_fs_active_reads_each_block_through_its_global_where_it_uses_it():
    """The count laid over the names block's own pointer (its low word): every name the sort then reaches is the
    one that many bytes further on — the ROM re-reads the pointer, and so does the C."""
    active(folder_path("NINE"), count_at=FS["AES_AD_FSNAMES"] + aes.WORD_BYTES)


# ---- dos_snext and the bell's Cconout, each alone -----------------------------------------------------------------------------
def snext_machine(path):
    """fs_input's run stopped at fs_active's first Fsnext: the search opened, its first entry in the DTA."""
    return fsl.stopped(addrs.AES_ROM_DOS_SNEXT, path).machine


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_dos_snext_finds_the_next_entry(through_line_f):
    result = fsl.run(SNEXT, (), snext_machine(ROOT_PATH), through_line_f=through_line_f)
    assert result.answer() == 1
    assert result.long(aes.AES_TRAP1_RETURN) == addrs.AES_DOS_SNEXT_TRAP_RETURN
    assert (result.word(aes.AES_DOS_ERR), result.word(aes.AES_DOS_AX)) == (0, 0)


def test_dos_snext_past_the_last_entry_answers_no_more_files():
    """The empty folder: `.`, then `..` (the first Fsnext), then nothing — ENMFIL, AES_DOS_AX 18."""
    first = fsl.run(SNEXT, (), snext_machine(folder_path("SUBDIR")))
    assert first.answer() == 1
    last = fsl.run(SNEXT, (), fs_continued(first))
    assert last.answer() == 0
    assert (last.word(aes.AES_DOS_ERR), last.word(aes.AES_DOS_AX)) == (1, sh.GEMDOSIF["DOS_AX_NO_MORE_FILES"])


def fs_continued(result):
    """The machine after `result` (`case.continued`), the GEMDOS machine's own fields staged afresh."""
    return merge_pokes(case.continued(result), fsl.aes_event.savptr_in_the_band())


LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES
BEL = addrs.CON_BEL


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("character", (BEL, ord("A"), 0x0A07), ids=("BEL", "a letter", "a word whose low byte is BEL"))
def test_the_cconout_glue(character, through_line_f):
    """Cconout of the word its caller pushed, through $fe3c28: the caller's return address parked — the run's sentinel,
    or the word after the Line-F caller's call word — and `__DOS`'s own."""
    return_site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    result = fsl.run(CCONOUT, (character,), fsl.stopped(addrs.AES_ROM_FS_ACTIVE + fsl.LINK_BYTES, ROOT_PATH).machine,
                     host_arguments=(return_site,), through_line_f=through_line_f)
    assert result.long(aes.AES_DOS_RETURN) == return_site
    assert result.long(aes.AES_TRAP1_RETURN) == addrs.AES_DOS_TRAP_RETURN
    assert rang(result) == (character & 0xFF == BEL)


# ---- fs_format ------------------------------------------------------------------------------------------------------------------
def fmt(path, top, count=None, *, tree=SELECTOR, pokes=None, **kwargs):
    """fs_format over the machine fs_input's first fs_newdir left for `path`: the list from name `top`, of `count`
    names (the directory's own by default)."""
    made = fsl.listed(path)
    return fsl.run(FORMAT, (tree, top, made.count if count is None else count), made.machine, pokes, **kwargs), made


def formatted(name):
    """A kept name as its row shows it: the kind, then the 8.3 name space-padded to eight with no dot."""
    stem, _dot, extension = name[1:].partition(b".")
    return (name[:1] + stem.ljust(8) + extension) if extension else name


# (the folder, the top): an empty list, one name, a full one, the first page of ten and its last, pages of a hundred.
FORMATS = (("SUBDIR", 0), ("ONE", 0), ("NINE", 0), ("TEN", 0), ("TEN", 1), ("BIG", 0), ("BIG", 50), ("BIG", 91),
           ("MIXED", 0), ("MIXED", 3), ("SORTED", 4))


@pytest.mark.parametrize("folder, top", FORMATS, ids=[f"{folder} from {top}" for folder, top in FORMATS])
def test_fs_format_lays_nine_names_into_the_list(folder, top):
    result, made = fmt(folder_path(folder), top)
    names = fsl.kept_names(made.final, made.count)[top:top + ROWS]
    assert fsl.row_texts(result.final) == [formatted(name) for name in names] + [b" "] * (ROWS - len(names))
    assert result.answer() == FS["FS_FORMAT_ANSWER"]
    for row in range(ROWS):
        assert result.object(SELECTOR, fsl.FIRST_NAME + row)["STATE"] == 0


@pytest.mark.parametrize("folder, top, count", (
    ("TEN", 5, None), ("TEN", 10, None), ("TEN", 12, None), ("TEN", -1, None), ("TEN", 0, 0), ("TEN", 0, -3),
    ("NINE", 0, 10), ("BIG", 95, None), ("BIG", 0, 9), ("BIG", 0, 10), ("BIG", 0, 32767), ("BIG", 30000, 32767),
    ("BIG", -20000, 20000)),
    ids=("a top five from the end: four blank rows", "a top at the count: all blank", "a top past it",
         "a top of -1: the name before the first", "a count of 0", "a negative count", "a count one past the names",
         "a hundred from 95", "a count of 9: the elevator the whole track", "a count of 10: the first that scrolls",
         "a count of 32767", "...from a top of 30000", "a count less a top that wraps the word negative: no names"))
def test_fs_format_over_a_top_or_a_count_off_the_list(folder, top, count):
    fmt(folder_path(folder), top, count)


def test_fs_format_adds_a_row_to_the_top_as_two_longwords():
    """68000 semantics, by argument alone (no caller hands such a top): `movea.w` the row, `adda.w` the top — each
    sign-extended, the sum a LONGWORD. From a top of 32767 the rows' index entries lie 131,068 bytes and on past the
    index, never below it: nine offsets staged there name the directory's last nine names, and the rows show them."""
    made = fsl.listed(folder_path("BIG"))
    index = case.long_in(made.final, FS["AES_AD_FSINDEX"])
    stride = FS["FS_INDEX_ENTRY_BYTES"]
    last_nine = made.final[index + (made.count - ROWS) * stride:index + made.count * stride]
    result, _made = fmt(folder_path("BIG"), TOP_AT_THE_WORD_S_END, COUNT_NINE_PAST_IT,
                        pokes={index + TOP_AT_THE_WORD_S_END * stride: bytes(last_nine)})
    names = fsl.kept_names(made.final, made.count)[-ROWS:]
    assert fsl.row_texts(result.final) == [formatted(name) for name in names]


TOP_AT_THE_WORD_S_END = 0x7FFF
COUNT_NINE_PAST_IT = aes.signed(TOP_AT_THE_WORD_S_END + ROWS)       # the count's word: nine more than the top, wrapped


def elevator(result):
    return result.object(SELECTOR, FS["FS_ELEVATOR"])


def test_fs_format_sizes_the_elevator_to_the_rows_share_of_the_names():
    track = aes.read_object(BASE_IMAGE, SELECTOR, FS["FS_SLIDER"])["HEIGHT"]
    whole, _made = fmt(folder_path("NINE"), 0)
    assert (elevator(whole)["Y"], elevator(whole)["HEIGHT"]) == (0, track)
    ten, _made = fmt(folder_path("TEN"), 1)
    height = ROWS * track // 10
    assert (elevator(ten)["Y"], elevator(ten)["HEIGHT"]) == (track - height, height)


# THE HALF-BOX FLOOR BINDS FOR NO DIRECTORY fs_active can list: at its hundred names the rows' share of the track is
# 9 * 56 / 100 = 5 pixels, half gl_hbox itself (and in high resolution 9 * 112 / 100 = 10 against 9). Only a count past
# the hundred reaches it — fs_format's own argument, which no caller hands it — so the arm is pinned by argument alone.
PAST_THE_NAMES_KEPT = 2 * fsl.NAMES_KEPT


def test_fs_format_keeps_the_elevator_half_a_box_tall():
    half = aes.signed(case.word_in(BASE_IMAGE, aes.AES_GL_HBOX)) // FS["FS_HALF"]
    track = aes.read_object(BASE_IMAGE, SELECTOR, FS["FS_SLIDER"])["HEIGHT"]
    assert ROWS * track // fsl.NAMES_KEPT == half and ROWS * track // PAST_THE_NAMES_KEPT < half
    result, _made = fmt(folder_path("BIG"), PAST_THE_NAMES_KEPT - ROWS, PAST_THE_NAMES_KEPT)
    assert (elevator(result)["HEIGHT"], elevator(result)["Y"]) == (half, track - half)


def test_fs_format_of_nine_names_takes_no_share_of_the_track():
    """Nine names scroll by nothing: the elevator's place would divide by the names past the rows — none. Run in a
    child first, so a C that took the share is a failed assertion here, not a worker dead of the division."""
    made = fsl.listed(folder_path("NINE"))
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_fs_format", made.machine, read_back=False,
        arguments=(("ctypes.c_uint32", hex(SELECTOR)), ("ctypes.c_int16", "0"), ("ctypes.c_int16", str(made.count))))
    assert returncode == 0, stderr
    result, _made = fmt(folder_path("NINE"), 0)
    assert elevator(result)["Y"] == 0


# ORDER, by a row's text laid over what fs_format stores or reads next (its TEDINFO's te_ptext pointed there): a row's
# STATE is cleared after its text is set, and the elevator is sized after every row.
def row_text_at(row, at):
    """Row `row`'s TEDINFO with its text's pointer `at`."""
    return {od.object_long(SELECTOR, fsl.FIRST_NAME + row, "SPEC") + aes.TE_PTEXT: at.to_bytes(aes.LONG_BYTES, "big")}


def test_fs_format_clears_a_row_s_state_after_its_text_is_set():
    """The first row's text ending on its own object's state word (its 'T' and its NUL): cleared after, the state is 0."""
    made = fsl.listed(folder_path("TEN"))
    text = formatted(fsl.kept_names(made.final, made.count)[0]) + NUL
    state_at = SELECTOR + fsl.FIRST_NAME * aes.OB_BYTES + aes.OB_STATE
    result, _made = fmt(folder_path("TEN"), 0, pokes=row_text_at(0, state_at + aes.WORD_BYTES - len(text)))
    assert result.word(state_at) == 0 and text[-aes.WORD_BYTES:] != bytes(aes.WORD_BYTES)


def test_fs_format_sizes_the_elevator_after_the_rows():
    """The last row's text laid over the slider's height: the track the elevator is sized by is the text's first two
    bytes, not the height the tree held."""
    made = fsl.listed(folder_path("TEN"))
    height_at = SELECTOR + FS["FS_SLIDER"] * aes.OB_BYTES + aes.OB_HEIGHT
    result, _made = fmt(folder_path("TEN"), 1, pokes=row_text_at(ROWS - 1, height_at))
    track = aes.signed(result.word(height_at))
    assert track == int.from_bytes(formatted(fsl.kept_names(made.final, made.count)[ROWS])[:aes.WORD_BYTES], "big")
    assert abs(elevator(result)["HEIGHT"] - ROWS * track / made.count) <= 1          # mul_div rounds


def test_fs_format_clears_a_selected_row_s_state():
    selected = aes.object_pokes(SELECTOR, fsl.FIRST_NAME + 2, STATE=SELECTED)
    result, _made = fmt(folder_path("TEN"), 0, pokes=selected)
    assert result.object(SELECTOR, fsl.FIRST_NAME + 2)["STATE"] == 0


def test_fs_format_puts_the_tree_on_the_bus():
    result, made = fmt(folder_path("TEN"), 1, tree=SELECTOR | aes.BUS_TAG)
    assert fsl.row_texts(result.final)[0] == formatted(fsl.kept_names(made.final, made.count)[1])


@pytest.mark.parametrize("path", (ROOT_PATH, folder_path("BIG"), folder_path("SUBDIR")), ids=lambda path: path)
def test_fs_format_as_fs_newdir_calls_it(path):
    machine, frame = fsl.entered(FORMAT, path)
    fsl.run(FORMAT, (frame(fsl.FORMAT_TREE), frame.word(fsl.FORMAT_TOP), frame.word(fsl.FORMAT_COUNT)), machine)


def test_fs_format_through_its_call_word():
    fmt(folder_path("TEN"), 1, through_line_f=True)


# ---- fs_sel ------------------------------------------------------------------------------------------------------------------------
def sel(row, state, machine=None, **kwargs):
    machine = fsl.listed(folder_path("TEN")).machine if machine is None else machine
    return fsl.run(SEL, (row, state), machine, **kwargs)


@pytest.mark.parametrize("row", range(1, ROWS + 1), ids=lambda row: f"row {row}")
def test_fs_sel_selects_a_row_and_draws_it(row):
    result = sel(row, SELECTED)
    assert result.object(SELECTOR, fsl.FIRST_NAME + row - 1)["STATE"] == SELECTED
    assert screen_changed(result)


def test_fs_sel_of_row_0_does_nothing():
    assert aes.stored_nothing(sel(0, SELECTED))


def test_fs_sel_deselects_a_selected_row():
    selected = sel(3, SELECTED)
    result = sel(3, 0, fs_continued(selected))
    assert result.object(SELECTOR, fsl.FIRST_NAME + 2)["STATE"] == 0


# ...the last a row whose LOW BYTE alone is 0: `tst.w 8(a6)` ($fe7b74) tests the word, so it is a row — an object far
# past the tree, which ob_change changes all the same.
ROW_0_IN_THE_LOW_BYTE_ALONE = 0x0100


@pytest.mark.parametrize("row, state", ((4, 0), (-1, SELECTED), (10, SELECTED), (2, SELECTED | od.STATE_BITS["CHECKED"]),
                                        (ROW_0_IN_THE_LOW_BYTE_ALONE, SELECTED)),
                         ids=("the state a row already has: nothing drawn", "row -1: the slider", "row 10: OK",
                              "two bits at once", "a row of $0100: the row is a WORD, and this one is not row 0"))
def test_fs_sel_over_another_row_or_state(row, state):
    sel(row, state)


def test_fs_sel_of_a_row_whose_low_byte_alone_is_0_stores():
    assert not aes.stored_nothing(sel(ROW_0_IN_THE_LOW_BYTE_ALONE, SELECTED))


def test_fs_sel_reads_the_tree_from_ad_fstree():
    """ad_fstree named another tree — an application's copy of the selector, in the tree band: that one's row changes."""
    copy = {aes.TREE_AT: bytes(BASE_IMAGE[SELECTOR:SELECTOR + aes.tree_length(SELECTOR) * aes.OB_BYTES])}
    machine = merge_pokes(fsl.listed(folder_path("TEN")).machine, copy, {FS["AES_AD_FSTREE"]: aes.TREE_AT.to_bytes(4, "big")})
    result = sel(2, SELECTED, machine)
    assert result.object(aes.TREE_AT, fsl.FIRST_NAME + 1)["STATE"] == SELECTED
    assert result.object(SELECTOR, fsl.FIRST_NAME + 1)["STATE"] == 0


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_fs_sel_as_fs_input_first_calls_it(through_line_f):
    """fs_input's own first call, before its first directory: row 0, nothing selected."""
    machine, frame = fsl.entered(SEL, ROOT_PATH)
    row, state = frame.word(fsl.SEL_ROW), frame.word(fsl.SEL_STATE)
    assert row == 0
    assert aes.stored_nothing(fsl.run(SEL, (row, state), machine, through_line_f=through_line_f))


def test_fs_sel_over_the_shown_cursor():
    result = sel(5, SELECTED, fsl.listed(folder_path("TEN"), shown=True).machine)
    assert result.object(SELECTOR, fsl.FIRST_NAME + 4)["STATE"] == SELECTED


# ---- fs_nscroll -----------------------------------------------------------------------------------------------------------------
def nscroll(folder, top, arrow, rows, *, row=0, shown=False, machine=None, tags=(0, 0), **kwargs):
    """fs_nscroll as fs_input's loop calls it over the listed `folder`: from `top`, `rows` rows by `arrow`, the
    selected row's word (`row`) moved out of fs_input's frame."""
    made = fsl.listed(folder_path(folder), shown=shown)
    return fsl.run(NSCROLL, (SELECTOR | tags[0], ROW_AT | tags[1], top, made.count, arrow, rows),
                   made.machine if machine is None else machine, {ROW_AT: vdi.pack_words(row)}, **kwargs)


def scrolled_to(folder, top):
    """The listed `folder` scrolled down to `top` by the ROM's own fs_nscroll — its list, its screen, its elevator."""
    if top == 0:
        return fsl.listed(folder_path(folder)).machine
    return fs_continued(nscroll(folder, 0, DOWN, top))


# (the folder, the top it starts from, the arrow, the rows, the top it answers)
SCROLLS = {
    "one row down": ("TEN", 0, DOWN, 1, 1),
    "down at the last page: nothing moves": ("TEN", 1, DOWN, 1, 1),
    "one row up": ("TEN", 1, UP, 1, 0),
    "up at the top: nothing moves": ("TEN", 0, UP, 1, 0),
    "nine names: never moves": ("NINE", 0, DOWN, 1, 0),
    "an empty list": ("SUBDIR", 0, DOWN, 1, 0),
    "a page down: nine rows, nothing copied": ("BIG", 0, DOWN, 9, 9),
    "eight rows down: one row copied": ("BIG", 0, DOWN, 8, 8),
    "two rows down": ("BIG", 20, DOWN, 2, 22),
    "a page up": ("BIG", 50, UP, 9, 41),
    "eight rows up": ("BIG", 50, UP, 8, 42),
    "three rows up": ("BIG", 50, UP, 3, 47),
    "a page down cut short by the list's end": ("BIG", 88, DOWN, 9, 91),
    "a page up cut short by its start": ("BIG", 4, UP, 9, 0),
    "the slider dragged far down": ("BIG", 0, DOWN, 60, 60),
    "...and far up": ("BIG", 70, UP, 45, 25),
    "no rows asked": ("BIG", 20, DOWN, 0, 20),
    "a negative count of rows": ("BIG", 20, DOWN, -2, 20),
    "folders and files": ("MIXED", 0, DOWN, 2, 2),
    "folders and files, back up: rows of unlike extensions copied down": ("MIXED", 3, UP, 2, 1),
}


@pytest.mark.parametrize("folder, top, arrow, rows, answer", SCROLLS.values(), ids=SCROLLS)
def test_fs_nscroll(folder, top, arrow, rows, answer):
    result = nscroll(folder, top, arrow, rows, machine=scrolled_to(folder, top))
    assert result.answer() == answer
    made = fsl.listed(folder_path(folder))
    names = fsl.kept_names(made.final, made.count)[answer:answer + ROWS]
    if answer != top:
        assert fsl.row_texts(result.final) == [formatted(name) for name in names] + [b" "] * (ROWS - len(names))
    else:
        assert aes.stored_nothing(result)


@pytest.mark.parametrize("row", (1, 5, 9), ids=lambda row: f"row {row} selected")
def test_fs_nscroll_deselects_and_forgets_the_selected_row(row):
    selected = fs_continued(sel(row, SELECTED, fsl.listed(folder_path("BIG")).machine))
    result = nscroll("BIG", 0, DOWN, 1, row=row, machine=selected)
    assert result.word(ROW_AT) == 0
    assert all(result.object(SELECTOR, fsl.FIRST_NAME + index)["STATE"] == 0 for index in range(ROWS))


def test_fs_nscroll_that_does_not_move_keeps_the_selected_row():
    selected = fs_continued(sel(2, SELECTED, fsl.listed(folder_path("TEN")).machine))
    result = nscroll("TEN", 0, UP, 1, row=2, machine=selected)
    assert result.word(ROW_AT) == 2 and result.object(SELECTOR, fsl.FIRST_NAME + 1)["STATE"] == SELECTED


def test_fs_nscroll_puts_its_pointers_on_the_bus():
    result = nscroll("BIG", 0, DOWN, 3, row=4, tags=(aes.BUS_TAG, aes.BUS_TAG))
    assert result.answer() == 3 and result.word(ROW_AT) == 0


@pytest.mark.parametrize("arrow, rows", ((DOWN, 1), (DOWN, 9), (UP, 4)), ids=("a row down", "a page down", "four up"))
def test_fs_nscroll_over_the_shown_cursor(arrow, rows):
    top = 0 if arrow == DOWN else 30
    machine = fsl.listed(folder_path("BIG"), shown=True).machine
    if top:
        machine = fs_continued(nscroll("BIG", 0, DOWN, top, shown=True))
    nscroll("BIG", top, arrow, rows, shown=True, machine=machine)


def test_fs_nscroll_through_its_call_word():
    assert nscroll("BIG", 0, DOWN, 2, through_line_f=True).answer() == 2


def test_fs_nscroll_draws_under_the_clip_it_found_and_puts_it_back():
    """The caller's clip narrowed to the list's left half by the ROM's own gsx_sclip first: the rows are drawn under
    their own clip, the slider under the caller's — and the caller's is what is left set."""
    made = fsl.listed(folder_path("BIG"))
    image = make_image(made.machine)
    box = aes.read_object(image, SELECTOR, FS["FS_FILE_BOX"])
    half = (*screen_origin(image, SELECTOR, FS["FS_FILE_BOX"]), box["WIDTH"] // 2, box["HEIGHT"])
    clipped = od.clip_set_by_the_rom(aes.RECTS_AT, merge_pokes(made.machine, {aes.RECTS_AT: vdi.pack_words(*half)}))
    result = nscroll("BIG", 0, DOWN, 2, machine=merge_pokes(clipped, fsl.aes_event.savptr_in_the_band()))
    assert tuple(result.field("AES", name) for name in ("GL_XCLIP", "GL_YCLIP", "GL_WCLIP", "GL_HCLIP")) == half


# ---- fs_newdir --------------------------------------------------------------------------------------------------------------------
def newdir(path, *, shown=False, tags=(0,) * 5, **kwargs):
    """fs_newdir as fs_input first calls it over `path`: its own title, path, spec and tree, the count moved out of
    fs_input's frame."""
    machine, frame = fsl.entered(NEWDIR, path, shown=shown)
    arguments = tuple(value | tag for value, tag in zip(fsl.newdir_arguments(frame), tags))
    return fsl.run(NEWDIR, arguments, machine, **kwargs), frame


NEWDIRS = (ROOT_PATH, folder_path("SUBDIR"), folder_path("ONE"), folder_path("TEN"), folder_path("BIG"),
           folder_path("MIXED", "*.T?T"), folder_path("REVERSE"), folder_path("NOWHERE"), "NOSLASH")


@pytest.mark.parametrize("path", NEWDIRS, ids=lambda path: path)
def test_fs_newdir_reads_lists_and_draws_a_directory(path):
    result, frame = newdir(path)
    count = aes.signed(result.word(COUNT_AT))
    names = fsl.kept_names(result.final, count)[:ROWS]
    assert fsl.row_texts(result.final) == [formatted(name) for name in names] + [b" "] * (ROWS - len(names))
    spec = text_at(result, frame(fsl.NEWDIR_SPEC))
    assert text_at(result, frame(fsl.NEWDIR_TITLE)) == b" " + spec + b" "


def test_fs_newdir_over_the_shown_cursor():
    newdir(folder_path("TEN"), shown=True)


def test_fs_newdir_puts_its_pointers_on_the_bus():
    """The title, the spec, the tree and the count each with a top byte (the path is GEMDOS's own to read)."""
    result, _frame = newdir(folder_path("TEN"), tags=(aes.BUS_TAG, 0, aes.BUS_TAG, aes.BUS_TAG, aes.BUS_TAG))
    assert result.word(COUNT_AT) == 10


# A ROM DEFECT, reproduced byte for byte: THE TITLE IS BUILT WITH NO BOUND in a scratch 40 bytes below gl_mntree. " " +
# the spec + " " + its NUL fits up to a spec of 37 characters; one or two more put the NUL, then the space, on
# gl_mntree's top byte (which a 24-bit bus never reads; the NUL after it falls on a byte that is 0), and from 40
# characters the menu bar's tree pointer itself is text — then gl_rzero behind it, which every caller of the "no clip"
# rectangle reads. An application's fsel_input path is all it takes: the user's own
# typing is held to the path field's template.
LONGEST_SPEC_THAT_FITS = fsl.TEXT_ROOM - len(b"  ") - 1
SNAPSHOT_MNTREE = case.long_in(BASE_IMAGE, aes.AES_GL_MNTREE)
RZERO = bytes(aes.GRECT_BYTES)


@pytest.mark.parametrize("characters, mntree_kept, rzero_kept", (
    (LONGEST_SPEC_THAT_FITS, True, True), (LONGEST_SPEC_THAT_FITS + 1, True, True),
    (LONGEST_SPEC_THAT_FITS + 2, True, True), (LONGEST_SPEC_THAT_FITS + 3, False, True),
    (fsl.TEXT_ROOM + 20, False, False)),
    ids=("the longest spec that fits", "one more: a NUL the bus never reads", "two more: a space there",
         "three more: the menu tree's pointer", "sixty: gl_rzero too"))
def test_fs_newdir_writes_a_long_spec_s_title_over_the_globals_after_its_scratch(characters, mntree_kept, rzero_kept):
    result, _frame = newdir("A:\\" + "?" * characters)
    assert (result.long(aes.AES_GL_MNTREE) & OS_BUS_ADDR_MASK == SNAPSHOT_MNTREE) == mntree_kept
    assert (result.after(aes.AES_GL_RZERO, aes.GRECT_BYTES) == RZERO) == rzero_kept


def test_fs_newdir_through_its_call_word():
    newdir(folder_path("ONE"), through_line_f=True)


# ---- the budgets ------------------------------------------------------------------------------------------------------------------
def test_the_budgets_cover_the_longest_runs():
    """The deepest prefix (fs_input to its first fs_newdir's return, over the 101-name folder, the cursor shown) and
    the longest case (fs_newdir of it): the prefix's DECLARED budget admits that measure by the derivations' margin
    and is no more than the declaration a run of it may make (`aes_event`'s two bounds); the case's is its measure
    times its margin."""
    assert fsl.listed(folder_path("BIG"), shown=True).insns == fsl.PREFIX_MEASURED_INSNS
    least = fsl.PREFIX_MEASURED_INSNS * aes_event.DERIVATION_MARGIN
    assert aes_event.DERIVATION_INSNS < least <= fsl.PREFIX_BUDGET <= least * aes_event.DERIVATION_STALE
    result, _frame = newdir(folder_path("BIG"), shown=True)
    assert result.info["regs"]["ninsns"] == fsl.RUN_MEASURED_INSNS


def test_a_prefix_past_its_declared_budget_s_margin_is_refused_by_name(monkeypatch):
    """RED: the deepest prefix under a declared budget one instruction short of its margin."""
    monkeypatch.setattr(fsl, "PREFIX_BUDGET", fsl.PREFIX_MEASURED_INSNS * aes_event.DERIVATION_MARGIN - 1)
    with pytest.raises(AssertionError, match=r"inside its declared budget's \(\d+\) margin of 5: raise the row's budget"):
        fsl.stopped.__wrapped__(addrs.AES_FS_INPUT_NEWDIR_RETURN, folder_path("BIG"), "", True)


def test_a_prefix_that_never_reaches_its_stop_is_refused_by_name():
    """...and a stop the run never reaches — fs_input with no memory returns before any fs_newdir."""
    with pytest.raises(AssertionError, match="never reached"):
        aes_event.stopped_at(make_image(aes.staged(fsl.INPUT, fsl.ARGUMENTS, fsl.exhausted(fsl.fs_input_machine(ROOT_PATH)))),
                             addrs.AES_ROM_FS_INPUT, addrs.AES_FS_INPUT_NEWDIR_RETURN)
