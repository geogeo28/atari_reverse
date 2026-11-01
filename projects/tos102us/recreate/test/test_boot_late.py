"""BOOT B6 HELD (`test/boot_late.py`, `src/boot/late/late.c`): the boot's interrupt-enabled late slice `[$fc0452, $fc047a)`
and the routines it ports with it (`$fc4a9e`, `$fc4be8`, `$fc053c`, `$fc0558`, `$fc0e56`) — the ROM's own against our C,
on the WARM and COLD machines (ruling D8, each A LABELLED STAGING), our side over a copy of the ROM window (rulings
"ROM-window overlay", "Own link rule").

THE WAITING ROUTINES ANSWERED AT THEIR ENTRIES on both shores (ruling D3, 2026-10-31; D4 for the floppy; R-B4-2 for the
clock): each answer's value held here to the ROM's text that would leave it and to the capture — Hatari's run of the ROM's
own code — that holds it; each answer shown to write what it says and nothing else. Held on every observable surface: the
stop, every register, the megabyte and the stores outside the BIOS stack's dead frames (the capture's own MASK field),
every ordered ledger, the faults, the answers in order; each surface's negative here; each arm's own cost pinned exactly;
the price the table's (ruling D9). THE END SURFACE: the machine both shores reach at `$fc047a` against the mid-boot
capture under its own mask — apart in exactly the classes named (D1, D4), the same on both shores; B4's open carry
(A3, A4, A6) closed here."""
import re
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs

import aes_boot
import boot
import boot_late as bl
import case
import layouts
import midboot_snapshot
import rom_data

C = bl.CONSTANTS
BAR = 1.10
WORD_BYTES, LONG_BYTES = bl.WORD_BYTES, bl.LONG_BYTES
# THE ROM'S INSTRUCTIONS THE ANSWERS ARE READ OFF (each held to its text below).
DRIVE_PROBE_SUCCESS_BRANCH = 0xfc177a   # the probe's `beq.w` to its success exit ...
DRIVE_PROBE_SUCCESS = 0xfc1cda          # ...`clr.l d0`
ACSI_TIMED_OUT = 0xfc0642               # `$fc062a`'s `moveq #-1,d1`: `_hz_200` passed the count
ACSI_FAILED = 0xfc0606                  # `moveq #-1,d0`: the probe's failure
ACSI_FLAGS_SET = 0xfc060c               # `tst.b d0`: the flags it returns
ACSI_FLOCK_TAKEN, ACSI_FLOCK_FREED = 0xfc0592, 0xfc060e     # `st flock` / `sf flock`
CLOCK_PROBE_ABSENT = 0xfc4c3e           # the probe's `ori #1,ccr`: no RP5C15
RS232_TABLE_LOADED = 0xfc2522           # `$fc2408`'s `movea.l #<the RS232 handlers' table>,a3`
PRTBLK_END = 0xfc41a4                   # past Prtblk's own `rts` ($fc41a2): the text the overlay lies in ends
DISPLAY_BIN = bl.RECREATE / "build" / "bootdisplay" / "display.bin"
DISTINCT_LONG = 0x5a3c_c3a5            # a register pattern whose every byte differs from what an answer writes
ACSI_TARGETS = tuple(range(0, 0x100, C["ACSI_TARGET_STEP"]))    # `moveq #0,d7` .. the byte's wrap
FLOPPY_DRIVES = (0, 1)                  # hdv_init's loop: `cmpi.w #2,-2(a6)` ($fc0fb4) — drives A: and B:
SR_INTERRUPT_MASK = 0x0700
JMP_ABSOLUTE_LONG, JSR_ABSOLUTE_LONG = 0x4ef9, 0x4eb9


# ---- THE ROM'S TEXT: every constant the C is spelt in, read off the instruction that uses it ------------------------------
def _listing(span):
    return [text for _at, text in rom_data.instructions(*span)]


