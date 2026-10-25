r"""THE HANDS' CAMPAIGN ON THE ROM'S MACHINE (band 6 wave 0, slice H) — `test/aes_desk.py`, and what `aes_boot.py` and
`tools/accessory_disk.py` gained for it, held.

NOTHING OF OURS RUNS IN THIS BATTERY: every machine is one the ROM booted, with no blob in it, so no test here says
"ours ran". What is held is THE ROM-SIDE CAMPAIGN band 6's rows are arrivals of:

  * EACH CHAIN'S IDLE (`test_the_chain_ends_at_the_rom_s_idle_having_done_what_its_name_says`, a case a chain — so the
    campaign shards over xdist's workers): every step ends where it says (the ROM's dispatcher's idle, or its named
    stop), the chain's own steps ENTER THE ACT'S OWN ROUTINE (read off the cycle profile — never off the chain's
    name), and where the act leaves something on the machine or the disk, it is there;
  * THE REACH TABLE (`aes_desk.reach`: routine <- chains) as a derivation, its union held;
  * THE STACKS' DEPTHS PER CHAIN OFF THE WRITE LEDGERS, the deepest of each held with its chain;
  * THE TWO ACTS THAT WAIT WITHOUT IDLING — a file shown, a rubber box — reached by A RECEPTION AT A NAMED STOP, the
    stops held to the ROM's bytes and `continued`'s two new arguments to their refusals;
  * THE FOLDER CHAIN, MENDED — and why it was broken: THE ORACLE'S CPU EXECUTED `$F620..$F627` AS THE 68040's MOVE16
    where a 68000 takes a Line-F exception, until the kit's fix (band 6 slice M16: `recreate_kit/oracle/move16_guard.c`,
    held over every `$Fxxx` word by the kit's `test/test_line_f.py`). Held here: the two words of the ROM it bit, the
    chains that pass them (the CPU's own exception, read off the cycle profile), and New Folder making its folder;
  * THE FIFTH CAPTURE'S DISK (files, the folder AUTO with a file in it, a program) and its machine.

MEASURED NUMBERS ARE THE ROM'S OVER THESE HANDS AND THESE DISKS: a count below is pinned where the ROM, the disk and
the chain decide it (a routine entered, a stack's lowest store) and nowhere a capture's phase does.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu

import st_build

import accessory_disk
import aes
import aes_boot
import aes_desk as desk
import aes_objects
import case
from aes_boot import Refused

BUS, WORD_BYTES = aes_boot.BUS, aes.WORD_BYTES
THE_ROM_S = aes_boot.THE_ROM_S
ROM = bytes(BASE_IMAGE[emu.ROM_BASE:emu.ROM_END])


def rom_words(at, count):
    return struct.unpack_from(f">{count}H", ROM, at - emu.ROM_BASE)


# ---- BAND 6'S ROUTINES ------------------------------------------------------------------------------------------------------------------
BAND_6_ROUTINES = 244                   # the design's §1


def test_band_6_s_routines_are_the_desk_s_ranges_and_its_leaves_less_the_seven_owned():
    """244 routines, each a start the AES map's inventory lists: the two ranges, the seventeen leaves filed in AES
    modules, less the seven bands 0-5 own — every one of which IS a start inside the ranges (a leaf or an owned
    routine that named no start would move the count without a word)."""
    starts, routines = set(desk.inventoried()), desk.routines()
    in_a_range = lambda at: any(lo <= at < hi for lo, hi in (desk.DESK_TEXT, desk.UTILITY_TEXT))        # noqa: E731
    assert len(routines) == BAND_6_ROUTINES == len(set(routines)) and list(routines) == sorted(routines)
    assert set(desk.DESK_LEAVES_IN_AES_MODULES) <= starts and not any(map(in_a_range, desk.DESK_LEAVES_IN_AES_MODULES))
    assert set(desk.OWNED_BY_BANDS_0_TO_5) <= starts and all(map(in_a_range, desk.OWNED_BY_BANDS_0_TO_5))
    assert not set(routines) & set(desk.OWNED_BY_BANDS_0_TO_5)
    assert {desk.SHOW_INFO, desk.MAKE_FOLDER, desk.ICON_DRAG, desk.COPY_ENGINE, desk.DIALOG_RUNNER, desk.OPEN_SELECTION,
            desk.DO_FORMAT, desk.INF_WRITE, desk.SHOW_FILE, addrs.AES_ROM_DESK_USERDEF} <= set(routines)


# ---- THE TWO WORDS THE ORACLE'S MOVE16 BIT (fixed in the kit, band 6 slice M16) --------------------------------------------------------
# The kit's CPU executed `$F620..$F627` as the 68040's MOVE16 (upstream Musashi's handler asks no CPU type); it takes
# the Line-F exception there now, as a 68000 does (`recreate_kit/test/test_line_f.py`, every `$Fxxx` word).
FORMER_MOVE16_WORDS = range(0xf620, 0xf628)
FILE_MENU_HANDLER = (0xfe1e80, 0xfe1f2a)
THE_TWO_WORDS = {0xfe1ec2: (0xf620, desk.SHOW_INFO), 0xfe1ece: (0xf624, desk.MAKE_FOLDER)}


def test_the_rom_holds_two_such_words_both_call_words_of_the_file_menu_s_handler():
    """FOUND BY THE SCAN, held to the ROM: the whole image holds a word of `$F620..$F627` at two even addresses and no
    other — the File menu handler's calls of Show Info and of New Folder, by the Line-F table's own entries."""
    everywhere = [at for at in range(emu.ROM_BASE, emu.ROM_END, WORD_BYTES) if case.word_in(BASE_IMAGE, at) in FORMER_MOVE16_WORDS]
    assert tuple(everywhere) == tuple(THE_TWO_WORDS)
    for at, (word, routine) in THE_TWO_WORDS.items():
        assert FILE_MENU_HANDLER[0] <= at < FILE_MENU_HANDLER[1]
        assert case.word_in(BASE_IMAGE, at) == word and aes.line_f_target(word) == routine


# THE CPU'S FRAME AT SHOW INFO'S WORD IS IN THE RUN'S LEDGER (reviewer B's test, band 6 wave 0's review, over the stand-in
# then). Entered from its top the File-menu handler makes a Line-F call of its own (`$fe1e90`) at the same stack pointer,
# whose frame ledgers the same six bytes in the same step. A continuation that BEGINS INSIDE the handler, past that
# call, has no such frame: the six bytes changed there are the exception's at Show Info's word, and the ledger holds them.
SHOW_INFO_ARM = 0xfe1ebc                # the File-menu handler's Show Info arm: `tst.w d6`, six bytes before its call word
LINE_F_FRAME_BYTES = 6                  # a 68000's group-1/2 frame: the status word, the PC (the Line-F word's own address)


def test_a_continuation_from_inside_the_file_menu_handler_ledgers_the_whole_frame_the_cpu_pushed():
    machine = desk.walked("drive A: selected").machine
    *to_the_menu, the_click = desk.item("File", "Show Info...")
    for step in to_the_menu:
        machine = aes_boot.Machine(desk.stepped(machine.boot, tuple(step.hand(machine))).boot)
    at_the_arm = aes_boot.continued.derive(machine.boot, tuple(the_click.hand(machine)), aes_boot.CONTINUED_INSNS, SHOW_INFO_ARM, None)
    assert at_the_arm.idle is None and at_the_arm.registers["pc"] & BUS == SHOW_INFO_ARM
    boot = aes_boot.continued.derive(at_the_arm, (), aes_boot.CONTINUED_INSNS, desk.SHOW_INFO, SHOW_INFO_ARM)
    assert boot.registers["pc"] & BUS == desk.SHOW_INFO
    assert boot.observed == ()
    frame_at = boot.registers["isp"] - WORD_BYTES   # the handler popped the six bytes and pushed its return, a long
    assert at_the_arm.registers["isp"] - LINE_F_FRAME_BYTES == frame_at
    changed = {at for at in range(frame_at, frame_at + LINE_F_FRAME_BYTES) if boot.ram[at] != at_the_arm.ram[at]}
    ledgered = {at for start, length in boot.stored for at in range(start, start + length)}
    assert changed and changed <= ledgered, f"bytes {sorted(map(hex, changed - ledgered))} of the CPU's frame changed and are in no ledger"


# ---- THE NAMED STOPS, AND `continued`'s TWO NEW ARGUMENTS --------------------------------------------------------------------------------
PUSH_255, CRAWIO_BY_LINE_F, DROP_THE_WORD, TEST_D0, BACK_TO_THE_PUSH = 0x3f3c, 0xf184, 0x548f, 0x4a40, 0x67f4
CRAWIO_GLUE = 0xfe3bfa                  # the DOS glue's entry for GEMDOS 6 (Crawio)
VIEWER_STOPS = (desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_THE_FILE_S_END)


@pytest.mark.parametrize("stop", VIEWER_STOPS)
def test_a_viewer_s_stop_is_the_first_instruction_of_its_own_key_poll(stop):
    """`move.w #$ff,-(sp)`; Crawio by its Line-F word; the word dropped; `tst.w d0`; `beq` BACK TO THE PUSH: the loop
    turns until a key comes, and the stop is its first instruction."""
    at = desk.STOPS[stop]
    assert rom_words(at, 6) == (PUSH_255, 0x00ff, CRAWIO_BY_LINE_F, DROP_THE_WORD, TEST_D0, BACK_TO_THE_PUSH)
    assert aes.line_f_target(CRAWIO_BY_LINE_F) == CRAWIO_GLUE and desk.UTILITY_TEXT[0] <= at < desk.UTILITY_TEXT[1]
    branch_at = at + 5 * WORD_BYTES
    assert branch_at + WORD_BYTES + struct.unpack(">b", bytes((BACK_TO_THE_PUSH & aes.BYTE_MASK,)))[0] == at


VIEWER_PAGE_COUNT_AT = addrs.AES_ROM_DESK_VIEWER_PAGE    # the viewer's page loop: its line counter loaded
MOVEQ_TO_D6 = 0x7c00                    # `moveq #n,d6`, the count in the low byte


def test_the_page_prompt_s_lines_are_the_disk_s_own_constant():
    """`moveq #21,d6` and a `dbf`: twenty-two lines a page — what the long file is longer than."""
    assert rom_words(VIEWER_PAGE_COUNT_AT, 1) == (MOVEQ_TO_D6 | accessory_disk.VIEWER_PAGE_LINES - 1,)
    assert accessory_disk.README.count(b"\r\n") == accessory_disk.README_LINES > 2 * accessory_disk.VIEWER_PAGE_LINES


THE_BOX, THE_SHOW = "a rubber box on the desktop, round the trash", "file: shown, a key at its end"


def test_the_rubber_box_s_poll_is_gr_stilldn_and_the_run_stands_there_twice_before_its_idle():
    """The chain's three steps: stopped at gr_stilldn's entry, at no idle, with the mask the MFP's interrupts pass —
    twice — and then the ROM's idle."""
    first, second, last = desk.walked(THE_BOX).steps
    stop = desk.STOPS[desk.RUBBER_BOX_POLL]
    assert stop == addrs.AES_ROM_GR_STILLDN
    for stepped in (first, second):
        registers = stepped.boot.registers
        assert stepped.boot.idle is None and registers["pc"] & BUS == stop
        assert registers["sr"] & aes_boot.SR_SUPERVISOR and (registers["sr"] & addrs.SR_IPL_MASK) >> aes_boot.SR_IPL_SHIFT < aes_boot.MFP_LEVEL
    assert last.boot.idle == THE_ROM_S


