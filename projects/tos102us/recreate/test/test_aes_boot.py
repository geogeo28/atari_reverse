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
from collections import namedtuple
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
import aes_event
import aes_gemctrl
import aes_pdpipe as pp
import aes_switch
import case
import fs_pexec
import isr
import routines
import transcription
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


# ---- THE TAKEOVER: A MACHINE WHOSE SCREEN MANAGER IS OURS (band 5 wave 2) -----------------------------------------------------
# EVERY MACHINE ANY BATTERY BOOTS — this one's (BOOTS) and the screen manager's handlers' (`aes_gemctrl.MACHINES`), by
# the modes of its two accessories (None: the desk alone) — on BOTH blobs. Nothing below names a PD, a stack address
# or an instruction count: a process is found BY ITS NAME, a span through the machine's own pointers, the stop by
# what the machine holds there.
EVERY_MACHINE = {"the desk alone": None, "two quiet accessories": (QUIET, QUIET),
                 "the first finds the second, writes to it and waits six ways": (BUSY, QUIET),
                 "both wait six ways": (MULTI, MULTI), "the first writes to the desk": (WRITE, QUIET),
                 **aes_gemctrl.ACCESSORY_MODES}
every_machine = pytest.mark.parametrize("label", EVERY_MACHINE)
every_blob = pytest.mark.parametrize("blob", isr.BLOBS)
A_DESK, WITH_ACCESSORIES, WITH_WINDOWS = "the desk alone", "two quiet accessories", aes_gemctrl.TWO_WINDOWS
THREE_MACHINES = pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES, WITH_WINDOWS))
ENTRY = aes_boot.ROM_ENTRY


def capture_and_disk(label):
    """The pre-init machine and the disk the machine `label` boots from."""
    modes = EVERY_MACHINE[label]
    if modes is None:
        return aes_boot.preinit(), aes_boot.blank_disk()
    return aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(*modes)


@functools.cache
def booted_as(label, blob=None):
    """The machine `label`, its screen manager the ROM's (`blob` None) or that blob's (a name of `isr.BLOBS`)."""
    ours = {} if blob is None else {"ours": aes_boot.ours_of(isr.blob_named(blob))}
    return aes_boot.Machine(aes_boot.booted(*capture_and_disk(label), **ours))


@functools.cache
def at_the_rom_s_ctlmgr(label):
    """The ROM's own boot of `label` STOPPED AT ITS ctlmgr's FIRST INSTRUCTION: one instruction — switchto's `rte` —
    past the takeover's stop."""
    return aes_boot.booted(*capture_and_disk(label), until=ENTRY)


def test_every_machine_a_battery_boots_is_taken_over():
    """The list above IS the batteries': this file's BOOTS, machine for machine, and every machine of the screen
    manager's handlers' battery."""
    assert set(EVERY_MACHINE) == set(BOOTS) | set(aes_gemctrl.MACHINES)
    for label in BOOTS:
        assert booted_as(label).ram == machine(label).ram and booted_as(label).registers == machine(label).registers
    for key in aes_gemctrl.MACHINES:
        assert booted_as(key).ram == aes_gemctrl.machine(key).ram


# ---- the blob, read by symbol ----
@every_blob
def test_the_entry_is_found_by_symbol_in_the_blob_s_elf(blob):
    """`ours_of` reads the blob's ELF: the entry, the dispatcher's poll and its idle, the two handlers' cores — each
    where `nm` places the symbol, inside the blob; and the blob's bytes are the file's."""
    built = isr.blob_named(blob)
    ours = aes_boot.ours_of(built)
    placed = {symbol.name: symbol for symbol in transcription.symbol_table(built.elf)}
    assert ours.entry == placed[aes_event.SCREEN_MANAGER_ENTRY_SYMBOL].start == built.entry(aes_boot.ENTRY_SYMBOL)
    assert ours.poll == built.entry(aes_boot.OUR_POLL) and ours.idle[0] == built.entry(aes_boot.OUR_IDLE) < ours.idle[1]
    assert ours.base == built.base and ours.image == built.bin.read_bytes() and ours.end >= ours.base + len(ours.image)
    assert all(ours.base <= at < ours.base + len(ours.image) and not at % WORD_BYTES for at in (ours.entry, ours.poll))
    assert dict(ours.handlers) == {getattr(addrs, name): built.entry(routines.core_symbol(name))
                                   for name in aes_boot.HANDLER_NAMES}


@pytest.mark.parametrize("symbol, said", [(aes_boot.ENTRY_SYMBOL, "has no entry `aes_rom_ctlmgr`: nothing of this build can be entered"),
                                          (aes_boot.OUR_IDLE, "has no entry `aes_idle`: its dispatcher has no idle to end a boot in"),
                                          (aes_boot.OUR_POLL, "has no entry `aes_chkkbd`")])
def test_a_blob_without_the_entry_or_a_dispatcher_s_idle_is_refused_by_name(symbol, said):
    """THE ENTRY IS FOUND BY SYMBOL OR NOT AT ALL: a blob whose ELF does not place `aes_rom_ctlmgr` (a build before
    ctlmgr was ported) is refused before any boot — and so is one whose dispatcher has no idle or no poll: the stop
    that ends a boot in OUR dispatcher would not exist."""
    built = isr.blob()
    without = tuple(each for each in transcription.symbol_table(built.elf) if each.name != symbol)
    reading = aes_boot._ours_at.__wrapped__
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(transcription, "symbol_table", lambda _elf: without)
        with pytest.raises(aes_boot.Refused, match=said):
            reading(str(built.elf), built.base, built.end, bytes(built.blob))
    assert reading(str(built.elf), built.base, built.end, bytes(built.blob)) == aes_boot.ours_of(built)


# ---- the stop ----
@every_machine
def test_the_registry_s_two_slots_are_where_the_machine_keeps_the_screen_manager_s_entry(label):
    """THE REGISTRY ENTRY (`aes_event.SCREEN_MANAGER_ENTRY`), HELD TO THE MACHINE: where the ROM's own boot enters its
    ctlmgr, the process entered is SCRENMGR — the PD the registry's constants name — and the two longwords its own
    pointers lead to (`entry_slots`: p_ldaddr; the PC of psetup's frame, still under the popped stack) are the
    registry's two slots, each holding the address ictlmgr's two immediates carry."""
    stopped = at_the_rom_s_ctlmgr(label)
    entered = case.long_in(stopped.ram, aes.AES_RLR) & BUS
    registry = aes_event.SCREEN_MANAGER_ENTRY
    assert entered == aes.SCREEN_MANAGER_PD and aes_boot._name_of(stopped.ram, entered) == aes_boot.SCREEN_MANAGER_NAME
    slots = aes_boot.entry_slots(stopped.ram, entered)
    assert slots == registry.slots == aes_event.SCREEN_MANAGER_ENTRY_SLOTS
    assert [case.long_in(stopped.ram, slot) for slot in slots] == [ENTRY, ENTRY]
    assert registry.symbols == {ENTRY: aes_boot.ENTRY_SYMBOL} and registry.at_entry
    assert stopped.registers["pc"] == ENTRY and stopped.registers["isp"] == aes.AES_UDA1_STACK_TOP == slots[1] + LONG_BYTES


def test_the_registry_s_rom_address_is_ictlmgr_s_two_immediates():
    """ictlmgr hands pstart ONE routine twice, by value: the load address (`move.l #,d7`) and the code (`move.l
    #,-(sp)`) — the registry's key is read off both, and pstart is the call that follows."""
    for at, opcode in ((aes_event.ICTLMGR_LDADDR_AT, aes_event.MOVE_L_IMMEDIATE_TO_D7),
                       (aes_event.ICTLMGR_CODE_AT, aes_event.PUSH_L_IMMEDIATE)):
        assert struct.unpack_from(">HI", BASE_IMAGE, at) == (opcode, ENTRY)
    call = aes_event.ICTLMGR_CODE_AT + WORD_BYTES + LONG_BYTES
    assert aes.line_f_target(rom_word(call)) == addrs.AES_ROM_PSTART