def test_the_slice_is_spelt_in_the_rom_s_own_operands():
    """`[$fc0452, $fc047a)` as the ROM's listing reads it, composed out of `boot/late.h` and the headers it names."""
    assert _listing(bl.SPAN) == [
        f"movew #{C['BOOT_SR_INTERRUPTS_OPEN']},%sr", f"moveq #{C['CARTRIDGE_HOOK_INTERRUPTS']},%d0",
        f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}", f"bsrw {bl.GEMDOS_BUFFERS[0]:#x}",
        f"movew {C['ROM_OS_HEADER'] + C['OS_HEADER_DOSDATE']:#x},{addrs.GEMDOS_DATE:#x}",
        f"bsrw {bl.CLOCK_DATE[0]:#x}", f"bsrw {bl.FLOPPY_BOOT[0]:#x}", f"bsrw {bl.ACSI_BOOT[0]:#x}",
        f"bsrw {bl.RESIDENT_SCAN[0]:#x}"]
    assert bl.SPAN == (C["ROM_DISPLAY_END"], C["ROM_LAUNCH"])


def test_gemdos_s_buffers_are_spelt_in_the_rom_s_own_operands():
    """`$fc4a9e`: four BCBs from BOOT_BCB_FIRST, two to a list, the first of each linked to the second, every one EMPTY,
    their sector buffers end to end from BOOT_SECTOR_BUFFER_FIRST; the lists' heads in _bufl; GEMDOS's init; Dsetdrv of
    the boot drive from the `link`'s one local; and the frame that is GEMDOS_BUFFERS_FRAME_BYTES with the `bsr`'s return."""
    fs = layouts.parse_constants((bl.RECREATE / "include" / "gemdos" / "fs.h",))
    bcbs = [C["BOOT_BCB_FIRST"] + each * fs["BCB_BYTES"] for each in range(2 * C["BOOT_BCBS_PER_LIST"])]
    buffers = [C["BOOT_SECTOR_BUFFER_FIRST"] + each * addrs.BOOT_SECTOR_BYTES for each in range(len(bcbs))]
    local = C["GEMDOS_BUFFERS_FRAME_BYTES"] - 2 * LONG_BYTES
    assert _listing(bl.GEMDOS_BUFFERS) == [
        f"linkw %fp,#-{local}",
        f"movel #{bcbs[1]},{bcbs[0] + fs['BCB_LINK']:#x}", f"movel #{bcbs[3]},{bcbs[2] + fs['BCB_LINK']:#x}",
        *[f"movew #-1,{bcb + fs['BCB_BUFDRV']:#x}" for bcb in bcbs],
        *[f"movel #{buffer},{bcb + fs['BCB_BUFR']:#x}" for bcb, buffer in zip(bcbs, buffers)],
        f"movel #{bcbs[0]},{addrs.SYSVAR_BUFL:#x}", f"movel #{bcbs[2]},{addrs.SYSVAR_BUFL + addrs.SYSVAR_BUFL_ENTRY_BYTES:#x}",
        f"jsr {C['ROM_GEMDOS_INIT']:#x}", f"movew {C['SYSVAR_BOOTDEV']:#x},%sp@", f"jsr {addrs.GEMDOS_DSETDRV:#x}",
        "unlk %fp", "rts"]
    assert fs["BCB_EMPTY"] == 0xffff


def test_the_clock_s_date_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.CLOCK_DATE) == [
        f"bsrs {addrs.BIOS_RTC_PROBE:#x}", "bcss 0xfc4c08", f"bsrs {C['ROM_RTC_READ']:#x}", "cmpl #-1,%d0",
        "beqs 0xfc4c08", f"movew %d0,{addrs.GEMDOS_TIME:#x}", "swap %d0", f"movew %d0,{addrs.GEMDOS_DATE:#x}",
        "moveq #0,%d0", "rts", "moveq #-1,%d0", "rts"]
    assert C["RTC_NO_STAMP"] == 0xffffffff


def test_the_floppy_s_boot_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.FLOPPY_BOOT) == [
        f"moveq #{C['CARTRIDGE_HOOK_FLOPPY_BOOT']},%d0", f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}",
        f"moveal {C['SYSVAR_HDV_BOOT']:#x},%a0", "jsr %a0@", "tstw %d0", "bnes 0xfc0556",
        f"lea {C['BOOT_DISK_BUFFER']:#x},%a0", "jsr %a0@", "rts"]