def test_what_continued_refuses_of_a_named_stop_each_by_name():
    """A boot at its idle continued `at` a stop; a stopped boot continued from no stop, or from another; and an idle
    met before `until`."""
    idle, stopped = aes_boot.inf_machine().boot, desk.walked(THE_BOX).steps[0].boot
    stop = desk.STOPS[desk.RUBBER_BOX_POLL]
    with pytest.raises(Refused, match=f"the idle of the ROM's dispatcher — not at {stop:#x}"):
        aes_boot.continued(idle, (), at=stop)
    with pytest.raises(Refused, match="stopped before its first idle is continued by nothing"):
        aes_boot.continued(stopped, ())
    with pytest.raises(Refused, match=f"this one stands at {stop:#x} — not at {stop + WORD_BYTES:#x}"):
        aes_boot.continued(stopped, (), at=stop + WORD_BYTES)
    with pytest.raises(Refused, match=f"reached its first idle and never arrived at {desk.STOPS[desk.VIEWER_AT_A_PAGE_S_END]:#x}"):
        aes_boot.continued(idle, (aes_boot.mouse_to(*desk.icon_point(aes_boot.inf_machine(), desk.THE_TRASH)),),
                           until=desk.STOPS[desk.VIEWER_AT_A_PAGE_S_END])


def test_a_step_with_no_reception_is_profiled_to_the_cycle():
    """The profile's three parts are THE RUN: from the box's poll to its next arrival there with nothing received,
    the GEM text's cycles, the OS's and the Line-F copy's sum to the run's own count — and the poll's own entry ran."""
    stopped, stop = desk.walked(THE_BOX).steps[0].boot, desk.STOPS[desk.RUBBER_BOX_POLL]
    again = desk.stepped(stopped, (), stop, stop)
    profile = again.profile
    assert sum(cycles for _pc, cycles in profile.text) + profile.os + profile.line_f == again.boot.cycles > 0
    assert profile.os > 0 and profile.line_f > 0 and stop in desk.cycles_at(profile)
    assert all(aes.AES_TEXT[0] <= pc < aes.AES_TEXT[1] and cycles for pc, cycles in profile.text)