@every_machine
@every_blob
def test_the_takeover_is_made_at_the_screen_manager_s_first_entry(label, blob):
    """WHERE: switchto's `rte`, about to pop the frame psetup pushed — the machine there IS the ROM's own boot one
    instruction before its ctlmgr (the megabyte's digest; the stack pointer six bytes lower), every register
    switchto loaded out of the never-saved UDA zero. WHAT: the process entered is SCRENMGR, its stack from the end
    of its UDA's state block to the frame's end; the registry's two slots mapped from the ROM's ctlmgr to the blob's
    entry; the blob laid THERE."""
    taken, ours = booted_as(label, blob).takeover, aes_boot.ours_of(isr.blob_named(blob))
    stopped, manager = at_the_rom_s_ctlmgr(label), booted_as(label, blob).screen_manager()
    digest, registers = taken.found
    assert taken.ours == ours and taken.laid == aes_boot.AT_THE_FIRST_ENTRY
    assert taken.process == manager.pd and manager.pid == SCREEN_MANAGER_PID
    assert digest == hashlib.sha256(stopped.ram).digest()
    assert registers["pc"] == addrs.AES_ROM_SWITCHTO_RTE and registers["isp"] == stopped.registers["isp"] - aes_boot.FRAME_BYTES
    assert not any(registers[name] for name in (*preinit_snapshot.DATA_REGISTERS, *preinit_snapshot.ADDRESS_REGISTERS))
    assert {name: registers[name] for name in registers if name not in ("pc", "isp", "sr")} == {
        name: stopped.registers[name] for name in registers if name not in ("pc", "isp", "sr")}
    assert taken.stack == (manager.uda + aes.UDA_STATE_BYTES, stopped.registers["isp"])
    assert not any(stopped.ram[taken.stack[0]:taken.stack[1] - aes_boot.FRAME_BYTES])
    assert taken.slots == {slot: (ENTRY, ours.entry) for slot in aes_event.SCREEN_MANAGER_ENTRY.slots}
    assert 0 < taken.instructions < booted_as(label, blob).boot.instructions


def stop_of(label):
    """The takeover's stop on the machine `label`, as `_vet_the_first_entry` is handed it: the megabyte (the ROM's
    boot one instruction on: the `rte` stores nothing), the process, its stack pointer, the registers switchto loaded."""
    stopped = at_the_rom_s_ctlmgr(label)
    registers = {name: 0 for name in (*preinit_snapshot.DATA_REGISTERS, *preinit_snapshot.ADDRESS_REGISTERS)}
    return bytearray(stopped.ram), case.long_in(stopped.ram, aes.AES_RLR) & BUS, stopped.registers["isp"] - aes_boot.FRAME_BYTES, registers


@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_stop_that_is_not_the_screen_manager_s_first_entry_is_refused_by_name(label):
    """THE VETS AT THE STOP, each RED on the machine of the stop itself with ONE thing wrong: another process's name;
    a stack pointer that is not the one its UDA names; one byte on its stack below the frame (its ctlmgr has run);
    a register switchto loaded that is not zero (a context was saved); a frame that would resume in user mode."""
    memory, pd, sp, registers = stop_of(label)
    uda = case.long_in(memory, pd + aes.PD_UDA) & BUS
    assert aes_boot._vet_the_first_entry(memory, pd, sp, registers) == (uda + aes.UDA_STATE_BYTES, sp + aes_boot.FRAME_BYTES)

    def wrong(at, data, said, sp=sp, registers=registers):
        doctored = bytearray(memory)
        doctored[at:at + len(data)] = data
        with pytest.raises(aes_boot.Refused, match=said):
            aes_boot._vet_the_first_entry(doctored, pd, sp, registers)

    wrong(pd + aes.PD_NAME, b"DESKTOP ", "not SCRENMGR")
    wrong(0, b"", "not on the stack its UDA names", sp=sp - WORD_BYTES)
    for at in (uda + aes.UDA_STATE_BYTES, sp - 1):
        wrong(at, b"\x01", "NOT THE SCREEN MANAGER'S FIRST ENTRY: its stack holds something")
    wrong(0, b"", "NOT THE SCREEN MANAGER'S FIRST ENTRY: switchto loaded {'a6': 4}", registers={**registers, "a6": 4})
    wrong(sp, struct.pack(">H", case.word_in(memory, sp) & ~preinit_snapshot.SR_SUPERVISOR), "holds the status word")


@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_mapping_that_is_not_the_registry_s_is_refused_by_name(label):
    """`_vetted_slots`: the slots of the process entered are the registry's two and each holds the ROM's ctlmgr — or
    the mapping is refused: ANOTHER PROCESS's slots (the desk's, by its own pointers), and the right slots holding
    something else (a build's ictlmgr that stored another routine)."""
    memory, pd, _sp, _registers = stop_of(label)
    assert aes_boot._vetted_slots(memory, pd) == aes_event.SCREEN_MANAGER_ENTRY.slots
    desk = aes_boot.Machine(at_the_rom_s_ctlmgr(label)).static_processes()[DESK_PID].pd
    with pytest.raises(aes_boot.Refused, match="the mapping would be applied to ANOTHER PROCESS"):
        aes_boot._vetted_slots(memory, desk)
    for slot in aes_event.SCREEN_MANAGER_ENTRY.slots:
        doctored = bytearray(memory)
        doctored[slot:slot + LONG_BYTES] = struct.pack(">I", addrs.AES_ROM_HCTL_BUTTON)
        with pytest.raises(aes_boot.Refused, match=f"the slot at {slot:#x} .* holds {addrs.AES_ROM_HCTL_BUTTON:#x}, not the ROM's ctlmgr"):
            aes_boot._vetted_slots(doctored, pd)


MAPPED = aes_boot._mapped              # the mapping as the takeover applies it, for a RED that applies part of it


def taken_over_with(label, blob, patch, **patched):
    """The takeover boot of `label` on `blob` MADE (never served), `aes_boot`'s `patched` attributes in force."""
    for name, value in patched.items():
        patch.setattr(aes_boot, name, value)
    return aes_boot.booted.derive(*capture_and_disk(label), ours=aes_boot.ours_of(isr.blob_named(blob)))


@every_blob
@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_takeover_whose_p_ldaddr_is_left_unmapped_is_refused(label, blob, monkeypatch):
    """RED: the frame's PC mapped and the PD's p_ldaddr left — the `rte` enters our ctlmgr and the boot runs to its
    idle, the machine a build's whose ictlmgr stored the ROM's address in the PD. Refused by name where it ends."""
    def the_frame_s_alone(memory, slots, mapping):
        return MAPPED(memory, [slot for slot in slots if slot != aes.SCREEN_MANAGER_PD + aes.PD_LDADDR], mapping)
    with pytest.raises(aes_boot.Refused, match="p_ldaddr holds 0xfe49d2 — the ROM's ctlmgr: LEFT UNMAPPED"):
        taken_over_with(label, blob, monkeypatch, _mapped=the_frame_s_alone)


@every_blob
@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_takeover_that_maps_nothing_or_the_pd_alone_never_enters_our_entry_and_is_refused(label, blob, monkeypatch):
    """RED, the mapping SKIPPED and the mapping of p_ldaddr ALONE: the `rte` pops the ROM's ctlmgr, the ROM's screen
    manager runs under a blob nobody entered — refused by name."""
    def the_pd_s_alone(memory, slots, mapping):
        return MAPPED(memory, [aes.SCREEN_MANAGER_PD + aes.PD_LDADDR], mapping)
    for skipped in (lambda memory, slots, mapping: {}, the_pd_s_alone):
        with pytest.raises(aes_boot.Refused, match="did not enter `aes_rom_ctlmgr`"):
            taken_over_with(label, blob, monkeypatch, _mapped=skipped)


@every_blob
@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_mapping_applied_to_the_wrong_pd_is_refused(label, blob, monkeypatch):
    """RED, by a real boot: the slots read off ANOTHER process of the AES's own table — the first that is not SCRENMGR
    by name — are not the registry's, and the takeover is refused there, before a byte is laid."""
    read = aes_boot.entry_slots

    def of_another_process(memory, _pd):
        table = [aes.AES_PD_TABLE + index * aes.PD_BYTES for index in range(aes.AES_PD_COUNT)]
        return read(memory, next(pd for pd in table if aes_boot._name_of(memory, pd) != aes_boot.SCREEN_MANAGER_NAME))
    with pytest.raises(aes_boot.Refused, match="the mapping would be applied to ANOTHER PROCESS"):
        taken_over_with(label, blob, monkeypatch, entry_slots=of_another_process)


@every_blob
def test_a_blob_laid_before_the_stop_is_stored_over_by_the_accessory_boot_and_refused(blob):
    """WHY THE BLOB IS LAID AT THE STOP — RED, a real boot: laid before the boot's first instruction, the blob is
    CLEARED by the accessory loader's Pexec (the largest free block is the harness's free window) before the screen
    manager first runs. Refused by name at the stop, the bytes counted off the run's own ledger."""
    ours = aes_boot.ours_of(isr.blob_named(blob))
    with pytest.raises(aes_boot.Refused, match=f"THE BOOT STORED OVER THE BLOB, laid before the boot's first instruction: "
                                               f"{ours.end - ours.base} byte"):
        aes_boot.booted.derive(*capture_and_disk(WITH_ACCESSORIES), ours=ours, laid=aes_boot.FROM_THE_START)


