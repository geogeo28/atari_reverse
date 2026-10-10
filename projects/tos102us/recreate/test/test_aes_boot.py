"""THE PRE-INIT MACHINE AND THE MACHINES THE ROM BOOTS OUT OF IT (`aes_boot.py`, `tools/preinit_snapshot.py`) — held by
what each IS, over ANY capture.

NOTHING HERE PINS A NUMBER A CAPTURE DECIDES. A fresh `make preinit` stops with other clocks and other dead frames
(`preinit_snapshot.MASK`), and the orchestrator's gate captures fresh every time: every address below is read through
the machine's own pointers (a PD's UDA, a basepage's TEXT base, a list's links), every count is derived (the EVBs
from the two loops of the ROM that link them), and what the ROM's own text decides — which is the same in every
capture — is read out of the ROM where the test names it.

WHAT IS HELD:
  * THE PRE-INIT MACHINE is the machine about to run `gem_entry`'s first instruction as a program, with no GEM
    variable written; its file round-trips; its mask is well formed;
  * A BOOTED MACHINE stands at the dispatcher's idle with every process waiting, the interrupt mask where the
    machine's horizontal blank leaves it, and the EVBs all accounted for;
  * THE ACCESSORY MACHINE is that, with both accessories loaded by the ROM's loader as the ROM lays them — the first
    in the spare static PD with no EVBs of its own, the second in an allocated block with five — and each one's own
    memory saying what the AES answered it;
  * THE DEVICE MODEL served what it says it serves, at addresses the ROM's own bytes hold it to;
  * NO MACHINE DEPENDS ON A BYTE THE CAPTURE DOES NOT REPRODUCE: booted from a pre-init machine whose masked bytes
    are noise, the ROM reaches the same machine;
  * THE POST-BOOT SNAPSHOT IS UNTOUCHED, and the desk's machine is its family: its own boot, met at the first idle.
"""
import fnmatch
import functools
import hashlib
import random
import struct

import pytest

import derived
import harness
from harness import BASE_IMAGE, addrs, emu, make_image

import boot_snapshot
import preinit_snapshot
import st_build

import accessory_disk
import aes
import aes_boot
import aes_gemctrl
import aes_pdpipe as pp
import case
import fs_pexec
import vdi
from aes_boot import FIND, HIDE, MULTI, QUIET, REGISTER, WRITE

RAM_BYTES = aes_boot.RAM_BYTES
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes_boot.BUS
SR_INTERRUPT_MASK = 0x0700
FIRST, SECOND = aes_boot.ACCESSORY_NAMES
DESK_PID, SCREEN_MANAGER_PID = 0, 1
SIX_WAYS = 6                            # the EVBs a six-way evnt_multi holds: one per kind of event
MESSAGE_BYTES = 16
SENDER_WORD = 1                         # a message's second word: who sent it
RESOLUTION_MODE = 0x03                  # the shifter's resolution byte: bits 0-1 are the mode (`addrs.h`)


def rom_word(at):
    return case.word_in(BASE_IMAGE, at)


# ---- the machines of this tree -------------------------------------------------------------------------------------------
BUSY = FIND | WRITE | MULTI
BOOTS = {
    "the desk alone": lambda: aes_boot.desk_machine(),
    "two quiet accessories": lambda: aes_boot.accessory_machine(),
    "the first finds the second, writes to it and waits six ways": lambda: aes_boot.accessory_machine(first=BUSY),
    "both wait six ways": lambda: aes_boot.accessory_machine(MULTI, MULTI),
    "the first writes to the desk": lambda: aes_boot.accessory_machine(first=WRITE),
}
ACCESSORY_BOOTS = [label for label in BOOTS if label != "the desk alone"]


@functools.cache
def machine(label):
    return BOOTS[label]()


every_boot = pytest.mark.parametrize("label", BOOTS)
every_accessory_boot = pytest.mark.parametrize("label", ACCESSORY_BOOTS)


def pre():
    return aes_boot.preinit()


def pre_of(label):
    """The pre-init machine the boot `label` starts from: the capture made with ITS disk in the drive."""
    return aes_boot.preinit() if label == "the desk alone" else aes_boot.accessory_preinit()


CAPTURES = {"with the blank disk": aes_boot.preinit, "with the accessories' disk": aes_boot.accessory_preinit}
DISKS = {"with the blank disk": aes_boot.blank_disk, "with the accessories' disk": lambda: aes_boot.accessory_disk_of(QUIET, QUIET)}
every_capture = pytest.mark.parametrize("capture", CAPTURES)
MOVEA_L_IMMEDIATE_SP = 0x2e7c           # movea.l #<long>,sp
MOVE_L_IMMEDIATE_TO_A0_DISPLACED = 0x217c           # move.l #<long>,<d16>(a0)


# ---- THE PRE-INIT MACHINE ------------------------------------------------------------------------------------------------
@every_capture
def test_the_pre_init_machine_stands_at_the_shell_s_entry_as_a_program(capture):
    """The PC is `gem_entry`, which the machine's own `exec_os` names; the CPU is in user mode, on the stack at the
    top of a TPA that is ALL of free memory; and the longword above the stack pointer — the one `gem_entry` reads —
    is a basepage whose program is `gem_entry` itself."""
    registers, ram = CAPTURES[capture]().registers, CAPTURES[capture]().ram
    assert registers["pc"] == case.long_in(ram, preinit_snapshot.EXEC_OS) == addrs.AES_ROM_GEM_ENTRY
    assert not registers["sr"] & preinit_snapshot.SR_SUPERVISOR
    basepage = case.long_in(ram, registers["usp"] + LONG_BYTES)
    assert case.long_in(ram, basepage + addrs.BASEPAGE_LOWTPA) == basepage
    assert case.long_in(ram, basepage + addrs.BASEPAGE_TBASE) == addrs.AES_ROM_GEM_ENTRY
    top = case.long_in(ram, basepage + addrs.BASEPAGE_HITPA)
    assert top == case.long_in(ram, addrs.SYSVAR_MEMTOP)
    assert case.long_in(ram, addrs.SYSVAR_MEMBOT) <= basepage < registers["usp"] < top


def gem_entry_s_first_stack():
    """The stack `gem_entry` moves to before anything else: its second instruction's operand (`movea.l #...,sp`)."""
    opcode, stack = struct.unpack_from(">HI", BASE_IMAGE, addrs.AES_ROM_GEM_ENTRY + WORD_BYTES)
    assert opcode == MOVEA_L_IMMEDIATE_SP
    return stack


@every_capture
def test_the_pre_init_registers_are_the_ones_the_launch_leaves(capture):
    """GEMDOS enters a program with every register cleared but the two it leaves its own frame's address in: a
    register file read wrongly off the capture (or off its file) is not this one — and the boot would carry it into
    the machine (`test_a_wrong_entry_register_reaches_the_booted_machine`)."""
    registers = CAPTURES[capture]().registers
    cleared = [name for name in (*preinit_snapshot.DATA_REGISTERS, *preinit_snapshot.ADDRESS_REGISTERS) if name not in ("d0", "a6")]
    assert not any(registers[name] for name in cleared)
    assert registers["d0"] == registers["a6"] and registers["a6"] < registers["usp"]
    assert preinit_snapshot.load(PATHS[capture]()).registers == registers


PATHS = {"with the blank disk": preinit_snapshot.preinit_path, "with the accessories' disk": preinit_snapshot.accessory_path}