def test_a_machine_with_a_forged_our_boot_label_is_refused_the_campaign():
    """NOTHING OF OURS RUNS HERE: a `Boot` that says it holds a blob — an our-boot's label, the blob any object — is
    refused before a run is made (asked of the derivation itself: such a `Boot` is no question a kept answer reads)."""
    boot = aes_boot.inf_machine().boot
    labelled = boot._replace(our_boot=aes_boot.OurBoot("a blob", None, (1, 0, 0)))
    with pytest.raises(Refused, match="THE ROM'S MACHINE'S: this one holds a blob"):
        desk.stepped.derive(labelled, ())


# ---- POINTS: what a hand is refused ----------------------------------------------------------------------------------------------------
def test_a_point_is_refused_where_the_machine_s_trees_do_not_show_one_thing_to_point_at():
    """No such item; an item the menu holds DISABLED (File > Open with nothing selected); two icons that read alike
    (the two drives); a drive the desk has no icon for; and AN ICON OUT OF SIGHT — every point of drive A:'s image
    under the window made full. AN ICON PARTLY IN SIGHT IS POINTED AT WHERE IT SHOWS: drive A:'s, its centre under
    its own window's closer, left of that window; the files disk's fourth item, its centre under the window's scroll
    bar, inside the work area."""
    idle, window = aes_boot.inf_machine(), desk.walked("files: A: opened").machine
    with pytest.raises(Refused, match="holds 0 titles or items that read 'No Such Item'"):
        desk.menu_point(idle, "No Such Item")
    with pytest.raises(Refused, match="the menu's 'Open' is DISABLED on this machine"):
        desk.menu_point(idle, "Open")
    assert desk.menu_point(desk.walked("drive A: selected").machine, "Open")
    with pytest.raises(Refused, match="shows 2 icons that are named 'FLOPPY DISK'"):
        desk.icon_point(idle, "FLOPPY DISK")
    with pytest.raises(Refused, match="shows 0 icons that are drive C:'s"):
        desk.drive_point(idle, "C")
    with pytest.raises(Refused, match="the icon 'drive A:' is not in sight"):
        desk.drive_point(desk.walked("files: the window made full").machine, "A")
    centre, shown = desk.drive_point(idle, "A"), desk.drive_point(window, "A")
    its_window, = desk.windows(window)
    assert aes_objects.inside(*centre, its_window) and not aes_objects.inside(*shown, its_window) and shown[1] == centre[1]
    tree, program = desk.desk_tree(window), desk.icon_index(window, desk.THE_PROGRAM)
    work_area = desk.box(window.ram, tree, aes_objects.parent_by_climbing(tree, program, window.ram))
    clipped = desk.icon_point(window, desk.THE_PROGRAM)
    assert aes_objects.inside(*clipped, work_area) and not aes_objects.inside(clipped[0] + desk.ICON_IMAGE_HALF, clipped[1], work_area)
    whole = desk.icon_point(window, desk.THE_README)      # ...where its neighbour, whole in the work area, is taken at its centre
    assert whole[1] == clipped[1] and aes_objects.inside(whole[0] + desk.ICON_IMAGE_HALF - 1, whole[1], work_area)
    with pytest.raises(Refused, match="no window is on top on this machine"):
        desk.top_window(idle)


REMOVE_A_DRIVE = "A: Options > Install Disk Drive, Remove pressed"
STEPS_TO_THE_DIALOG = 3                 # the bar's title, the item, the click: the dialog is up after them
TAKEN_OUT_OF_THE_INSTALL_DIALOG = 4     # the objects of its tree the desk unlinks for a disk drive (an icon's type boxes)


def test_a_dialog_s_button_is_found_under_the_tree_the_desk_runs_and_not_under_the_nearest_object_with_no_next():
    """THE INSTALL DISK DRIVE DIALOG'S TREE HOLDS OBJECTS THE DESK TOOK OUT OF IT — four, each left with no next,
    between its fields and its three buttons. The nearest object below `Remove` with no next is one of those: a root
    nobody runs, and the search that took it found "0 dialogs" (the second review's finding 1). The button is found
    under THE ROOT THE DESK'S STACK HOLDS, which shows it: `Install`, `Remove` and `Cancel` are three points of one
    row, left to right. And a button no dialog that is up shows is refused still."""
    chain = desk.CHAINS[REMOVE_A_DRIVE]
    machine = desk.walked(chain.after).machine
    for step in chain.steps[:STEPS_TO_THE_DIALOG]:
        machine = aes_boot.Machine(desk.stepped(machine.boot, tuple(step.hand(machine)), None, None, step.budget).boot)
    tree, remove = desk.dialog_button(machine, "Remove")
    no_next = [index for index in range(1, remove) if aes_objects.object_word(machine.ram, tree, index, "NEXT") == aes.OB_NIL]
    assert len(no_next) == TAKEN_OUT_OF_THE_INSTALL_DIALOG and remove - 1 not in no_next and remove - 2 in no_next, (
        "the walk down from Remove passes Install and stops at an object the desk took out")
    assert not set(no_next) & set(aes_objects.children_of(machine.ram, tree, aes.OB_ROOT))
    (install_x, row), (remove_x, remove_y), (cancel_x, cancel_y) = (desk.button_point(machine, text) for text in ("Install", "Remove", "Cancel"))
    assert row == remove_y == cancel_y and install_x < remove_x < cancel_x
    assert {desk.dialog_button(machine, text)[0] for text in ("Install", "Cancel")} == {tree}
    with pytest.raises(Refused, match="0 dialogs that are up on this machine hold a button reading 'Read-Only'"):
        desk.button_point(machine, "Read-Only")


# ---- THE CAMPAIGN: a case a chain ----------------------------------------------------------------------------------------------------------
ROOT_AT = (st_build.RESERVED_SECTORS + st_build.FAT_COPIES * st_build.SECTORS_PER_FAT) * st_build.SECTOR_BYTES


def root_of(disk):
    """`{the eleven bytes of a name: its attribute}` of a floppy image's live root entries."""
    entries = (disk[ROOT_AT + nth * st_build.DIR_ENTRY_BYTES:ROOT_AT + (nth + 1) * st_build.DIR_ENTRY_BYTES] for nth in range(st_build.ROOT_ENTRIES))
    return {bytes(entry[:st_build.DIR_NAME_BYTES]): entry[st_build.DIR_NAME_BYTES] for entry in entries
            if entry[0] not in (0, st_build.DELETED_ENTRY)}


def name_on_disk(name):
    return st_build.dos_name(name)


def written(chain):
    """The sectors the chain's own steps wrote to the floppy: Rwabs calls with the write flag."""
    return [call for stepped in chain.steps for call in stepped.boot.floppy
            if call.function == aes_boot.RWABS and call.arguments[0] & aes_boot.RWABS_WRITE and call.arguments[1]]