@every_blob
def test_on_the_desk_s_boot_nothing_stores_there_and_a_blob_laid_from_the_start_makes_the_same_machine(blob):
    """...and the desk's boot, which loads no program, never touches the window: laid from the start or at the stop,
    the same megabyte and the same registers — the stop is the place because of Pexec, not of anything the takeover
    needs of it."""
    ours = aes_boot.ours_of(isr.blob_named(blob))
    early = aes_boot.booted.derive(*capture_and_disk(A_DESK), ours=ours, laid=aes_boot.FROM_THE_START)
    plain = booted_as(A_DESK, blob).boot
    assert (early.ram, early.registers, early.idle) == (plain.ram, plain.registers, plain.idle)
    assert early.takeover.laid == aes_boot.FROM_THE_START and early.takeover.slots == plain.takeover.slots


@every_blob
def test_a_window_that_is_not_free_where_the_blob_goes_is_refused(blob):
    """RED, a real boot: one byte of the pre-init machine set inside the blob's span — on the desk's boot, where
    nothing clears the window — and the takeover is refused at the stop: it lays the blob over nothing."""
    ours, (capture, disk) = aes_boot.ours_of(isr.blob_named(blob)), capture_and_disk(A_DESK)
    for at in (ours.base, ours.end - 1):
        ram = bytearray(capture.ram)
        assert not ram[at]
        ram[at] = 0x4e
        with pytest.raises(aes_boot.Refused, match=f"holds something where the blob goes, from {at:#x}"):
            aes_boot.booted.derive(capture._replace(ram=bytes(ram)), disk, ours=ours)


@every_machine
@every_blob
def test_the_rest_of_the_boot_stores_nothing_into_the_blob(label, blob):
    """ZERO STORES AFTER THE LAY, on every machine (the run's write ledger from the lay on, and every sector the
    harness laid): the blob in the booted machine is the blob's bytes. And BEFORE it the window was the loader's to
    clear: the accessory boots stored the WHOLE span (Pexec's clear), the desk's not one byte."""
    booted, ours = booted_as(label, blob), aes_boot.ours_of(isr.blob_named(blob))
    taken = booted.takeover
    assert taken.stored_after == () and not booted.boot.writes_truncated
    assert booted.ram[ours.base:ours.base + len(ours.image)] == ours.image and not any(booted.ram[ours.base + len(ours.image):ours.end])
    assert taken.cleared == (0 if EVERY_MACHINE[label] is None else ours.end - ours.base)
    stored = {at for start, length in booted.boot.stored for at in range(max(start, ours.base), min(start + length, ours.end))}
    assert len(stored) == taken.cleared, "the boot's whole ledger names no byte of the span the clear did not"


def test_a_store_over_the_blob_after_the_lay_is_refused_whoever_made_it():
    """`_TakingOver._vet_not_stored_over`, on its own inputs: a sector the HARNESS laid into the span after the blob
    (the ledger names no harness store) and bytes that are no longer the blob's are each refused by name."""
    ours = aes_boot.ours_of(isr.blob())
    memory = bytearray(BASE_IMAGE)
    taking = aes_boot._TakingOver(memory, ours, aes_boot.FROM_THE_START)
    taking._stored_in_the_span = lambda since, until=None: []
    taking._vet_not_stored_over()
    taking.harness_laid(ours.base - st_build.SECTOR_BYTES + 1, st_build.SECTOR_BYTES)
    with pytest.raises(aes_boot.Refused, match="THE BOOT STORED OVER THE BLOB.*: 1 byte"):
        taking._vet_not_stored_over()
    taking._laid_by_the_harness.clear()
    memory[ours.base + 4] ^= 1
    with pytest.raises(aes_boot.Refused, match="is no longer the blob's bytes"):
        taking._vet_not_stored_over()


# ---- THE STRUCTURAL TEST: what a takeover machine differs from the ROM's in ----
@every_machine
@every_blob
def test_a_takeover_machine_differs_from_the_rom_s_in_the_four_classes_alone(label, blob):
    """THE HEART. Beside the machine the ROM booted from the same capture, a machine whose screen manager is ours
    differs — in the whole megabyte — ONLY in: the dispatcher's dead frames, the screen manager's saved context, the
    screen manager's stack, and its p_ldaddr, which is MAPPED and then equal; and in the blob's span. Each class
    lies where the machine's own pointers put it; THE CPU STANDS IN THE SAME REGISTERS at the same idle."""
    rom, ours = booted_as(label), booted_as(label, blob)
    result = aes_boot.compared(rom, ours)
    assert result.differing == [], f"{label} on {blob} differs outside the classes at {[(hex(at), size) for at, size in result.differing]}"
    assert rom.registers == ours.registers and rom.idle == ours.idle == aes_boot.THE_ROM_S
    assert set(result.within) == {aes_boot.DEAD_DISPATCHER_FRAMES, aes_boot.SAVED_CONTEXT, aes_boot.MANAGER_STACK, aes_boot.THE_BLOB}
    assert all(result.within.values()), "a class the two machines do not differ in"
    ldaddr = ours.screen_manager().pd + aes.PD_LDADDR
    assert ours.long(ldaddr) == ours.ours.entry and rom.long(ldaddr) == ENTRY
    assert case.long_in(aes_boot.mapped_back(ours), ldaddr) == ENTRY
    unmapped = aes_boot._differing_runs(rom.ram[ldaddr:ldaddr + LONG_BYTES], ours.ram[ldaddr:ldaddr + LONG_BYTES])
    assert unmapped, "the PD's p_ldaddr differs before the mapping: it is what the mapping is for"


@every_machine
@every_blob
def test_each_class_is_where_the_machine_s_own_pointers_put_it(label, blob):
    """The classes, read: the dispatcher's dead frames end at the stack pointer the idle stands at, inside the
    dispatcher's stack; the saved context is savestate's block of the screen manager's UDA; its stack runs from the
    state block's end to where the takeover's stop found psetup's frame end, and its parked stack pointer — on both
    shores — lies inside it; the blob's span is the blob's."""
    rom, ours = booted_as(label), booted_as(label, blob)
    classes, beside = aes_boot.by_nature(rom, ours)
    manager = ours.screen_manager()
    bottom, top = aes_event.DISPATCHER_STACK
    assert classes[aes_boot.DEAD_DISPATCHER_FRAMES] == (bottom, ours.registers["isp"]) and bottom < ours.registers["isp"] < top
    assert classes[aes_boot.SAVED_CONTEXT] == (manager.uda + aes.UDA_REGS, manager.uda + aes.UDA_TRAP_SSP)
    lo, hi = classes[aes_boot.MANAGER_STACK]
    assert (lo, hi) == (manager.uda + aes.UDA_STATE_BYTES, ours.takeover.stack[1])
    assert hi < manager.uda + ours.static_uda_bytes()[SCREEN_MANAGER_PID]
    for each in (rom, ours):
        assert lo < each.long(manager.uda + aes.UDA_SUPER_SP) & BUS < hi
    assert classes[aes_boot.THE_BLOB] == (ours.ours.base, ours.ours.end)
    assert set(beside) == {aes_boot.LINE_F_MASK, aes_boot.TRAP_SAVE_FRAME}
    assert beside[aes_boot.TRAP_SAVE_FRAME][1] == ours.long(addrs.SYSVAR_SAVPTR)


def flipped(booted, at):
    ram = bytearray(booted.ram)
    ram[at] ^= 0x24
    return aes_boot.Machine(booted.boot._replace(ram=bytes(ram)))


@THREE_MACHINES
@every_blob
def test_the_comparison_still_sees_a_byte_beside_every_class(label, blob):
    """NO CLASS IS A BYTE WIDER THAN ITS SPAN: one byte flipped just under and just over each class is a difference
    the comparison names at that address, one flipped at either end INSIDE is none — and a flipped byte of p_ldaddr
    is a difference too, in that longword and nowhere else (the mapping gives OUR ENTRY the ROM's name, and no other
    value: an address one bit off is left as it is, and differs)."""
    rom, ours = booted_as(label), booted_as(label, blob)
    classes, _beside = aes_boot.by_nature(rom, ours)
    for lo, hi in classes.values():
        for at in (lo - 1, hi):
            assert aes_boot.compared(rom, flipped(ours, at)).differing == [(at, 1)], f"unseen beside [{lo:#x}, {hi:#x})"
        for at in (lo, hi - 1):
            assert aes_boot.compared(rom, flipped(ours, at)).differing == []
    ldaddr = ours.screen_manager().pd + aes.PD_LDADDR
    for at in range(ldaddr, ldaddr + LONG_BYTES):
        seen = aes_boot.compared(rom, flipped(ours, at)).differing
        assert seen and all(ldaddr <= start and start + size <= ldaddr + LONG_BYTES for start, size in seen)


@every_machine
@every_blob
def test_the_screen_manager_alone_is_parked_in_our_text(label, blob):
    """WHOSE PROCESS IS WHOSE, read off each one's parked frame (`whose`): on a takeover machine the screen manager is
    resumed IN THE BLOB and every other process — the desk, each accessory — in the AES's ROM text; on the machine
    the ROM booted, every one in the ROM's."""
    rom, ours = booted_as(label), booted_as(label, blob)
    assert {process.name: rom.resumed_in(process) for process in rom.waiting()} == {
        process.name: aes_boot.THE_ROM_S for process in rom.waiting()}
    assert {process.name: ours.resumed_in(process) for process in ours.waiting()} == {
        process.name: aes_boot.OURS if process.name == aes_boot.SCREEN_MANAGER_NAME else aes_boot.THE_ROM_S
        for process in ours.waiting()}
    assert len(ours.waiting()) == len(rom.waiting()) > 1