def test_the_acsi_s_boot_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.ACSI_BOOT) == [
        "moveq #0,%d7", f"bsrs {C['ROM_ACSI_READ_BOOT_SECTOR']:#x}", "bnes 0xfc057e",
        f"moveal {C['SYSVAR_DSKBUFP']:#x},%a0", f"movew #{addrs.BOOT_SECTOR_WORDS - 1},%d1", "moveq #0,%d0",
        "addw %a0@+,%d0", "dbf %d1,0xfc056a", f"cmpw #{addrs.BOOT_EXECUTABLE_SUM},%d0", "bnes 0xfc057e",
        f"moveal {C['SYSVAR_DSKBUFP']:#x},%a0", "jsr %a0@", f"addb #{C['ACSI_TARGET_STEP']},%d7", "bnes 0xfc055a", "rts"]


def test_the_reset_resident_scan_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.RESIDENT_SCAN) == [
        f"moveal {addrs.SYSVAR_PHYSTOP:#x},%a0", f"subaw #{C['RESIDENT_PAGE_BYTES']},%a0",
        f"cmpal #{C['RESIDENT_SCAN_FLOOR']},%a0", "beqs 0xfc0e94", f"cmpil #{C['RESIDENT_MAGIC']},%a0@",
        "bnes 0xfc0e5c", f"cmpal %a0@({C['RESIDENT_SELF']}),%a0", "bnes 0xfc0e5c", "clrw %d0", "moveal %a0,%a1",
        f"movew #{addrs.BOOT_SECTOR_WORDS - 1},%d1", "addw %a1@+,%d0", "dbf %d1,0xfc0e7e", f"cmpw #{C['RESIDENT_SUM']},%d0",
        "bnes 0xfc0e5c", "movel %a0,%sp@-", f"jsr %a0@({C['RESIDENT_ENTRY']})", "moveal %sp@+,%a0", "bras 0xfc0e5c",
        "rts"]


# ---- THE ANSWERS: each entry, each value, held to the ROM's text and to the capture --------------------------------------
def _at(at):
    return rom_data.instructions(at, at + WORD_BYTES)[0][1]


def test_the_drive_probe_is_hdv_init_s_and_its_answer_the_capture_s():
    """D3: the probe hdv_init calls for each drive, the drive at 12(sp); hdv_init stores its D0 in the drive's status
    word; the capture's ROM run stored DRIVE_PRESENT for BOTH drives — the probe's success exit (`clr.l d0`)."""
    assert _at(bl.DRIVE_PROBE_CALL) == f"jsr {bl.DRIVE_PROBE:#x}"
    assert _at(bl.DRIVE_PROBE + 6) == f"tstw %sp@({bl.DRIVE_PROBE_DEVICE_AT})"
    status = case.long_in(BASE_IMAGE, bl.DRIVE_STATUS_LOAD + WORD_BYTES)
    assert _at(bl.DRIVE_STATUS_LOAD) == f"addal #{status},%a0"
    capture = boot.midboot_machine()
    assert [case.word_in(capture.ram, status + drive * WORD_BYTES) for drive in FLOPPY_DRIVES] == [bl.DRIVE_PRESENT] * 2
    assert _at(DRIVE_PROBE_SUCCESS_BRANCH) == f"beqw {DRIVE_PROBE_SUCCESS:#x}" and _at(DRIVE_PROBE_SUCCESS) == "clrl %d0"
    assert bl.DRIVE_PRESENT == 0


def test_floprd_is_the_machine_s_own_xbios_entry_and_hdv_boot_calls_it():
    assert _at(bl.FLOPRD_CALL) == f"jsr {bl.FLOPRD_ENTRY:#x}"
    machine = bl.start_of(boot.COLD)
    memory = bytearray(BASE_IMAGE)
    memory[:bl.RAM_BYTES] = machine.ram
    assert aes_boot._xbios_entry(memory, aes_boot.XBIOS_FLOPRD) == bl.FLOPRD_ENTRY