INF_ON_DISK, FOLDER_ON_DISK = name_on_disk(desk.THE_INF), name_on_disk(desk.NEW_FOLDER)
RENAMED_ON_DISK = name_on_disk(desk.THE_RENAMED)
ATTR_READ_ONLY = 0x01                   # a directory entry's read-only bit (`gemdos/fs.h`: GEMDOS_ATTR_READ_ONLY)
DENIED = "file: read-only, dragged to the trash, OK — access denied, Return"
README_ON_DISK, AUTO_ON_DISK, INSIDE_ON_DISK = (name_on_disk(name) for name in (desk.THE_README, desk.THE_FOLDER, accessory_disk.INSIDE_NAME))
LAUNCHED = "files: the program double-clicked — launched"
# `{chain: what its last machine holds}` — where the act leaves something a test can read off the machine or the disk.
def shown_texts(machine):
    return [text for _index, text, _letter in desk.icons(machine)]


def drive_letters(machine):
    """The letters of the drive icons the desk shows, in its tree's order."""
    return [letter for _index, _text, letter in desk.icons(machine) if letter.strip("\0")]


def the_inf_is_written(chain):
    return written(chain) and INF_ON_DISK in root_of(chain.machine.boot.disk)


LEFT_BEHIND = {
    "Options > Save Desktop, Return": the_inf_is_written,
    "text view: Options > Save Desktop, Return": the_inf_is_written,
    "drive A: selected": lambda chain: desk.drive_is_selected(chain.machine, "A"),
    "window: View > Show as Text": lambda chain: (
        desk.menu_item_is_checked(chain.machine, "Show as Text") and not desk.menu_item_is_checked(chain.machine, "Show as Icons")),
    "window: View > Sort by Size": lambda chain: (
        desk.menu_item_is_checked(chain.machine, "Sort by Size") and not desk.menu_item_is_checked(chain.machine, "Sort by Name")),
    "folder: File > Close": lambda chain: {desk.NEW_FOLDER, desk.THE_INF} <= set(shown_texts(chain.machine)) and len(desk.windows(chain.machine)) == 1,
    "files: A: opened": lambda chain: (
        {desk.THE_README, desk.THE_FOLDER, desk.THE_INF} <= set(shown_texts(chain.machine)) and len(desk.windows(chain.machine)) == 1),
    THE_BOX: lambda chain: desk.icon_is_selected(chain.machine, desk.THE_TRASH),
    "A: opened": lambda chain: desk.THE_INF in shown_texts(chain.machine) and len(desk.windows(chain.machine)) == 1,
    "window: A: opened again (two windows)": lambda chain: len(desk.windows(chain.machine)) == 2 and chain.machine.word(aes.AES_GL_WTOP) == 2,
    "A: File > Open": lambda chain: desk.THE_INF in shown_texts(chain.machine),
    "window: File > Close Window": lambda chain: desk.windows(chain.machine) == (),
    "window: its closer clicked": lambda chain: desk.windows(chain.machine) == (),
    "window: its fuller clicked": lambda chain: desk.top_window(chain.machine)[2:] > desk.top_window(desk.walked("A: opened").machine)[2:],
    "file: selected": lambda chain: desk.icon_is_selected(chain.machine, desk.THE_INF),
    "file: dragged to the trash, Return (Cancel, the dialog's default)": lambda chain: (
        INF_ON_DISK in root_of(chain.machine.boot.disk) and not written(chain)),
    "file: dragged to the trash, OK": lambda chain: INF_ON_DISK not in root_of(chain.machine.boot.disk) and written(chain),
    "folder: File > New Folder, 'A', Return": lambda chain: root_of(chain.machine.boot.disk).get(FOLDER_ON_DISK) == st_build.ATTR_DIRECTORY,
    "folder: the file dragged onto it, Return": lambda chain: chain.machine.boot.disk.count(INF_ON_DISK) == 2,
    "folder: opened": lambda chain: [text for _index, text, letter in desk.icons(chain.machine) if not letter.strip("\0")] == [desk.THE_TRASH],
    "folder: dragged to the trash, OK": lambda chain: FOLDER_ON_DISK not in root_of(chain.machine.boot.disk) and written(chain),
    "files: the long file dragged onto the folder, Return": lambda chain: chain.machine.boot.disk.count(README_ON_DISK) == 2,
    "files: the folder (not empty) dragged to the trash, OK": lambda chain: (
        AUTO_ON_DISK not in root_of(chain.machine.boot.disk) and chain.machine.boot.disk.count(INSIDE_ON_DISK) == 0),
    "files: the window made full": lambda chain: desk.top_window(chain.machine)[2:] > desk.top_window(desk.walked("files: A: opened").machine)[2:],
    LAUNCHED: lambda chain: chain.machine.static_processes()[0].name == desk.THE_PROGRAM.split(".")[0].encode().ljust(aes.PD_NAME_BYTES),
    # ---- band 6 wave 1a's fix pass: the dialogs' less-trodden buttons
    "A: Options > Install Disk Drive, Remove pressed": lambda chain: drive_letters(chain.machine) == ["B"],
    "A: Options > Install Disk Drive, 'C' typed, Install pressed": lambda chain: drive_letters(chain.machine) == ["B", "A", "c"],
    "file: File > Show Info, Backspace, 'A', Return (renamed)": lambda chain: (
        root_of(chain.machine.boot.disk).get(RENAMED_ON_DISK) == st_build.ATTR_NONE and INF_ON_DISK not in root_of(chain.machine.boot.disk)
        and desk.THE_RENAMED in shown_texts(chain.machine)),
    desk.READ_ONLY_FILE: lambda chain: root_of(chain.machine.boot.disk).get(INF_ON_DISK) == ATTR_READ_ONLY and written(chain),
    # (GEMDOS refuses the delete: the disk as the chain found it, not a sector written)
    DENIED: lambda chain: root_of(chain.machine.boot.disk).get(INF_ON_DISK) == ATTR_READ_ONLY and not written(chain),
}
# ---- band 6 wave 4, slice H: what the devices' acts leave — a disk formatted single-sided (its new serial logged in),
# drive A: copied onto drive B: (all but the boot sector's serial and checksum), the file printed (its bytes, then the
# engine's CR LF: `$fed6b4`, `$fed6bc`) or nothing printed
PRINT_ENDS_WITH = b"\r\n"
BOOT_SECTOR_CHECKSUM_AT = st_build.SECTOR_BYTES - WORD_BYTES
COPY_DIFFERS_AT = {*range(st_build.BOOT_SERIAL_AT, st_build.BOOT_SERIAL_AT + st_build.BOOT_SERIAL_BYTES),
                   *range(BOOT_SECTOR_CHECKSUM_AT, st_build.SECTOR_BYTES)}


def formatted_single_sided_and_logged_in(chain):
    disk = chain.machine.boot.disk
    aes_boot.Floppy(chain.machine.image(), disk)            # (refused, by name, unless the driver's record holds it)
    return aes_boot.geometry_of(disk)[2] == 1 and accessory_disk.serial_of(disk) != accessory_disk.serial_of(aes_boot.inf_disk_of())