@every_blob
def test_a_resumed_pc_is_ours_the_rom_s_or_refused(blob):
    """THE CLASSIFICATION, at its edges: the blob's first and last byte are OURS; the AES's ROM text from gem_entry to
    its Line-F table is THE ROM'S; and a PC anywhere else — the byte before and after the blob, the BIOS, the table
    itself, RAM — is refused by name. With no blob (the ROM's machine) a PC where a blob would lie is refused too."""
    ours = aes_boot.ours_of(isr.blob_named(blob))
    last = ours.base + len(ours.image) - 1
    lo, hi = aes.AES_TEXT
    assert [aes_boot.whose(pc, ours) for pc in (ours.base, ours.entry, last)] == [aes_boot.OURS] * 3
    assert [aes_boot.whose(pc, ours) for pc in (lo, addrs.AES_ROM_SWITCHTO_RTE, hi - 1, ENTRY)] == [aes_boot.THE_ROM_S] * 4
    assert aes_boot.whose(0xff000000 | ENTRY, ours) == aes_boot.THE_ROM_S, "a PC is a bus address: its top byte decides nothing"
    for elsewhere in (ours.base - 1, last + 1, lo - 1, hi, addrs.ISR_HBL, RAM_BYTES - WORD_BYTES):
        with pytest.raises(aes_boot.Refused, match=f"a process resumed at {elsewhere:#x}: neither in the blob"):
            aes_boot.whose(elsewhere, ours)
    with pytest.raises(aes_boot.Refused, match="neither in no blob"):
        aes_boot.whose(ours.entry)
    assert aes_boot.whose(ENTRY) == aes_boot.THE_ROM_S


# ---- WHERE A BOOT ENDS, AND A MACHINE CONTINUED ----
ONTO_THE_VIEW_TITLE = (aes_boot.mouse_to(*aes_event.THE_VIEW_TITLE_S_POINT),)
ONTO_ITS_PLAIN_ITEM = (aes_boot.mouse_to(*aes_event.VIEW_S_PLAIN_ITEM_S_POINT),)
A_CLICK = (aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.ikbd(aes_boot.NO_BUTTON, 0, 0), aes_boot.CLICK_TICKS)
THE_MENU_CHAIN = (ONTO_THE_VIEW_TITLE, ONTO_ITS_PLAIN_ITEM, A_CLICK)


def onto_the_top_window_s(gadget):
    """What moves the mouse onto that gadget of WITH_WINDOWS' top window (a point read off the machine)."""
    return (aes_boot.mouse_to(*aes_gemctrl.gadget(WITH_WINDOWS, gadget)),)


MENU, CLOSER = "the View menu dropped, its plain item chosen", "the top window's closer clicked"
# The chains a machine is continued by: the desk's menu worked and — where an accessory has a window — its top
# window's closer clicked. NAMES ONLY: what a chain receives is made where it is asked (`receptions_of`: a gadget's
# point is read off a booted machine, and nothing boots at this module's import).
CHAINS = [(A_DESK, MENU), (WITH_ACCESSORIES, MENU), (WITH_WINDOWS, MENU), (WITH_WINDOWS, CLOSER)]


def receptions_of(chain):
    """What the chain `chain` receives at each idle in turn."""
    return THE_MENU_CHAIN if chain == MENU else (onto_the_top_window_s("the closer"), A_CLICK)


@functools.cache
def continued_through(label, blob, chain):
    """The machine `label` (its screen manager `blob`'s, or the ROM's) at each idle of `chain`, the first its own."""
    machines = [booted_as(label, blob)]
    for received in receptions_of(chain):
        machines.append(machines[-1].continued(*received))
    return tuple(machines)


every_chain = pytest.mark.parametrize("label, chain", CHAINS)


@every_machine
@every_blob
def test_every_boot_ends_at_the_rom_s_idle_because_the_desk_parks_last(label, blob):
    """WHICH DISPATCHER'S IDLE ENDS A BOOT: a process parks through the dispatcher of the build it runs, so the last
    park decides — and in every boot here the last to park is THE DESK (the ROM's code): both machines stand at the
    ROM's idle poll, in the same registers, the screen manager of the takeover machine parked EARLIER, in our frames."""
    for booted in (booted_as(label), booted_as(label, blob)):
        assert booted.idle == aes_boot.THE_ROM_S and booted.registers["pc"] == addrs.AES_ROM_IDLE_LOOP
        assert not (booted.long(aes.AES_RLR) or booted.long(aes.AES_DRL) or booted.word(aes.AES_FORK_COUNT))
    assert booted_as(label, blob).boot.polls >= 1 and booted_as(label, blob).boot.blanks == booted_as(label).boot.blanks == 1


@THREE_MACHINES
@every_blob
def test_a_machine_whose_screen_manager_parks_last_idles_in_our_dispatcher(label, blob):
    """...AND THE STOP EXISTS ON BOTH: the mouse moved onto a menu title wakes the screen manager ALONE — it drops the
    menu and parks inside mn_do, the last to park. The ROM's machine idles in the ROM's dispatcher; the takeover
    machine IN OURS: at the blob's keyboard poll, called from the blob's idle, nothing ready, woken or queued."""
    ours = aes_boot.ours_of(isr.blob_named(blob))
    rom_s, taken = (continued_through(label, each, MENU)[1] for each in (None, blob))
    assert rom_s.idle == aes_boot.THE_ROM_S and rom_s.registers["pc"] == addrs.AES_ROM_IDLE_LOOP
    assert taken.idle == aes_boot.OURS and taken.registers["pc"] == ours.poll
    back = taken.long(taken.registers["isp"]) & BUS
    assert ours.idle[0] <= back < ours.idle[1], "the poll is the idle's own: its return address lies in the blob's idle"
    assert aes_switch.waits_for_an_interrupt(taken.ram) and aes_switch.waits_for_an_interrupt(rom_s.ram)
    assert taken.resumed_in(taken.screen_manager()) == aes_boot.OURS


@every_chain
@every_blob
def test_woken_the_two_screen_managers_do_the_same(label, chain, blob):
    """THE LIVE FRAMES AND THE SAVED CONTEXT, VETTED BY WHAT THE SCREEN MANAGER DOES WHEN WOKEN. From the first idle
    the two machines RECEIVE THE SAME — real IKBD bytes through the ROM's ACIA handler, the system timer's ticks
    through Timer C's — idle after idle; and at every idle: THE SAME HANDLER CALLS in the same order with the same
    point (the ROM's ctlmgr's and ours, each watched at its own handlers' entries), and THE SAME MACHINE — the whole
    megabyte but the classes: the menu drawn, the item chosen, the message in the desk's or the accessory's hands,
    every AES list. Where the two idle in two dispatchers the comparison NAMES the two words that then differ by
    nature (and is refused them where they do not)."""
    rom_s, taken = continued_through(label, None, chain), continued_through(label, blob, chain)
    for step, (rom, ours) in enumerate(zip(rom_s[1:], taken[1:])):
        assert rom.observed == ours.observed, f"idle {step}: the ROM's ctlmgr called {rom.observed}, ours {ours.observed}"
        two_dispatchers = rom.idle != ours.idle
        beside = (aes_boot.LINE_F_MASK, aes_boot.TRAP_SAVE_FRAME) if two_dispatchers else ()
        result = aes_boot.compared(rom, ours, beside)
        assert result.differing == [], f"idle {step} of {chain}: differs at {[(hex(at), size) for at, size in result.differing]}"
        assert two_dispatchers or rom.registers == ours.registers
        # WHO MAY INTERRUPT THE IDLE is the machine's, whichever build's dispatcher stands there: supervisor mode, the
        # mask the horizontal blank left. The condition codes are by nature — those of the last test each build's
        # idle made before its poll (the ROM's `tst`, our compiler's own).
        for each in (rom, ours):
            assert each.registers["sr"] & aes_boot.OPEN_TO_INTERRUPTS == preinit_snapshot.SR_SUPERVISOR | addrs.HBL_IPL_FLOOR
        assert not rom.boot.writes_truncated and not ours.boot.writes_truncated
    assert any(rom.observed for rom in rom_s[1:]), "the chain never reached a handler of the screen manager"
    assert rom_s[-1].idle == taken[-1].idle == aes_boot.THE_ROM_S, "the chain ends with the desk parked last, as a boot does"