def test_the_acsi_s_no_device_is_what_the_rom_s_probe_leaves_and_what_the_capture_holds():
    """D3 "no device": the probe `lea`s A6 and A5 first; its first command byte unacknowledged, `$fc062a` ends with
    `moveq #-1,d1`, `$fc0606` `moveq #-1,d0`, then `tst.b d0` and `sf flock`. The capture — Hatari's run of the ROM's own
    probe, eight times, the reset-resident scan after it touching none of the four — holds exactly these."""
    assert _at(bl.ACSI_PROBE) == f"lea {bl.ACSI_A6:#x},%fp" and _at(bl.ACSI_PROBE + 6) == f"lea {bl.ACSI_A5:#x},%a5"
    assert _at(ACSI_TIMED_OUT) == "moveq #-1,%d1" and _at(ACSI_FAILED) == "moveq #-1,%d0" and _at(ACSI_FLAGS_SET) == "tstb %d0"
    assert _at(ACSI_FLOCK_TAKEN) == f"st {addrs.SYSVAR_FLOCK:#x}" and _at(ACSI_FLOCK_FREED) == f"sf {addrs.SYSVAR_FLOCK:#x}"
    assert _at(bl.ACSI_WAIT_ADD) == f"addl {addrs.SYSVAR_HZ_200:#x},%d1"
    capture = boot.midboot_machine()
    assert {name: capture.registers[name] for name in bl.ACSI_NO_DEVICE} == bl.ACSI_NO_DEVICE
    assert capture.ram[addrs.SYSVAR_FLOCK] == 0


def _standing_at(machine, entry, **registers):
    """`machine` standing at `entry` as a caller's `jsr` leaves it: a return address pushed under the stack pointer."""
    ram = bytearray(machine.ram)
    sp = machine.registers["isp"] - LONG_BYTES
    struct.pack_into(">I", ram, sp, bl.SPAN[1])
    return machine._replace(ram=bytes(ram), registers={**machine.registers, "pc": entry, "isp": sp, **registers})


@pytest.mark.parametrize("entry", sorted(bl.ANSWERED - {bl.FLOPRD_ENTRY}), ids=hex)
def test_each_answer_writes_what_it_says_and_nothing_else(entry):
    """Each answer from a machine whose every scratch register holds a pattern: the registers it names written, the
    flags it names, the PC the return, the stack one longword up — every other register and byte as they were."""
    machine = bl.start_of(boot.COLD)
    before = _standing_at(machine, entry, **{name: DISTINCT_LONG for name in ("d0", "d1", "a5", "a6")},
                          d7=0x40, sr=machine.registers["sr"] | 0x1f)
    after, asked, laid = bl.answered(before)
    registers = {**before.registers, "pc": bl.SPAN[1], "isp": before.registers["isp"] + LONG_BYTES}
    ram = bytearray(before.ram)
    if entry == bl.DRIVE_PROBE:     # what the capture's own hdv_init stored for the drive asked (the ROM's run on Hatari)
        status = case.long_in(BASE_IMAGE, bl.DRIVE_STATUS_LOAD + WORD_BYTES)
        drive = case.word_in(before.ram, before.registers["isp"] + bl.DRIVE_PROBE_DEVICE_AT)
        registers["d0"] = case.word_in(boot.midboot_machine().ram, status + drive * WORD_BYTES)
        assert asked == ("the drive probe", drive)
    elif entry == bl.ACSI_PROBE:    # read off the ROM's text: the two `lea`s, the two `moveq #-1`, `tst.b` over -1
        a6, a5 = (_operand_of_lea(at) for at in (bl.ACSI_PROBE, bl.ACSI_PROBE + 6))
        registers.update(d0=_moveq_minus_one(ACSI_FAILED), d1=_moveq_minus_one(ACSI_TIMED_OUT), a5=a5, a6=a6)
        registers["sr"] = before.registers["sr"] & ~0x1f | 0x08      # X (the wait's `add.l`, no carry) Z V C clear, N set
        ram[addrs.SYSVAR_FLOCK] = 0
        assert asked == ("the ACSI probe", 0x40) and laid == ((addrs.SYSVAR_FLOCK, 1),)
    else:                           # the probe's absent arm: `ori #1,ccr` — the carry
        assert _at(CLOCK_PROBE_ABSENT) == "orib #1,%ccr"
        registers["sr"] = before.registers["sr"] | 0x01
        assert asked == ("the clock's probe",)
    assert after.registers == registers and after.ram == bytes(ram)