@pytest.mark.parametrize("register", ("d5", "a3"))
def test_a_wrong_entry_register_reaches_the_booted_machine(register):
    """The capture's registers are not decoration: gem_entry's first traps save the caller's file, and a boot entered
    with one callee-saved register wrong leaves another machine."""
    wrong = pre()._replace(registers={**pre().registers, register: 0x1234})
    assert aes_boot.desk_machine(wrong).ram != machine("the desk alone").ram


@every_capture
def test_no_gem_variable_is_written_in_the_pre_init_machine(capture):
    """From the stack `gem_entry` first moves to, up to the bottom of the TPA — the AES's and the desktop's whole BSS,
    every PD, UDA and list head — the machine is zero; and neither of GEM's two doors is hung yet: the Line-F vector
    and trap #2 still name the BIOS's own."""
    ram = CAPTURES[capture]().ram
    assert not any(ram[gem_entry_s_first_stack():case.long_in(ram, addrs.SYSVAR_MEMBOT)])
    assert case.long_in(ram, addrs.VECTOR_LINE_F) & BUS < addrs.AES_ROM_GEM_ENTRY
    assert emu.ROM_BASE <= case.long_in(ram, addrs.VECTOR_TRAP_GEM) & BUS < addrs.AES_ROM_GEM_ENTRY


@every_capture
def test_the_pre_init_machine_carries_the_shifter_as_the_machine_shadows_it(capture):
    """The resolution the capture read out of the shifter is the one the BIOS's shadow holds, and the palette is the
    ROM's own default table — the one the booted AES then points `colorptr` at."""
    machine_io = CAPTURES[capture]().io
    resolution = machine_io[preinit_snapshot.SHIFTER_RESOLUTION - preinit_snapshot.IO_AT]
    assert resolution & RESOLUTION_MODE == CAPTURES[capture]().ram[addrs.SYSVAR_SSHIFTMD]
    palette = machine_io[:preinit_snapshot.PALETTE_BYTES]
    table = machine("the desk alone").long(addrs.SYSVAR_COLORPTR) & BUS
    assert emu.ROM_BASE <= table and bytes(BASE_IMAGE[table:table + len(palette)]) == palette


@every_capture
def test_the_driver_logged_in_the_disk_the_capture_booted_with(capture):
    """THE DISK IN THE DRIVE AT `gem_entry`, READ OFF THE MACHINE: the driver's record for drive A: holds the BPB of
    the image's boot sector and its three serial bytes, and the driver's boot-sector buffer the same serial — written
    by the ROM's own Getbpb before the capture, from the image this tree serves. (`st_build` derives a serial from the
    files, so a capture made with another build of the accessory is another disk here.)"""
    ram, disk = CAPTURES[capture]().ram, DISKS[capture]()
    record, buffer = aes_boot.driver_record(BASE_IMAGE), aes_boot.driver_boot_sector(BASE_IMAGE)
    serial = accessory_disk.serial_of(disk)
    assert ram[record:record + aes_boot.BPB_WORDS.size] == aes_boot.bpb_of(disk)
    assert ram[record + aes_boot.FLOPPY_RECORD_SERIAL:][:len(serial)] == serial
    assert ram[buffer + st_build.BOOT_SERIAL_AT:][:len(serial)] == serial
    assert accessory_disk.serial_of(aes_boot.blank_disk()) != accessory_disk.serial_of(aes_boot.accessory_disk_of(QUIET, QUIET))


def test_a_pre_init_file_round_trips_and_a_file_that_is_not_one_is_refused():
    packed = preinit_snapshot.packed(pre())
    assert len(packed) == preinit_snapshot.FILE_BYTES and preinit_snapshot.unpacked(packed) == pre()
    for wrong in (packed[:-1], packed[:RAM_BYTES] + bytes(len(packed) - RAM_BYTES), pre().ram):
        with pytest.raises(ValueError, match="not a pre-init machine"):
            preinit_snapshot.unpacked(wrong)


A_REGISTER_DUMP = """
> r
  D0 000F7FC6   D1 00000001   D2 00000002   D3 00000003
  D4 00000004   D5 00000005   D6 00000006   D7 00000007
  A0 00000008   A1 00000009   A2 0000000A   A3 0000000B
  A4 0000000C   A5 0000000D   A6 000F7FC6   A7 000F7FF8
USP  000F7FF8 ISP  0000755A
SR=0300 T=00 S=0 M=0 X=0 N=0 Z=0 V=0 C=0 IM=3 STP=0
Prefetch 2a4f (MOVEA) 2e7c (MOVEA) Chip latch 00000000
00fd9eca 2a4f                     movea.l a7,a5
Next PC: 00fd9ecc
"""


def test_a_register_dump_is_read_as_hatari_prints_it():
    """Every register by its own name, the PC the instruction about to run (not `Next PC`), and A7 held to the stack
    pointer the status register names — a dump read a column off is refused."""
    registers = preinit_snapshot.registers_in(A_REGISTER_DUMP)
    assert registers == {"d0": 0xf7fc6, **{f"d{n}": n for n in range(1, 8)}, **{f"a{n}": 8 + n for n in range(6)},
                         "a6": 0xf7fc6, "usp": 0xf7ff8, "isp": 0x755a, "sr": 0x0300, "pc": 0xfd9eca}
    with pytest.raises(SystemExit, match="A7 is not its USP"):
        preinit_snapshot.registers_in(A_REGISTER_DUMP.replace("A7 000F7FF8", "A7 000F7FF0"))
    with pytest.raises(SystemExit, match="no register dump"):
        preinit_snapshot.registers_in("> cont\n")


def test_a_capture_that_is_not_the_shell_s_entry_is_refused(tmp_path):
    """The capture tool's own vet, on machines that are not the pre-init one: another PC than the machine's `exec_os`
    names, and the right PC in supervisor mode. And a tree with no capture says which target makes one."""
    preinit_snapshot._vet_stopped_at_the_shell_s_entry(pre())
    elsewhere = pre()._replace(registers={**pre().registers, "pc": addrs.AES_ROM_GEM_ENTRY + WORD_BYTES})
    in_supervisor = pre()._replace(registers={**pre().registers, "sr": pre().registers["sr"] | preinit_snapshot.SR_SUPERVISOR})
    for wrong, said in ((elsewhere, "an arbitrary instant"), (in_supervisor, "supervisor mode")):
        with pytest.raises(SystemExit, match=said):
            preinit_snapshot._vet_stopped_at_the_shell_s_entry(wrong)
    with pytest.raises(FileNotFoundError, match="make preinit"):
        preinit_snapshot.load(tmp_path / "preinit.bin")


def test_the_pre_init_mask_is_regions_of_ram_in_order_and_apart():
    ends = 0
    for at, size, why in preinit_snapshot.MASK:
        assert ends <= at and size > 0 and at + size <= RAM_BYTES and why
        ends = at + size
    assert preinit_snapshot.masked(pre().ram) == preinit_snapshot.masked(bytes(pre().ram))


# ---- THE CPU, WHERE A RUN STANDS STOPPED ---------------------------------------------------------------------------------
def test_a_stopped_cpu_is_entered_with_the_whole_register_file_and_returned_from_a_driver_as_by_rts():
    """`_enter` lays every register of the capture — the status register, BOTH stack pointers by their own names —
    and the driver's return is an `rts` with its answer: D0, the PC, four bytes off the stack the CPU stands on, and
    no other register."""
    memory, entry = make_image(pre_pokes()), pre().registers["pc"]
    emu.install_chip_seeds()
    try:
        stopped = emu.run_bench(memory, entry, 0, aes_boot.OFF_THE_MACHINE, emu.SENTINEL, max_insns=1, door={entry})
        assert stopped["status"] == emu.BENCH_DOOR and not stopped["ninsns"]
        aes_boot._enter(pre().registers)
        assert aes_boot._registers_now() == pre().registers
        answer, to, sp = 0x12345678, addrs.AES_ROM_GEM_ENTRY + WORD_BYTES, pre().registers["usp"]
        aes_boot._return_from_the_driver(answer, to, sp)
        assert aes_boot._registers_now() == {**pre().registers, "d0": answer, "pc": to, "usp": sp + LONG_BYTES}
    finally:
        emu.bench_abort()
    assert bytes(memory[:RAM_BYTES]) == pre().ram