def test_the_chains_reach_both_handlers_with_the_cursor_s_point():
    """What the watch saw, read: the menu chain's first reception arrives at hctl_rect with the title's point, the
    closer's click at hctl_button with the closer's — on the ROM's machine, whose call the other shore is held to."""
    title = continued_through(A_DESK, None, MENU)[1]
    assert title.observed == (("hctl_rect", aes_event.THE_VIEW_TITLE_S_POINT),)
    closed = continued_through(WITH_WINDOWS, None, CLOSER)
    assert closed[1].observed == () and closed[2].observed == (("hctl_button", aes_gemctrl.gadget(WITH_WINDOWS, "the closer")),)


@THREE_MACHINES
@every_blob
def test_two_words_differ_by_nature_only_where_the_idles_are_two_dispatchers(label, blob):
    """THE DROPS NAMED BESIDE ARE MINIMAL, AND REFUSED WHERE NOT NEEDED: at a boot's idle (one dispatcher) naming
    either is refused — the machines do not differ there; where the takeover machine idles in OUR dispatcher each of
    the two is needed (without it the comparison names its bytes), and a name that is no class is refused."""
    rom, ours = booted_as(label), booted_as(label, blob)
    for unneeded in (aes_boot.LINE_F_MASK, aes_boot.TRAP_SAVE_FRAME):
        with pytest.raises(aes_boot.Refused, match="a class named beside and not needed"):
            aes_boot.compared(rom, ours, (unneeded,))
    with pytest.raises(aes_boot.Refused, match="no class a comparison may name beside"):
        aes_boot.compared(rom, ours, ("the screen",))
    rom, ours = (continued_through(label, each, MENU)[1] for each in (None, blob))
    _classes, beside = aes_boot.by_nature(rom, ours)
    for needed, other in ((aes_boot.LINE_F_MASK, aes_boot.TRAP_SAVE_FRAME), (aes_boot.TRAP_SAVE_FRAME, aes_boot.LINE_F_MASK)):
        lo, hi = beside[needed]
        left = aes_boot.compared(rom, ours, (other,)).differing
        assert left and all(lo <= at and at + size <= hi for at, size in left)
    assert set(aes_boot.by_nature(rom, ours)[0]) >= {aes_boot.DISPATCHER_STACK}


# ---- THE DEAD SPANS ARE DEAD: noise ----
DEAD_NOISE_SEED = 0x7052


@every_chain
@pytest.mark.parametrize("blob", (None, *isr.BLOBS), ids=("the ROM's own", *isr.BLOBS))
def test_noise_in_the_dead_spans_changes_no_continuation(label, chain, blob):
    """THE DROPPED SPANS THAT ARE DEAD, PROVED DEAD: the dispatcher's stack below the idle's stack pointer, the screen
    manager's stack below its parked stack pointer, the BIOS's register-save frame under savptr — filled with NOISE
    on the booted machine (the ROM's, and each takeover's), the machine receives the same chain and takes THE SAME
    INSTRUCTIONS to the same registers and the same handler calls at every idle; outside the noise the megabyte is
    the plain machine's, and inside it each byte is the noise carried or the very byte the plain run stored there."""
    plain = continued_through(label, blob, chain)
    spans = aes_boot.dead_spans(plain[0])
    assert all(lo < hi for lo, hi in spans.values()) and set(spans) == {
        aes_boot.DEAD_DISPATCHER_FRAMES, aes_boot.MANAGER_STACK, aes_boot.TRAP_SAVE_FRAME}
    noisy = aes_boot.noised(plain[0], spans.values(), DEAD_NOISE_SEED)
    noise = {at: noisy.ram[at] for lo, hi in spans.values() for at in range(lo, hi)}
    assert all(noisy.ram[at] != plain[0].ram[at] for at in noise)
    stored = set()
    for step, received in enumerate(receptions_of(chain), start=1):
        noisy = noisy.continued(*received)
        stored |= {at for start, length in plain[step].boot.stored for at in range(start, start + length)}
        assert noisy.registers == plain[step].registers and noisy.observed == plain[step].observed
        assert (noisy.boot.instructions, noisy.boot.cycles, noisy.idle) == (
            plain[step].boot.instructions, plain[step].boot.cycles, plain[step].idle)
        for at, size in aes_boot._differing_runs(noisy.ram, plain[step].ram):
            for each in range(at, at + size):
                assert each in noise and each not in stored and noisy.ram[each] == noise[each], (
                    f"idle {step}: the noised machine differs at {each:#x}, where the noise was not carried untouched")


@every_blob
def test_noise_in_a_live_frame_is_refused_by_name(blob):
    """...and the proof has teeth: the same noise ONE FRAME HIGHER — over the frame the screen manager is parked on,
    the status word and the PC switchto pops — is no machine: woken, it is resumed at a wild PC and never idles
    again — refused BY NAME, on the ROM's machine and the takeover's. And at OUR idle, the noise over the longword at
    the dispatcher's stack pointer — the poll's return address into the blob's idle — is refused the same way."""
    for whose in (None, blob):
        stood = continued_through(A_DESK, whose, MENU)[0]
        manager = stood.screen_manager()
        parked = stood.long(manager.uda + aes.UDA_SUPER_SP) & BUS
        live = aes_boot.noised(stood, [(parked, parked + aes_boot.FRAME_BYTES)], DEAD_NOISE_SEED)
        with pytest.raises(aes_boot.Refused, match="the machine never waits for an interrupt"):
            live.continued(*ONTO_THE_VIEW_TITLE, budget=LIVE_NOISE_INSNS)
    at_ours = continued_through(A_DESK, blob, MENU)[1]
    sp = at_ours.registers["isp"]
    assert at_ours.idle == aes_boot.OURS
    with pytest.raises(aes_boot.Refused, match="the machine never waits for an interrupt"):
        aes_boot.noised(at_ours, [(sp, sp + LONG_BYTES)], DEAD_NOISE_SEED).continued(*ONTO_ITS_PLAIN_ITEM, budget=LIVE_NOISE_INSNS)


@pytest.mark.parametrize("label", (A_DESK, WITH_WINDOWS))
@every_blob
def test_noise_in_the_dead_spans_at_our_idle_changes_no_continuation(label, blob):
    """THE SAME PROOF WHERE THE MACHINE IDLES IN OUR DISPATCHER (the menu dropped, the screen manager parked last, in
    mn_do): the dead part of the dispatcher's stack — all of it below OUR idle's stack pointer, the part of the
    dropped whole stack that is not the two idles' live frames — the screen manager's stack below its parked stack
    pointer (deeper here: it sleeps inside the menu's own wait) and the BIOS's register-save frame, in which OUR
    idle's poll last saved. Noised, the machine takes the rest of the chain exactly as the plain one does."""
    plain = continued_through(label, blob, MENU)
    assert plain[1].idle == aes_boot.OURS
    spans = aes_boot.dead_spans(plain[1])
    bottom, top = DISPATCHER_STACK_PINNED
    assert spans[aes_boot.DEAD_DISPATCHER_FRAMES] == (bottom, plain[1].registers["isp"]) and bottom < plain[1].registers["isp"] < top
    assert spans[aes_boot.MANAGER_STACK][1] < aes_boot.dead_spans(plain[0])[aes_boot.MANAGER_STACK][1], "parked deeper than at the boot"
    noisy = aes_boot.noised(plain[1], spans.values(), DEAD_NOISE_SEED)
    noise = {at: noisy.ram[at] for lo, hi in spans.values() for at in range(lo, hi)}
    stored = set()
    for step, received in enumerate(receptions_of(MENU)[1:], start=2):
        noisy = noisy.continued(*received)
        stored |= {at for start, length in plain[step].boot.stored for at in range(start, start + length)}
        assert (noisy.registers, noisy.observed, noisy.boot.instructions, noisy.boot.cycles, noisy.idle) == (
            plain[step].registers, plain[step].observed, plain[step].boot.instructions, plain[step].boot.cycles, plain[step].idle)
        for at, size in aes_boot._differing_runs(noisy.ram, plain[step].ram):
            for each in range(at, at + size):
                assert each in noise and each not in stored and noisy.ram[each] == noise[each], f"idle {step}: differs at {each:#x}"


LIVE_NOISE_INSNS = 200_000              # a strayed machine is not waited on: the plain one arrives in some 80,000
A_POLL_AND_NO_MORE = 5_000              # instructions: one pass of an idle's loop, its keyboard poll a BIOS trap
STANDS_AT = ("pc", "isp", "usp", *(f"d{n}" for n in range(3, 8)), *(f"a{n}" for n in range(3, 7)))    # ...and what a C call keeps