def _operand_of_lea(at):
    return int(re.fullmatch(r"lea (0x[0-9a-f]+),%(?:fp|a5)", _at(at)).group(1), 16)


def _moveq_minus_one(at):
    assert _at(at).startswith("moveq #-1,")
    return 0xffffffff


def test_floprd_s_answer_is_the_device_model_s_read_of_the_capture_s_disk():
    """D4: hdv_boot's Floprd served by `aes_boot.Floppy` (drive A: never logged in): the boot sector of the blank disk
    laid at the buffer it names, D0 the model's answer, nothing else of the machine but the return."""
    shore = bl.the_rom_s(boot.COLD)
    floprd = [asked for asked in shore.answers if asked[0] == "Floprd"]
    assert len(floprd) == 1
    sector = bytes(shore.slice.machine.ram[C["BOOT_DISK_BUFFER"]:C["BOOT_DISK_BUFFER"] + addrs.BOOT_SECTOR_BYTES])
    assert sector == bl.the_disk()[:addrs.BOOT_SECTOR_BYTES]
    assert any(
        start <= C["BOOT_DISK_BUFFER"] and C["BOOT_DISK_BUFFER"] + addrs.BOOT_SECTOR_BYTES <= start + length
        for start, length in shore.slice.stored)


def test_an_entry_no_answer_names_is_refused():
    with pytest.raises(boot.Refused, match="no answered entry"):
        bl.answered(bl.start_of(boot.COLD))


# ---- THE PRODUCT AND ITS STAGING ------------------------------------------------------------------------------------------
def test_the_product_lies_at_its_laid_address_clear_of_b5_s_overlay():
    display = layouts.parse_constants((bl.INCLUDE_BOOT / "display.h",))["DISPLAY_LAID_AT"]
    product = bl.product()
    assert product.base == C["LATE_LAID_AT"] and product.symbols[bl.ENTRY_SYMBOL] == product.base
    assert display + DISPLAY_BIN.stat().st_size <= product.base and product.base + len(product.code) <= PRTBLK_END


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_the_rom_s_run_is_the_same_with_and_without_the_overlay(machine):
    plain, with_it = bl.the_rom_s(machine), bl.the_rom_s(machine, laid=bl.overlay())
    assert (with_it.slice.stop, with_it.slice.instructions, with_it.slice.cycles, with_it.own, with_it.answers) == (
        plain.slice.stop, plain.slice.instructions, plain.slice.cycles, plain.own, plain.answers)
    assert with_it.slice.machine == plain.slice.machine and with_it.slice.stored == plain.slice.stored
    assert all(getattr(with_it.slice, ledger) == getattr(plain.slice, ledger) for ledger in bl.LEDGERS)


@pytest.mark.parametrize("span", bl.THE_ROM_S_SPANS, ids=lambda span: f"{span[0]:#x}")
def test_a_run_of_ours_that_runs_the_rom_s_code_is_refused_by_name(span):
    """THE FALSE GREEN: code laid as ours that jumps into the ROM's own slice — or any routine this slice ports — would
    be held equal on the ROM's instructions."""
    if span == bl.SPAN:
        jump_in = struct.pack(">HI", JMP_ABSOLUTE_LONG, span[0])
    else:       # a routine the slice ports, called as ours would call it, then on to the slice's end
        jump_in = struct.pack(">HIHI", JSR_ABSOLUTE_LONG, span[0], JMP_ABSOLUTE_LONG, bl.SPAN[1])
    with pytest.raises(boot.Refused, match=rf"the run executed \[{span[0]:#x}, {span[1]:#x}\)"):
        bl.our_side(boot.COLD, code=jump_in)


# ---- EVERY ARM, EVERY HELD SURFACE ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module", params=bl.MACHINES)
def a_pair(request):
    machine = request.param
    return machine, bl.the_rom_s(machine), bl.our_side(machine)