def copied_onto_drive_b(chain):
    source, copy = chain.machine.boot.disk, chain.machine.boot.drive_b
    return {at for at in range(len(source)) if source[at] != copy[at]} == COPY_DIFFERS_AT and source == aes_boot.inf_disk_of()


def printed(chain):
    return chain.steps[-1].boot.printed == aes_boot.default_inf() + PRINT_ENDS_WITH


def nothing_printed(chain):
    return all(not step.boot.printed for step in chain.steps)


LEFT_BEHIND.update({desk.FORMATTED: formatted_single_sided_and_logged_in, desk.COPIED: copied_onto_drive_b,
                    "file: File > Open, five seconds, Print clicked (printed)": printed,
                    "file: the printer not ready, five seconds, Retry (printed)": printed,
                    desk.NOT_READY: nothing_printed, "file: the printer not ready, Retry (not ready again)": nothing_printed})
# `{chain: the two words its own steps ran, one per step}` — the File menu's Show Info and New Folder, by the CPU's own
# Line-F exception (read off each step's cycle profile: the word's PC charged).
SHOW_INFO_WORD, NEW_FOLDER_WORD = ((at, word) for at, (word, _routine) in THE_TWO_WORDS.items())
THROUGH_THE_TWO_WORDS = {
    "A: File > Show Info, Return": (SHOW_INFO_WORD,), "file: File > Show Info, Return": (SHOW_INFO_WORD,),
    "file: File > Show Info, Backspace, 'A', Return (renamed)": (SHOW_INFO_WORD,), desk.READ_ONLY_FILE: (SHOW_INFO_WORD,),
    "folder: selected, File > Show Info, Return": (SHOW_INFO_WORD,), "files: the program selected, File > Show Info, Return": (SHOW_INFO_WORD,),
    "folder: File > New Folder, 'A', Return": (NEW_FOLDER_WORD,),
    # (band 6 wave 2's, and its fix pass's) New Folder again; Show Info of an emptied drive A:; a folder made after the
    # read-only file and in the files window
    "folder: File > New Folder again, 'A', Return — the name taken, Return": (NEW_FOLDER_WORD,),
    desk.EMPTIED_INFO: (SHOW_INFO_WORD,), desk.READ_ONLY_COPIED: (NEW_FOLDER_WORD,), desk.A_FIFTH_ENTRY: (NEW_FOLDER_WORD,)}


def test_the_tables_of_this_battery_name_chains_there_are():
    assert set(LEFT_BEHIND) <= set(desk.CHAINS) and set(THROUGH_THE_TWO_WORDS) <= set(desk.CHAINS)
    assert all(chain.after in desk.CHAINS or chain.after in desk.MACHINES for chain in desk.CHAINS.values())
    assert all(step.until is None or step.until in desk.STOPS for chain in desk.CHAINS.values() for step in chain.steps)
    assert all(set(chain.enters) <= set(desk.routines()) for chain in desk.CHAINS.values())


# THE CAMPAIGN'S SIZE, by the block that added the chains: `{block: (chains, steps)}` — a group of band 6 wave 1b (or 2) adds
# its own chains' count and steps inside its own block (`aes_desk.CHAINS`' matching block), so no two authors edit one
# line; the pin is the sum.
CHAINS_AND_STEPS_BY_BLOCK = {
    "band 6 waves 0 and 1a": (51, 158),
    # ---- band 6 wave 1b, group G1 (units I, L) ----
    "band 6 wave 1b, group G1": (3, 5),
    # ---- end of group G1's ----
    # ---- band 6 wave 1b, group G2 (units A, K, J) ----
    "band 6 wave 1b, group G2": (4, 14),     # (the fix pass's) Show as Icons; Save Desktop, a window open, then scrolled; B: and the trash boxed
    # ---- end of group G2's ----
    # ---- band 6 wave 1b, group G3 (units B, G) ----
    "band 6 wave 1b, group G3": (5, 13),     # a drive put down on the desktop, its object's corner clicked, three sorts
    # ---- end of group G3's ----
    # ---- band 6 wave 1b, group G4 (units C, H, E, F) ----
    "band 6 wave 1b, group G4": (6, 29),    # the name conflict three ways, B into A, A holding B deleted, copies unconfirmed
    # ---- end of group G4's ----
    # ---- band 6 wave 2, group G1 (units C, F, E) ----
    "band 6 wave 2, group G1": (7, 33),    # (+ the fix pass's) Show Info of the emptied drive; the read-only file copied
    # ---- end of group G1's wave-2 ----
    # ---- band 6 wave 2, group G2 (units H, G, M) ----
    "band 6 wave 2, group G2": (7, 30),    # desktop icons into a window and onto icons, New Folder again, a file onto its drive;
                                           # (the fix pass's) drive A: into its window, emptied
    # ---- end of group G2's wave-2 ----
    # ---- band 6 wave 2, group G3 (units I, J, K, L) ----
    "band 6 wave 2, group G3": (16, 49),   # the arrows, the bar, the slider; the window sized, then paged; one of two closed; Esc;
                                           # (the fix pass's) three INF restarts kept; a fifth entry, then the down arrow;
                                           # two windows shown as text
    # ---- end of group G3's wave-2 ----
    # ---- band 6 wave 2, group G4 (units A, B) ----
    "band 6 wave 2, group G4": (2, 7),     # (the fix pass's) the text view: a line dragged; an icon put down
    # ---- end of group G4's wave-2 ----
    # ---- band 6 wave 4, slice H (the devices) ----
    "band 6 wave 4, slice H": (12, 25),    # Format up, EXIT, FORMAT, then OK and EXIT; the copy up, EXIT, COPY onto a
                                           # second disk; Print: not ready, Cancel, Retry, five seconds then Retry or Print
    # ---- end of slice H's ----
    # ---- band 6 wave 4, group G1 (unit M) ----
    "band 6 wave 4, group G1": (1, 6),     # (the fix pass) the INF shown again: its engine's words stale by a run
    # ---- end of group G1's wave-4 ----
    # ---- band 6 wave 4, group G2 (unit N) ----
    "band 6 wave 4, group G2": (1, 5),     # a single-sided disk in drive B:, drive A: dropped on it, OK, COPY: refused
    # ---- end of group G2's wave-4 ----
    # ---- band 6 slice F3's fix pass (the cartridge's line a drive: a labelled class of disk) ----
    "band 6 slice F3's fix pass": (1, 1),  # drive 'c' opened on the labelled class's machine (`aes_desk.CARTRIDGE_OPENED`)
    # ---- end of slice F3's fix pass ----
    # ---- band 6 slice F3 stage 2's fix pass (a folder's acts in a window restored after a show) ----
    "band 6 slice F3 stage 2's fix pass": (2, 18),     # the long file shown, AUTO opened; INSIDE.TXT shown, File > Close
    # ---- end of slice F3 stage 2's fix pass ----
    # ---- band 6 slice F3 stage 3's fix pass (two arms of the stage's three no chain reached) ----
    "band 6 slice F3 stage 3's fix pass": (2, 8),      # Esc at the idle, no window; A: and B: boxed, A: dragged onto B:
    # ---- end of slice F3 stage 3's fix pass ----
    # ---- band 6 W3a's prep (two arms of the cycle no chain reached) ----
    "band 6 W3a's prep": (2, 4),           # two windows: the lower one's title clicked (WM_TOPPED), the top one's dragged (WM_MOVED)
    # ---- end of band 6 W3a's prep ----
}
CHAINS, STEPS = (sum(chains for chains, _steps in CHAINS_AND_STEPS_BY_BLOCK.values()),
                 sum(steps for _chains, steps in CHAINS_AND_STEPS_BY_BLOCK.values()))