# ---- a machine continued: its refusals, and what keeps a boot ----
def test_a_machine_is_continued_from_an_idle_by_what_it_can_receive_or_refused():
    """A boot stopped before its first idle stands at none; a reception that is no IKBD byte, mouse move or click's
    ticks is none; and a machine that NEVER IDLES — the button pressed on a menu's item and HELD: the screen manager
    sends its message and waits the button up by yielding (ct_msgup's `while (button & 1) dsptch()`), ready for ever —
    is refused by name inside its budget, not waited on."""
    with pytest.raises(aes_boot.Refused, match="stands at no idle"):
        aes_boot.continued.derive(at_the_rom_s_ctlmgr(A_DESK), ())
    with pytest.raises(aes_boot.Refused, match="a machine cannot receive"):
        booted_as(A_DESK).continued(("a key typed", 0x1c))
    with pytest.raises(aes_boot.Refused, match="the mouse cannot be moved to"):
        booted_as(A_DESK).continued(aes_boot.mouse_to(4000, 5))
    on_the_item = continued_through(A_DESK, None, MENU)[2]
    with pytest.raises(aes_boot.Refused, match="the machine never waits for an interrupt"):
        on_the_item.continued(aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.CLICK_TICKS, budget=LIVE_NOISE_INSNS)


@every_blob
def test_a_machine_that_receives_nothing_idles_again_where_it_stood(blob):
    """Continued with nothing received, a machine polls once and waits again AT THE SAME POLL, ON THE SAME STACK: the
    same megabyte outside its dead spans — from the ROM's idle, where the poll's own masked return rewrites the Line-F
    mask word (the ROM's code, and that word alone), and from OUR idle (the run entered AT the blob's poll, its return
    address into the blob's idle armed), where no C writes it. The scratch registers are then the poll's own leavings
    (at a boot's first idle they are the last switch's), and from there on the machine is A FIXED POINT: continued
    again, the same registers and the same megabyte, byte for byte."""
    (mask_lo, mask_hi, _why), = aes.LINE_F_MASK_WINDOW
    for stood in (booted_as(A_DESK), booted_as(A_DESK, blob),
                  continued_through(A_DESK, blob, MENU)[1]):
        again = stood.continued()
        left_out = [*aes_boot.dead_spans(stood).values(), *([(mask_lo, mask_hi)] if stood.idle == aes_boot.THE_ROM_S else [])]
        differing = [(at, size) for at, size in aes_boot._differing_runs(stood.ram, again.ram)
                     if not any(lo <= at and at + size <= hi for lo, hi in left_out)]
        assert differing == [] and again.idle == stood.idle and again.observed == ()
        assert {name: again.registers[name] for name in STANDS_AT} == {name: stood.registers[name] for name in STANDS_AT}
        assert again.registers["sr"] & aes_boot.OPEN_TO_INTERRUPTS == stood.registers["sr"] & aes_boot.OPEN_TO_INTERRUPTS, (
            "the machine is entered under the status register its idle was met with: the mask is not the harness's")
        assert 0 < again.boot.instructions < A_POLL_AND_NO_MORE
        once_more = again.continued()
        assert (once_more.ram, once_more.registers, once_more.boot.instructions) == (again.ram, again.registers, again.boot.instructions)


def test_a_takeover_boot_is_kept_by_the_blob_s_content():
    """`booted` is keyed by the pre-init machine AND THE BLOB, by value: one changed byte of the blob's image, another
    entry, another poll or another moment of the lay is another question — and the ROM's own boot is none of them.
    A source edit rebuilds the blob, so it re-derives every takeover machine (and the tree's key moves with it)."""
    capture, disk = capture_and_disk(A_DESK)
    bench, shipped = (aes_boot.ours_of(isr.blob_named(name)) for name in isr.BLOBS)

    def key(**named):
        return derived.key_of(aes_boot.booted.derive, (capture, disk), named)

    image = bytearray(bench.image)
    image[-1] ^= 1
    others = (key(ours=shipped), key(ours=bench._replace(image=bytes(image))), key(ours=bench._replace(entry=bench.entry + 2)),
              key(ours=bench._replace(poll=bench.poll + 2)), key(ours=bench, laid=aes_boot.FROM_THE_START), key())
    assert key(ours=bench) == key(ours=aes_boot.ours_of(isr.blob())) and len({key(ours=bench), *others}) == 1 + len(others)
    assert bench.image != shipped.image and bench.entry == isr.blob().entry(aes_boot.ENTRY_SYMBOL)


@every_blob
def test_a_screen_manager_parked_in_the_rom_s_text_is_no_takeover_machine(blob):
    """`_TakingOver.made`'s last vet, on a real takeover machine's own megabyte: as it stands it is passed; with the
    PC of the frame its screen manager is parked on naming the ROM's text — a machine whose `rte` entered our entry
    and whose screen manager all the same runs the ROM's code — it is refused by name. (No boot here makes one: the
    vet is held on its inputs.)"""
    booted = booted_as(A_DESK, blob)
    memory = booted.image()
    taking = aes_boot._TakingOver(memory, booted.ours, aes_boot.FROM_THE_START)
    taking.taken, taking.entered, taking._stored_in_the_span = booted.takeover, True, lambda since, until=None: []
    assert taking.made(memory, True) == booted.takeover
    manager = booted.screen_manager()
    parked = booted.long(manager.uda + aes.UDA_SUPER_SP) & BUS
    memory[parked + aes_boot.FRAME_PC:parked + aes_boot.FRAME_BYTES] = struct.pack(">I", addrs.AES_ROM_DSPTCH)
    with pytest.raises(aes_boot.Refused, match=f"stands parked at {addrs.AES_ROM_DSPTCH:#x}, in the ROM's text"):
        taking.made(memory, True)
    assert taking.made(memory, False) == booted.takeover, "a boot stopped at `until` stands at no idle: nothing is parked yet"


@every_blob
def test_a_poll_of_ours_is_an_idle_only_where_the_blob_s_idle_made_it(blob):
    """THE STOP THAT ENDS A RUN IN OUR DISPATCHER, on its inputs: the blob's keyboard poll is called by its idle AND
    by its ev_multi. Over a machine that waits for an interrupt, a stop at the poll whose return address lies in the
    blob's idle ends the run there (an idle of OURS, a poll counted); one that returns anywhere else — ev_multi's —
    ends nothing and counts nothing, though the three words idle tests say the machine waits."""
    booted = continued_through(A_DESK, blob, MENU)[1]
    ours, sp = booted.ours, booted.registers["isp"]
    assert booted.idle == aes_boot.OURS and aes_switch.waits_for_an_interrupt(booted.ram)
    for back, ends in ((ours.idle[0], True), (ours.idle[1] - WORD_BYTES, True), (ours.idle[1], False),
                       (ours.idle[0] - WORD_BYTES, False), (ours.entry, False)):
        memory = booted.image()
        memory[sp:sp + LONG_BYTES] = struct.pack(">I", back)
        run = aes_boot._Run(memory, aes_boot.Floppy(memory, booted.boot.disk), aes_boot.CONTINUED_INSNS, ours=ours)
        assert run._stopped(ours.poll, sp) is ends
        assert (run.idle, run.polls) == ((aes_boot.OURS, 1) if ends else (None, 0))


# ---- THE CLASSES OF TWO DISPATCHERS' IDLES, PINNED FROM OUTSIDE THE CODE THAT NAMES THEM ------------------------------------
# What `by_nature` answers where the two machines idle in two builds' dispatchers is held to spans READ ELSEWHERE:
# the dispatcher's stack from the ROM's own text (savestate's `lea <top>,sp`) and the word under it (psetup's SR
# save word, the last of the scheduler's three: the stack's first byte is the one after), the mask word from the
# AES's header, the BIOS's save frame from the machine's `savptr`.
SAVESTATE_LOADS_THE_DISPATCHER_STACK_AT = 0xfe3922      # `lea $8c1a,sp`
LEA_ABSOLUTE_LONG_TO_SP = 0x4ff9
USP_READS_BELOW_THE_STACK = 0x100       # the bytes under the dispatcher's stack: the SR save words, and what the USP names


def _dispatcher_stack_pinned():
    opcode, top = struct.unpack_from(">HI", BASE_IMAGE, SAVESTATE_LOADS_THE_DISPATCHER_STACK_AT)
    assert opcode == LEA_ABSOLUTE_LONG_TO_SP
    return aes.AES_SR_PSETUP + WORD_BYTES, top


DISPATCHER_STACK_PINNED = _dispatcher_stack_pinned()


def pinned_two_dispatcher_classes(ours):
    """`{class: (lo, hi)}` for a takeover machine that idles in OUR dispatcher beside the ROM's that idles in its own —
    from the pins above and the machine's own pointers, by no line of `by_nature`."""
    manager, savptr = ours.screen_manager(), ours.long(addrs.SYSVAR_SAVPTR) & BUS
    return {aes_boot.DISPATCHER_STACK: DISPATCHER_STACK_PINNED,
            aes_boot.SAVED_CONTEXT: (manager.uda + aes.UDA_REGS, manager.uda + aes.UDA_TRAP_SSP),
            aes_boot.MANAGER_STACK: (manager.uda + aes.UDA_STATE_BYTES, aes.AES_UDA1_STACK_TOP),
            aes_boot.THE_BLOB: (ours.ours.base, ours.ours.base + len(ours.ours.image)),
            aes_boot.LINE_F_MASK: (aes.AES_LINEF_MASK_WORD, aes.AES_LINEF_MASK_WORD + WORD_BYTES),
            aes_boot.TRAP_SAVE_FRAME: (savptr - addrs.TRAP_SAVE_FRAME_BYTES, savptr)}


