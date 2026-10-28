r"""BAND 5 WAVE 4, THE ROM'S SIDE OF THE MACHINES (slice M) — what `test/aes_boot.py` gained for the wave, held on the
machines THE ROM makes, before any of our init runs on one:

  * THE FOURTH CAPTURE (`make preinit-inf`, ruling W4-R7) and its machine: the blank disk plus the ROM's own default
    DESKTOP.INF — the `#E` reader's file arm, its parse and app_reschange in place;
  * THE BOOT'S DEVICE MODEL AS FAR AS A DRIVE'S WINDOW (ruling W4-R8): the floppy at the driver's FOUR entries (XBIOS
    Floprd the fourth) and the drive's media-change mode, the one byte of the driver's state the desk drives — a
    drive icon's double click, the window opened ON THE ROM'S MACHINE, ub_trampoline's arrivals counted, the desk's
    USERBLKs walked;
  * THE SERVED DOOR (ruling W4-R6): deskmain and the shell's built-ins ANSWERED AT THEIR ENTRY, a labelled argument
    class — the teardown and gem_entry's second pass, the launch pass to dos_exec's entry, sh_cmd's arm — with every
    refusal;
  * THE OUR-BOOT MACHINE'S PREMISES (ruling W4-R1), vetted against the ROM's own run — and THE LAY MADE on the disks
    without an accessory (slice B built it: A LABELLED STAGING, held by `test_aes_ourboot.py`), refused by name on
    one with;
  * gem_entry's THREE BY-VALUE DECLARATIONS OF THE REGISTRY (the tick glue, justretf's slot, the walked USERBLKs) held
    to the ROM — declared here, ACTIVATED BY SLICE B, PARTS OF THE DOOR SINCE SLICE F (the full flip) — and THE SCAN
    — no live longword holding, by value, the ROM's copy of A ROUTINE THE REGISTRY DECLARES (seventeen routines, not
    every ROM routine): BEHIND THE DOOR IT FINDS NONE, on every door machine, at the first idle and after a
    continuation — and ONE at deskmain's entry, where no row stands; each part the full flip added, taken out of the
    door in turn, is refused by the scan for its own longwords; what the scan cannot see (a ROM routine nobody
    declared, a value under a non-zero top byte) is held where a test can hold it — `vet_the_door_stands` for the
    door's own longwords, the Line-F table's nine copied entries by name; and A CONTINUATION BEHIND THE DOOR ENTERS
    OUR GLUE AND OUR TRAMPOLINE where the ROM-booted machine enters the ROM's (a cycle profile), and leaves the ROM's
    machine.

NO ROW IS PRICED HERE, and but for the door machines and the one our-boot lay, every machine below is the ROM's own.
Addresses of the ROM are held to its bytes where they are named; nothing a capture decides is pinned.
"""
import functools
import re
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import preinit_snapshot
import st_build

import accessory_disk
import aes
import aes_boot
import aes_ctlmgr
import aes_event
import aes_objdraw as od
import aes_objects
import case
import isr
import test_aes_boot as battery
import test_aes_shell_buf as shell_buf
import vdi
from aes_boot import QUIET, Refused

RAM_BYTES, BUS = aes_boot.RAM_BYTES, aes_boot.BUS
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
every_blob = battery.every_blob
ICONS, TEXT = aes_boot.VIEW_AS_ICONS, aes_boot.VIEW_AS_TEXT
AS_BOOTED, CHANGED = aes_boot.RESOLUTION_AS_BOOTED, aes_boot.RESOLUTION_CHANGED
EVERY_E_LINE = [(view, resolution) for view in (ICONS, TEXT) for resolution in (AS_BOOTED, CHANGED)]
RTS_WORD = 0x4e75
rom_word = battery.rom_word


def rom_long(at):
    return case.long_in(BASE_IMAGE, at)


# ---- THE FOURTH CAPTURE AND ITS DISK ------------------------------------------------------------------------------------------
def test_the_default_desktop_inf_is_the_rom_s_own_text_with_one_e_line():
    """The file on the disk is CUT OUT OF THE ROM: found by its first line, to its NUL, once — the text the reader
    falls back on — with exactly one `#E` line, the default pairs. A ROM that holds two, or another `#E`, is refused."""
    text = aes_boot.default_inf()
    rom = bytes(BASE_IMAGE[emu.ROM_BASE:emu.ROM_END])
    assert rom.count(text + b"\0") == 1 and text.startswith(accessory_disk.INF_FIRST_LINE) and b"\0" not in text
    assert text.count(b"#E ") == 1 and accessory_disk.INF_E_LINE in text and text.endswith(b"\r\n")
    assert accessory_disk.INF_E_LINE == b"#E %02X %02X \r\n" % (ICONS, AS_BOOTED)
    with pytest.raises(ValueError, match="holds 2 texts beginning"):
        accessory_disk.default_inf(rom + text)
    with pytest.raises(ValueError, match="does not hold exactly one `#E` line"):
        accessory_disk.default_inf(rom.replace(accessory_disk.INF_E_LINE, b"#E 1B 10\r\n"))


def test_the_inf_disk_is_one_disk_to_the_machine_whatever_its_e_line_asks():
    """ONE DISK FOR EVERY `#E` LINE: built from the unpatched text, the two pairs patched in the image, inside the
    file's own cluster — the boot sector (its serial), both FATs and the root are the same bytes; what differs is the
    hex digits of the pairs and nothing else; and the image `make` hands the capture is the unpatched one."""
    text, plain = aes_boot.default_inf(), aes_boot.inf_disk_of()
    first_file = accessory_disk.file_at(0, len(text))
    line = accessory_disk.inf_pairs_at(plain, text)
    pairs = range(line + accessory_disk.INF_VIEW_PAIR_AT, line + accessory_disk.INF_RESOLUTION_PAIR_AT + 2)
    assert plain[first_file:first_file + len(text)] == text and first_file <= line < first_file + len(text)
    for view, resolution in EVERY_E_LINE:
        disk = aes_boot.inf_disk_of(view, resolution)
        assert disk[:first_file] == plain[:first_file] and accessory_disk.serial_of(disk) == accessory_disk.serial_of(plain)
        assert disk[line:line + len(accessory_disk.INF_E_LINE)] == b"#E %02X %02X \r\n" % (view, resolution)
        differing = [at for at in range(len(disk)) if disk[at] != plain[at]]
        assert set(differing) <= set(pairs) and len(differing) == (view != ICONS) + (resolution != AS_BOOTED)
    assert accessory_disk.serial_of(plain) != accessory_disk.serial_of(aes_boot.blank_disk()), "another disk than the blank one"
    assert accessory_disk.inf_disk_path().read_bytes() == plain, "`make preinit-inf` booted the unpatched disk"
    assert preinit_snapshot.inf_path().name == "preinit_inf.bin"


def test_a_resolution_no_boot_survives_is_refused_by_name():
    """RISK 10 OF THE WAVE'S DESIGN, as the refusal it is: a `#E` line that asks another resolution than the two that
    boot leaves the device model (the BIOS waits for a vertical blank no boot delivers) — no disk is made of it."""
    for pair in (0x12, 0x13, 0x00, 0xff):
        with pytest.raises(ValueError, match=rf"resolution pair {pair:02X} is no disk of this harness: only \['10', '11'\] boot"):
            aes_boot.inf_disk_of(ICONS, pair)
    with pytest.raises(ValueError, match="view pair is one byte"):
        accessory_disk.inf_disk_of(aes_boot.default_inf(), 0x100)


def test_the_inf_capture_stands_at_the_shell_s_entry_and_logged_its_own_disk_in():
    """The fourth capture stands where the other three do — `gem_entry`, user mode, the launch's stacks — and the
    driver's record there is THE INF DISK's, whatever its `#E` line (the BPB, the geometry words, the serial): the
    blank disk and the accessories' are refused by name over it, and it over the blank disk's capture."""
    capture = aes_boot.inf_preinit()
    assert capture.registers["pc"] == aes_boot.GEM_ENTRY == case.long_in(capture.ram, preinit_snapshot.EXEC_OS)
    assert not capture.registers["sr"] & preinit_snapshot.SR_SUPERVISOR
    assert {name: capture.registers[name] for name in ("usp", "isp", "sr")} == {
        name: aes_boot.preinit().registers[name] for name in ("usp", "isp", "sr")}, "the launch is the blank disk's launch"
    memory = make_image({0: capture.ram})
    for view, resolution in EVERY_E_LINE:
        aes_boot.Floppy(memory, aes_boot.inf_disk_of(view, resolution))
    for other in (aes_boot.blank_disk(), aes_boot.accessory_disk_of(QUIET, QUIET)):
        with pytest.raises(Refused, match="is not the one the driver logged in"):
            aes_boot.Floppy(memory, other)
    with pytest.raises(Refused, match="is not the one the driver logged in"):
        aes_boot.Floppy(make_image({0: aes_boot.preinit().ram}), aes_boot.inf_disk_of())


# The reader's arms and app_reschange's, each held to the ROM's own instructions there (`$fda408`'s listing).
READER_READS_THE_FILE, READER_TAKES_THE_DEFAULT, READER_PARSES_THE_E_LINE = 0xfda496, 0xfda4b4, 0xfda4fa
APP_RESCHANGE, APP_RESCHANGE_CHANGES = 0xfdbae0, 0xfdbaf6
BOOT_DEVICE, CHANGE_FLAG = 0x8908, 0x890a          # gem_entry's two words the reader and app_reschange work on
FILE_BUFFER_BYTES = 2048
PUSH_W_IMMEDIATE, PUSH_D6_W, LINE_F_DOS_READ, LINE_F_ROM_RAM, LINE_F_SCAN_2 = 0x3f3c, 0x3f06, 0xf37c, 0xf358, 0xf33c
ADDQ_5_A5, CMP_W_ABSOLUTE_D0, MOVE_W_ARGUMENT_TO_ABSOLUTE = 0x5a8d, 0xb079, 0x33ee
ROM_RAM_DEFAULT_INF = 3


def test_the_reader_s_arms_are_the_rom_s_own_instructions():
    """WHERE THE BOOTS BELOW ARE STOPPED, held to the ROM: the file arm's dos_read of 2,048 bytes, the default arm's
    rom_ram(3), the `#E` arm's skip to the SECOND pair and its scan_2, app_reschange's compare with the booted device
    (`$8908`) and its "changes" arm's store there."""
    assert struct.unpack_from(">4H", BASE_IMAGE, READER_READS_THE_FILE + 4) == (PUSH_W_IMMEDIATE, FILE_BUFFER_BYTES, PUSH_D6_W, LINE_F_DOS_READ)
    assert struct.unpack_from(">3H", BASE_IMAGE, READER_TAKES_THE_DEFAULT + 6) == (PUSH_W_IMMEDIATE, ROM_RAM_DEFAULT_INF, LINE_F_ROM_RAM)
    assert (rom_word(READER_PARSES_THE_E_LINE), rom_word(READER_PARSES_THE_E_LINE + 8)) == (ADDQ_5_A5, LINE_F_SCAN_2)
    assert struct.unpack_from(">HI", BASE_IMAGE, APP_RESCHANGE + 8) == (CMP_W_ABSOLUTE_D0, BOOT_DEVICE)
    assert struct.unpack_from(">HHI", BASE_IMAGE, APP_RESCHANGE_CHANGES) == (MOVE_W_ARGUMENT_TO_ABSOLUTE, 8, BOOT_DEVICE)
    assert struct.unpack_from(">HHI", BASE_IMAGE, APP_RESCHANGE_CHANGES + 8)[2] == CHANGE_FLAG


def stopped_at(capture, disk, until):
    return aes_boot.booted(capture, disk, until=until)


@pytest.mark.parametrize("resolution", (AS_BOOTED, CHANGED), ids=("the booted resolution", "another"))
def test_the_inf_boot_runs_the_reader_s_file_arm_its_parse_and_app_reschange_in_place(resolution):
    """THE ROM'S OWN BOOT OF THE INF DISK reaches what no other capture's does: the reader READS the file (never the
    default arm), parses the `#E` line's second pair and hands app_reschange `(pair & 3) + 1` — the booted device for
    the default pair (no change: the "changes" arm is never reached), another for `11`, whose arm then runs — and
    still boots to the desk: gsx_init re-derives the device from the workstation it opens."""
    capture, disk = aes_boot.inf_preinit(), aes_boot.inf_disk_of(ICONS, resolution)
    for arm in (READER_READS_THE_FILE, READER_PARSES_THE_E_LINE):
        assert stopped_at(capture, disk, arm).registers["pc"] == arm
    with pytest.raises(Refused, match=f"never arrived at {READER_TAKES_THE_DEFAULT:#x}"):
        stopped_at(capture, disk, READER_TAKES_THE_DEFAULT)
    asked = stopped_at(capture, disk, APP_RESCHANGE)
    device = case.word_in(asked.ram, BOOT_DEVICE)
    assert case.word_in(asked.ram, asked.registers["isp"] + LONG_BYTES) == (resolution & 3) + 1
    if resolution == AS_BOOTED:
        assert (resolution & 3) + 1 == device
        with pytest.raises(Refused, match=f"never arrived at {APP_RESCHANGE_CHANGES:#x}"):
            stopped_at(capture, disk, APP_RESCHANGE_CHANGES)
    else:
        assert (resolution & 3) + 1 != device and stopped_at(capture, disk, APP_RESCHANGE_CHANGES).registers["pc"] == APP_RESCHANGE_CHANGES
    booted = inf(ICONS, resolution)
    assert booted.idle == aes_boot.THE_ROM_S and booted.word(CHANGE_FLAG) == 0
    assert booted.word(BOOT_DEVICE) == aes_boot.desk_machine().word(BOOT_DEVICE), "the device the workstation opened with"


def test_the_blank_disk_s_boot_takes_the_default_arm_and_parses_no_e_line():
    """...and THE CONVERSE, on the desk's own capture: no DESKTOP.INF, so the reader takes rom_ram's default and
    never reaches the file arm, the `#E` arm or app_reschange (the design's finding 0.6: the parse needs a file)."""
    capture, disk = aes_boot.preinit(), aes_boot.blank_disk()
    assert stopped_at(capture, disk, READER_TAKES_THE_DEFAULT).registers["pc"] == READER_TAKES_THE_DEFAULT
    for arm in (READER_READS_THE_FILE, READER_PARSES_THE_E_LINE, APP_RESCHANGE):
        with pytest.raises(Refused, match=f"never arrived at {arm:#x}"):
            stopped_at(capture, disk, arm)


@functools.cache
def inf(view=ICONS, resolution=AS_BOOTED):
    return aes_boot.inf_machine(view, resolution)


@pytest.mark.parametrize("view, resolution", EVERY_E_LINE, ids=lambda pair: f"{pair:02X}")
def test_the_inf_machine_is_a_desk_with_no_accessory_whatever_its_e_line(view, resolution):
    """THE DESKTOP.INF MACHINE at its first idle: the ROM's dispatcher's, one horizontal blank taken, the desk and the
    screen manager waiting and nobody else, no accessory loaded, no clock moved — and nothing of the free window
    touched: the boot's highest store below the screen lies under the window the harness uses."""
    booted = inf(view, resolution)
    assert booted.idle == aes_boot.THE_ROM_S and booted.boot.blanks == 1 and not booted.boot.writes_truncated
    assert len(booted.waiting()) == 2 and booted.screen_manager().waiting
    assert booted.word(aes.AES_ACCESSORY_COUNT) == 0 and not booted.static_processes()[-1].basepage
    capture = aes_boot.inf_preinit()
    for at, size, _why in preinit_snapshot.MASK[:2]:
        assert booted.ram[at:at + size] == capture.ram[at:at + size], "no time passes in a boot"
    window = aes_boot.harness_window(aes_boot.ours_of(isr.blob_named(next(iter(isr.BLOBS)))))
    assert not any(aes_boot._stored_within(booted.boot.stored, lo, hi) for lo, hi in window.values()), "nothing stored in the harness's window"


def test_the_inf_machine_depends_on_no_byte_the_capture_does_not_reproduce():
    """THE MASK'S RULE, on the fourth capture and THROUGH A DRIVE'S WINDOW: booted from a pre-init machine whose every
    masked byte is noise, the ROM takes the same instructions to the same registers and the same machine outside the
    mask — and so does the window's continuation after it (the served Getbpb reads no latch of the mask).

    "NO BYTE THE CAPTURE DOES NOT REPRODUCE" IS THE MASK, AND THE MASK IS HELD FROM BOTH SIDES: that two captures of
    this disk agree outside it is `make preinit-twice` (the gate's; this capture failed it until the mask held the
    boot's three dead stacks whole), and that it holds those stacks whole on THIS capture is the test below."""
    plain, noise = inf(TEXT), aes_boot.inf_machine(TEXT, machine=battery.noisy(aes_boot.inf_preinit()))
    for one, other in ((plain, noise), (window_of(plain), window_of(noise))):
        assert other.registers == one.registers and other.boot.instructions == one.boot.instructions
        assert preinit_snapshot.masked(other.ram) == preinit_snapshot.masked(one.ram) and other.observed == one.observed