# ---- A BOOTED MACHINE ------------------------------------------------------------------------------------------------------
@every_boot
def test_a_booted_machine_stands_at_the_dispatcher_s_idle(label):
    """At idle's poll, in supervisor mode, with nothing ready, nothing woken and no fork queued — inside the
    dispatcher (its guard set), as the post-boot snapshot is."""
    booted = machine(label)
    assert booted.registers["pc"] == addrs.AES_ROM_IDLE_LOOP
    assert booted.registers["sr"] & preinit_snapshot.SR_SUPERVISOR
    assert not (booted.long(aes.AES_RLR) or booted.long(aes.AES_DRL) or booted.word(aes.AES_FORK_COUNT))
    assert booted.ram[aes.AES_INDISP] == aes.AES_INDISP_SET == BASE_IMAGE[aes.AES_INDISP]


@every_boot
def test_a_booted_machine_runs_at_the_mask_the_horizontal_blank_leaves(label):
    """`gem_main`'s `sti` clears the interrupt mask; the ROM's horizontal-blank handler — the one interrupt the boot
    takes, through the machine's own vector — raises it to 3 in the interrupted context, where it stays: ONE blank
    in every boot here. (The model keeps the next one pending from where one is taken; no boot here lowers the mask
    a second time, so that half is unpinned.)"""
    booted = machine(label)
    assert booted.boot.blanks == 1
    assert booted.registers["sr"] & SR_INTERRUPT_MASK == addrs.HBL_IPL_FLOOR


@every_boot
def test_gem_s_two_doors_are_hung(label):
    """Trap #2 names the AES's own entry in the ROM, the Line-F vector the copy of the handler the AES Malloc'd."""
    booted = machine(label)
    assert booted.long(addrs.VECTOR_TRAP_GEM) & BUS >= addrs.AES_ROM_GEM_ENTRY
    handler = booted.long(addrs.VECTOR_LINE_F) & BUS
    assert booted.long(addrs.SYSVAR_MEMBOT) <= handler < RAM_BYTES


@every_boot
def test_every_process_of_a_booted_machine_waits(label):
    """The not-ready list is the desk, the screen manager and each accessory loaded — every one waiting on at least
    one EVB, each with a pid no other has."""
    booted = machine(label)
    waiting = booted.waiting()
    expected = {b"".ljust(aes.PD_NAME_BYTES), b"SCRENMGR"} | (
        {name.encode() for name in aes_boot.ACCESSORY_NAMES} if label != "the desk alone" else set())
    assert {process.name for process in waiting} == expected and len(waiting) == len(expected)
    assert all(process.waiting and process.events for process in waiting)
    assert len({process.pid for process in waiting}) == len(waiting)
    by_pid = {process.pid: process for process in waiting}
    assert by_pid[DESK_PID].name.strip() == b"" and by_pid[SCREEN_MANAGER_PID].name == b"SCRENMGR"


@every_boot
def test_every_waiting_process_is_parked_on_its_own_uda_s_stack(label):
    """WHERE EACH UDA LIES: the static ones end to end below the PD table (the desk's, the screen manager's, the
    spare PD's), an allocated accessory's right after its PD — and the supervisor stack pointer each waiting process
    was parked with is inside its own UDA, above the state block."""
    booted = machine(label)
    static = booted.static_processes()
    assert static[0].uda + sum(booted.static_uda_bytes()) == aes.AES_PD_TABLE
    sizes = {process.pd: size for process, size in zip(static, booted.static_uda_bytes())}
    sizes.update({process.pd: aes_boot.ACCESSORY_UDA_BYTES for process in booted.allocated_accessories()})
    for process in booted.waiting():
        parked = booted.long(process.uda + aes.UDA_SUPER_SP)
        assert process.uda + aes.UDA_STATE_BYTES < parked <= process.uda + sizes[process.pd]


def supplied(at):
    """How many EVBs one of the ROM's two linking loops supplies: its `cmp.w #n,d7`."""
    opcode, count = struct.unpack_from(">2H", BASE_IMAGE, at)
    assert opcode == aes_boot.CMP_W_IMMEDIATE_D7
    return count


@every_boot
def test_every_evb_is_free_or_on_a_process_s_list(label):
    """THE SUPPLY IS THE ROM'S TWO LOOPS: gem_main links fifteen, and each ALLOCATED accessory (every one but the
    first) brings five. What is not on the free list is on a waiting process's own — no EVB is lost, none counted
    twice."""
    booted = machine(label)
    supply = (supplied(aes_boot.GEM_MAIN_EVB_COUNT_AT)
              + supplied(aes_boot.ACCESSORY_EVB_COUNT_AT) * len(booted.allocated_accessories()))
    held = [evb for process in booted.waiting() for evb in process.events]
    free = booted.free_events()
    assert len(set(held) | set(free)) == len(held) + len(free) == supply


@every_boot
def test_the_desk_s_screen_is_the_snapshot_s(label):
    """The desktop every boot draws is the one the post-boot snapshot shows, pixel for pixel: an accessory draws
    nothing, and nothing in the nine hundred vertical blanks the snapshot waits changes the screen."""
    booted = machine(label)
    screen = booted.long(addrs.SYSVAR_V_BAS_AD)
    assert screen == case.long_in(BASE_IMAGE, addrs.SYSVAR_V_BAS_AD)
    assert booted.ram[screen:RAM_BYTES] == bytes(BASE_IMAGE[screen:RAM_BYTES])


# ---- THE ACCESSORY MACHINE ---------------------------------------------------------------------------------------------------
@every_accessory_boot
def test_the_first_accessory_has_the_spare_static_pd_and_the_second_an_allocated_one(label):
    """WHAT PLAN §0 READ FROM THE CODE, MEASURED. The first accessory runs in the THIRD PD of the AES's own table —
    no block allocated, its basepage parked where sndcli parks it — and is NOT in `$c6b2[]`; the second's PD is the
    one entry there, at the head of a block of its own GEMDOS allocated above the AES's BSS: PD, then UDA, with its
    CDA and its five EVBs inside the block's 2,226 bytes."""
    booted = machine(label)
    first, second = booted.named(FIRST), booted.named(SECOND)
    assert booted.static_processes()[aes.AES_PD_COUNT - 1] == first
    assert booted.long(aes_boot.FIRST_ACCESSORY_BASEPAGE) & BUS == first.basepage
    assert booted.allocated_accessories() == (second,)
    assert not any(booted.long(aes.AES_ACCESSORY_PDS + index * LONG_BYTES) for index in range(1, aes_boot.ACCESSORY_SLOTS))
    block = range(second.pd, second.pd + aes_boot.ACCESSORY_BLOCK_BYTES)
    assert second.pd >= booted.long(addrs.SYSVAR_MEMBOT) and second.uda == second.pd + aes.PD_BYTES
    assert second.cda in block and second.uda + aes_boot.ACCESSORY_UDA_BYTES <= second.cda
    in_the_block = [evb for process in booted.waiting() for evb in process.events if evb in block]
    in_the_block += [evb for evb in booted.free_events() if evb in block]
    assert len(in_the_block) == supplied(aes_boot.ACCESSORY_EVB_COUNT_AT)