def through_the_two_words(name):
    """`((address, word), ...)`: the two words the chain `name`'s own steps ran, in step order (the CPU's exception)."""
    return tuple(site for step in desk.walked(name).steps for site in (SHOW_INFO_WORD, NEW_FOLDER_WORD)
                 if site[0] in desk.cycles_at(step.profile))


def test_every_chain_names_a_routine_of_its_act_and_the_campaign_is_this_many_chains_and_steps():
    """NO CHAIN IS HELD BY ITS NAME ALONE (the design's risk 7): each of the CHAINS names at least one routine ITS OWN
    STEPS must enter — the act's own, read off the ROM — and the per-chain case holds it to the cycle profile."""
    assert [name for name, chain in desk.CHAINS.items() if not chain.enters] == []
    assert (len(desk.CHAINS), sum(len(chain.steps) for chain in desk.CHAINS.values())) == (CHAINS, STEPS)


@pytest.mark.parametrize("name", desk.CHAINS)
def test_the_chain_ends_at_the_rom_s_idle_having_done_what_its_name_says(name):
    """EACH CHAIN, ON THE ROM'S MACHINE: every step ends where it says — its named stop (at no idle, the PC the
    stop's), else the idle of the ROM's dispatcher — with its ledger whole; the machine holds no blob; ITS OWN STEPS
    ENTERED THE ACT'S ROUTINES (the cycle profile); what the act leaves behind is there; the File menu's two former
    MOVE16 words it ran are the ones its menu items call for and no other; and no stack was stored outside its span's
    reach (a depth is below the stack's size, PD0's above nothing)."""
    declared, chain = desk.CHAINS[name], desk.walked(name)
    for step, stepped in zip(declared.steps, chain.steps):
        boot = stepped.boot
        assert not boot.writes_truncated and aes_boot.blob_of(boot) is None
        if step.until is None:
            assert boot.idle == THE_ROM_S and boot.registers["pc"] & BUS == aes_boot.IDLE_LOOP, step.what
        else:
            assert boot.idle is None and boot.registers["pc"] & BUS == desk.STOPS[step.until], step.what
    assert chain.machine.idle == THE_ROM_S and len(chain.steps) == len(declared.steps)
    missed = [f"{routine:#x}" for routine in declared.enters if routine not in desk.entered(name)]
    assert not missed, f"{name!r} idled and its own steps never entered {missed}: the chain did not do what its name says"
    assert LEFT_BEHIND.get(name, lambda _chain: True)(chain), f"{name!r} did not leave what its act leaves"
    assert through_the_two_words(name) == THROUGH_THE_TWO_WORDS.get(name, ())
    for which, (lo, hi) in desk.stacks(chain.machine).items():
        if not (name in desk.THE_DESK_S_BLOCKS_ARE_CLEARED_IN and which == desk.USERDEF_STACK):
            assert desk.depths(name)[which] < hi - lo, which
    assert desk.depths(name)[desk.PD0_STACK] > 0


def test_a_launch_frees_the_desk_s_blocks_and_the_loader_clears_them():
    """WHY THE LAUNCH IS LEFT OUT OF THE USERDEF STACK'S DEPTHS: deskmain's return frees the desk's five blocks, the
    trampoline's kilobyte among them, and Pexec clears the program's memory over it — every byte stored, which is no
    depth of a stack."""
    assert desk.depths(LAUNCHED)[desk.USERDEF_STACK] == desk.USERDEF_STACK_BYTES
    assert LAUNCHED in desk.THE_DESK_S_BLOCKS_ARE_CLEARED_IN


# ---- A KEY IS PRESSED AND LET GO -------------------------------------------------------------------------------------------------------
THE_KEY = "a key typed at the desk's idle"


def test_a_typed_key_is_let_go_and_the_rom_s_machine_is_another_with_it_held():
    """`typed` delivers the make code AND ITS BREAK CODE: the same key pressed and never let go leaves the ROM's
    machine another one at the same idle (the keyboard handler's own state: a key it holds as down)."""
    idle, (step,) = aes_boot.inf_machine(), desk.CHAINS[THE_KEY].steps
    pressed, released = aes_boot.ikbd(desk.SCAN_A), aes_boot.ikbd(desk.SCAN_A | desk.KEY_RELEASED)
    assert tuple(step.hand(idle)) == (pressed, released)
    held = desk.stepped(idle.boot, (pressed,)).boot
    let_go = desk.walked(THE_KEY).machine.boot
    assert held.idle == let_go.idle == THE_ROM_S and held.ram != let_go.ram