def test_ours_is_the_rom_s_on_every_held_surface(a_pair):
    _machine, the_rom_s, ours = a_pair
    assert bl.differences(the_rom_s, ours) == []
    assert ours.slice.stop == bl.SPAN[1] and ours.slice.machine.registers == the_rom_s.slice.machine.registers


def test_the_answers_are_asked_in_the_rom_s_order(a_pair):
    """The hooks with 1; GEMDOS's init; Dsetdrv of drive 0 (`_bootdev`); the clock once; the hooks with 3; the drive probe for A: then B:; Floprd once (the boot sector,
    drive A:); the ACSI for each of its eight targets in order — on both shores."""
    _machine, the_rom_s, ours = a_pair
    assert ours.answers == the_rom_s.answers
    hooks = "the cartridge's hooks"
    assert [asked for asked in ours.answers if asked[0] != "Floprd"] == [
        (hooks, C["CARTRIDGE_HOOK_INTERRUPTS"]), ("GEMDOS's init",), ("Dsetdrv", 0), ("the clock's probe",),
        (hooks, C["CARTRIDGE_HOOK_FLOPPY_BOOT"]),
        *[("the drive probe", drive) for drive in FLOPPY_DRIVES], *[("the ACSI probe", target) for target in ACSI_TARGETS]]
    assert [asked[0] for asked in ours.answers].index("Floprd") == 5 + len(FLOPPY_DRIVES)


def test_the_slice_s_state_is_laid(a_pair):
    """What the slice is FOR, on both shores: the interrupts open (mask 3), the two buffer lists, the DOS date the OS
    header's, the drives counted and mounted (both answered), the boot sector read, flock free, A0 the scan's floor."""
    _machine, _the_rom_s, ours = a_pair
    ram, registers = ours.slice.machine.ram, ours.slice.machine.registers
    assert registers["sr"] & SR_INTERRUPT_MASK == C["BOOT_SR_INTERRUPTS_OPEN"] & SR_INTERRUPT_MASK
    fs = layouts.parse_constants((bl.RECREATE / "include" / "gemdos" / "fs.h",))
    first, third = C["BOOT_BCB_FIRST"], C["BOOT_BCB_FIRST"] + 2 * fs["BCB_BYTES"]
    assert [case.long_in(ram, addrs.SYSVAR_BUFL + list_ * addrs.SYSVAR_BUFL_ENTRY_BYTES) for list_ in (0, 1)] == [first, third]
    assert case.word_in(ram, addrs.GEMDOS_DATE) == case.word_in(BASE_IMAGE, C["ROM_OS_HEADER"] + C["OS_HEADER_DOSDATE"])
    assert case.long_in(ram, addrs.SYSVAR_DRVBITS) & 0b11 == 0b11
    assert ram[addrs.SYSVAR_FLOCK] == 0 and registers["a0"] == C["RESIDENT_SCAN_FLOOR"] and registers["d7"] == 0


def test_no_interrupt_is_delivered_and_no_hardware_is_touched(a_pair):
    """The slice opens the interrupts and none arrives (D3); every device it reaches is answered at an entry, so its
    ledgers are EMPTY on both shores — the probes' DMA/FDC writes are on no shore's."""
    _machine, the_rom_s, ours = a_pair
    for shore in (the_rom_s, ours):
        assert all(not getattr(shore.slice, ledger) for ledger in bl.LEDGERS)


def test_the_stores_apart_lie_in_the_bios_stack_s_dead_frames_alone(a_pair):
    """Unmapped, the megabytes differ in THE RESIDUE alone (the capture's own MASK field: the BIOS stack under its top),
    and nothing is stored below it — the frames apart are each shore's own depths (hdv_boot one call nearer the top on
    ours). The residue is dead at `$fc047a`: B4's `test_the_capture_s_masked_bytes_are_read_by_no_run_to_gem_entry`."""
    _machine, the_rom_s, ours = a_pair
    lo, hi = bl.STACK_RESIDUE
    differing = [at for at, (one, other) in enumerate(zip(the_rom_s.slice.machine.ram, ours.slice.machine.ram)) if one != other]
    assert differing and lo <= min(differing) and max(differing) < hi
    below = range(lo - (hi - lo), lo)
    for shore in (the_rom_s, ours):
        assert not [start for start, length in shore.slice.stored if start < below.stop and below.start < start + length]