def test_the_loader_s_own_text_names_what_these_tests_read():
    """sndcli stores the first accessory's basepage at FIRST_ACCESSORY_BASEPAGE (an absolute-long operand of its own
    body); the allocator asks GEMDOS for ACCESSORY_BLOCK_BYTES."""
    body = bytes(BASE_IMAGE[aes_boot.SNDCLI:aes_boot.SNDCLI_END])
    assert struct.pack(">I", aes_boot.FIRST_ACCESSORY_BASEPAGE) in body
    opcode, asked = struct.unpack_from(">HI", BASE_IMAGE, aes_boot.ACCESSORY_BLOCK_ASKED_AT)
    assert opcode == aes_boot.MOVE_L_IMMEDIATE_TO_STACK and asked == aes_boot.ACCESSORY_BLOCK_BYTES


STACK_REACHED_AT_MOST = 0x80            # of the accessory's own stack: the trap's `movem.l d1-a6` on it, and a `bsr`


def written_by_the_accessory(booted, process, mode):
    """The words of its own TEXT and DATA a test accessory writes as it runs, `{offset from TEXT: bytes}` — each AS
    THE MACHINE HOLDS IT: the five answers it keeps, the id it found (kept as its message's target) and the sender's
    id in the message it sends."""
    symbols = aes_boot.accessory().symbols
    words = [symbols[name] for name in aes_boot.RESULT_WORDS]
    words += [symbols["acc_write_to"]] if mode & FIND else []
    words += [symbols["sent"] + SENDER_WORD * WORD_BYTES] if mode & WRITE else []
    text = booted.long(process.basepage + addrs.BASEPAGE_TBASE)
    return {at: booted.ram[text + at:text + at + WORD_BYTES] for at in words}


@every_accessory_boot
def test_each_accessory_is_the_file_on_the_disk_loaded_and_relocated_by_the_rom(label):
    """A LOADED ACCESSORY IS ITS FILE, WHOLE: every byte of TEXT and DATA the image on the disk holds for it (its mode
    word among them), the TEXT base added to each longword its relocation table names (`fs_pexec.relocated`) — but
    for the few words the accessory itself writes — and a BSS the loader cleared: the part of its stack no call
    reaches is zero, and so is the message buffer of an accessory no wait came back to."""
    booted = machine(label)
    built, disk = aes_boot.accessory(), booted.boot.disk
    fixups = aes_boot.fixups_of(built.file)
    text_bytes, data_bytes, bss_bytes, _symbols = aes_boot.lengths_of(built.file)
    loaded_bytes = text_bytes + data_bytes
    assert fixups, "the accessory is built with absolute longwords: a table that names none proves no relocation"
    for index, name in enumerate(aes_boot.ACCESSORY_NAMES):
        process = booted.named(name)
        text = booted.long(process.basepage + addrs.BASEPAGE_TBASE)
        assert text == process.basepage + aes_boot.BASEPAGE_BYTES
        on_disk = disk[accessory_disk.file_at(index) + aes_boot.PRG_HEADER_BYTES:][:loaded_bytes]
        mode = case.word_in(on_disk, built.symbols["acc_mode"])
        expected = bytearray(fs_pexec.relocated(on_disk, fixups, text))
        for at, word in written_by_the_accessory(booted, process, mode).items():
            expected[at:at + len(word)] = word
        assert booted.ram[text:text + loaded_bytes] == bytes(expected)
        stack_top = text + built.symbols["stack_top"]
        assert stack_top == text + loaded_bytes + bss_bytes
        stack_bottom = text + built.symbols["received"] + MESSAGE_BYTES
        assert not any(booted.ram[stack_bottom:stack_top - STACK_REACHED_AT_MOST])
        if not booted.results(process)["res_wakes"]:
            assert not any(booted.ram[text + built.symbols["received"]:stack_bottom])


# EVERY MODE ANY BATTERY BOOTS AN ACCESSORY IN — this battery's, and the screen manager's handlers' machines
# (`aes_gemctrl.ACCESSORY_MODES`: a window of each kind they need, a menu entry, the bar hidden), READ OFF THEM so a
# machine added there is held here the day it is.
MODES = tuple(sorted({QUIET, FIND, WRITE, MULTI, BUSY, REGISTER | HIDE,
                      *(mode for pair in aes_gemctrl.ACCESSORY_MODES.values() for mode in pair)}))


def test_the_disk_is_one_disk_to_the_machine_whatever_the_modes():
    """EVERYTHING THE MACHINE READS BEFORE `gem_entry` IS THE SAME BYTES FOR EVERY MODE PAIR: the boot sector (its
    serial), both FATs, the root directory — in fact every byte of the image outside the one longword of each
    accessory's own cluster that says its mode (a window's kind, then the flags). So one capture, made with the quiet pair's disk in the drive, is the
    pre-init machine of all of them: GEMDOS's cache and the driver's record are every pair's."""
    assert set(MODES) >= {mode for pair in aes_gemctrl.ACCESSORY_MODES.values() for mode in pair} and len(MODES) >= 12
    quiet = aes_boot.accessory_disk_of(QUIET, QUIET)
    mode_words = [accessory_disk.file_at(index) + accessory_disk.mode_word_at(aes_boot.accessory())
                  for index in range(len(aes_boot.ACCESSORY_NAMES))]
    assert all(at >= st_build.FIRST_DATA_SECTOR * st_build.SECTOR_BYTES for at in mode_words)
    assert quiet == accessory_disk.disk_path().read_bytes(), "the image the capture booted is not this tree's"
    for first in MODES:
        for second in MODES:
            image = bytearray(aes_boot.accessory_disk_of(first, second))
            assert [case.long_in(image, at) for at in mode_words] == [first, second]
            for at in mode_words:
                image[at:at + LONG_BYTES] = bytes(LONG_BYTES)
            assert bytes(image) == quiet


def test_a_relocation_table_is_read_with_its_skips():
    """The reader the test above stands on, over a table the accessory's own does not have: a fixup more than 254
    bytes past the one before, which the stream carries with a skip byte (`fs_pexec`'s encoder, the loader's own
    battery's)."""
    fixups = (4, 4 + 2 * fs_pexec.PRG_SKIP_DISTANCE + 6, 4 + 2 * fs_pexec.PRG_SKIP_DISTANCE + 10)
    program = fs_pexec.program("FAR", bytes(0x300), fixups=fixups)
    assert fs_pexec.PRG_SKIP in program.relocation
    assert aes_boot.fixups_of(program.file) == fixups
    assert aes_boot.fixups_of(fs_pexec.program("PLAIN", bytes(0x10)).file) == ()


@every_accessory_boot
def test_each_accessory_was_answered_its_own_id(label):
    """What the ROM's appl_init answered each accessory — kept in the accessory's own DATA — is the pid its PD holds."""
    booted = machine(label)
    for name in aes_boot.ACCESSORY_NAMES:
        process = booted.named(name)
        assert booted.results(process)["res_id"] == process.pid


def test_two_quiet_accessories_wait_for_a_message_having_done_nothing_else():
    booted = machine("two quiet accessories")
    for name in aes_boot.ACCESSORY_NAMES:
        process = booted.named(name)
        assert len(process.events) == 1 and booted.results(process)["res_wakes"] == 0
        assert booted.results(process)["res_find"] == booted.results(process)["res_write"] == aes_boot.NOT_CALLED