# ---- THE REACH TABLE AND THE STACKS -----------------------------------------------------------------------------------------------------
# Of band 6's 244, by the campaign's own steps (the boot's routines are not a chain's): `{block: routines its chains
# reached first}` — a group of band 6 wave 1b (or 2) adds the routines ITS chains reach that none reached before, in its own
# block; the pin is the sum.
REACHED_BY_BLOCK = {
    "band 6 waves 0 and 1a": 219,
    # ---- band 6 wave 1b, group G1 (units I, L) ----
    "band 6 wave 1b, group G1": 0,
    # ---- end of group G1's ----
    # ---- band 6 wave 1b, group G2 (units A, K, J) ----
    "band 6 wave 1b, group G2": 0,
    # ---- end of group G2's ----
    # ---- band 6 wave 1b, group G3 (units B, G) ----
    "band 6 wave 1b, group G3": 1,          # move_drvicon `$fdc268` (the drive put down on a bare spot)
    # ---- end of group G3's ----
    # ---- band 6 wave 1b, group G4 (units C, H, E, F) ----
    "band 6 wave 1b, group G4": 4,          # $fdcf04 draw_dial, $fdcf48 do_namecon, $fdd0d2 sub_path, $fdd762 path_part
    # ---- end of group G4's ----
    # ---- band 6 wave 2, group G1 (units C, F, E) ----
    "band 6 wave 2, group G1": 0,
    # ---- end of group G1's wave-2 ----
    # ---- band 6 wave 2, group G2 (units H, G, M) ----
    "band 6 wave 2, group G2": 2,          # $fe038c fun_disk, $fe0454 fun_desk2win (a desktop icon let go in a window)
    # ---- end of group G2's wave-2 ----
    # ---- band 6 wave 2, group G3 (units I, J, K, L) ----
    "band 6 wave 2, group G3": 0,
    # ---- end of group G3's wave-2 ----
    # ---- band 6 wave 2, group G4 (units A, B) ----
    "band 6 wave 2, group G4": 0,
    # ---- end of group G4's wave-2 ----
    # ---- band 6 wave 4, slice H (the devices) ----
    "band 6 wave 4, slice H": 9,           # $fed912 format, $fedde4 copy, $fed624 print; $fed888 $fee236 the utilities'
                                           # dialog; $fee166 $fee450 format's; $fee294 the copy's tracks; $fed832 a byte put
    # ---- end of slice H's ----
    # ---- band 6 wave 4, group G1 (unit M) ----
    "band 6 wave 4, group G1": 0,
    # ---- end of group G1's wave-4 ----
    # ---- band 6 wave 4, group G2 (unit N) ----
    "band 6 wave 4, group G2": 1,          # $fee364 util_error: the copy's "not the same type"
    # ---- end of group G2's wave-4 ----
    # ---- band 6 slice F3's fix pass ----
    "band 6 slice F3's fix pass": 2,       # $fed522 cart_sfirst, $fed534 cart_snext (pn_active's cartridge arm, drive 'c')
    # ---- end of slice F3's fix pass ----
    # ---- band 6 slice F3 stage 2's fix pass ----
    "band 6 slice F3 stage 2's fix pass": 0,
    # ---- end of slice F3 stage 2's fix pass ----
    # ---- band 6 slice F3 stage 3's fix pass ----
    "band 6 slice F3 stage 3's fix pass": 0,
    # ---- end of slice F3 stage 3's fix pass ----
    # ---- band 6 W3a's prep ----
    "band 6 W3a's prep": 0,                # (hndl_msg's two arms: no routine first reached)
    # ---- end of band 6 W3a's prep ----
}
REACHED = sum(REACHED_BY_BLOCK.values())


def test_the_reach_table_has_a_row_for_every_routine_and_is_read_off_each_chain_s_own_steps():
    """THE DERIVATION: `{routine: chains}` over band 6's 244 — REACHED with a chain, in `CHAINS`' order; a chain's row
    is ITS OWN steps' (the file selected enters no folder maker though the chain it goes on to does), and a routine
    is reached by its FIRST INSTRUCTION (a chain whose profile holds only a later PC of it — a return into a routine
    its predecessor entered — does not reach it)."""
    table = desk.reach()
    assert tuple(table) == desk.routines()
    assert sum(1 for chains in table.values() if chains) == REACHED
    assert all(list(chains) == [name for name in desk.CHAINS if name in chains] for chains in table.values())
    assert "folder: File > New Folder, 'A', Return" in table[desk.MAKE_FOLDER] and "A: opened" not in table[desk.MAKE_FOLDER]
    assert set(table[desk.SHOW_FILE]) == {THE_SHOW, "files: the long file shown, a blank at each page's end and at its end",
                                          *(chain for chain in desk.CHAINS if chain.endswith(("then the long file shown",
                                                                                              "then the long file's line shown"))),
                                          desk.SHOWN_AGAIN,     # (band 6 wave 4's fix pass: the INF shown again)
                                          desk.SHOWN_THEN_FOLDER_OPENED, desk.SHOWN_THEN_FOLDER_CLOSED}   # (F3 stage 2's fix pass)
    assert len(table[desk.SHOW_FILE]) == 8
    for name in ("A: opened", THE_SHOW):
        assert {routine for routine, chains in table.items() if name in chains} == desk.entered(name)
    assert desk.reach(("A: opened",))[desk.MAKE_FOLDER] == ()


def test_a_routine_is_reached_by_its_first_instruction_not_by_any_of_its_pcs():
    """The dialog's Return RETURNS INTO the File menu's Open (it parked inside its alert) and runs its tail: cycles in
    the routine's span, none at its entry — not a reach."""
    alert, answered = "file: File > Open (the Show / Print / Cancel alert)", THE_SHOW
    lo, hi = desk.OPEN_SELECTION, desk.routines()[desk.routines().index(desk.OPEN_SELECTION) + 1]
    ran = set().union(*(desk.cycles_at(step.profile) for step in desk.walked(answered).steps))
    assert desk.OPEN_SELECTION in desk.entered(alert) and desk.OPEN_SELECTION not in desk.entered(answered)
    assert any(lo < pc < hi for pc in ran)


PD0_BYTES, PD1_BYTES = desk.PD0_BYTES, desk.PD1_BYTES     # (their one home: `aes_desk`)
DEEPEST = {desk.PD0_STACK: ("A: File > Open", 1460), desk.PD1_STACK: ("window: View > Show as Text", 722),
           desk.DISPATCHER_STACK: ("window: A: opened again (two windows)", 190), desk.USERDEF_STACK: ("window: View > Show as Text", 438)}
DISPATCHER_ELSEWHERE = 188
# THE DISPATCHER AT 190 — not the second window alone: band 6 wave 2's re-derivation (Reviewer B's, its fix pass's
# measure) finds it on these five chains, four of them pure walks of the ROM after "A: opened" (nothing by hand, nothing
# laid), the fifth through Show Info's word — the ROM's own depth (W6-R4: REPORTED, the deepest unchanged at 190).
# What stores at 190 is not traced.
DISPATCHER_AT_190 = frozenset({DEEPEST[desk.DISPATCHER_STACK][0], "A: opened, drive A: dragged into its window, Return",
                               "A: opened, the trash dragged into its window, Return",
                               "file: dragged to the trash, OK — then drive A: dragged into its window", desk.EMPTIED_INFO,
                               desk.LOWER_WINDOW_TOPPED})     # (band 6 W3a's prep: the two windows' chain, the lower one topped)


def test_the_deepest_each_stack_is_taken_and_by_which_chain_off_the_write_ledgers():
    """MEASURED, THE ROM'S OWN DESK ON THE ROM'S AES: PD0 1,460 of 1,792 (File > Open on drive A:: 332 spare, 88 under
    the 244-byte nest band 5 charges), PD1 722 of 1,196 (a menu chosen over a window), the dispatcher 190 on the
    chains DISPATCHER_AT_190 (a second window opened, a desktop icon dropped into a window) and 188 ON EVERY OTHER,
    the userdef stack 438 of 1,024 (the text view drawn). A depth
    is the lowest STORE of a chain's own steps."""
    spans = desk.stacks(aes_boot.inf_machine())
    assert (spans[desk.PD0_STACK][1] - spans[desk.PD0_STACK][0], spans[desk.PD1_STACK][1] - spans[desk.PD1_STACK][0]) == (PD0_BYTES, PD1_BYTES)
    assert {which: desk.deepest(which) for which in DEEPEST} == DEEPEST
    assert ({name: desk.depths(name)[desk.DISPATCHER_STACK] for name in desk.CHAINS}
            == {name: DEEPEST[desk.DISPATCHER_STACK][1] if name in DISPATCHER_AT_190 else DISPATCHER_ELSEWHERE for name in desk.CHAINS})