@THREE_MACHINES
@every_blob
def test_the_classes_of_two_dispatchers_idles_are_the_pinned_spans_and_not_a_byte_more(label, blob):
    """ON A MACHINE THAT IDLES IN OUR DISPATCHER (both idles of the menu chain that do): the classes `by_nature`
    answers ARE the pinned ones — the dispatcher's WHOLE stack and no byte under or over it, the mask word's two
    bytes, the forty-six of the save frame under savptr — and the comparison SEES a byte flipped just outside each
    pinned span (and anywhere in the 256 bytes UNDER the dispatcher's stack, which hold the scheduler's SR save words
    and what the USP names at an idle), and none flipped at either end inside. The probes are the pins', so a class
    widened in the code is a byte the comparison no longer sees."""
    both = (aes_boot.LINE_F_MASK, aes_boot.TRAP_SAVE_FRAME)
    for step in (1, 2):
        rom, ours = (continued_through(label, each, MENU)[step] for each in (None, blob))
        assert rom.idle == aes_boot.THE_ROM_S and ours.idle == aes_boot.OURS
        pinned = pinned_two_dispatcher_classes(ours)
        classes, beside = aes_boot.by_nature(rom, ours)
        assert {**classes, **beside} == pinned
        assert aes_boot.compared(rom, ours, both).differing == []
        if step == 2 and label != A_DESK:
            continue                    # the flips below: one idle of each machine, and both of the desk's
        bottom, _top = pinned[aes_boot.DISPATCHER_STACK]
        under = [bottom - offset for offset in (1, 2, 3, 4, 5, 6, USP_READS_BELOW_THE_STACK // 2, USP_READS_BELOW_THE_STACK)]
        for lo, hi in pinned.values():
            for at in {lo - 1, hi, *under}:
                assert aes_boot.compared(rom, flipped(ours, at), both).differing == [(at, 1)], f"unseen at {at:#x}, beside [{lo:#x}, {hi:#x})"
            for at in (lo, hi - 1):
                assert aes_boot.compared(rom, flipped(ours, at), both).differing == []


def test_a_comparison_is_of_the_rom_s_machine_and_a_takeover_s_whose_screen_managers_are_one_process():
    """`by_nature`'s two refusals: the second machine must be a takeover's and the first the ROM's own (either the
    other way round, or two of a kind, is refused by name — no AttributeError), and the two screen managers must be
    ONE process by their PDs' own fields: a ROM machine whose SCRENMGR has another id is not the machine compared."""
    rom, ours = booted_as(A_DESK), booted_as(A_DESK, "the bench blob")
    for first, second in ((rom, rom), (ours, rom), (ours, ours)):
        with pytest.raises(aes_boot.Refused, match="a comparison is of the machine THE ROM BOOTED and, second"):
            aes_boot.compared(first, second)
    manager = rom.screen_manager()
    ram = bytearray(rom.ram)
    ram[manager.pd + aes.PD_PID:manager.pd + aes.PD_PID + WORD_BYTES] = struct.pack(">H", manager.pid + 4)
    another = aes_boot.Machine(rom.boot._replace(ram=bytes(ram)))
    with pytest.raises(aes_boot.Refused, match="the two machines' screen managers are not one process"):
        aes_boot.compared(another, ours)


@every_blob
def test_our_entry_must_be_entered_on_the_top_of_the_screen_manager_s_stack(blob):
    """`_TakingOver._entered`, on its inputs: the stop at our entry is the `rte`'s landing — on the stack's top, the
    frame popped — and at any other stack pointer (a call of the entry, a second arrival) it is refused by name."""
    booted = booted_as(A_DESK, blob)
    top = booted.takeover.stack[1]
    for sp, said in ((top, None), (top - aes_boot.FRAME_BYTES, "not on the top"), (top - LONG_BYTES, "not on the top"),
                     (top + WORD_BYTES, "not on the top")):
        taking = aes_boot._TakingOver(booted.image(), booted.ours, aes_boot.FROM_THE_START)
        taking.taken = booted.takeover
        if said is None:
            taking.stopped(booted.ours.entry, sp, 0)
            assert taking.entered and taking.armed == frozenset()
        else:
            with pytest.raises(aes_boot.Refused, match=f"our entry is entered at SP {sp:#x}, {said}"):
                taking.stopped(booted.ours.entry, sp, 0)
            assert not taking.entered


# ---- "NO STORE AFTER THE LAY", THROUGH THE REAL LEDGER --------------------------------------------------------------------
STORE_D0_WORD_ABSOLUTE = b"\x33\xc0"    # move.w d0,<xxx>.l
JUMP_ABSOLUTE = b"\x4e\xf9"             # jmp <xxx>.l


def storing_into_itself(ours):
    """`ours` WITH AN ENTRY THAT STORES INTO THE BLOB'S OWN SPAN — twelve bytes of code and a word appended to the
    image: `move.w d0,<the word>` (D0 is zero at the first entry, and so is the word: the store changes NO byte),
    then `jmp <the blob's own entry>`. A labelled forgery of a BUILD, for the RED alone."""
    stub = ours.base + len(ours.image)
    word = stub + len(STORE_D0_WORD_ABSOLUTE) + LONG_BYTES + len(JUMP_ABSOLUTE) + LONG_BYTES
    code = STORE_D0_WORD_ABSOLUTE + struct.pack(">I", word) + JUMP_ABSOLUTE + struct.pack(">I", ours.entry) + bytes(WORD_BYTES)
    return ours._replace(image=ours.image + code, end=stub + len(code), entry=stub), word


@every_blob
@pytest.mark.parametrize("label", (A_DESK, WITH_ACCESSORIES))
def test_a_store_into_the_blob_after_the_lay_is_seen_by_the_run_s_own_ledger_and_refused(label, blob):
    """RED, BY A REAL BOOT AND THE REAL LEDGER, THE BLOB LAID AT THE STOP: a build whose entry stores one word into its
    own span — a zero over a zero: no byte changes, so only the ledger can tell — is refused by name where the boot
    ends, the two bytes counted. (What the mark is for: without it the ledger's entries before the lay — Pexec's
    clear — would be read as stores over the blob, and with it past them all, nothing would.)"""
    forged, word = storing_into_itself(aes_boot.ours_of(isr.blob_named(blob)))
    with pytest.raises(aes_boot.Refused, match=f"THE BOOT STORED OVER THE BLOB, laid at the screen manager's first entry: "
                                               f"2 byte\\(s\\) of its span .* from {word:#x} on"):
        aes_boot.booted.derive(*capture_and_disk(label), ours=forged)


# ---- A CONTINUED TAKEOVER MACHINE STILL HOLDS ITS BLOB -----------------------------------------------------------------------
def with_a_blob_spanning(booted, lo, hi):
    """The takeover machine `booted` AS IF ITS BLOB LAY OVER `[lo, hi)` — a labelled forgery of the `Ours` it carries
    (the span and the bytes found there; its entry, poll and idle are the real blob's, so it runs as it did): what a
    continuation that stores THERE is to the vet."""
    forged = booted.ours._replace(base=lo, end=hi, image=booted.ram[lo:hi])
    return aes_boot.Machine(booted.boot._replace(takeover=booted.takeover._replace(ours=forged)))


@every_blob
def test_a_continuation_that_reaches_the_blob_is_refused_by_name(blob):
    """THE STANDING LIMIT, RED three ways through the continuation's own vet (`_vet_the_blob_was_not_reached`):
      * THE RUN'S LEDGER: a span the continued run really stores in (the screen manager's saved context, which
        savestate writes when it parks again) — refused, the bytes counted;
      * AN INTERRUPT HANDLER'S STORES: a span the ROM's mouse interrupt writes (the cursor's position), the machine
        receiving a move — refused though the run that follows stores nothing there;
      * BYTES NO LEDGER NAMES: the machine's blob with one byte of its text changed before it is continued — refused
        as bytes that are not the blob's.
    And the plain machine, the same receptions, is continued."""
    booted = booted_as(A_DESK, blob)
    manager = booted.screen_manager()
    context = (manager.uda + aes.UDA_REGS, manager.uda + aes.UDA_TRAP_SSP)
    cursor = (vdi.LINEA_GCURX, vdi.LINEA_GCURY + WORD_BYTES)
    assert booted.continued(*ONTO_THE_VIEW_TITLE).observed
    with pytest.raises(aes_boot.Refused, match="CANNOT BE CONTINUED THROUGH AN ALLOCATION THAT REACHES THE BLOB: the "
                                               f"continuation stored .* byte\\(s\\) of its span \\[{context[0]:#x}"):
        with_a_blob_spanning(booted, *context).continued(*ONTO_THE_VIEW_TITLE)
    off_the_bar = (aes_boot.mouse_to(*aes_event.A_POINT_ON_THE_DESKTOP),)
    quiet = booted.continued(*off_the_bar)
    assert not {at for start, length in quiet.boot.stored for at in range(start, start + length)} & set(range(*cursor)), (
        "the premise: the run after a move over the desktop stores nothing at the cursor's position — the handler did")
    with pytest.raises(aes_boot.Refused, match=f"the continuation stored .* byte\\(s\\) of its span \\[{cursor[0]:#x}"):
        with_a_blob_spanning(booted, *cursor).continued(*off_the_bar)
    for at in (booted.ours.entry + 5, booted.ours.base + len(booted.ours.image) - 1):
        changed = bytearray(booted.ram)
        changed[at] ^= 0xff
        with pytest.raises(aes_boot.Refused, match="left its span holding other bytes than the blob's"):
            aes_boot.Machine(booted.boot._replace(ram=bytes(changed))).continued()


def test_an_interrupt_the_idle_s_mask_would_never_let_in_is_refused():
    """THE INTERRUPT MODEL DELIVERS ONLY WHAT THE CPU WOULD TAKE: a machine whose idle stands at mask 6 or 7 — a
    dispatcher that left the interrupts shut — receives no IKBD byte and no tick: refused by name, where a model that
    ran the handler anyway would show a dead machine alive. At 5 and below an MFP interrupt is taken."""
    booted = booted_as(A_DESK)
    for mask, said in ((7, "the interrupt mask at 7"), (6, "the interrupt mask at 6")):
        shut = {**booted.registers, "sr": booted.registers["sr"] & ~addrs.SR_IPL_MASK | mask << aes_boot.SR_IPL_SHIFT}
        stood = aes_boot.Machine(booted.boot._replace(registers=shut))
        for received in (ONTO_THE_VIEW_TITLE, (aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0),)):
            with pytest.raises(aes_boot.Refused, match=f"{said}: the IKBD's byte .* is never taken. On iron this machine is dead"):
                stood.continued(*received)
    memory = booted.image()
    for mask in range(aes_boot.MFP_LEVEL):
        aes_boot._Receiving(memory, preinit_snapshot.SR_SUPERVISOR | mask << aes_boot.SR_IPL_SHIFT).all_of(
            (aes_boot.ikbd(aes_boot.NO_BUTTON, 1, 0),))
    with pytest.raises(aes_boot.Refused, match="the system timer's tick .* is never taken"):
        pressed = booted.image()
        aes_boot._Receiving(pressed, booted.registers["sr"]).all_of((aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0),))
        aes_boot._Receiving(pressed, booted.registers["sr"] | addrs.SR_IPL_MASK).all_of((aes_boot.CLICK_TICKS,))