def received_by(booted, process):
    text = booted.long(process.basepage + addrs.BASEPAGE_TBASE)
    at = text + aes_boot.accessory().symbols["received"]
    return booted.ram[at:at + MESSAGE_BYTES]


def sent_by(booted, process):
    text = booted.long(process.basepage + addrs.BASEPAGE_TBASE)
    at = text + aes_boot.accessory().symbols["sent"]
    return booted.ram[at:at + MESSAGE_BYTES]


def test_the_first_accessory_finds_the_second_through_the_accessories_table_and_its_message_arrives():
    """THE DEBTS' MACHINE. appl_find by name answers the second accessory's pid — a PD only fpdnm's walk of `$c6b2[]`
    reaches; appl_write to it is answered 1; the second accessory was woken ONCE by its evnt_mesag and holds the
    sixteen bytes the first sent, the sender's id in them; and the first then waits SIX WAYS, on six EVBs."""
    booted = machine("the first finds the second, writes to it and waits six ways")
    first, second = booted.named(FIRST), booted.named(SECOND)
    results = booted.results(first)
    assert results["res_find"] == second.pid and results["res_write"] == 1 and results["res_wakes"] == 0
    assert booted.results(second)["res_wakes"] == 1
    message = received_by(booted, second)
    assert message == sent_by(booted, first)
    assert case.word_in(message, SENDER_WORD * WORD_BYTES) == first.pid
    assert len(first.events) == SIX_WAYS and len(second.events) == 1


def test_two_six_way_waits_leave_two_evbs_free_of_twenty():
    """PLAN §0'S INEQUALITY, MEASURED ONE WAIT SHORT OF IT: the desk and the screen manager hold three EVBs each,
    two accessories in a six-way evnt_multi six each — eighteen of the twenty supplied. An APPLICATION in PD0 asking
    six where the desk asks three makes it twenty-one against twenty: get_evb's empty free list is reachable."""
    booted = machine("both wait six ways")
    held = {process.pid: len(process.events) for process in booted.waiting()}
    supply = supplied(aes_boot.GEM_MAIN_EVB_COUNT_AT) + supplied(aes_boot.ACCESSORY_EVB_COUNT_AT)
    assert held[booted.named(FIRST).pid] == held[booted.named(SECOND).pid] == SIX_WAYS
    assert len(booted.free_events()) == supply - sum(held.values())
    assert sum(held.values()) - held[DESK_PID] + SIX_WAYS > supply


def test_a_message_written_to_the_desk_is_read_by_the_desk():
    """The first accessory's appl_write to pid 0 is answered 1, and by the first idle the desk has taken the sixteen
    bytes out of its pipe (the pipe's index is back at 0, the bytes still where they lay) and waits again."""
    booted = machine("the first writes to the desk")
    first, = [process for process in booted.waiting() if process.name == FIRST.encode()]
    desk, = [process for process in booted.waiting() if process.pid == DESK_PID]
    assert booted.results(first)["res_write"] == 1
    assert booted.word(desk.pd + aes.PD_QUEUE_INDEX) == 0
    assert booted.ram[desk.pd + aes.PD_QUEUE:desk.pd + aes.PD_QUEUE + MESSAGE_BYTES] == sent_by(booted, first)
    assert desk.waiting


# ---- THE DEVICE MODEL ------------------------------------------------------------------------------------------------------
def test_the_device_model_s_addresses_are_the_rom_s_own():
    """The blitter probe: the bus-error vector pointed at its own tail (`move.l #tail,8(a0)`), the touch of the
    blitter's registers right after, the tail restoring the vector. The floppy driver: Getbpb's record load. The
    disk vectors of the pre-init machine: three routines of the ROM. The horizontal blank's vector: the ROM's
    handler."""
    opcode, tail, displacement = struct.unpack_from(">HIH", BASE_IMAGE, aes_boot.BLITTER_PROBE_TOUCH - 8)
    assert (opcode, tail, displacement) == (MOVE_L_IMMEDIATE_TO_A0_DISPLACED, aes_boot.BLITTER_PROBE_FAULTED, aes_boot.VECTOR_BUS_ERROR)
    assert struct.unpack_from(">2H", BASE_IMAGE, aes_boot.BLITTER_PROBE_TOUCH) == aes_boot.BLITTER_PROBE_TOUCH_WORDS
    assert aes_boot.BLITTER_PROBE < aes_boot.BLITTER_PROBE_TOUCH < aes_boot.BLITTER_PROBE_FAULTED
    assert rom_word(aes_boot.FLOPPY_GETBPB_RECORD_LOAD) == aes_boot.ADDA_L_IMMEDIATE_A5
    assert rom_word(aes_boot.FLOPPY_BOOT_SECTOR_BUFFER_LOAD) == aes_boot.ADDA_L_IMMEDIATE_A1
    for capture in CAPTURES.values():
        for vector in (addrs.HDV_BPB, addrs.HDV_MEDIACH, addrs.HDV_RWABS):
            assert emu.ROM_BASE <= case.long_in(capture().ram, vector) < addrs.AES_ROM_GEM_ENTRY
        assert case.long_in(capture().ram, addrs.VECTOR_HBL) == addrs.ISR_HBL


@every_boot
def test_the_blitter_probe_took_its_bus_error_on_the_stack_it_ran_on(label):
    """THE MACHINE'S MEMORY WHERE THE PROBE'S TAIL IS ENTERED (read out of it there, not the model's own record): one
    group-0 frame at the supervisor stack pointer, inside the UDA of the process that asked (the desk) — a READ of
    supervisor data in its status word, the blitter's address, the touch's opcode, the status register at mask 7 as
    the probe raised it, a PC inside the probe. The frame is DEAD from that instruction on (the tail reloads SP from
    A2) and the desk's later calls write over it: nothing is claimed of it in the booted machine."""
    booted = machine(label)
    (at, frame), = booted.boot.bus_error_frame.items()
    status, access, opcode, stacked_sr, stacked_pc = aes_boot._BUS_ERROR_FRAME.unpack(frame)
    desk = booted.static_processes()[DESK_PID]
    assert desk.uda + aes.UDA_STATE_BYTES <= at < desk.uda + booted.static_uda_bytes()[DESK_PID]
    assert status & aes_boot.STATUS_READ and status & FUNCTION_CODE == aes_boot.STATUS_SUPERVISOR_DATA
    assert access == aes_boot.BLITTER_REGISTERS and opcode == aes_boot.BLITTER_PROBE_TOUCH_WORDS[0]
    assert aes_boot.BLITTER_PROBE_TOUCH < stacked_pc <= aes_boot.BLITTER_PROBE_FAULTED
    assert stacked_sr & SR_INTERRUPT_MASK == SR_INTERRUPT_MASK and stacked_sr & preinit_snapshot.SR_SUPERVISOR
    stored = {offset for start, length in booted.boot.stored for offset in range(start, start + length)}
    assert set(range(at, at + len(frame))) <= stored


FUNCTION_CODE = 0x7                     # a bus error's status word: the function code of the access