def test_a_depth_is_from_the_stack_s_top_down_to_the_lowest_byte_stored_inside_it():
    stored = ((0x0f0, 0x20), (0x180, 4), (0x1fe, 8), (0x300, 16))
    assert desk.depth_stored(stored, 0x100, 0x200) == 0x100         # a run that begins below the stack reaches its floor
    assert desk.depth_stored(stored[1:], 0x100, 0x200) == 0x80
    assert desk.depth_stored(stored[2:], 0x100, 0x200) == 2         # ...and one that ends past its top begins inside
    assert desk.depth_stored(stored[3:], 0x100, 0x200) == 0


# ---- THE FOLDER CHAIN, ON THE CPU'S OWN EXCEPTION -------------------------------------------------------------------------------------------
def test_new_folder_makes_its_folder_through_the_cpu_s_own_line_f_exception():
    """THE RED THE MEASURING PASS MET (the oracle EXECUTED `$f624` as MOVE16: the chain idled at every step, entered no
    folder maker and wrote no sector), MENDED IN THE KIT: the same hands, every step's profile charging the word's PC,
    the folder maker entered and a sector written, the folder on the disk."""
    machine, ran, wrote = desk.walked("A: opened").machine, set(), False
    for step in desk.CHAINS["folder: File > New Folder, 'A', Return"].steps:
        stepped = desk.stepped.derive(machine.boot, tuple(step.hand(machine)))
        assert stepped.boot.idle == THE_ROM_S
        wrote |= any(call.function == aes_boot.RWABS and call.arguments[0] & aes_boot.RWABS_WRITE for call in stepped.boot.floppy)
        machine, ran = aes_boot.Machine(stepped.boot), ran | set(desk.cycles_at(stepped.profile))
    assert NEW_FOLDER_WORD[0] in ran and desk.MAKE_FOLDER in ran and wrote and FOLDER_ON_DISK in root_of(machine.boot.disk)


# ---- THE FILES DISK AND ITS MACHINE (the fifth capture) -------------------------------------------------------------------------------
FILES_ROOT = {name_on_disk(accessory_disk.INF_NAME): st_build.ATTR_NONE, README_ON_DISK: st_build.ATTR_NONE,
              name_on_disk(accessory_disk.PROGRAM_NAME): st_build.ATTR_NONE, AUTO_ON_DISK: st_build.ATTR_DIRECTORY,
              st_build.DEFAULT_LABEL.encode().ljust(st_build.DIR_NAME_BYTES): st_build.ATTR_VOLUME_LABEL}
SYSTEM_SECTORS_BYTES = st_build.FIRST_DATA_SECTOR * st_build.SECTOR_BYTES


def test_the_files_disk_holds_files_a_folder_with_a_file_in_it_and_a_program_and_is_one_disk_whatever_its_view():
    """The root: the ROM's own DESKTOP.INF, the long text, the program — the test accessory's file, whole — and the
    folder; the folder's file inside it and no program there (TOS would run one before the desk); and the two views'
    images differ in the `#E` line's VIEW pair alone, inside the DESKTOP.INF's own cluster: the boot sector, both FATs
    and the root are the same bytes."""
    icons, text = aes_boot.files_disk_of(aes_boot.VIEW_AS_ICONS), aes_boot.files_disk_of(aes_boot.VIEW_AS_TEXT)
    assert root_of(icons) == FILES_ROOT == root_of(text)
    assert icons.count(aes_boot.accessory().file) == 1 and icons.count(accessory_disk.README) == 1
    assert icons.count(INSIDE_ON_DISK) == 1 and icons.count(accessory_disk.INSIDE) == 1 and b"PRG" not in INSIDE_ON_DISK
    assert icons[:SYSTEM_SECTORS_BYTES] == text[:SYSTEM_SECTORS_BYTES]
    differing = [at for at in range(len(icons)) if icons[at] != text[at]]
    line = icons.index(accessory_disk.INF_E_LINE)
    assert differing and set(differing) <= set(range(line + accessory_disk.INF_VIEW_PAIR_AT, line + accessory_disk.INF_VIEW_PAIR_AT + 2))
    assert text[line:line + len(accessory_disk.INF_E_LINE)] == accessory_disk.INF_E_LINE.replace(b"1B", b"%02X" % aes_boot.VIEW_AS_TEXT)
    with pytest.raises(ValueError, match="view pair is one byte"):
        accessory_disk.files_disk_of(aes_boot.default_inf(), aes_boot.accessory().file, 0x100)


def test_the_files_capture_logged_its_own_disk_in_and_boots_to_a_desk_with_no_accessory():
    """THE FIFTH CAPTURE: stopped at gem_entry in user mode, the driver's record the files disk's (its BPB and its
    serial — another disk in the drive is refused by name), and the ROM's boot of it a desk and a screen manager, the
    spare PD unused, at the ROM's idle."""
    capture, disk = aes_boot.files_preinit(), aes_boot.files_disk_of()
    assert capture.registers["pc"] == aes_boot.GEM_ENTRY and not capture.registers["sr"] & aes_boot.SR_SUPERVISOR
    record = aes_boot.driver_record(BASE_IMAGE)       # (the ROM's own instruction names it)
    assert bytes(capture.ram[record:record + aes_boot.BPB_WORDS.size]) == aes_boot.bpb_of(disk)
    assert accessory_disk.serial_of(disk) not in (accessory_disk.serial_of(aes_boot.inf_disk_of()), accessory_disk.serial_of(aes_boot.blank_disk()))
    with pytest.raises(Refused, match="this machine booted with another disk"):
        aes_boot.booted(capture, aes_boot.inf_disk_of())
    machine = aes_boot.files_machine()
    desk_s, manager, spare = machine.static_processes()
    assert machine.idle == THE_ROM_S and desk_s.waiting and manager.name == aes_boot.SCREEN_MANAGER_NAME and not spare.waiting
    assert machine.word(aes.AES_ACCESSORY_COUNT) == 0 and machine.boot.disk == disk


def test_the_page_prompt_is_met_twice_and_the_end_once_over_the_long_file():
    """The long file shown: the viewer stops at its page prompt after each of two full pages and at the file's end
    after the last, short one — the three named stops, in that order, before the idle."""
    chain = desk.walked("files: the long file shown, a blank at each page's end and at its end")
    stood_at = [stepped.boot.registers["pc"] & BUS for stepped in chain.steps if stepped.boot.idle is None]
    assert stood_at == [desk.STOPS[stop] for stop in (desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_A_PAGE_S_END, desk.VIEWER_AT_THE_FILE_S_END)]