# ---- THE STACKS THE BOOT RAN ON ARE DEAD AT THE STOP, AND THE MASK HOLDS EACH WHOLE -----------------------------------------------
EVERY_CAPTURE = {"the blank disk's": aes_boot.preinit, "the accessories'": aes_boot.accessory_preinit,
                 "the seven accessories'": aes_boot.seven_accessory_preinit, "the DESKTOP.INF disk's": aes_boot.inf_preinit}
GEMDOS_LOADS_ITS_STACK_AT = (0xfc4fb8, 0xfc4fd8)        # its `trap #1` handler, a caller in user mode / in supervisor mode
GEMDOS_LAYS_A_CONTEXT_AT, LEA_A5_DISPLACED_A0 = 0xfc4fbe, 0x41ed          # `lea 50(a5),a0`: the context's size, off the USP
EXCEPTION_FRAME_BYTES = WORD_BYTES + LONG_BYTES         # a 68000 interrupt's or trap's: the status word, the PC


def masked_to(top):
    """`(floor, bytes)` of the pre-init mask's region that ends at `top` — exactly one, or the mask does not hold it."""
    (floor, size), = [(at, size) for at, size, _why in preinit_snapshot.MASK if at + size == top]
    return floor, size


@pytest.mark.parametrize("label", EVERY_CAPTURE)
def test_the_three_stacks_the_boot_ran_on_are_dead_at_the_stop_and_the_mask_holds_each_to_its_top(label):
    """WHAT A CAPTURE CANNOT REPRODUCE OUTSIDE ITS CLOCKS IS WHAT INTERRUPTS PUSHED ON STACKS NOBODY RETURNS TO — and
    each such stack is in the mask TO ITS TOP, the top read off the ROM and this capture's own registers, never off
    which bytes some boots happened to show (`--twice` failed on the fourth capture for exactly that):
      * GEMDOS's own, to the address its `trap #1` handler loads SP with on every call;
      * the BIOS's own, to the ISP the capture stopped with — the address the AUTO runner reloads — the machine in
        USER mode, the launch frame GEMDOS's `rte` popped still under it;
      * the launched program's, to the context GEMDOS laid 50 bytes under its USP (the stop's D0 and A6).
    AND THIS CAPTURE'S DEEPEST FRAME LIES INSIDE: nothing was ever stored for as far again below either floor — a
    boot that nests deeper is named here, not met as a difference between two captures."""
    capture = EVERY_CAPTURE[label]()
    ram, registers = capture.ram, capture.registers
    assert not registers["sr"] & preinit_snapshot.SR_SUPERVISOR
    for at in GEMDOS_LOADS_ITS_STACK_AT:
        assert struct.unpack_from(">HI", BASE_IMAGE, at) == (battery.MOVEA_L_IMMEDIATE_SP, preinit_snapshot.GEMDOS_STACK_TOP)
    assert masked_to(preinit_snapshot.GEMDOS_STACK_TOP)[0] == preinit_snapshot.GEMDOS_STACK_FLOOR
    bios_top = registers["isp"]
    assert bios_top == preinit_snapshot.BIOS_STACK_TOP == rom_long(battery.AUTO_RUNNER_ABANDONS_ITS_STACK + WORD_BYTES)
    assert struct.unpack_from(">HI", ram, bios_top - EXCEPTION_FRAME_BYTES) == (registers["sr"], registers["pc"]), "the launch frame"
    opcode, context_bytes = struct.unpack_from(">HH", BASE_IMAGE, GEMDOS_LAYS_A_CONTEXT_AT)
    context = registers["usp"] - context_bytes
    assert opcode == LEA_A5_DISPLACED_A0 and context == preinit_snapshot.LAUNCH_CONTEXT == registers["a6"] == registers["d0"]
    for top in (bios_top, context):
        floor, size = masked_to(top)
        assert size == preinit_snapshot.STACK_DEAD_BYTES
        assert not any(ram[floor - size:floor]), f"{label} capture: a frame lies below {floor:#x}, deeper than the mask reaches under {top:#x}"
    assert any(ram[masked_to(bios_top)[0]:bios_top]), "the BIOS's stack holds the boot's frames"
    assert not any(lo <= aes_boot.driver_mode(make_image({0: ram})) < lo + size for lo, size, _why in preinit_snapshot.MASK)


# ---- THE DEVICE MODEL: THE DRIVER'S FOURTH ENTRY AND ITS MEDIA-CHANGE MODE -------------------------------------------------------
XBIOS_DISPATCHER, XBIOS_FUNCTIONS, FLOPRD_ROUTINE = 0xfc07f2, 65, 0xfc1782
BSR_W = 0x6100
DESK_ASKS_FLOPRD_AT, DESK_FORCES_THE_CHANGE_AT = 0xfe1b5c, 0xfe1ba4
LINE_F_TRP14, LINE_F_TRP13, CLR_L_PUSH = 0xf180, 0xf1a0, 0x42a7
BIOS_RWABS = 4
MEDIACH_ADDS_THE_MODES_AT, GETBPB_LOADS_THE_MODES_AT, MEDIACH_TESTS_CHANGED_AT = 0xfc1194, 0xfc1160, 0xfc119a
ADDA_L_IMMEDIATE_A5, CMPI_B_A5 = 0xdbfc, 0x0c15


def test_the_fourth_entry_and_the_mode_byte_are_the_rom_s_own():
    """THE MODEL'S NEW ADDRESSES, HELD TO THE ROM: the XBIOS dispatcher the machine's vector names loads its table by
    `lea`, the table counts 65 functions and its eighth is the floppy driver's Floprd (a `bsr` first: its own
    prologue); the desk asks `Floprd` through trp14 and then `Rwabs(0, NULL, 2, 0, drive)` through trp13; and the byte
    the ROM's Rwabs stores a NULL buffer's count in is the one its Mediach tests for CHANGED and its Getbpb rewrites."""
    capture = aes_boot.preinit()
    assert case.long_in(capture.ram, addrs.VECTOR_TRAP_XBIOS) == XBIOS_DISPATCHER
    table = XBIOS_DISPATCHER + WORD_BYTES + struct.unpack_from(">h", BASE_IMAGE, XBIOS_DISPATCHER + WORD_BYTES)[0]
    assert (rom_word(XBIOS_DISPATCHER), rom_word(table)) == (aes_boot.LEA_PC_RELATIVE_A0, XBIOS_FUNCTIONS)
    memory = make_image({0: capture.ram})
    assert aes_boot._xbios_entry(memory, aes_boot.XBIOS_FLOPRD) == FLOPRD_ROUTINE and rom_word(FLOPRD_ROUTINE) == BSR_W
    floppy = aes_boot.Floppy(memory, aes_boot.blank_disk())
    assert sorted(floppy.entries.values()) == sorted((aes_boot.GETBPB, aes_boot.MEDIACH, aes_boot.RWABS, aes_boot.FLOPRD))
    assert struct.unpack_from(">3H", BASE_IMAGE, DESK_ASKS_FLOPRD_AT) == (PUSH_W_IMMEDIATE, aes_boot.XBIOS_FLOPRD, LINE_F_TRP14)
    assert struct.unpack_from(">7H", BASE_IMAGE, DESK_FORCES_THE_CHANGE_AT) == (
        PUSH_W_IMMEDIATE, aes_boot.MEDIA_CHANGED, CLR_L_PUSH, 0x4267, PUSH_W_IMMEDIATE, BIOS_RWABS, LINE_F_TRP13)
    modes = aes_boot.driver_mode(memory) - aes_boot.DRIVE_A
    assert struct.unpack_from(">HI", BASE_IMAGE, MEDIACH_ADDS_THE_MODES_AT) == (ADDA_L_IMMEDIATE_A5, modes)
    assert struct.unpack_from(">HI", BASE_IMAGE, GETBPB_LOADS_THE_MODES_AT) == (aes_boot.MOVEA_L_IMMEDIATE_A1, modes)
    assert struct.unpack_from(">HH", BASE_IMAGE, MEDIACH_TESTS_CHANGED_AT) == (CMPI_B_A5, aes_boot.MEDIA_CHANGED)
    assert not any(lo <= aes_boot.driver_mode(memory) < lo + size for lo, size, _why in preinit_snapshot.MASK), "no byte of the mask"