def test_our_own_cost_is_pinned_exactly(a_pair):
    """COST IS THE ONLY SURFACE of the C's shape where every other surface holds (the scan's loop, the BCBs' stores), so
    each arm's own cycles are pinned."""
    _machine, the_rom_s, ours = a_pair
    assert (ours.own, the_rom_s.own) == OWN_CYCLES


OWN_CYCLES = (115_906, 136_546)         # ours, the ROM's: the same on WARM and COLD (the slice reads nothing they differ in)


# ---- THE END SURFACE: the mid-boot capture ---------------------------------------------------------------------------------
def test_the_end_surface_is_the_capture_but_the_classes_named():
    """COLD — the capture is a power-on's boot — reaches `$fc047a` on both shores equal to the capture outside its MASK
    but for D1 (the cold arm's memctrl on the flat megabyte: D6, memctrl, D6's copy where the BIOS framed it) and D4 (the
    lower floppy driver's scratch D2 / A1 and its own state in [$9f6, $a54)) — the same on both shores, pinned exactly."""
    capture = boot.midboot_machine()
    rom, ours = bl.against_the_capture(bl.the_rom_s(boot.COLD), capture), bl.against_the_capture(bl.our_side(boot.COLD), capture)
    assert rom == ours
    registers, differing = ours
    assert registers == set(bl.END_REGISTERS_OWED)
    lower = {at for at in differing if bl.LOWER_DRIVER_STATE[0] <= at < bl.LOWER_DRIVER_STATE[1]}
    assert differing - lower == set(bl.MEMCTRL_COPIES)
    assert sorted(lower) == LOWER_DRIVER_BYTES_APART


LOWER_DRIVER_BYTES_APART = [0x9f7, 0xa0d, 0xa14, 0xa15, 0xa24, 0xa25, 0xa26, 0xa27, 0xa2a, 0xa2b, 0xa2e, 0xa31, 0xa37,
                            0xa39, 0xa3b, 0xa3d, 0xa3e, 0xa3f, 0xa42, 0xa43, 0xa4a, 0xa4b, 0xa4f, 0xa53]


def test_the_memctrl_copies_are_the_cold_arm_s_own():
    """D1 named, not assumed: the capture's ST holds memctrl $05, the oracle's flat megabyte sizes $08 — in memctrl and in
    D6's low byte where the BIOS framed D6 below savptr (the register save area: D3 at $90c, a longword each)."""
    capture = boot.midboot_machine()
    ours = bl.our_side(boot.COLD).slice.machine
    memctrl, framed = bl.MEMCTRL_COPIES
    assert (capture.ram[memctrl], ours.ram[memctrl]) == (capture.registers["d6"], ours.registers["d6"]) == (0x05, 0x08)
    assert (capture.ram[framed], ours.ram[framed]) == (0x05, 0x08)


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_b4_s_open_carry_closes_a3_a4_a6_are_the_capture_s(machine):
    """B4's OPEN CARRY: A3, A4 and A6 at `$fc047a` reach the pre-init machine (the BIOS process's basepage). On both shores,
    from the ROM's machine at `$fc0452`, they are the capture's: A6 the ACSI probe's answer (its `lea $ffff8606,a6`), A3
    the RS232 table B3's ROM init leaves ($fc2522 `movea.l #$fc25a0,a3` — which B3's C does NOT leave: owed there), A4
    what the ROM's routines before $fc0452 leave."""
    capture = boot.midboot_machine()
    for shore in (bl.the_rom_s(machine), bl.our_side(machine)):
        held = shore.slice.machine.registers
        assert {name: held[name] for name in ("a3", "a4", "a6")} == {name: capture.registers[name] for name in ("a3", "a4", "a6")}
    assert _at(RS232_TABLE_LOADED) == f"moveal #{C['ROM_RS232_HANDLER_TABLE']},%a3" and capture.registers["a3"] == C["ROM_RS232_HANDLER_TABLE"]