@every_boot
def test_the_driver_is_asked_whether_the_disk_changed_and_to_read(label):
    """Over the disk its capture booted with, a boot asks the driver two things only: whether the medium changed —
    it did not — and to READ; the disk is left as it was. The desk alone reads nothing (GEMDOS answers from what it
    cached before `gem_entry`); the accessories' boot reads each accessory's own first sector, and the root."""
    booted = machine(label)
    calls = booted.boot.floppy
    assert calls and {call.function for call in calls} <= {aes_boot.MEDIACH, aes_boot.RWABS}
    assert {call.answer for call in calls if call.function == aes_boot.MEDIACH} == {addrs.MEDIACH_UNCHANGED}
    reads = [call.arguments for call in calls if call.function == aes_boot.RWABS]
    assert not any(flag & aes_boot.RWABS_WRITE for flag, *_rest in reads)
    records = {record for _flag, _buffer, count, first, _device in reads for record in range(first, first + count)}
    if label == "the desk alone":
        assert not reads and booted.boot.disk == aes_boot.blank_disk()
        return
    root = st_build.RESERVED_SECTORS + st_build.FAT_COPIES * st_build.SECTORS_PER_FAT
    files = {accessory_disk.file_at(index) // st_build.SECTOR_BYTES for index in range(len(aes_boot.ACCESSORY_NAMES))}
    assert {root} | files <= records
    modes = (booted.accessory_word(booted.named(name), "acc_mode") for name in aes_boot.ACCESSORY_NAMES)
    assert booted.boot.disk == aes_boot.accessory_disk_of(*modes)


def test_a_disk_the_machine_did_not_boot_with_is_refused():
    """The model swaps no disk in: one of another geometry, and one of the right geometry and ANOTHER SERIAL (the
    accessories' over the capture made with the blank one, and the other way round), are refused by name before a
    single instruction runs."""
    other = bytearray(aes_boot.blank_disk())
    other[st_build.BPB_AT + 2] = 2 * st_build.SECTORS_PER_CLUSTER
    with pytest.raises(aes_boot.Refused, match="another geometry"):
        aes_boot.Floppy(make_image(pre_pokes()), other)
    for capture, disk in ((aes_boot.preinit, aes_boot.accessory_disk_of(QUIET, QUIET)),
                          (aes_boot.accessory_preinit, aes_boot.blank_disk())):
        with pytest.raises(aes_boot.Refused, match="booted with another disk"):
            aes_boot.booted.derive(capture(), disk)


def pre_pokes():
    return {0: pre().ram}


def test_the_floppy_answers_drive_a_alone_only_inside_the_disk_and_no_getbpb():
    memory = make_image(pre_pokes())
    floppy = aes_boot.Floppy(memory, aes_boot.blank_disk())
    stack = harness.emu.STACK_TOP
    entry = {function: at for at, function in floppy.entries.items()}

    def call(function, *words):
        memory[stack + LONG_BYTES:stack + LONG_BYTES + len(words) * WORD_BYTES] = struct.pack(f">{len(words)}H", *words)
        return floppy.served(entry[function], stack)[0]

    assert call(aes_boot.MEDIACH, aes_boot.DRIVE_A) == addrs.MEDIACH_UNCHANGED
    with pytest.raises(aes_boot.Refused, match="drive A: alone"):
        call(aes_boot.MEDIACH, aes_boot.DRIVE_A + 1)
    with pytest.raises(aes_boot.Refused, match="Getbpb of drive 0"):
        call(aes_boot.GETBPB, aes_boot.DRIVE_A)
    past = len(floppy.disk) // st_build.SECTOR_BYTES
    with pytest.raises(aes_boot.Refused, match="leaves the disk"):
        call(aes_boot.RWABS, 0, 0, 0x8000, 1, past, aes_boot.DRIVE_A)
    with pytest.raises(aes_boot.Refused, match="drive A: alone"):
        call(aes_boot.RWABS, 0, 0, 0x8000, 1, 0, aes_boot.DRIVE_A + 1)
    buffer, record = 0x8000, st_build.RESERVED_SECTORS - 1       # the boot sector and the first of the FAT: neither empty
    assert call(aes_boot.RWABS, 0, buffer >> 16, buffer & 0xffff, 2, record, aes_boot.DRIVE_A) == 0
    at = record * st_build.SECTOR_BYTES
    assert all(any(floppy.disk[at + sector * st_build.SECTOR_BYTES:][:st_build.SECTOR_BYTES]) for sector in range(2))
    assert memory[buffer:buffer + 2 * st_build.SECTOR_BYTES] == floppy.disk[at:at + 2 * st_build.SECTOR_BYTES]


@every_boot
def test_the_hardware_the_boot_touches_is_the_hardware_declared(label):
    """Every I/O read was served by a declaration — the palette's sixteen words and the resolution byte, each as the
    capture read it — or by the kit's own model of the keyboard ACIA's status; every off-image store is a byte for
    the IKBD. (A read of anything else refuses the boot before it is kept.)"""
    boot = machine(label).boot
    declared = aes_boot.io_seed_of(pre_of(label))
    for at, width, value in boot.io_reads:
        assert value == int.from_bytes(bytes(declared[at + offset] for offset in range(width)), "big")
    palette = {preinit_snapshot.SHIFTER_PALETTE + index * WORD_BYTES for index in range(addrs.SHIFTER_PALETTE_ENTRIES)}
    assert {at for at, _width, _value in boot.io_reads} == palette | {preinit_snapshot.SHIFTER_RESOLUTION}
    assert {at for at, _value in boot.hardware_reads} == {addrs.IKBD_ACIA_STATUS}
    assert {(at, width) for at, width, _value in boot.hardware_writes} == {(addrs.IKBD_ACIA_DATA, 1)}
    assert len(boot.hardware_reads) == len(boot.hardware_writes)


@every_boot
def test_the_palette_the_boot_read_is_the_palette_the_vdi_realized(label):
    """`vq_color` over every pen stores what the shifter answered, per mille, in the VDI's own table — and the booted
    machine's table is the post-boot snapshot's: the palette the capture carried out of Hatari is the one Hatari's
    own boot read. (A boot answered another palette realizes another table: the declaration is not decoration.)"""
    booted = machine(label)
    at, size = vdi.LINEA_REQ_COL, vdi.VDI_REQ_COL_WORDS * WORD_BYTES
    assert any(booted.ram[at:at + size]) and booted.ram[at:at + size] == bytes(BASE_IMAGE[at:at + size])


def test_the_resolution_byte_s_other_bits_decide_nothing():
    """The capture reads the resolution register with its unused bits as Hatari's debugger shows them; the boot
    masks them off — a machine whose register reads them clear boots to the same machine."""
    plain = pre()
    at = preinit_snapshot.SHIFTER_RESOLUTION - preinit_snapshot.IO_AT
    io = bytearray(plain.io)
    io[at] &= RESOLUTION_MODE
    assert io[at] != plain.io[at], "the capture's register reads no unused bit set: this test would hold nothing"
    cleared = aes_boot.desk_machine(plain._replace(io=bytes(io)))
    assert cleared.ram == machine("the desk alone").ram and cleared.registers == machine("the desk alone").registers


@every_boot
def test_the_ledger_of_a_boot_is_whole_and_inside_the_machine(label):
    boot = machine(label).boot
    assert not boot.writes_truncated
    ends = 0
    for start, length in boot.stored:
        assert ends <= start and length > 0 and start + length <= RAM_BYTES
        ends = start + length
    unchanged = bytearray(pre_of(label).ram)
    for start, length in boot.stored:
        unchanged[start:start + length] = boot.ram[start:start + length]
    assert bytes(unchanged) == boot.ram, "the boot changed a byte its ledger does not name"


# ---- NO MACHINE DEPENDS ON A BYTE THE CAPTURE DOES NOT REPRODUCE ------------------------------------------------------------
NOISE_SEED = 0x7051


def noisy(plain):
    """`plain` with every masked byte replaced by noise that differs from it."""
    generator, ram = random.Random(NOISE_SEED), bytearray(plain.ram)
    for at, size, _why in preinit_snapshot.MASK:
        for offset in range(at, at + size):
            ram[offset] ^= generator.randrange(1, 256)
    return plain._replace(ram=bytes(ram))


BOOTED_FROM = {"the desk alone": aes_boot.desk_machine,
               "two quiet accessories": lambda machine: aes_boot.accessory_machine(machine=machine),
               "the first finds the second, writes to it and waits six ways":
                   lambda machine: aes_boot.accessory_machine(first=BUSY, machine=machine)}


@pytest.mark.parametrize("label", BOOTED_FROM)
def test_no_booted_machine_depends_on_a_byte_the_capture_does_not_reproduce(label):
    """Booted from a pre-init machine whose every masked byte — every clock, every dead frame — is NOISE, the ROM
    takes the same instructions to the same registers and leaves the same machine, outside the mask. And INSIDE it,
    each byte is the noise carried through untouched or the very byte the plain boot wrote there: the boot reads
    none of them."""
    capture = pre_of(label)
    noise = noisy(capture)
    plain, perturbed = machine(label), BOOTED_FROM[label](noise)
    assert perturbed.registers == plain.registers
    assert (perturbed.boot.instructions, perturbed.boot.cycles) == (plain.boot.instructions, plain.boot.cycles)
    assert preinit_snapshot.masked(perturbed.ram) == preinit_snapshot.masked(plain.ram)
    stored = {at for start, length in plain.boot.stored for at in range(start, start + length)}
    for at, size, _why in preinit_snapshot.MASK:
        for offset in range(at, at + size):
            carried = perturbed.ram[offset] == noise.ram[offset] and plain.ram[offset] == capture.ram[offset]
            assert carried or (offset in stored and perturbed.ram[offset] == plain.ram[offset])


@every_boot
def test_no_time_passes_in_a_boot(label):
    """No clock interrupt is delivered, and the boot stores to no clock: every one is the pre-init machine's."""
    booted = machine(label)
    for at, size in ((addrs.SYSVAR_HZ_200, LONG_BYTES), (addrs.SYSVAR_VBCLOCK, LONG_BYTES), (addrs.SYSVAR_FRCLOCK, LONG_BYTES),
                     (addrs.SYSVAR_TIMER_C_DIVIDER, WORD_BYTES)):
        assert booted.ram[at:at + size] == pre_of(label).ram[at:at + size]


# ---- THE POST-BOOT SNAPSHOT: UNTOUCHED, AND THE DESK'S MACHINE'S OWN FAMILY -----------------------------------------------------
def test_the_snapshot_machine_is_untouched_by_the_pre_init_machine_and_its_boots():
    """The file every other test stands on is the file `harness` loaded, a differential still starts from it after
    every machine of this module was derived, and nothing here is in the tree key of anyone's derivation: the
    pre-init machines' names are outside every keyed pattern (a capture moves no kept answer) and neither is the
    snapshot's file."""
    on_disk = boot_snapshot.snapshot_path().read_bytes()
    before = hashlib.sha256(on_disk).digest()
    for label in BOOTS:
        machine(label)
    assert bytes(BASE_IMAGE[:RAM_BYTES]) == on_disk == bytes(make_image()[:RAM_BYTES])
    assert hashlib.sha256(boot_snapshot.snapshot_path().read_bytes()).digest() == before
    for made in (preinit_snapshot.preinit_path(), preinit_snapshot.accessory_path()):
        assert made != boot_snapshot.snapshot_path() and made.parent == boot_snapshot.snapshot_path().parent
        relative = str(made.relative_to(derived.RECREATE))
        assert not any(fnmatch.fnmatch(relative, pattern) for pattern in derived.PROJECT_INPUTS)
        assert made not in derived.input_files()


def test_a_boot_is_kept_by_the_pre_init_machine_s_content():
    """`booted` is a kept derivation whose key reads the pre-init machine BY VALUE: one changed byte of its RAM, one
    register, one palette byte or another disk is another question."""
    plain, disk = pre(), aes_boot.blank_disk()

    def key(machine=plain, disk=disk):
        return derived.key_of(aes_boot.booted.derive, (machine, disk), {})

    moved = bytearray(plain.ram)
    moved[addrs.SYSVAR_HZ_200 + 3] ^= 1
    others = (key(machine=plain._replace(ram=bytes(moved))),
              key(machine=plain._replace(registers={**plain.registers, "d1": plain.registers["d1"] ^ 1})),
              key(machine=plain._replace(io=bytes([plain.io[0] ^ 1]) + plain.io[1:])),
              key(disk=aes_boot.accessory_disk_of(QUIET, QUIET)))
    assert key() == key() and len({key(), *others}) == 1 + len(others)


AUTO_RUNNER_ABANDONS_ITS_STACK = 0xfc0d42          # the BIOS's AUTO runner, no program found: `lea $755a,sp`
LEA_ABSOLUTE_LONG_SP = 0x4ff9


def abandoned_stack(capture):
    """THE AUTO RUNNER'S STACK, `(lo, hi)`, off a pre-init machine's own pointers — and that it is DEAD there.

    The AES's parent process is the BIOS's AUTO runner, whose stack is the top of its own basepage: the command
    tail's 128 bytes. It ran `\\AUTO`'s search on it in supervisor mode, interrupts open, and then ABANDONED it — the
    one instruction that loads SP with the BIOS's own stack, which is the ISP the capture stopped with. Nothing
    points into it any more: neither stack pointer, nor the frame GEMDOS saved for either process. What an interrupt
    pushed below the runner's SP while it ran is still there, and which interrupt — if any — is each boot's phase."""
    ram, registers = capture.ram, capture.registers
    basepage = case.long_in(ram, registers["usp"] + LONG_BYTES)
    runner = case.long_in(ram, basepage + addrs.BASEPAGE_PARENT)
    lo, hi = runner + addrs.BASEPAGE_COMMAND_TAIL, runner + aes_boot.BASEPAGE_BYTES
    opcode, reloaded = struct.unpack_from(">HI", BASE_IMAGE, AUTO_RUNNER_ABANDONS_ITS_STACK)
    assert opcode == LEA_ABSOLUTE_LONG_SP and reloaded == registers["isp"]
    saved = [case.long_in(ram, process + addrs.BASEPAGE_SAVED_FRAME) for process in (basepage, runner)]
    assert not any(lo <= pointer < hi for pointer in (registers["usp"], registers["isp"], *saved))
    return lo, hi


@every_capture
def test_the_auto_runner_s_abandoned_stack_is_the_mask_s_last_region(capture):
    """The span the family test leaves out IS a region of the pre-init mask — so the noise test above proves it dead
    the way it proves every clock dead: a boot from a machine with NOISE all over that stack takes the same
    instructions to the same machine. Above it lies the environment the runner made, which is live."""
    lo, hi = abandoned_stack(CAPTURES[capture]())
    assert (lo, hi - lo) in [(at, size) for at, size, _why in preinit_snapshot.MASK]
    assert CAPTURES[capture]().ram[hi:hi + len(b"PATH=")] == b"PATH="


def family_differences(booted_ram, snapshot_ram, capture):
    """Where a desk machine and the snapshot differ in what THE FAMILY holds byte for byte: the exception vectors,
    and the TPA below the AES's first stack but for the Line-F handler's mask word and the AUTO runner's abandoned
    stack (`abandoned_stack`: dead on both shores, each with its own boot's interrupts). `(address, length)` runs."""
    ours, theirs = bytearray(booted_ram), bytearray(snapshot_ram)
    bottom, screen = case.long_in(ours, addrs.SYSVAR_MEMBOT), case.long_in(ours, addrs.SYSVAR_V_BAS_AD)
    first_stack = capture.registers["usp"] - TOP_OF_TPA_STACK_BYTES
    left_out = [(lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW] + [abandoned_stack(capture)]
    assert bottom < first_stack < screen and all(bottom <= lo < hi <= first_stack for lo, hi in left_out)
    for lo, hi in left_out:
        ours[lo:hi] = theirs[lo:hi] = bytes(hi - lo)
    held = [(0, VECTOR_TABLE_BYTES), (bottom, first_stack)]
    return [(lo + at, size) for lo, hi in held
            for at, size in boot_snapshot.differing_fields(bytes(ours[lo:hi]), bytes(theirs[lo:hi]))]


def saved_contexts(booted):
    """Each static process's UDA state block: the registers and both stack pointers it was parked with."""
    return [booted.ram[process.uda:process.uda + aes.UDA_STATE_BYTES] for process in booted.static_processes()]


def test_the_desk_s_machine_is_the_snapshot_s_own_boot_met_at_its_first_idle():
    """THE FAMILY. The ROM booted in the oracle from the pre-init machine, over the capture's blank disk, is the
    machine Hatari booted, met nine hundred vertical blanks earlier — held where no capture's phase reaches:
      * the exception vectors, every one;
      * THE TPA below the screen, byte for byte, but two spans derived from the machine: the Line-F handler's
        self-patched mask word, and the AUTO runner's ABANDONED STACK (`abandoned_stack`: 128 bytes no stack pointer
        or saved frame names, in which each boot keeps the frames of the interrupts that runner took — the two shores
        are two boots). Everything else there is held: the runner's and the AES's basepages, the environment, the
        Line-F handler's copy, everything the AES and the desktop Malloc'd and filled;
      * both processes as their PDs and their saved contexts say them (the UDA's state block: every register, both
        stack pointers), each waiting on as many EVBs; the not-ready list; the free EVBs, as many;
      * the screen (`test_the_desk_s_screen_is_the_snapshot_s`).
    WHAT IS NOT HELD, because a capture's phase or the time between the two decides it (measured over three fresh
    captures of each: 56 to 62 bytes outside `boot_snapshot.MASK`): the clocks and GEMDOS's time of day; `colorptr`,
    still pending here (no vertical blank has loaded the palette the AES asked for); the floppy's vertical-blank
    state; the AES's tick-driven words; `savptr`'s last frame; the frames interrupts left on the stacks, dead and
    in the holes of live ones."""
    booted, snapshot = machine("the desk alone"), aes_boot.Machine(snapshot_as_a_boot())
    assert booted.long(addrs.SYSVAR_MEMBOT) == snapshot.long(addrs.SYSVAR_MEMBOT)
    differing = family_differences(booted.ram, snapshot.ram, pre())
    assert not differing, f"the desk's machine and the snapshot differ at {[(hex(at), size) for at, size in differing]}"
    for process, snapshot_s in zip(booted.static_processes(), snapshot.static_processes()):
        assert process._replace(events=()) == snapshot_s._replace(events=())
        assert len(process.events) == len(snapshot_s.events)
    assert saved_contexts(booted) == saved_contexts(snapshot)
    assert [process.pd for process in booted.waiting()] == [process.pd for process in snapshot.waiting()]
    assert len(booted.free_events()) == len(snapshot.free_events())


def test_the_family_still_sees_a_byte_beside_the_span_it_leaves_out():
    """THE EXCLUSION IS EXACTLY THE DEAD STACK: one byte flipped just under it (the runner's basepage: the last byte
    of GEMDOS's saved frame pointer), just over it (the environment's first byte), in the AES's own basepage, or in
    a vector, is a difference the family names at that address — and one flipped INSIDE the span is none. And the
    desk's parked stack pointer one frame off is another saved context than the snapshot's."""
    booted, snapshot = machine("the desk alone").ram, bytes(BASE_IMAGE[:RAM_BYTES])
    lo, hi = abandoned_stack(pre())
    aes_basepage = case.long_in(pre().ram, pre().registers["usp"] + LONG_BYTES)
    assert not family_differences(booted, snapshot, pre())
    for at in (lo - 1, hi, aes_basepage + addrs.BASEPAGE_TBASE, addrs.VECTOR_HBL):
        flipped = bytearray(booted)
        flipped[at] ^= 0x24
        assert family_differences(bytes(flipped), snapshot, pre()) == [(at, 1)]
    for at in (lo, (lo + hi) // 2, hi - 1):
        flipped = bytearray(booted)
        flipped[at] ^= 0x24
        assert not family_differences(bytes(flipped), snapshot, pre())
    desk = machine("the desk alone")
    parked = bytearray(booted)
    parked[desk.static_processes()[DESK_PID].uda + aes.UDA_SUPER_SP + LONG_BYTES - 1] ^= 2      # a LIVE frame's pointer
    moved = aes_boot.Machine(desk.boot._replace(ram=bytes(parked)))
    assert saved_contexts(moved) != saved_contexts(aes_boot.Machine(snapshot_as_a_boot())) == saved_contexts(desk)


VECTOR_TABLE_BYTES = 0x400              # the 68000's 256 vectors
TOP_OF_TPA_STACK_BYTES = 0x100          # below the stack `Pexec` left the AES at the TPA's top: dead once gem_entry leaves it


def snapshot_as_a_boot():
    """The post-boot snapshot in a `Boot`'s clothes, for the readers a `Machine` has — its megabyte alone."""
    empty = {field: None for field in aes_boot.Boot._fields}
    return aes_boot.Boot(**{**empty, "ram": bytes(BASE_IMAGE[:RAM_BYTES]), "registers": {}})


@every_accessory_boot
def test_an_accessory_machine_is_the_desk_s_plus_its_accessories(label):
    """The same desk: the static processes' ids, UDAs and CDAs, the desk's and the screen manager's waits, the
    screen, and every AES list head but the ones the accessories are on."""
    booted, desk = machine(label), machine("the desk alone")
    for index in (DESK_PID, SCREEN_MANAGER_PID):
        with_accessories, alone = booted.static_processes()[index], desk.static_processes()[index]
        assert with_accessories._replace(events=()) == alone._replace(events=())
        assert len(with_accessories.events) == len(alone.events)
    assert booted.registers == desk.registers


# ---- A ROW OVER THE ACCESSORY MACHINE: THE WORKED EXAMPLE ---------------------------------------------------------------------
@pytest.mark.parametrize("name", aes_boot.ACCESSORY_NAMES)
def test_fpdnm_finds_each_accessory_by_name_on_both_shores(name):
    """HOW A LATER WAVE RUNS A ROW OVER THIS MACHINE: its megabyte is the case's pokes (`Machine.pokes`), the lever
    of a leaf laid over it, the case's own staging over that — and the differential is the one every battery runs.
    Here the verified fpdnm, by name: the first accessory is found in the static table, the SECOND only by the walk
    of `$c6b2[]` (the accessory arm, which no machine before this one reached) — our C and the ROM agree on both."""
    booted = machine("two quiet accessories")
    staged = case.merge_pokes(aes.leaf_machine(booted.pokes), pp.name_pokes(name.encode()))
    result = pp.run(pp.FPDNM, (pp.NAME_AT, DESK_PID), staged)
    assert result.long_answer() == booted.named(name).pd