def test_a_machine_whose_xbios_is_not_the_rom_s_dispatcher_is_refused():
    capture = aes_boot.preinit()
    elsewhere = make_image({0: capture.ram, addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", 0x30000)})
    with pytest.raises(Refused, match="XBIOS vector .0x30000. does not name the ROM's dispatcher"):
        aes_boot.Floppy(elsewhere, aes_boot.blank_disk())
    not_a_lea = make_image({0: capture.ram, addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", addrs.AES_ROM_GEM_ENTRY)})
    with pytest.raises(Refused, match="does not name the ROM's dispatcher"):
        aes_boot.Floppy(not_a_lea, aes_boot.blank_disk())


def test_a_machine_whose_disk_vector_names_ram_is_refused_with_the_four_routines_the_model_stands_for():
    """THE MODEL'S FOUR ENTRIES — the three disk vectors and XBIOS Floprd — are the ROM's or the model is refused: a
    vector re-pointed into RAM is named, with the count the refusal states."""
    elsewhere = make_image({0: aes_boot.preinit().ram, addrs.HDV_RWABS: struct.pack(">I", 0x30000)})
    with pytest.raises(Refused, match=f"do not name four routines of the ROM .*{aes_boot.RWABS} at 0x30000"):
        aes_boot.Floppy(elsewhere, aes_boot.blank_disk())


PRE_INIT_CAPTURES = {"the blank disk's": (aes_boot.preinit, aes_boot.blank_disk),
                     "the accessories'": (aes_boot.accessory_preinit, lambda: aes_boot.accessory_disk_of(QUIET, QUIET)),
                     "the DESKTOP.INF disk's": (aes_boot.inf_preinit, aes_boot.inf_disk_of)}


@pytest.mark.parametrize("label", PRE_INIT_CAPTURES)
def test_a_getbpb_of_the_disk_logged_in_would_rewrite_what_the_machine_holds(label):
    """WHY A SERVED Getbpb STORES NOTHING BUT THE MODE: on every capture the driver's record for drive A: is, byte for
    byte, what the ROM's Getbpb computes of THIS disk's boot sector — the nine BPB words (the flags none), the five
    geometry words, the three serial bytes — and its boot-sector buffer holds the disk's boot sector. A geometry
    word that is another's is refused as a BPB word is."""
    capture, disk = (made() for made in PRE_INIT_CAPTURES[label])
    memory = make_image({0: capture.ram})
    record, buffer = aes_boot.driver_record(memory), aes_boot.driver_boot_sector(memory)
    expected = aes_boot.bpb_of(disk) + aes_boot.record_geometry_of(disk) + accessory_disk.serial_of(disk)
    assert bytes(memory[record:record + len(expected)]) == expected and len(expected) == aes_boot.FLOPPY_RECORD_SERIAL + st_build.BOOT_SERIAL_BYTES
    assert bytes(memory[buffer:buffer + st_build.SECTOR_BYTES]) == disk[:st_build.SECTOR_BYTES]
    assert aes_boot.record_geometry_of(disk) == struct.pack(">5H", st_build.TRACKS, st_build.HEADS, st_build.SECTORS_PER_TRACK * st_build.HEADS,
                                                            st_build.SECTORS_PER_TRACK, st_build.HIDDEN_SECTORS)
    memory[record + aes_boot.FLOPPY_RECORD_GEOMETRY + 1] ^= 1          # ...the tracks, one more or less
    with pytest.raises(Refused, match="another geometry"):
        aes_boot.Floppy(memory, disk)


class Driver:
    """The model's entries called as the dispatchers' `jsr`s leave them, over a pre-init machine's megabyte."""

    def __init__(self, capture=aes_boot.preinit, disk=aes_boot.blank_disk):
        self.memory = make_image({0: capture().ram})
        self.floppy = aes_boot.Floppy(self.memory, disk())
        self._entry = {function: at for at, function in self.floppy.entries.items()}

    def call(self, function, *words):
        stack = emu.STACK_TOP
        self.memory[stack + LONG_BYTES:stack + LONG_BYTES + len(words) * WORD_BYTES] = struct.pack(f">{len(words)}H", *words)
        return self.floppy.served(self._entry[function], stack)[0]

    def floprd(self, buffer, device, sector, track, side, count):
        return self.call(aes_boot.FLOPRD, buffer >> 16, buffer & aes.WORD_MASK, 0, 0, device, sector, track, side, count)

    def mode(self):
        return self.memory[aes_boot.driver_mode(self.memory)]


BUFFER = 0x8000
A = aes_boot.DRIVE_A


def test_floprd_reads_the_sectors_of_one_side_of_one_track_or_is_refused():
    """XBIOS Floprd at the driver's own routine: `count` sectors from (track, side, sector) are the records Rwabs
    names `(track * sides + side) * sectors a track + sector - 1` on — held against the disk's own bytes for the boot
    sector, the first accessory's own sectors (the disk's first data record: track 1, side 0) and a run of the second
    side; laid in the buffer and handed to the run's ledger; and REFUSED BY NAME off the track (sector 0, a run past
    the ninth), off the disk (a third side, track 80), of no buffer, past the RAM, and of drive B."""
    driver, disk = Driver(*PRE_INIT_CAPTURES["the accessories'"]), aes_boot.accessory_disk_of(QUIET, QUIET)
    track_bytes = st_build.SECTORS_PER_TRACK * st_build.SECTOR_BYTES
    first_file = st_build.FIRST_DATA_SECTOR * st_build.SECTOR_BYTES
    assert first_file == st_build.HEADS * track_bytes, "the first data record opens track 1"
    for sector, track, side, count in ((1, 0, 0, 1), (1, 1, 0, 2), (3, 1, 1, 7)):
        assert driver.floprd(BUFFER, A, sector, track, side, count) == 0
        at = (track * st_build.HEADS + side) * track_bytes + (sector - 1) * st_build.SECTOR_BYTES
        size = count * st_build.SECTOR_BYTES
        assert bytes(driver.memory[BUFFER:BUFFER + size]) == disk[at:at + size]
        assert driver.floppy.laid_by_the_last_call() == ((BUFFER, disk[at:at + size]),) and driver.floppy.laid_by_the_last_call() == ()
        assert driver.floppy.calls[-1] == aes_boot.Call(aes_boot.FLOPRD, (BUFFER, A, sector, track, side, count), 0)
    assert any(disk[:st_build.SECTOR_BYTES]) and all(any(disk[first_file + nth * st_build.SECTOR_BYTES:][:st_build.SECTOR_BYTES])
                                                     for nth in range(2)), "sectors that say something"
    for sector, track, side, count, buffer in ((0, 0, 0, 1, BUFFER), (9, 0, 0, 2, BUFFER), (1, 0, 0, 0, BUFFER), (1, 0, 2, 1, BUFFER),
                                               (1, st_build.TRACKS, 0, 1, BUFFER), (1, 0, 0, 1, 0), (1, 0, 0, 2, RAM_BYTES - st_build.SECTOR_BYTES)):
        with pytest.raises(Refused, match="leaves the track, the disk or the RAM"):
            driver.floprd(buffer, A, sector, track, side, count)
    with pytest.raises(Refused, match="Floprd of drive 1: the model holds drive A: alone"):
        driver.floprd(BUFFER, A + 1, 1, 0, 0, 1)


def test_the_forced_change_is_stored_answered_and_ended_as_the_rom_s_driver_does():
    """THE DESK'S PROTOCOL, call by call. `Rwabs(0, NULL, 2, 0, A:)` transfers nothing and stores CHANGED in the
    driver's own mode byte; Mediach then answers CHANGED (as often as it is asked); a transfer in that state answers
    E_CHNG and moves nothing, as the ROM's does (band 6 wave 4: GEMDOS's first read after a format asks one); Getbpb
    answers the driver's record, lays the boot sector in the driver's buffer and ENDS the change — Mediach is
    UNCHANGED again. Any other mode than the forced change is refused."""
    driver = Driver()
    record, buffer = driver.floppy.record, aes_boot.driver_boot_sector(driver.memory)
    assert driver.mode() != aes_boot.MEDIA_CHANGED and driver.call(aes_boot.MEDIACH, A) == aes_boot.MEDIA_UNCHANGED
    for mode in (0, 1, 3):
        with pytest.raises(Refused, match=f"Rwabs of no buffer with the count {mode}: .* serves the forced change .2. alone"):
            driver.call(aes_boot.RWABS, 0, 0, 0, mode, 0, A)
    before = bytes(driver.memory[:RAM_BYTES])
    assert driver.call(aes_boot.RWABS, 0, 0, 0, aes_boot.MEDIA_CHANGED, 0, A) == 0 and driver.mode() == aes_boot.MEDIA_CHANGED
    differing = [at for at in range(RAM_BYTES) if driver.memory[at] != before[at]]
    stack_frame = range(emu.STACK_TOP, emu.STACK_TOP + 0x20)
    assert [at for at in differing if at not in stack_frame] == [aes_boot.driver_mode(driver.memory)], "the mode byte and nothing else"
    assert driver.floppy.laid_by_the_last_call() == ((aes_boot.driver_mode(driver.memory), bytes((aes_boot.MEDIA_CHANGED,))),)
    assert [driver.call(aes_boot.MEDIACH, A) for _ in range(2)] == [aes_boot.MEDIA_CHANGED] * 2
    driver.memory[BUFFER:BUFFER + st_build.SECTOR_BYTES] = bytes(st_build.SECTOR_BYTES)
    assert driver.call(aes_boot.RWABS, 0, BUFFER >> 16, BUFFER & aes.WORD_MASK, 1, 0, A) == addrs.E_CHNG_LONG
    assert driver.floppy.laid_by_the_last_call() == () and not any(driver.memory[BUFFER:BUFFER + st_build.SECTOR_BYTES])
    assert driver.mode() == aes_boot.MEDIA_CHANGED
    with pytest.raises(Refused, match="Getbpb of drive 1: the model holds drive A: alone"):
        driver.call(aes_boot.GETBPB, A + 1)
    driver.memory[buffer:buffer + st_build.SECTOR_BYTES] = bytes(st_build.SECTOR_BYTES)      # (so that its rewrite is seen)
    assert driver.call(aes_boot.GETBPB, A) == record and driver.mode() == aes_boot.MEDIA_UNCHANGED
    assert bytes(driver.memory[buffer:buffer + st_build.SECTOR_BYTES]) == aes_boot.blank_disk()[:st_build.SECTOR_BYTES]
    assert [at for at, _data in driver.floppy.laid_by_the_last_call()] == [buffer, aes_boot.driver_mode(driver.memory)]
    assert driver.call(aes_boot.MEDIACH, A) == aes_boot.MEDIA_UNCHANGED
    assert [call.function for call in driver.floppy.calls] == [aes_boot.MEDIACH, aes_boot.RWABS, aes_boot.MEDIACH, aes_boot.MEDIACH,
                                                               aes_boot.RWABS, aes_boot.GETBPB, aes_boot.MEDIACH]
    assert driver.floppy.calls[1].arguments == (0, 0, aes_boot.MEDIA_CHANGED, 0, A)


# ---- A DRIVE'S WINDOW, ON THE ROM'S MACHINE ---------------------------------------------------------------------------------------
ICON_IMAGE_HALF = 16                    # an icon's image is 32 pixels square: its centre, from the ICONBLK's own origin
A_DOUBLE_CLICK = (aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.ikbd(aes_boot.NO_BUTTON, 0, 0)) * 2 + (aes_boot.CLICK_TICKS,)


def drive_icon(booted, letter):
    """The centre of the image of drive `letter`'s icon on the desk of `booted`, READ OFF THE MACHINE: the object of
    its desktop tree that is an icon whose ICONBLK bears the letter, where ob_offset puts it."""
    tree = booted.long(aes.AES_GL_NEWDESK) & BUS
    assert tree == (booted.long(aes.AES_DESK_GLOBALS) & BUS) + aes_event.DESK_OBJECTS, "the desktop's tree is the desk's block's objects"
    found = []
    for index in range(aes_event.DESK_OBJECT_COUNT):
        thing = tree + index * aes.OB_BYTES
        block = booted.long(thing + aes.OB_SPEC) & BUS
        if booted.word(thing + aes.OB_TYPE) & aes.OB_TYPE_MASK == aes.G_ICON and booted.word(block + aes.IB_CHAR) & aes.BYTE_MASK == ord(letter):
            x, y = aes_objects.screen_origin(booted.ram, tree, index)
            found.append((x + booted.word(block + aes.IB_XICON) + ICON_IMAGE_HALF, y + booted.word(block + aes.IB_YICON) + ICON_IMAGE_HALF))
    point, = found
    return point


@functools.cache
def window_of(booted, letter="A"):
    """`booted` continued through a double click on drive `letter`'s icon: the machine at the next idle."""
    return booted.continued(aes_boot.mouse_to(*drive_icon(booted, letter)), *A_DOUBLE_CLICK)


WINDOW_MACHINES = {"the desk alone": aes_boot.desk_machine, "two quiet accessories": aes_boot.accessory_machine,
                   "the DESKTOP.INF machine, as icons": inf, "the DESKTOP.INF machine, as text": lambda: inf(TEXT)}
ITEMS_ON_THE_DISK = {"the desk alone": 0, "two quiet accessories": 2, "the DESKTOP.INF machine, as icons": 1, "the DESKTOP.INF machine, as text": 1}
FSFIRST, FSNEXT = 0x4e, 0x4f


@pytest.mark.parametrize("label", WINDOW_MACHINES)
def test_a_drive_s_window_opens_on_the_rom_s_machine_through_the_driver_s_four_entries(label):
    """RULING W4-R8, ON THE ROM'S MACHINE: a double click on drive A:'s icon and the run to the next idle — the ROM's
    own desk, GEMDOS and BIOS, with the driver answered at its entries IN THE DESK'S OWN ORDER: Floprd of the boot
    sector into a block of the desk's, the forced change, Mediach answered CHANGED, Getbpb, then the root's sectors
    read and Mediach UNCHANGED from there on. NO HARDWARE IS TOUCHED (no FDC register, no PSG port, no MFP bit — the
    refusal the design's probe met is gone), nothing is stored in the harness's window, the run ends at the ROM's
    idle with the desk's block walked: no USERBLK but in the text view."""
    booted = WINDOW_MACHINES[label]()
    window = window_of(booted)
    calls = window.boot.floppy
    assert [call.function for call in calls[:4]] == [aes_boot.FLOPRD, aes_boot.RWABS, aes_boot.MEDIACH, aes_boot.GETBPB]
    buffer, *read = calls[0].arguments
    assert read == [A, 1, 0, 0, 1] and buffer, "the boot sector, one sector, into a block of the desk's own"
    assert calls[1].arguments == (0, 0, aes_boot.MEDIA_CHANGED, 0, A) and calls[2].answer == aes_boot.MEDIA_CHANGED
    assert calls[3].answer == aes_boot.driver_record(window.image())
    rest = calls[4:]
    assert rest and {call.function for call in rest} == {aes_boot.RWABS, aes_boot.MEDIACH}
    assert all(call.answer == aes_boot.MEDIA_UNCHANGED for call in rest if call.function == aes_boot.MEDIACH)
    assert all(call.arguments[1] and not call.arguments[0] & aes_boot.RWABS_WRITE for call in rest if call.function == aes_boot.RWABS)
    assert window.ram[aes_boot.driver_mode(window.image())] == aes_boot.MEDIA_UNCHANGED
    assert window.boot.disk == booted.boot.disk, "nothing written to the disk"
    assert not window.boot.hardware_reads and not window.boot.hardware_writes and not window.boot.io_reads
    assert window.idle == aes_boot.THE_ROM_S and len(window.waiting()) == len(booted.waiting())
    harness_window = aes_boot.harness_window(aes_boot.ours_of(isr.blob_named(next(iter(isr.BLOBS)))))
    assert not any(aes_boot._stored_within(window.boot.stored, lo, hi) for lo, hi in harness_window.values())
    walked = aes_event.userblk_slots(window.ram)
    assert len(walked) == (ITEMS_ON_THE_DISK[label] if "as text" in label else 0)
    assert aes_event.userblk_slots(booted.ram) == (), "no window, no item"


def test_a_double_click_on_drive_b_is_refused_by_name():
    """The model holds drive A: alone, and says so where the desk asks the other: drive B:'s icon (on a machine with
    one drive the ROM would ask for the other disk — a hand's)."""
    with pytest.raises(Refused, match="Floprd of drive 1: the model holds drive A: alone"):
        window_of(aes_boot.desk_machine(), "B")


# ---- ub_trampoline's ARRIVALS, AND THE DESK'S USERBLKS WALKED ---------------------------------------------------------------------
def holders_of(machine, value):
    """Every longword at an even address of `machine` that holds `value`: the brute read the walk is held to."""
    return [at for at in range(0, RAM_BYTES - LONG_BYTES + WORD_BYTES, WORD_BYTES) if case.long_in(machine.ram, at) == value]


def test_the_desk_s_userdef_set_up_is_read_out_of_the_rom_s_own_instructions():
    """THE WALK'S TWO OFFSETS AND ITS BOUND, held to the ROM: the desk's item objects begin where `$fe3066` stores the
    type G_USERDEF less the type's own offset, its USERBLKs where `$fe3094` copies `$8c32`; the objects run to the
    block's end (133 of them: desk_alloc's 19,094 bytes), and the USERBLKs of as many end below the objects."""
    assert aes_event.DESK_GLOBALS_BYTES == struct.unpack_from(">I", BASE_IMAGE, addrs.AES_ROM_DESK_ALLOC + 6)[0]
    assert aes_event.DESK_OBJECTS + aes_event.DESK_OBJECT_COUNT * aes.OB_BYTES == aes_event.DESK_GLOBALS_BYTES
    assert aes_event.DESK_USERBLKS + aes_event.DESK_OBJECT_COUNT * aes.UB_BYTES <= aes_event.DESK_OBJECTS
    assert rom_long(aes_event.DESK_COPIES_THE_TRAMPOLINE_AT + WORD_BYTES) == aes.AES_USERDEF_TRAMPOLINE
    assert rom_long(aes_event.USERBLK_TRAMPOLINE_STORED_AT + WORD_BYTES) == aes_event.USERBLK_TRAMPOLINE


def test_a_text_window_s_item_is_drawn_through_the_trampoline_once_and_its_userblk_is_walked():
    """THE TRAMPOLINE'S ARRIVALS, COUNTED, on the ROM's machine: the INF machine in the text view, drive A:'s window
    opened — its one item (the DESKTOP.INF itself) is a G_USERDEF object, the desk copies `$8c32` into its USERBLK
    and its draw arrives at ub_trampoline EXACTLY ONCE, handed that object and that USERBLK's parameter. In the icon
    view: no arrival. THE WALK FINDS THE SLOT, and it is where the machine keeps the trampoline's address: every
    longword of the megabyte that holds it is `$8c32`, the walked USERBLK — or one dead one, on the desk's own stack
    below its parked stack pointer (the draw's frame)."""
    text, icons = window_of(inf(TEXT)), window_of(inf(ICONS))
    assert icons.observed == () and aes_event.userblk_slots(icons.ram) == ()
    (name, (thing, parameter)), = text.observed
    (_none, slot), = aes_event.userblk_slots(text.ram)
    block = text.long(aes.AES_DESK_GLOBALS) & BUS
    assert name == aes_boot.TRAMPOLINE and slot == block + aes_event.DESK_USERBLKS + thing * aes.UB_BYTES + aes.UB_CODE
    assert text.long(slot) == aes_event.USERBLK_TRAMPOLINE and text.long(slot - aes.UB_CODE + aes.UB_PARM) == parameter
    assert text.word(block + aes_event.DESK_OBJECTS + thing * aes.OB_BYTES + aes.OB_TYPE) & aes.OB_TYPE_MASK == aes.G_USERDEF
    assert aes_event.slots_over(aes_event.USERBLK_TRAMPOLINE_SLOT, text.ram) == (aes.AES_USERDEF_TRAMPOLINE, slot)
    assert aes_event.slots_over(aes_event.USERBLK_TRAMPOLINE_SLOT, inf(TEXT).ram) == (aes.AES_USERDEF_TRAMPOLINE,)
    holders = holders_of(text, aes_event.USERBLK_TRAMPOLINE)
    desk = text.static_processes()[0]
    dead = [at for at in holders if at not in (aes.AES_USERDEF_TRAMPOLINE, slot)]
    assert set(holders) >= {aes.AES_USERDEF_TRAMPOLINE, slot} and len(dead) <= 1
    assert all(desk.uda + aes.UDA_STATE_BYTES <= at < text.long(desk.uda + aes.UDA_SUPER_SP) & BUS for at in dead)
    assert holders_of(icons, aes_event.USERBLK_TRAMPOLINE) == [aes.AES_USERDEF_TRAMPOLINE]


def test_the_walk_takes_an_object_only_with_the_userblk_of_its_own_index():
    """THE WALK'S TEETH, on labelled crafted megabytes of the text window's machine: an object whose type is no longer
    G_USERDEF, one whose ob_spec names ANOTHER index's USERBLK, and a block pointer that is null or names no block of
    the machine (nothing there is an object) each walk to nothing; an object beside it given the type and its own
    USERBLK is walked too."""
    text = window_of(inf(TEXT))
    (_none, slot), = aes_event.userblk_slots(text.ram)
    block = text.long(aes.AES_DESK_GLOBALS) & BUS
    thing = (slot - block - aes_event.DESK_USERBLKS) // aes.UB_BYTES
    at = block + aes_event.DESK_OBJECTS + thing * aes.OB_BYTES

    def walked(pokes):
        ram = bytearray(text.ram)
        for where, data in pokes.items():
            ram[where:where + len(data)] = data
        return aes_event.userblk_slots(ram)

    assert walked({at + aes.OB_TYPE: struct.pack(">H", aes.G_ICON)}) == ()
    assert walked({at + aes.OB_SPEC: struct.pack(">I", slot + aes.UB_BYTES)}) == ()
    assert walked({aes.AES_DESK_GLOBALS: bytes(LONG_BYTES)}) == () == walked({aes.AES_DESK_GLOBALS: struct.pack(">I", RAM_BYTES - 0x100)})
    beside = {at + aes.OB_BYTES + aes.OB_TYPE: struct.pack(">H", aes.G_USERDEF),
              at + aes.OB_BYTES + aes.OB_SPEC: struct.pack(">I", slot + aes.UB_BYTES)}
    assert walked(beside) == ((None, slot), (None, slot + aes.UB_BYTES))
    assert aes_event.userblk_slots(stopped_at(aes_boot.preinit(), aes_boot.blank_disk(), addrs.AES_ROM_DESK_ALLOC).ram) == (), "before desk_alloc"


# ---- THE SERVED DOOR ------------------------------------------------------------------------------------------------------------
DESKMAIN, GEM_MAIN, SH_CMD, DOS_EXEC = addrs.AES_ROM_DESKMAIN, addrs.AES_ROM_GEM_MAIN, addrs.AES_ROM_SH_CMD, addrs.AES_ROM_DOS_EXEC
SHOW_FILE = addrs.AES_ROM_DESK_SHOW_FILE
LINE_F_TABLE = aes.AES_LINEF_TABLE      # the Line-F handler's call table: a longword for each call word's low twelve bits
LINE_F_CALL_INDEX = 0x0ffc
SH_MAIN_AFTER_DOS_EXEC, SH_CMD_S_TAIL = 0xfeb2ac, 0xc42f            # dos_exec's return into sh_main; `lea $c42f,a5` ($feb30a)
SHELL_COMMAND, SHELL_TAIL, SHELL_TAIL_BYTE = 0xc79e, 0xc82a, 0xc42e      # the shell's command and tail pointers; the tail's first byte
VDI_S_OWN_TRAP, OLD_CRITIC = 0x8c2a, aes.AES_OLD_CRITIC
LINE_F_VECTOR = 0x2c
# The usable-disk word (`aes/loader.h`): gem_entry stores 1 there before its loop ($fd9f64), and ON THE FIRST PASS
# ALONE the loop's `jsr` of size_theglo pushes its return address over it — the first stack's top; gem_main is first
# entered with that address's low word in it. The loop's `bra` comes back with SP = A6 = PD0's top, so EVERY LATER
# PASS's `jsr` pushes on PD0's stack and the word is what the desk last stored: 0 or 1 ($fe2a62 / $fe2a6a).
USABLE_DISK_WORD = aes.header_constants("loader.h")["AES_DISK_USABLE"]
SIZE_THEGLO = addrs.AES_ROM_SIZE_THEGLO
SIZE_THEGLO_RETURNS_TO = 0xfd9f78       # ($fd9f72 jsr $fee800; `aes_geminit` holds the same to the ROM's bytes)
DESK_CLEARS_THE_WORD_AT, DESK_SETS_THE_WORD_AT = 0xfe2a62, 0xfe2a6a
CLR_W_ABSOLUTE_LONG, MOVE_W_IMMEDIATE_ABSOLUTE_LONG = 0x4279, 0x33fc
AN_INTERRUPTED_PC_OF_HATARI_S_BOOTS = 0x00fd9f82          # the clear loop's `dbmi`: what kept captures hold at `$8990`
SHOW_FILE_BYTE = 0xfe


def test_each_routine_the_door_serves_is_called_by_the_shell_once_by_a_line_f_word():
    """`SERVED_ROUTINES`, HELD TO THE ROM: the word at each declared site is a Line-F CALL whose table entry is the
    routine — deskmain from sh_main, the four built-ins from sh_cmd's four arms — and no other word of the shell
    (sh_main and sh_cmd, `$feb0e6..$feb3c0`) calls any of them."""
    shell = range(addrs.AES_ROM_SH_MAIN, addrs.AES_ROM_SH_CMD + 0xc4, WORD_BYTES)
    for routine, (name, site) in aes_boot.SERVED_ROUTINES.items():
        word = rom_word(site)
        assert word >> 12 == 0xf and not word & 1 and rom_long(LINE_F_TABLE + (word & LINE_F_CALL_INDEX)) == routine, name
        assert [at for at in shell if rom_word(at) == word] == [site], f"{name}: one call in the shell"
    assert len({name for name, _site in aes_boot.SERVED_ROUTINES.values()}) == len(aes_boot.SERVED_ROUTINES) == 5


@functools.cache
def at_deskmain(label="the desk's"):
    """The ROM's own boot STOPPED AT deskmain's ENTRY — of the desk's capture, or the DESKTOP.INF machine's."""
    capture, disk = (aes_boot.preinit(), aes_boot.blank_disk()) if label == "the desk's" else (aes_boot.inf_preinit(), aes_boot.inf_disk_of())
    return stopped_at(capture, disk, DESKMAIN)


@pytest.mark.parametrize("label", ("the desk's", "the DESKTOP.INF machine's"))
def test_deskmain_answered_0_runs_the_teardown_and_gem_entry_s_second_pass(label):
    """THE ROAD NO MACHINE TAKES, by the served door on the ROM's own machine: deskmain answered 0 at its entry —
    sh_main's loop ends, gem_main's TEARDOWN runs (giveerr and restore_trap2 put the BIOS's handler back in `$404` and
    the VDI's own entry in `$88`: the values the AES saved), gem_main returns, gem_entry loops and ENTERS gem_main A
    SECOND TIME — on the same stack pointer and frame register as the first, the Line-F vector
    still the copy the first pass made (the `$2c` test's skip arm: no second Malloc). WHAT `$8992` HOLDS THERE is the
    next test's: it is whatever the desk left, and this door never ran the desk. THE MACHINE IS LABELLED: one
    `Served`, deskmain, 0."""
    first = at_deskmain(label)
    capture, disk = (aes_boot.preinit(), aes_boot.blank_disk()) if label == "the desk's" else (aes_boot.inf_preinit(), aes_boot.inf_disk_of())
    entered = stopped_at(capture, disk, GEM_MAIN)
    again = aes_boot.served(first, 0, until=GEM_MAIN)
    assert again.served == (aes_boot.Served("deskmain", DESKMAIN, 0, ()),) and first.served == () and again.idle is None
    assert {name: again.registers[name] for name in ("pc", "isp", "a6", "sr")} == {name: entered.registers[name] for name in ("pc", "isp", "a6", "sr")}
    # ...BUT IT IS ANOTHER ENTRY THAN THE FIRST (the design's risk 9): `rlr` still names the shell's PD where the first
    # pass entered with none — our gem_main must not read it before it stores it.
    assert case.long_in(again.ram, aes.AES_RLR) == aes.SHELL_PD and case.long_in(entered.ram, aes.AES_RLR) == 0
    copy = case.long_in(first.ram, LINE_F_VECTOR)
    assert case.long_in(again.ram, LINE_F_VECTOR) == copy and not copy >> 24 and case.long_in(entered.ram, LINE_F_VECTOR) == copy
    assert case.long_in(again.ram, addrs.VECTOR_TRAP_GEM) == case.long_in(first.ram, VDI_S_OWN_TRAP) != addrs.GEM_TRAP2
    assert case.long_in(again.ram, aes_event.ETV_CRITIC) == case.long_in(first.ram, OLD_CRITIC) != addrs.AES_ROM_CRIT_ERR
    assert case.long_in(first.ram, addrs.VECTOR_TRAP_GEM) == addrs.GEM_TRAP2 and case.long_in(first.ram, aes_event.ETV_CRITIC) == addrs.AES_ROM_CRIT_ERR
    # ...AND THE SECOND PASS IS A WHOLE INIT: it arrives at deskmain again, on the stack pointer the first did — a boot
    # stopped there, to be served again (the label then two long).
    second = aes_boot.served(first, 0, until=DESKMAIN)
    assert (second.registers["pc"], second.registers["isp"]) == (DESKMAIN, first.registers["isp"]) and len(second.served) == 1
    assert case.long_in(second.ram, addrs.VECTOR_TRAP_GEM) == addrs.GEM_TRAP2, "the second pass took the trap again"
    twice = aes_boot.served(second, 0, until=GEM_MAIN)
    assert [each.routine for each in twice.served] == ["deskmain"] * 2 and twice.registers["isp"] == entered.registers["isp"]


def test_on_the_served_machine_only_the_usable_disk_word_is_the_first_pass_s_at_gem_main_s_second_entry():
    """`$8992` AT gem_main's SECOND ENTRY IS WHAT THE FIRST PASS LEFT THERE — NOTHING PUSHES OVER IT AGAIN. The first
    pass's `jsr` of size_theglo runs on gem_entry's first stack and lays its return address at `$8990`; the loop's
    `bra` comes back with SP = A6 = PD0's top, so the SECOND pass's `jsr` pushes on PD0's stack, where gem_main's own
    return address will lie. The real desk stores the word itself — 0 where a GEMDOS call on the current drive fails,
    1 where one succeeds (held to the ROM's two instructions) — so on a real second pass it is the desk's 0 or 1.

    ON THE SERVED MACHINE ONLY (a labelled argument class, W4-R6: deskmain is ANSWERED AT ITS ENTRY, the desk never
    ran) the longword is still the first pass's `$00fd9f78`. And A LABELLED CRAFT says the second pass does not push
    there: the desk's 0, its 1 and the interrupted PC Hatari's boots hold, each poked at deskmain's entry, are each
    still there at the second gem_main."""
    capture, disk, first, at = aes_boot.preinit(), aes_boot.blank_disk(), at_deskmain(), USABLE_DISK_WORD - WORD_BYTES
    entered, on_the_first_stack = stopped_at(capture, disk, GEM_MAIN), stopped_at(capture, disk, SIZE_THEGLO)
    assert on_the_first_stack.registers["isp"] == at, "the first pass's jsr pushes over the word"
    assert case.long_in(on_the_first_stack.ram, at) == SIZE_THEGLO_RETURNS_TO
    second_pass = aes_boot.served(first, 0, until=SIZE_THEGLO)
    assert second_pass.registers["isp"] == entered.registers["isp"] != at, "the second pass's pushes where gem_main's will: PD0's stack"
    assert case.long_in(second_pass.ram, second_pass.registers["isp"]) == SIZE_THEGLO_RETURNS_TO
    assert struct.unpack_from(">HI", BASE_IMAGE, DESK_CLEARS_THE_WORD_AT) == (CLR_W_ABSOLUTE_LONG, USABLE_DISK_WORD)
    assert struct.unpack_from(">HHI", BASE_IMAGE, DESK_SETS_THE_WORD_AT) == (MOVE_W_IMMEDIATE_ABSOLUTE_LONG, 1, USABLE_DISK_WORD)
    # THE SERVED MACHINE ONLY: nothing between the first pass's push and the second entry stored there.
    again = aes_boot.served(first, 0, until=GEM_MAIN)
    assert case.long_in(again.ram, at) == case.long_in(entered.ram, at) == case.long_in(first.ram, at) == SIZE_THEGLO_RETURNS_TO
    # THE LABELLED CRAFT: what a desk that ran, or a boot that took an interrupt up there, would have left.
    for left in (SIZE_THEGLO_RETURNS_TO & ~aes.WORD_MASK, SIZE_THEGLO_RETURNS_TO & ~aes.WORD_MASK | 1, AN_INTERRUPTED_PC_OF_HATARI_S_BOOTS):
        ram = bytearray(first.ram)
        ram[at:at + LONG_BYTES] = struct.pack(">I", left)
        crafted = aes_boot.served(first._replace(ram=bytes(ram)), 0, until=GEM_MAIN)
        assert crafted.registers["pc"] == GEM_MAIN and case.long_in(crafted.ram, at) == left, f"{left:#x} did not survive to the second entry"


def shel_write(command, tail):
    """THE ROM'S OWN shel_write(1, 1, 0, command, tail) as the served door calls it over a stopped machine: the two
    strings staged in the call's image alone."""
    pokes = case.merge_pokes(od.string_pokes(command, at=shell_buf.BUFFER, room=0x80), od.string_pokes(tail, at=shell_buf.SECOND, room=0x80))
    return shell_buf.SH_WRITE, (1, 1, 0, shell_buf.BUFFER, shell_buf.SECOND), pokes


THE_INF_ITSELF = accessory_disk.INF_NAME.encode()


def test_deskmain_answered_a_launch_after_a_real_shel_write_reaches_dos_exec_s_entry():
    """THE LAUNCH PASS, by the served door: on the INF machine stopped at deskmain, THE ROM'S OWN shel_write is CALLED
    over the machine (the command a file the disk holds — the DESKTOP.INF itself — and no tail: never a poke of the
    shell's buffers), deskmain answered 1: sh_main's next pass runs sh_cmd's default arm (the tail's first byte is no
    built-in's), sh_find finds the file, and dos_exec is ENTERED — the checkpoint: its return into sh_main, the
    command, mode 0 and the tail on its frame, on the stack pointer the design read off the listing (six bytes under
    deskmain's). The label says what was done: deskmain, 1, after AES_ROM_SH_WRITE."""
    first = at_deskmain("the DESKTOP.INF machine's")
    asked = aes_boot.served(first, 1, until=SH_CMD, calls=(shel_write(THE_INF_ITSELF, b""),))
    assert asked.registers["isp"] == first.registers["isp"] and asked.ram[SHELL_TAIL_BYTE] == 0
    launched = aes_boot.served(first, 1, until=DOS_EXEC, calls=(shel_write(THE_INF_ITSELF, b""),))
    sp, command, tail = launched.registers["isp"], case.long_in(launched.ram, SHELL_COMMAND), case.long_in(launched.ram, SHELL_TAIL)
    assert sp == first.registers["isp"] - LONG_BYTES - WORD_BYTES
    assert struct.unpack_from(">IIHI", launched.ram, sp) == (SH_MAIN_AFTER_DOS_EXEC, command, 0, tail) and tail == SHELL_TAIL_BYTE
    assert bytes(launched.ram[command:command + len(THE_INF_ITSELF) + 1]) == THE_INF_ITSELF + b"\0"
    assert launched.served == (aes_boot.Served("deskmain", DESKMAIN, 1, (shell_buf.SH_WRITE,)),)
    assert bytes(first.ram[command:command + len(THE_INF_ITSELF)]) != THE_INF_ITSELF, "the buffer is shel_write's doing"


def test_a_launch_of_a_file_the_disk_does_not_hold_never_reaches_dos_exec():
    """...and where sh_find finds nothing (the blank disk: the same call, the same answer) dos_exec is never entered:
    refused by name at the first idle — the shell's own error alert, the desk's process waiting in it."""
    with pytest.raises(Refused, match=f"reached its first idle and never arrived at {DOS_EXEC:#x}"):
        aes_boot.served(at_deskmain(), 1, until=DOS_EXEC, calls=(shel_write(THE_INF_ITSELF, b""),))
    alert = aes_boot.Machine(aes_boot.served(at_deskmain(), 1, calls=(shel_write(THE_INF_ITSELF, b""),)))
    assert alert.idle == aes_boot.THE_ROM_S and alert.served[0].answer == 1 and len(alert.waiting()) == 2
    # THE LABEL IS CARRIED THROUGH A CONTINUATION: a machine made through the door stays one.
    assert alert.continued().served == alert.served and aes_boot.desk_machine().served == ()


def test_a_built_in_of_the_shell_is_served_at_its_entry_and_the_shell_goes_back_to_the_desk():
    """A UTILITY, served: shel_write's tail beginning `$fe`, deskmain answered 1 — sh_cmd's `$fe` arm calls the desk's
    "show a file" with the tail past its command byte (`$c42f`), from its one site; that routine ANSWERED AT ITS ENTRY
    (its answer is not read: sh_cmd answers 1 whatever), the shell goes back to the desk: deskmain is entered again,
    on the stack pointer of the first time. Two labels, in order."""
    first = at_deskmain("the DESKTOP.INF machine's")
    shown = aes_boot.served(first, 1, until=SHOW_FILE, calls=(shel_write(THE_INF_ITSELF, bytes((SHOW_FILE_BYTE,)) + THE_INF_ITSELF),))
    sp = shown.registers["isp"]
    assert shown.ram[SHELL_TAIL_BYTE] == SHOW_FILE_BYTE
    assert struct.unpack_from(">II", shown.ram, sp) == (aes_boot.SERVED_ROUTINES[SHOW_FILE][1] + WORD_BYTES, SH_CMD_S_TAIL)
    back = aes_boot.served(shown, 0, until=DESKMAIN)
    assert (back.registers["pc"], back.registers["isp"]) == (DESKMAIN, first.registers["isp"])
    assert [(each.routine, each.answer) for each in back.served] == [("deskmain", 1), (aes_boot.SERVED_ROUTINES[SHOW_FILE][0], 0)]


def crafted(boot, registers=None, pokes=None):
    """A LABELLED CRAFTED BOOT for a refusal: `boot` with some registers or bytes replaced."""
    ram = bytearray(boot.ram)
    for at, data in (pokes or {}).items():
        ram[at:at + len(data)] = data
    return boot._replace(ram=bytes(ram), registers={**boot.registers, **(registers or {})})


def test_what_the_served_door_refuses_each_by_name():
    """THE DOOR'S REFUSALS: a boot that stands at an idle, or stopped at a routine the door does not serve; a routine
    entered in user mode; a caller that is not the shell (the return address neither the ROM's site nor in a blob); an
    answer that is no word; A SECOND ARRIVAL at a served routine before `until` (deskmain answered 0 with no stop
    named: the second pass would RUN the ROM's deskmain under a label that says it was served); and the first idle
    before `until`."""
    first = at_deskmain()
    with pytest.raises(Refused, match="THE SERVED DOOR ANSWERS A ROUTINE AT ITS ENTRY: this boot stands at .*, the idle of the ROM's dispatcher"):
        aes_boot.served(aes_boot.desk_machine().boot, 0)
    with pytest.raises(Refused, match=f"this boot stands at {GEM_MAIN:#x} — at none of"):
        aes_boot.served(stopped_at(aes_boot.preinit(), aes_boot.blank_disk(), GEM_MAIN), 0)
    with pytest.raises(Refused, match="deskmain is entered in user mode"):
        aes_boot.served(crafted(first, {"sr": first.registers["sr"] & ~preinit_snapshot.SR_SUPERVISOR}), 0)
    elsewhere = struct.pack(">I", addrs.AES_ROM_SH_MAIN)
    with pytest.raises(Refused, match=f"deskmain was not called by the shell: it would return to {addrs.AES_ROM_SH_MAIN:#x}"):
        aes_boot.served(crafted(first, pokes={first.registers["isp"]: elsewhere}), 0)
    for answer in (0x10000, -0x8001):
        with pytest.raises(Refused, match="deskmain answers a word"):
            aes_boot.served(first, answer)
    with pytest.raises(Refused, match="THE RUN ARRIVED AT deskmain AGAIN before an idle"):
        aes_boot.served(first, 0)
    with pytest.raises(Refused, match=f"THE RUN ARRIVED AT deskmain AGAIN before {DOS_EXEC:#x}"):
        aes_boot.served(first, 0, until=DOS_EXEC)
    with pytest.raises(Refused, match=f"reached its first idle and never arrived at {GEM_MAIN:#x}"):
        aes_boot.served(first, 1, until=GEM_MAIN)
    assert aes_boot.served(first, -1, until=SH_CMD).served[0].answer == aes.WORD_MASK, "a negative word is a word"


@every_blob
def test_the_served_door_on_a_takeover_machine_calls_no_routine_and_a_door_the_teardown_gives_back_is_refused(blob):
    """ON A MACHINE WHOSE BLOB IS OURS (a takeover: the screen manager's, and behind THE DOOR) the served door
    answers deskmain as on the ROM's — the caller is the ROM's sh_main still — and says two things by name: a routine
    CALLED over the machine first is refused (on a takeover nothing has said whose it would be; on an OUR-BOOT machine
    it is the ROM's, the desk's own call: `test_aes_ourboot.py`); and behind a door the
    teardown's own giveerr and restore_trap2 — the ROM's gem_main's, on a takeover machine — hand `$404` and `$88`
    back (and its vex_timv the VDI's tick vector): THE DOOR IS NO LONGER OURS, refused where the served run ends and
    never silently lost (the design's risk 7 — a takeover's door is a claim about a machine at an idle of its desk)."""
    capture, disk = aes_boot.preinit(), aes_boot.blank_disk()
    taken = aes_boot.booted(capture, disk, until=DESKMAIN, ours=aes_boot.ours_of(isr.blob_named(blob)))
    with pytest.raises(Refused, match="a routine called over a TAKEOVER machine, before deskmain is answered"):
        aes_boot.served(taken, 1, until=SH_CMD, calls=(shel_write(THE_INF_ITSELF, b""),))
    again = aes_boot.served(taken, 0, until=GEM_MAIN)
    assert again.served[0].routine == "deskmain" and again.takeover.ours == taken.takeover.ours
    behind = aes_boot.booted(capture, disk, until=DESKMAIN, ours=aes_boot.ours_of(isr.blob_named(blob), aes_event.THE_DOOR))
    with pytest.raises(Refused, match="THE DOOR IS NO LONGER OURS where the served run ends"):
        aes_boot.served(behind, 0, until=GEM_MAIN)


# ---- THE OUR-BOOT MACHINE'S PREMISES, AGAINST THE ROM'S OWN RUN ---------------------------------------------------------------------
OUR_BOOT_DISKS = {"the blank disk": (aes_boot.preinit, aes_boot.blank_disk), "the DESKTOP.INF disk": (aes_boot.inf_preinit, aes_boot.inf_disk_of),
                  "the DESKTOP.INF disk, as text and another resolution": (aes_boot.inf_preinit, lambda: aes_boot.inf_disk_of(TEXT, CHANGED))}


@functools.cache
def ours_of(blob):
    return aes_boot.ours_of(isr.blob_named(blob))


@every_blob
@pytest.mark.parametrize("label", OUR_BOOT_DISKS)
def test_labelled_staging_the_our_boot_machine_s_premises_hold_and_its_lay_boots_on_the_disks_without_an_accessory(label, blob):
    """RULING W4-R1's PREMISES, MEASURED ON THE ROM'S SIDE for both blobs: the capture stands at gem_entry in user
    mode; the window the harness uses — the blob's span, the staging band, the stack band — is zero there; and THE
    ROM'S OWN BOOT of that machine and disk stores NOT ONE BYTE in it before its first idle. AND THE LAY IS MADE THERE
    (slice B: a LABELLED STAGING — `test_aes_ourboot.py` holds the machine): the blob's own gem_entry reaches
    deskmain's entry, not one cycle of the ROM's GEM text nor of its Line-F handler's copy on the way."""
    capture, disk = (made() for made in OUR_BOOT_DISKS[label])
    ours = ours_of(blob)
    window = aes_boot.vet_ours_can_be_laid_at_gem_entry(capture, disk, ours)
    assert window == aes_boot.harness_window(ours) and set(window) == {aes_boot.THE_BLOB, aes_boot.STAGING_BAND, aes_boot.STACK_BAND}
    assert window[aes_boot.THE_BLOB] == (ours.base, ours.end) and window[aes_boot.STACK_BAND] == (emu.STACK_GUARD_LO, emu.STACK_BAND_HI)
    spans = sorted(window.values())
    assert all(hi <= lo_after for (_lo, hi), (lo_after, _hi) in zip(spans, spans[1:])), "three spans apart"
    ours_booted = aes_boot.booted(capture, disk, until=aes_boot.deskmain_entry(ours), ours=ours, laid=aes_boot.AT_GEM_ENTRY)
    assert ours_booted.our_boot.ours == ours and ours_booted.our_boot.ran[0] > 0 and ours_booted.our_boot.ran[1:] == (0, 0)


@every_blob
def test_over_a_disk_with_an_accessory_the_rom_s_own_boot_clears_the_window_and_the_lay_is_refused(blob):
    """RULING W4-R2, AS THE REFUSAL IT IS: on the accessories' capture the window is zero at the stop too — and the
    ROM's own boot stores at EVERY BYTE of the blob's span before its first idle (the loader's `Pexec(3)` clears the
    largest free block). The vet says so with the count, and `booted(..., laid=AT_GEM_ENTRY)` is refused FOR THAT:
    no accessory disk has an our-boot machine, and the blob is never put back after a clear."""
    capture, disk, ours = aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(QUIET, QUIET), ours_of(blob)
    said = rf"THE ROM'S OWN BOOT OF THIS DISK STORES AT {ours.end - ours.base} BYTE\(S\) OF the blob's own span"
    with pytest.raises(Refused, match=said):
        aes_boot.vet_ours_can_be_laid_at_gem_entry(capture, disk, ours)
    with pytest.raises(Refused, match=said):
        aes_boot.booted.derive(capture, disk, ours=ours, laid=aes_boot.AT_GEM_ENTRY)


def test_each_premise_of_the_our_boot_machine_is_refused_by_name_where_it_fails():
    """THE VET'S TEETH, on labelled crafted captures: a PC that is not gem_entry; an `exec_os` that names another
    routine; a capture in supervisor mode; one byte in each span of the window, at its first and at its last address;
    a boot whose write ledger saturates (the seven accessories': what it stores is not known); a lay asked with no
    blob, and one handed a door (the harness maps no longword of the our-boot machine)."""
    capture, disk = aes_boot.preinit(), aes_boot.blank_disk()
    ours = ours_of(next(iter(isr.BLOBS)))

    def vet(**changed):
        return aes_boot.vet_ours_can_be_laid_at_gem_entry(capture._replace(**changed), disk, ours)

    with pytest.raises(Refused, match="not gem_entry"):
        vet(registers={**capture.registers, "pc": addrs.AES_ROM_GEM_MAIN})
    exec_os_elsewhere = bytearray(capture.ram)
    exec_os_elsewhere[preinit_snapshot.EXEC_OS:preinit_snapshot.EXEC_OS + LONG_BYTES] = struct.pack(">I", addrs.AES_ROM_GEM_MAIN)
    with pytest.raises(Refused, match=f"its exec_os names {addrs.AES_ROM_GEM_MAIN:#x}: not gem_entry"):
        vet(ram=bytes(exec_os_elsewhere))
    with pytest.raises(Refused, match="stands at gem_entry in supervisor mode"):
        vet(registers={**capture.registers, "sr": capture.registers["sr"] | preinit_snapshot.SR_SUPERVISOR})
    for what, (lo, hi) in aes_boot.harness_window(ours).items():
        for at in (lo, hi - 1):
            ram = bytearray(capture.ram)
            ram[at] = 0xa5
            with pytest.raises(Refused, match=f"THE WINDOW IS NOT ZERO AT THE STOP: {what} .* holds something from {at:#x}"):
                vet(ram=bytes(ram))
        beside = bytearray(capture.ram)
        beside[lo - 1] = beside[hi] = 0xa5      # ...and a byte on either side of it is not the window's
        assert vet(ram=bytes(beside))
    seven = (aes_boot.seven_accessory_preinit(), aes_boot.seven_accessory_disk_of(*(QUIET,) * len(aes_boot.SEVEN_ACCESSORY_NAMES)))
    with pytest.raises(Refused, match="saturated its write ledger: what it stores in the window is not known"):
        aes_boot.vet_ours_can_be_laid_at_gem_entry(*seven, ours)
    with pytest.raises(Refused, match="nothing is laid at gem_entry.* without a blob"):
        aes_boot.booted.derive(capture, disk, laid=aes_boot.AT_GEM_ENTRY)
    with pytest.raises(Refused, match="is handed NO DOOR: the harness maps no longword of the our-boot machine"):
        aes_boot.booted.derive(capture, disk, ours=aes_boot.ours_of(isr.blob_named(next(iter(isr.BLOBS))), aes_event.THE_DOOR),
                               laid=aes_boot.AT_GEM_ENTRY)


def test_the_stores_counted_in_a_span_are_the_runs_bytes_inside_it():
    assert aes_boot._stored_within(((0x10, 0x10), (0x30, 4), (0x100, 1)), 0x18, 0x32) == 8 + 2
    assert aes_boot._stored_within(((0x10, 0x10),), 0x20, 0x30) == 0 == aes_boot._stored_within((), 0, RAM_BYTES)


# ---- gem_entry's THREE BY-VALUE STORES: DECLARED BY SLICE M, ACTIVATED BY SLICE B (`test_aes_ourboot.py`), IN THE DOOR SINCE F ------
DECLARED_BY_SLICE_M = (aes_event.USERBLK_TRAMPOLINE_SLOT, aes_event.JUSTRETF_SLOT, aes_event.TICK_GLUE)     # (pending then; none is now)
STORED_BY_GEM_ENTRY_AT = {aes_event.USERBLK_TRAMPOLINE_SLOT.what: aes_event.USERBLK_TRAMPOLINE_STORED_AT,
                          aes_event.JUSTRETF_SLOT.what: aes_event.JUSTRETF_STORED_AT, aes_event.TICK_GLUE.what: aes_event.TICK_GLUE_STORED_AT}


@pytest.mark.parametrize("declared", DECLARED_BY_SLICE_M, ids=lambda declared: declared.what)
def test_each_declaration_of_the_wave_is_gem_entry_s_own_by_value_store_mapped_where_a_run_ends_and_a_part_of_the_door(declared):
    """THE WAVE'S THREE DECLARATIONS, HELD TO THE ROM AND TO THE MACHINES: each one's ROM routine and its first slot are
    the two operands of gem_entry's own `lea` / `move.l a0` pair, inside gem_entry; the text it stands for begins at
    the routine, lies in the AES's ROM text and ends on an `rts`; every machine the ROM boots holds the routine in
    that slot; BOTH BLOBS LINK AN ENTRY FOR IT (found by symbol, as a door part is). SINCE SLICE B each is among the
    tuple Tier 3 reads — MAPPED WHERE A RUN ENDS, never at its entry — proved a mapping by the rows of the build's own
    start-up; and SINCE THE FULL FLIP (slice F) EACH IS A PART OF THE DOOR a takeover maps, its first slot among the
    machine's own longwords the door requires to hold the ROM's at the stop and ours after (the scan, below)."""
    (rom, symbol), = declared.symbols.items()
    at = STORED_BY_GEM_ENTRY_AT[declared.what]
    assert aes.AES_TEXT[0] <= addrs.AES_ROM_GEM_ENTRY <= at < addrs.AES_ROM_GEM_ENTRY_END
    assert aes_event.GEM_ENTRY_STORES.unpack_from(BASE_IMAGE, at) == (
        aes_event.LEA_ABSOLUTE_LONG_A0, rom, aes_event.MOVE_L_A0_TO_ABSOLUTE, declared.slots[0])
    (lo, hi), = aes_event.ROM_TEXT_OF[declared.what]
    assert lo == rom and aes.AES_TEXT[0] <= lo < hi <= aes.AES_TEXT[1] and rom_word(hi - WORD_BYTES) == RTS_WORD
    for booted in (aes_boot.desk_machine(), aes_boot.accessory_machine(), inf()):
        assert booted.long(declared.slots[0]) == rom
    for blob in isr.BLOBS:
        part, = aes_boot.ours_of(isr.blob_named(blob), door=(declared,)).door
        (mapped_rom, entry), = part.mapping
        assert mapped_rom == rom and isr.blob_named(blob).base <= entry < isr.blob_named(blob).end
    assert declared.what not in aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3 and declared in aes_event.STORED_BY_GEM_ENTRY
    # (the trampoline AT ENTRY TOO since band 6 W3a stage 3: the text view's rows draw through the arrival's USERBLKs)
    assert declared in aes_event.CODE_RELOCATIONS and declared.at_entry == (declared is aes_event.USERBLK_TRAMPOLINE_SLOT)
    assert declared in aes_event.THE_DOOR and declared not in aes_event.THE_TRAP_DOOR
    assert aes_event.MAPPING_PROVED_BY[declared.what] == aes_event.STORED_BY_GEM_ENTRY_PROVED_BY
    assert aes_event.THE_MACHINE_S_VECTORS[declared.what][0] == declared.slots[0]


def test_no_declaration_is_pending_and_the_tick_glue_s_slots_are_the_machine_s():
    """NONE IS PENDING ANY MORE (STATUS's count is this dictionary's length: slice B activated the three). THE TICK
    GLUE'S SLOTS: `$947e`, where gem_entry keeps it; the VDI's own tick vector, which holds it on every machine the ROM
    boots (gsx_tick handed it over) while the AES keeps the VDI's displaced one beside; the AES's contrl[7..8] and
    [9..10], through which a vex_timv hands and displaces it — and, since the teardown is run (slice B), that
    displaced-save longword itself, which the teardown's own vex_timv leaves the glue in. justretf's routine is the
    glue table's own symbol for it."""
    assert aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3 == {} and aes_event.STORED_BY_GEM_ENTRY == (
        aes_event.JUSTRETF_SLOT, aes_event.TICK_GLUE, aes_event.USERBLK_TRAMPOLINE_SLOT)
    kept, vector, handed, displaced, saved = aes_event.TICK_GLUE.slots
    assert saved == aes.header_constants("evdisp.h")["AES_TICK_CHAIN"] == aes_event.TICK_GLUE_DISPLACED_AT
    assert (kept, vector) == (aes_event.TICK_GLUE_KEPT_AT, vdi.field("LINEA", "USER_TIM").at)
    assert (handed, displaced) == (aes.AES_GSX_CONTRL_PTR, aes.AES_GSX_CONTRL_PTR2) == aes_event.GLUE_CODE_SLOTS[2:4]
    for booted in (aes_boot.desk_machine(), aes_boot.accessory_machine(), inf()):
        assert booted.long(vector) == booted.long(kept) == addrs.AES_ROM_TICK_GLUE
        chained = booted.long(aes.header_constants("evdisp.h")["AES_TICK_CHAIN"])
        assert chained != addrs.AES_ROM_TICK_GLUE and not aes.AES_TEXT[0] <= chained < aes.AES_TEXT[1], "the VDI's own, displaced"
    assert aes_event.JUSTRETF_SLOT.symbols == {addrs.AES_ROM_JUSTRETF: aes_event.HANDED_ENTRY_SYMBOLS[addrs.AES_ROM_JUSTRETF]}
    assert not aes_event.JUSTRETF_SLOT.at_entry and not aes_event.TICK_GLUE.at_entry, "the glue's rule: where a run ends"


def test_a_door_part_names_a_longword_of_the_machine_or_a_walk_of_it_or_is_refused():
    """`door_slots`: a longword of the machine's own (a vector, a kept routine), a walk's slots, or BOTH (the desk's
    trampoline: `$8c32`, then the USERBLKs the desk copied it into) — every part of THE DOOR names one — and A
    DECLARATION THAT NAMES NEITHER IS REFUSED BY NAME: the registry's other three (the fork queue's codes, the
    GEMDOS glue's text sites, the screen manager's entry) are no part of a door."""
    ram = aes_boot.accessory_machine().ram
    part = lambda declared: aes_boot.DoorPart(declared.what, ())      # noqa: E731
    assert aes_boot.door_slots(ram, part(aes_event.GEM_TRAP_VECTOR)) == ((None, addrs.VECTOR_TRAP_GEM),)
    assert aes_boot.door_slots(ram, part(aes_event.PROGRAM_ENTRY)) == aes_event.first_entry_frames(ram) != ()
    text_window = window_of(inf(TEXT)).ram
    assert aes_boot.door_slots(text_window, part(aes_event.USERBLK_TRAMPOLINE_SLOT)) == (
        (None, aes.AES_USERDEF_TRAMPOLINE), *aes_event.userblk_slots(text_window)) and len(aes_event.userblk_slots(text_window)) == 1
    assert aes_boot.door_slots(ram, part(aes_event.JUSTRETF_SLOT)) == ((None, aes_event.JUSTRETF_KEPT_AT),)
    assert aes_boot.door_slots(ram, part(aes_event.TICK_GLUE)) == ((None, aes_event.TICK_GLUE_KEPT_AT), (None, TICK_VECTOR))
    assert aes_boot.door_slots(ram, part(aes_event.GLUE_CODES)) == ((None, BUTTON_VECTOR), (None, MOTION_VECTOR))
    for declared in aes_event.THE_DOOR:
        assert aes_boot.door_slots(ram, part(declared))
    not_of_a_door = [declared for declared in aes_event.CODE_RELOCATIONS if declared not in aes_event.THE_DOOR]
    assert not_of_a_door == [aes_event.FORK_CODES, aes_event.TEXT_SITES, aes_event.SCREEN_MANAGER_ENTRY]
    for declared in not_of_a_door:
        with pytest.raises(Refused, match="names neither a vector of the machine nor a walk of it"):
            aes_boot.door_slots(ram, part(declared))


# ---- THE SCAN: NO LONGWORD HOLDS, BY VALUE, THE ROM'S COPY OF A ROUTINE THE REGISTRY DECLARES ------------------------------------------
BUTTON_VECTOR, MOTION_VECTOR, TICK_VECTOR = (vdi.field("LINEA", name).at for name in ("USER_BUT", "USER_MOT", "USER_TIM"))
# WHAT EVERY MACHINE THE ROM BOOTS HOLDS BY VALUE AT ITS FIRST IDLE, `{slot: the build's symbol}` — the registry's
# entries, each in a slot of the registry — beside gem_entry's own address, the BIOS's.
ON_THE_ROM_S_MACHINE = {
    addrs.VECTOR_TRAP_GEM: "aes_rom_trap2", aes_event.ETV_CRITIC: "aes_rom_crit_err",
    BUTTON_VECTOR: "aes_rom_button_glue", MOTION_VECTOR: "aes_rom_motion_glue", TICK_VECTOR: "aes_rom_tick_glue",
    aes.AES_USERDEF_TRAMPOLINE: "aes_rom_ub_trampoline", aes_event.JUSTRETF_KEPT_AT: "aes_rom_justretf",
    aes_event.TICK_GLUE_KEPT_AT: "aes_rom_tick_glue", aes_event.SCREEN_MANAGER_ENTRY_SLOTS[0]: "aes_rom_ctlmgr",
    # (band 6's binding: the handler copy's table operand, `$cc24` — the ROM's call table, the registry's since slice B0)
    aes_event.LINEF_TABLE_SLOT.slots[0]: "aes_linef_table"}
# ...AND WHAT A DOOR OF THE TRAP DOOR'S THREE ALONE — WAVE 3's NARROW DOOR — LEAVES THE ROM'S (it maps `$88`, `$404`,
# the programs' frames, and the takeover the screen manager's entry): SIX LONGWORDS — gem_entry's three by-value
# stores and THE TWO GLUES gsx_init handed the VDI before the takeover's stop. Slice M's FINDING (behind a door called
# ours the ROM's button and motion glue, and through them its fork functions, and its tick glue still ran) — PAID BY
# THE FULL FLIP: THE DOOR maps all six, and behind it NOTHING IS LEFT (`LEFT_THE_ROM_S_BEHIND_THE_DOOR`, empty). The
# six stay named, by the part that maps each: what the scan refuses for when that part is taken out of the door. AND
# A SEVENTH SINCE BAND 6's BINDING: the handler copy's table operand (`$cc24`), which the narrow door leaves the ROM's.
LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE = {slot: symbol for slot, symbol in ON_THE_ROM_S_MACHINE.items() if slot not in (
    addrs.VECTOR_TRAP_GEM, aes_event.ETV_CRITIC, aes_event.SCREEN_MANAGER_ENTRY_SLOTS[0])}
LEFT_THE_ROM_S_BEHIND_THE_DOOR = {}
MAPPED_BY_THE_FULL_FLIP_S_PARTS = {
    aes_event.JUSTRETF_SLOT.what: (aes_event.JUSTRETF_KEPT_AT,), aes_event.TICK_GLUE.what: (aes_event.TICK_GLUE_KEPT_AT, TICK_VECTOR),
    aes_event.USERBLK_TRAMPOLINE_SLOT.what: (aes.AES_USERDEF_TRAMPOLINE,), aes_event.GLUE_CODES.what: (BUTTON_VECTOR, MOTION_VECTOR),
    aes_event.LINEF_TABLE_SLOT.what: aes_event.LINEF_TABLE_SLOT.slots}     # (band 6's binding, the door's ninth longword)
assert sorted(slot for slots in MAPPED_BY_THE_FULL_FLIP_S_PARTS.values() for slot in slots) == sorted(LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE)
SCANNED = {"the desk alone": aes_boot.desk_machine, "two quiet accessories": aes_boot.accessory_machine, "the DESKTOP.INF machine": inf}
CAPTURE_OF = {"the desk alone": aes_boot.preinit, "two quiet accessories": aes_boot.accessory_preinit, "the DESKTOP.INF machine": aes_boot.inf_preinit}


def test_the_scan_s_routines_are_the_registry_s_and_gem_entry():
    """WHAT THE SCAN LOOKS FOR IS A LIST: the routines the registry's declarations name and gem_entry — seventeen
    values today (STATUS quotes the count off this dictionary's length), NOT every ROM routine a build has an entry
    for. What that leaves unseen is held below (`test_what_the_scan_cannot_see_...`)."""
    routines = aes_boot.routines_by_value()
    assert routines[aes_boot.GEM_ENTRY] is None and set(ON_THE_ROM_S_MACHINE.values()) <= set(routines.values())
    for name, declared in battery._relocations_declared().items():
        assert all(routines[rom] == symbol for rom, symbol in declared.symbols.items()), name
    assert len(routines) == 1 + len({rom for declared in battery._relocations_declared().values() for rom in declared.symbols})


@pytest.mark.parametrize("label", SCANNED)
def test_the_scan_finds_on_the_rom_s_machine_each_entry_in_a_slot_of_the_registry_and_gem_entry_s_three(label):
    """THE SCAN ON A MACHINE THE ROM BOOTED: nine longwords hold an entry of the registry's, EACH IN A SLOT THE
    REGISTRY DECLARES for it and none dead — OF THE ROUTINES THE REGISTRY DECLARES, AND OF NO OTHER: the scan looks
    for those entries alone, so it does not say the declarations are complete (a brute scan for ANY longword holding
    an address of GEM's text finds more on a narrow-door machine — a saved A0 naming dsptch, two residues naming
    dos_alloc, the Line-F copy's nine table longwords — none in a slot, by the second review's reading);
    and gem_entry's own address lies where the BIOS stored it — `exec_os`, the AES basepage's
    text base (found through the launch's own stack), and at most one frame of the launch above it. The vet itself is
    of a machine CALLED OURS: on this one it is refused by name."""
    booted = SCANNED[label]()
    held = aes_boot.entries_held_by_value(booted)
    registry = {each.slot: each for each in held if each.routine != aes_boot.GEM_ENTRY}
    assert {slot: each.symbol for slot, each in registry.items()} == ON_THE_ROM_S_MACHINE
    for slot, each in registry.items():
        (what,) = [declared.what for declared in battery._relocations_declared().values() if each.routine in declared.symbols
                   and slot in (*aes_event.slots_over(declared, booted.ram), *aes_event.THE_MACHINE_S_VECTORS.get(declared.what, ()))]
        assert each.where == aes_boot.IN_A_SLOT.format(what) and not each.dead, f"{slot:#x}"
    bios = [each for each in held if each.routine == aes_boot.GEM_ENTRY]
    capture = CAPTURE_OF[label]()
    basepage = case.long_in(capture.ram, capture.registers["usp"] + LONG_BYTES) & BUS
    assert {each.slot for each in bios} >= {preinit_snapshot.EXEC_OS, basepage + addrs.BASEPAGE_TBASE}
    assert all(each.where == aes_boot.THE_BIOS_S and each.symbol is None for each in bios)
    assert all(each.slot >= capture.registers["usp"] - battery.TOP_OF_TPA_STACK_BYTES for each in bios if each.slot not in (
        preinit_snapshot.EXEC_OS, basepage + addrs.BASEPAGE_TBASE)) and len(bios) <= 3
    with pytest.raises(Refused, match="the scan vets a machine CALLED OURS"):
        aes_boot.vet_no_entry_is_held_as_the_rom_s(booted)


@functools.cache
def behind_the_door(label, blob, view=ICONS, without=()):
    """The machine `label` BEHIND THE DOOR of the blob named (`without`: LESS the parts so named — a RED's) — the door
    machine every Tier 3 row from an idle runs over (`aes_ctlmgr.our_machine`), which this battery asks for to hold
    the scan over it and to continue it (`test_aes_boot.WHO_ASKS_FOR_A_DOOR` lists it)."""
    ours, door = isr.blob_named(blob), tuple(part for part in aes_event.THE_DOOR if part.what not in without)
    if label == "the desk alone":
        return aes_boot.desk_machine(ours=ours, door=door)
    if label == "two quiet accessories":
        return aes_boot.accessory_machine(ours=ours, door=door)
    return aes_boot.inf_machine(view, ours=ours, door=door)


def left_the_rom_s(machine):
    """`{slot: the build's symbol}`: what the scan finds held by value as the ROM's in a live longword of `machine`."""
    return {each.slot: each.symbol for each in aes_boot.entries_held_by_value(machine) if each.routine != aes_boot.GEM_ENTRY and not each.dead}


@every_blob
@pytest.mark.parametrize("label", SCANNED)
def test_behind_the_door_at_its_idle_no_live_longword_holds_the_rom_s_copy_of_a_routine_the_registry_declares(label, blob):
    """THE VET PASSES ON EVERY DOOR MACHINE AT ITS FIRST IDLE (the full flip, band 5 wave 4 — until it this test was
    the pin of a RED: six longwords the narrow door left the ROM's): behind THE DOOR not one live longword of the
    machine holds the ROM's address of a routine the registry declares — gem_entry's own, the BIOS's, alone found
    (`exec_os`, the AES basepage's text base, a frame of the launch: not mapped on either shore) — and every longword
    the ROM-booted machine holds such a routine in holds THE BLOB'S OWN ENTRY for it here. OF THE REGISTRY'S ROUTINES,
    AT AN IDLE: no claim about another ROM routine, nor about another stop (the two tests after the scan's reds)."""
    booted = behind_the_door(label, blob)
    passed = aes_boot.vet_no_entry_is_held_as_the_rom_s(booted)
    assert passed and all(each.where == aes_boot.THE_BIOS_S or each.dead for each in passed)
    assert left_the_rom_s(booted) == LEFT_THE_ROM_S_BEHIND_THE_DOOR == {}
    ours, built = booted.ours, isr.blob_named(blob)
    assert left_the_rom_s(SCANNED[label]()) == ON_THE_ROM_S_MACHINE
    for slot, symbol in ON_THE_ROM_S_MACHINE.items():
        assert booted.long(slot) == built.entry(symbol) and ours.base <= booted.long(slot) < ours.end, f"${slot:x} holds the blob's own `{symbol}`"


FULL_FLIP_S_PARTS = (aes_event.JUSTRETF_SLOT, aes_event.TICK_GLUE, aes_event.USERBLK_TRAMPOLINE_SLOT, aes_event.GLUE_CODES)
# ...and the part THE BINDING added (band 6 slice B0): the Line-F call table the handler's copy indexes.
PAST_THE_TRAP_DOOR = (*FULL_FLIP_S_PARTS, aes_event.LINEF_TABLE_SLOT)


@every_blob
@pytest.mark.parametrize("left_out", PAST_THE_TRAP_DOOR, ids=lambda part: part.what)
def test_each_part_the_full_flip_added_taken_out_of_the_door_is_refused_by_the_scan_for_its_own_longwords(left_out, blob):
    """A MAPPING NOBODY WOULD MISS IS NOT A MAPPING — THE DOOR'S OWN TEETH, part by part, by a real boot: the quiet
    pair's machine behind THE DOOR LESS ONE of the four parts the full flip added (justretf's slot; the tick glue;
    the desk's trampoline; the two glues) — or of the one the binding added (the handler copy's table) — is REFUSED
    BY THE SCAN, naming exactly that part's longwords — each a slot of the registry, still the ROM's — and no other;
    and with the five all out (the trap door's three alone: wave 3's narrow door) it names the seven."""
    assert tuple(part for part in aes_event.THE_DOOR if part not in aes_event.THE_TRAP_DOOR) == PAST_THE_TRAP_DOOR
    booted = behind_the_door("two quiet accessories", blob, without=(left_out.what,))
    slots = MAPPED_BY_THE_FULL_FLIP_S_PARTS[left_out.what]
    with pytest.raises(Refused) as refused:
        aes_boot.vet_no_entry_is_held_as_the_rom_s(booted)
    said = str(refused.value)
    assert f"{len(slots)} longword(s)" in said and "A ROUTINE THE REGISTRY DECLARES IS HELD BY VALUE AS THE ROM'S" in said
    for slot in slots:
        assert f"${slot:x} holds" in said and f"`{ON_THE_ROM_S_MACHINE[slot]}`" in said and aes_boot.IN_A_SLOT.format(left_out.what) in said
    assert left_the_rom_s(booted) == {slot: ON_THE_ROM_S_MACHINE[slot] for slot in slots}
    narrow = behind_the_door("two quiet accessories", blob, without=tuple(part.what for part in PAST_THE_TRAP_DOOR))
    assert [part.what for part in narrow.ours.door] == [part.what for part in aes_event.THE_TRAP_DOOR]
    assert left_the_rom_s(narrow) == LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE and len(LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE) == 7


def with_longs(booted, pokes):
    """A LABELLED CRAFTED MEGABYTE: the machine `booted` with the longwords `pokes` laid in — a `Machine`."""
    ram = bytearray(booted.ram)
    for at, value in pokes.items():
        ram[at:at + LONG_BYTES] = struct.pack(">I", value)
    return aes_boot.Machine(booted.boot._replace(ram=bytes(ram)))


@every_blob
def test_the_scan_refuses_a_rom_entry_put_back_and_sees_what_is_dead_and_what_nobody_declared(blob):
    """THE VET'S TEETH, on labelled crafted megabytes of a door machine (which passes as it stands): ONE ROM ENTRY PUT
    BACK in a longword the door mapped is refused, that longword named; a ROM entry laid IN A DEAD SPAN (the
    dispatcher's stack below the idle's stack pointer, a fork entry outside the queue's live run) is seen, said dead
    and not refused; one laid IN A LIVE LONGWORD NOBODY DECLARED is refused as that — AND SO IS ONE IN A LIVE FRAME OF
    THE DISPATCHER'S STACK, at the idle's stack pointer and at the stack's last longword (the dead span ends where the
    idle stands: no run leaves a routine there, so this is the span's upper bound's only red); and one in the blob's
    own span is the build's constant, not scanned."""
    booted = behind_the_door("the desk alone", blob)
    passed = aes_boot.vet_no_entry_is_held_as_the_rom_s(booted)
    assert passed and all(each.where == aes_boot.THE_BIOS_S for each in passed)
    for slot in LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE:
        the_rom_s = SCANNED["the desk alone"]().long(slot)
        with pytest.raises(Refused, match=rf"1 longword\(s\): \${slot:x} holds {the_rom_s:#x} "):
            aes_boot.vet_no_entry_is_held_as_the_rom_s(with_longs(booted, {slot: the_rom_s}))
    dead_frame = booted.registers["isp"] - 2 * LONG_BYTES
    stale_fork = aes.AES_FORK_QUEUE + ((booted.word(aes.AES_FORK_HEAD) + booted.word(aes.AES_FORK_COUNT)) % aes.AES_FORK_ENTRIES) * aes.FORK_ENTRY_BYTES
    dead = aes_boot.vet_no_entry_is_held_as_the_rom_s(with_longs(booted, {dead_frame: addrs.GEM_TRAP2, stale_fork: addrs.AES_ROM_BCHANGE}))
    assert {each.slot: (each.where, each.dead) for each in dead if each.dead} == {
        dead_frame: (aes_boot.DEAD_DISPATCHER_FRAMES, True),
        stale_fork: (f"{aes_boot.DEAD_FORK_ENTRY} ({(stale_fork - aes.AES_FORK_QUEUE) // aes.FORK_ENTRY_BYTES})", True)}
    live_and_undeclared = aes.AES_GL_NEWDESK                  # (a longword of GEMBSS no declaration names)
    with pytest.raises(Refused, match=rf"\${live_and_undeclared:x} holds {addrs.GEM_TRAP2:#x} .`aes_rom_trap2`.: no slot of the registry and no dead span"):
        aes_boot.vet_no_entry_is_held_as_the_rom_s(with_longs(booted, {live_and_undeclared: addrs.GEM_TRAP2}))
    idle_s_sp, stack_end = booted.registers["isp"], aes_event.DISPATCHER_STACK[1]
    assert aes_event.DISPATCHER_STACK[0] < dead_frame < idle_s_sp <= stack_end - LONG_BYTES, "the idle stands on live frames of that stack"
    for live_frame in {idle_s_sp, stack_end - LONG_BYTES}:
        said = rf"1 longword\(s\): \${live_frame:x} holds {addrs.GEM_TRAP2:#x} .`aes_rom_trap2`.: no slot of the registry and no dead span"
        with pytest.raises(Refused, match=said):
            aes_boot.vet_no_entry_is_held_as_the_rom_s(with_longs(booted, {live_frame: addrs.GEM_TRAP2}))
    in_the_blob = with_longs(booted, {booted.ours.base + 0x100: addrs.GEM_TRAP2})
    assert not any(booted.ours.base <= each.slot < booted.ours.end for each in aes_boot.entries_held_by_value(in_the_blob))


# ---- WHAT THE SCAN CANNOT SEE, AND WHERE IT IS NOT RUN (slice F's fix pass; the second review's findings 1 and 2) ----------------------
# The scan is a list of the registry's routines matched as whole longwords at an idle. Three limits, each held:
#   * A ROM ROUTINE NOBODY DECLARED PASSES IT, wherever it lies — and IN A LONGWORD OF THE DOOR what refuses it is
#     `vet_the_door_stands` (asked where a boot, a continuation and a served run end): anything there but the blob's own
#     entry, a ROM routine's address under a non-zero top byte too.
#   * TWELVE LIVE LONGWORDS OF EVERY DOOR MACHINE HOLD OTHER ROM ROUTINES (the reviewer's wider scan, every `fn` of
#     names.txt in GEM's text; re-read by the fix pass on six door machines, `scratchpad/b5/W4/FIXF/probe/p3.out`), none
#     of which a door can map. NINE ARE HELD HERE, through the machine's own pointer: the first nine entries of the
#     Line-F call table, the tail of the 100 bytes gem_entry copies behind vector `$2c` (the ROM's table by ruling
#     W4-R3; by the reviewer's reading the handler reads the ROM's table and never the copy's tail). THE OTHER THREE
#     ROUTINES ARE NAMED AND NOT PINNED — where they lie is a capture's and a boot's: aes_dsptch in PD0's UDA (a saved
#     register of the desk's process, which parks through the ROM's dispatcher); dos_alloc twice (residue on the first
#     stack and on PD0's, left by the ROM's own start-up); the desk's resume PC in its parked frame (ROM code the desk
#     is resumed in: the desk is the ROM's on both shores).
#   * AT deskmain's ENTRY the scan REFUSES a door machine: the AES's contrl still holds the ROM's tick glue.
AN_UNDECLARED_ROM_ROUTINE, ITS_ENTRY_IN_A_BUILD = addrs.AES_ROM_FORKQ, "aes_forkq_alcyon"      # (no declaration of the registry names it)
A_NON_ZERO_TOP_BYTE = 0x01000000                          # (the 68000's bus drops it: the same routine to the CPU, another value to a compare)
LINE_F_HANDLER_BYTES = aes.AES_LINEF_TABLE - addrs.AES_ROM_LINEF_HANDLER
LINE_F_ENTRIES_COPIED = (aes.LINEF_COPY_BYTES - LINE_F_HANDLER_BYTES) // LONG_BYTES
HELD_AT_DESKMAIN_S_ENTRY = {aes.AES_GSX_CONTRL_PTR: "aes_rom_tick_glue"}      # (STATUS quotes this dictionary's length)


@every_blob
def test_what_the_scan_cannot_see_in_a_longword_of_the_door_is_refused_by_the_door_s_own_vet(blob):
    """THE SCAN'S LIMIT, AND WHAT COVERS IT IN THE DOOR'S OWN LONGWORDS — labelled crafted megabytes of the quiet pair's
    door machine. In each of the nine longwords the door maps (the binding's table among them): A ROM ROUTINE THE
    REGISTRY DOES NOT DECLARE (forkq), and THE ROM'S `trap #2` HANDLER UNDER A NON-ZERO TOP BYTE, each PASS THE SCAN —
    it matches eighteen whole values
    — and each is REFUSED BY `vet_the_door_stands`, that longword's part named. And in a live longword that is no
    part of the door (gl_newdesk) the undeclared routine passes the scan and NOTHING REFUSES IT: said, not hidden."""
    booted = behind_the_door("two quiet accessories", blob)
    assert AN_UNDECLARED_ROM_ROUTINE not in aes_boot.routines_by_value() and len(aes_boot.routines_by_value()) == 18
    assert isr.blob_named(blob).entry(ITS_ENTRY_IN_A_BUILD), "a ROM routine a build has an entry for"
    longwords = [(part, slot) for part in booted.ours.door for pd, slot in aes_boot.door_slots(booted.ram, part) if pd is None]
    assert sorted(slot for _part, slot in longwords) == sorted(
        slot for part in aes_event.THE_DOOR for slot in aes_event.THE_MACHINE_S_VECTORS.get(part.what, ())) and len(longwords) == 9
    for part, slot in longwords:
        for wrong in (AN_UNDECLARED_ROM_ROUTINE, A_NON_ZERO_TOP_BYTE | addrs.GEM_TRAP2):
            crafted = with_longs(booted, {slot: wrong})
            assert aes_boot.vet_no_entry_is_held_as_the_rom_s(crafted) is not None, "the scan does not see it"
            with pytest.raises(Refused, match=rf"THE DOOR IS NO LONGER OURS as crafted: {re.escape(part.what)} holds {wrong:#x}, not the blob's"):
                aes_boot.vet_the_door_stands(crafted.ram, booted.ours, "as crafted")
    elsewhere = with_longs(booted, {aes.AES_GL_NEWDESK: AN_UNDECLARED_ROM_ROUTINE})
    assert aes_boot.vet_no_entry_is_held_as_the_rom_s(elsewhere) is not None
    aes_boot.vet_the_door_stands(elsewhere.ram, booted.ours, "as crafted")


@every_blob
@pytest.mark.parametrize("label", SCANNED)
def test_behind_the_door_the_line_f_table_s_nine_copied_entries_are_live_rom_routines_the_scan_does_not_look_for(label, blob):
    """THE SENTENCE "NO ROM ROUTINE IS HELD BY VALUE" WOULD BE FALSE, AND HERE IS WHY, by the machine's own pointer:
    behind vector `$2c` lies gem_entry's copy of the Line-F handler, and after the handler's own bytes the copy holds
    THE FIRST NINE ENTRIES OF THE ROM'S CALL TABLE — nine ROM routines, live, on every door machine, none of them a
    routine the registry declares, so the scan passes over them. The table is the ROM's by ruling W4-R3 (band 6)."""
    booted = behind_the_door(label, blob)
    copy = booted.long(addrs.VECTOR_LINE_F) & BUS
    assert copy == aes.AES_LINEF_COPY and (LINE_F_HANDLER_BYTES, LINE_F_ENTRIES_COPIED) == (0x3e, 9)
    copied = [booted.long(copy + LINE_F_HANDLER_BYTES + nth * LONG_BYTES) for nth in range(LINE_F_ENTRIES_COPIED)]
    assert copied == [rom_long(LINE_F_TABLE + nth * LONG_BYTES) for nth in range(LINE_F_ENTRIES_COPIED)]
    assert all(aes.AES_TEXT[0] <= routine < aes.AES_TEXT[1] for routine in copied) and len(set(copied)) == LINE_F_ENTRIES_COPIED
    assert not set(copied) & set(aes_boot.routines_by_value())
    dead = aes_boot.dead_by_nature(booted)
    assert not any(lo <= copy + LINE_F_HANDLER_BYTES < hi for lo, hi in dead.values()), "live: no dead span holds the copy"
    assert aes_boot.vet_no_entry_is_held_as_the_rom_s(booted) is not None


@every_blob
def test_at_deskmain_s_entry_a_door_machine_holds_the_rom_s_tick_glue_in_contrl_and_the_scan_refuses_there(blob):
    """WHERE THE SCAN IS RUN: AT AN IDLE AND WHERE A CONTINUATION ENDS — NOT AT deskmain's ENTRY. The takeover machine
    behind THE DOOR, stopped there (the machine the served door answers deskmain on), holds THE ROM'S TICK GLUE IN ONE
    LONGWORD: the AES's contrl, the ROM's gsx_tick's hand-in from before the takeover's stop — a slot of the registry
    a value TRAVELS through, no longword of the machine's own, so no part of the door maps it and `vet_the_door_stands`
    passes there. The scan refuses for exactly that longword; BY THE FIRST IDLE IT IS GONE. And the displaced-save
    `$948a` (the brief of the flip listed it among what the door gains) holds THE VDI'S OWN tick routine at the idle
    on both the ROM-booted and the door machine — no routine of GEM's: nothing of a door to map there."""
    capture, disk = aes_boot.preinit(), aes_boot.blank_disk()
    behind = aes_boot.Machine(aes_boot.booted(capture, disk, until=DESKMAIN, ours=aes_boot.ours_of(isr.blob_named(blob), aes_event.THE_DOOR)))
    assert left_the_rom_s(behind) == HELD_AT_DESKMAIN_S_ENTRY and len(HELD_AT_DESKMAIN_S_ENTRY) == 1
    (contrl, symbol), = HELD_AT_DESKMAIN_S_ENTRY.items()
    assert contrl in aes_event.TICK_GLUE.slots and contrl not in aes_event.THE_MACHINE_S_VECTORS[aes_event.TICK_GLUE.what]
    with pytest.raises(Refused, match=rf"1 longword\(s\): \${contrl:x} holds {addrs.AES_ROM_TICK_GLUE:#x} .`{symbol}`.: a slot of the registry"):
        aes_boot.vet_no_entry_is_held_as_the_rom_s(behind)
    aes_boot.vet_the_door_stands(behind.ram, behind.ours, "at deskmain's entry")
    at_the_idle, the_rom_s = behind_the_door("the desk alone", blob), SCANNED["the desk alone"]()
    assert left_the_rom_s(at_the_idle) == {} and at_the_idle.long(contrl) != addrs.AES_ROM_TICK_GLUE
    displaced = at_the_idle.long(aes_event.TICK_GLUE_DISPLACED_AT)
    assert displaced == the_rom_s.long(aes_event.TICK_GLUE_DISPLACED_AT) and not aes.AES_TEXT[0] <= displaced & BUS < aes.AES_TEXT[1]
    assert emu.ROM_BASE <= displaced & BUS < aes.AES_TEXT[0], "the VDI's own, in the ROM below GEM's text"


DEAD_GLUE_NOISE_SEED = 0x7054


def test_the_button_glue_leaves_its_own_address_on_its_stack_and_that_stack_is_dead():
    """A HOLDER THE SCAN FOUND AND NO DECLARATION NAMES — AND WHY IT IS DEAD: after a click (a drive's window opened)
    one longword of THE BUTTON AND MOTION GLUES' OWN STACK holds the button glue's address: the VDI's mouse handler
    enters the glue with it in A1 and the glue's `movem.l` saves A1 there. The scan says so (dead, in that span) on
    the machine before the click it is not there; and the span IS dead, by noise: the INF machine with both glues'
    stacks noised opens the same window — the same instructions, the same megabyte outside the two stacks."""
    booted = inf(TEXT)
    window = window_of(booted)
    lo, hi = aes_boot.GLUE_STACKS[aes_boot.GLUE_STACK]
    in_the_stack = [each for each in aes_boot.entries_held_by_value(window) if lo <= each.slot < hi]
    assert [(each.symbol, each.where, each.dead) for each in in_the_stack] == [("aes_rom_button_glue", aes_boot.GLUE_STACK, True)]
    assert not [each for each in aes_boot.entries_held_by_value(booted) if lo <= each.slot < hi]
    spans = sorted(aes_boot.GLUE_STACKS.values())
    assert spans[0][1] == spans[1][0] and spans[0][0] == aes.AES_TIMER_COUNTDOWN + LONG_BYTES, "the two stacks, end to end above the tick's words"
    noised = window_of(aes_boot.noised(booted, spans, DEAD_GLUE_NOISE_SEED))
    assert (noised.registers, noised.boot.instructions, noised.observed) == (window.registers, window.boot.instructions, window.observed)
    outside = bytearray(noised.ram)
    outside[spans[0][0]:spans[1][1]] = window.ram[spans[0][0]:spans[1][1]]
    assert bytes(outside) == window.ram


def test_a_live_fork_entry_is_a_slot_and_a_run_one_is_dead():
    """THE FORK QUEUE, BY ITS OWN WORDS: on a crafted megabyte whose queue holds one entry (head 3, count 1) the entry
    at 3 is a slot of the registry holding a ROM fork function — live — and the same code at 2 and at 4 is dead."""
    booted = aes_boot.desk_machine()
    ram = bytearray(booted.ram)
    ram[aes.AES_FORK_HEAD:aes.AES_FORK_HEAD + WORD_BYTES] = struct.pack(">H", 3)
    ram[aes.AES_FORK_COUNT:aes.AES_FORK_COUNT + WORD_BYTES] = struct.pack(">H", 1)
    for index in (2, 3, 4):
        at = aes.AES_FORK_QUEUE + index * aes.FORK_ENTRY_BYTES + aes.FORK_CODE
        ram[at:at + LONG_BYTES] = struct.pack(">I", addrs.AES_ROM_BCHANGE)
    forks = {(each.slot - aes.AES_FORK_QUEUE) // aes.FORK_ENTRY_BYTES: each
             for each in aes_boot.entries_held_by_value(aes_boot.Machine(booted.boot._replace(ram=bytes(ram)))) if each.routine == addrs.AES_ROM_BCHANGE}
    assert {index: each.dead for index, each in forks.items()} == {2: True, 3: False, 4: True}
    assert forks[3].where == aes_boot.IN_A_SLOT.format(aes_event.FORK_CODES.what) and forks[2].where.startswith(aes_boot.DEAD_FORK_ENTRY)


# ---- BEHIND THE DOOR, CONTINUED: WHO RUNS THE GLUE AND THE TRAMPOLINE, AND THE MACHINE THEY LEAVE (the full flip) -------------------
# The door's four added parts are longwords the VDI's interrupts and the desk's draws jump through. A boot enters none
# of them (no mouse packet, no tick, no window item before the first idle), so who runs them is read where something
# does: A CONTINUATION, PROFILED, on the ROM-booted machine and on the same boot behind THE DOOR — the same hand (the
# mouse moved, a click and its ticks; a drive's window opened in the text view), through the ROM's own ACIA and Timer C
# handlers on both. Slice M's finding, measured then on the narrow door (the ROM's button glue 440 cycles, its motion
# glue 248, its tick glue 1,914 behind a door called ours), is what this turns: BEHIND THE DOOR THE ROM'S TEXT OF EACH
# PART RUNS NOT ONE CYCLE, AND OUR ENTRY OF IT RUNS THE ROM'S OWN CYCLES (each is a `.S` of the ROM's instructions).
# justretf's SLOT IS ENTERED BY NEITHER RUN (drawrat, its one caller, is not reached by a hand's move or click: the
# VDI draws the mouse itself) — that part is held by the scan, above, and by gem_main's stretches; said, not hidden.
A_CLICK = (aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.ikbd(aes_boot.NO_BUTTON, 0, 0), aes_boot.CLICK_TICKS)
THE_GLUES, THE_TICK, THE_TRAMPOLINE, THE_CURSOR = (
    aes_event.GLUE_CODES.what, aes_event.TICK_GLUE.what, aes_event.USERBLK_TRAMPOLINE_SLOT.what, aes_event.JUSTRETF_SLOT.what)
# `{the continuation: (the machine's label, its view, what it receives — made from the ROM-booted machine —, the parts
# of the door the run ENTERS)}`
CONTINUED_BEHIND_THE_DOOR = {
    "two quiet accessories: the mouse moved, and a click on the desktop": (
        "two quiet accessories", ICONS, lambda _booted: (aes_boot.mouse_to(*aes_event.A_POINT_ON_THE_DESKTOP), *A_CLICK), {THE_GLUES, THE_TICK}),
    "the desk alone: the mouse moved, and a click on the desktop": (
        "the desk alone", ICONS, lambda _booted: (aes_boot.mouse_to(*aes_event.A_POINT_ON_THE_DESKTOP), *A_CLICK), {THE_GLUES, THE_TICK}),
    "the DESKTOP.INF machine as text: drive A:'s window opened": (
        "the DESKTOP.INF machine", TEXT, lambda booted: (aes_boot.mouse_to(*drive_icon(booted, "A")), *A_DOUBLE_CLICK),
        {THE_GLUES, THE_TICK, THE_TRAMPOLINE})}
PROFILE_HELD_BY_A_CONTINUATION = "a profiled continuation of this battery's (`test_aes_boot_w4.py`)"


def continued_and_profiled(machine, received, spans):
    """`machine` CONTINUED through `received` WITH THE CYCLE PROFILE ON — a derivation of its own, nothing kept —:
    `(the machine at its next idle, the cycles at the PCs of each of `spans`)` (`spans`: `((lo, hi), ...)` each)."""
    aes_event.vet_the_profile_is_free("a profiled continuation")
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        with aes_event.profile_held(PROFILE_HELD_BY_A_CONTINUATION):
            after = aes_boot.Machine(aes_boot.continued.derive(machine.boot, received))
    finally:
        emu.prof_enable(False)
    return after, [sum(emu.prof_cycles(lo, hi) for lo, hi in each) for each in spans]


def our_text_of(blob, part):
    """`((lo, hi), ...)`: the blob's own text of the routines the door part `part` names, in the order of its
    `symbols` — each from the blob's entry for it, AS LONG AS THE ROM'S OWN TEXT OF IT (`aes_event.ROM_TEXT_OF`: every
    one ships as the ROM's instructions, byte-pinned)."""
    built = isr.blob_named(blob)
    lengths = {lo: hi - lo for lo, hi in aes_event.ROM_TEXT_OF[part.what]}
    # (the binding's table is no routine: no text of the ROM's stands for it — none of ours either)
    return tuple((built.entry(symbol), built.entry(symbol) + lengths[rom]) for rom, symbol in part.symbols.items() if rom in lengths)


USERDEF_STACK = "the desk's G_USERDEF stack: dead once the trampoline has returned (it loads its stack pointer from the top)"
USERDEF_STACK_BYTES = aes.header_constants("deskmem.h")["USERDEF_STACK_BYTES"]


def dead_spans_a_code_address_is_left_in(machine):
    """`{what: (lo, hi)}`: THE DEAD SPANS OF A CONTINUED MACHINE (`aes_boot.dead_by_nature`: each process's stack under
    its parked stack pointer, the dispatcher's dead frames...) AND THE DESK'S G_USERDEF STACK, through the machine's
    own pointer to its top — where the desk's draw of a window item leaves the address it read out of its USERBLK,
    and the trampoline's `jsr` its own return site."""
    top = machine.long(aes.AES_USERDEF_STACK) & BUS
    return {**aes_boot.dead_by_nature(machine), USERDEF_STACK: (top - USERDEF_STACK_BYTES, top)}


def the_bound_desk_s_draw(machine):
    """THE DESK'S G_USERDEF DRAW OVER OUR AES (band 6's binding): the trampoline's saved caller's stack pointer (a place
    in each build's AES frames, `$8c36`) and the G_USERDEF stack (dead once the trampoline has returned: the desk's
    draw code's frames over each build's AES), `((lo, hi), ...)` — by nature, a class each."""
    return ((aes.AES_USERDEF_SP_SAVE, aes.AES_USERDEF_SP_SAVE + LONG_BYTES), dead_spans_a_code_address_is_left_in(machine)[USERDEF_STACK])


# ---- band 6 slice F2 (group G2) ---- THE GLUE'S PARKED RETURN: drive_check, flipped, reaches trp13's `.S` through the shipped
# blob's glue, whose `jsr` makes the `.S` park THE GLUE'S return in AES_BIOS_RETURN where the ROM's door parks its caller's
# — F1's declared divergence (R9's kind; read by trp13's own two instructions alone:
# `test_the_bios_door_s_parked_return_is_named_by_trp13_alone`). NAMED ONLY WHERE OUR MACHINE HOLDS THERE A RETURN INSIDE
# THE SHIPPED BLOB'S GLUE (`tier3.glue_ranges`) and the ROM's machine another: on the shipped blob, after a drive_check.
def the_glue_s_parked_return(rom_after, ours_after, blob):
    """`((lo, hi),)` — AES_BIOS_RETURN where the shipped glue's return is parked there (above) — or `()`."""
    at, parked = aes.AES_BIOS_RETURN, ours_after.long(aes.AES_BIOS_RETURN)
    in_the_glue = blob == battery.THE_SHIPPED_BLOB and any(lo <= parked < hi for lo, hi in battery.harness.bench_tier3().glue_ranges())
    return ((at, at + LONG_BYTES),) if in_the_glue and rom_after.long(at) != parked else ()


def given_the_rom_s_names(machine, blob, in_the_dead_spans=True):
    """A continued door machine's megabyte AS IT IS COMPARED WITH THE ROM-BOOTED ONE'S: every code address of the
    registry given the ROM's name THROUGH THE REGISTRY ITSELF (`tier3.mapped_back`: the door's longwords, the fork
    queue's codes our glue queued, the walked USERBLKs the desk copied `$8c32` into) — AND, IN THE DEAD SPANS ALONE
    (`dead_spans_a_code_address_is_left_in`; not with `in_the_dead_spans` False: a RED's), every longword that names
    A PLACE INSIDE THE BLOB'S TEXT OF A DOOR PART given the same place of the ROM's text of it: an entry the ROM's own
    code read out of a mapped longword and left in a frame, a return site of the trampoline's own `jsr` (each `.S`
    is the ROM's instructions: one offset names one instruction on both shores). Mapped, never dropped. The megabyte."""
    tier3, built = battery.harness.bench_tier3(), isr.blob_named(blob)
    relocations = [each for each in tier3.code_relocations(str(built.elf), aes_event.SCREEN_MANAGER_ENTRY_SYMBOL) if each.mapping]
    ram = tier3.mapped_back(bytearray(machine.ram), relocations)
    texts = [(lo, hi, rom) for part in aes_event.THE_DOOR for (lo, hi), rom in zip(our_text_of(blob, part), part.symbols)]
    for span_lo, span_hi in dead_spans_a_code_address_is_left_in(machine).values() if in_the_dead_spans else ():
        for at in range(span_lo + span_lo % WORD_BYTES, span_hi - LONG_BYTES + 1, WORD_BYTES):
            held = case.long_in(ram, at)
            for lo, hi, rom in texts:
                if lo <= held < hi:
                    ram[at:at + LONG_BYTES] = struct.pack(">I", rom + held - lo)
    return ram


@every_blob
@pytest.mark.parametrize("label", CONTINUED_BEHIND_THE_DOOR)
def test_behind_the_door_a_continuation_runs_our_glue_and_our_trampoline_and_leaves_the_rom_s_machine(label, blob):
    """WHO RAN, AND WHAT IS LEFT (above), both blobs. THE ROM-BOOTED MACHINE'S RUN spends cycles in the ROM's text of
    each part the hand reaches — the button and motion glues, the tick glue, and for a text window the trampoline — and
    none in the blob's; THE DOOR MACHINE'S RUN spends NOT ONE CYCLE in the ROM's text of ANY part of the door, and in
    OUR entry of each part entered EXACTLY THE ROM'S CYCLES; the same handlers observed. Where it ends the door
    stands (`continued`'s own vet), THE SCAN STILL FINDS NOTHING (a walked USERBLK holds OUR trampoline), and THE
    MEGABYTE IS THE ROM-BOOTED MACHINE'S — every code address given the ROM's name — outside the classes a takeover
    machine differs in by nature and THE TWO GLUE STACKS (dead between interrupts: each build's own frames under its
    glue — our forkq is C — and each REQUIRED to differ)."""
    machine, view, receives, entered = CONTINUED_BEHIND_THE_DOOR[label]
    rom = SCANNED[machine]() if view == ICONS else inf(view)
    behind, received = behind_the_door(machine, blob, view), receives(rom)
    parts = [part for part in aes_event.THE_DOOR if part not in aes_event.THE_TRAP_DOOR and aes_event.ROM_TEXT_OF[part.what]]
    spans = [aes_event.ROM_TEXT_OF[part.what] for part in parts] + [our_text_of(blob, part) for part in parts]
    (rom_after, rom_in), (ours_after, ours_in) = (continued_and_profiled(each, received, spans) for each in (rom, behind))
    in_the_rom_s_text = dict(zip((part.what for part in parts), zip(rom_in[:len(parts)], ours_in[:len(parts)])))
    in_our_entries = dict(zip((part.what for part in parts), zip(rom_in[len(parts):], ours_in[len(parts):])))
    assert {what for what, (the_rom_s_run, _ours) in in_the_rom_s_text.items() if the_rom_s_run} == entered, in_the_rom_s_text
    assert THE_CURSOR not in entered, "justretf's slot: entered by neither run (held by the scan and by gem_main's stretches)"
    for what in in_the_rom_s_text:
        (the_rom_s_run, our_run), (the_rom_s_run_in_ours, our_run_in_ours) = in_the_rom_s_text[what], in_our_entries[what]
        assert our_run == 0 == the_rom_s_run_in_ours, f"{what}: our run {our_run} cycles in the ROM's text, the ROM's {the_rom_s_run_in_ours} in the blob's"
        assert our_run_in_ours == the_rom_s_run, f"{what}: the ROM's routine ran {the_rom_s_run} cycles, our entry {our_run_in_ours}"
    # (our machine idles in OUR dispatcher since band 6's binding: the desk, over our AES, parks through ours)
    assert ours_after.observed == rom_after.observed and (ours_after.idle, rom_after.idle) == (aes_boot.OURS, aes_boot.THE_ROM_S)
    # THE SCAN, where the continuation ends
    assert left_the_rom_s(ours_after) == {} and aes_boot.vet_no_entry_is_held_as_the_rom_s(ours_after)
    walked = aes_event.userblk_slots(ours_after.ram)
    assert len(walked) == (THE_TRAMPOLINE in entered) and all(
        ours_after.long(slot) == isr.blob_named(blob).entry("aes_rom_ub_trampoline") for _none, slot in walked)
    # THE MEGABYTE
    classes, nameable = aes_boot.by_nature(rom_after, ours_after)
    for name, (lo, hi) in aes_boot.GLUE_STACKS.items():
        assert rom_after.ram[lo:hi] != ours_after.ram[lo:hi], f"{name}: named, and the two machines hold the same bytes there"
    # ...the two idles' (two dispatchers since the binding) and THE BOUND DESK'S (`aes_ctlmgr.the_bound_desk_s_classes`)
    left_out = sorted((*classes.values(), *aes_boot.GLUE_STACKS.values(), *nameable.values(),
                       *aes_ctlmgr.the_bound_desk_s_classes(rom_after, ours_after).values(), *the_bound_desk_s_draw(ours_after),
                       *the_glue_s_parked_return(rom_after, ours_after, blob)))
    assert all(hi <= lo_after for (_lo, hi), (lo_after, _hi) in zip(left_out, left_out[1:])), "the classes do not overlap"
    mine = given_the_rom_s_names(ours_after, blob)
    differing = [(at, length) for at, length in aes_boot.differing_runs(rom_after.ram, bytes(mine))
                 if not any(lo <= at and at + length <= hi for lo, hi in left_out)]
    assert differing == [], f"behind THE DOOR the continued machine differs outside the classes at {[(hex(at), n) for at, n in differing[:6]]}"


@every_blob
def test_the_glue_s_parked_return_is_named_on_the_shipped_blob_alone_where_drive_check_ran(blob):
    """THE NAME FIRES WHERE IT IS FOR (`the_glue_s_parked_return`): the text window's continuation opens drive A:'s window
    (drive_check, flipped) — on the shipped blob our machine holds the glue's return in AES_BIOS_RETURN and the ROM's its
    caller's, so it is named; on the bench blob, whose C calls trp13's C twin, nothing is."""
    machine, view, receives, _entered = CONTINUED_BEHIND_THE_DOOR["the DESKTOP.INF machine as text: drive A:'s window opened"]
    rom, behind = inf(view), behind_the_door(machine, blob, view)
    received = receives(rom)
    named = the_glue_s_parked_return(rom.continued(*received), behind.continued(*received), blob)
    assert named == (((aes.AES_BIOS_RETURN, aes.AES_BIOS_RETURN + LONG_BYTES),) if blob == battery.THE_SHIPPED_BLOB else ())


@every_blob
def test_a_continued_door_machine_compared_with_no_code_address_mapped_differs_where_the_addresses_travelled(blob):
    """THE COMPARE'S TEETH (the test above), on the text window's continuation: taken AS THE MEGABYTE STANDS — nothing
    given the ROM's name — the door machine differs from the ROM-booted one, outside the classes, in the door's own
    longwords, the walked USERBLK and the fork queue's codes; and mapped through the registry but NOT in the dead
    spans it differs in exactly TWO longwords — one on the desk's own stack under its parked stack pointer, the
    trampoline's address the desk's draw left in its frame; one on the desk's G_USERDEF stack, the return site of the
    trampoline's own `jsr` into the desk's draw code, the same offset inside the routine on both shores. SINCE BAND 6's
    BINDING the desk's stack and its G_USERDEF stack hold our AES's frames under the desk's — classes by nature, and
    the two longwords found by what the ROM's machine holds there: the return site on the G_USERDEF stack is still
    ours at the same offset; the trampoline's address in the desk's own dead frame is OVERWRITTEN on ours by our AES's
    frames (the binding's by nature: the ROM's machine alone keeps it)."""
    machine, view, receives, _entered = CONTINUED_BEHIND_THE_DOOR["the DESKTOP.INF machine as text: drive A:'s window opened"]
    rom, behind = inf(view), behind_the_door(machine, blob, view)
    received = receives(rom)
    rom_after, ours_after = rom.continued(*received), behind.continued(*received)
    classes, nameable = aes_boot.by_nature(rom_after, ours_after)
    left_out = (*classes.values(), *aes_boot.GLUE_STACKS.values(), *nameable.values(),
                *aes_ctlmgr.the_bound_desk_s_classes(rom_after, ours_after).values(), *the_bound_desk_s_draw(ours_after),
                *the_glue_s_parked_return(rom_after, ours_after, blob))

    def outside_the_classes(mine):
        """The longwords the two megabytes differ in outside the classes: each run of differing bytes ends where a
        code address does (two addresses of one megabyte differ from their second byte on)."""
        return sorted({at + length - LONG_BYTES for at, length in aes_boot.differing_runs(rom_after.ram, bytes(mine))
                       if not any(lo <= at < hi for lo, hi in left_out)})

    unmapped = set(outside_the_classes(ours_after.ram))
    (_none, userblk), = aes_event.userblk_slots(ours_after.ram)
    assert unmapped >= {*LEFT_THE_ROM_S_BEHIND_THE_TRAP_DOOR_ALONE, addrs.VECTOR_TRAP_GEM, aes_event.ETV_CRITIC, userblk}
    in_the_fork_queue = [at for at in unmapped if aes.AES_FORK_QUEUE <= at < aes.AES_FORK_QUEUE + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES]
    assert in_the_fork_queue, "our glue queued OUR fork functions"
    built = isr.blob_named(blob)
    assert outside_the_classes(given_the_rom_s_names(ours_after, blob, in_the_dead_spans=False)) == []
    desk, our_trampoline = ours_after.static_processes()[0], built.entry("aes_rom_ub_trampoline")
    trampoline_s_text = range(aes_event.USERBLK_TRAMPOLINE, aes_event.USERBLK_TRAMPOLINE_END)
    in_the_two = (aes_ctlmgr.the_desk_s_stack(ours_after), dead_spans_a_code_address_is_left_in(ours_after)[USERDEF_STACK])
    holding = [at for span_lo, span_hi in in_the_two for at in range(span_lo + span_lo % WORD_BYTES, span_hi - LONG_BYTES + 1, WORD_BYTES)
               if rom_after.long(at) in trampoline_s_text]
    in_its_frame, on_its_userdef_stack = holding
    assert desk.uda + aes.UDA_STATE_BYTES <= in_its_frame < ours_after.long(desk.uda + aes.UDA_SUPER_SP) & BUS
    assert rom_after.long(in_its_frame) == aes_event.USERBLK_TRAMPOLINE != ours_after.long(in_its_frame)
    lo, hi = dead_spans_a_code_address_is_left_in(ours_after)[USERDEF_STACK]
    assert lo <= on_its_userdef_stack < hi and hi == ours_after.long(aes.AES_USERDEF_STACK) & BUS == rom_after.long(aes.AES_USERDEF_STACK) & BUS
    back_to = rom_after.long(on_its_userdef_stack) - aes_event.USERBLK_TRAMPOLINE
    assert 0 < back_to < aes_event.USERBLK_TRAMPOLINE_END - aes_event.USERBLK_TRAMPOLINE and ours_after.long(on_its_userdef_stack) == our_trampoline + back_to
    assert outside_the_classes(given_the_rom_s_names(ours_after, blob)) == []


@every_blob
def test_a_door_that_maps_the_trampoline_s_slot_has_its_own_entry_watched(blob):
    """`trampoline_stops`, FOR THE DAY THE DOOR MAPS IT: an `Ours` whose door holds the trampoline's part is watched
    at the ROM's entry AND at the blob's own (found by symbol), with the one reader — the desk's draw code calls
    either through the same USERBLK, with the same frame."""
    ours = aes_boot.ours_of(isr.blob_named(blob), door=(aes_event.USERBLK_TRAMPOLINE_SLOT,))
    (_rom, entry), = ours.door[0].mapping
    stops = aes_boot.trampoline_stops(ours)
    assert set(stops) == {aes_event.USERBLK_TRAMPOLINE, entry} and len(set(stops.values())) == 1
    frame = bytearray(RAM_BYTES)
    frame[0x1004:0x1008] = struct.pack(">I", 0x2000)
    frame[0x2000 + aes.PARM_OBJECT:0x2000 + aes.PARM_OBJECT + WORD_BYTES] = struct.pack(">H", 9)
    frame[0x2000 + aes.PARM_PARM:0x2000 + aes.PARM_PARM + LONG_BYTES] = struct.pack(">I", 0x12345678)
    name, read = stops[entry]
    assert name == aes_boot.TRAMPOLINE and read(frame, 0x1000) == (9, 0x12345678)