def test_the_warm_machine_is_no_power_on_s_and_differs_where_its_ram_was_the_desk_s():
    """WHY THE END SURFACE IS COLD's: WARM keeps the RAM the head's clears do not reach — the post-boot snapshot's
    (a desk's) above $10000 and the shell's environment at $840 — where the capture's power-on holds zeros."""
    capture = boot.midboot_machine()
    _registers, differing = bl.against_the_capture(bl.our_side(boot.WARM), capture)
    assert any(at >= 0x10000 for at in differing) and any(0x840 <= at < 0x850 for at in differing)


# ---- EACH SURFACE'S NEGATIVE ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cold_pair():
    return bl.the_rom_s(boot.COLD), bl.our_side(boot.COLD)


def _with_slice(shore, **changes):
    return shore._replace(slice=shore.slice._replace(**changes))


def _ram_changed(shore, at, value):
    ram = bytearray(shore.slice.machine.ram)
    ram[at] = value
    return _with_slice(shore, machine=shore.slice.machine._replace(ram=bytes(ram)))


def _registers_changed(shore, **changes):
    return _with_slice(shore, machine=shore.slice.machine._replace(registers={**shore.slice.machine.registers, **changes}))


def test_each_held_surface_changed_alone_is_named(cold_pair):
    the_rom_s, ours = cold_pair
    changed = {
        "stop": _with_slice(ours, stop=bl.SPAN[0]),
        "registers": _registers_changed(ours, d2=ours.slice.machine.registers["d2"] ^ 1),
        "ram": _ram_changed(ours, addrs.GEMDOS_DATE, ours.slice.machine.ram[addrs.GEMDOS_DATE] ^ 1),
        "stored": _with_slice(ours, stored=(*ours.slice.stored, (bl.STACK_RESIDUE[0] - 2, 1))),
        **{ledger: _with_slice(ours, **{ledger: (*getattr(ours.slice, ledger), ("a staged entry",))}) for ledger in bl.LEDGERS},
        "answers": ours._replace(answers=ours.answers[:-1]),
    }
    assert set(changed) == {*bl.SURFACES, "answers"}
    for surface, shore in changed.items():
        found = bl.differences(the_rom_s, shore)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


@pytest.mark.parametrize("register", boot.REGISTER_NAMES)
def test_every_register_is_held(cold_pair, register):
    the_rom_s, ours = cold_pair
    found = bl.differences(the_rom_s, _registers_changed(ours, **{register: ours.slice.machine.registers[register] ^ 1}))
    assert len(found) == 1 and found[0].startswith("registers")


def test_the_residue_alone_is_not_held(cold_pair):
    """A byte just above and just below the residue is seen; one inside it is not."""
    the_rom_s, ours = cold_pair
    lo, hi = bl.STACK_RESIDUE
    for at, seen in ((lo - 1, True), (lo, False), (hi - 1, False), (hi, True)):
        found = bl.differences(the_rom_s, _ram_changed(ours, at, ours.slice.machine.ram[at] ^ 0xff))
        assert bool(found) == seen, (hex(at), found)


# ---- ITS PRICE (ruling D9): the table's rows ------------------------------------------------------------------------------
def test_the_table_prices_both_machines_on_each_shore_s_own_cycles_under_the_bar():
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_late_slice(row)]
    assert [row.registered for row in rows] == list(bl.SLICES)
    bench = tier3.RomBench()
    for row in rows:
        machine = bl.SLICES[row.registered]
        assert (row.entry, row.symbol) == (bl.SPAN[0], bl.ENTRY_SYMBOL)
        priced, measured = bl.priced(machine), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


class _OursOwnReadShort:
    emu = bl.emu

    def __getattr__(self, name):
        return getattr(self.emu, name)

    def prof_cycles(self, lo, hi):
        return self.emu.prof_cycles(lo, hi) - (4 if lo == bl.product().base else 0)


def test_the_rest_beside_each_shore_s_own_is_held_equal_in_the_price(monkeypatch):
    monkeypatch.setattr(bl, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="beside its own, ours spent"):
        bl.priced(boot.COLD)