# ---- THE REGISTRY: an entry declared beside the tuple Tier 3 reads is NAMED, with its owner, until it is mapped -------------
def _relocations_declared():
    return {name: value for name, value in vars(aes_event).items() if isinstance(value, aes_event.RelocatedCode)}


def _held_at(pokes, at):
    """The longword a row's machine holds at `at`: its pokes over the snapshot."""
    held = bytearray(BASE_IMAGE[at:at + LONG_BYTES])
    for start, data in pokes.items():
        for offset in range(max(at, start), min(at + LONG_BYTES, start + len(data))):
            held[offset - at] = data[offset - start]
    return case.long_in(held, 0)


def rows_on_a_takeover_machine(rows):
    """The Tier 3 rows whose machine is A TAKEOVER'S: the screen manager's p_ldaddr holds A BLOB'S ENTRY — the bench
    blob's or the shipped one's, by symbol (the ROM's ctlmgr, nothing, or a value a case staged there is none)."""
    slot = aes_event.SCREEN_MANAGER_ENTRY_SLOTS[0]
    entries = {aes_boot.ours_of(isr.blob_named(name)).entry for name in isr.BLOBS}
    return [row for row in rows if isinstance(row.pokes, dict) and _held_at(row.pokes, slot) in entries]


def test_every_relocation_declared_is_mapped_at_tier_3_or_named_not_yet_with_its_owner():
    """NOTHING IS DECLARED BESIDE THE REGISTRY SILENTLY. Every `RelocatedCode` of `aes_event` is in the tuple Tier 3
    reads (`CODE_RELOCATIONS`) or NAMED in `DECLARED_NOT_YET_MAPPED_AT_TIER3` with its reason and the slice that owes
    its mapping site — never both, never neither."""
    declared, not_yet = _relocations_declared(), aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3
    assert aes_event.SCREEN_MANAGER_ENTRY in declared.values() and len(declared) >= 4
    for name, relocation in declared.items():
        mapped, named = relocation in aes_event.CODE_RELOCATIONS, relocation.what in not_yet
        assert mapped != named, f"aes_event.{name} ({relocation.what}): in the tuple Tier 3 reads: {mapped}; named not yet mapped: {named}"
    assert set(not_yet) <= {relocation.what for relocation in declared.values()}, "a name of the list that no relocation has"
    assert all(reason and owner for reason, owner in not_yet.values())


def test_no_tier_3_row_runs_on_a_takeover_machine_while_a_relocation_is_not_yet_mapped():
    """...AND THE LIST MUST BE EMPTY THE DAY A TIER 3 ROW RUNS ON A TAKEOVER MACHINE — read off the row registry
    itself (`tier3.ROWS`: a row whose machine holds a blob's entry in the screen manager's p_ldaddr): that row's two
    shores differ in the slots by nature, and only the registry maps them. So the flip cannot land its rows and forget
    the entry: this reddens, naming the first such row."""
    not_yet = aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3
    rows = harness.bench_tier3().ROWS
    assert len(rows) > 1000, "the registry read is Tier 3's whole table"
    taken_over = rows_on_a_takeover_machine(rows)
    assert not (taken_over and not_yet), (
        f"{len(taken_over)} Tier 3 row(s) run on a takeover machine (the first: {taken_over[0].function} / {taken_over[0].case}) "
        f"while {sorted(not_yet)} is still not mapped at Tier 3: add it to CODE_RELOCATIONS with its site in "
        f"`tier3.code_relocations`")


def test_a_row_on_a_takeover_machine_is_told_from_the_rom_s_by_the_slot_it_holds():
    """...and the reading has teeth: a row over the snapshot, over a machine before ictlmgr, over the ROM's own boot
    and over a machine a case staged another address in is none; one over a takeover machine's megabyte is — found
    by the slot, whatever its name."""
    row = namedtuple("Row", "function case pokes")
    taken, slot = booted_as(A_DESK, "the bench blob"), aes_event.SCREEN_MANAGER_ENTRY_SLOTS[0]
    before = {slot: bytes(LONG_BYTES)}
    rows = [row("a", "the snapshot", {}), row("b", "before ictlmgr", before), row("c", "the ROM's boot", booted_as(A_DESK).pokes),
            row("d", "a takeover", taken.pokes), row("e", "a delta over one", {slot - 2: taken.ram[slot - 2:slot + 6]}),
            row("f", "another address staged", {slot: struct.pack(">I", addrs.AES_ROM_HCTL_BUTTON)})]
    assert [each.case for each in rows_on_a_takeover_machine(rows)] == ["a takeover", "a delta over one"]


@every_blob
def test_a_machine_restaged_carries_its_blob_as_the_staging_left_it(blob):
    """`restaged`: a megabyte with a byte of the blob's text changed, handed as the machine's bare RAM, is refused when
    continued (the blob is not the blob's); handed through `restaged` — the staging LABELLED, the `Ours` it carries
    given the bytes — it is continued, the changed byte still there, and a store over it after that is refused as any
    is. On the ROM's machine it is the megabyte replaced and nothing else."""
    booted = booted_as(A_DESK, blob)
    memory, at = booted.image(), booted.ours.base + len(booted.ours.image) - 1
    memory[at] ^= 0xff
    with pytest.raises(aes_boot.Refused, match="holding other bytes than the blob's"):
        aes_boot.Machine(booted.boot._replace(ram=bytes(memory[:RAM_BYTES]))).continued()
    staged = aes_boot.restaged(booted, memory)
    assert staged.ours.image[-1] == memory[at] != booted.ours.image[-1] and staged.ours._replace(image=b"") == booted.ours._replace(image=b"")
    again = staged.continued(*ONTO_THE_VIEW_TITLE)
    assert again.ram[at] == memory[at] and again.observed == booted.continued(*ONTO_THE_VIEW_TITLE).observed
    changed = bytearray(again.ram)
    changed[at] ^= 0xff
    with pytest.raises(aes_boot.Refused, match="holding other bytes than the blob's"):
        aes_boot.Machine(again.boot._replace(ram=bytes(changed))).continued()
    rom = booted_as(A_DESK)
    assert aes_boot.restaged(rom, memory).ram == bytes(memory[:RAM_BYTES]) and aes_boot.restaged(rom, memory).takeover is None
